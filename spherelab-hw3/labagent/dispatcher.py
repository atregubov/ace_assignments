"""The single path from a model's proposed tool call to fixture state.

``Dispatcher.execute()`` records the proposal, reserves tool budget, validates the arguments,
and asks the active policies before any local service runs. A policy denial becomes an error
result that goes back to the model. ``BudgetExceeded`` propagates and ends the session.
"""
from labagent.limits import OUTER_TOOL_ATTEMPTS, SEARCH_RESULT_LIMIT, SNIPPET_CHARS
from labagent.types import BudgetExceeded, PolicyDenied, TransientToolError
from labagent.utils import validate


class Dispatcher:
    def __init__(self, runtime, policies):
        self.runtime = runtime
        self.policies = policies
        # One handler per registered tool. Each receives the validated action and returns
        # a JSON-serializable result, or raises PolicyDenied / TransientToolError.
        self.tools = {
            "read_doc": self.read_doc,
            "search_docs": self.search_docs,
            "send_message": self.send_message,
            "propose_payment": self.propose_payment,
            "commit_payment": self.commit_payment,
            "remember": self.remember,
            "recall": self.recall_tool,
            "unstable": self.unstable,
        }

    # ----- events and decisions -------------------------------------------------------

    def emit(self, kind, action=None, decision=None, outcome=None):
        """Build an event with the audit policy, then keep it in memory and in SQLite."""
        row = self.policies.audit.event(self.runtime, kind, action, decision, outcome)
        self.runtime.events.append(row)
        self.runtime.store.record("audit", row, row["event_id"])

    def require(self, decision):
        if not decision.allowed:
            raise PolicyDenied(decision.reason)

    # ----- the checked path -----------------------------------------------------------

    def execute(self, action):
        """Check one proposed action, run it if every policy allows it, and return the result.

        Order: proposal event -> tool budget -> schema validation -> task gate -> authorization
        -> tool-specific checks inside the handler (retrieval, egress, memory, approval).
        """
        runtime, policies = self.runtime, self.policies
        runtime.pending_docs = []
        self.emit("proposal", action)
        policies.budget.reserve("tool", runtime)
        if runtime.tool_attempts >= OUTER_TOOL_ATTEMPTS:
            raise BudgetExceeded("outer_tool_limit")
        runtime.tool_attempts += 1  # failed and denied attempts count too
        try:
            validate(action)
            self.require(policies.task_gate.check(runtime.context, action, runtime))
            self.require(policies.authorize.check(runtime.context, action, runtime))
            handler = self.tools.get(action.tool)
            if handler is None:
                raise PolicyDenied("unimplemented_tool")
            result = handler(action)
            self.emit("tool_result", action, "allow", "executed")
            return result
        except PolicyDenied as exc:
            self.emit("tool_result", action, "deny", str(exc))
            return {"error": "policy_denied", "reason": str(exc)}
        except TransientToolError as exc:
            self.emit("tool_result", action, "allow", "transient_error")
            return {"error": str(exc)}

    # ----- documents ------------------------------------------------------------------

    def read_doc(self, action):
        doc = self.runtime.store.get("docs", action.args["doc_id"])
        self.require(self.policies.retrieval.check(self.runtime.context, doc, self.runtime))
        return self.document(doc)

    def search_docs(self, action):
        # Filter by access *before* ranking, so unauthorized titles and snippets never reach
        # the model. There is deliberately no result cache that could be shared across users.
        retrieval, runtime = self.policies.retrieval, self.runtime
        terms = action.args["query"].lower().split()

        def hits(doc):
            text = (doc["title"] + doc["body"]).lower()
            return sum(term in text for term in terms)

        visible = [d for d in runtime.store.objects("docs") if retrieval.check(runtime.context, d, runtime).allowed]
        matches = sorted((d for d in visible if hits(d) > 0), key=lambda d: (-hits(d), d["id"]))
        return {"documents": [self.document(d, snippet=True) for d in matches[:SEARCH_RESULT_LIMIT]]}

    def document(self, doc, snippet=False):
        """Return a document to the model and record that it entered the context."""
        self.policies.retrieval.observe(doc, self.runtime)
        self.runtime.pending_docs.append(doc["id"])
        self.runtime.last_source = doc["id"]
        body = doc["body"][:SNIPPET_CHARS] if snippet else doc["body"]
        return {"id": doc["id"], "title": doc["title"], "body": body,
                "label": doc["label"], "version": doc["version"]}

    # ----- messages and payments ------------------------------------------------------

    def send_message(self, action):
        runtime, args = self.runtime, action.args
        self.require(self.policies.egress.check(runtime.context, action, runtime))
        return runtime.store.record("outbox", {
            "user_id": runtime.context.user_id, "tenant_id": runtime.context.tenant_id,
            "recipient": args["recipient"], "body": args["body"],
            "internal_projects": sorted(runtime.internal_projects), "run_id": runtime.run_id,
        })

    def propose_payment(self, action):
        context = self.runtime.context
        return self.runtime.store.record("proposals", {
            "user_id": context.user_id, "tenant_id": context.tenant_id,
            "args": dict(action.args), "status": "pending_review",
        })

    def commit_payment(self, action):
        return self.policies.approval.commit(self.runtime.context, action, self.runtime)

    # ----- memory ---------------------------------------------------------------------

    def remember(self, action):
        runtime, args = self.runtime, action.args
        # Origin comes from the trusted ingestion path: if no document has been read in this
        # session yet, the candidate can only have come from the user's task.
        row = {"user_id": runtime.context.user_id, "tenant_id": runtime.context.tenant_id,
               "key": args["key"], "value": args["value"], "schema_version": 1,
               "origin": "user_preference" if runtime.last_source == "task" else "tool_result",
               "source_id": runtime.last_source, "confirmation_id": args.get("confirmation_id"),
               "created_at": runtime.clock.now(), "status": "candidate"}
        decision = self.policies.memory.check(runtime.context, row, runtime)
        row["status"] = "active" if decision.allowed else "candidate"
        row["reason"] = decision.reason
        stored = runtime.store.record("memories", row)
        return {"id": stored["id"], "status": stored["status"], "reason": stored["reason"]}

    def recall_tool(self, action):
        return {"memories": self.recall()}

    def recall(self):
        """Return active memories that pass the memory policy now; quarantine the user's own failures."""
        runtime, result = self.runtime, []
        for row in runtime.store.rows("memories"):
            if row["status"] != "active":
                continue
            decision = self.policies.memory.check(runtime.context, row, runtime)
            if decision.allowed:
                result.append(row)
            elif row["user_id"] == runtime.context.user_id and row["tenant_id"] == runtime.context.tenant_id:
                runtime.store.record("memories", {**row, "status": "quarantined", "reason": decision.reason}, row["id"])
        runtime.memory_active = result
        return result

    # ----- fault injection (assignment 6) ---------------------------------------------

    def unstable(self, action):
        mode = action.args["mode"]
        if mode == "transient":
            raise TransientToolError("simulated_transient_failure")
        if mode == "oversize":
            return {"body": "x" * 20000}
        if mode == "stall":
            if not self.runtime.clock.virtual:
                raise PolicyDenied("virtual_fault_only")
            self.runtime.clock.advance(95)  # past the 90 s policy deadline, on the test clock only
            return {"body": "late read-only result"}
        if mode == "normal":
            return {"body": "service healthy"}
        raise PolicyDenied("unknown_fault_fixture")
