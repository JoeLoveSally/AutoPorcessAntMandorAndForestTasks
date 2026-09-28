from types import SimpleNamespace

import pytest

from domain_data import AutomationError, Element, Observation
from workflow.session import Session


def observation(oid, texts):
    return Observation(
        oid,
        0.0,
        1440,
        3200,
        "alipay",
        [Element(text, (100, 400 + index * 120, 600, 470 + index * 120), oid)
         for index, text in enumerate(texts)],
        page="feed",
    )


class ScanningSession(Session):
    def __init__(self, observations):
        super().__init__(SimpleNamespace(), {"max_scrolls": 8})
        self.observations = list(observations)

    def ensure(self, _page):
        return self.observations.pop(0)

    def observe(self, _reason):
        # row()'s pairing retry re-captures mid-render frames from the same
        # scripted stream.
        return self.observations.pop(0)

    def scroll(self, *_args, **_kwargs):
        return self.observations.pop(0)


def test_optional_row_is_absent_after_two_stable_bottom_observations():
    page = observation("1", ["去蚂蚁森林逛一逛", "领取"])
    same_1 = observation("2", ["去蚂蚁森林逛一逛", "领取"])
    same_2 = observation("3", ["去蚂蚁森林逛一逛", "领取"])
    session = ScanningSession([page, same_1, same_2])

    _, title, button = session.row("不存在的可选任务", required=False)

    assert title is None
    assert button is None


def test_required_row_missing_at_stable_bottom_fails_closed():
    page = observation("1", ["其他任务"])
    same_1 = observation("2", ["其他任务"])
    same_2 = observation("3", ["其他任务"])
    session = ScanningSession([page, same_1, same_2])

    with pytest.raises(AutomationError, match="complete scan"):
        session.row("庄园小课堂")


def test_optional_row_absent_at_the_feed_footer_skips():
    # Device evidence (2026-09-25, run 7a53ce): 去蚂蚁森林逛一逛 was not
    # assigned today, and the list's tail reads 完成任务后会获赠饲料，
    # 超过当天24点未领取会消失哦 (pinned from frame 0032 through the
    # exhausted budget at 0040) while the demo-era end markers never
    # appeared - so the absence could not be confirmed and the optional
    # task failed instead of skipping. The footer renders only once,
    # after the last row, so it must close the scan like its siblings.
    # The mid frames vary frame by frame like the device's OCR jitter,
    # which keeps the stable-view fallback from ending the scan early.
    frames = [observation(str(index), ["饲料任务", f"其他任务{index}"])
              for index in range(1, 8)]
    frames.append(observation("8", ["饲料任务",
                                    "完成任务后会获赠饲料，超过当天24点未领取会消失哦"]))
    frames.append(observation("9", ["饲料任务",
                                    "完成任务后会获赠饲料，超过当天24点未领取会消失哦"]))
    session = ScanningSession(frames)

    _, title, button = session.row("去蚂蚁森林逛一逛", required=False)

    assert title is None
    assert button is None


def test_bottom_clipped_row_is_lifted_before_pairing(monkeypatch):
    # Device evidence (2026-09-25, run e22b56): the sesame row first
    # rendered at y3103 of the 3200px screen with its button column past
    # the fold - only the x60g reward chip drew at y3100-3172 - so three
    # no-scroll refreshes never exposed a pill, the column fallback came
    # back synthetic, and complete_row rejected it with "Task completion
    # not verified". A failed pairing on a title inside the bottom fold
    # must lift the list once and pair again on the raised frame.
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    clipped = Observation("1", 0.0, 1440, 3200, "alipay", [
        Element("饲料任务", (585, 1012, 838, 1079), "1"),
        Element("去芝麻攒粒攻略逛一逛", (324, 3103, 832, 3151), "1"),
        Element("x60g", (1202, 3100, 1351, 3172), "1"),
    ], page="feed")
    lifted = Observation("2", 0.0, 1440, 3200, "alipay", [
        Element("饲料任务", (585, 1012, 838, 1079), "2"),
        Element("去芝麻攒粒攻略逛一逛", (324, 1660, 832, 1708), "2"),
        Element("领取", (1179, 1755, 1282, 1808), "2"),
    ], page="feed")

    class BottomClippedSession(ScanningSession):
        # A re-capture without any screen input replays the same clipped
        # view (the device's refresh retries never moved the list); only
        # an actual scroll lifts the row.
        def observe(self, _reason):
            return clipped

        def scroll(self, *_args, **_kwargs):
            return lifted

    session = BottomClippedSession([clipped])

    _, title, button = session.row("去芝麻攒粒攻略逛一逛")

    assert title.text == "去芝麻攒粒攻略逛一逛"
    assert button.text == "领取"


def test_required_row_missing_at_the_feed_footer_fails_closed():
    frames = [observation(str(index), ["饲料任务", f"其他任务{index}"])
              for index in range(1, 8)]
    frames.append(observation("8", ["饲料任务",
                                    "完成任务后会获赠饲料，超过当天24点未领取会消失哦"]))
    frames.append(observation("9", ["饲料任务",
                                    "完成任务后会获赠饲料，超过当天24点未领取会消失哦"]))
    session = ScanningSession(frames)

    with pytest.raises(AutomationError, match="Required task missing"):
        session.row("庄园小课堂")


def test_lottery_sign_card_resolves_the_exact_sign_button():
    # Real-device evidence (2026-09-23) and demo video 01:08: the forest
    # lottery 每日签到 card's right-side button OCRs as exactly "签到";
    # row() found zero buttons because the label was missing from the
    # TASK_BUTTON whitelist and aborted the friends task before any draw.
    page = Observation("1", 0.0, 1440, 3200, "alipay", [
        Element("每日签到", (180, 2400, 640, 2500), "1"),
        Element("签到", (1150, 2420, 1330, 2520), "1"),
        Element("每天访问，得1次抽奖机会", (300, 2530, 900, 2590), "1"),
    ], page="lottery")
    session = ScanningSession([page])

    _, title, button = session.row("每日签到", page="lottery")

    assert title.text == "每日签到"
    assert button.text == "签到"


def test_signed_state_still_resolves_as_the_row_button():
    # The signed state must resolve as the row button too so a re-visit
    # (left lottery after the right one) skips it instead of failing the
    # whole run on an unresolvable button.
    page = Observation("1", 0.0, 1440, 3200, "alipay", [
        Element("每日签到", (180, 2400, 640, 2500), "1"),
        Element("已签到", (1150, 2420, 1330, 2520), "1"),
    ], page="lottery")
    session = ScanningSession([page])

    _, title, button = session.row("每日签到", page="lottery")

    assert title.text == "每日签到"
    assert button.text == "已签到"


def test_row_reobserves_when_the_first_frame_lacks_the_row_button(monkeypatch):
    # Device evidence (2026-09-23): the first frame after the lottery side
    # switch had the market row's title drawn but not its 去逛逛 button -
    # pairing once on that mid-render capture failed the whole friends task
    # before any advertisement ran.
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    mid_render = Observation("1", 0.0, 1440, 3200, "alipay", [
        Element("去森林市集逛一逛(0/2)", (339, 2419, 930, 2482), "1"),
        Element("浏览市集15s，可得1次机会", (329, 2509, 869, 2559), "1"),
    ], page="lottery")
    rendered = Observation("2", 0.0, 1440, 3200, "alipay", [
        Element("去森林市集逛一逛(0/2)", (339, 2419, 930, 2482), "2"),
        Element("浏览市集15s，可得1次机会", (329, 2509, 869, 2559), "2"),
        Element("去逛逛", (1150, 2440, 1290, 2500), "2"),
    ], page="lottery")
    session = ScanningSession([mid_render, rendered])

    _, title, button = session.row("去杂货铺逛一逛|去森林市集逛一逛",
                                   page="lottery")

    assert title.text == "去森林市集逛一逛(0/2)"
    assert button.text == "去逛逛"


def test_row_falls_back_to_the_button_column_when_ocr_misses_the_pill(
        monkeypatch):
    # Device evidence (2026-09-23): the market row's 去逛逛 pill was visible
    # in every captured frame yet OCR never returned it (its identical twins
    # on the rows below were read fine), so a zero-button pairing after the
    # refresh retries must still resolve to the right-aligned button column
    # those twins pin down instead of failing the whole task.
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    frames = [Observation(str(index), 0.0, 1440, 3200, "alipay", [
        Element("去森林市集逛一逛(0/2)", (339, 2419, 930, 2482), str(index)),
        Element("浏览市集15s，可得1次机会", (329, 2509, 869, 2559), str(index)),
    ], page="lottery") for index in range(1, 5)]
    session = ScanningSession(frames)

    obs, title, button = session.row("去杂货铺逛一逛|去森林市集逛一逛",
                                     page="lottery")

    assert title.text == "去森林市集逛一逛(0/2)"
    assert button.observation == obs.id
    x, y = button.point
    assert 1108 <= x <= 1353
    assert y == 2485  # the title's center plus the +35 offset of both twins


def test_optional_row_absent_when_the_scroll_budget_expires():
    # Device evidence (2026-09-28, run 77dae5): the farm drawer's rotating
    # campaign banner rewrites the frame signature on every capture, so
    # no_progress never reaches 2, no footer ever renders, and the scroll
    # budget dies on the loop head - the row is absent just as surely as
    # the footer and stable-view paths say, and an optional row must skip
    # instead of raising on the third confirmation path.
    frames = [observation(str(index), ["饲料任务", f"其他任务{index % 2}"])
              for index in range(1, 12)]
    session = ScanningSession(frames)

    _, title, button = session.row("不存在的可选任务", required=False)

    assert title is None
    assert button is None


def test_required_row_missing_when_the_scroll_budget_expires_fails_closed():
    # The same budget death must stay fail-closed for a required row: an
    # oscillating view is not proof that a task exists elsewhere.
    frames = [observation(str(index), ["饲料任务", f"其他任务{index % 2}"])
              for index in range(1, 12)]
    session = ScanningSession(frames)

    with pytest.raises(AutomationError, match="Cannot confirm complete scan"):
        session.row("庄园小课堂")
