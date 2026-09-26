from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from queue import Empty, Full, Queue
from threading import Event, Thread

import numpy as np

from domain_data import AutomationError


@dataclass(frozen=True)
class Frame:
    image: np.ndarray
    captured_at: float
    sequence: int
    device_size: tuple[int, int]

    def to_device(self, point: tuple[int, int]) -> tuple[int, int]:
        height, width = self.image.shape[:2]
        device_width, device_height = self.device_size
        return (
            round(point[0] * device_width / width),
            round(point[1] * device_height / height),
        )


class PersistentAdbTouch:
    """Keep one adb shell alive so taps do not pay process startup latency."""

    def __init__(self, serial: str, adb: str = "adb"):
        self.serial, self.adb = serial, adb
        self.process = None

    def __enter__(self):
        try:
            self.process = subprocess.Popen(
                [self.adb, "-s", self.serial, "shell"],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            raise AutomationError(f"Realtime touch unavailable: {exc}", "REALTIME") from exc
        return self

    def tap(self, point: tuple[int, int]):
        if not self.process or not self.process.stdin or self.process.poll() is not None:
            raise AutomationError("Realtime touch channel stopped", "REALTIME")
        try:
            self.process.stdin.write(f"input tap {point[0]} {point[1]}\n".encode())
            self.process.stdin.flush()
        except OSError as exc:
            raise AutomationError(f"Realtime touch failed: {exc}", "REALTIME") from exc

    def close(self):
        if not self.process:
            return
        if self.process.stdin:
            try:
                self.process.stdin.write(b"exit\n")
                self.process.stdin.flush()
            except OSError:
                pass
        try:
            self.process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        self.process = None

    def __exit__(self, *_args):
        self.close()


class AdbScreenrecordStream:
    """Decode Android's H.264 screenrecord output without per-frame ADB calls."""

    def __init__(self, serial: str, device_size: tuple[int, int], adb: str = "adb",
                 ffmpeg: str = "ffmpeg", decode_width: int = 720, bitrate: int = 8_000_000):
        self.serial, self.device_size = serial, device_size
        self.adb, self.ffmpeg = adb, ffmpeg
        device_width, device_height = device_size
        self.decode_width = min(decode_width, device_width)
        self.decode_height = round(device_height * self.decode_width / device_width / 2) * 2
        self.bitrate = bitrate
        self.recorder = self.decoder = None
        self.worker = None
        self.stop_event = Event()
        self.frames = Queue(maxsize=2)
        self.error = None

    def __enter__(self):
        try:
            self.recorder = subprocess.Popen(
                [
                    self.adb, "-s", self.serial, "exec-out", "screenrecord",
                    "--output-format=h264",
                    f"--size={self.decode_width}x{self.decode_height}",
                    f"--bit-rate={self.bitrate}", "--time-limit=60", "-",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self.decoder = subprocess.Popen(
                [
                    self.ffmpeg, "-loglevel", "error", "-f", "h264",
                    "-flags", "low_delay", "-i", "pipe:0", "-pix_fmt", "bgr24",
                    "-f", "rawvideo", "pipe:1",
                ],
                stdin=self.recorder.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            self.close()
            raise AutomationError(f"Realtime stream unavailable: {exc}", "REALTIME") from exc
        self.worker = Thread(target=self._read_frames, name="energy-rain-frames", daemon=True)
        self.worker.start()
        return self

    def read(self, timeout=3):
        if self.error:
            raise AutomationError(self.error, "REALTIME")
        try:
            return self.frames.get(timeout=timeout)
        except Empty as exc:
            raise AutomationError(self._process_error() or "Realtime frame timeout", "REALTIME") from exc

    def _read_frames(self):
        if not self.decoder or not self.decoder.stdout:
            self.error = "Realtime decoder was not started"
            return
        frame_size = self.decode_width * self.decode_height * 3
        sequence = 0
        try:
            while not self.stop_event.is_set():
                content = _read_exact(self.decoder.stdout, frame_size)
                if len(content) != frame_size:
                    break
                sequence += 1
                image = np.frombuffer(content, dtype=np.uint8).reshape(
                    self.decode_height, self.decode_width, 3
                ).copy()
                frame = Frame(image, time.monotonic(), sequence, self.device_size)
                try:
                    self.frames.put_nowait(frame)
                except Full:
                    try:
                        self.frames.get_nowait()
                    except Empty:
                        pass
                    self.frames.put_nowait(frame)
        except (OSError, ValueError) as exc:
            self.error = f"Realtime frame reader failed: {exc}"

    def _process_error(self):
        for process in (self.recorder, self.decoder):
            if process and process.poll() is not None and process.stderr:
                detail = process.stderr.read().decode(errors="replace").strip()
                if detail:
                    return detail
        return None

    def close(self):
        self.stop_event.set()
        for process in (self.recorder, self.decoder):
            if process and process.poll() is None:
                process.terminate()
        for process in (self.recorder, self.decoder):
            if not process:
                continue
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        if self.worker:
            self.worker.join(timeout=2)
        self.recorder = self.decoder = self.worker = None

    def __exit__(self, *_args):
        self.close()


def _read_exact(stream, size):
    chunks = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
