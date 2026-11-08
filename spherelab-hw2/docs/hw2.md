# Assignment 2 - Enforcing Tool Authorization

Use the [shared student guide](STUDENT_README.md) for setup, implementation interfaces, evaluation, and submission.

> **At a glance**
>
> - **Edit:** `security/authorize.py`
> - **Submit:** the common archive, your policy, all deterministic test results, and one allow and one deny trace.
> - **Model runs:** 12 [trials](STUDENT_README.md#trials-sessions-and-model-requests) (`eval --modes baseline,student`). The completed assignment 6 budget caps each session at 6 model requests, so the worst case is 72 requests.
> - **Grading:** threat model 15 · policy and complete mediation 45 · adversarial tests 25 · live comparison and memo 15. Deny-all gets no functionality credit.

## Overview

The assistant accepts well-formed tool calls but uses its service account's broad permissions for every user. A malicious document or an ordinary model error can therefore cause it to read another project or act for another user. Repair this confused-deputy failure with a small reference monitor.

After this exercise, you should be able to implement default-deny authorization, derive authority from authenticated context, and test a security boundary independently of model behavior.

## Background and required reading

Read the policy table below and the tool-execution overview in the OpenAI function calling guide [5](STUDENT_README.md#readings). A tool name and a valid JSON schema describe what can be requested; they do not establish who may request it. In the client-side setup used here, application code executes the proposed action.

## Software tools

Edit `security/authorize.py`. The scaffold supplies schema validation, an immutable user context, resource and recipient lookup, a dispatcher, and direct tests for proposed actions. You may use plain Python predicates; learning a new policy language is not required.

## Assignment instructions

### Setup

Open the assignment 2 bundle. Inspect two users in tenant A, one user in tenant B, a finance role, project membership, and internal/external recipient records. The attacker may supply retrieved text and arbitrary proposed tool-call arguments in direct dispatcher tests. The attacker cannot change authenticated context or authoritative metadata.

Only `read_doc`, `send_message`, and `propose_payment` are enabled in this bundle. Deny every other operation, including `search_docs`; retrieval search is introduced in homework 3. The policy is conjunctive: every applicable rule must allow the action. Unknown tools, missing context, malformed arguments, and lookup failures deny access.

| Operation | Required conditions |
| --- | --- |
| Read a document | Document is in the user's tenant and a project the user belongs to |
| Send a message | Tool is allowed by the current task; recipient is an exact registered internal identity in the user's tenant and permitted by the task |
| Propose a payment | User has the finance role; account is in the user's tenant; amount is a positive integer number of cents within the configured proposal limit |
| Commit a payment or modify policy | Denied in this assignment |

### Tasks

1. **Find the authority error.** Reproduce one cross-project read and one forged-role request on the vulnerable bundle. Trace whether `user_id`, `tenant_id`, or `role` is being accepted from model arguments. Record the observed document access or state change.
2. **Implement the monitor.** Complete `check(context, action, runtime)` in `security/authorize.py`. Use the trusted context and resource registry. Treat any identity fields inside model arguments as invalid rather than as authority. Validate types and bounds, including booleans accidentally accepted as integers. Return a structured allow/deny decision with a reason code. The dispatcher (`labagent/dispatcher.py`, not editable) calls it immediately before every tool execution, including retried calls; confirm this from the code and a test, and report any path that would bypass it.
3. **Build adversarial tests.** Add four regression cases to the six supplied scenario cases and the direct boundary checks. Together, cover a legitimate read and send, unauthorized project, other tenant, role spoofing, unknown tool, missing context, out-of-range amount, and a permission revoked before execution. Test a syntactically valid but unauthorized action. Assert that a denial produces no tool side effect.
4. **Exercise the live agent.** Run three benign and three attack tasks on baseline and patched versions: 12 trials. Compare proposed actions with executed actions. Submit every forbidden action to the dispatcher in a direct test; the policy must still hold when the model is assumed to be fully misled.
5. **Write the memo.** Describe the complete-mediation boundary and its assumptions. Explain why prompts, tool descriptions, and an LLM-based permission classifier are insufficient substitutes for this policy check. Identify one route around the monitor that must remain unavailable in deployment.

### What can go wrong

A check that trusts an action's claimed tenant has merely moved the vulnerability. A cached allow decision can outlive a role change. If a backend or alternate tool path can be invoked without the dispatcher, document and close that path within the supplied application.

## Submission instructions

Submit the common archive, your policy implementation, and all supplied and added deterministic test results. Include one allow trace and one deny trace showing trusted identity and a reason code, with no credentials.

Grading out of 100: threat model 15; correct policy and complete mediation 45; adversarial tests 25; live comparison and memo 15. A deny-all implementation receives no legitimate-functionality credit and cannot receive full policy credit.

