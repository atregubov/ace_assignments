"""Configure Chat Completions and run the tool-using agent with per-request limits."""
import asyncio
import os
from dataclasses import replace
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from labagent.limits import MAX_MODEL_RESPONSE_BYTES, MAX_PROMPT_BYTES, SDK_MAX_TURNS
from labagent.types import BudgetExceeded, ModelError
from labagent.utils import function_tools, to_canonical_json_string

try:
    from agents import (
        Agent, Model, ModelRetrySettings, ModelSettings, OpenAIChatCompletionsModel,
        RunConfig, Runner as SDKRunner,
    )
    from agents.exceptions import AgentsException
    from openai import APIStatusError, APITimeoutError, AsyncOpenAI, DefaultAsyncHttpxClient
except ModuleNotFoundError as exc:
    raise RuntimeError("Install the agent dependencies with python -m pip install -r requirements.txt") from exc


class OpenAIModel:
    """Configure the provider client and use it for one agent session at a time."""

    backend, api = "openai", "chat.completions"

    def __init__(self, *, model_id=None, base_url=None, api_key=None, temperature=0,
                 token_limit_field="max_tokens"):
        if token_limit_field not in {"max_tokens", "max_completion_tokens"}:
            raise ValueError("Choose max_tokens or max_completion_tokens for the output-token limit")
        self.token_limit_field = token_limit_field
        self.temperature = None if temperature in ("default", None) else float(temperature)
        if self.temperature is not None and not 0 <= self.temperature <= 2:
            raise ValueError("Use a temperature from 0 to 2, or default for provider-controlled sampling")
        self.model_id = model_id or os.getenv("OPENAI_MODEL")
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.model_id or not self._api_key:
            raise ValueError("Set OPENAI_MODEL and OPENAI_API_KEY, or supply --model and --api-key")
        url = urlsplit(base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1")
        if (url.scheme not in {"http", "https"} or not url.hostname or
                url.username is not None or url.password is not None or url.fragment):
            raise ValueError("Use an HTTP(S) API base URL without embedded credentials or fragments")
        self.base_url = urlunsplit((url.scheme, url.netloc, url.path.rstrip("/"), "", ""))
        self._query = dict(parse_qsl(url.query, keep_blank_values=True))

    async def run_session(self, runner):
        try:
            async with AsyncOpenAI(
                base_url=self.base_url, api_key=self._api_key, default_query=self._query,
                max_retries=0, http_client=DefaultAsyncHttpxClient(follow_redirects=False),
            ) as client:
                model = OpenAIChatCompletionsModel(model=self.model_id, openai_client=client)
                return await run_session(runner, model, temperature=self.temperature,
                                         token_limit_field=self.token_limit_field)
        except (BudgetExceeded, ModelError):
            raise
        except Exception as exc:
            raise ModelError(f"live_session_{type(exc).__name__}") from None


def validate_turn(response):
    """Validate the whole turn before the SDK can schedule even one tool."""
    calls = [item for item in response.output if item.type == "function_call"]
    if len(calls) > 1:
        raise ModelError("multiple_tool_calls_not_supported")
    if any(item.type not in {"message", "function_call", "reasoning"} for item in response.output):
        raise ModelError("unsupported_model_output")
    if not calls:
        if not any(getattr(part, "text", None) or getattr(part, "refusal", None)
                   for item in response.output if item.type == "message" for part in item.content):
            raise ModelError("empty_model_response")
        return
    call = calls[0]
    if not isinstance(call.call_id, str) or not call.call_id.isprintable() or not 1 <= len(call.call_id) <= 256:
        raise ModelError("invalid_tool_call_id")
    if not isinstance(call.name, str) or not call.name:
        raise ModelError("invalid_native_tool_call")


class BoundedModel(Model):
    """Reserve and account for one provider call before the Agents SDK executes tools."""

    def __init__(self, chat_model, runner, token_limit_field):
        self.chat_model, self.runner = chat_model, runner
        self.token_limit_field = token_limit_field

    def stream_response(self, *args, **kwargs):
        raise ModelError("This harness processes complete, non-streaming model turns")

    async def get_response(self, system_instructions, input, model_settings, tools,
                           output_schema, handoffs, tracing, **options):
        run = self.runner
        schemas = [(t.name, t.description, t.params_json_schema) for t in tools]
        if len(to_canonical_json_string([system_instructions, input, schemas]).encode()) > MAX_PROMPT_BYTES:
            raise ModelError("outer_prompt_bytes")

        cap, timeout = run.reserve_model()
        field = self.token_limit_field
        settings = replace(model_settings, timeout=timeout, preserve_raw_usage=True,
                           max_tokens=cap if field == "max_tokens" else None,
                           extra_args={"max_completion_tokens": cap} if field == "max_completion_tokens" else None)
        request = {"attempt": run.rt.model_attempts, "max_output_tokens": cap, "token_limit_field": field,
                   "timeout_seconds": timeout,
                   "temperature": settings.temperature, "input_tokens": None, "output_tokens": None}
        run.model_requests.append(request)
        try:
            async with asyncio.timeout(timeout):
                # OpenAIChatCompletionsModel calls the supplied AsyncOpenAI client's
                # chat.completions.create and returns the SDK's normalized tool calls.
                response = await self.chat_model.get_response(
                    system_instructions, input, settings, tools, output_schema, handoffs, tracing, **options
                )
        except (TimeoutError, APITimeoutError):
            run.rt.usage_unknown += 1
            raise ModelError("provider_timeout_usage_unknown") from None
        except APIStatusError as exc:
            run.rt.usage_unknown += 1
            raise ModelError(f"provider_http_{exc.status_code}") from None
        except Exception as exc:
            # Provider bodies and exception messages can contain sensitive input.
            run.rt.usage_unknown += 1
            raise ModelError(f"provider_{type(exc).__name__}") from None
        usage = response.raw_usage or {}
        for provider_key, key in (("prompt_tokens", "input_tokens"), ("completion_tokens", "output_tokens")):
            count = usage.get(provider_key)
            if type(count) is int and count >= 0:
                request[key] = count
                setattr(run.rt, key, getattr(run.rt, key) + count)
        if request["input_tokens"] is None or request["output_tokens"] is None:
            run.rt.usage_unknown += 1
        run.check_deadline()
        if sum(len(item.model_dump_json().encode()) for item in response.output) > MAX_MODEL_RESPONSE_BYTES:
            raise ModelError("model_response_too_large")
        validate_turn(response)
        return response


async def run_session(runner, chat_model, *, temperature, token_limit_field):
    """Run the SDK agent with the lab runner as the trusted context for local tools."""
    agent = Agent(
        name="Spherelab Agent", instructions=runner.system, tools=function_tools(),
        model=BoundedModel(chat_model, runner, token_limit_field),
        model_settings=ModelSettings(temperature=temperature, retry=ModelRetrySettings(max_retries=0)),
    )
    try:
        result = await SDKRunner.run(
            agent, input=runner.history[0]["content"], context=runner, max_turns=SDK_MAX_TURNS,
            run_config=RunConfig(tracing_disabled=True, trace_include_sensitive_data=False),
        )
    except AgentsException as exc:
        # The SDK wraps callback errors in UserError. Preserve the lab's terminal reason.
        if isinstance(exc.__cause__, (BudgetExceeded, ModelError)):
            raise exc.__cause__ from None
        raise ModelError(f"agent_{type(exc).__name__}") from None
    return result.final_output
