from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from queue import Empty, Full, Queue
from threading import Event, Thread

import numpy as np

from device_bridge.common import Size
from runtime.config import RealtimeConfig
from runtime.errors import DeviceError


@dataclass(frozen=True, slots=True)
class Frame:
    image: np.ndarray
    captured_at: float
    sequence: int
    device_size: Size

    def to_device(self, point: tuple[int, int]) -> tuple[int, int]:
        height, width = self.image.shape[:2]
        return (
            round(point[0] * self.device_size.width / width),
            round(point[1] * self.device_size.height / height),
        )


class PersistentAdbTouch:
    """Keeps one adb shell alive so taps do not pay process startup cost."""

    def __init__(self, serial: str, adb_path: str = "adb"):
        self.serial = serial
        self.adb_path = adb_path
        self._process: subprocess.Popen[bytes] | None = None

    def __enter__(self) -> PersistentAdbTouch:
        self._process = subprocess.Popen(
            [self.adb_path, "-s", self.serial, "shell"],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        return self

    def tap(self, point: tuple[int, int]) -> None:
        if self._process is None or self._process.stdin is None or self._process.poll() is not None:
            raise DeviceError("Persistent adb touch channel is not running")
        self._process.stdin.write(f"input tap {point[0]} {point[1]}\n".encode())
        self._process.stdin.flush()

    def __exit__(self, *_args) -> None:
        if self._process is None:
            return
        if self._process.stdin:
            try:
                self._process.stdin.write(b"exit\n")
                self._process.stdin.flush()
            except OSError:
                pass
        try:
            self._process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self._process.terminate()
            self._process.wait(timeout=2)
        self._process = None


class AdbScreenrecordFrameStream:
    """Decodes Android's unbuffered H.264 screenrecord stream in real time."""

    def __init__(
        self,
        serial: str,
        device_size: Size,
        adb_path: str = "adb",
        ffmpeg_path: str = "ffmpeg",
        decode_width: int = 720,
        bit_rate: int = 8_000_000,
    ):
        self.serial = serial
        self.device_size = device_size
        self.adb_path = adb_path
        self.ffmpeg_path = ffmpeg_path
        self.decode_width = min(decode_width, device_size.width)
        raw_height = device_size.height * self.decode_width / device_size.width
        self.decode_height = int(round(raw_height / 2) * 2)
        self.bit_rate = bit_rate
        self._recorder: subprocess.Popen[bytes] | None = None
        self._ffmpeg: subprocess.Popen[bytes] | None = None
        self._thread: Thread | None = None
        self._stop = Event()
        self._frames: Queue[Frame] = Queue(maxsize=2)
        self._error: str | None = None

    def __enter__(self) -> AdbScreenrecordFrameStream:
        self._recorder = subprocess.Popen(
            [
                self.adb_path,
                "-s", self.serial,
                "exec-out",
                "screenrecord",
                "--output-format=h264",
                f"--size={self.decode_width}x{self.decode_height}",
                f"--bit-rate={self.bit_rate}",
                "--time-limit=60",
                "-",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert self._recorder.stdout is not None
        self._ffmpeg = subprocess.Popen(
            [
                self.ffmpeg_path,
                "-loglevel", "error",
                "-f", "h264",
                "-flags", "low_delay",
                "-i", "pipe:0",
                "-pix_fmt", "bgr24",
                "-f", "rawvideo",
                "pipe:1",
            ],
            stdin=self._recorder.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._thread = Thread(target=self._read_frames, name="adb-frame-reader", daemon=True)
        self._thread.start()
        return self

    def next_frame(self, timeout: float = 3.0) -> Frame:
        if self._error:
            raise DeviceError(self._error)
        try:
            return self._frames.get(timeout=timeout)
        except Empty as exc:
            detail = self._process_error()
            raise DeviceError(detail or "Timed out waiting for Android video frame") from exc

    def _read_frames(self) -> None:
        assert self._ffmpeg is not None and self._ffmpeg.stdout is not None
        size = self.decode_width * self.decode_height * 3
        sequence = 0
        try:
            while not self._stop.is_set():
                content = _read_exact(self._ffmpeg.stdout, size)
                if len(content) != size:
                    break
                sequence += 1
                image = np.frombuffer(content, dtype=np.uint8).reshape(
                    self.decode_height, self.decode_width, 3
                ).copy()
                frame = Frame(image, time.monotonic(), sequence, self.device_size)
                try:
                    self._frames.put_nowait(frame)
                except Full:
                    try:
                        self._frames.get_nowait()
                    except Empty:
                        pass
                    self._frames.put_nowait(frame)
        except Exception as exc:
            self._error = f"Android frame reader failed: {exc}"

    def _process_error(self) -> str | None:
        if self._recorder is not None and self._recorder.poll() is not None and self._recorder.stderr:
            return self._recorder.stderr.read().decode(errors="replace").strip()
        if self._ffmpeg is not None and self._ffmpeg.poll() is not None and self._ffmpeg.stderr:
            return self._ffmpeg.stderr.read().decode(errors="replace").strip()
        return None

    def __exit__(self, *_args) -> None:
        self._stop.set()
        for process in (self._recorder, self._ffmpeg):
            if process is not None and process.poll() is None:
                process.terminate()
        for process in (self._recorder, self._ffmpeg):
            if process is not None:
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
        if self._thread:
            self._thread.join(timeout=2)


class ScrcpyFrameStream:
    """Streams scrcpy's recorder output through FFmpeg without displaying a window."""

    def __init__(
        self,
        serial: str,
        device_size: Size,
        config: RealtimeConfig,
        adb_path: str = "adb",
        ffmpeg_path: str = "ffmpeg",
        decode_width: int = 720,
    ):
        self.serial = serial
        self.device_size = device_size
        self.config = config
        self.adb_path = adb_path
        self.ffmpeg_path = ffmpeg_path
        self.decode_width = min(decode_width, device_size.width)
        raw_height = device_size.height * self.decode_width / device_size.width
        self.decode_height = int(round(raw_height / 2) * 2)
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        self._fifo: Path | None = None
        self._scrcpy: subprocess.Popen[bytes] | None = None
        self._tail: subprocess.Popen[bytes] | None = None
        self._ffmpeg: subprocess.Popen[bytes] | None = None
        self._thread: Thread | None = None
        self._stop = Event()
        self._frames: Queue[Frame] = Queue(maxsize=2)
        self._error: str | None = None

    def __enter__(self) -> ScrcpyFrameStream:
        if shutil.which(self.config.scrcpy_path) is None:
            raise DeviceError(f"scrcpy not found: {self.config.scrcpy_path}")
        if shutil.which(self.ffmpeg_path) is None:
            raise DeviceError(f"FFmpeg not found: {self.ffmpeg_path}")
        self._temporary = tempfile.TemporaryDirectory(prefix="ants-auto-scrcpy-", dir="/tmp")
        self._fifo = Path(self._temporary.name) / "video.mkv"
        self._tail = subprocess.Popen(
            ["tail", "--follow=name", "--retry", "--bytes=+1", str(self._fifo)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        assert self._tail.stdout is not None
        self._ffmpeg = subprocess.Popen(
            [
                self.ffmpeg_path,
                "-loglevel", "error",
                "-fflags", "nobuffer",
                "-flags", "low_delay",
                "-i", "pipe:0",
                "-vf", f"scale={self.decode_width}:{self.decode_height}",
                "-pix_fmt", "bgr24",
                "-f", "rawvideo",
                "pipe:1",
            ],
            stdin=self._tail.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self._thread = Thread(target=self._read_frames, name="scrcpy-frame-reader", daemon=True)
        self._thread.start()
        major = _scrcpy_major(self.config.scrcpy_path)
        command = [
            self.config.scrcpy_path,
            "--verbosity", "error",
            "--serial", self.serial,
            "--no-control",
            "--record", str(self._fifo),
            "--record-format", "mkv",
            "--max-size", str(self.config.max_size),
            "--max-fps", str(self.config.max_fps),
        ]
        if major >= 2:
            command.extend(("--no-window", "--no-audio", "--video-bit-rate", str(self.config.bit_rate)))
        else:
            command.extend(("--no-display", "--bit-rate", str(self.config.bit_rate)))
        environment = os.environ.copy()
        environment["ADB"] = shutil.which(self.adb_path) or self.adb_path
        environment["SCRCPY_SERVER_PATH"] = str(self.config.server_path)
        self._scrcpy = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            env=environment,
        )
        return self

    def next_frame(self, timeout: float = 2.0) -> Frame:
        if self._error:
            raise DeviceError(self._error)
        try:
            return self._frames.get(timeout=timeout)
        except Empty as exc:
            detail = self._process_error()
            raise DeviceError(detail or "Timed out waiting for scrcpy video frame") from exc

    def _read_frames(self) -> None:
        assert self._ffmpeg is not None and self._ffmpeg.stdout is not None
        size = self.decode_width * self.decode_height * 3
        sequence = 0
        try:
            while not self._stop.is_set():
                content = _read_exact(self._ffmpeg.stdout, size)
                if len(content) != size:
                    break
                sequence += 1
                image = np.frombuffer(content, dtype=np.uint8).reshape(
                    self.decode_height, self.decode_width, 3
                ).copy()
                frame = Frame(image, time.monotonic(), sequence, self.device_size)
                try:
                    self._frames.put_nowait(frame)
                except Full:
                    try:
                        self._frames.get_nowait()
                    except Empty:
                        pass
                    self._frames.put_nowait(frame)
        except Exception as exc:
            self._error = f"scrcpy frame reader failed: {exc}"

    def _process_error(self) -> str | None:
        if self._scrcpy is not None and self._scrcpy.poll() is not None and self._scrcpy.stderr:
            return self._scrcpy.stderr.read().decode(errors="replace").strip()
        if self._ffmpeg is not None and self._ffmpeg.poll() is not None and self._ffmpeg.stderr:
            return self._ffmpeg.stderr.read().decode(errors="replace").strip()
        if self._tail is not None and self._tail.poll() is not None:
            return "Video recording tail process stopped unexpectedly"
        return None

    def __exit__(self, *_args) -> None:
        self._stop.set()
        for process in (self._scrcpy, self._tail, self._ffmpeg):
            if process is not None and process.poll() is None:
                process.terminate()
        for process in (self._scrcpy, self._tail, self._ffmpeg):
            if process is not None:
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
        if self._thread:
            self._thread.join(timeout=2)
        if self._temporary:
            self._temporary.cleanup()


def _read_exact(stream, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _scrcpy_major(path: str) -> int:
    try:
        value = subprocess.run([path, "--version"], capture_output=True, timeout=5, check=False)
    except OSError:
        return 0
    match = re.search(r"scrcpy\s+(\d+)", value.stdout.decode(errors="replace"))
    return int(match.group(1)) if match else 0
