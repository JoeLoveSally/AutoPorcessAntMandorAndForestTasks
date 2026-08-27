from __future__ import annotations

import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Protocol

from device_bridge.common import DeviceInfo, DeviceMetrics, Size
from runtime.errors import DeviceError


class AndroidDevice(Protocol):
    serial: str

    def launch_package(self, package: str) -> None: ...
    def force_stop_package(self, package: str) -> None: ...
    def current_package_activity(self) -> tuple[str | None, str | None]: ...
    def screenshot_bytes(self) -> bytes: ...
    def dump_ui_xml(self) -> bytes: ...
    def tap(self, point: tuple[int, int]) -> None: ...
    def swipe(self, start: tuple[int, int], end: tuple[int, int], duration_ms: int = 400) -> None: ...
    def back(self) -> None: ...
    def wake(self) -> None: ...
    def size(self) -> Size: ...


class AdbDevice:
    _ACTIVITY = re.compile(
        r"(?:mResumedActivity:|ResumedActivity:|topResumedActivity=).*?\s(\S+?)/(\S+?)(?:\s|})"
    )

    def __init__(self, serial: str, adb_path: str = "adb", timeout: float = 20.0):
        self.serial = serial
        self.adb_path = adb_path
        self.timeout = timeout
        self._size: Size | None = None

    @classmethod
    def connect(cls, serial: str = "", adb_path: str = "adb", timeout: float = 20.0) -> AdbDevice:
        if Path(adb_path).is_file() is False and shutil.which(adb_path) is None:
            raise DeviceError(f"ADB not found: {adb_path}")
        devices = cls.list_devices(adb_path, timeout)
        ready = [item for item in devices if item.state == "device"]
        if serial:
            selected = next((item for item in devices if item.serial == serial), None)
            if selected is None:
                raise DeviceError(f"Configured device not found: {serial}")
            if selected.state != "device":
                raise DeviceError(f"Device {serial} is not ready: {selected.state}")
            return cls(serial, adb_path, timeout)
        if len(ready) != 1:
            detail = ", ".join(f"{item.serial}:{item.state}" for item in devices) or "none"
            raise DeviceError(f"Expected exactly one ready device, found: {detail}")
        return cls(ready[0].serial, adb_path, timeout)

    @staticmethod
    def list_devices(adb_path: str = "adb", timeout: float = 20.0) -> list[DeviceInfo]:
        result = _run_process([adb_path, "devices", "-l"], timeout)
        devices: list[DeviceInfo] = []
        for line in result.decode(errors="replace").splitlines()[1:]:
            parts = line.split(maxsplit=2)
            if len(parts) >= 2:
                devices.append(DeviceInfo(parts[0], parts[1], parts[2] if len(parts) == 3 else ""))
        return devices

    def _run(self, *args: str) -> bytes:
        return _run_process([self.adb_path, "-s", self.serial, *args], self.timeout)

    def shell(self, *args: str) -> str:
        return self._run("shell", *args).decode(errors="replace")

    def launch_package(self, package: str) -> None:
        output = self.shell(
            "cmd", "package", "resolve-activity", "--brief",
            "-a", "android.intent.action.MAIN", "-c", "android.intent.category.LAUNCHER", package,
        )
        component = next(
            (line.strip() for line in reversed(output.splitlines()) if line.strip().startswith(f"{package}/")),
            None,
        )
        if not component:
            raise DeviceError(f"Launcher not found for {package}")
        self.shell("am", "start", "-W", "-n", component)

    def force_stop_package(self, package: str) -> None:
        self.shell("am", "force-stop", package)

    def current_package_activity(self) -> tuple[str | None, str | None]:
        output = self.shell("dumpsys", "activity", "activities")
        for line in output.splitlines():
            if match := self._ACTIVITY.search(line.strip()):
                return match.group(1), match.group(2)
        return None, None

    def screenshot_bytes(self) -> bytes:
        content = self._run("exec-out", "screencap", "-p")
        if not content.startswith(b"\x89PNG"):
            raise DeviceError("ADB returned an invalid screenshot")
        return content

    def dump_ui_xml(self) -> bytes:
        remote = "/data/local/tmp/ants-auto-window.xml"
        self.shell("uiautomator", "dump", "--compressed", remote)
        content = self._run("exec-out", "cat", remote)
        if not content.lstrip().startswith(b"<?xml"):
            raise DeviceError("UIAutomator returned invalid XML")
        return content

    def tap(self, point: tuple[int, int]) -> None:
        if not self.size().contains(point):
            raise DeviceError(f"Tap outside screen: {point}")
        self.shell("input", "tap", str(point[0]), str(point[1]))

    def swipe(self, start: tuple[int, int], end: tuple[int, int], duration_ms: int = 400) -> None:
        if not self.size().contains(start) or not self.size().contains(end):
            raise DeviceError(f"Swipe outside screen: {start} -> {end}")
        self.shell(
            "input", "swipe", str(start[0]), str(start[1]), str(end[0]), str(end[1]), str(duration_ms)
        )

    def back(self) -> None:
        self.shell("input", "keyevent", "KEYCODE_BACK")

    def wake(self) -> None:
        """Wake the screen and dismiss a non-secure keyguard.

        Long idle periods between runs leave the phone asleep; without this
        every observation classifies the AOD clock as an unknown page and the
        recovery ladder burns its budget on Back presses that do nothing.
        """
        self.shell("input", "keyevent", "KEYCODE_WAKEUP")
        time.sleep(0.8)
        if not self._keyguard_showing():
            return
        width, height = self.size().width, self.size().height
        self.shell(
            "input", "swipe",
            str(width // 2), str(int(height * 0.82)),
            str(width // 2), str(int(height * 0.25)),
            "300",
        )
        time.sleep(0.8)
        if self._keyguard_showing():
            raise DeviceError(
                "The keyguard is still showing after waking the device; "
                "unlock the phone once so the run can continue"
            )

    def _keyguard_showing(self) -> bool:
        policy = self.shell("dumpsys", "window", "policy")
        return bool(re.search(r"^\s+showing=true\s*$", policy, re.MULTILINE))

    def size(self) -> Size:
        if self._size is None:
            output = self.shell("wm", "size")
            matches = re.findall(r"(\d+)x(\d+)", output)
            if not matches:
                raise DeviceError("Unable to determine screen size")
            width, height = matches[-1]
            self._size = Size(int(width), int(height))
        return self._size

    def measure(self, operation: str, samples: int = 5) -> DeviceMetrics:
        if samples < 1:
            raise ValueError("samples must be positive")
        durations: list[float] = []
        for _ in range(samples):
            started = time.perf_counter()
            if operation == "screenshot":
                self.screenshot_bytes()
            elif operation == "activity":
                self.current_package_activity()
            elif operation == "ui_dump":
                self.dump_ui_xml()
            else:
                raise ValueError(f"Unknown measurement operation: {operation}")
            durations.append((time.perf_counter() - started) * 1000)
        return DeviceMetrics(operation, tuple(durations))


def _run_process(command: list[str], timeout: float) -> bytes:
    try:
        result = subprocess.run(command, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise DeviceError(f"Command timed out: {' '.join(command[2:])}") from exc
    except OSError as exc:
        raise DeviceError(f"Unable to run {command[0]}: {exc}") from exc
    if result.returncode:
        message = (result.stderr or result.stdout).decode(errors="replace").strip()
        raise DeviceError(message or f"Command failed: {' '.join(command)}")
    return result.stdout
