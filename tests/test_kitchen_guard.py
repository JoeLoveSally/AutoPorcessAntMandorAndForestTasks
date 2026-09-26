"""Kitchen cooking guard calibrated against device evidence.

Runs 3496e7 -> 295962 (2026-09-25): with the chickens out the 做美食 tap is
refused behind a ~2s toast (小鸡不在家哦，等它回来) that the runner's ~4s
capture cadence misses, so the gallery postcondition starved and left the
submission RESULT_UNKNOWN - which then blocked every later spend of the
task. The refusal proof lives in the action's own before frame: that frame
records the standing out-state bubble at tap time, so the submission stays
cancellable even after the chickens walk back home. The live out-state
bubble skips the cook (never tap into the refusal), while a submission
whose before frame shows a normal kitchen stays fail-closed behind the
intent guard.
"""

import json
from pathlib import Path
from types import SimpleNamespace

from domain_data import AutomationError, Element, Observation
from workflow.manor import daily as manor_daily
from workflow.manor.daily import Manor


def obs(page, texts, oid="fixture"):
    elements = [Element(text, (100, 400 + 60 * i, 900, 460 + 60 * i), oid)
                for i, text in enumerate(texts)]
    return Observation(oid, 0.0, 1440, 3200, "alipay", elements, page)


class FakeStore:
    def __init__(self, pending=()):
        self.pending = list(pending)
        self.updates = []

    def unresolved(self, task):
        return [(row[0], row[1], None) for row in self.pending]

    def pending_frames(self, task):
        return list(self.pending)

    def action(self, action, state, after=None):
        self.updates.append((action, state, after))
        self.pending = [p for p in self.pending if p[0] != action]


class FakeKitchen:
    def __init__(self, kitchen_frame, pending=()):
        self.task = "manor.feed.kitchen"
        self.ex = SimpleNamespace(
            store=FakeStore(pending),
            observer=SimpleNamespace(directory=Path("/runs/20260925-now")),
        )
        self.feed = obs("feed", ["饲料任务", "小鸡厨房", "去完成"], "feed")
        anchor = Element("小鸡厨房", (60, 3000, 400, 3060), "feed")
        button = Element("去完成", (1150, 3000, 1330, 3060), "feed")
        self.row_value = (self.feed, anchor, button)
        # Claimed today already (runs 697d65/d9fb5d/3496e7): no
        # 领今日食材 left on the main page and the store consumed its
        # 领10g食材, so neither claim tap fires in these fixtures.
        self.child = obs("ingredient_shop",
                         ["献爱心得食材", "规则", "爱心食材店",
                          "领取每日限量食材"], "child")
        self.gallery = obs("kitchen",
                           ["秋食风味录", "美食图鉴", "爱心食材店"], "gallery")
        self.home = obs("feed", ["蚂蚁庄园", "饲料任务"], "home")
        self.kitchen_frame = kitchen_frame
        self.obs = None
        self.taps = []
        self.done_calls = []
        self.complete_rows = []

    def row(self, *args, **kwargs):
        return self.row_value

    def tap_element(self, _obs, _button, predicate, **kwargs):
        assert predicate(self.kitchen_frame)
        self.obs = self.kitchen_frame

    def tap(self, pattern, predicate, **kwargs):
        # Faithful to the executor: only spend (irreversible) taps enter
        # store.intent(), so only those meet the unresolved guard.
        if kwargs.get("spend"):
            stuck = self.ex.store.unresolved(self.task)
            if stuck:
                raise AutomationError(
                    f"Unresolved submission for {self.task}: "
                    f"'{stuck[0][1]}' awaits evidence",
                    "RESULT_UNKNOWN")
        if pattern == "爱心食材店":
            self.obs = self.child
        elif pattern == "做美食":
            assert predicate(self.gallery)
            self.obs = self.gallery
        self.taps.append((pattern, kwargs))

    def back(self, target, **kwargs):
        if callable(target):
            landing = self.kitchen_frame
            assert target(landing)
        elif "kitchen" in target:
            landing = self.kitchen_frame
        else:
            landing = self.home
        self.obs = landing

    def done(self, obs=None, **kwargs):
        self.done_calls.append(kwargs)

    def complete_row(self, title):
        self.complete_rows.append(title)


def kitchen_out():
    # Attempt 3496e7/295962 frame: chickens out, ingredients claimed.
    return obs("kitchen",
               ["秋食风味录", "普通美食 10 /27", "爱心美食已解锁1个",
                "截止时间：2026.10.31", "爱心食材店", "0肥料",
                "主人，我出去啦", "有事来找我哦", "明日可领食材", "做美食"],
               "kitchen-out")


def kitchen_home():
    return obs("kitchen",
               ["秋食风味录", "普通美食 10 /27", "爱心美食已解锁1个",
                "截止时间：2026.10.31", "爱心食材店", "0肥料",
                "明日可领食材", "做美食"],
               "kitchen-home")


# Action 59: run 3496e7 fired 做美食 from frame 0032-b9750b while the
# chickens were out (the recorded frame carries 主人，我出去啦).
REFUSED_ROW = (59, "做美食", "0032-b9750b", "20260925-194216-3496e7")


def serve_frames(texts_by_key):
    def load(_session, run, frame_id):
        return texts_by_key.get((run, frame_id))
    return load


def test_out_state_cancels_the_refused_cook_and_skips(monkeypatch):
    # Run 3496e7: the 做美食 tap was refused (RESULT_UNKNOWN); run 295962
    # died at the intent before it could even tap. The before frame proves
    # the refusal, so cancel it anchored on that frame, and the live
    # out-state bubble skips the cook instead of tapping blind.
    monkeypatch.setattr(manor_daily, "_load_frame_texts",
                        serve_frames({(REFUSED_ROW[3], REFUSED_ROW[2]):
                                      ["主人，我出去啦"]}))
    session = FakeKitchen(kitchen_out(), pending=[REFUSED_ROW])

    Manor(session).kitchen()

    assert session.ex.store.updates == [(59, "CANCELLED", "0032-b9750b")]
    assert session.done_calls == [{"skipped": True}]
    assert [p for p, _ in session.taps] == ["爱心食材店"]
    assert session.complete_rows == []


def test_chickens_returned_home_still_clears_the_refused_submission(
        monkeypatch):
    # The live bubble disappears once the chickens walk back, but the
    # refusal is still provable from the recorded before frame - without
    # that the cook tap stays locked behind its own stale submission and
    # the task can never finish that day.
    monkeypatch.setattr(manor_daily, "_load_frame_texts",
                        serve_frames({(REFUSED_ROW[3], REFUSED_ROW[2]):
                                      ["主人，我出去啦"]}))
    session = FakeKitchen(kitchen_home(), pending=[REFUSED_ROW])

    Manor(session).kitchen()

    assert session.ex.store.updates == [(59, "CANCELLED", "0032-b9750b")]
    meals = [kwargs for name, kwargs in session.taps if name == "做美食"]
    assert [m.get("detail") for m in meals] == [{"meal": 1}, {"meal": 2}]
    assert session.done_calls == []
    assert session.complete_rows == ["小鸡厨房"]


def test_clean_frame_pending_stays_fail_closed(monkeypatch):
    # A submission fired from a normal kitchen frame proves nothing about
    # a refusal: the intent guard must keep blocking the cook rather than
    # blanket-clearing stale work.
    monkeypatch.setattr(manor_daily, "_load_frame_texts",
                        serve_frames({("other-run", "0004-clean"):
                                      ["明日可领食材", "做美食"]}))
    session = FakeKitchen(
        kitchen_home(), pending=[(12, "做美食", "0004-clean", "other-run")])

    try:
        Manor(session).kitchen()
    except AutomationError as error:
        assert error.code == "RESULT_UNKNOWN"
        assert "awaits evidence" in str(error)
    else:
        raise AssertionError("expected the intent guard to hold")

    assert session.ex.store.updates == []
    assert session.done_calls == []
    assert [p for p, _ in session.taps] == ["爱心食材店"]


def test_missing_frame_record_fails_closed(monkeypatch):
    # Purged or unreadable frames leave no proof of refusal, so nothing
    # may be cancelled on that account.
    monkeypatch.setattr(manor_daily, "_load_frame_texts",
                        serve_frames({}))
    session = FakeKitchen(
        kitchen_home(), pending=[(13, "做美食", "0009-gone", "gone-run")])

    try:
        Manor(session).kitchen()
    except AutomationError as error:
        assert error.code == "RESULT_UNKNOWN"
    else:
        raise AssertionError("expected the intent guard to hold")

    assert session.ex.store.updates == []


def test_load_frame_texts_reads_the_recorded_run_frame(tmp_path):
    runs = tmp_path / "runs"
    (runs / "20260925-194216-3496e7").mkdir(parents=True)
    frame = runs / "20260925-194216-3496e7" / "0032-b9750b.json"
    frame.write_text(json.dumps({
        "page": "kitchen",
        "elements": [{"text": "秋食风味录"}, {"text": "主人，我出去啦"}],
    }, ensure_ascii=False), encoding="utf-8")
    session = SimpleNamespace(ex=SimpleNamespace(
        observer=SimpleNamespace(directory=runs / "20260925-now")))

    assert manor_daily._load_frame_texts(
        session, "20260925-194216-3496e7", "0032-b9750b") == [
            "秋食风味录", "主人，我出去啦"]
    assert manor_daily._load_frame_texts(
        session, "20260925-194216-3496e7", "missing") is None
    assert manor_daily._load_frame_texts(
        session, "20260925-never-run", "0032-b9750b") is None
