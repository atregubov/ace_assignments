"""Tool schemas, local SDK callbacks, and shared JSON and hash helpers."""
from __future__ import annotations

import hashlib
import json
from functools import partial
from typing import TYPE_CHECKING, Any

from labagent.limits import MAX_ARGUMENT_BYTES, MAX_TOOL_ARGUMENTS_BYTES
from labagent.types import Action, ModelError, PolicyDenied

if TYPE_CHECKING:
    from agents import FunctionTool
    from agents.tool_context import ToolContext
    from labagent.runner import Runner


def to_canonical_json_string(value: Any) -> str:
    """Serialize JSON with sorted keys, compact separators and Unicode characters."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def to_hash_string(value: Any) -> str:
    """Return the SHA-256 hex digest of a value's canonical JSON."""
    return hashlib.sha256(to_canonical_json_string(value).encode()).hexdigest()


PAYMENT = {"account": str, "payee": str, "amount_cents": int, "currency": str,
           "document_id": str, "document_version": int, "operation_id": str}
SCHEMAS = {
    "search_docs": ({"query": str}, {}),
    "read_doc": ({"doc_id": str}, {}),
    "send_message": ({"recipient": str, "body": str}, {}),
    "propose_payment": (PAYMENT, {}),
    "commit_payment": ({**PAYMENT, "approval_id": str}, {}),
    "remember": ({"key": str, "value": str}, {"confirmation_id": str}),
    "recall": ({}, {}),
    "unstable": ({"mode": str}, {}),
}
IDENTITY = {"user_id": str, "tenant_id": str, "role": str}


def validate(action):
    """Check structure while passing identity-looking fields to assignment 2's policy."""
    if action.tool not in SCHEMAS or not isinstance(action.args, dict):
        raise PolicyDenied("unknown_tool_or_arguments")
    required, optional = SCHEMAS[action.tool]
    fields = {**required, **optional, **IDENTITY}
    if not set(required) <= set(action.args) or not set(action.args) <= set(fields):
        raise PolicyDenied("invalid_fields")
    for k, v in action.args.items():
        if type(v) is not fields[k]:
            raise PolicyDenied("invalid_type")
        if isinstance(v, str) and len(v.encode()) > MAX_ARGUMENT_BYTES:
            raise PolicyDenied("argument_too_large")


def tool_specs():
    descriptions = {
        "search_docs": "Search fixture documents and return authorized snippets.",
        "read_doc": "Read a fixture document by its ID.",
        "send_message": "Record a message in the LOCAL simulated outbox. No real mail.",
        "propose_payment": "Create a simulated payment proposal for a human reviewer.",
        "commit_payment": "Commit a previously approved simulated payment.",
        "remember": "Propose a preference memory; confirmation may be required.",
        "recall": "Retrieve active preferences for the authenticated user.",
        "unstable": "Read-only test service; modes transient, oversize, stall, normal.",
    }
    return [{"name": name, "description": descriptions[name],
             "inputSchema": {"type": "object", "properties": {
                 k: {"type": "integer" if v is int else "string"}
                 for k, v in {**req, **opt}.items()},
                 "required": list(req), "additionalProperties": False}}
            for name, (req, opt) in SCHEMAS.items()]


def strict_json(text):
    """Decode native Chat Completions arguments before a tool can run."""
    if not isinstance(text, str):
        raise ModelError("invalid_json_response")
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ModelError("duplicate_json_key")
            obj[key] = value
        return obj

    def nonfinite(_):
        raise ModelError("non_finite_json")

    try:
        if len(text.encode()) > MAX_TOOL_ARGUMENTS_BYTES:
            raise ModelError("model_response_too_large")
        value = json.loads(text, object_pairs_hook=unique, parse_constant=nonfinite)
        # Also reject exponent overflow and lone surrogates inside escaped strings.
        json.dumps(value, allow_nan=False, ensure_ascii=False).encode()
        return value
    except (ValueError, RecursionError) as exc:
        raise ModelError("invalid_json_response") from exc


async def invoke_local(tool_name: str, context: ToolContext[Runner], arguments: str) -> str:
    """The SDK supplies the tool name and call ID. The harness supplies the authenticated session."""
    if context.tool_name != tool_name:
        raise ModelError("tool_name_mismatch")
    args = strict_json(arguments)
    if not isinstance(args, dict):
        raise ModelError("invalid_native_tool_call")
    action = Action(tool_name, args, context.tool_call_id)
    return to_canonical_json_string(context.context.execute_tool(action))


def function_tools() -> list[FunctionTool]:
    """Register the MCP definitions as local SDK functions."""
    # Load SDK dependencies only when constructing tools for model execution.
    from agents import FunctionTool
    from mcp.types import Tool as MCPTool

    definitions = (MCPTool(**spec) for spec in tool_specs())
    return [FunctionTool(name=tool.name, description=tool.description or "",
                         params_json_schema=tool.input_schema, strict_json_schema=False,
                         on_invoke_tool=partial(invoke_local, tool.name)) for tool in definitions]
