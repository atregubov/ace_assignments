"""All model proposals use one dispatcher in both available execution engines."""
from lab.dispatcher import Dispatcher
from lab.types import BudgetExceeded, ModelError, canonical


class Runner:
    def __init__(self, runtime, policies, model, task, quota=None):
        self.rt, self.p, self.model, self.quota = runtime, policies, model, quota
        self.dispatcher = Dispatcher(runtime, policies)
        self.system = policies.prompt_defense.system_text(task)
        self.history = [{"role": "user", "content": task}]
        self.final, self.error = None, None
        self.done = False

    def step(self):
        r, p = self.rt, self.p
        if self.done:
            return
        try:
            # Trusted outer bounds also protect intentionally vulnerable snapshots.
            if r.model_attempts >= 12 or r.clock.now() >= 120:
                raise BudgetExceeded("outer_run_limit")
            p.budget.reserve("model", r)
            if self.quota:
                self.quota.reserve()
            timeout = min(30.0, 120 - r.clock.now(), p.budget.timeout(r))
            max_tokens = min(1024, p.budget.output_limit(r))
            r.model_attempts += 1
            self.dispatcher.emit("model_request")
            reply = self.model.generate(self.system, self.history, max_tokens, timeout, r)
            r.input_tokens += reply.input_tokens
            r.output_tokens += reply.output_tokens
            if not reply.usage_known:
                r.usage_unknown += 1
            p.budget.after_call(r)  # late proposals must never reach the dispatcher
            if reply.final is not None:
                self.final = reply.final
                r.terminal_reason = "final_answer"
                self.done = True
            else:
                action = reply.action
                result = self.dispatcher.execute(action)
                encoded = canonical(result)
                if len(encoded.encode()) > 32768 or r.result_bytes + len(encoded.encode()) > 65536:
                    raise BudgetExceeded("outer_context_bytes")
                p.budget.admit(encoded, r)
                r.result_bytes += len(encoded.encode())
                r.context_docs.extend(r.pending_docs)
                self.history.extend([
                    {"action": action.as_dict(), "call_id": action.call_id},
                    {"result": result, "wrapped": p.prompt_defense.wrap_result(result), "call_id": action.call_id},
                ])
        except BudgetExceeded as e:
            r.terminal_reason = str(e)
            self.done = True
        except ModelError as e:
            r.usage_unknown += 1
            self.error = str(e)
            r.terminal_reason = "infrastructure_error"
            self.done = True
        if self.done:
            self.dispatcher.emit("run_end", outcome=r.terminal_reason)

    def run(self, engine="python"):
        if engine == "langgraph":
            from agent.langgraph_engine import execute
            execute(self)
        elif engine == "python":
            while not self.done:
                self.step()
        else:
            raise ValueError("Unknown engine")
        return self
