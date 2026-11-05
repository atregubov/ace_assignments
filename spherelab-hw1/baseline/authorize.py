from lab.types import allow, deny


def check(context, action, runtime):
    # VULNERABLE: the service account can read every project; model claims a role.
    if action.tool == "commit_payment":
        return deny("commit_disabled")
    if action.tool == "propose_payment":
        user = runtime.store.get("users", context.user_id) if context else None
        if action.args.get("role") != "finance" and (not user or "finance" not in user["roles"]):
            return deny("finance_required")
    return allow("vulnerable_service_account")
