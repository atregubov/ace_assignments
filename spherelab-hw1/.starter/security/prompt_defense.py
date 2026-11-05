"""TODO: replace this deliberately vulnerable hook with the published policy.
Keep signatures unchanged. Add public regression tests for your repair.
"""
def system_text(task):
    return "You are Spherelab Agent. Complete the task using tools. Task: " + task


def wrap_result(result):
    return result
