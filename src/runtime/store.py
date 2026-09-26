from __future__ import annotations

import fcntl
import hashlib
import json
import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

from domain_data import AutomationError


class Store:
    def __init__(self, root, serial, run):
        root.mkdir(parents=True, exist_ok=True)
        self.serial, self.run = serial, run
        self.day = datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()
        self.lock = (root / (hashlib.sha256(serial.encode()).hexdigest()[:16] + ".lock")).open("a")
        try:
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.lock.close()
            raise AutomationError("Another process controls this device", "LOCKED") from exc
        self.db = sqlite3.connect(root / "task_state.db")
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS tasks (
                serial TEXT, day TEXT, task TEXT, status TEXT, evidence TEXT, run TEXT,
                PRIMARY KEY(serial, day, task));
            CREATE TABLE IF NOT EXISTS verified_tasks (
                serial TEXT, day TEXT, task TEXT, status TEXT, evidence TEXT, run TEXT,
                PRIMARY KEY(serial, day, task));
            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY, serial TEXT, day TEXT, task TEXT, run TEXT,
                name TEXT, state TEXT, before_id TEXT, after_id TEXT, detail TEXT);
        """)
        # Preserve verified results created by versions that predate the
        # separate verified-state table. This runs before TaskManager can
        # replace the current task row with RUNNING.
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO verified_tasks "
                "SELECT serial,day,task,status,evidence,run FROM tasks "
                "WHERE status IN ('SUCCESS','ALREADY_DONE')"
            )

    def close(self):
        self.db.close()
        self.lock.close()

    def status(self, task):
        row = self.db.execute("SELECT status FROM tasks WHERE serial=? AND day=? AND task=?",
                              (self.serial, self.day, task)).fetchone()
        return row[0] if row else None

    def verified_status(self, task):
        """Return the last page-verified terminal state for this business day.

        TaskManager writes RUNNING before probing the live page. Keeping the
        last verified result separately prevents that transient state from
        removing the guard against repeating a resource-consuming action.
        """
        row = self.db.execute(
            "SELECT status FROM verified_tasks WHERE serial=? AND day=? AND task=?",
            (self.serial, self.day, task),
        ).fetchone()
        return row[0] if row else None

    def unresolved(self, task):
        return self.db.execute("SELECT id, name, detail FROM actions WHERE serial=? AND day=? AND task=? "
                               "AND state IN ('INTENT','SENT','RESULT_UNKNOWN')",
                               (self.serial, self.day, task)).fetchall()

    def pending_frames(self, task):
        """Pending submissions paired with the frame they were fired from.

        The before frame is durable evidence: it records the screen state
        at tap time, so a condition proved by that frame (kitchen run
        3496e7: 做美食 fired while the chickens were out) stays provable
        after the live screen has moved on.
        """
        return self.db.execute("SELECT id, name, before_id, run FROM actions "
                               "WHERE serial=? AND day=? AND task=? "
                               "AND state IN ('INTENT','SENT','RESULT_UNKNOWN')",
                               (self.serial, self.day, task)).fetchall()

    def task(self, task, status, evidence):
        with self.db:
            self.db.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?) ON CONFLICT(serial,day,task) "
                            "DO UPDATE SET status=excluded.status,evidence=excluded.evidence,run=excluded.run",
                            (self.serial, self.day, task, status, json.dumps(evidence), self.run))
            if status in ("SUCCESS", "ALREADY_DONE"):
                self.db.execute(
                    "INSERT INTO verified_tasks VALUES (?,?,?,?,?,?) "
                    "ON CONFLICT(serial,day,task) DO UPDATE SET "
                    "status=excluded.status,evidence=excluded.evidence,run=excluded.run",
                    (self.serial, self.day, task, status, json.dumps(evidence), self.run),
                )

    def intent(self, task, name, before, detail):
        # Device evidence (2026-09-23): a failed spend tap leaves
        # RESULT_UNKNOWN behind (reconcile at done() is the only resolver),
        # so it blocks every later spend for this task that day. Name the
        # stuck action - the bare message sent the diagnosis after the
        # claim tap while the sign tap an hour earlier was the real cause.
        stuck = self.unresolved(task)
        if stuck:
            raise AutomationError(
                f"Unresolved submission for {task}: '{stuck[0][1]}' awaits evidence",
                "RESULT_UNKNOWN")
        with self.db:
            cursor = self.db.execute("INSERT INTO actions(serial,day,task,run,name,state,before_id,detail) "
                                     "VALUES (?,?,?,?,?,'INTENT',?,?)",
                                     (self.serial, self.day, task, self.run, name, before, json.dumps(detail)))
        return cursor.lastrowid

    def action(self, action, state, after=None):
        with self.db:
            self.db.execute("UPDATE actions SET state=?,after_id=? WHERE id=?", (state, after, action))

    def reconcile(self, task, observation):
        with self.db:
            self.db.execute("UPDATE actions SET state='VERIFIED',after_id=? WHERE serial=? AND day=? "
                            "AND task=? AND state IN ('INTENT','SENT','RESULT_UNKNOWN')",
                            (observation, self.serial, self.day, task))
