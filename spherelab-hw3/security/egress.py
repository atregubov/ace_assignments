"""Assignment 3: outbound information flow. Specification: docs/hw3.md.

check(context, action, runtime) -> Decision
    Called for every ``send_message`` after the task gate and authorization. ``action.args``
    holds ``recipient`` and ``body``. Decide from what the run has read
    (``runtime.internal_projects``, filled by ``retrieval.observe``), never from the body text
    or from anything the model says about it.

    context  Trusted ``Context`` from the case definition or operator CLI: ``user_id``, ``tenant_id``,
             ``task_id``, ``allowed_tools`` and ``allowed_recipients``. Can be ``None`` in tests.
    action   Untrusted ``Action`` proposed by the model: ``action.tool`` (str) and ``action.args``
             (dict, already schema-checked). Treat every argument as attacker-controlled.
    runtime  ``Runtime`` for this session: ``runtime.store`` (authoritative SQLite lookups),
             ``runtime.assignment``, counters, ``runtime.clock`` and ``runtime.events``.

Trusted lookups: ``runtime.store.get(kind, id)`` returns a dict or ``None``.
    users       {"id", "tenant", "roles": [...], "projects": [...], "recipients": [...]}
    docs        {"id", "tenant", "project", "label": "PUBLIC"|"INTERNAL", "title", "body", "version"}
    recipients  {"id", "tenant", "projects": [...], "external": bool}
    accounts    {"id", "tenant"}          vendors  {"id", "tenant"}
See inputs/world.json for every record.
The run label is monotonic: once internal material has been read, it stays internal for the
rest of the run.

Return ``allow(reason)`` or ``deny(reason)`` from ``labagent.types``. The reason is a short
code (e.g. ``"unknown_recipient"``) that appears in traces and in the denial sent to the model.

Keep the function signatures unchanged; the harness imports this module by name. Add your
own regression tests as ``tests/public/test_student_*.py`` (start from
``tests/public/template_student_test.py``).
"""
from labagent.types import allow


def check(context, action, runtime):
    # VULNERABLE: any recipient may receive anything the run has read.
    return allow("vulnerable_no_flow_policy")
