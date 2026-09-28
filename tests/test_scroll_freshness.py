"""Session.scroll() before-frame reuse: fresh frames skip the capture.

Device cadence (2026-09-28): a fresh capture costs ~3-4s of screenshot+OCR
and the daily chain spends 157 before-scroll captures (~403s). A caller's
current frame is valid as the swipe's before-frame while it is inside the
freshness window; an expired frame must be recaptured instead of letting
validate() reject the swipe mid-action.
"""
import time
from types import SimpleNamespace

from domain_data import Observation
from workflow.session import Session


def observation(oid, age=0.0):
    return Observation(oid, time.monotonic() - age, 1440, 3200, "alipay",
                       [], page="feed")


class RecordingExecutor:
    def __init__(self, captures):
        self.captures = iter(captures)
        self.capture_reasons = []
        self.swipes = []
        self.interruption_handler = None
        self.observer = SimpleNamespace(capture=self._capture)
        self.budget = SimpleNamespace(check=lambda: None)

    def _capture(self, reason):
        self.capture_reasons.append(reason)
        return next(self.captures)

    def swipe(self, obs, region, target, *, allow_unknown=False):
        self.swipes.append(obs)
        return obs


def test_fresh_caller_frame_is_reused_without_a_capture():
    executor = RecordingExecutor([observation("new")])
    flow = Session(executor, {})

    returned = flow.scroll(obs=observation("fresh", age=2.0))

    assert executor.capture_reasons == []
    assert executor.swipes[0].id == "fresh"
    assert returned.id == "fresh"


def test_expired_caller_frame_is_recaptured_before_the_swipe():
    executor = RecordingExecutor([observation("new")])
    flow = Session(executor, {})

    returned = flow.scroll(obs=observation("stale", age=30.0))

    assert executor.capture_reasons == ["before-scroll"]
    assert executor.swipes[0].id == "new"
    assert returned.id == "new"


def test_missing_frame_still_captures_the_before_frame():
    executor = RecordingExecutor([observation("new")])
    flow = Session(executor, {})

    returned = flow.scroll()

    assert executor.capture_reasons == ["before-scroll"]
    assert executor.swipes[0].id == "new"
    assert returned.id == "new"
