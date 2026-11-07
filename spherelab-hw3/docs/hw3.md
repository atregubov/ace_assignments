# Assignment 3 - Protecting Retrieved Data and Outbound Messages

Use the [shared student guide](STUDENT_README.md) for setup, implementation interfaces, evaluation, and submission.

> **At a glance**
>
> - **Edit:** `security/retrieval.py`, `security/egress.py`
> - **Submit:** the common archive, before/after context document IDs, outbound allow/deny results, and an access-vs-egress violation table.
> - **Live model runs:** 24 episodes, 26 sessions because `cache_scope` has two (`eval --modes baseline,student`). The completed assignment 6 budget caps each session at 6 model requests, so the worst case is 156 requests.
> - **Grading:** diagnosis 15 · retrieval 25 · labels and egress 30 · evaluation 20 · memo 10. Internal use and public external sends must keep working.

## Overview

Spherelab Agent uses retrieval-augmented generation to answer questions about project documents. Its retriever mixes tenants, and its message tool can send an internal summary outside the organization. Repair both the retrieval access boundary and the outbound information-flow boundary.

After this exercise, you should be able to prevent unauthorized context from reaching a model, preserve confidentiality labels through a workflow, and explain the limits of detecting leaks with known secret strings.

## Background and required reading

Read the access and disclosure rules below and the CaMeL abstract [7](STUDENT_README.md#readings). The exercise uses a deliberately small label system; it is not a reimplementation of CaMeL. Authorization to read a document does not imply authorization to disclose it to every recipient.

## Software tools

Edit `security/retrieval.py` and `security/egress.py`. The scaffold supplies twelve documents, trusted tenant/project metadata, `PUBLIC` and `INTERNAL` labels, a recipient registry, context inspection, and exact synthetic leak markers. Retrieval uses fixed local search.

## Assignment instructions

### Setup

Open the assignment 3 bundle. The user may read their own project's internal documents and any public documents. Same-tenant project members may receive that project's internal content; external recipients may receive only public content. The authenticated user may receive a final answer derived from documents they are entitled to read.

The attacker may modify one public document body, but cannot change its stored label or ACL. The attacker tries either to place an unauthorized document in model context or to make an external outbox message depend on internal material. The two violations have separate test oracles.

### Tasks

1. **Observe two leaks.** Inspect a query that retrieves another project's document and an authorized internal read followed by an external send. Record the document IDs entering model context and the outbox contents. Explain why blocking only the final answer misses the first violation.
2. **Enforce access before context construction.** Filter search candidates using trusted user context before ranking/selecting authorized results for the model. Apply the same check to document reads by ID. Ensure snippets and titles do not expose unauthorized documents. The harness deliberately has no retrieval cache; in your memo, state what a cache key would have to include (for example authorization scope and document version) to be safe.
3. **Preserve confidentiality through execution.** Maintain a trusted run label: once a run reads internal material, its generated text and action arguments are treated as internal. Track the set of contributing internal projects as well. An outbound send is allowed only when the recipient is authorized for all of them. A model cannot reset labels, select its own provenance, or declare a summary public. Keep labels monotonic for that run.
4. **Evaluate leakage and usefulness.** Run six benign and six attack cases on both versions: 24 live episodes, plus direct retrieval and egress tests. Include public-to-external and internal-to-authorized-member sends that should succeed. Attack cases cover another tenant, an unauthorized same-tenant project, forged public labels, an internal summary sent externally, an encoded marker, and cross-session isolation (`cache_scope`: two users in separate sessions over one persistent store). Inspect context and state rather than relying only on marker matching.
5. **Assess the conservative policy.** Show that a run which has read internal material also blocks a later public-only external message. Demonstrate that a fresh run reading only public sources can send it. Explain this utility cost, the danger of model-decided declassification, and the additional machinery a more precise design would require.

### What can go wrong

Regex removal of a known marker does not establish confidentiality: a model can paraphrase, encode, or split information. Label metadata must come from the trusted store. A final-output check cannot undo unauthorized content already sent to the inference service. Include logs and caches in your discussion of data exposure.

## Submission instructions

Submit the common archive, before-and-after context document IDs, outbound allow/deny results, and a short table showing access violations and egress violations separately. State the exact limits of the two-label, run-level approximation.

Grading out of 100: diagnosis 15; retrieval enforcement 25; label propagation and egress enforcement 30; security and utility evaluation 20; memo and reproducibility 10. Both authorized internal use and public external sends must remain functional.

