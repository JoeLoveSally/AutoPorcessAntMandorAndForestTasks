from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from ..domain.models import Observation, RunResult


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
