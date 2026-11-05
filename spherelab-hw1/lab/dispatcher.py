import uuid
from lab.schema import validate
from lab.types import PolicyDenied, TransientToolError, canonical


class Dispatcher:
    def __init__(self, runtime, policies):
        self.rt, self.p = runtime, policies

    def emit(self, kind, action=None, decision=None, outcome=None):
        row = self.p.audit.event(self.rt, kind, action, decision, outcome)
        self.rt.events.append(row)
        self.rt.store.record("audit", row, row["event_id"])

    def require(self, decision):
        if not decision.allowed:
            raise PolicyDenied(decision.reason)

    def execute(self, action):
        r, p = self.rt, self.p
        r.pending_docs = []
        self.emit("proposal", action)
        p.budget.reserve("tool", r)
        if r.tool_attempts >= 16:
            from lab.types import BudgetExceeded
            raise BudgetExceeded("outer_tool_limit")
        r.tool_attempts += 1
        try:
            validate(action)
            self.require(p.task_gate.check(r.context, action, r))
            self.require(p.authorize.check(r.context, action, r))
            args = action.args
            if action.tool == "read_doc":
                doc = r.store.get("docs", args["doc_id"])
                self.require(p.retrieval.check(r.context, doc, r))
                result = self.document(doc)
            elif action.tool == "search_docs":
                # No content cache: avoid sharing a retrieval cache across principals.
                docs = [d for d in r.store.objects("docs") if p.retrieval.check(r.context, d, r).allowed]
                terms = args["query"].lower().split()
                docs = sorted(docs, key=lambda d: (-sum(t in (d["title"] + d["body"]).lower() for t in terms), d["id"]))
                docs = [d for d in docs if any(t in (d["title"] + d["body"]).lower() for t in terms)][:3]
                result = {"documents": [self.document(d, snippet=True) for d in docs]}
            elif action.tool == "send_message":
                self.require(p.egress.check(r.context, action, r))
                result = r.store.record("outbox", {"user_id": r.context.user_id, "tenant_id": r.context.tenant_id,
                    "recipient": args["recipient"], "body": args["body"],
                    "internal_projects": sorted(r.internal_projects), "run_id": r.run_id})
            elif action.tool == "propose_payment":
                result = r.store.record("proposals", {"user_id": r.context.user_id, "tenant_id": r.context.tenant_id,
                    "args": dict(args), "status": "pending_review"})
            elif action.tool == "commit_payment":
                result = p.approval.commit(r.context, action, r)
            elif action.tool == "remember":
                row = {"user_id": r.context.user_id, "tenant_id": r.context.tenant_id,
                    "key": args["key"], "value": args["value"], "schema_version": 1,
                    "origin": "user_preference" if r.last_source == "task" else "tool_result",
                    "source_id": r.last_source, "confirmation_id": args.get("confirmation_id"),
                    "created_at": r.clock.now(), "status": "candidate"}
                decision = p.memory.check(r.context, row, r)
                row["status"] = "active" if decision.allowed else "candidate"
                row["reason"] = decision.reason
                stored = r.store.record("memories", row)
                result = {"id": stored["id"], "status": stored["status"], "reason": stored["reason"]}
            elif action.tool == "recall":
                result = {"memories": self.recall()}
            elif action.tool == "unstable":
                if args["mode"] == "transient":
                    raise TransientToolError("simulated_transient_failure")
                if args["mode"] == "oversize":
                    result = {"body": "x" * 20000}
                elif args["mode"] == "stall":
                    if not r.clock.virtual:
                        raise PolicyDenied("virtual_fault_only")
                    r.clock.advance(95)  # virtual-clock fault only
                    result = {"body": "late read-only result"}
                elif args["mode"] == "normal":
                    result = {"body": "service healthy"}
                else:
                    raise PolicyDenied("unknown_fault_fixture")
            else:
                raise PolicyDenied("unimplemented_tool")
            self.emit("tool_result", action, "allow", "executed")
            return result
        except PolicyDenied as e:
            self.emit("tool_result", action, "deny", str(e))
            return {"error": "policy_denied", "reason": str(e)}
        except TransientToolError as e:
            self.emit("tool_result", action, "allow", "transient_error")
            return {"error": str(e)}

    def document(self, doc, snippet=False):
        self.p.retrieval.observe(doc, self.rt)
        self.rt.pending_docs.append(doc["id"])
        self.rt.last_source = doc["id"]
        return {"id": doc["id"], "title": doc["title"], "body": doc["body"][:300] if snippet else doc["body"],
                "label": doc["label"], "version": doc["version"]}

    def recall(self):
        result = []
        for row in self.rt.store.rows("memories"):
            if row["status"] != "active":
                continue
            decision = self.p.memory.check(self.rt.context, row, self.rt)
            if decision.allowed:
                result.append(row)
            elif row["user_id"] == self.rt.context.user_id and row["tenant_id"] == self.rt.context.tenant_id:
                self.rt.store.record("memories", {**row, "status": "quarantined", "reason": decision.reason}, row["id"])
        self.rt.memory_active = result
        return result
