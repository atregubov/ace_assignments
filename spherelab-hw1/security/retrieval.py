from lab.types import allow, deny


def check(context, doc, runtime):
    if not doc:
        return deny("unknown_document")
    if runtime.assignment < 3:
        return allow("earlier_snapshot_acl_is_in_authorize")
    user = runtime.store.get("users", context.user_id)
    if not user or user["tenant"] != context.tenant_id:
        return deny("unknown_principal")
    if doc["label"] == "PUBLIC":
        return allow()
    if doc["tenant"] == user["tenant"] and doc["project"] in user["projects"]:
        return allow()
    return deny("document_access")


def observe(doc, runtime):
    if doc["label"] == "INTERNAL":
        runtime.internal_projects.add((doc["tenant"], doc["project"]))
