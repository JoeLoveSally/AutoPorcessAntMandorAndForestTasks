"""Stale targets are re-acquired instead of failing the task.

Device evidence (2026-09-23): OCR grouped the summary page's animated
chevron into 去抽奖>, the pixel guard saw the button change between capture
and tap, and the pattern tap - unlike tap_element - had no stale retry.

Device evidence (2026-09-24, run 081743): the retry alone was not enough -
the lottery result view's 做任务继续抽 CTA animates (crop diff 39.3 against
the guard's 28 threshold), so the guard failed on the re-found frame too
and the second STALE propagated out of the retry. After a fresh OCR
re-find has verified text and position, the pixel diff is redundant and
the retries skip it.
"""

import time
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from action_executor import Executor
from domain_data import AutomationError, Element, Observation
from workflow.session import Session


def observation(oid, texts, *, page):
    elements = [Element(text, bounds, oid) for text, bounds in texts]
    return Observation(oid, 0.0, 1440, 3200, "alipay", elements, page)


class TappingExecutor:
    def __init__(self, captures, taps):
        self._captures = iter(captures)
        self.observer = SimpleNamespace(capture=lambda _reason: next(self._captures))
        self.budget = SimpleNamespace(check=lambda: None)
        self._taps = iter(taps)
        self.tap_calls = []
        self.tap_kwargs = []

    def tap(self, obs, element, predicate, name, task, **kwargs):
        self.tap_calls.append((obs.id, element.text))
        self.tap_kwargs.append(kwargs)
        result = next(self._taps)
        if isinstance(result, Exception):
            raise result
        return result


def test_pattern_tap_reacquires_a_stale_target():
    stale = observation("1", [("去抽奖>", (1060, 1230, 1340, 1310))],
                        page="forest_summary")
    fresh = observation("2", [("去抽奖>", (1075, 1240, 1345, 1318))],
                        page="forest_summary")
    landed = observation("3", [("每日签到", (100, 2400, 400, 2470))],
                         page="lottery")
    executor = TappingExecutor(
        captures=[stale, fresh],
        taps=[AutomationError("Target changed since observation", "STALE"),
              landed],
    )
    session = Session(executor, {"package": "alipay"})

    result = session.tap("^去抽奖>?$", lambda o: o.page == "lottery")

    assert result is landed
    assert executor.tap_calls == [
        ("1", "去抽奖>"),
        ("2", "去抽奖>"),
    ]
    # The first attempt keeps the pixel guard; only the retry - whose fresh
    # OCR re-find just verified text and position - skips it.
    assert "pixel_guard" not in executor.tap_kwargs[0]
    assert executor.tap_kwargs[1]["pixel_guard"] is False


def test_element_tap_reacquires_a_stale_target_without_the_pixel_guard():
    stale = observation("1", [("去抽奖>", (1060, 1230, 1340, 1310))],
                        page="forest_summary")
    fresh = observation("2", [("去抽奖>", (1075, 1240, 1345, 1318))],
                        page="forest_summary")
    landed = observation("3", [("每日签到", (100, 2400, 400, 2470))],
                         page="lottery")
    executor = TappingExecutor(
        captures=[fresh],
        taps=[AutomationError("Target changed since observation", "STALE"),
              landed],
    )
    session = Session(executor, {"package": "alipay"})

    result = session.tap_element(stale, stale.elements[0],
                                 lambda o: o.page == "lottery", name="去抽奖")

    assert result is landed
    assert executor.tap_kwargs[1]["pixel_guard"] is False


def _guard_executor(png_bytes):
    device = SimpleNamespace(foreground=lambda: "alipay",
                             screenshot=lambda: png_bytes)
    return Executor(device, None, None, None, "alipay",
                    SimpleNamespace(check=lambda: None))


def test_pixel_guard_flags_changed_pixels_and_can_be_skipped_after_refind():
    observed = np.zeros((64, 64, 3), np.uint8)
    observed[10:20, 10:50] = 200   # the CTA box as it was observed
    current = np.zeros((64, 64, 3), np.uint8)   # animated: box differs by 200
    png = cv2.imencode(".png", current)[1].tobytes()
    obs = Observation(
        "obs1", time.monotonic(), 64, 64, "alipay",
        [Element("做任务继续抽", (10, 10, 50, 20), "obs1")],
        page="lottery", image=observed,
    )

    with pytest.raises(AutomationError, match="Target changed since observation"):
        _guard_executor(png).validate(obs, obs.elements[0])

    # The session retries call validate with pixel_guard=False right after
    # their fresh OCR re-find, so an animated CTA survives here.
    _guard_executor(png).validate(obs, obs.elements[0], pixel_guard=False)
