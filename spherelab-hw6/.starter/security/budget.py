"""Assignment 6: execution budget. Specification: docs/hw6.md.

The policy limits are in ``runtime.limits`` (a copy of ``labagent.limits.POLICY_LIMITS``):
``model``, ``tool``, ``bytes``, ``deadline``, ``request_timeout`` and ``max_output_tokens``.
Counters are in ``runtime.model_attempts``, ``runtime.tool_attempts`` and
``runtime.result_bytes``; the trusted harness increments them after your checks pass. Elapsed
time is ``runtime.clock.now()`` in seconds (a virtual clock in tests). Raise
``BudgetExceeded(reason)`` from ``labagent.types`` to end the session with that reason.

reserve(kind, runtime) -> None
    Called before every model request (``kind == "model"``) and every tool attempt
    (``kind == "tool"``). Stop before the next attempt would exceed its limit.
admit(text, runtime) -> str
    Called with each tool result's canonical JSON before it enters the conversation.
    Count UTF-8 bytes, not characters.
after_call(runtime) -> None
    Called after each model response and before a returned tool call is dispatched.
timeout(runtime) -> float
    Seconds allowed for the next model request.
output_limit(runtime) -> int
    Output-token cap for the next model request.

The outer harness ceilings in ``labagent.limits`` still apply when these functions do nothing.

Keep the function signatures unchanged; the harness imports this module by name. Add your
own regression tests as ``tests/public/test_student_*.py`` (start from
``tests/public/template_student_test.py``).
"""


def reserve(kind, runtime):
    pass  # VULNERABLE: no attempt limit.


def admit(text, runtime):
    return text  # VULNERABLE: no context-size limit or deadline check.


def after_call(runtime):
    pass  # VULNERABLE: late responses are accepted.


def timeout(runtime):
    return 30.0  # VULNERABLE: ignores the remaining run time.


def output_limit(runtime):
    return 1024  # VULNERABLE: above the policy ceiling.
