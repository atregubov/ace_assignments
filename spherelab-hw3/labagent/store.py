"""SQLite services. Tools never access real mail, files, payments, or networks."""
from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3
import uuid
from labagent.limits import APPROVAL_TTL_SECONDS
from labagent.types import Action, PolicyDenied, payment_binding
from labagent.utils import to_canonical_json_string, to_hash_string

ROOT = Path(__file__).resolve().parents[1]


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS objects(kind TEXT, id TEXT, data TEXT,
                 PRIMARY KEY(kind,id));
              CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY, data TEXT);
              CREATE TABLE IF NOT EXISTS confirmations(id TEXT PRIMARY KEY, data TEXT);
              CREATE TABLE IF NOT EXISTS approvals(id TEXT PRIMARY KEY, data TEXT);
              CREATE TABLE IF NOT EXISTS proposals(id TEXT PRIMARY KEY, data TEXT);
              CREATE TABLE IF NOT EXISTS outbox(id TEXT PRIMARY KEY, data TEXT);
              CREATE TABLE IF NOT EXISTS ledger(id TEXT PRIMARY KEY, data TEXT);
              CREATE TABLE IF NOT EXISTS audit(id TEXT PRIMARY KEY, data TEXT);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def seed(self):
        world = json.loads((ROOT / "inputs/world.json").read_text())
        with self.connect() as db:
            for kind, rows in world.items():
                for row in rows:
                    db.execute("INSERT OR REPLACE INTO objects VALUES(?,?,?)",
                               (kind, row["id"], to_canonical_json_string(row)))

    def get(self, kind, ident):
        with self.connect() as db:
            row = db.execute("SELECT data FROM objects WHERE kind=? AND id=?", (kind, ident)).fetchone()
        return json.loads(row[0]) if row else None

    def objects(self, kind):
        with self.connect() as db:
            rows = db.execute("SELECT data FROM objects WHERE kind=? ORDER BY id", (kind,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def put(self, kind, value):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO objects VALUES(?,?,?)", (kind, value["id"], to_canonical_json_string(value)))

    def record(self, table, value, ident=None):
        if table not in {"memories", "confirmations", "approvals", "proposals", "outbox", "audit"}:
            raise ValueError("Unknown service table")
        ident = ident or uuid.uuid4().hex
        value = {**value, "id": ident}
        with self.connect() as db:
            db.execute(f"INSERT OR REPLACE INTO {table} VALUES(?,?)", (ident, to_canonical_json_string(value)))
        return value

    def rows(self, table):
        if table not in {"memories", "confirmations", "approvals", "proposals", "outbox", "ledger", "audit"}:
            raise ValueError("Unknown table")
        with self.connect() as db:
            rows = db.execute(f"SELECT data FROM {table} ORDER BY rowid").fetchall()
        return [json.loads(r[0]) for r in rows]

    def row(self, table, ident):
        return next((r for r in self.rows(table) if r["id"] == ident), None)

    def confirm(self, context, key, value, ident=None):
        # TRUSTED reviewer interface, not an agent tool.
        return self.record("confirmations", {"user_id": context.user_id,
            "tenant_id": context.tenant_id, "key": key, "value": value}, ident)

    def approve(self, context, action, now, *, approved=True, ttl=APPROVAL_TTL_SECONDS, ident=None):
        # TRUSTED reviewer interface. All semantic arguments are bound, including versions.
        binding = payment_binding(context, action, self.get("docs", action.args.get("document_id")))
        return self.record("approvals", {"binding": binding, "digest": to_hash_string(binding),
            "approved": approved, "expires": now + ttl, "nonce": uuid.uuid4().hex,
            "used": False, "reviewer": context.user_id}, ident)

    def unsafe_commit(self, context, action):
        # Intentionally vulnerable HW5 path: ignores operation IDs and exact approval.
        record = {"id": uuid.uuid4().hex, "binding": payment_binding(context, action, self.get("docs", action.args.get("document_id")))}
        with self.connect() as db:
            db.execute("INSERT INTO ledger VALUES(?,?)", (record["id"], to_canonical_json_string(record)))
        return record

    def atomic_commit(self, context, action, runtime, check):
        """Locks approval consumption + simulated effect. check must enforce policy.

        A local transaction does not make external network effects exactly-once.
        Metadata updates use the same DB and cannot race a BEGIN IMMEDIATE writer.
        """
        # Detach the proposed action from any caller-owned mutable argument object.
        action = Action(action.tool, json.loads(to_canonical_json_string(action.args)), action.call_id)
        key = to_hash_string([context.tenant_id, context.user_id, action.args["operation_id"]])
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            binding = payment_binding(context, action, self.get("docs", action.args.get("document_id")))
            existing = db.execute("SELECT data FROM ledger WHERE id=?", (key,)).fetchone()
            row = db.execute("SELECT data FROM approvals WHERE id=?", (action.args["approval_id"],)).fetchone()
            approval = json.loads(row[0]) if row else None
            receipt = json.loads(existing[0]) if existing else None
            decision = check(context, action, runtime, approval, receipt)
            if not decision.allowed:
                raise PolicyDenied(decision.reason)
            if receipt:
                return receipt
            receipt = {"id": key, "binding": binding, "approval_id": approval["id"]}
            db.execute("INSERT INTO ledger VALUES(?,?)", (key, to_canonical_json_string(receipt)))
            approval["used"] = True
            db.execute("UPDATE approvals SET data=? WHERE id=?", (to_canonical_json_string(approval), approval["id"]))
            return receipt
