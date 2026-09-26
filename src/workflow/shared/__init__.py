import re

from domain_data import AutomationError
from state_machine import Budget
from workflow.recovery import dismiss


def browse(s, swipe):
    # Device cadence (2026-09-23): each capture costs ~2.7-4.0s of
    # screenshot+OCR, and the old cycle spent three per swipe (fresh frame
    # for the overlay check, fresh before-frame, swipe result) plus a dead
    # sleep - ~10.6s between swipes; the user's note: 下滑频率太低. Feed the
    # swipe's own result frame into the next dismissal/completion check and
    # let the 700ms stroke pace the loop. Without a swipe there is no new
    # frame, so the next check captures afresh.
    budget = Budget(55, s.ex.budget)
    obs = None
    while budget.remaining:
        obs = dismiss(s, obs)
        if obs.has("已完成.*可领|浏览完成|已完成", (.45,0,1,.3)):
            return obs
        if obs.page != "ad":
            raise AutomationError("Advertisement timer not identified", "TIMER_MISSING")
        if swipe:
            obs = s.scroll((.5,.73,.5,.55), obs=obs)
        else:
            obs = None
    raise AutomationError("Advertisement completion not verified", "TIMEOUT")


def lottery(s, ads, exchange=False):
    for title in ("每日签到",):
        # Device evidence (2026-09-23): signing flips the chance badge and
        # makes the whole 每日签到 card leave the panel, so success is the
        # card's absence as much as an explicit 已签到. An absent card on
        # arrival means an earlier partial run already signed this side.
        obs = s.ensure("lottery")
        if not obs.has(title):
            continue
        obs, _, button = s.row(title, page="lottery")
        if button.text in ("领取", "签到"):
            s.tap_element(obs, button,
                          lambda o, title=title:o.page == "lottery"
                          and (o.has("领取成功|已签到|已领取")
                               or not o.has(title)),
                          name="lottery-sign", spend=True)
    for index in range(ads):
        obs, title, button = s.row("去杂货铺逛一逛|去森林市集逛一逛", page="lottery")
        if re.search(rf"[（(]{ads}/{ads}[）)]", title.text) and "领取" not in button.text:
            break
        if "领取" not in button.text:
            attempts = s.config.get("ad_entry_attempts", 2)
            for attempt in range(attempts):
                s.tap_element(
                    obs,
                    button,
                    lambda o:o.page in ("ad", "UNKNOWN") or "guess" in o.overlays,
                    name="lottery-ad",
                )
                try:
                    browse(s, True)
                    break
                except AutomationError as exc:
                    if exc.code != "TIMER_MISSING" or attempt + 1 >= attempts:
                        raise
                    s.back(("lottery",), allow_unknown=True)
                    obs, title, button = s.row(
                        "去杂货铺逛一逛|去森林市集逛一逛", page="lottery"
                    )
            # Same completion-view race as the TIMER_MISSING retry above
            # (device evidence 2026-09-25, run f4b926): s.obs.page is
            # browse's stale ad frame while the fresh observation may
            # already be the unruled 任务已完成 summary; the ("lottery",)
            # target guards the landing instead.
            s.back(("lottery",), allow_unknown=True)
            obs, _, button = s.row("去杂货铺逛一逛|去森林市集逛一逛", page="lottery")
        if button.text != "领取":
            raise AutomationError("Lottery advertisement reward not available")
        previous = title.text
        s.tap_element(obs, button, lambda o, previous=previous:o.page == "lottery" and (
            o.has("领取成功") or not o.has(re.escape(previous))
        ),
                      name="lottery-ad-claim", spend=True, detail={"ad":index+1})
    if exchange:
        # Device evidence (2026-09-24, run 6b2c7c): 确认兑换 completes the
        # subtask and its row collapses out of the panel (the same removal
        # the sign strip and the finished ad rows do), so a rerun finds no
        # 消耗饲料换机会 row at all - skip the done exchange instead of
        # raising Required task missing.
        obs, _, button = s.row("消耗饲料换机会", page="lottery", required=False)
        if button is not None and "去完成" in button.text:
            s.tap_element(obs, button, lambda o:o.has("兑换确认|确认兑换"), name="exchange-open")
            s.tap("确认兑换",
                  # Device evidence (2026-09-25, run adde3c): the IP
                  # variant draws no 领取成功|已兑换 toast at all - across
                  # six post-tap captures the only stable success proof is
                  # the 消耗饲料换机会 row collapsing out of the panel
                  # together with the chance count flipping 4次 -> 6次,
                  # first visible on the second capture (~8s in). Keep the
                  # toast for variants that show it and take the collapsed
                  # row plus a readable count as the same completion the
                  # rerun skip above already documents; a failed confirm
                  # keeps the row and still times out visibly.
                  lambda o:o.page == "lottery" and (
                      o.has("领取成功|已兑换")
                      or (not o.has("消耗饲料换机会")
                          and o.has(r"还剩\d+次|剩余\d+次|还有\d+次"))),
                  spend=True, overlay=True,
                  # Device evidence (2026-09-24, run 10b0f5): the IP page's
                  # expanded exchange panel hides 立即抽奖, so the lottery
                  # rule loses group one and the panel reads UNKNOWN while
                  # the CTA text itself is OCR-verified - the postcondition
                  # still demands the recognizable lottery page, hence the
                  # allow_unknown whitelist semantics proven on run 115920
                  # for the dimmed result view.
                  allow_unknown=True)
        else:
            # Device evidence (2026-09-25, runs adde3c -> b8fdaf -> bb1540):
            # the IP variant's confirm postcond timed out without a toast
            # and left '确认兑换' pending in the store, so store.intent()
            # blocked the retry's draw tap with RESULT_UNKNOWN even though
            # the exchange had gone through. Evidence is either the row
            # gone or the row back with its (1/1) done counter - the panel's
            # stable done state (bb1540; the same marker row() itself
            # accepts as completion) - on a lottery frame with a readable
            # count; verify the stale submission here. Any other stuck
            # action keeps blocking until done() can reconcile it.
            if (obs.page == "lottery"
                    and (not obs.has("消耗饲料换机会")
                         or obs.has(r"消耗饲料换机会.*[（(]1/1[）)]"))
                    and obs.has(r"还剩\d+次|剩余\d+次|还有\d+次")):
                for action_id, name, _ in s.ex.store.unresolved(s.task):
                    if name == "确认兑换":
                        s.ex.store.action(action_id, "VERIFIED", obs.id)
    obs = s.ensure("lottery")
    no_progress = 0
    readable = r"还剩\d+次|剩余\d+次|还有\d+次"
    for _ in range(s.config.get("max_reset_scrolls", 8)):
        if obs.has("^[立三主]即抽奖$") and obs.has(readable):
            break
        before = obs
        obs = s.scroll((.5,.4,.5,.82))
        no_progress = no_progress + 1 if s.same_view(before, obs) else 0
        if no_progress >= 2:
            break
    if not obs.has("^[立三主]即抽奖$") or not obs.has(readable):
        raise AutomationError("Lottery available chances not verified")
    if obs.has(r"还剩0次|剩余0次|还有0次"):
        # Device evidence (2026-09-23): the one-tap draw leaves the badge
        # at 还有0次机会; a re-run reaching this point has already run the
        # idempotent sign and ad phases above (a fresh sign grants its
        # chance before this check), so an explicit zero means the draw is
        # done for the day - skip instead of failing the nonzero read-guard
        # or double-spending.
        return
    s.tap("^[立三主]即抽奖$", lambda o:o.has(
        # The spec-era popup said 获得奖励/开心收下 (video 02:03); this
        # period's draw shows 恭喜抽中 + prize balls with 做任务继续抽 once
        # the one-tap draw consumed every chance (device 2026-09-23, run
        # 111049: 3 chances -> 66g/20g/10g in one view), and the dimmed
        # result view loses every lottery rule marker, so only texts can
        # prove completion.
        "获得奖励|开心收下|恭喜抽中|做任务继续抽"), spend=True)
    obs = dismiss(s)
    if obs.has("恭喜抽中|做任务继续抽|我知道了|获得奖励|开心收下"):
        # Close the era result view through its OCR'd CTA: the dimmed view
        # leaves the page UNKNOWN and the side switch that follows needs a
        # recognizable lottery page back (postcondition: view gone and the
        # task list readable as lottery again). Device evidence (2026-09-24,
        # run 6b2c7c): the costume-prize result (丹桂秋光) carries a lone
        # 我知道了 CTA instead of 做任务继续抽; spec L56/L63 (videos 02:03
        # and 03:54) document the 获得奖励 popup closed through 开心收下,
        # which the draw's own postcondition already accepts - so take all
        # three documented spellings.
        s.tap("做任务继续抽|我知道了|开心收下",
              lambda o: o.page == "lottery"
              and not o.has("恭喜抽中|做任务继续抽"),
              # Device evidence (2026-09-23, run 115920): the executor's
              # unknown-page guard refused this tap because the dimmed
              # result view loses every lottery rule marker - the CTA text
              # itself is OCR-verified and the postcondition still demands
              # the recognizable lottery page, which is the allow_unknown
              # whitelist semantics.
              allow_unknown=True)
