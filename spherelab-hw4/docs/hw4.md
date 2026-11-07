# Assignment 4 - Preventing Persistent Memory Poisoning

Use the [shared student guide](STUDENT_README.md) for setup, implementation interfaces, evaluation, and submission.

> **At a glance**
>
> - **Edit:** `security/memory.py`
> - **Submit:** the common archive, session A and B traces, memory snapshots before and after repair, and a recovery procedure.
> - **Live model runs:** 12 two-session episodes, i.e. 24 sessions (`eval --modes baseline,student`). The completed assignment 6 budget caps each session at 6 model requests, so the worst case is 144 requests.
> - **Grading:** persistence demo 20 · admission and retrieval 40 · two-session tests 25 · recovery and memo 15. Confirmed memory must keep working.

## Overview

The assistant stores preferences between sessions. A document tells it to remember an attacker-selected default recipient as if the user had requested it. The resulting preference can affect later tasks after the original document has disappeared. Repair memory admission, retrieval, and recovery.

After this exercise, you should be able to reproduce an attack across sessions, distinguish content provenance from authority, and remove poisoned state without disabling legitimate memory.

## Background and required reading

Read the memory activation rules below and the memory/context-poisoning discussion in the OWASP agentic risk material [8](STUDENT_README.md#readings). Storage can preserve malicious instructions as readily as useful facts. A trustworthy record of where text came from does not make its instructions trustworthy.

## Software tools

Edit `security/memory.py`. The scaffold supplies a candidate-memory queue, authenticated preference-confirmation events, SQLite storage, a two-session runner, and a quarantine operation. No new database or authentication system is required.

## Assignment instructions

### Setup

Open the assignment 4 bundle. Session A reads a document and extracts candidate memories. Session B starts with empty conversation history and the same persistent store. The legitimate preference schema permits `answer_style` with values `bullets` or `prose`, and a default recipient selected from the trusted user-specific recipient list.

Only an explicit authenticated user preference event can activate a preference. Model- or document-derived candidates stay untrusted until that event confirms the exact key and value. The attacker may alter a document in session A. They cannot create confirmation events or directly edit the database. Supplied legacy records model previously compromised state for recovery testing.

The attacker objective is activation or trusted retrieval of a forbidden preference. Record any subsequent forbidden action attempt and execution separately; the supplied tool policy may correctly block downstream harm even when memory integrity fails.

### Tasks

1. **Demonstrate persistence.** Plant a preference-changing instruction in a document, run session A, then remove the document and start session B. Inspect stored and active memory. If the live model does not extract the candidate, run the published direct memory test and label its result as a policy check.
2. **Design the admission rules.** Write the allowed preference schema and activation rule. Each record must bind tenant, user, key, value, origin, source identifier, confirmation identifier, and schema version. Assign origin from the trusted ingestion path. Reject an item's self-description as “user approved.”
3. **Implement admission and retrieval.** Validate candidate types and permissible values. Require a matching confirmation for activation. Recheck user/tenant scope and schema version when retrieving memory, including legacy rows. Keep external content in an untrusted data field rather than concatenating it into a system instruction. Use the supplied quarantine mechanism for invalid records.
4. **Test two-session behavior.** Run two benign and four adversarial two-session cases on both versions: 24 live session episodes. Cover a confirmed style preference, a confirmed valid recipient, an unconfirmed extracted preference, forged approval text, another user's record, and an invalid legacy record. Also run the deterministic admission tests. Show that a legitimate preference survives a restart.
5. **Recover and explain.** Quarantine the poisoned record with `python -m labagent quarantine`, and rerun session B. The harness rechecks memory on every recall and keeps no derived cache; note what a production system would also have to invalidate. Write a short recovery procedure that identifies affected records without deleting every user's memory. Explain why downstream authorization is still necessary after this repair.

### What can go wrong

Clearing all memory before every task hides the vulnerability while breaking the intended feature. Namespaced storage without admission checks still stores malicious preferences for the correct user. A record with valid provenance may still be untrusted content.

## Submission instructions

Submit the common archive, session A and B traces, memory snapshots before and after repair, and the recovery procedure. Use explicit counts for poisoned candidates, activated preferences, attempted forbidden actions, and executed forbidden actions.

Grading out of 100: persistence demonstration 20; admission and retrieval controls 40; two-session and isolation tests 25; recovery procedure and memo 15. Legitimate confirmed memory must continue to work.

