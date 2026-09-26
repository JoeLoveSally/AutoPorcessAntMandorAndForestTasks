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
