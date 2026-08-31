import sqlite3
from pathlib import Path

from domain_data import StepStatus
from runtime.state_store import StateStore


def test_step_upsert_and_latest(tmp_path: Path):
    store = StateStore(tmp_path / "state.db")
    store.save_step("run-1", "daily", "donate", StepStatus.IN_PROGRESS, "before")
    store.save_step("run-1", "daily", "donate", StepStatus.SUCCESS, "after")
    latest = store.latest_step("daily", "donate")
    assert latest is not None
    assert latest.status is StepStatus.SUCCESS
    assert latest.observation_id == "after"


def test_incomplete_steps_only_returns_latest_unresolved_records(tmp_path: Path):
    store = StateStore(tmp_path / "state.db")
    store.save_step("run-1", "daily", "donate", StepStatus.IN_PROGRESS)
    store.save_step("run-2", "daily", "donate", StepStatus.SUCCESS)
    store.save_step("run-2", "daily", "water", StepStatus.IN_PROGRESS)
    store.save_step("run-2", "forest", "rain", StepStatus.IN_PROGRESS)

    incomplete = store.incomplete_steps("daily")

    assert [item.step for item in incomplete] == ["water"]


def test_process_lock_is_exclusive(tmp_path: Path):
    store = StateStore(tmp_path / "state.db")
    assert store.acquire_lock("daily", "one")
    assert not store.acquire_lock("daily", "two")
    store.release_lock("daily", "one")
    assert store.acquire_lock("daily", "two")


def test_dead_process_lock_is_reclaimed(tmp_path: Path):
    store = StateStore(tmp_path / "state.db")
    with store._connect() as connection:
        connection.execute(
            "INSERT INTO process_lock(name, owner, acquired_at, pid) VALUES (?, ?, ?, ?)",
            ("daily", "crashed-run", "2026-01-01T00:00:00+00:00", 999_999_999),
        )

    assert store.acquire_lock("daily", "new-run")


def test_existing_lock_table_is_migrated_with_pid(tmp_path: Path):
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE process_lock (name TEXT PRIMARY KEY, owner TEXT NOT NULL, acquired_at TEXT NOT NULL)"
        )

    store = StateStore(path)
    with store._connect() as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(process_lock)")}

    assert "pid" in columns
