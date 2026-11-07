from labagent.types import BudgetExceeded


def reserve(kind, runtime):
    if runtime.clock.now() >= runtime.limits["deadline"]:
        raise BudgetExceeded("deadline")
    used = runtime.model_attempts if kind == "model" else runtime.tool_attempts
    if used >= runtime.limits[kind]:
        raise BudgetExceeded(kind + "_limit")


def admit(text, runtime):
    if runtime.clock.now() >= runtime.limits["deadline"]:
        raise BudgetExceeded("late_result")
    size = len(text.encode("utf-8"))
    if runtime.result_bytes + size > runtime.limits["bytes"]:
        raise BudgetExceeded("context_bytes")
    return text


def after_call(runtime):
    if runtime.clock.now() >= runtime.limits["deadline"]:
        raise BudgetExceeded("late_result")


def timeout(runtime):
    remaining = runtime.limits["deadline"] - runtime.clock.now()
    if remaining <= 0:
        raise BudgetExceeded("deadline")
    return min(runtime.limits["request_timeout"], remaining)


def output_limit(runtime):
    return runtime.limits["max_output_tokens"]
