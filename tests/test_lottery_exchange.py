"""Lottery exchange completion evidence calibrated against device evidence.

Run adde3c (2026-09-25): the IP variant's 确认兑换 really went through
(还剩4次 -> 6次, the 消耗饲料换机会 row collapsed out of the panel ~8s after
the confirm) but never drew the 领取成功|已兑换 toast the postcondition
waited for, so the tap timed out on a completed exchange. The predicate must
accept the collapsed-row-plus-readable-count evidence while still guarding
the lottery page and still failing when the confirm did nothing.
"""

from types import SimpleNamespace

from domain_data import AutomationError, Element, Observation
from workflow import shared as shared_workflow
from workflow.shared import lottery


def obs(page, texts, oid="fixture"):
    elements = [Element(text, (100, 400 + 60 * i, 900, 460 + 60 * i), oid)
                for i, text in enumerate(texts)]
    return Observation(oid, 0.0, 1440, 3200, "alipay", elements, page)


class FakeStore:
    def __init__(self, pending=()):
        self.pending = list(pending)
        self.verified = []

    def unresolved(self, task):
        return list(self.pending)

    def action(self, action, state, after=None):
        self.verified.append((action, state, after))
        self.pending = [p for p in self.pending if p[0] != action]


class FakeLottery:
    def __init__(self):
        self.task = "manor.feed.ip_lottery"
        self.config = {}
        self.ex = SimpleNamespace(store=FakeStore())
        self.panel = obs("lottery", ["装扮抽抽乐", "消耗饲料换机会(0/1)",
                                     "去完成", "还剩4次机会", "立即抽奖"],
                         "panel")
        self.final = obs("lottery", ["装扮抽抽乐", "还剩6次机会",
                                     "一键连抽6次", "立即抽奖"], "final")
        # First ensure feeds the sign loop (no 每日签到 card -> already
        # signed); the post-exchange ensure feeds the chance verification.
        self._ensures = [self.panel, self.final]
        self.exchange_row = (self.panel,
                             Element("消耗饲料换机会(0/1)", (334, 2453, 846, 2514),
                                     "panel"),
                             Element("去完成", (1152, 2500, 1285, 2551), "panel"))
        self.tap_element_calls = []
        self.taps = {}

    def ensure(self, page):
        return self._ensures.pop(0)

    def row(self, title, required=True, reset=False, page="feed"):
        return self.exchange_row

    def tap_element(self, _obs, button, predicate, **kwargs):
        self.tap_element_calls.append((button.text, kwargs.get("name")))
        assert predicate(obs("UNKNOWN", ["消耗饲料换机会(0/1)", "取消",
                                         "确认兑换"], "exchange-open"))

    def tap(self, pattern, predicate, **kwargs):
        stuck = self.ex.store.unresolved(self.task)
        if stuck:
            raise AutomationError(
                f"Unresolved submission for {self.task}: "
                f"'{stuck[0][1]}' awaits evidence",
                "RESULT_UNKNOWN")
        self.taps[pattern] = (predicate, kwargs)


def test_exchange_accepts_the_toastless_row_collapse(monkeypatch):
    monkeypatch.setattr(shared_workflow, "dismiss",
                        lambda session: session.final)
    session = FakeLottery()

    lottery(session, 0, exchange=True)

    assert session.tap_element_calls == [("去完成", "exchange-open")]
    predicate, kwargs = session.taps["确认兑换"]
    # Mid-processing frame (adde3c 0055): row still drawn, count not yet
    # flipped - the confirm must not count as done here.
    assert not predicate(obs("lottery", ["装扮抽抽乐", "消耗饲料换机会(0/1)",
                                         "还剩4次机会", "立即抽奖"], "mid"))
    # Success frame (adde3c 0056+): row collapsed and count readable.
    assert predicate(obs("lottery", ["装扮抽抽乐", "还剩6次机会",
                                     "一键连抽6次", "立即抽奖"], "done"))
    # Legacy variant evidence: the toast alone still proves completion.
    assert predicate(obs("lottery", ["装扮抽抽乐", "领取成功", "还剩5次机会"],
                         "toast"))
    # Row-and-count text on an unrecognised page (partial OCR of the
    # transitional frame) must stay fail-closed behind the page guard.
    assert not predicate(obs("UNKNOWN", ["还剩6次机会"], "unknown"))
    # The lottery draw itself still runs after the exchange.
    assert "^[立三主]即抽奖$" in session.taps
    assert kwargs == {"spend": True, "overlay": True, "allow_unknown": True}


def test_exchange_skips_when_the_subtask_row_already_collapsed(monkeypatch):
    monkeypatch.setattr(shared_workflow, "dismiss",
                        lambda session: session.final)
    session = FakeLottery()
    # Rerun after adde3c: the exchange completed, so row() must report the
    # missing row (required=False) and the flow skips to chance verification.
    session.row = lambda *args, **kwargs: (session.panel,
                                           Element("x", (0, 0, 1, 1), "panel"),
                                           None)

    lottery(session, 0, exchange=True)

    assert "确认兑换" not in session.taps
    assert "^[立三主]即抽奖$" in session.taps


def test_retry_reconciles_the_stale_confirm_with_the_collapsed_row(
        monkeypatch):
    # Device evidence (2026-09-25, runs adde3c -> b8fdaf): the timed-out
    # confirm left '确认兑换' pending in the store, and the retry - which
    # correctly skips the already-done exchange - then died at the draw tap
    # under the store's intent() guard with RESULT_UNKNOWN. Reaching the
    # skip branch on a lottery frame without the row and with a readable
    # count IS the evidence that confirm awaited, so the stale submission
    # must be verified there or the task stays locked for the day.
    monkeypatch.setattr(shared_workflow, "dismiss",
                        lambda session: session.final)
    session = FakeLottery()
    session.ex.store = FakeStore([(7, "确认兑换", None)])
    gone = obs("lottery", ["装扮抽抽乐", "还剩6次机会", "立即抽奖"], "row-gone")
    session.row = lambda *args, **kwargs: (gone, None, None)

    lottery(session, 0, exchange=True)

    assert session.ex.store.verified == [(7, "VERIFIED", "row-gone")]
    assert "^[立三主]即抽奖$" in session.taps


def test_retry_reconciles_when_the_row_reports_the_done_counter(monkeypatch):
    # Device evidence (2026-09-25, run bb1540): the collapsed row renders
    # back as 消耗饲料换机会(1/1) - the panel's stable done state, the same
    # marker row() accepts as its button - so the evidence guard must take
    # the (1/1) counter as well as the row's absence, or the retry stays
    # locked behind the stale submission forever.
    monkeypatch.setattr(shared_workflow, "dismiss",
                        lambda session: session.final)
    session = FakeLottery()
    session.ex.store = FakeStore([(55, "确认兑换", None)])
    done_row = obs("lottery", ["装扮抽抽乐", "消耗饲料换机会(1/1)",
                               "还剩6次机会", "立即抽奖"], "done-row")
    anchor = Element("消耗饲料换机会(1/1)", (335, 2543, 840, 2596), "done-row")
    session.row = lambda *args, **kwargs: (done_row, anchor, anchor)

    lottery(session, 0, exchange=True)

    assert session.ex.store.verified == [(55, "VERIFIED", "done-row")]
    assert "^[立三主]即抽奖$" in session.taps


def test_retry_reconciles_the_stale_sign_with_the_consumed_card(monkeypatch):
    # Device evidence (2026-09-28, runs 84c8a6 -> fc7b38): 84c8a6's sign
    # tap took effect (the card left the panel in one refresh) but its
    # postcondition starved on the UNKNOWN-classified frames and left
    # lottery-sign RESULT_UNKNOWN, so fc7b38's intent guard refused the
    # next spend while the sign itself was already done. The consumed card
    # on a lottery frame IS the evidence the sign awaited - verify there.
    monkeypatch.setattr(shared_workflow, "dismiss",
                        lambda session: session.final)
    session = FakeLottery()
    session.ex.store = FakeStore([(9, "lottery-sign", None)])
    gone = obs("lottery", ["装扮抽抽乐", "还剩6次机会", "立即抽奖"], "sign-gone")
    session._ensures = [gone, session.final]

    lottery(session, 0)

    assert session.ex.store.verified == [(9, "VERIFIED", "sign-gone")]
    assert "^[立三主]即抽奖$" in session.taps


def test_retry_cancels_the_stale_sign_and_resigns_while_the_card_offers_it(
        monkeypatch):
    # The opposite fate: the card still offering the sign proves the stuck
    # tap never took effect, so it is cancelled - the flow then re-fires
    # the sign itself instead of staying locked behind the stale
    # submission for the rest of the day.
    monkeypatch.setattr(shared_workflow, "dismiss",
                        lambda session: session.final)
    session = FakeLottery()
    session.ex.store = FakeStore([(9, "lottery-sign", None)])
    card = obs("lottery", ["每日签到", "签到", "每天访问，得1次抽奖机会",
                           "装扮抽抽乐", "还剩4次机会", "立即抽奖"], "sign-card")
    anchor = Element("每日签到", (335, 2419, 900, 2482), "sign-card")
    button = Element("签到", (1150, 2485, 1350, 2555), "sign-card")
    session._ensures = [card, session.final]
    session.row = lambda *args, **kwargs: (card, anchor, button)
    signed = obs("lottery", ["装扮抽抽乐", "还剩5次机会", "立即抽奖"], "signed")

    def tap_element(_obs, element, predicate, **kwargs):
        session.tap_element_calls.append((element.text, kwargs.get("name")))
        assert predicate(signed)

    session.tap_element = tap_element

    lottery(session, 0)

    assert session.ex.store.verified == [(9, "CANCELLED", "sign-card")]
    assert session.tap_element_calls == [("签到", "lottery-sign")]
    assert "^[立三主]即抽奖$" in session.taps


def panel_of(oid, *items):
    return Observation(oid, 0.0, 1440, 3200, "alipay",
                       [Element(text, bounds, oid) for text, bounds in items],
                       page="lottery")


def test_ad_claim_accepts_the_pill_consumed_toastless_panel(monkeypatch):
    # Device evidence (2026-09-28, run 1a0a44): the claim landed - frames
    # 0019 -> 0020 flip 还有1次机会 to 还有2次机会 and consume the 领取 pill -
    # but the panel draws no 领取成功 toast and the (1/2) title only counts
    # browses, so both original alternatives starved on a completed claim
    # and left RESULT_UNKNOWN. The pill vanishing from its paired
    # title_y+35 slot is the completion evidence.
    monkeypatch.setattr(shared_workflow, "dismiss",
                        lambda session: session.final)
    session = FakeLottery()
    claim_row = panel_of("claim-row",
                         ("去森林市集逛一逛(1/2)", (339, 2419, 930, 2482)),
                         ("领取", (1171, 2461, 1266, 2509)),
                         ("还有1次机会", (100, 400, 900, 460)),
                         ("立即抽奖", (100, 520, 900, 580)))
    title = Element("去森林市集逛一逛(1/2)", (339, 2419, 930, 2482), "claim-row")
    pill = Element("领取", (1171, 2461, 1266, 2509), "claim-row")
    session.row = lambda *args, **kwargs: (claim_row, title, pill)
    captured = {}

    def tap_element(_obs, element, predicate, **kwargs):
        session.tap_element_calls.append((element.text, kwargs.get("name")))
        captured[kwargs.get("name")] = predicate

    session.tap_element = tap_element

    lottery(session, 1)

    predicate = captured["lottery-ad-claim"]
    # Toastless success: title unchanged, pill gone, count bumped; a
    # different row's 领取 ~300px below must not read as ours still open.
    assert predicate(panel_of(
        "consumed",
        ("去森林市集逛一逛(1/2)", (339, 2419, 930, 2482)),
        ("还有2次机会", (100, 400, 900, 460)),
        ("立即抽奖", (100, 520, 900, 580)),
        ("领取", (1171, 2731, 1266, 2779))))
    # Our pill still standing at the paired slot: the claim did not fire.
    assert not predicate(panel_of(
        "offered",
        ("去森林市集逛一逛(1/2)", (339, 2419, 930, 2482)),
        ("领取", (1171, 2461, 1266, 2509)),
        ("还有1次机会", (100, 400, 900, 460))))
    assert not predicate(Observation("unknown", 0.0, 1440, 3200, "alipay",
                                     [], page="UNKNOWN"))
    assert "^[立三主]即抽奖$" in session.taps


def test_retry_reconciles_the_stale_ad_claim_with_the_consumed_pill(monkeypatch):
    monkeypatch.setattr(shared_workflow, "dismiss",
                        lambda session: session.final)
    # Device evidence (2026-09-28, runs 1a0a44 -> next): fc7b38 left
    # lottery-ad-claim RESULT_UNKNOWN behind a claim that had landed
    # (pill gone, count +1), so the intent guard would refuse every later
    # spend that day. The pill already consumed on the entry panel IS the
    # evidence the claim awaited - verify it there.
    session = FakeLottery()
    session.ex.store = FakeStore([(11, "lottery-ad-claim", None)])
    gone = panel_of("pill-gone",
                    ("去森林市集逛一逛(1/2)", (339, 2419, 930, 2482)),
                    ("还有2次机会", (100, 400, 900, 460)),
                    ("立即抽奖", (100, 520, 900, 580)))
    session._ensures = [gone, session.final]

    lottery(session, 0)

    assert session.ex.store.verified == [(11, "VERIFIED", "pill-gone")]
    assert "^[立三主]即抽奖$" in session.taps


def test_retry_cancels_the_stale_ad_claim_while_the_pill_still_offers(monkeypatch):
    monkeypatch.setattr(shared_workflow, "dismiss",
                        lambda session: session.final)
    # The opposite fate: the pill still standing at the row's paired
    # title_y+35 slot proves the stuck claim never took, so it is
    # cancelled and the ads loop is free to fire the claim again.
    session = FakeLottery()
    session.ex.store = FakeStore([(11, "lottery-ad-claim", None)])
    standing = panel_of("still-offered",
                        ("去森林市集逛一逛(1/2)", (339, 2419, 930, 2482)),
                        ("领取", (1171, 2461, 1266, 2509)),
                        ("还有1次机会", (100, 400, 900, 460)),
                        ("立即抽奖", (100, 520, 900, 580)))
    session._ensures = [standing, session.final]

    lottery(session, 0)

    assert session.ex.store.verified == [(11, "CANCELLED", "still-offered")]
    assert "^[立三主]即抽奖$" in session.taps


def test_result_view_close_takes_the_suit_cta_spelling(monkeypatch):
    # Device evidence (2026-09-30, run 573250): the permanent-suit prize
    # rendered 恭喜抽中 6件奖品 with a lone 穿上装扮 CTA on the dimmed
    # result view - a fourth spelling of the same dismiss after 开心收下 /
    # 做任务继续抽 / 我知道了 - and the three-spelling anchor failed closed
    # with found 0 across three identical frames.
    result = obs("UNKNOWN", ["恭喜抽中", "6件奖品",
                             "已放入装扮列表-永久套装", "穿上装扮"], "suit")
    monkeypatch.setattr(shared_workflow, "dismiss", lambda session: result)
    session = FakeLottery()

    lottery(session, 0)

    pattern = "做任务继续抽|我知道了|开心收下|穿上装扮"
    assert pattern in session.taps
    predicate, kwargs = session.taps[pattern]
    # The closed view is the recognizable lottery page without the result
    # header; the dimmed result view itself must never satisfy it.
    assert predicate(obs("lottery", ["装扮抽抽乐", "还剩6次机会",
                                     "立即抽奖"], "closed"))
    assert not predicate(result)
    assert not predicate(obs("lottery", ["恭喜抽中", "还剩6次机会"],
                             "header-left"))
    assert kwargs == {"allow_unknown": True}
