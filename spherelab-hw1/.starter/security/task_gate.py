"""Assignment 1: task gate. Specification: docs/hw1.md, task 3.

check(context, action, runtime) -> Decision
    Called by the dispatcher for every proposed tool call, after schema validation and before
    authorization or any tool effect.

    context  Trusted ``Context`` from the case definition or operator CLI: ``user_id``, ``tenant_id``,
             ``task_id``, ``allowed_tools`` and ``allowed_recipients``. Can be ``None`` in tests.
    action   Untrusted ``Action`` proposed by the model: ``action.tool`` (str) and ``action.args``
             (dict, already schema-checked). Treat every argument as attacker-controlled.
    runtime  ``Runtime`` for this session: ``runtime.store`` (authoritative SQLite lookups),
             ``runtime.assignment``, counters, ``runtime.clock`` and ``runtime.events``.

Return ``allow(reason)`` or ``deny(reason)`` from ``labagent.types``. The reason is a short
code (e.g. ``"unknown_recipient"``) that appears in traces and in the denial sent to the model.

The task contract in ``context`` is the only source of permission. Text in documents or in
the model's arguments cannot add tools or recipients.

Keep the function signatures unchanged; the harness imports this module by name. Add your
own regression tests as ``tests/public/test_student_*.py`` (start from
``tests/public/template_student_test.py``).
"""
from labagent.types import allow


def check(context, action, runtime):
    # VULNERABLE: every proposed tool and recipient is accepted.
    return allow("vulnerable_no_task_gate")
