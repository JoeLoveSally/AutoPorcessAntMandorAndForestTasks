from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from domain_data import StepResult, StepStatus
from logger import RunLogger
from runtime.errors import AutomationError
from runtime.state_store import StateStore

Probe = Callable[[], StepStatus | None]
Operation = Callable[[], None]
Verification = Callable[[], bool]


@dataclass(frozen=True, slots=True)
class AtomicStep:
    name: str
    probe: Probe
    perform: Operation
    verify: Verification
    max_attempts: int = 1


class StateMachine:
    def __init__(
        self,
        run_id: str,
        workflow: str,
        store: StateStore,
        logger: RunLogger,
    ):
        self.run_id = run_id
        self.workflow = workflow
        self.store = store
        self.logger = logger

    def execute(self, step: AtomicStep) -> StepResult:
        initial = step.probe()
        if initial in (StepStatus.SUCCESS, StepStatus.ALREADY_DONE, StepStatus.NOT_AVAILABLE):
            result = StepResult(step.name, initial, "resolved by current page state", 0)
            self.record(result)
            return result
        self.begin(step.name)
        error: Exception | None = None
        for attempt in range(1, step.max_attempts + 1):
            try:
                step.perform()
                if step.verify():
                    result = StepResult(step.name, StepStatus.SUCCESS, attempts=attempt)
                    self.record(result)
                    return result
                error = AutomationError("verification returned false")
            except Exception as exc:
                error = exc
            self.logger.emit("step.retry", step=step.name, attempt=attempt, error=str(error))
        result = StepResult(step.name, StepStatus.FAILED, str(error or "unknown failure"), step.max_attempts)
        self.record(result)
        return result

    def begin(
        self,
        name: str,
        observation_id: str | None = None,
        detail: str | None = None,
    ) -> None:
        self.store.save_step(
            self.run_id,
            self.workflow,
            name,
            StepStatus.IN_PROGRESS,
            observation_id,
            detail,
        )
        self.logger.emit(
            "step.started",
            step=name,
            observation_id=observation_id,
            detail=detail,
        )

    def record(
        self,
        result: StepResult,
        observation_id: str | None = None,
    ) -> None:
        self.store.save_step(
            self.run_id,
            self.workflow,
            result.name,
            result.status,
            observation_id=observation_id,
            detail=result.detail,
        )
        self.logger.emit(
            "step.finished",
            step=result.name,
            status=result.status.value,
            attempts=result.attempts,
            detail=result.detail,
        )
