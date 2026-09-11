from __future__ import annotations

import time
from dataclasses import dataclass

import cv2
import numpy as np

from domain_data import AutomationError
from screen_perception.vision import energy_balls


@dataclass(frozen=True)
class RainStats:
    frames: int
    detections: int
    taps: int
    duration: float


def play(session, round_number):
    """Play one already-entered round using a bounded ADB frame loop.

    The frame loop is intentionally separate from page automation. If a local
    scrcpy control transport becomes available it can replace this function;
    the state machine and postcondition remain unchanged.
    """
    s = session
    obs = s.observe(f"rain-round-{round_number}-before")
    if not obs.has("立即开始"):
        raise AutomationError("Energy rain start control missing")
    s.tap("立即开始", lambda o:o.page == "rain" or o.page == "UNKNOWN", name="rain-start", spend=True)
    started = time.monotonic()
    deadline = started + 18
    tapped = set()
    frames = detections = 0
    interval = []
    previous = None
    while time.monotonic() < deadline:
        before = time.monotonic()
        png = s.ex.device.screenshot()
        image = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise AutomationError("Energy rain screenshot decode failed", "DEVICE")
        frames += 1
        interval.append(time.monotonic() - before)
        for point in energy_balls(image):
            detections += 1
            # Round-local spatial identity. Objects move, so only suppress a
            # point briefly; a later object at the same location remains tappable.
            key = (point[0] // 42, point[1] // 42)
            now = time.monotonic()
            prior = tapped.get(key)
            if prior and now - prior < .32:
                continue
            s.ex.device.tap(point)
            tapped[key] = now
        latest = s.ex.observer.capture("rain-round-frame")
        if latest.page in ("rain", "forest") and latest.has("获得|结算|本轮|能量雨结束|再来一次"):
            break
        if previous is not None and latest.page == "rain" and latest.has("立即开始"):
            break
        previous = latest.page
        time.sleep(.07)
    else:
        raise AutomationError("Energy rain round did not reach a bounded result", "TIMEOUT")
    result = s.observe(f"rain-round-{round_number}-result")
    if not result.has("获得|结算|能量雨结束|再来一次|送TA机会"):
        raise AutomationError("Energy rain result page not verified", "RESULT_UNKNOWN")
    s.ex.logger.emit("energy_rain.round", round=round_number, frames=frames,
                     detections=detections, taps=len(tapped), duration=time.monotonic()-started,
                     average_frame_interval=sum(interval)/len(interval) if interval else 0)
    return result
