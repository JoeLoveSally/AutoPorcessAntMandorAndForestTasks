"""Kitchen cooking guard calibrated against device evidence.

Runs 3496e7 -> 295962 (2026-09-25): with the chickens out the 做美食 tap is
refused behind a ~2s toast (小鸡不在家哦，等它回来) that the runner's ~4s
capture cadence misses, so the postcondition starved and left the
submission RESULT_UNKNOWN - which then blocked every later spend of the
task. The refusal proof lives in the action's own before frame: that frame
records the standing out-state bubble at tap time, so the submission stays
cancellable even after the chickens walk back home.

Run 780c45 (2026-09-26): on-device the tap cooks directly and answers
with a result modal (金枪鱼海苔卷制作成功 / 厨余生成了60肥料) - the spec's
美食图鉴 gallery has never rendered - so the old gallery postcondition
starved on a cook that DID happen. That submission's proof lives in the
later frames of its own run: verify it from that record. A submission
with neither record stays fail-closed behind the intent guard; the live
out-state bubble skips the cook instead of tapping into the refusal.
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
    def __init__(self, kitchen_frame, pending=(), dialog=None, confirmed=None,
                 shop_frame=None, shop_frames=None, shop_claim_frames=None,
                 cook_frame=None):
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
        if shop_frame is not None:
            self.child = shop_frame
        # One entry frame per 爱心食材店 visit: the first visit lands on
        # shop_frames[0], a post-cook retry on the next one.
        self.shop_frames = list(shop_frames) if shop_frames is not None else [self.child]
        # One served frame per 领10g食材 tap; empty keeps the historic
        # behavior of leaving the observation untouched.
        self.shop_claim_frames = list(shop_claim_frames or [])
        self.gallery = obs("kitchen",
                           ["秋食风味录", "美食图鉴", "爱心食材店"], "gallery")
        self.home = obs("feed", ["蚂蚁庄园", "饲料任务"], "home")
        self.kitchen_frame = kitchen_frame
        self.dialog = dialog
        self.confirmed = confirmed
        self.cook_frame = cook_frame
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
            self.obs = (self.shop_frames.pop(0)
                        if len(self.shop_frames) > 1 else self.shop_frames[0])
        elif pattern == "领10g食材" and self.shop_claim_frames:
            frame = self.shop_claim_frames.pop(0)
            assert predicate(frame)
            self.obs = frame
        elif pattern == "做美食":
            frame = (self.cook_frame if self.cook_frame is not None
                     else self.gallery)
            assert predicate(frame)
            self.obs = frame
        elif pattern in ("领今日食材", "领取食材"):
            assert self.dialog is not None and predicate(self.dialog)
            self.obs = self.dialog
        elif pattern == "^确认$":
            assert self.confirmed is not None and predicate(self.confirmed)
            self.obs = self.confirmed
        self.taps.append((pattern, kwargs))

    def back(self, target, **kwargs):
        if callable(target):
            # The executor observes first: the frame at hand (gallery or
            # result modal) must NOT satisfy the predicate, or back would
            # return without dismissing it.
            assert not target(self.obs)
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


def kitchen_pending():
    # Run e480ea frame 0016: the standing claim button before the tap,
    # chickens already out.
    return obs("kitchen",
               ["秋食风味录", "普通美食 10 /27", "爱心美食已解锁1个",
                "截止时间：2026.10.31", "爱心食材店", "0肥料",
                "主人，我出去啦", "有事来找我哦", "60g", "领今日食材", "做美食"],
               "kitchen-pending")


def kitchen_pantry_dialog():
    # Run e480ea frame 0018: the near-full pantry's confirm dialog over
    # the still-OCR-visible button - the frame the old not-has
    # postcondition could never accept before it timed out.
    return obs("kitchen",
               ["秋食风味录", "普通美食 10 /27", "爱心美食已解锁1个",
                "截止时间：2026.10.31", "爱心食材店", "0肥料",
                "食材快放不下啦", "当前仅能装下50g食材", "确认领取今日食材吗？",
                "确认", "领今日食材", "做美食"],
               "kitchen-pantry")


def kitchen_confirmed():
    # Post-^确认$ frame: the dialog is gone and the claim shows its done
    # state while the chickens are still out.
    return obs("kitchen",
               ["秋食风味录", "普通美食 10 /27", "爱心美食已解锁1个",
                "截止时间：2026.10.31", "爱心食材店", "0肥料",
                "主人，我出去啦", "有事来找我哦", "明日可领食材", "做美食"],
               "kitchen-confirmed")


def test_pantry_near_full_dialog_is_confirmed_and_the_chain_continues():
    # Run e480ea (2026-09-26): the pantry was nearly full, so the claim
    # raised its confirm dialog instead of completing; the button stayed
    # OCR-visible behind it and the not-has postcondition starved. The
    # dialog is the claim proceeding - accept it, anchor ^确认$, then let
    # the rest of the chain (store visit, chickens-out skip) run.
    session = FakeKitchen(
        kitchen_pending(),
        dialog=kitchen_pantry_dialog(),
        confirmed=kitchen_confirmed(),
    )

    Manor(session).kitchen()

    assert [p for p, _ in session.taps] == ["领今日食材", "^确认$", "爱心食材店"]
    assert session.done_calls == [{"skipped": True}]
    assert session.complete_rows == []


# Run e480ea (2026-09-26) left this claim RESULT_UNKNOWN after its
# postcondition starved behind the pantry dialog; the retry 4a78d9 died at
# the intent guard before it could tap 领今日食材 at all.
STALE_CLAIM = (90, "领今日食材", "0016-a9ea0f", "20260926-111215-e480ea")


def test_stale_claim_is_cancelled_while_the_affordance_still_offers_it():
    # The retry's fresh kitchen frame still offers 领今日食材 - durable
    # proof the stale submission never took effect - so cancel it and let
    # the claim chain fire instead of dying at the intent guard again.
    session = FakeKitchen(
        kitchen_pending(),
        pending=[STALE_CLAIM],
        dialog=kitchen_pantry_dialog(),
        confirmed=kitchen_confirmed(),
    )

    Manor(session).kitchen()

    assert session.ex.store.updates == [(90, "CANCELLED", "kitchen-pending")]
    assert [p for p, _ in session.taps] == ["领今日食材", "^确认$", "爱心食材店"]
    assert session.done_calls == [{"skipped": True}]


def test_stale_claim_is_verified_once_the_affordance_is_consumed():
    # A previous run died after the claim went through (the button now
    # reads 明日可领): verify the stale submission on that evidence so the
    # later spends of this retry - the shop claim and the cooks - can fire.
    session = FakeKitchen(kitchen_home(), pending=[STALE_CLAIM])

    Manor(session).kitchen()

    assert session.ex.store.updates == [(90, "VERIFIED", "kitchen-home")]
    meals = [kwargs for name, kwargs in session.taps if name == "做美食"]
    assert [m.get("detail") for m in meals] == [{"meal": 1}, {"meal": 2}]
    assert session.complete_rows == ["小鸡厨房"]


def shop_claimable():
    # A fresh shop frame that still offers the daily claim.
    return obs("ingredient_shop",
               ["献爱心得食材", "规则", "领10g食材"], "shop-open")


def test_stale_shop_claim_is_cancelled_while_the_shop_offers_it():
    # A 领10g食材 stuck from an earlier run would block every later spend
    # of this task (the intent guard is task-wide), so it must resolve on
    # the shop's own affordance before the retry's shop tap.
    stale = (91, "领10g食材", "0021-88bb12", "20260925-104400-oldrun")
    session = FakeKitchen(kitchen_home(), pending=[stale],
                          shop_frame=shop_claimable())

    Manor(session).kitchen()

    assert session.ex.store.updates == [(91, "CANCELLED", "shop-open")]
    assert any(p == "领10g食材" for p, _ in session.taps)


def bag_full_refusal():
    # Run 6bafea frame 0024: the bag at its 300g cap refuses the free
    # 10g with a ~8s toast while the button stays OCR-visible - the frame
    # the plain not-has postcondition could never accept.
    return obs("ingredient_shop",
               ["献爱心得食材", "规则", "领10g食材",
                "食材袋放不下了，使用后", "再领取吧"], "shop-refused")


def bag_claimed():
    return obs("ingredient_shop",
               ["献爱心得食材", "规则", "领取每日限量食材"], "shop-claimed")


def test_bag_full_refusal_is_accepted_and_retried_after_the_cooks():
    # Run 6bafea (2026-09-26): the near-full pantry filled the bag to
    # 300g, so the shop refused the claim behind a toast - the chain must
    # take that as the submission's answer instead of starving, and honor
    # the toast's own advice (使用后再领取吧) with one post-cook retry.
    session = FakeKitchen(
        kitchen_home(),
        shop_frames=[shop_claimable(), shop_claimable()],
        shop_claim_frames=[bag_full_refusal(), bag_claimed()],
    )

    Manor(session).kitchen()

    assert [p for p, _ in session.taps] == [
        "爱心食材店", "领10g食材", "做美食", "做美食",
        "爱心食材店", "领10g食材"]
    assert session.done_calls == []
    assert session.complete_rows == ["小鸡厨房"]


def cook_result_modal():
    # Run 780c45 frame 0031: the tap cooks directly on-device and answers
    # with a modal (金枪鱼海苔卷制作成功 + 查看图鉴 + 厨余生成了60肥料) over a
    # dimmed kitchen - the 美食图鉴 gallery from the spec video has never
    # rendered on a real frame.
    return obs("kitchen",
               ["秋食风味录", "普通美食 10/27", "金枪鱼海苔卷制作成功",
                "喂食小鸡立产0.12颗爱心蛋", "查看图鉴", "厨余生成了60肥料",
                "3次内必解锁一道新的美食哦", "明日可领食材", "做美食"],
               "cook-modal")


def test_cook_accepts_the_device_result_modal():
    # The modal IS the cook's proof on-device; demanding 美食图鉴 starved
    # 780c45's successful cook. The dismissal predicate must also name the
    # modal's own texts, or a modal frame that classifies kitchen would
    # pass without back ever pressing and the modal would swallow the
    # next tap.
    session = FakeKitchen(kitchen_home(), cook_frame=cook_result_modal())

    Manor(session).kitchen()

    meals = [kwargs for name, kwargs in session.taps if name == "做美食"]
    assert [m.get("detail") for m in meals] == [{"meal": 1}, {"meal": 2}]
    assert session.done_calls == []
    assert session.complete_rows == ["小鸡厨房"]


# Run 780c45 (2026-09-26): the cook succeeded but the gallery postcond
# timed out, leaving RESULT_UNKNOWN that blocks every later spend of the
# retry (id=109, before frame 0029-8a7cec on a normal kitchen).
COOK_ROW = (109, "做美食", "0029-8a7cec", "20260926-134447-780c45")


def test_stale_cook_is_verified_by_the_run_own_result_frames(monkeypatch):
    # The submission's own run recorded the result modal right after the
    # tap - durable proof it took effect. Verify on that record (at
    # entry, before the first spend can trip the guard) and let the
    # retry's cooks fire.
    monkeypatch.setattr(manor_daily, "_load_frame_texts",
                        serve_frames({(COOK_ROW[3], COOK_ROW[2]):
                                      ["明日可领食材", "做美食"]}))
    monkeypatch.setattr(
        manor_daily, "_load_run_proof",
        lambda _s, run, after, _pattern:
            "0031-21cfe1" if (run, after) == (COOK_ROW[3], COOK_ROW[2])
            else None)
    session = FakeKitchen(kitchen_home(), pending=[COOK_ROW])

    Manor(session).kitchen()

    assert session.ex.store.updates == [(109, "VERIFIED", "0031-21cfe1")]
    meals = [kwargs for name, kwargs in session.taps if name == "做美食"]
    assert [m.get("detail") for m in meals] == [{"meal": 1}, {"meal": 2}]
    assert session.complete_rows == ["小鸡厨房"]


def test_load_run_proof_finds_the_first_later_matching_frame(tmp_path):
    runs = tmp_path / "runs"
    run = runs / "20260926-134447-780c45"
    run.mkdir(parents=True)
    for frame_id, texts in [
            ("0029-8a7cec", ["明日可领食材", "做美食"]),
            ("0030-dce30c", ["秋食风味录", "明日可领食材"]),
            ("0031-21cfe1", ["金枪鱼海苔卷制作成功", "厨余生成了60肥料"])]:
        (run / f"{frame_id}.json").write_text(
            json.dumps({"page": "kitchen",
                        "elements": [{"text": t} for t in texts]},
                       ensure_ascii=False), encoding="utf-8")
    session = SimpleNamespace(ex=SimpleNamespace(
        observer=SimpleNamespace(directory=runs / "20260926-now")))

    assert manor_daily._load_run_proof(
        session, "20260926-134447-780c45", "0029-8a7cec",
        r"制作成功|厨余生成|查看图鉴") == "0031-21cfe1"
    # No frame after the tap proves anything: no proof, no cancel.
    assert manor_daily._load_run_proof(
        session, "20260926-134447-780c45", "0031-21cfe1",
        r"制作成功|厨余生成|查看图鉴") is None
    assert manor_daily._load_run_proof(
        session, "20260926-never", "0029-8a7cec",
        r"制作成功|厨余生成|查看图鉴") is None
