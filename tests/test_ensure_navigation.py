"""ensure() re-plans navigation from observed reality.

Real-device evidence (2026-09-21): Back from the feed page landed on the
Alipay home instead of the forest, and the old hard-coded expectation waited
for a page that Back can never reach from there.
"""

from types import SimpleNamespace

from domain_data import Element, Observation
from workflow.session import Session


def observation(oid, texts=(), *, page):
    elements = [Element(text, bounds, oid) for text, bounds in texts]
    return Observation(oid, 0.0, 1440, 3200, "alipay", elements, page)


class FakeExecutor:
    def __init__(self, stream):
        self._stream = iter(stream)
        self.observer = SimpleNamespace(capture=lambda _reason: next(self._stream))
        self.budget = SimpleNamespace(check=lambda: None)
        self.back_calls = []
        self.tap_calls = []
        self.wait_calls = []

    def wait(self, predicate, timeout, reason):
        # Transient OCR glitches resolve on a refreshed frame; keep capturing
        # until the predicate holds instead of aborting on the first frame.
        self.wait_calls.append(reason)
        while True:
            after = next(self._stream)
            if predicate(after):
                return after

    def back(self, obs, predicate, name, allow_unknown, recover=True):
        after = next(self._stream)
        # The old implementation demanded the target page here, which Back
        # cannot reach from the feed page; any new page must count as progress.
        assert predicate(after), "the observed landing page must satisfy back's postcondition"
        assert not predicate(obs), "staying on the same page must not satisfy back"
        self.back_calls.append((obs.id, predicate, name))
        return after

    def tap(self, obs, element, predicate, name, task, **kwargs):
        after = next(self._stream)
        assert predicate(after), "the scripted result must satisfy the tap postcondition"
        self.tap_calls.append(name)
        return after


def test_ensure_replans_route_when_back_lands_on_an_unexpected_page():
    feed_top = observation("1", page="feed")
    before_back = observation("2", page="feed")
    landed = observation("3", page="alipay")
    home = observation("4", [("蚂蚁森林", (300, 1540, 620, 1640))], page="alipay")
    forest = observation("5", page="forest")
    executor = FakeExecutor([feed_top, before_back, landed, home, forest])
    session = Session(executor, {"package": "alipay"})

    assert session.ensure("forest") is forest
    assert [call[2] for call in executor.back_calls] == ["return"]
    assert executor.tap_calls == ["^蚂蚁森林$"]


def test_ensure_survives_one_unrecognized_entry_frame():
    # Real-device evidence (2026-09-22): OCR read "扫一扫" as "扫一拉", the
    # home classified UNKNOWN, and ensure() aborted on its first frame even
    # though the package already matched.
    glitch = observation("1", [("扫一拉", (90, 180, 240, 240))], page="UNKNOWN")
    home = observation("2", [("蚂蚁森林", (300, 1540, 620, 1640))], page="alipay")
    forest = observation("3", page="forest")
    executor = FakeExecutor([glitch, home, home, forest])
    session = Session(executor, {"package": "alipay"})

    assert session.ensure("forest") is forest
    assert executor.wait_calls == ["recognize"]
    assert executor.tap_calls == ["^蚂蚁森林$"]


def test_ensure_backs_out_of_a_leftover_friend_page():
    # Real-device evidence (2026-09-23): an interrupted run left the screen
    # on 昂宇的蚂蚁森林 with 一键收 exposed, and ensure() aborted on the
    # unrecognized forest_friend origin instead of backing out to the forest.
    entry = observation("1", [("昂宇的蚂蚁森林", (180, 220, 700, 300)),
                              ("一键收", (1050, 2050, 1330, 2160))],
                        page="forest_friend")
    still_friend = observation("2", page="forest_friend")
    forest = observation("3", page="forest")
    executor = FakeExecutor([entry, still_friend, forest])
    session = Session(executor, {"package": "alipay"})

    assert session.ensure("forest") is forest
    assert [call[2] for call in executor.back_calls] == ["return"]
    assert executor.tap_calls == []


def test_ensure_taps_the_summary_page_home_without_backing_out():
    # Device evidence (2026-09-23): with every friend harvested, 找能量 opens
    # the energy summary page instead of the deck; its 返回森林首页 button is
    # the deterministic route home (Back would depend on the stack position
    # an interrupted run left behind).
    summary = observation("1", [("找能量共获得", (500, 400, 940, 470)),
                                ("返回森林首页", (400, 3050, 1040, 3140))],
                          page="forest_summary")
    home = observation("2", page="forest")
    executor = FakeExecutor([summary, summary, home])
    session = Session(executor, {"package": "alipay"})

    assert session.ensure("forest") is home
    assert executor.tap_calls == ["返回森林首页"]
    assert executor.back_calls == []


def test_ensure_backs_out_of_a_leftover_ad_page():
    # Real-device evidence (2026-09-23, run 20260923-105813): a crashed
    # ad-browse left the entry on the market ad page (its guess modal was
    # dismissed first), and ensure() aborted with "No verified navigation
    # from ad to forest" instead of backing out through the lottery detour;
    # Back from the ad is proven by every completed ad run.
    entry = observation("1", [("滑动浏览得抽奖机会", (945, 298, 1306, 345)),
                              ("森林市集", (128, 214, 361, 280))],
                        page="ad")
    # Each Back re-observes its before-frame first, then lands one step up:
    # ad -> lottery -> treasure -> forest.
    ad_again = observation("2", page="ad")
    lottery = observation("3", page="lottery")
    lottery_again = observation("4", page="lottery")
    treasure = observation("5", page="treasure")
    treasure_again = observation("6", page="treasure")
    forest = observation("7", page="forest")
    executor = FakeExecutor([entry, ad_again, lottery, lottery_again,
                             treasure, treasure_again, forest])
    session = Session(executor, {"package": "alipay"})

    assert session.ensure("forest") is forest
    assert [call[2] for call in executor.back_calls] == ["return"] * 3
    assert executor.tap_calls == []


def test_family_route_ignores_the_encouragement_card_phrase():
    # Real-device evidence (2026-09-24, run c47f25): a transient
    # "暂不符合领奖条件" card rendered 快攒亲密度昨天18:53 above the bottom
    # 三即签到 button, so the unanchored 攒亲密度 alternative double-matched
    # and the route aborted as AMBIGUOUS. The button keeps its loose
    # [立三主]即签到 anchor; the 攒亲密度 alternative is full-string only.
    family = observation("1", [("快攒亲密度昨天18:53", (297, 2745, 756, 2804)),
                               ("三即签到", (599, 2951, 848, 3012))],
                         page="family")
    tasks = observation("2", page="family_tasks")
    executor = FakeExecutor([family, family, tasks])
    session = Session(executor, {"package": "alipay"})

    assert session.ensure("family_tasks") is tasks
    assert executor.tap_calls == ["[立三主]即签到|^攒亲密度$"]
