"""TODO: replace this deliberately vulnerable hook with the published policy.
Keep signatures unchanged. Add public regression tests for your repair.
"""
from lab.types import allow


def check(context, action, runtime):
    return allow("vulnerable_no_task_gate")
