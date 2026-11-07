from labagent.types import allow


def check(context, action, runtime):
    return allow("vulnerable_no_task_gate")
