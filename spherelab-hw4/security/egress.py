from labagent.types import allow, deny


def check(context, action, runtime):
    recipient = runtime.store.get("recipients", action.args.get("recipient"))
    if not recipient:
        return deny("unknown_recipient")
    for tenant, project in runtime.internal_projects:
        if recipient["external"] or recipient["tenant"] != tenant or project not in recipient["projects"]:
            return deny("internal_data_egress")
    return allow()
