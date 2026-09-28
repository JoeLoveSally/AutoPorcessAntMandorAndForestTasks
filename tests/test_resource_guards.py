from types import SimpleNamespace

import pytest

from domain_data import AutomationError, Element, Observation
from workflow.forest.daily import PLAZA_ENTRY, PLAZA_SCROLL, RAIN_ENTRY, WATER_DIALOG, Forest
from workflow.manor.daily import Manor


def observation(oid, texts, page):
    return Observation(
        oid, 0.0, 1440, 3200, "alipay",
        [Element(text, (100, 400 + index * 100, 500, 470 + index * 100), oid)
         for index, text in enumerate(texts)],
        page=page,
    )


class CompletedParentSession:
    def __init__(self, title):
        self.obs = observation("done", [title, "领取"], "feed")
        self.done_calls = []

    def row(self, *_args, **_kwargs):
        return self.obs, self.obs.elements[0], self.obs.elements[1]

    def done(self, obs, **kwargs):
        self.done_calls.append((obs.id, kwargs))


@pytest.mark.parametrize("method,title", [("farm", "芭芭农场"), ("kitchen", "小鸡厨房")])
def test_completed_resource_task_is_idempotent(method, title):
    session = CompletedParentSession(title)

    getattr(Manor(session), method)()

    assert session.done_calls == [("done", {"already": True})]


class WaterGuardSession:
    def __init__(self):
        # Plaza card elements sit at their real label-row geometry
        # (PLAZA_ENTRY), not the generic test helper's arbitrary column.
        self.home = Observation(
            "forest", 0.0, 1440, 3200, "alipay",
            [Element("真爱合种", (617, 2629, 782, 2674), "forest")],
            page="forest",
        )
        self.love = observation("love", ["为爱攒能量"], "love")
        self.task = "forest.love"
        self.ex = SimpleNamespace(
            store=SimpleNamespace(
                unresolved=lambda _task: [],
                verified_status=lambda _task: "SUCCESS",
            )
        )
        self.taps = []

    def ensure(self, _page):
        return self.home

    def tap(self, pattern, predicate, **_kwargs):
        self.taps.append(pattern)
        assert predicate(self.love)
        return self.love

    def observe(self, _reason):
        return self.love


def test_previous_verified_water_blocks_repeat_when_live_progress_is_unclear():
    session = WaterGuardSession()

    with pytest.raises(AutomationError) as raised:
        Forest(session).water(True)

    assert raised.value.code == "RESULT_UNKNOWN"
    assert session.taps == ["^真爱合种$"]


def test_love_water_completion_matches_real_page_copy():
    session = SimpleNamespace(config={})
    obs = observation("love", ["已为爱攒100g能量"], "love")

    assert Forest(session)._water_completed(obs, True, 100)


def test_cooperate_water_completion_requires_owner_and_today_evidence():
    session = SimpleNamespace(config={"forest_owner": "健桥"})
    forest = Forest(session)
    current = observation("current", ["健桥浇了520g水，为绿水青山做贡献", "2分钟前"], "cooperate")
    old = observation("old", ["健桥浇了520g水，为绿水青山做贡献", "昨天22:57"], "cooperate")
    other = observation("other", ["巨帅浇了520g水", "2分钟前"], "cooperate")

    assert forest._water_completed(current, False, 520)
    assert not forest._water_completed(old, False, 520)
    assert not forest._water_completed(other, False, 520)


def test_cooperate_completion_ignores_freshness_outside_the_feed_row():
    # Device evidence (2026-09-24, run 091908): feed "健桥浇了520g水" with
    # its own timestamp "昨天12:19" while the fixed "今日排行）" header
    # satisfied the old frame-wide freshness check - an unwatered day
    # recorded ALREADY_DONE. Freshness must come from the feed's own row.
    shared = [
        Element("今日排行）", (19, 574, 207, 622), "page"),
        Element("健桥浇了520g水，离胡杨又近一步啦", (102, 2664, 822, 2711), "page"),
    ]
    stale = Observation("page", 0.0, 1440, 3200, "alipay",
                        shared + [Element("昨天12:19", (893, 2666, 1046, 2709), "page")],
                        page="cooperate")
    fresh = Observation("page", 0.0, 1440, 3200, "alipay",
                        shared + [Element("刚刚", (893, 2666, 1046, 2709), "page")],
                        page="cooperate")
    forest = Forest(SimpleNamespace(config={"forest_owner": "健桥"}))

    assert not forest._water_completed(stale, False, 520)
    assert forest._water_completed(fresh, False, 520)


def test_love_water_submit_accepts_the_returned_page_with_total_rise():
    # Device evidence (2026-09-23, run 121403): the submit closed the
    # confirm panel and raised the team total 42700g -> 42800g with no
    # reward popup and no success toast, so the returned page itself must
    # count - with the total rise as the ground truth of the spend.
    forest = Forest(SimpleNamespace(config={}))
    returned = observation("returned", ["为爱攒能量", "攒能量明细", "42800g"], "love")

    assert forest._water_submitted(returned, True, 100, 42700)


def test_love_water_submit_rejects_open_panel_or_unmoved_total():
    forest = Forest(SimpleNamespace(config={}))
    # Total already reads high but the balance line proves the panel is
    # still open; and a closed panel over an unmoved total proves nothing.
    panel_open = observation("open", ["为爱攒能量", "你当前有 22789 g", "42800g"], "love")
    unchanged = observation("unchanged", ["为爱攒能量", "42700g"], "love")

    assert not forest._water_submitted(panel_open, True, 100, 42700)
    assert not forest._water_submitted(unchanged, True, 100, 42700)
    # The cooperate submit keeps its owner-feed evidence instead.
    assert not forest._water_submitted(unchanged, False, 520, 42700)


def test_water_base_reads_the_team_total_and_tolerates_ocr_variants():
    forest = Forest(SimpleNamespace(config={}))
    frame = observation("panel", ["你当前有 22789 g", "100g", "42700g)"], "love")

    # The prefixed balance line never matches; the parenthesis does.
    assert forest._g_values(frame) == [100, 42700]


def test_water_quantity_band_excludes_the_calendar_day_numbers():
    # Device evidence (2026-09-24, run 085605): with the panel open the
    # love page's calendar day "12" (center y=.909) matched the old .95
    # region next to the quantity "20" (y=.549) and the task died as
    # ambiguous; a calendar "30" could likewise fake the "+" tap's
    # next-value check while the quantity never moved.
    frame = Observation(
        "panel", 0.0, 1440, 3200, "alipay",
        [Element("20", (700, 1730, 750, 1785), "panel"),   # quantity, y=.549
         Element("12", (1040, 2870, 1140, 2950), "panel"),  # calendar, y=.909
         Element("30", (500, 2870, 600, 2950), "panel"),    # calendar, y=.909
        ],
        page="love",
    )

    # The old band matched all three; the capped band keeps only the panel.
    assert len(frame.find(r"^\d+\s*(?:g|克)?$", (.15, .4, .85, .95))) == 3
    assert [q.text for q in frame.find(r"^\d+\s*(?:g|克)?$", WATER_DIALOG)] == ["20"]
    assert not frame.has(r"^30\s*(?:g|克)?$", WATER_DIALOG)


def test_cooperate_entry_drags_the_plaza_card_row_not_the_icon_row():
    # Device evidence (2026-09-24, run 090814): the old .67 band hit the
    # fixed 乐园/背包/领奖励 icon row and five drags moved nothing, while
    # the 合种 card sits clipped behind 真爱合种 in the 森林广场 card row
    # at y=.81.
    class Stop(Exception):
        pass

    class PlazaSession:
        def __init__(self):
            self.scrolls = []
            self.tapped = None

        def ensure(self, _page):
            return observation("home", ["森林广场", "能量雨", "真爱合种"], "forest")

        def scroll(self, path, **_kwargs):
            self.scrolls.append(path)
            # The drag reveals the 合种 card: its label lands in the real
            # PLAZA_ENTRY band, its art badge sits above it.
            return Observation(
                "revealed", 0.0, 1440, 3200, "alipay",
                [Element("合种", (882, 2569, 959, 2604), "revealed"),
                 Element("真爱合种", (617, 2629, 782, 2674), "revealed"),
                 Element("合种", (917, 2625, 1006, 2679), "revealed")],
                page="forest",
            )

        def tap(self, pattern, _predicate, **_kwargs):
            self.tapped = pattern
            raise Stop

    session = PlazaSession()

    with pytest.raises(Stop):
        Forest(session).water(False)

    assert session.scrolls == [PLAZA_SCROLL]
    assert session.tapped == "^合种$"


def test_cooperate_entry_taps_the_card_label_not_the_art_badge():
    # Device evidence (2026-09-25, run d04112): the 合种 card repeats its
    # name as a mini-badge on the art (合种 [882,2569], y=.808) directly
    # above its own label ([917,2625], y=.829), so ^合种$ matched twice
    # over the SAME card and the entry tap died "found 2". The entry band
    # keeps the label row only; the scroll stop must wait for the label,
    # not the badge.
    frame = Observation(
        "home", 0.0, 1440, 3200, "alipay",
        [Element("合种", (882, 2569, 959, 2604), "home"),        # art badge
         Element("真爱合种", (617, 2629, 782, 2674), "home"),
         Element("合种", (917, 2625, 1006, 2679), "home"),       # card label
        ],
        page="forest",
    )

    assert len(frame.find("^合种$", PLAZA_ENTRY)) == 1

    class Stop(Exception):
        pass

    class EntrySession:
        def __init__(self):
            self.tapped = None

        def ensure(self, _page):
            return frame

        def tap(self, pattern, _predicate, **kwargs):
            self.tapped = (pattern, kwargs.get("region"))
            raise Stop

    session = EntrySession()

    with pytest.raises(Stop):
        Forest(session).water(False)

    assert session.tapped == ("^合种$", PLAZA_ENTRY)


def test_rain_entry_accepts_the_short_energy_rain_card_label():
    # Device evidence (2026-09-24, run 092325): the plaza card label reads
    # "能量雨" (spec line 103 calls the entry 天天能量雨), so the old
    # anchored pattern found 0 after five drags of the correct band.
    class Stop(Exception):
        pass

    class RainSession:
        def __init__(self):
            self.tapped = None

        def ensure(self, _page):
            return observation("home", ["能量雨", "真爱合种"], "forest")

        def tap(self, pattern, _predicate, **_kwargs):
            self.tapped = pattern
            raise Stop

    session = RainSession()

    with pytest.raises(Stop):
        Forest(session).rain()

    assert session.tapped == RAIN_ENTRY


def test_confirm_tap_picks_the_dialog_button_over_the_page_button():
    # Device evidence (2026-09-24, run 093245): with the confirm dialog
    # open both the dialog's 浇水 (0.691,0.621) and the uncovered page's
    # bottom-right 浇水 (0.865,0.969) fullmatch ^浇水$, so the old
    # (0,.6,1,1) region raised "found 2". The dialog band keeps the dialog
    # button and still covers the love confirm 攒能量, whose center
    # (0.499,0.667) was measured on run 085605.
    frame = Observation(
        "dialog", 0.0, 1440, 3200, "alipay",
        [Element("浇水", (924, 1948, 1065, 2024), "dialog"),
         Element("浇水", (1174, 3062, 1317, 3141), "dialog"),
         Element("520", (634, 1685, 747, 1751), "dialog"),
         Element("攒能量", (668, 2110, 768, 2158), "dialog")],
        page="cooperate",
    )

    assert len(frame.find(r"^浇水$", WATER_DIALOG)) == 1
    assert len(frame.find(r"^浇水$", (0, .6, 1, 1))) == 2   # the old band's clash
    assert frame.has(r"^攒能量$", WATER_DIALOG)              # love path stays covered


def test_cooperate_water_submit_accepts_the_total_rise():
    # Device evidence (2026-09-24, run 9002e4): the feed is a two-row
    # cycling ticker whose new owner row never appeared during the wait
    # (all visible stamps were 昨天/09-xx) and the toast reads +520g, not
    # 成功...520g - only the team total 101870 -> 102390 (+520) proves the
    # spend. The dialog's 暂不 marks it still open, so it fails closed.
    forest = Forest(SimpleNamespace(config={}))
    returned = observation("returned", ["今日排行", "520g", "102390g"], "cooperate")
    open_dialog = observation("open", ["暂不", "浇水", "102390g"], "cooperate")
    unchanged = observation("short", ["今日排行", "520g", "101870g"], "cooperate")

    assert forest._water_submitted(returned, False, 520, 101870)
    assert not forest._water_submitted(open_dialog, False, 520, 101870)
    assert not forest._water_submitted(unchanged, False, 520, 101870)
