"""Outer course quota persists across resets and comparisons; not a student hook."""
from pathlib import Path
import sqlite3
from lab.types import BudgetExceeded


class Quota:
    def __init__(self, path, assignment):
        self.path, self.assignment = str(path), assignment
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=15) as db:
            # Serialize the first open so concurrent workers can upgrade a shared quota.
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE IF NOT EXISTS quota(assignment INTEGER PRIMARY KEY, attempts INTEGER NOT NULL)")
            columns = {row[1] for row in db.execute("PRAGMA table_info(quota)")}
            if "week" in columns:
                db.execute("ALTER TABLE quota RENAME COLUMN week TO assignment")
            db.execute("INSERT OR IGNORE INTO quota (assignment, attempts) VALUES (?, 0)", (assignment,))

    def reserve(self):
        with sqlite3.connect(self.path, timeout=15) as db:
            db.execute("BEGIN IMMEDIATE")
            used = db.execute("SELECT attempts FROM quota WHERE assignment=?", (self.assignment,)).fetchone()[0]
            if used >= (240 if self.assignment == 1 else 120):
                raise BudgetExceeded("outer_course_quota")
            db.execute("UPDATE quota SET attempts=attempts+1 WHERE assignment=?", (self.assignment,))

