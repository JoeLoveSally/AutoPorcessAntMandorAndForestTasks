"""Offline tests; no phone or third-party dependencies required."""

import unittest
from types import SimpleNamespace

from domain_data import AutomationError
from state_machine.task_manager import TaskManager, TaskSpec, select_tasks


class FakeStore:
    def __init__(self):
        self.states = {}
        self.events = []

    def status(self, task):
        return self.states.get(task)

    def task(self, task, status, evidence):
        self.states[task] = status
        self.events.append((task, status, evidence))


class FakeLogger:
    def __init__(self):
        self.events = []

    def emit(self, name, **fields):
        self.events.append((name, fields))


class TaskManagerTests(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()
        self.logger = FakeLogger()
        self.session = SimpleNamespace(task=None)
        self.manager = TaskManager(self.store, self.logger, self.session)

    def test_success_then_next_task(self):
        seen = []

        def finish():
            seen.append((self.manager.current_task, self.manager.current_module, self.session.task))
            self.store.task(self.session.task, "SUCCESS", {"page": "manor"})

        self.manager.run([TaskSpec("manor.home.diary", "manor_home", finish),
                          TaskSpec("manor.family.donate_egg", "manor_family", finish)])
        self.assertEqual([item[0] for item in seen],
                         ["manor.home.diary", "manor.family.donate_egg"])
        self.assertEqual(seen[0][1], "manor.home")
        self.assertEqual(self.manager.current_task, None)
        self.assertEqual(len(self.manager.completed), 2)

    def test_previous_success_does_not_skip_actual_page_probe(self):
        task = "manor.home.diary"
        self.store.states[task] = "SUCCESS"
        seen = []

        def probe():
            seen.append(self.store.status(task))
            self.store.task(task, "ALREADY_DONE", {"page": "diary"})

        self.manager.run([TaskSpec(task, "manor_home", probe)])
        self.assertEqual(seen, ["RUNNING"])
        self.assertEqual(self.store.status(task), "ALREADY_DONE")

    def test_return_without_completion_evidence_fails_closed(self):
        task = "manor.home.diary"
        with self.assertRaises(AutomationError) as raised:
            self.manager.run([TaskSpec(task, "manor_home", lambda: None)])
        self.assertEqual(raised.exception.code, "NO_COMPLETION_EVIDENCE")
        self.assertEqual(self.store.status(task), "FAILED")
        self.assertEqual(self.manager.completed, [])

    def test_failure_stops_remaining_tasks(self):
        task = "manor.family.donate_egg"
        later = []

        def resource_failure():
            raise AutomationError("No eggs", "RESOURCE")

        with self.assertRaises(AutomationError):
            self.manager.run([TaskSpec(task, "manor_family", resource_failure),
                              TaskSpec("manor.family.meal", "manor_family", lambda: later.append(True))])
        self.assertEqual(self.store.status(task), "FAILED")
        self.assertEqual(self.store.events[-1][2]["reason"], "RESOURCE")
        self.assertEqual(later, [])

    def test_debug_selects_only_requested_task(self):
        tasks = [TaskSpec("manor.home.diary", "manor_home", lambda: None),
                 TaskSpec("manor.family.donate_egg", "manor_family", lambda: None)]
        self.assertEqual([t.task_id for t in select_tasks(tasks, "debug", task="manor.home.diary")],
                         ["manor.home.diary"])
        self.assertEqual([t.task_id for t in select_tasks(tasks, "debug", module="manor_family")],
                         ["manor.family.donate_egg"])


if __name__ == "__main__":
    unittest.main()
