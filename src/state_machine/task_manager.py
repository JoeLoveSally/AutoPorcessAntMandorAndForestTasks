"""Global task scheduling; business decisions stay in workflow modules.

Task paths (for example manor.family.donate_egg) identify the current
module and leaf task. The persistent Store owns the only task status record.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from domain_data import AutomationError

TERMINAL = frozenset({"SUCCESS", "ALREADY_DONE", "SKIPPED"})


@dataclass(frozen=True)
class TaskSpec:
    task_id: str
    module: str
    execute: Callable[[], None]

    def __post_init__(self):
        if not self.task_id or not self.module or not callable(self.execute):
            raise ValueError("Task requires an ID, module and executable workflow")


class TaskManager:
    """Runs selected tasks in declared order and stops at the first failure.

    Store.task() is the only status writer. A workflow must call Session.done()
    after checking the actual Alipay page; returning without evidence is failure.
    A previously successful local record never authorizes skipping page probing.
    """

    def __init__(self, store, logger, session):
        self.store = store
        self.logger = logger
        self.session = session
        self.current_task: str | None = None
        self.completed: list[str] = []

    @property
    def current_module(self) -> str | None:
        if self.current_task is None:
            return None
        return self.current_task.rpartition(".")[0]

    def run(self, tasks: Iterable[TaskSpec]) -> None:
        for spec in tasks:
            self.current_task = spec.task_id
            self.session.task = spec.task_id
            previous = self.store.status(spec.task_id)
            self.store.task(spec.task_id, "RUNNING", {"previous_status": previous})
            self.logger.emit("task.started", task=spec.task_id, module=spec.module,
                             previous_status=previous)
            try:
                spec.execute()
                status = self.store.status(spec.task_id)
                if status not in TERMINAL:
                    raise AutomationError(
                        f"Workflow {spec.task_id} returned without verified completion",
                        "NO_COMPLETION_EVIDENCE",
                    )
            except BaseException as exc:
                # Do not rewrite a successfully verified business result if a
                # later navigation/cleanup operation raised an exception.
                current = self.store.status(spec.task_id)
                if current not in TERMINAL:
                    self.store.task(spec.task_id, "FAILED", {
                        "reason": getattr(exc, "code", "INTERRUPTED"),
                        "message": str(exc),
                    })
                self.logger.emit("task.failed", task=spec.task_id,
                                 status=self.store.status(spec.task_id),
                                 reason=getattr(exc, "code", "INTERRUPTED"),
                                 error=str(exc))
                raise
            self.completed.append(spec.task_id)
            self.logger.emit("task.finished", task=spec.task_id, status=status)
        self.current_task = None


def select_tasks(tasks: Iterable[TaskSpec], command: str, module: str | None = None,
                 task: str | None = None) -> list[TaskSpec]:
    """Debug selects only the requested task or module, never its prerequisites."""
    selected = [spec for spec in tasks if command == "daily"
                or spec.task_id == task or (not task and spec.module == module)]
    if not selected:
        raise AutomationError("Unknown task or module", "INVALID_TASK")
    return selected
