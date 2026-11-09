"""Assignment 5: binding human approval to the exact action. Specification: docs/hw5.md.

commit(context, action, runtime) -> receipt dict
    Called for every ``commit_payment`` after the task gate and authorization. Return a ledger
    receipt, or raise ``PolicyDenied(reason)`` to refuse. ``action.args`` holds the payment
    fields plus ``approval_id``.

    context  Trusted ``Context`` from the case definition or operator CLI: ``user_id``, ``tenant_id``,
             ``task_id``, ``allowed_tools`` and ``allowed_recipients``. Can be ``None`` in tests.
    action   Untrusted ``Action`` proposed by the model: ``action.tool`` (str) and ``action.args``
             (dict, already schema-checked). Treat every argument as attacker-controlled.
    runtime  ``Runtime`` for this session: ``runtime.store`` (authoritative SQLite lookups),
             ``runtime.assignment``, counters, ``runtime.clock`` and ``runtime.events``.

Helpers you are expected to use:
    runtime.store.atomic_commit(context, action, runtime, check)
        Takes a SQLite write lock, loads the approval named by ``approval_id`` and any existing
        receipt for the same operation ID, and calls
        ``check(context, action, runtime, approval, receipt) -> Decision``. On ``allow`` it
        either returns the existing receipt or writes one new ledger row and marks the
        approval used, in one transaction. On ``deny`` it raises ``PolicyDenied``. You write
        ``check``.
    labagent.types.payment_binding(context, action, document)   what the reviewer approved
    labagent.utils.to_hash_string(value)                        SHA-256 of canonical JSON
Approval records: {"id", "binding", "digest", "approved", "expires", "nonce", "used", "reviewer"}.
For the current time use ``(runtime.approval_now or runtime.clock.now)()``; the CLI sets
``approval_now`` to wall-clock time for approvals issued by a separate ``review`` process.
``labagent.limits.PAYMENT_LIMIT_CENTS`` is the payment limit.

Keep the function signatures unchanged; the harness imports this module by name. Add your
own regression tests as ``tests/public/test_student_*.py`` (start from
``tests/public/template_student_test.py``).
"""
from labagent.types import PolicyDenied


def commit(context, action, runtime):
    approval = runtime.store.row("approvals", action.args.get("approval_id"))
    # VULNERABLE: any approved record authorizes any payment, any number of times.
    if not approval or not approval["approved"]:
        raise PolicyDenied("approval_missing")
    return runtime.store.unsafe_commit(context, action)
