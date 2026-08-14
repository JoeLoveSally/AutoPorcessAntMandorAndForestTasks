from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ..device.adb import AndroidDevice
from ..domain.models import Observation
from .ui_tree import UiTree


class ObservationCollector:
    def __init__(self, device: AndroidDevice):
        self.device = device

    def observe(self, directory: Path | None = None, name: str = "observation") -> Observation:
        timestamp = datetime.now(timezone.utc)
        screenshot_path: Path | None = None
        ui_tree_path: Path | None = None
        ui_tree: UiTree | None = None
        errors: list[str] = []
        if directory is not None:
            directory.mkdir(parents=True, exist_ok=True)
            screenshot_path = directory / f"{name}.png"
            ui_tree_path = directory / f"{name}.xml"
            try:
                self.device.screenshot(screenshot_path)
            except Exception as exc:
                errors.append(f"screenshot: {exc}")
                screenshot_path = None
            try:
                self.device.dump_ui(ui_tree_path)
                ui_tree = UiTree.from_file(ui_tree_path)
            except Exception as exc:
                errors.append(f"ui_tree: {exc}")
                ui_tree_path = None
        try:
            package, activity = self.device.current_package_activity()
        except Exception as exc:
            package, activity = None, None
            errors.append(f"activity: {exc}")
        labels = ui_tree.visible_labels() if ui_tree else ()
        return Observation(
            timestamp=timestamp,
            device_serial=self.device.serial,
            package=package,
            activity=activity,
            screenshot_path=screenshot_path,
            ui_tree_path=ui_tree_path,
            ui_tree=ui_tree,
            visible_labels=labels,
            errors=tuple(errors),
        )
