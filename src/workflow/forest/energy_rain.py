from __future__ import annotations

import math
import time
from dataclasses import dataclass

import cv2
import numpy as np

from device_bridge.realtime import AdbScreenrecordStream, PersistentAdbTouch
from domain_data import AutomationError


@dataclass
class Track:
    id: int
    x: float
    y: float
    last_seen: float
    previous_x: float | None = None
    previous_y: float | None = None
    previous_seen: float | None = None
    tapped_at: float | None = None
    retired: bool = False

    def update(self, x, y, now):
        self.previous_x, self.previous_y, self.previous_seen = self.x, self.y, self.last_seen
        self.x, self.y, self.last_seen = x, y, now

    def predicted(self, latency, height):
        vx = vy = 0.0
        if self.previous_seen is not None and self.previous_y is not None:
            elapsed = self.last_seen - self.previous_seen
            if elapsed > 0:
                vx = (self.x - (self.previous_x if self.previous_x is not None else self.x)) / elapsed
                vy = max(0.0, (self.y - self.previous_y) / elapsed)
        return round(self.x + vx * latency), min(height - 1, round(self.y + vy * latency))


@dataclass(frozen=True)
class RainStats:
    frames: int
    detections: int
    taps: int
    unique_targets: int
    duration: float


def play(session, round_number):
    """Play one round over a continuous video and persistent touch channel."""
    s = session
    obs = s.observe(f"rain-round-{round_number}-before")
    start = obs.one("^[立三主]即开[始启]$")
    s.ex.validate(obs, start)
    config = s.config
    action = None
    started = time.monotonic()
    frames = detections = taps = 0
    tracks = {}
    next_id = 1
    game_seen = False
    non_game_frames = 0
    last_targets = started

    try:
        with (
            AdbScreenrecordStream(
                s.ex.device.serial,
                (obs.width, obs.height),
                s.ex.device.adb,
                config.get("ffmpeg", "ffmpeg"),
                config.get("realtime_width", 720),
                config.get("realtime_bitrate", 8_000_000),
            ) as stream,
            PersistentAdbTouch(s.ex.device.serial, s.ex.device.adb) as touch,
        ):
            stream.read(timeout=config.get("realtime_start_timeout", 12))
            if s.ex.device.foreground() != s.ex.package:
                raise AutomationError("Foreground changed before energy rain", "CONTEXT_CHANGED")
            action = s.ex.store.intent(
                s.task,
                f"rain-round-{round_number}-start",
                obs.id,
                {"round": round_number, "target": start.text},
            )
            s.ex.logger.emit(
                "action.intent", task=s.task, name=f"rain-round-{round_number}-start",
                before=obs.id, point=start.point, irreversible=True,
            )
            touch.tap(start.point)
            s.ex.store.action(action, "SENT")
            started = time.monotonic()
            active_after = started + config.get("rain_countdown_seconds", 2.6)
            deadline = started + config.get("rain_duration_seconds", 22)
            last_targets = active_after

            while time.monotonic() < deadline:
                frame = stream.read(timeout=3)
                frames += 1
                game_frame = frame.captured_at >= active_after and is_game_frame(frame.image)
                game_seen = game_seen or game_frame
                if game_seen and not game_frame:
                    non_game_frames += 1
                    if non_game_frames >= 8:
                        break
                elif game_frame:
                    non_game_frames = 0

                points = energy_balls(frame.image) if game_frame else []
                detections += len(points)
                if points:
                    last_targets = frame.captured_at
                for key in list(tracks):
                    track = tracks[key]
                    if track.tapped_at is None and frame.captured_at - track.last_seen > .30:
                        del tracks[key]

                unmatched = {key for key, track in tracks.items() if not track.retired}
                for x, y in points:
                    candidate = min(
                        unmatched,
                        key=lambda key: math.dist(
                            tracks[key].predicted(0, frame.image.shape[0]), (x, y)
                        ),
                        default=None,
                    )
                    radius = config.get("rain_dedup_radius", 46) * frame.image.shape[1] / obs.width
                    if candidate is not None and math.dist(
                        tracks[candidate].predicted(0, frame.image.shape[0]), (x, y)
                    ) <= radius:
                        tracks[candidate].update(x, y, frame.captured_at)
                        unmatched.remove(candidate)
                    else:
                        tracks[next_id] = Track(next_id, x, y, frame.captured_at)
                        next_id += 1

                eligible = []
                for track in tracks.values():
                    if track.tapped_at is not None:
                        if frame.captured_at - track.tapped_at > .45:
                            track.retired = True
                        continue
                    if frame.captured_at - track.last_seen > .12:
                        continue
                    if track.previous_y is None or track.y <= track.previous_y + 1:
                        continue
                    point = track.predicted(config.get("rain_touch_prediction", .08), frame.image.shape[0])
                    if safe_tap_point(point, frame.image.shape[1], frame.image.shape[0]):
                        eligible.append((point[1], track, point))

                for _urgency, track, point in sorted(eligible, reverse=True)[:2]:
                    device_point = frame.to_device(point)
                    touch.tap(device_point)
                    track.tapped_at = frame.captured_at
                    taps += 1
                    s.ex.logger.emit(
                        "energy_rain.tap", round=round_number, frame=frame.sequence,
                        track=track.id, point=device_point,
                    )

                if game_seen and time.monotonic() - last_targets > 1.8 and time.monotonic() - started > 10:
                    break

        if not game_seen:
            raise AutomationError("Energy rain game frames were not detected", "REALTIME")
        result = s.wait(
            lambda o:o.has("获得|结算|能量雨结束|再来一次|送TA机会"),
            f"rain-round-{round_number}-result", timeout=12,
        )
        s.ex.store.action(action, "VERIFIED", result.id)
    except BaseException:
        if action is not None:
            s.ex.store.action(action, "RESULT_UNKNOWN")
        raise

    stats = RainStats(frames, detections, taps, len(tracks), time.monotonic() - started)
    s.ex.logger.emit(
        "energy_rain.round", round=round_number, frames=stats.frames,
        detections=stats.detections, taps=stats.taps, unique_targets=stats.unique_targets,
        duration=round(stats.duration, 3),
    )
    return result


def energy_balls(image):
    height, width = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (35, 75, 85), (90, 255, 255))
    mask[:int(height * .08)] = 0
    mask[int(height * .88):] = 0
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    result = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if not width * height * .00009 <= area <= width * height * .015:
            continue
        (x, y), radius = cv2.minEnclosingCircle(contour)
        if radius > 0 and area / (math.pi * radius * radius) >= .38:
            result.append((round(x), round(y)))
    return sorted(result, key=lambda point: -point[1])


def is_game_frame(image):
    height, width = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    board = hsv[int(height * .15):int(height * .75), :width]
    if not board.size:
        return False
    blue = cv2.inRange(board, (85, 50, 90), (125, 255, 255))
    return float(np.mean(blue > 0)) >= .35


def safe_tap_point(point, width, height):
    x, y = point
    return y < height * .86 and not (x >= width * .86 and y <= height * .14)
