from __future__ import annotations

import re
import struct
import subprocess
import time

import cv2
import numpy as np

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

    def frame(self):
        """Screen pixels as a BGR array.

        Device cadence (2026-09-28): exec-out screencap -p spends ~2.1s
        per capture, of which ~0.5s is the device-side PNG encode. The raw
        stream (16-byte width/height/format/bpp header + RGBA payload,
        measured 1440x3200) skips the encode at 1.6s and decodes to the
        same pixels - against the PNG path it differed by mean 0.47,
        below the 0.57 drift of two raw captures of the moving page. An
        unexpected header or format falls back to the PNG path.
        """
        data = self.run("exec-out", "screencap")
        if len(data) >= 16:
            width, height, fmt, _bpp = struct.unpack("<4i", data[:16])
            if (fmt == 1 and width > 0 and height > 0
                    and len(data) == 16 + width * height * 4):
                rgba = np.frombuffer(data, np.uint8, offset=16).reshape(height, width, 4)
                return cv2.cvtColor(rgba, cv2.COLOR_RGBA2BGR)
        image = cv2.imdecode(np.frombuffer(self.screenshot(), np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise AutomationError("Cannot decode screenshot", "DEVICE")
        return image

    def metrics_summary(self):
        """Aggregate per-command ADB timings collected by run()."""
        totals = {}
        for args, seconds in self.metrics:
            parts = list(args[:2])
            if len(parts) > 1:
                parts[1] = parts[1].split(" ")[0]
            entry = totals.setdefault(" ".join(parts),
                                      {"count": 0, "total": 0.0, "max": 0.0})
            entry["count"] += 1
            entry["total"] = round(entry["total"] + seconds, 2)
            entry["max"] = round(max(entry["max"], seconds), 2)
        return totals

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
