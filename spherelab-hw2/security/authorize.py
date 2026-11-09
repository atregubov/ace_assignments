"""Assignment 2: tool authorization (reference monitor). Specification: docs/hw2.md.

check(context, action, runtime) -> Decision
    Called by the dispatcher for every proposed tool call, after the task gate and immediately
    before the tool runs, including on retries. The policy table in the handout is
    conjunctive: deny unless every applicable rule allows.

    context  Trusted ``Context`` from the case definition or operator CLI: ``user_id``, ``tenant_id``,
             ``task_id``, ``allowed_tools`` and ``allowed_recipients``. Can be ``None`` in tests.
    action   Untrusted ``Action`` proposed by the model: ``action.tool`` (str) and ``action.args``
             (dict, already schema-checked). Treat every argument as attacker-controlled.
             Identity-looking arguments (``user_id``, ``tenant_id``, ``role``) pass schema
             validation on purpose. They are claims, never authority.
    runtime  ``Runtime`` for this session: ``runtime.store`` (authoritative SQLite lookups),
             ``runtime.assignment``, counters, ``runtime.clock`` and ``runtime.events``.

Trusted lookups: ``runtime.store.get(kind, id)`` returns a dict or ``None``.
    users       {"id", "tenant", "roles": [...], "projects": [...], "recipients": [...]}
    docs        {"id", "tenant", "project", "label": "PUBLIC"|"INTERNAL", "title", "body", "version"}
    recipients  {"id", "tenant", "projects": [...], "external": bool}
    accounts    {"id", "tenant"}          vendors  {"id", "tenant"}
See inputs/world.json for every record.
Read records at check time; a role or project removed a moment ago must already be denied.
``labagent.limits.PAYMENT_LIMIT_CENTS`` is the configured proposal limit. Remember that
``bool`` is a subclass of ``int`` in Python.

Return ``allow(reason)`` or ``deny(reason)`` from ``labagent.types``. The reason is a short
code (e.g. ``"unknown_recipient"``) that appears in traces and in the denial sent to the model.

Keep the function signatures unchanged; the harness imports this module by name. Add your
own regression tests as ``tests/public/test_student_*.py`` (start from
``tests/public/template_student_test.py``).
"""
from labagent.types import allow, deny


def check(context, action, runtime):
    # VULNERABLE: the service account can read every project; model claims a role.
    if action.tool == "commit_payment":
        return deny("commit_disabled")
    if action.tool == "propose_payment":
        user = runtime.store.get("users", context.user_id) if context else None
        # VULNERABLE: a model-supplied "role" argument is accepted as authority.
        if action.args.get("role") != "finance" and (not user or "finance" not in user["roles"]):
            return deny("finance_required")
    return allow("vulnerable_service_account")
