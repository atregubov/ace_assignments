from lab.types import allow


def check(context, action, runtime):
    return allow("vulnerable_no_flow_policy")
