from lab.types import allow, deny
from lab.schema import SCHEMAS


def check(context, action, runtime):
    if action.tool not in SCHEMAS:
        return deny("unknown_tool")
    if context is None or any(k in action.args for k in ("user_id", "tenant_id", "role")):
        return deny("untrusted_identity")
    user = runtime.store.get("users", context.user_id)
    if not user or user["tenant"] != context.tenant_id:
        return deny("unknown_principal")
    if runtime.assignment == 2 and action.tool not in {"read_doc", "send_message", "propose_payment"}:
        return deny("operation_not_enabled_in_snapshot")
    if action.tool not in context.allowed_tools and runtime.assignment != 1:
        return deny("task_tool_not_allowed")
    # HW2 owns the direct-read ACL. From HW3 onward, retrieval.check owns it,
    # including search snippets, so the teaching vulnerability is not masked.
    if action.tool == "read_doc" and runtime.assignment == 2:
        doc = runtime.store.get("docs", action.args.get("doc_id"))
        if not doc or doc["tenant"] != user["tenant"] or doc["project"] not in user["projects"]:
            return deny("document_access")
    if action.tool == "send_message":
        recipient = runtime.store.get("recipients", action.args.get("recipient"))
        if not recipient:
            return deny("unknown_recipient")
        if runtime.assignment == 2 and (recipient["external"] or recipient["tenant"] != user["tenant"]):
            return deny("recipient_tenant")
    if action.tool in {"propose_payment", "commit_payment"}:
        account = runtime.store.get("accounts", action.args.get("account"))
        vendor = runtime.store.get("vendors", action.args.get("payee"))
        amount = action.args.get("amount_cents")
        if "finance" not in user["roles"] or not account or account["tenant"] != user["tenant"]:
            return deny("payment_authority")
        if not vendor or vendor["tenant"] != user["tenant"]:
            return deny("vendor_access")
        if type(amount) is not int or not 0 < amount <= 50000 or action.args.get("currency") != "USD":
            return deny("payment_bounds")
        if action.tool == "commit_payment" and runtime.assignment < 5:
            return deny("commit_disabled")
    return allow()
