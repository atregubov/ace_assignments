# Assignment 5 - Binding Human Approval to an Exact Action

Use the [shared student guide](STUDENT_README.md) for setup, implementation interfaces, evaluation, and submission.

> **At a glance**
>
> - **Edit:** `security/approval.py`
> - **Submit:** the common archive, one rejected mismatch trace, your binding specification, the deterministic test results, and ledger evidence.
> - **Model runs:** 8 [trials](STUDENT_README.md#trials-sessions-and-model-requests) (`eval --modes baseline,student`). The completed assignment 6 budget caps each session at 6 model requests, so the worst case is 48 requests.
> - **Grading:** exploit 15 · exact-action checks 35 · replay/concurrency 30 · tests and memo 20. The approved payment must succeed exactly once.

## Overview

The assistant prepares a simulated payment and asks a reviewer to approve it. The vulnerable implementation stores only `approved = true`. A changed payee or amount can therefore reuse an earlier approval, and a retry can create duplicate ledger entries. Bind approval to the precise operation and make retries safe.

After this exercise, you should be able to identify approval laundering, prevent time-of-check/time-of-use failures, and distinguish replay rejection from idempotent retry handling.

## Background and required reading

Read the approval requirements in Tasks 2 and 3 and the Agents SDK guide to human review and approvals [9](STUDENT_README.md#readings). A workflow pause provides an opportunity for review. The application still has to ensure that the reviewed action is the action executed and that resumption cannot duplicate a side effect.

## Software tools

Edit `security/approval.py`. The scaffold supplies canonical serialization, action hashing, a reviewer interface, a trusted clock, and a SQLite transaction helper that can atomically consume an approval and write a simulated payment. Implement policy checks rather than cryptographic primitives.

## Assignment instructions

### Setup

Open the assignment 5 bundle. The authenticated finance user requests a USD 50.00 payment to lab vendor `vendor-a`. All payments require approval, must use a registered tenant vendor, and may not exceed the configured USD 500.00 limit. The trusted reviewer approves only the exact action shown in the review manifest.

The attacker controls an invoice's text and delayed tool-result text. The test harness can replay a changed proposed action to isolate the approval-boundary bug. That replay does not imply that the attacker can alter the trusted approval store. The attack objective is a committed operation that differs from the approved operation, lacks valid approval, or duplicates its effect.

### Tasks

1. **Reproduce the mismatch.** Approve the original proposal, then use the supplied mutation case to change its payee or amount before execution. Test a repeat submission. Inspect the ledger for changed or duplicated operations; a reassuring natural-language summary is not evidence of authorization.
2. **Specify the approval record.** Bind the reviewer decision to authenticated user and tenant, tool, normalized arguments, operation ID, relevant document/version digests, expiry, and a server-generated nonce. The review screen must display payee, amount, currency, and any attached artifact being approved. A digest alone is not a useful human review screen.
3. **Enforce approval at commit.** Revalidate current role, task policy, vendor, amount, and resource versions. Compare the final action with the immutable approved action immediately before commit. Reject changes, missing or expired approval, and an already consumed approval used for a different operation. Use the supplied transaction helper so approval consumption and the ledger effect cannot race.
4. **Test replay and recovery.** The ten deterministic cases are supplied in `tests/public/test_boundaries.py`; run them and add at least two of your own in `tests/public/test_student_*.py`. They cover the unchanged approved action, rejected review, changed payee, changed amount/currency, changed attachment version, expired approval, revoked finance role, reused approval for a new operation, concurrent duplicate commit, and crash/retry after a committed write. The last two must produce exactly one ledger effect; an identical retry may return the recorded receipt. Run two benign and two attack cases live on both versions: eight trials.
5. **Write the memo.** Explain where the original approval lost its meaning, how your design binds review to execution, and how the transaction helper changes the concurrency argument. State what your implementation assumes about authenticated reviewers and the external payment service.

### What can go wrong

Hashing the proposal but executing a separately mutable object leaves the race intact. Checking a nonce outside the commit transaction permits concurrent reuse. A retry after a lost response must not cause a second payment. In a real external service, use that service's idempotency mechanism or an explicit reconciliation design; a local database transaction alone cannot guarantee exactly-once external effects.

## Submission instructions

Submit the common archive, one rejected mismatch trace, the approval-to-action binding specification, all ten test results, and ledger evidence for the concurrent and crash/retry cases.

Grading out of 100: exploit and diagnosis 15; exact-action and policy checks 35; replay/concurrency behavior 30; tests, evidence, and memo 20. Full credit requires the unchanged approved payment to succeed exactly once.

