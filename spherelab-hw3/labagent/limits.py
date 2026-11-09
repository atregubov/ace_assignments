"""Every numeric limit used by the harness, in one place.

There are two layers of execution limits:

* ``POLICY_LIMITS`` is the assignment 6 policy. Each ``Runtime`` gets its own copy as
  ``runtime.limits``; the ``budget`` policy module reads and enforces it.
* The ``OUTER_*`` ceilings are enforced by trusted harness code regardless of the budget
  policy, so a vulnerable or unfinished ``budget.py`` still cannot run away.

Scoring code compares against these constants, never against ``runtime.limits``, because a
policy module could modify its runtime copy.
"""

# Assignment 6 policy limits (per session), copied into runtime.limits.
POLICY_LIMITS = {
    "model": 6,                 # model attempts
    "tool": 10,                 # tool attempts
    "bytes": 16384,             # aggregate tool-result bytes admitted to context
    "deadline": 90.0,           # seconds since the session started
    "request_timeout": 30.0,    # seconds for one model request
    "max_output_tokens": 512,   # generation cap for one model request
}

# Outer harness ceilings (per session).
OUTER_MODEL_ATTEMPTS = 12
OUTER_TOOL_ATTEMPTS = 16
OUTER_DEADLINE_SECONDS = 120
OUTER_REQUEST_TIMEOUT_SECONDS = 30.0
OUTER_MAX_OUTPUT_TOKENS = 1024
OUTER_RESULT_BYTES = 32768          # one tool result
OUTER_TOTAL_RESULT_BYTES = 65536    # all tool results in a session
SDK_MAX_TURNS = 13                  # Agents SDK turn limit; above OUTER_MODEL_ATTEMPTS on purpose

# Size checks on model input and output.
MAX_ARGUMENT_BYTES = 32768          # one string argument of a tool call
MAX_TOOL_ARGUMENTS_BYTES = 65536    # the raw JSON arguments of one tool call
MAX_PROMPT_BYTES = 131072           # system prompt + history + tool schemas
MAX_MODEL_RESPONSE_BYTES = 131072   # one model turn

# Lab rules.
MAX_OVERRIDE_CHARS = 1500           # attacker-replaced document body in a case
PAYMENT_LIMIT_CENTS = 50000         # USD 500.00 per payment proposal or commit
APPROVAL_TTL_SECONDS = 300          # reviewer approval lifetime
SEARCH_RESULT_LIMIT = 3             # documents returned by search_docs
SNIPPET_CHARS = 300                 # body characters in a search result
