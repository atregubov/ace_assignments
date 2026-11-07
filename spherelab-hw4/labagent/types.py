from dataclasses import dataclass, field
import time
from typing import Any

from labagent.limits import POLICY_LIMITS


@dataclass(frozen=True)
class Context:
    user_id: str
    tenant_id: str
    task_id: str
    allowed_tools: tuple[str, ...]
    allowed_recipients: tuple[str, ...] = ()


@dataclass(frozen=True)
class Action:
    tool: str
    args: dict
    call_id: str = "call"

    def as_dict(self):
        return {"tool": self.tool, "args": self.args}


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str


def allow(reason="allowed"):
    return Decision(True, reason)


def deny(reason):
    return Decision(False, reason)


class LabError(Exception):
    pass


class PolicyDenied(LabError):
    pass


class BudgetExceeded(LabError):
    pass


class ModelError(LabError):
    """Infrastructure or model protocol error; not counted as a defended attack."""


class TransientToolError(LabError):
    pass


class Clock:
    def __init__(self, virtual=False):
        self.virtual = virtual
        self.value = 0.0
        self.start = time.monotonic()

    def now(self):
        return self.value if self.virtual else time.monotonic() - self.start

    def advance(self, seconds):
        if not self.virtual:
            raise ValueError("Fault delays use a virtual clock only")
        self.value += seconds


@dataclass
class Runtime:
    store: Any
    context: Context
    assignment: int
    clock: Clock
    run_id: str
    model_attempts: int = 0
    tool_attempts: int = 0
    result_bytes: int = 0
    internal_projects: set = field(default_factory=set)
    context_docs: list = field(default_factory=list)
    last_source: str = "task"
    terminal_reason: str | None = None
    events: list = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    usage_unknown: int = 0
    memory_active: list = field(default_factory=list)
    limits: dict = field(default_factory=lambda: dict(POLICY_LIMITS))  # assignment 6 policy limits
    pending_docs: list = field(default_factory=list)  # documents returned by the current tool call
    approval_now: Any = None  # optional epoch-time clock for approval expiry across processes


def payment_binding(context, action, document=None):
    # Defer this import because the utility module uses the shared action and error types.
    from labagent.utils import to_hash_string

    args = {k: v for k, v in action.args.items() if k != "approval_id"}
    return {"user_id": context.user_id, "tenant_id": context.tenant_id,
            "tool": "commit_payment", "args": args,
            "document_digest": to_hash_string(document) if document else None}
