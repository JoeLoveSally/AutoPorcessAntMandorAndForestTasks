from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any

from ..domain.models import Observation, RunResult


class HumanRunLogger:
    def __init__(self, directory: Path, started_at: datetime):
        directory.mkdir(parents=True, exist_ok=True)
        timestamp = started_at.strftime("%Y%m%d-%H%M%S-%f")
        self.path = directory / f"{timestamp}.log"
        self.logger = logging.getLogger("ants_automation")

    def info(self, event: str, **fields: Any) -> None:
        detail = " ".join(f"{key}={value!r}" for key, value in fields.items())
        message = f"{event} {detail}".rstrip()
        timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(f"{timestamp} INFO {message}\n")
        self.logger.info(message)


class EvidenceRecorder:
    def __init__(self, root: Path):
        self.root = root

    def new_run(self) -> Path:
        run = self.root / datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
        run.mkdir(parents=True, exist_ok=False)
        return run

    @staticmethod
    def write_observation_metadata(run: Path, observation: Observation, name: str) -> Path:
        path = run / f"{name}.json"
        path.write_text(
            json.dumps(
                {
                    "timestamp": observation.timestamp.isoformat(),
                    "device": observation.device_serial,
                    "package": observation.package,
                    "activity": observation.activity,
                    "screenshot": str(observation.screenshot_path) if observation.screenshot_path else None,
                    "ui_xml": str(observation.ui_tree_path) if observation.ui_tree_path else None,
                    "visible_labels": list(observation.visible_labels),
                    "errors": list(observation.errors),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        return path

    @staticmethod
    def write_result(run: Path, result: RunResult) -> Path:
        path = run / "result.json"
        path.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        return path
