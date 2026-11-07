from labagent.types import PolicyDenied


def commit(context, action, runtime):
    approval = runtime.store.row("approvals", action.args.get("approval_id"))
    if not approval or not approval["approved"]:
        raise PolicyDenied("approval_missing")
    return runtime.store.unsafe_commit(context, action)
