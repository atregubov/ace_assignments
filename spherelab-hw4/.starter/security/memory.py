"""Assignment 4: memory admission and retrieval. Specification: docs/hw4.md.

check(context, row, runtime) -> Decision
    Called twice in a memory's life:
    * at admission, when the model calls ``remember``: ``allow`` makes the row ``active``,
      ``deny`` leaves it a ``candidate``;
    * at retrieval, on every ``active`` row when the model calls ``recall``: a denied row
      owned by the current user is quarantined by the dispatcher.

    row      Memory record. The dispatcher fills ``user_id``, ``tenant_id``, ``origin``
             (``"user_preference"`` or ``"tool_result"``), ``source_id`` and
             ``schema_version`` from the trusted session. ``key``, ``value`` and
             ``confirmation_id`` come from the model. Legacy rows may contain anything.
    context  Trusted ``Context`` from the case definition or operator CLI: ``user_id``, ``tenant_id``,
             ``task_id``, ``allowed_tools`` and ``allowed_recipients``. Can be ``None`` in tests.
    runtime  ``Runtime`` for this session: ``runtime.store`` (authoritative SQLite lookups),
             ``runtime.assignment``, counters, ``runtime.clock`` and ``runtime.events``.

Trusted confirmations, created only by ``python -m labagent confirm``:
``runtime.store.row("confirmations", confirmation_id)`` returns
{"id", "user_id", "tenant_id", "key", "value"} or ``None``. A user's permitted recipients are in
``runtime.store.get("users", user_id)["recipients"]``.

Return ``allow(reason)`` or ``deny(reason)`` from ``labagent.types``. The reason is a short
code (e.g. ``"unknown_recipient"``) that appears in traces and in the denial sent to the model.

Keep the function signatures unchanged; the harness imports this module by name. Add your
own regression tests as ``tests/public/test_student_*.py`` (start from
``tests/public/template_student_test.py``).
"""
from labagent.types import allow


def check(context, row, runtime):
    # VULNERABLE: every candidate is activated and every stored row is trusted on recall.
    return allow("vulnerable_trust_all_memory")
