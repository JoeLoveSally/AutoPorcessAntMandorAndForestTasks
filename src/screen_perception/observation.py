from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

from device_bridge.adb import AndroidDevice
from domain_data import Observation
from logger import RunLogger
from screen_perception.ui_tree import UiTree


class ObservationMode(StrEnum):
    FAST = "fast"
    FULL = "full"


class ObservationCollector:
    def __init__(self, device: AndroidDevice, logger: RunLogger | None = None):
        self.device = device
        self.logger = logger
        self._sequence = 0

    def capture(
        self,
        directory: Path | None,
        reason: str,
        mode: ObservationMode = ObservationMode.FULL,
    ) -> Observation:
        self._sequence += 1
        observation_id = f"{self._sequence:04d}-{uuid.uuid4().hex[:8]}"
        prefix = f"{self._sequence:04d}-{_safe(reason)}"
        screenshot_path = directory / f"{prefix}.png" if directory else None
        ui_tree_path = directory / f"{prefix}.xml" if directory and mode is ObservationMode.FULL else None
        if directory:
            directory.mkdir(parents=True, exist_ok=True)
        errors: list[str] = []
        screenshot: bytes | None = None
        xml: bytes | None = None
        tree: UiTree | None = None
        if mode is ObservationMode.FULL:
            for attempt in range(2):
                try:
                    before = self.device.screenshot_bytes()
                    xml = self.device.dump_ui_xml()
                    screenshot = self.device.screenshot_bytes()
                    tree = UiTree.from_bytes(xml)
                    if not _materially_changed(before, screenshot):
                        break
                    if attempt == 1:
                        errors.append("unstable_observation:page changed during capture")
                except Exception as exc:
                    errors.append(f"full_observation:{exc}")
                    break
        else:
            try:
                screenshot = self.device.screenshot_bytes()
            except Exception as exc:
                errors.append(f"screenshot:{exc}")
        if screenshot_path and screenshot is not None:
            screenshot_path.write_bytes(screenshot)
        if ui_tree_path and xml is not None:
            ui_tree_path.write_bytes(xml)
        try:
            package, activity = self.device.current_package_activity()
        except Exception as exc:
            package, activity = None, None
            errors.append(f"activity:{exc}")
        size = self.device.size()
        observation = Observation(
            id=observation_id,
            captured_at=datetime.now(timezone.utc),
            device_serial=self.device.serial,
            package=package,
            activity=activity,
            width=size.width,
            height=size.height,
            screenshot_path=screenshot_path,
            ui_tree_path=ui_tree_path,
            screenshot=screenshot,
            ui_tree=tree,
            errors=tuple(errors),
        )
        if self.logger:
            self.logger.emit(
                "observation.captured",
                observation_id=observation.id,
                reason=reason,
                mode=mode.value,
                package=package,
                activity=activity,
                errors=errors,
                screenshot=screenshot_path.name if screenshot_path else None,
            )
        return observation


def _safe(value: str) -> str:
    return "".join(character if character.isalnum() or character in "-_" else "-" for character in value)[:80]


def _materially_changed(before: bytes, after: bytes) -> bool:
    try:
        import cv2
        import numpy as np

        first = cv2.imdecode(np.frombuffer(before, np.uint8), cv2.IMREAD_GRAYSCALE)
        second = cv2.imdecode(np.frombuffer(after, np.uint8), cv2.IMREAD_GRAYSCALE)
        if first is None or second is None or first.shape != second.shape:
            return True
        width = 180
        height = max(1, round(first.shape[0] * width / first.shape[1]))
        first = cv2.resize(first, (width, height))
        second = cv2.resize(second, (width, height))
        # Carousels and game animation commonly occupy the upper half.  Element
        # coordinates used for actions live predominantly in the lower half;
        # compare that stable action area so animation does not poison an
        # otherwise coherent UI-tree/screenshot pair.
        first = first[first.shape[0] // 2 :, :]
        second = second[second.shape[0] // 2 :, :]
        changed = np.count_nonzero(cv2.absdiff(first, second) > 20)
        return changed / first.size > 0.08
    except Exception:
        return before != after
