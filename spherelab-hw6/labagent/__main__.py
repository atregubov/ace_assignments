"""Command-line interface: ``python -m labagent <command>``.

Evaluation commands (``list``, ``run``, ``eval``, ``grade``) run published cases in fresh
databases. Operator commands (``init``, ``inspect``, ``chat``, ``confirm``, ``review``,
``quarantine``) work on one persistent state file. ``confirm`` and ``review`` are trusted
operator actions; the model has no tool for them.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

from labagent.evaluate import cases, run_case, save_results
from labagent.policies import Policies, ROOT
from labagent.runner import Runner
from labagent.store import Store
from labagent.types import Action, Clock, Context, Runtime

MODES = ["student", "baseline", "prompt", "reference"]
STATE_TABLES = ["outbox", "memories", "proposals", "approvals", "ledger", "audit"]
PUBLIC_TESTS = ["tests.public.test_boundaries", "tests.public.test_policy"]


# ----- parser -------------------------------------------------------------------------

def add_model_options(parser):
    parser.add_argument("--model", "--model-id", dest="model_id", help="Provider model ID (OPENAI_MODEL)")
    parser.add_argument("--base-url", help="Chat Completions API root, including any /v1 prefix (OPENAI_BASE_URL)")
    parser.add_argument("--api-key", help="Provider API key (prefer the OPENAI_API_KEY environment variable)")
    parser.add_argument("--temperature", default="0", help="Sampling temperature (0-2), or default to omit it")
    parser.add_argument("--token-limit-field", choices=("max_tokens", "max_completion_tokens"), default="max_tokens",
                        help="Output-cap parameter accepted by your Chat Completions endpoint")


def build_parser(default_assignment):
    assignment_option = dict(type=int, choices=range(1, 7), default=default_assignment,
                             help="Select an assignment by number (default: %(default)s).")
    parser = argparse.ArgumentParser(prog="python -m labagent",
                                     description="Spherelab OpenAI agent security lab with local simulated tools")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="List the cases for an assignment")
    p.add_argument("--assignment", **assignment_option)
    p.set_defaults(handler=cmd_list)

    for command, help_text in [("run", "Run one case"), ("eval", "Run all cases"),
                               ("grade", "Run all cases and the public policy tests")]:
        p = sub.add_parser(command, help=help_text)
        p.add_argument("--assignment", **assignment_option)
        add_model_options(p)
        p.add_argument("--out", type=Path, default=Path("runs"))
        p.add_argument("--mode", choices=MODES, default="student")
        p.add_argument("--case-file", type=Path, help="Full copied case JSON; traces record its hash")
        if command == "run":
            p.add_argument("--case", required=True)
        else:
            p.add_argument("--repeat", type=int, default=1)
            p.add_argument("--modes", help="Comma-separated modes; overrides --mode")
        p.set_defaults(handler=cmd_evaluate)

    p = sub.add_parser("init", help="Create a new persistent state file")
    p.add_argument("--state", type=Path, required=True)
    p.set_defaults(handler=cmd_init)

    p = sub.add_parser("inspect", help="Print one table of a state file")
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--table", choices=STATE_TABLES, required=True)
    p.set_defaults(handler=cmd_inspect)

    p = sub.add_parser("review", help="Trusted reviewer: show a payment proposal and optionally approve it")
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--proposal", required=True)
    p.add_argument("--user", required=True)
    p.add_argument("--approve", action="store_true", help="Explicit trusted reviewer decision")
    p.set_defaults(handler=cmd_review)

    p = sub.add_parser("confirm", help="Trusted user: confirm one preference value")
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--user", required=True)
    p.add_argument("--key", choices=["answer_style", "default_recipient"], required=True)
    p.add_argument("--value", required=True)
    p.set_defaults(handler=cmd_confirm)

    p = sub.add_parser("quarantine", help="Remove one memory from active use, keeping it as evidence")
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--memory-id", required=True)
    p.set_defaults(handler=cmd_quarantine)

    p = sub.add_parser("chat", help="Run one free-form task against a persistent state file")
    p.add_argument("--state", type=Path, required=True)
    p.add_argument("--user", default="alice")
    p.add_argument("--assignment", **assignment_option)
    p.add_argument("--mode", choices=MODES, default="student")
    p.add_argument("--task", required=True)
    p.add_argument("--allow-tools", default="read_doc,search_docs")
    p.add_argument("--recipients", default="")
    add_model_options(p)
    p.set_defaults(handler=cmd_chat)
    return parser


def model_options(args):
    return {"model_id": args.model_id, "base_url": args.base_url, "api_key": args.api_key,
            "temperature": args.temperature, "token_limit_field": args.token_limit_field}


# ----- evaluation commands ------------------------------------------------------------

def selected_cases(args, parser):
    Policies(args.assignment, getattr(args, "mode", "student"))  # rejects other assignments in a student bundle
    case_file = getattr(args, "case_file", None)
    if case_file is None:
        return cases(args.assignment)
    selected = cases(path=case_file)
    if any(c["assignment"] != args.assignment for c in selected):
        parser.error("Case file assignment number must match --assignment")
    return selected


def cmd_list(args, parser):
    selected = selected_cases(args, parser)
    print(json.dumps([{"case": c["id"], "kind": c["kind"], "task": c["task"]} for c in selected], indent=2))
    return 0


def cmd_evaluate(args, parser):
    """run / eval / grade. Exit codes: 0 pass, 1 failed grade checks, 2 infrastructure error."""
    selected = selected_cases(args, parser)
    if args.command == "run":
        selected = [c for c in selected if c["id"] == args.case]
    if not selected:
        parser.error("No matching cases")
    repetitions = getattr(args, "repeat", 1)
    if not 1 <= repetitions <= 10:
        parser.error("--repeat must be between 1 and 10")
    modes = args.modes.split(",") if getattr(args, "modes", None) else [args.mode]

    batch = args.out / ("batch-" + uuid.uuid4().hex[:10])
    rows = []
    for mode in modes:
        for case in selected:
            for trial in range(repetitions):
                path = batch / f'hw{args.assignment}-{case["id"]}-{mode}-{trial}'
                row = run_case(case, mode, path, trial=trial, **model_options(args))
                rows.append(row)
                print(json.dumps({k: row[k] for k in ["case_id", "configuration", "status", "task_success",
                                                      "attacker_objective_met", "stop_reason"]}))
    summary = save_results(batch, rows)
    print(json.dumps({"output": str(batch), "summary": summary}, indent=2))

    if any(r["status"] != "completed" for r in rows):
        return 2
    if args.command != "grade":
        return 0
    scenarios_failed = any(r["attacker_objective_met"] or (r["kind"] == "benign" and r["task_success"] is not True)
                           for r in rows)
    tests_failed = [not public_tests_pass(args.assignment, mode) for mode in modes]
    return 1 if scenarios_failed or any(tests_failed) else 0


def public_tests_pass(assignment, mode):
    """Run the published direct policy tests in a subprocess for one mode."""
    env = dict(os.environ, LAB_ASSIGNMENT=str(assignment), LAB_MODE=mode)
    check = subprocess.run([sys.executable, "-m", "unittest", *PUBLIC_TESTS, "-q"], cwd=ROOT, env=env, timeout=60)
    return check.returncode == 0


# ----- operator commands on a persistent state file -----------------------------------

def cmd_init(args, parser):
    if args.state.exists():
        parser.error("State file exists; choose a new path to reset the lab")
    Store(args.state).seed()
    print(args.state)
    return 0


def open_store(args, parser):
    if not args.state.is_file():
        parser.error("Initialize the state file first")
    return Store(args.state)


def operator_context(store, user_id, parser, tools=(), recipients=()):
    """Build the trusted context for a lab user named on the command line."""
    user = store.get("users", user_id)
    if not user:
        parser.error("Unknown lab user")
    return user, Context(user["id"], user["tenant"], "manual", tuple(tools), tuple(recipients))


def cmd_inspect(args, parser):
    print(json.dumps(open_store(args, parser).rows(args.table), indent=2))
    return 0


def cmd_quarantine(args, parser):
    store = open_store(args, parser)
    row = store.row("memories", args.memory_id)
    if not row:
        parser.error("Unknown memory ID")
    store.record("memories", {**row, "status": "quarantined", "reason": "manual_recovery"}, row["id"])
    print("Memory quarantined. Retrieval has no cache to invalidate.")
    return 0


def cmd_confirm(args, parser):
    store = open_store(args, parser)
    _, ctx = operator_context(store, args.user, parser)
    print(json.dumps(store.confirm(ctx, args.key, args.value), indent=2))
    return 0


def cmd_review(args, parser):
    store = open_store(args, parser)
    user, ctx = operator_context(store, args.user, parser)
    proposal = store.row("proposals", args.proposal)
    if (not proposal or proposal["user_id"] != ctx.user_id or proposal["tenant_id"] != ctx.tenant_id
            or "finance" not in user["roles"]):
        parser.error("Proposal is not reviewable by this lab user")
    doc = store.get("docs", proposal["args"].get("document_id"))
    print(json.dumps({"proposal": proposal, "document_being_approved": doc}, indent=2))
    if args.approve:
        # Manual approvals use wall-clock time so they can expire across separate processes.
        action = Action("commit_payment", {**proposal["args"], "approval_id": "pending"})
        print(json.dumps(store.approve(ctx, action, time.time()), indent=2))
    return 0


def cmd_chat(args, parser):
    store = open_store(args, parser)
    _, ctx = operator_context(store, args.user, parser, tools=args.allow_tools.split(","),
                              recipients=[x for x in args.recipients.split(",") if x])
    policies = Policies(args.assignment, args.mode)
    rt = Runtime(store, ctx, args.assignment, Clock(), uuid.uuid4().hex)
    # Budget clocks stay monotonic within the run; approval expiry uses epoch time so that
    # an approval issued by a separate `review` process is compared on the same clock.
    rt.approval_now = time.time
    from labagent.model import OpenAIModel  # needs the inference SDK; other commands do not

    model = OpenAIModel(**model_options(args))
    runner = Runner(rt, policies, args.task).run(model)
    print(json.dumps({"final": runner.final, "stop_reason": rt.terminal_reason,
                      "error": runner.error, "run_id": rt.run_id}, indent=2))
    return 2 if runner.error else 0


# ----- entry point --------------------------------------------------------------------

def main(argv=None):
    config = json.loads((ROOT / "course.json").read_text())
    parser = build_parser(default_assignment=config["assignment"] or 1)
    args = parser.parse_args(argv)
    return args.handler(args, parser)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, RuntimeError) as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(2)
