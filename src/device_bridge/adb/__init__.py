from __future__ import annotations

import re
import subprocess
import time

from domain_data import AutomationError


class Device:
    def __init__(self, serial: str, adb: str = "adb"):
        self.serial, self.adb = serial, adb
        state = self.run("get-state").decode().strip()
        if state != "device":
            raise AutomationError(f"Device {serial}: {state}", "DEVICE")
        self.metrics = []

    def run(self, *args, timeout=20):
        start = time.monotonic()
        try:
            result = subprocess.run([self.adb, "-s", self.serial, *args],
                                    capture_output=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise AutomationError(str(exc), "DEVICE") from exc
        if hasattr(self, "metrics"):
            self.metrics.append((args[:2], time.monotonic() - start))
        if result.returncode:
            raise AutomationError(result.stderr.decode(errors="replace"), "DEVICE")
        return result.stdout

    def shell(self, *args):
        return self.run("shell", *args).decode(errors="replace")

    def info(self):
        return {"serial": self.serial, "model": self.shell("getprop", "ro.product.model").strip(),
                "android": self.shell("getprop", "ro.build.version.release").strip(),
                "size": self.shell("wm", "size").strip(),
                "density": self.shell("wm", "density").strip(),
                "display": self.shell("dumpsys", "input")}

    def foreground(self):
        output = self.shell("dumpsys", "activity", "activities")
        match = re.search(r"(?:topResumedActivity=|mResumedActivity:).*?\s([\w.]+)/", output)
        return match[1] if match else ""

    def screenshot(self):
        data = self.run("exec-out", "screencap", "-p")
        if not data.startswith(b"\x89PNG"):
            raise AutomationError("Invalid screenshot", "DEVICE")
        return data

    def tree(self):
        data = self.run("exec-out", "uiautomator", "dump", "/dev/tty", timeout=10)
        start, end = data.find(b"<?xml"), data.rfind(b"</hierarchy>")
        if start < 0 or end < 0:
            raise AutomationError("UI Tree unavailable", "UI_TREE")
        return data[start:end + len(b"</hierarchy>")]

    def launch(self, package):
        output = self.shell("cmd", "package", "resolve-activity", "--brief", package)
        components = [s.strip() for s in output.splitlines() if s.strip().startswith(package + "/")]
        if not components:
            raise AutomationError("No application launcher", "DEVICE")
        self.shell("am", "start", "-W", "-n", components[-1])

    def tap(self, point):
        self.shell("input", "tap", str(point[0]), str(point[1]))

    def back(self):
        self.shell("input", "keyevent", "4")

    def swipe(self, start, end, duration=350):
        self.shell("input", "swipe", *map(str, (*start, *end, duration)))
