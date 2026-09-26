"""Ad-browsing cadence: one capture per swipe.

Device evidence (2026-09-23, run 20260923-103757): every capture costs
2.7-4.0s of screenshot+OCR, and the old browse cycle spent three captures
per swipe (fresh frame for the overlay check, fresh before-frame, swipe
result) plus a dead sleep - ~10.6s between swipes. The user's note:
下滑频率太低. browse must feed the swipe's own result frame into the next
dismissal/completion check instead of capturing again.
"""

from types import SimpleNamespace

from domain_data import Element, Observation
from workflow.session import Session
from workflow.shared import browse


def test_browse_feeds_the_swipe_frame_into_the_next_completion_check():
    entered = Observation(
        "entered", 0.0, 1440, 3200, "alipay",
        [Element("滑动浏览得抽奖机会", (300, 2400, 1140, 2500), "entered")],
        page="ad",
    )
    completed = Observation(
        "completed", 4.0, 1440, 3200, "alipay",
        [Element("已完成 可领奖励", (1000, 300, 1400, 380), "completed")],
        page="ad",
    )

    class PacedSession(Session):
        def __init__(self):
            super().__init__(SimpleNamespace(budget=None), {})
            self.observe_calls = 0
            self.scrolls = []
            self._frames = iter((entered, completed))

        def observe(self, _reason="observe"):
            self.observe_calls += 1
            return next(self._frames)

        def scroll(self, *args, **kwargs):
            self.scrolls.append((args, kwargs))
            return next(self._frames)

    session = PacedSession()

    result = browse(session, True)

    assert result is completed
    # One capture in total: the swipe's own frame answers the next
    # overlay/completion check instead of a fresh ~3s capture, which cut the
    # observed 10.6s-per-swipe cycle down to a single stroke plus capture.
    assert session.observe_calls == 1
    (args, kwargs), = session.scrolls
    # The previous frame serves as the swipe's before-frame (swipes skip the
    # element-pixel comparison, only expiry/page/overlay checks).
    assert args == ((.5, .73, .5, .55),)
    assert kwargs["obs"] is entered
