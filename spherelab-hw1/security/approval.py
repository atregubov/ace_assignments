from lab.types import allow, deny, digest, payment_binding


def check(context, action, runtime, approval, receipt):
    user = runtime.store.get("users", context.user_id)
    account = runtime.store.get("accounts", action.args.get("account"))
    vendor = runtime.store.get("vendors", action.args.get("payee"))
    doc = runtime.store.get("docs", action.args.get("document_id"))
    amount = action.args.get("amount_cents")
    if not user or user["tenant"] != context.tenant_id or "finance" not in user["roles"]:
        return deny("payment_authority_revoked")
    if action.tool not in context.allowed_tools:
        return deny("task_tool_not_allowed")
    if not account or not vendor or account["tenant"] != context.tenant_id or vendor["tenant"] != context.tenant_id:
        return deny("payment_resource_scope")
    if type(amount) is not int or not 0 < amount <= 50000 or action.args.get("currency") != "USD":
        return deny("payment_bounds")
    if not doc or doc["tenant"] != context.tenant_id or doc["project"] not in user["projects"]:
        return deny("payment_document_scope")
    if doc["version"] != action.args.get("document_version"):
        return deny("document_changed")
    binding = payment_binding(context, action, doc)
    if receipt:
        return allow("idempotent_receipt") if receipt["binding"] == binding else deny("operation_changed")
    if not approval or not approval.get("approved") or not approval.get("nonce"):
        return deny("approval_missing_or_rejected")
    now = getattr(runtime, "approval_now", runtime.clock.now)()
    if approval["used"] or approval["expires"] <= now:
        return deny("approval_used_or_expired")
    if approval["binding"] != binding or approval["digest"] != digest(binding):
        return deny("approval_action_mismatch")
    return allow()


def commit(context, action, runtime):
    return runtime.store.atomic_commit(context, action, runtime, check)
