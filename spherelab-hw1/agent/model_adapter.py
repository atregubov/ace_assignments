"""One strict response envelope for mock, Bedrock Converse JSON and native tools.

Mock is scripted action simulation, NEVER evidence of model injection resistance.
Bedrock runs in a cancellable child process. No inference credentials enter traces.
"""
from dataclasses import dataclass
import json
import multiprocessing
import os
import re
from lab.schema import tool_specs
from lab.types import Action, ModelError, canonical


@dataclass
class Reply:
    action: Action | None = None
    final: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    usage_known: bool = True


def _unique_object(pairs):
    obj = {}
    for k, v in pairs:
        if k in obj:
            raise ModelError("duplicate_json_key")
        obj[k] = v
    return obj


def parse_json(text):
    if len(text.encode()) > 65536:
        raise ModelError("model_response_too_large")
    try:
        obj = json.loads(text, object_pairs_hook=_unique_object,
                         parse_constant=lambda _: (_ for _ in ()).throw(ModelError("non_finite_json")))
    except (ValueError, TypeError) as e:
        raise ModelError("invalid_json_response") from e
    if isinstance(obj, dict) and set(obj) == {"final"} and isinstance(obj["final"], str):
        return Reply(final=obj["final"])
    if isinstance(obj, dict) and set(obj) == {"tool", "args"} and isinstance(obj["tool"], str) and isinstance(obj["args"], dict):
        return Reply(action=Action(obj["tool"], obj["args"]))
    raise ModelError("invalid_response_envelope")


class MockModel:
    backend, model_id, api, region = "mock", "scripted-simulator-v1", "local", "local"

    def __init__(self, script, *, late_at=None, failures=0):
        self.script = list(script)
        self.index = 0
        self.late_at, self.failures = late_at, failures

    def generate(self, system, history, max_tokens, timeout, runtime):
        if self.failures:
            self.failures -= 1
            raise ModelError("simulated_provider_error")
        if self.late_at == self.index:
            runtime.clock.advance(95)
        item = self.script[self.index] if self.index < len(self.script) else {"final": "Task complete."}
        self.index += 1
        # Explicit substitution makes a replay depend on actually retrieved data.
        def resolve(value):
            if value == "$last.body":
                for turn in reversed(history):
                    if "result" in turn:
                        return str(turn["result"].get("body", "No accessible document."))
            if value == "$last.memories":
                for turn in reversed(history):
                    if "result" in turn:
                        return canonical(turn["result"].get("memories", []))
            return value
        item = json.loads(canonical(item))
        if "args" in item:
            item["args"] = {k: resolve(v) for k, v in item["args"].items()}
        if "final" in item:
            item["final"] = resolve(item["final"])
        reply = parse_json(canonical(item))
        # Simulator has no actual token usage; do not invent billed token counts.
        reply.usage_known = False
        return reply


def converse_request(model_id, system, history, max_tokens, mode):
    messages = []
    if mode == "json":
        system += ('\nReturn ONLY one JSON object: {"tool":"name","args":{...}} or {"final":"answer"}. '
                   'No markdown, code blocks, or reasoning text. Tool schemas: ' + canonical(tool_specs()))
    for h in history:
        if "action" in h:
            a = h["action"]
            content = [{"text": canonical(a)}] if mode == "json" else [{"toolUse": {
                "toolUseId": h["call_id"], "name": a["tool"], "input": a["args"]}}]
            messages.append({"role": "assistant", "content": content})
        elif "result" in h:
            content = [{"text": "UNTRUSTED TOOL RESULT " + canonical(h["wrapped"])}] if mode == "json" else [{"toolResult": {
                "toolUseId": h["call_id"], "content": [{"json": h["wrapped"]}]}}]
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": h["role"], "content": [{"text": h["content"]}]})
    request = {"modelId": model_id, "system": [{"text": system}], "messages": messages,
               "inferenceConfig": {"maxTokens": max_tokens, "temperature": 0.0}}
    if mode == "native":
        request["toolConfig"] = {"tools": tool_specs()}
    if len(canonical(request).encode()) > 131072:
        raise ModelError("outer_prompt_bytes")
    return request


def parse_converse(response, mode):
    blocks = response.get("output", {}).get("message", {}).get("content", [])
    calls = [b["toolUse"] for b in blocks if "toolUse" in b]
    if mode == "native" and calls:
        if len(calls) != 1:
            raise ModelError("multiple_tool_calls_not_supported")
        c = calls[0]
        if not isinstance(c.get("name"), str) or not isinstance(c.get("input"), dict):
            raise ModelError("invalid_native_tool_call")
        call_id = c.get("toolUseId", "")
        if not isinstance(call_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", call_id):
            raise ModelError("invalid_tool_call_id")
        reply = Reply(action=Action(c["name"], c["input"], call_id))
    else:
        text = "".join(b.get("text", "") for b in blocks)
        if not text:
            raise ModelError("empty_model_response")
        reply = parse_json(text) if mode == "json" else Reply(final=text)
    usage = response.get("usage", {})
    reply.input_tokens = usage.get("inputTokens", 0)
    reply.output_tokens = usage.get("outputTokens", 0)
    reply.usage_known = "inputTokens" in usage and "outputTokens" in usage
    return reply


def _bedrock_worker(pipe, request, region, timeout):
    try:
        import boto3
        from botocore.config import Config
        # total_max_attempts includes the initial request. No invisible SDK retry.
        client = boto3.client("bedrock-runtime", region_name=region, config=Config(
            connect_timeout=min(10, timeout), read_timeout=timeout,
            retries={"total_max_attempts": 1, "mode": "standard"}))
        response = client.converse(**request)
        response.pop("ResponseMetadata", None)
        if len(canonical(response).encode()) > 131072:
            pipe.send({"error": "response_too_large"})
        else:
            pipe.send({"response": response})
    except Exception as e:
        # Never return exception strings (may contain endpoints or credential data).
        code = getattr(e, "response", {}).get("Error", {}).get("Code", type(e).__name__)
        pipe.send({"error": str(code)[:80]})
    finally:
        pipe.close()


class BedrockModel:
    backend = "bedrock"

    def __init__(self, model_id=None, region=None, mode="json"):
        self.model_id = model_id or os.getenv("BEDROCK_MODEL_ID", "")
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self.mode = mode
        self.api = "converse-" + mode
        if not self.model_id or mode not in {"json", "native"}:
            raise ValueError("Set BEDROCK_MODEL_ID and choose json or native")

    def generate(self, system, history, max_tokens, timeout, runtime):
        request = converse_request(self.model_id, system, history, max_tokens, self.mode)
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe(duplex=False)
        proc = context.Process(target=_bedrock_worker, args=(child, request, self.region, timeout), daemon=True)
        proc.start()
        child.close()
        try:
            if not parent.poll(timeout):
                raise ModelError("provider_timeout_usage_unknown")
            message = parent.recv()
            if "error" in message:
                raise ModelError(message["error"])
            return parse_converse(message["response"], self.mode)
        except EOFError as e:
            raise ModelError("provider_worker_failed") from e
        finally:
            parent.close()
            if proc.is_alive():
                proc.terminate()
            proc.join(timeout=2)

