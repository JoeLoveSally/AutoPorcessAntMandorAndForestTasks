from __future__ import annotations

import json
import math
import queue
import threading
import time
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from device_bridge.realtime import AdbScreenrecordFrameStream, PersistentAdbTouch
from logger import RunLogger
from runtime.config import Config


@dataclass(slots=True)
class Track:
    id: int
    x: float
    y: float
    last_seen: float
    previous_y: float | None = None
    previous_x: float | None = None
    previous_seen: float | None = None
    tapped_at: float | None = None
    confirmed: bool = False
    missed_frames_after_tap: int = 0
    retired: bool = False

    def update(self, x: float, y: float, now: float) -> None:
        self.previous_x = self.x
        self.previous_y = self.y
        self.previous_seen = self.last_seen
        self.x = x
        self.y = y
        self.last_seen = now

    def predicted(self, latency_seconds: float, height: int) -> tuple[int, int]:
        velocity_x = 0.0
        velocity_y = 0.0
        if self.previous_y is not None and self.previous_seen is not None:
            elapsed = self.last_seen - self.previous_seen
            if elapsed > 0:
                velocity_y = max(0.0, (self.y - self.previous_y) / elapsed)
                if self.previous_x is not None:
                    velocity_x = (self.x - self.previous_x) / elapsed
        return (
            round(self.x + velocity_x * latency_seconds),
            min(height - 1, round(self.y + velocity_y * latency_seconds)),
        )


@dataclass(frozen=True, slots=True)
class EnergyRainStats:
    frames: int
    unique_targets: int
    taps: int
    confirmed_hits: int
    hit_rate: float
    elapsed_seconds: float
    average_frame_interval_ms: float


class EnergyRainPlayer:
    def __init__(self, config: Config, logger: RunLogger):
        self.config = config
        self.logger = logger

    def play(
        self,
        device,
        start_point: tuple[int, int] | None = None,
        artifacts_directory: Path | None = None,
        round_name: str = "round",
    ) -> EnergyRainStats:
        started = time.monotonic()
        deadline = started + self.config.realtime.rain_duration_seconds
        tracks: dict[int, Track] = {}
        next_id = 1
        frames = 0
        taps = 0
        frame_times: list[float] = []
        last_targets = started
        diagnostics = artifacts_directory / round_name if artifacts_directory else None
        if diagnostics is not None:
            diagnostics.mkdir(parents=True, exist_ok=True)
        diagnostic_context = (
            _DiagnosticWriter(diagnostics) if diagnostics is not None else nullcontext()
        )
        with (
            AdbScreenrecordFrameStream(
                device.serial,
                device.size(),
                self.config.device.adb_path,
                bit_rate=self.config.realtime.bit_rate,
            ) as stream,
            PersistentAdbTouch(device.serial, self.config.device.adb_path) as touch,
            diagnostic_context as diagnostic_writer,
        ):
            # Start only after the video and touch channels are ready, so the
            # three-second countdown is available for decoder warm-up.
            stream.next_frame(timeout=25)
            if start_point is not None:
                touch.tap(start_point)
            started = time.monotonic()
            deadline = started + self.config.realtime.rain_duration_seconds
            active_after = started + 2.6
            last_targets = active_after
            game_seen = False
            non_game_frames = 0
            while time.monotonic() < deadline:
                frame = stream.next_frame(timeout=3)
                frames += 1
                frame_times.append(frame.captured_at)
                game_frame = frame.captured_at >= active_after and _is_game_frame(frame.image)
                game_seen = game_seen or game_frame
                if game_seen and not game_frame:
                    non_game_frames += 1
                    # The result/gift page can briefly resemble the game. Stop
                    # before its reward text or top-right menu is tapped.
                    if non_game_frames >= 8:
                        break
                elif game_frame:
                    non_game_frames = 0
                detections = _balls(frame.image) if game_frame else []
                if detections:
                    last_targets = frame.captured_at
                # An unclicked object that has not been observed for a short
                # interval has left the board; retaining it lets a later ball
                # inherit stale coordinates and causes duplicate/missed taps.
                for key in list(tracks):
                    track = tracks[key]
                    if track.tapped_at is None and frame.captured_at - track.last_seen > 0.30:
                        del tracks[key]
                unmatched = set(tracks)
                for x, y in detections:
                    unmatched = {key for key in unmatched if not tracks[key].retired}
                    candidate = min(
                        unmatched,
                        key=lambda key: math.dist(
                            tracks[key].predicted(0.0, frame.image.shape[0]), (x, y)
                        ),
                        default=None,
                    )
                    if candidate is not None:
                        track = tracks[candidate]
                        elapsed = max(0.0, frame.captured_at - track.last_seen)
                        speed = 0.0
                        if track.previous_seen is not None and track.previous_x is not None:
                            prior_elapsed = track.last_seen - track.previous_seen
                            if prior_elapsed > 0:
                                speed = math.dist(
                                    (track.x, track.y),
                                    (track.previous_x, track.previous_y or track.y),
                                ) / prior_elapsed
                        base_radius = self.config.realtime.dedup_radius_pixels * frame.image.shape[1] / device.size().width
                        radius = min(base_radius * 2.5, base_radius + speed * elapsed * 1.5)
                        distance = math.dist(track.predicted(0.0, frame.image.shape[0]), (x, y))
                    else:
                        radius = distance = 0.0
                    if candidate is not None and distance <= radius:
                        tracks[candidate].update(x, y, frame.captured_at)
                        unmatched.remove(candidate)
                    else:
                        tracks[next_id] = Track(next_id, x, y, frame.captured_at)
                        next_id += 1
                eligible: list[tuple[int, Track, tuple[int, int]]] = []
                for track in tracks.values():
                    if track.tapped_at is not None:
                        if frame.captured_at - track.tapped_at > 0.45:
                            track.retired = True
                        if track.last_seen < frame.captured_at:
                            track.missed_frames_after_tap += 1
                        else:
                            track.missed_frames_after_tap = 0
                        if (
                            frame.captured_at - track.tapped_at <= 0.45
                            and track.missed_frames_after_tap >= 2
                        ):
                            track.confirmed = True
                        continue
                    if frame.captured_at - track.last_seen > 0.12:
                        continue
                    # A static green decoration can look circular too. Require
                    # the same object to have moved down between two frames
                    # before it is eligible for a tap.
                    if track.previous_y is None or track.y <= track.previous_y + 1:
                        continue
                    local = track.predicted(0.08, frame.image.shape[0])
                    if local[1] >= frame.image.shape[0] * 0.86:
                        continue
                    eligible.append((local[1], track, local))
                # ``input tap`` commands execute serially on Android. Sending
                # every object from one frame builds a stale coordinate queue;
                # send only the two lowest (most urgent) balls, then recompute
                # the rest from the next video frame.
                frame_taps: list[tuple[int, int]] = []
                for _urgency, track, local in sorted(eligible, reverse=True)[:2]:
                    if not _safe_tap_point(local, frame.image.shape[1], frame.image.shape[0]):
                        continue
                    device_point = frame.to_device(local)
                    touch.tap(device_point)
                    self.logger.emit(
                        "energy_rain.tap",
                        frame=frame.sequence,
                        track_id=track.id,
                        local_point=local,
                        device_point=device_point,
                    )
                    track.tapped_at = time.monotonic()
                    taps += 1
                    frame_taps.append(local)
                if diagnostic_writer is not None and (
                    frame.sequence % self.config.realtime.diagnostic_frame_interval == 0
                    or frame_taps
                ):
                    diagnostic_writer.submit(
                        frame.sequence,
                        frame.captured_at,
                        frame.image,
                        detections,
                        frame_taps,
                        game_frame,
                    )
                if game_seen and tracks and time.monotonic() - last_targets > 1.8 and time.monotonic() - started > 10:
                    break
        now = time.monotonic()
        targeted = [track for track in tracks.values() if track.tapped_at is not None]
        hits = sum(track.confirmed for track in targeted)
        hit_rate = hits / len(targeted) if targeted else 0.0
        intervals = [
            later - earlier
            for earlier, later in zip(frame_times, frame_times[1:], strict=False)
        ]
        stats = EnergyRainStats(
            frames,
            len(tracks),
            taps,
            hits,
            hit_rate,
            now - started,
            (sum(intervals) / len(intervals) * 1000) if intervals else 0.0,
        )
        self.logger.emit(
            "energy_rain.round",
            frames=stats.frames,
            unique_targets=stats.unique_targets,
            taps=stats.taps,
            confirmed_hits=stats.confirmed_hits,
            hit_rate=round(stats.hit_rate, 4),
            elapsed_seconds=round(stats.elapsed_seconds, 3),
            average_frame_interval_ms=round(stats.average_frame_interval_ms, 2),
        )
        return stats


def _balls(image: np.ndarray) -> list[tuple[int, int]]:
    height, width = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (35, 75, 85), (90, 255, 255))
    mask[: int(height * 0.08), :] = 0
    mask[int(height * 0.88) :, :] = 0
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    points: list[tuple[int, int]] = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if not width * height * 0.00009 <= area <= width * height * 0.015:
            continue
        (x, y), radius = cv2.minEnclosingCircle(contour)
        if radius <= 0 or area / (math.pi * radius * radius) < 0.38:
            continue
        points.append((round(x), round(y)))
    return sorted(points, key=lambda point: -point[1])


def _is_game_frame(image: np.ndarray) -> bool:
    """Require the blue-sky game board before detecting or tapping targets."""
    height, width = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    board = hsv[int(height * 0.15) : int(height * 0.75), :width]
    if not board.size:
        return False
    blue = cv2.inRange(board, (85, 50, 90), (125, 255, 255))
    return float(np.mean(blue > 0)) >= 0.35


def _safe_tap_point(point: tuple[int, int], width: int, height: int) -> bool:
    """Keep taps away from the persistent three-dot menu in the top-right."""
    x, y = point
    # The menu hit target is wider than the three visible dots. A ball that
    # enters this strip is allowed to fall below it before being tapped.
    return not (x >= width * 0.86 and y <= height * 0.14)


def _save_diagnostic_frame(
    directory: Path,
    sequence: int,
    captured_at: float,
    image: np.ndarray,
    detections: list[tuple[int, int]],
    taps: list[tuple[int, int]],
    game_frame: bool,
) -> None:
    """Persist a bounded replay sample and its exact detection/tap metadata."""
    annotated = image.copy()
    for point in detections:
        cv2.circle(annotated, point, 12, (0, 255, 255), 3)
    for point in taps:
        cv2.drawMarker(
            annotated,
            point,
            (0, 0, 255),
            cv2.MARKER_CROSS,
            34,
            4,
        )
    image_name = f"frame-{sequence:06d}.jpg"
    cv2.imwrite(
        str(directory / image_name),
        annotated,
        (cv2.IMWRITE_JPEG_QUALITY, 82),
    )
    record = {
        "frame": sequence,
        "captured_at": captured_at,
        "game_frame": game_frame,
        "detections": detections,
        "taps": taps,
        "image": image_name,
    }
    with (directory / "frames.jsonl").open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n")


class _DiagnosticWriter:
    """Write replay samples off the real-time detection thread.

    The queue is deliberately bounded: diagnostic evidence may be dropped
    under I/O pressure, but gameplay latency must never increase because the
    disk cannot keep up.
    """

    def __init__(self, directory: Path, capacity: int = 8):
        self.directory = directory
        self.items: queue.Queue[tuple | None] = queue.Queue(maxsize=capacity)
        self.worker = threading.Thread(
            target=self._run,
            name="energy-rain-diagnostics",
            daemon=True,
        )

    def __enter__(self):
        self.worker.start()
        return self

    def __exit__(self, *_exc_info):
        self.items.put(None)
        self.worker.join(timeout=10)

    def submit(
        self,
        sequence: int,
        captured_at: float,
        image: np.ndarray,
        detections: list[tuple[int, int]],
        taps: list[tuple[int, int]],
        game_frame: bool,
    ) -> None:
        item = (
            sequence,
            captured_at,
            image.copy(),
            list(detections),
            list(taps),
            game_frame,
        )
        try:
            self.items.put_nowait(item)
        except queue.Full:
            return

    def _run(self) -> None:
        while True:
            item = self.items.get()
            if item is None:
                return
            try:
                _save_diagnostic_frame(self.directory, *item)
            except Exception:
                # Diagnostics are best-effort and must never abort a round.
                continue
