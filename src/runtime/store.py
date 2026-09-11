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
            CREATE TABLE IF NOT EXISTS actions (
                id INTEGER PRIMARY KEY, serial TEXT, day TEXT, task TEXT, run TEXT,
                name TEXT, state TEXT, before_id TEXT, after_id TEXT, detail TEXT);
        """)

    def close(self):
        self.db.close()
        self.lock.close()

    def status(self, task):
        row = self.db.execute("SELECT status FROM tasks WHERE serial=? AND day=? AND task=?",
                              (self.serial, self.day, task)).fetchone()
        return row[0] if row else None

    def unresolved(self, task):
        return self.db.execute("SELECT id, name, detail FROM actions WHERE serial=? AND day=? AND task=? "
                               "AND state IN ('INTENT','SENT','RESULT_UNKNOWN')",
                               (self.serial, self.day, task)).fetchall()

    def task(self, task, status, evidence):
        with self.db:
            self.db.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?) ON CONFLICT(serial,day,task) "
                            "DO UPDATE SET status=excluded.status,evidence=excluded.evidence,run=excluded.run",
                            (self.serial, self.day, task, status, json.dumps(evidence), self.run))

    def intent(self, task, name, before, detail):
        if self.unresolved(task):
            raise AutomationError(f"Unresolved submission for {task}", "RESULT_UNKNOWN")
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
