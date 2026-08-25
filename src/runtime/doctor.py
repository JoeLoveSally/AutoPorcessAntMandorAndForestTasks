from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from device_bridge.adb import AdbDevice
from runtime.config import Config


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    ok: bool
    detail: str


def run_doctor(config: Config) -> list[Check]:
    checks: list[Check] = []
    for name, executable in (
        ("adb", config.device.adb_path),
        ("ffmpeg", "ffmpeg"),
        ("scrcpy", config.realtime.scrcpy_path),
    ):
        found = shutil.which(executable)
        checks.append(Check(name, found is not None, found or f"not found: {executable}"))
    try:
        device = AdbDevice.connect(
            config.device.serial,
            config.device.adb_path,
            config.device.timeout_seconds,
        )
        size = device.size()
        package, activity = device.current_package_activity()
        checks.append(Check("device", True, f"{device.serial} {size.width}x{size.height}"))
        checks.append(Check("foreground", True, f"{package or '-'} / {activity or '-'}"))
    except Exception as exc:
        checks.append(Check("device", False, str(exc)))
    for name, path in (
        ("logs_directory", config.runtime.logs_directory),
        ("screenshots_directory", config.runtime.screenshots_directory),
        ("state_directory", config.runtime.state_database.parent),
        ("cache_directory", config.runtime.cache_directory),
    ):
        try:
            Path(path).mkdir(parents=True, exist_ok=True)
            checks.append(Check(name, True, str(path)))
        except OSError as exc:
            checks.append(Check(name, False, str(exc)))
    return checks
