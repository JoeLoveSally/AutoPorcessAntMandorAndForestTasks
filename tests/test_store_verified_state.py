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


def test_second_account_does_not_inherit_the_first_accounts_records(tmp_path):
    # Two Alipay accounts share one phone and therefore one serial. The raw
    # serial would let the second account read the first's records, and the
    # diary's verified_status guard, the unresolved-submission guard and the
    # kitchen reconciliation all decide from this key - so the second account
    # would skip a task the first one finished.
    first = Store(tmp_path, "serial", "run-1", account="main")
    try:
        first.task("manor.home.diary", "SUCCESS", {"observation": "obs-1"})
        assert first.verified_status("manor.home.diary") == "SUCCESS"
    finally:
        first.close()

    second = Store(tmp_path, "serial", "run-2", account="xiao")
    try:
        assert second.status("manor.home.diary") is None
        assert second.verified_status("manor.home.diary") is None
    finally:
        second.close()


def test_two_accounts_still_cannot_drive_the_same_phone_at_once(tmp_path):
    # The lock covers the device, not the account: whichever account a run
    # is working, it must own the phone exclusively.
    held = Store(tmp_path, "serial", "run-1", account="main")
    try:
        with pytest.raises(AutomationError,
                           match="Another process controls this device"):
            Store(tmp_path, "serial", "run-2", account="xiao")
    finally:
        held.close()

