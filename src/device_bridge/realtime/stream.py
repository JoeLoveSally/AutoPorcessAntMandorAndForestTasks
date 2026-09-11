from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass

import av
import numpy as np

from domain_data import AutomationError


@dataclass(frozen=True)
class Frame:
    image: np.ndarray
    captured_at: float
    sequence: int


class AdbScreenrecordStream:
    """Decode an Android H264 screenrecord stream without a display window."""
    def __init__(self, serial, adb="adb", size="720x1600", bitrate="8M"):
        self.command = [adb, "-s", serial, "exec-out", "screenrecord",
                        "--output-format=h264", "--size=" + size, "--bit-rate=" + bitrate,
                        "--time-limit=60", "-"]
        self.process = None
        self.container = None
        self.sequence = 0

    def __enter__(self):
        try:
            self.process = subprocess.Popen(self.command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.container = av.open(self.process.stdout, format="h264", options={"fflags": "nobuffer"})
        except Exception as exc:
            self.close()
            raise AutomationError(f"Realtime stream unavailable: {exc}", "REALTIME") from exc
        return self

    def read(self, timeout=3):
        if not self.container:
            raise AutomationError("Realtime stream is closed", "REALTIME")
        started = time.monotonic()
        while time.monotonic() - started < timeout:
            try:
                packet = next(self.container.demux(video=0))
                for frame in packet.decode():
                    self.sequence += 1
                    return Frame(frame.to_ndarray(format="bgr24"), time.monotonic(), self.sequence)
            except (StopIteration, av.error.EOFError):
                break
        error = self.process.stderr.read().decode(errors="replace") if self.process and self.process.stderr else ""
        raise AutomationError(error or "Realtime stream frame timeout", "REALTIME")

    def close(self):
        if self.container:
            self.container.close()
            self.container = None
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None

    def __exit__(self, *_args):
        self.close()
