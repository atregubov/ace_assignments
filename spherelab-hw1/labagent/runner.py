"""Manage each lab session's history, tool calls, and resource limits."""
import asyncio
from labagent.dispatcher import Dispatcher
from labagent.limits import (
    OUTER_DEADLINE_SECONDS, OUTER_MAX_OUTPUT_TOKENS, OUTER_MODEL_ATTEMPTS,
    OUTER_REQUEST_TIMEOUT_SECONDS, OUTER_RESULT_BYTES, OUTER_TOTAL_RESULT_BYTES,
)
from labagent.types import BudgetExceeded, ModelError
from labagent.utils import to_canonical_json_string


class Runner:
    def __init__(self, runtime, policies, task):
        self.rt, self.p = runtime, policies
        self.dispatcher = Dispatcher(runtime, policies)
        self.system = policies.prompt_defense.system_text(task)
        self.system += "\nRequest at most one tool per turn and wait for its result."
        self.history = [{"role": "user", "content": task}]
        self.model_requests = []
        self.final, self.error = None, None

    def reserve_model(self):
        """Reserve one model request; return its (output-token cap, timeout in seconds)."""
        r, budget = self.rt, self.p.budget
        if r.model_attempts >= OUTER_MODEL_ATTEMPTS or r.clock.now() >= OUTER_DEADLINE_SECONDS:
            raise BudgetExceeded("outer_run_limit")
        budget.reserve("model", r)
        timeout = min(OUTER_REQUEST_TIMEOUT_SECONDS, OUTER_DEADLINE_SECONDS - r.clock.now(), budget.timeout(r))
        max_tokens = min(OUTER_MAX_OUTPUT_TOKENS, budget.output_limit(r))
        r.model_attempts += 1
        self.dispatcher.emit("model_request")
        return max_tokens, timeout

    def check_deadline(self):
        if self.rt.clock.now() >= OUTER_DEADLINE_SECONDS:
            raise BudgetExceeded("outer_run_limit")
        self.p.budget.after_call(self.rt)

    def execute_tool(self, action):
        self.check_deadline()
        result = self.dispatcher.execute(action)
        encoded = to_canonical_json_string(result)
        size = len(encoded.encode())
        if size > OUTER_RESULT_BYTES or self.rt.result_bytes + size > OUTER_TOTAL_RESULT_BYTES:
            raise BudgetExceeded("outer_context_bytes")
        self.p.budget.admit(encoded, self.rt)
        self.rt.result_bytes += size
        self.rt.context_docs.extend(self.rt.pending_docs)
        wrapped = self.p.prompt_defense.wrap_result(result)
        self.history.extend([
            {"action": action.as_dict(), "call_id": action.call_id},
            {"result": result, "wrapped": wrapped, "call_id": action.call_id},
        ])
        return wrapped

    def run(self, model):
        try:
            self.final = asyncio.run(model.run_session(self))
            reason = "final_answer"
        except BudgetExceeded as exc:
            reason = str(exc)
        except ModelError as exc:
            self.error, reason = str(exc), "infrastructure_error"
        self.rt.terminal_reason = reason
        self.dispatcher.emit("run_end", outcome=reason)
        return self
