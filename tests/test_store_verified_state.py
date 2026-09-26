import pytest

from domain_data import AutomationError
from runtime.store import Store


def test_existing_verified_task_is_migrated_before_next_run(tmp_path):
    import sqlite3

    database = sqlite3.connect(tmp_path / "task_state.db")
    database.execute(
        "CREATE TABLE tasks (serial TEXT, day TEXT, task TEXT, status TEXT, "
        "evidence TEXT, run TEXT, PRIMARY KEY(serial, day, task))"
    )
    database.execute(
        "INSERT INTO tasks VALUES ('serial', date('now'), 'forest.love', "
        "'SUCCESS', '{}', 'old-run')"
    )
    database.commit()
    database.close()

    store = Store(tmp_path, "serial", "new-run")
    try:
        assert store.verified_status("forest.love") == "SUCCESS"
    finally:
        store.close()


def test_running_state_does_not_erase_last_verified_result(tmp_path):
    store = Store(tmp_path, "serial", "run-1")
    try:
        store.task("forest.cooperate", "SUCCESS", {"observation": "done"})
        store.task("forest.cooperate", "RUNNING", {"previous_status": "SUCCESS"})

        assert store.status("forest.cooperate") == "RUNNING"
        assert store.verified_status("forest.cooperate") == "SUCCESS"
    finally:
        store.close()


def test_failed_probe_does_not_replace_verified_result(tmp_path):
    store = Store(tmp_path, "serial", "run-1")
    try:
        store.task("forest.love", "ALREADY_DONE", {"observation": "done"})
        store.task("forest.love", "FAILED", {"reason": "OCR"})

        assert store.status("forest.love") == "FAILED"
        assert store.verified_status("forest.love") == "ALREADY_DONE"
    finally:
        store.close()


def test_unresolved_submission_names_the_stuck_action(tmp_path):
    # Device evidence (2026-09-23): the forest sign's RESULT_UNKNOWN blocked
    # the ad-claim tap an hour later, and the bare message pointed at the
    # claim instead of the sign that actually caused it.
    store = Store(tmp_path, "serial", "run-1")
    try:
        action = store.intent("forest.friends", "lottery-sign", "obs-1",
                              {"target": "签到"})
        store.action(action, "RESULT_UNKNOWN")

        with pytest.raises(AutomationError,
                           match=r"'lottery-sign' awaits evidence"):
            store.intent("forest.friends", "lottery-ad-claim", "obs-2",
                         {"ad": 1})
    finally:
        store.close()
