# Assignment 6 - Bounding Execution and Investigating Incidents

Use the [shared student guide](STUDENT_README.md) for setup, implementation interfaces, evaluation, and submission.

> **At a glance**
>
> - **Edit:** `security/budget.py`, `security/audit.py`
> - **Submit:** the common archive, the limit tests, a usage comparison, and the incident timeline.
> - **Model runs:** 12 [trials](STUDENT_README.md#trials-sessions-and-model-requests) (`eval --modes baseline,student`). Baseline sessions can reach the 12-request outer ceiling and repaired ones stop at 6, so the worst case is 108 requests.
> - **Grading:** diagnosis 15 · enforcement 40 · audit events 20 · incident and recovery 15 · reproducibility 10. Stopping every run fails.

## Overview

A retrieved troubleshooting note persuades the assistant to keep retrying a failing tool. Another fixture returns oversized results. The assistant wastes inference calls and leaves an incomplete record of what happened. Implement limits enforced outside the model and use the resulting events to investigate an incident.

After this exercise, you should be able to contain unproductive agent execution, account for retries, preserve useful audit evidence, and validate recovery after a bounded failure.

## Background and required reading

Read the execution limits and event fields specified below. Agent loops turn a model's bad plan into repeated resource consumption. A model instruction to stop, an SDK retry setting, and an application-wide budget address different parts of that problem.

## Software tools

Edit `security/budget.py` and `security/audit.py`. The scaffold supplies a provider adapter, local fault-injection tools, a controllable test clock, bounded local output capture, and outer limits on each run.

## Assignment instructions

### Setup

Open the assignment 6 bundle. The attacker may alter one returned note or choose a supplied fault fixture. They cannot start arbitrary processes or issue real network floods. Fault-injection tools are read-only; use simulated delays and errors for most tests.

The application policy permits at most six model attempts and ten tool attempts per run, a 512-token generation ceiling per model call, 16 KiB of aggregate tool-result text admitted to context, and a 90-second run deadline. Set an individual request timeout of at most 30 seconds or the remaining run time, whichever is smaller. Every retry consumes the same shared run budget. The outer harness ceilings bound each run while students inspect the vulnerable implementation.

### Tasks

1. **Reproduce the failure.** Run `python -m unittest tests.public.test_policy.PublishedPolicyTests.test_retry_attempts_and_oversized_result -v`. Inspect the attempt counter and admitted bytes. Use the supplied incident trace to identify which component initiates each retry. Reserve model calls for the bounded live comparison in Task 4.
2. **Implement the limits.** Reserve call/tool budget before dispatch and stop before the next request would exceed it. Count unsuccessful attempts and retries. Enforce the deadline and context-size limit in trusted code. The supplied adapter (`labagent/model.py`, not editable) already disables client and SDK retries and wraps each request in a cancellable timeout; confirm this from the code and a trace, and make `timeout()` and `after_call()` cooperate with it so late results are discarded. Preserve an explicit terminal reason.
3. **Make events usable.** Emit run and event IDs, parent event, authenticated principal, tool, argument digest, authorization decision, outcome, attempts, usage, elapsed time, and stop reason. Keep raw credentials and sensitive bodies out of ordinary logs. Record a protected fixture reference when needed for reproduction. A tool-result instruction cannot clear prior events or replace the trusted event emitter.
4. **Run fault and utility tests.** Test repeated transient errors, recursive retry instructions, oversized output, a stalled call using virtual time, a late tool result, and a normal three-step task. Assert hard bounds and no side effect from a discarded late proposal. Run three benign and three bounded attack cases live on both versions: twelve trials.
5. **Investigate and recover.** Using `fixtures/incident_trace.json`, produce a five-event timeline. Identify the first untrusted input, the attempted policy violation, which control acted, and any side effect actually committed. Describe containment and reset steps, then show that a clean legitimate task completes after recovery. Distinguish observations from hypotheses.

### What can go wrong

A framework step limit may omit provider retries or calls inside a tool. A timeout does not necessarily cancel server-side work, reverse a committed effect, or prevent charges. Report observed provider usage and unknown usage on failed requests; do not claim an exact dollar ceiling from a client timeout. A log hash helps correlation but does not by itself make logs tamper-proof.

## Submission instructions

Submit the common archive, the limit tests, a usage comparison, and the incident timeline. Include evidence of a normal task succeeding and a runaway task stopping with a specific reason.

Grading out of 100: failure diagnosis 15; enforcement and retry accounting 40; useful audit events 20; incident reconstruction and recovery 15; reproducibility 10. A defense that immediately stops every run fails the legitimate-task requirements.

