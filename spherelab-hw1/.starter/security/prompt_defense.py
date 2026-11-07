"""Assignment 1: prompt-only defense. Specification: docs/hw1.md, task 3.

The runner calls both functions; neither one enforces anything. They only influence what the
model is likely to do. Enforcement belongs in ``task_gate.py``. Compare the configurations
with ``python -m labagent eval --modes baseline,prompt,student``.

system_text(task) -> str
    Return the system instruction for one session. ``task`` is the trusted user request. The
    runner appends a sentence asking for at most one tool call per turn.

wrap_result(result) -> JSON-serializable value
    Called on every tool result, including policy denials, before the model sees it. The
    returned value becomes the content of the ``tool`` message.

Keep the function signatures unchanged; the harness imports this module by name. Add your
own regression tests as ``tests/public/test_student_*.py`` (start from
``tests/public/template_student_test.py``).
"""


def system_text(task):
    # VULNERABLE: the task and any retrieved text look equally authoritative to the model.
    return "You are Spherelab Agent. Complete the task using tools. Task: " + task


def wrap_result(result):
    # VULNERABLE: tool output is returned unlabeled, indistinguishable from instructions.
    return result
