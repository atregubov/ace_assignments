"""Assignment 3: retrieval access control and provenance. Specification: docs/hw3.md.

check(context, doc, runtime) -> Decision
    Called for a direct ``read_doc`` and for every candidate document of ``search_docs``
    before ranking, so a denied document contributes no title, snippet or score.
    ``doc`` is the trusted stored document dict, or ``None`` if the ID does not exist.

observe(doc, runtime) -> None
    Called once for every document actually returned to the model. Record the provenance
    the egress policy needs in ``runtime.internal_projects``, a set that lasts for the whole
    run. A natural element is a ``(tenant, project)`` tuple.

    context  Trusted ``Context`` from the case definition or operator CLI: ``user_id``, ``tenant_id``,
             ``task_id``, ``allowed_tools`` and ``allowed_recipients``. Can be ``None`` in tests.
    runtime  ``Runtime`` for this session: ``runtime.store`` (authoritative SQLite lookups),
             ``runtime.assignment``, counters, ``runtime.clock`` and ``runtime.events``.

Trusted lookups: ``runtime.store.get(kind, id)`` returns a dict or ``None``.
    users       {"id", "tenant", "roles": [...], "projects": [...], "recipients": [...]}
    docs        {"id", "tenant", "project", "label": "PUBLIC"|"INTERNAL", "title", "body", "version"}
    recipients  {"id", "tenant", "projects": [...], "external": bool}
    accounts    {"id", "tenant"}          vendors  {"id", "tenant"}
See inputs/world.json for every record.
Labels and ACL fields come only from the store; an attacker can rewrite a public body but
not its ``label``, ``tenant`` or ``project``.

Return ``allow(reason)`` or ``deny(reason)`` from ``labagent.types``. The reason is a short
code (e.g. ``"unknown_recipient"``) that appears in traces and in the denial sent to the model.

Keep the function signatures unchanged; the harness imports this module by name. Add your
own regression tests as ``tests/public/test_student_*.py`` (start from
``tests/public/template_student_test.py``).
"""
from labagent.types import allow, deny


def check(context, doc, runtime):
    # VULNERABLE: any existing document, from any tenant or project, is returned.
    return allow("vulnerable_global_search") if doc else deny("unknown_document")


def observe(doc, runtime):
    pass  # VULNERABLE: discards provenance when content is read.
