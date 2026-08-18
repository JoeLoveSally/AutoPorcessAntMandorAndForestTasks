from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import subprocess
from typing import Protocol

from ..runtime.errors import DeviceError, LaunchError


@dataclass(frozen=True)
class DeviceInfo:
    serial: str
    state: str
    details: str = ""


class AndroidDevice(Protocol):
    serial: str

    def launch_package(self, package: str) -> None: ...
    def force_stop_package(self, package: str) -> None: ...
    def current_package_activity(self) -> tuple[str | None, str | None]: ...
    def screenshot(self, destination: Path) -> Path: ...
    def screenshot_bytes(self) -> bytes: ...
    def dump_ui(self, destination: Path) -> Path: ...
    def tap(self, point: tuple[int, int]) -> None: ...
    def tap_many(self, points: list[tuple[int, int]]) -> None: ...
    def swipe(self, start: tuple[int, int], end: tuple[int, int], duration_ms: int = 400) -> None: ...
    def back(self) -> None: ...
    def screen_size(self) -> tuple[int, int]: ...


class AdbDevice:
    _ACTIVITY = re.compile(r"(?:mResumedActivity:|topResumedActivity=).*?\s(\S+?)/(\S+?)(?:\s|})")

    def __init__(self, serial: str, adb_path: str = "adb", timeout: float = 20.0):
        self.serial = serial
        self.adb_path = adb_path
        self.timeout = timeout

    @classmethod
    def connect(cls, serial: str = "", adb_path: str = "adb", timeout: float = 20.0) -> "AdbDevice":
        if Path(adb_path).is_file() is False and shutil.which(adb_path) is None:
            raise DeviceError(f"ADB not found: {adb_path}")
        devices = cls._list_devices(adb_path, timeout)
        if serial:
            selected = next((item for item in devices if item.serial == serial), None)
            if selected is None:
                raise DeviceError(f"Configured device not found: {serial}")
            if selected.state != "device":
                raise DeviceError(f"Device {serial} is not ready: {selected.state}")
            return cls(serial, adb_path, timeout)
        ready = [item for item in devices if item.state == "device"]
        if len(ready) != 1:
            detail = ", ".join(f"{item.serial}:{item.state}" for item in devices) or "none"
            raise DeviceError(f"Expected exactly one ready device, found: {detail}")
        return cls(ready[0].serial, adb_path, timeout)

    @staticmethod
    def _list_devices(adb_path: str, timeout: float) -> list[DeviceInfo]:
        try:
            result = subprocess.run(
                [adb_path, "devices", "-l"], capture_output=True, timeout=timeout, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise DeviceError("Unable to query ADB devices") from exc
        if result.returncode:
            raise DeviceError(result.stderr.decode(errors="replace").strip() or "adb devices failed")
        devices: list[DeviceInfo] = []
        for line in result.stdout.decode(errors="replace").splitlines()[1:]:
            parts = line.split(maxsplit=2)
            if len(parts) >= 2:
                devices.append(DeviceInfo(parts[0], parts[1], parts[2] if len(parts) == 3 else ""))
        return devices

    def _run(self, *args: str, binary: bool = False):
        command = [self.adb_path, "-s", self.serial, *args]
        try:
            result = subprocess.run(command, capture_output=True, timeout=self.timeout, check=False)
        except subprocess.TimeoutExpired as exc:
            raise DeviceError(f"ADB timeout: {' '.join(args)}") from exc
        except OSError as exc:
            raise DeviceError(f"ADB execution failed: {exc}") from exc
        if result.returncode:
            message = (result.stderr or result.stdout).decode(errors="replace").strip()
            raise DeviceError(message or f"ADB command failed: {' '.join(args)}")
        return result.stdout if binary else result.stdout.decode(errors="replace")

    def shell(self, *args: str) -> str:
        return self._run("shell", *args)

    def launch_package(self, package: str) -> None:
        output = self.shell(
            "cmd", "package", "resolve-activity", "--brief",
            "-a", "android.intent.action.MAIN",
            "-c", "android.intent.category.LAUNCHER", package,
        )
        component = next(
            (line.strip() for line in reversed(output.splitlines()) if line.strip().startswith(f"{package}/")),
            None,
        )
        if not component:
            raise LaunchError(f"Launcher not found for {package}")
        started = self.shell("am", "start", "-W", "-n", component)
        if "Error:" in started or "Exception" in started:
            raise LaunchError(started.strip())

    def force_stop_package(self, package: str) -> None:
        self.shell("am", "force-stop", package)

    def current_package_activity(self) -> tuple[str | None, str | None]:
        output = self.shell("dumpsys", "activity", "activities")
        for line in output.splitlines():
            match = self._ACTIVITY.search(line.strip())
            if match:
                return match.group(1), match.group(2)
        return None, None

    def screenshot(self, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self._run("exec-out", "screencap", "-p", binary=True))
        return destination

    def screenshot_bytes(self) -> bytes:
        return self._run("exec-out", "screencap", "-p", binary=True)

    def dump_ui(self, destination: Path) -> Path:
        destination.parent.mkdir(parents=True, exist_ok=True)
        remote = "/sdcard/auto_process_window.xml"
        self.shell("uiautomator", "dump", "--compressed", remote)
        content = self._run("exec-out", "cat", remote, binary=True)
        if not content.lstrip().startswith(b"<?xml"):
            raise DeviceError("UIAutomator returned invalid XML")
        destination.write_bytes(content)
        return destination

    def tap(self, point: tuple[int, int]) -> None:
        self.shell("input", "tap", str(point[0]), str(point[1]))

    def tap_many(self, points: list[tuple[int, int]]) -> None:
        for point in points:
            self.tap(point)

    def swipe(self, start: tuple[int, int], end: tuple[int, int], duration_ms: int = 400) -> None:
        self.shell(
            "input", "swipe", str(start[0]), str(start[1]), str(end[0]), str(end[1]), str(duration_ms)
        )

    def back(self) -> None:
        self.shell("input", "keyevent", "KEYCODE_BACK")

    def screen_size(self) -> tuple[int, int]:
        output = self.shell("wm", "size")
        match = re.search(r"(\d+)x(\d+)", output)
        if not match:
            raise DeviceError("Unable to determine screen size")
        return int(match.group(1)), int(match.group(2))
