import argparse
import json
from pathlib import Path
import sys
import uuid
from agent.loop import Runner
from agent.model_adapter import BedrockModel, MockModel
from lab.evaluate import cases, context_for, run_case, save_results
from lab.policies import Policies, ROOT
from lab.quota import Quota
from lab.store import Store
from lab.types import Action, Clock, Context, Runtime


def main(argv=None):
    config = json.loads((ROOT / "course.json").read_text())
    assignment_option = dict(type=int, choices=range(1, 7), default=config["assignment"] or 1,
                             help="Select an assignment by number (default: %(default)s).")
    parser = argparse.ArgumentParser(description="Spherelab agent security lab (local simulated services)")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ["list", "run", "eval", "grade"]:
        p = sub.add_parser(command)
        p.add_argument("--assignment", **assignment_option)
        if command != "list":
            p.add_argument("--backend", choices=["mock", "bedrock"], default="mock")
            p.add_argument("--engine", choices=["python", "langgraph"], default="python")
            p.add_argument("--api-mode", choices=["json", "native"], default="json")
            p.add_argument("--out", type=Path, default=Path("runs"))
            p.add_argument("--mode", choices=["student", "baseline", "prompt", "reference"], default="student")
            p.add_argument("--case-file", type=Path, help="Full copied case JSON; traces record its hash")
        if command == "run":
            p.add_argument("--case", required=True)
        if command in {"eval", "grade"}:
            p.add_argument("--repeat", type=int, default=1)
            p.add_argument("--modes", help="Comma-separated modes; overrides --mode")
    init = sub.add_parser("init")
    init.add_argument("--state", type=Path, required=True)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--state", type=Path, required=True)
    inspect.add_argument("--table", choices=["outbox", "memories", "proposals", "approvals", "ledger", "audit"], required=True)
    review = sub.add_parser("review")
    review.add_argument("--state", type=Path, required=True)
    review.add_argument("--proposal", required=True)
    review.add_argument("--user", required=True)
    review.add_argument("--approve", action="store_true", help="Explicit trusted reviewer decision")
    confirm = sub.add_parser("confirm")
    confirm.add_argument("--state", type=Path, required=True)
    confirm.add_argument("--user", required=True)
    confirm.add_argument("--key", choices=["answer_style", "default_recipient"], required=True)
    confirm.add_argument("--value", required=True)
    quarantine = sub.add_parser("quarantine")
    quarantine.add_argument("--state", type=Path, required=True)
    quarantine.add_argument("--memory-id", required=True)
    chat = sub.add_parser("chat")
    chat.add_argument("--state", type=Path, required=True)
    chat.add_argument("--user", default="alice")
    chat.add_argument("--assignment", **assignment_option)
    chat.add_argument("--mode", choices=["student", "baseline", "prompt", "reference"], default="student")
    chat.add_argument("--task", required=True)
    chat.add_argument("--allow-tools", default="read_doc,search_docs")
    chat.add_argument("--recipients", default="")
    chat.add_argument("--backend", choices=["mock", "bedrock"], default="mock")
    chat.add_argument("--api-mode", choices=["json", "native"], default="json")
    args = parser.parse_args(argv)
    if args.command in {"list", "run", "eval", "grade"}:
        Policies(args.assignment, getattr(args, "mode", "student"))  # enforce student snapshot
        case_file = getattr(args, "case_file", None)
        if case_file is None:
            selected = cases(args.assignment)
        else:
            selected = cases(path=case_file)
            if any(c["assignment"] != args.assignment for c in selected):
                parser.error("Case file assignment number must match --assignment")
        if args.command == "list":
            print(json.dumps([{"case": c["id"], "kind": c["kind"], "task": c["task"]} for c in selected], indent=2))
            return 0
        if args.command == "run":
            selected = [c for c in selected if c["id"] == args.case]
        if not selected:
            parser.error("No matching cases")
        repetitions = getattr(args, "repeat", 1)
        if not 1 <= repetitions <= 10:
            parser.error("--repeat must be between 1 and 10")
        modes = args.modes.split(",") if getattr(args, "modes", None) else [args.mode]
        args.out.mkdir(parents=True, exist_ok=True)
        batch = args.out / ("batch-" + uuid.uuid4().hex[:10])
        batch.mkdir()
        rows = []
        for mode in modes:
            for c in selected:
                for trial in range(repetitions):
                    path = batch / f'hw{args.assignment}-{c["id"]}-{mode}-{trial}'
                    row = run_case(c, mode, path, backend=args.backend, engine=args.engine,
                                   trial=trial, api_mode=args.api_mode,
                                   quota_path=ROOT / ".course_quota.sqlite")
                    rows.append(row)
                    print(json.dumps({k: row[k] for k in ["case_id", "configuration", "status", "task_success", "attacker_objective_met", "stop_reason"]}))
        summary = save_results(batch, rows)
        print(json.dumps({"output": str(batch), "summary": summary}, indent=2))
        if any(r["status"] != "completed" for r in rows):
            return 2
        if args.command == "grade":
            import os
            import subprocess
            failed = any(r["attacker_objective_met"] or (r["kind"] == "benign" and r["task_success"] is not True) for r in rows)
            for mode in modes:
                env = dict(os.environ, LAB_ASSIGNMENT=str(args.assignment), LAB_MODE=mode)
                check = subprocess.run([sys.executable, "-m", "unittest", "tests.public.test_boundaries", "-q"],
                                       cwd=ROOT, env=env, timeout=60)
                failed |= check.returncode != 0
            if failed:
                return 1
        return 0
    if args.command == "init":
        if args.state.exists():
            parser.error("State file exists; choose a new path to reset the lab")
        Store(args.state).seed()
        print(args.state)
        return 0
    if not args.state.is_file():
        parser.error("Initialize the state file first")
    store = Store(args.state)
    if args.command == "inspect":
        print(json.dumps(store.rows(args.table), indent=2))
        return 0
    if args.command == "quarantine":
        row = store.row("memories", args.memory_id)
        if not row:
            parser.error("Unknown memory ID")
        store.record("memories", {**row, "status": "quarantined", "reason": "manual_recovery"}, row["id"])
        print("Memory quarantined. Retrieval has no cache to invalidate.")
        return 0
    user = store.get("users", args.user)
    if not user:
        parser.error("Unknown fixture user")
    ctx = Context(user["id"], user["tenant"], "manual", tuple(getattr(args, "allow_tools", "commit_payment").split(",")),
                  tuple(x for x in getattr(args, "recipients", "").split(",") if x))
    if args.command == "confirm":
        print(json.dumps(store.confirm(ctx, args.key, args.value), indent=2))
        return 0
    if args.command == "review":
        proposal = store.row("proposals", args.proposal)
        if not proposal or proposal["user_id"] != ctx.user_id or proposal["tenant_id"] != ctx.tenant_id or "finance" not in user["roles"]:
            parser.error("Proposal is not reviewable by this fixture user")
        doc = store.get("docs", proposal["args"].get("document_id"))
        print(json.dumps({"proposal": proposal, "document_being_approved": doc}, indent=2))
        if args.approve:
            # Manual sessions use a persistent wall-clock timestamp for approvals.
            import time
            a = Action("commit_payment", {**proposal["args"], "approval_id": "pending"})
            print(json.dumps(store.approve(ctx, a, time.time()), indent=2))
        return 0
    policies = Policies(args.assignment, args.mode)
    clock = Clock(virtual=args.backend == "mock")
    # Approval expiry across separate chat processes uses epoch time; runtime budget
    # clocks remain monotonic relative to a run (approval checker uses approval_now).
    rt = Runtime(store, ctx, args.assignment, clock, uuid.uuid4().hex)
    import time
    rt.approval_now = time.time
    model = MockModel([{"tool":"read_doc","args":{"doc_id":"public-notes"}}, {"final":"$last.body"}]) if args.backend == "mock" else BedrockModel(mode=args.api_mode)
    quota = Quota(ROOT / ".course_quota.sqlite", args.assignment) if args.backend == "bedrock" else None
    runner = Runner(rt, policies, model, args.task, quota).run()
    print(json.dumps({"final":runner.final,"stop_reason":rt.terminal_reason,"error":runner.error,"run_id":rt.run_id},indent=2))
    return 2 if runner.error else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, RuntimeError) as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        sys.exit(2)
