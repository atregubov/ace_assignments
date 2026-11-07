"""Select the security policy implementations for each assignment and mode."""
import importlib
import json
from pathlib import Path

# Policy module name -> the assignment in which students implement it.
POLICY_FN_ASSIGNMENT_NUMBER = {"prompt_defense": 1, "task_gate": 1, "authorize": 2,
                               "retrieval": 3, "egress": 3, "memory": 4, "approval": 5,
                               "budget": 6, "audit": 6}
ROOT = Path(__file__).resolve().parents[1]


class Policies:
    """Expose imported security policy modules to the runner and dispatcher."""

    def __init__(self, assignment, mode="student"):
        config = json.loads((ROOT / "course.json").read_text())
        if assignment not in range(1, 7) or mode not in {"student", "baseline", "prompt", "reference"}:
            raise ValueError("Invalid assignment or mode")
        if config["student"] and assignment != config["assignment"]:
            raise ValueError(f"This student package is for assignment {config['assignment']}")
        if config["student"] and mode == "reference":
            raise ValueError("Reference mode requires the instructor bundle")
        if mode == "prompt" and assignment != 1:
            raise ValueError("Prompt-only comparison is for assignment 1")
        self.assignment, self.mode = assignment, mode
        for policy_fn, policy_assignment in POLICY_FN_ASSIGNMENT_NUMBER.items():
            if policy_assignment == assignment and (mode == "baseline" or (mode == "prompt" and policy_fn == "task_gate")):
                package = "baseline"
            elif mode == "reference" or (policy_assignment != assignment and not config["student"]):
                package = "reference"
            else:
                package = "security"
            setattr(self, policy_fn, importlib.import_module(package + "." + policy_fn))
