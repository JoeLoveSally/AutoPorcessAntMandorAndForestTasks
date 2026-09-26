"""Manor browse retry re-checks completion calibrated against device evidence.

Run 19d92f (2026-09-24): the 15s video really completed while browse()
reported TIMER_MISSING (its top-right timer never OCR'd), and the retry
re-rowed the list but tapped the freshly claimable 领取 as if it were the
entry - claiming the feed reward and then timing out waiting for an ad
page. The retry must re-check the row the way the pre-loop check does and
complete instead of tapping again.
"""

from domain_data import AutomationError, Element, Observation
from workflow import shared as shared_workflow
from workflow.manor.daily import Manor


def obs(page, texts=(), oid="fixture"):
    elements = [Element(text, (100, 1900, 900, 1990), oid) for text in texts]
    return Observation(oid, 0.0, 1440, 3200, "alipay", elements, page)


class FakeSession:
    def __init__(self):
        self.task = "manor.feed.video"
        self.config = {"ad_entry_attempts": 2}
        self.obs = None
        self._list = obs("feed", ["看庄园小视频", "和小鸡一起看15s公益小视频"])
        self._buttons = [
            Element("去完成", (1158, 2014, 1301, 2070), "fixture"),
            Element("领取", (1158, 2014, 1301, 2070), "fixture"),
        ]
        self._title = Element("看庄园小视频", (321, 1945, 628, 1998), "fixture")
        self._open = obs("ad", ["看15s视频"])
        self.tap_element_calls = []
        self.back_calls = []
        self.complete_row_calls = []
        self.done_args = []

    def row(self, _pattern, required=True, reset=False, page="feed"):
        return self._list, self._title, self._buttons.pop(0)

    def tap_element(self, _obs, button, predicate, **kwargs):
        self.tap_element_calls.append((button.text, kwargs.get("name")))
        after = self._open
        assert predicate(after), "the scripted ad frame must satisfy browse-open"
        self.obs = after
        return after

    def back(self, pages, **kwargs):
        self.back_calls.append((pages, kwargs))
        self.obs = self._list
        return self.obs

    def complete_row(self, pattern, page="feed", claim=False):
        self.complete_row_calls.append((pattern, page, claim))

    def done(self, _obs, **kwargs):
        self.done_args.append(kwargs)


def test_browse_retry_completes_instead_of_tapping_the_claim_button(
        monkeypatch):
    def raise_timer_missing(_session, _swipe):
        raise AutomationError("timer never OCR'd", "TIMER_MISSING")

    monkeypatch.setattr(shared_workflow, "browse", raise_timer_missing)
    session = FakeSession()

    Manor(session).browse("看庄园小视频")

    # Exactly one entry tap: the retry must stop on the claimable row and
    # complete it - a second call would claim the feed as a side effect.
    assert [call[1] for call in session.tap_element_calls] == ["browse-open"]
    assert len(session.back_calls) == 1
    assert session.back_calls[0][1]["allow_unknown"] is True
    assert len(session.complete_row_calls) == 1
    assert session.complete_row_calls[0][0] == "看庄园小视频"
    assert session.done_args == []


def test_successful_browse_backs_to_feed_despite_the_completion_race(
        monkeypatch):
    # Device evidence (2026-09-25, run f4b926): browse() returns while
    # s.obs still reads the ad frame, but the completion view auto-advances
    # to the unruled 任务已完成 summary before s.back()'s own observation -
    # so an allow_unknown flag computed from s.obs.page would say False and
    # validate() would refuse the fresh UNKNOWN observation. Back must
    # allow unknown unconditionally; the ("feed",) target guards landing.
    def succeed(session, _swipe):
        session.obs = obs("ad", ["浏览完成"])
        return session.obs

    monkeypatch.setattr(shared_workflow, "browse", succeed)
    session = FakeSession()

    Manor(session).browse("看庄园小视频")

    assert session.back_calls == [(("feed",), {"allow_unknown": True})]
    assert session.complete_row_calls == [("看庄园小视频", "feed", False)]
