from lab.types import digest


def event(runtime, kind, action=None, decision=None, outcome=None):
    return {"run_id": runtime.run_id, "event_id": f"{runtime.run_id}:{len(runtime.events)}",
            "parent_event": runtime.events[-1]["event_id"] if runtime.events else None,
            "principal": runtime.context.user_id, "tenant": runtime.context.tenant_id,
            "kind": kind, "tool": action.tool if action else None,
            "argument_digest": digest(action.args) if action else None,
            "decision": decision, "outcome": outcome,
            "model_attempts": runtime.model_attempts, "tool_attempts": runtime.tool_attempts,
            "input_tokens": runtime.input_tokens, "output_tokens": runtime.output_tokens,
            "usage_unknown": runtime.usage_unknown, "elapsed": runtime.clock.now(),
            "stop_reason": runtime.terminal_reason, "source_id": runtime.last_source}
