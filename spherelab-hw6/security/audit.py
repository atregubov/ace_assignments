"""Assignment 6: audit events. Specification: docs/hw6.md, task 3.

event(runtime, kind, action=None, decision=None, outcome=None) -> dict
    Called by the trusted dispatcher and runner; the returned dict is appended to
    ``runtime.events`` and stored in the SQLite ``audit`` table.

    kind      "model_request", "proposal", "tool_result" or "run_end"
    action    the proposed ``Action`` (tool events only), or ``None``
    decision  "allow" / "deny" (tool results only), or ``None``
    outcome   "executed", a denial reason, "transient_error", or the terminal reason

The event must be JSON-serializable and must have a unique ``event_id``. Useful fields are on
``runtime``: ``run_id``, ``context``, ``events``, counters, ``input_tokens``,
``output_tokens``, ``usage_unknown``, ``clock``, ``terminal_reason`` and ``last_source``
(the most recent document ID, or "task"). ``to_hash_string`` in ``labagent.utils`` produces a
digest. Never copy message bodies or other raw arguments into events.

Keep the function signatures unchanged; the harness imports this module by name. Add your
own regression tests as ``tests/public/test_student_*.py`` (start from
``tests/public/template_student_test.py``).
"""


def event(runtime, kind, action=None, decision=None, outcome=None):
    # VULNERABLE: no principal, tool, decision, linkage or usage; incidents cannot be reconstructed.
    return {"event_id": f"{runtime.run_id}:{len(runtime.events)}", "kind": kind}
