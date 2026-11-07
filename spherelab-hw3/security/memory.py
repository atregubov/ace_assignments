from labagent.types import allow, deny


def check(context, row, runtime):
    if row.get("user_id") != context.user_id or row.get("tenant_id") != context.tenant_id:
        return deny("memory_scope")
    if row.get("schema_version") != 1 or row.get("status") == "quarantined":
        return deny("memory_schema_or_quarantine")
    if row.get("key") == "answer_style":
        valid = row.get("value") in {"bullets", "prose"}
    elif row.get("key") == "default_recipient":
        user = runtime.store.get("users", context.user_id)
        valid = bool(user) and row.get("value") in user["recipients"]
    else:
        valid = False
    if not valid:
        return deny("memory_value")
    proof = runtime.store.row("confirmations", row.get("confirmation_id"))
    if not proof or any(proof.get(k) != row.get(k) for k in ("user_id", "tenant_id", "key", "value")):
        return deny("memory_unconfirmed")
    if row.get("origin") not in {"tool_result", "user_preference"} or not row.get("source_id"):
        return deny("memory_provenance")
    return allow()
