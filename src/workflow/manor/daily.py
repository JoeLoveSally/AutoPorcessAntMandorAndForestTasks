from __future__ import annotations

import json
import re

from domain_data import AutomationError, Element


def _load_frame_texts(session, run, frame_id):
    """Texts of a recorded run frame, or None when it cannot be read.

    The observer's directory sits at <runs root>/<current run>, so the
    sibling run folder holds every past submission's before frame; any
    read failure returns None and callers must treat that as "no proof".
    """
    try:
        root = session.ex.observer.directory.parent
        payload = json.loads((root / run / f"{frame_id}.json")
                             .read_text(encoding="utf-8"))
        return [element.get("text", "") for element in payload["elements"]]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _load_run_proof(session, run, after_frame, pattern):
    """First later frame of ``run`` matching ``pattern``, or None.

    The runner records every frame a submission produced (same directory
    as the before frame), so a postcondition that timed out on the wrong
    text still left durable proof of what the app actually answered -
    frame ids sort zero-padded, and any read failure means "no proof".
    """
    try:
        root = session.ex.observer.directory.parent
        frame_ids = sorted(p.stem for p in (root / run).glob("*.json"))
    except OSError:
        return None
    for frame_id in frame_ids:
        if frame_id <= after_frame:
            continue
        texts = _load_frame_texts(session, run, frame_id)
        if texts is not None and any(re.search(pattern, t) for t in texts):
            return frame_id
    return None


class Manor:
    def __init__(self, session):
        self.s = session

    def family_donate(self):
        s = self.s
        obs, title, button = s.row("每日捐蛋|捐蛋做好事", page="family_tasks")
        if re.search("[明朋]天再来", button.text) or re.search(r"[（(]1/1[）)]", title.text):
            s.done(obs, already=True)
            return
        if s.ex.store.unresolved(s.task):
            raise AutomationError("Donation result unresolved; family progress is not complete", "RESULT_UNKNOWN")
        s.tap_element(obs, button, lambda o: o.page == "donate_projects", name="open-donation")
        obs = s.observe("project-list")
        projects = obs.find("^去捐蛋$")
        if not projects:
            raise AutomationError("No donation project found")
        s.tap_element(obs, min(projects, key=lambda e:e.point[1]),
                      lambda o:o.page == "donate_detail", name="first-project")
        # Device evidence (2026-09-24, run 17b8ff): the detail page's
        # bottom-center control reads 去捐蛋 (3 chars wide), not spec L14's
        # 立即捐蛋; keep the demo-era labels as tolerated variants.
        s.tap("^[立三主]即捐蛋$|^捐爱心蛋$|^去捐蛋$", lambda o:o.page == "donate_quantity")
        obs = s.observe("donation-quantity")
        one_selected = obs.has(r"^[1/]\s*颗$", (0,.5,1,1))
        quantity_controls = obs.has("^5颗$", (0,.5,1,1)) and obs.has("^自定义$", (0,.5,1,1))
        if not (one_selected and quantity_controls and obs.has("当前还?有.*颗爱心蛋")):
            raise AutomationError("Donation quantity is not verified as one", "QUANTITY")
        s.tap("^[立三主]即捐蛋$|^捐爱心蛋$", lambda o:o.page == "donate_success", region=(0,.7,1,1),
              spend=True, detail={"eggs":1})
        s.ensure("family_tasks")
        s.complete_row("每日捐蛋|捐蛋做好事", page="family_tasks")

    def family_action(self, kind):
        s = self.s
        title_pattern = (r"^请家人吃一顿美食.*[（(]\d+/\d+[）)]$" if kind == "meal"
                         else r"^帮喂家人小鸡.*[（(]\d+/\d+[）)]$")
        obs, title, button = s.row(title_pattern, page="family_tasks")
        if re.search("[明朋]天再来|点后|已完成", button.text) or re.search(r"[（(]1/1[）)]", title.text):
            s.done(obs, already=True)
            return
        if obs.has("暂无小鸡"):
            # Device evidence (2026-09-24, run 974051): the feed slot
            # rendered the disabled two-line label 暂无小鸡可喂 (OCR
            # segments it as 暂无小鸡 + 可喂), so no TASK_BUTTON matched -
            # row() fell through three row-refresh frames to the column
            # fallback, whose tap is a no-op on the dead label. No family
            # chicken is feedable right now; (0/1) cannot advance.
            s.done(obs, skipped=True)
            return
        prompt = "美食" if kind == "meal" else "确认喂食"
        s.tap_element(obs, button, lambda o:o.has(prompt) or o.has("^确认$"), name="family-"+kind)
        # Device evidence (2026-09-24, run 3b0d9e): the open sheet classifies
        # UNKNOWN (title OCRs 已选4份美食..., matching no page rule), so
        # page == family_tasks alone proves dismissal. The old
        # not-o.has(prompt) clause was unsatisfiable for meal - the list row
        # title 请家人吃一顿美食(1/3) itself contains 美食 - so a verified
        # 0/3 -> 1/3 请客 still timed out; complete_row re-verifies below.
        s.tap("^确认$", lambda o:o.page == "family_tasks",
              overlay=True, allow_unknown=True, spend=True)
        s.complete_row(title_pattern, page="family_tasks")

    def sign(self):
        """Claim the feed-page sign-in strip.

        Real-device evidence (2026-09-21): the strip carries no standalone
        "签到" text, OCR misreads "今天" often, and the whole strip disappears
        once claimed. Anchor on the list header plus a "第N天" cell instead.
        """
        s = self.s
        obs = s.ensure("feed")
        for _ in range(s.config.get("max_reset_scrolls", 8)):
            if obs.has("饲料任务", (.2, .24, .8, .40)):
                break
            obs = s.scroll((.5, .4, .5, .68))
        if not obs.has("饲料任务", (.2, .24, .8, .40)):
            raise AutomationError("Feed list top not reachable for daily sign", "UNKNOWN")
        # Absence must be confirmed twice on a verified top view; a single
        # observation cannot prove the strip is gone.
        for _attempt in range(2):
            if obs.find(r"第[2-5]天", (0, .36, 1, .48)):
                break
            obs = s.observe("sign-strip-absence-confirm")
            if not obs.has("饲料任务", (.2, .24, .8, .40)):
                raise AutomationError("Feed top lost while confirming sign strip", "UNKNOWN")
        else:
            s.done(obs, already=True)
            return
        if obs.has("^已领取$", (.68, .36, 1, .48)):
            s.done(obs, already=True)
            return
        buttons = obs.find("^领取$", (.68, .36, 1, .48))
        if len(buttons) != 1:
            raise AutomationError("Daily sign-in claim control is not unique", "AMBIGUOUS")
        button = buttons[0]
        s.tap_element(obs, button,
                      lambda o:o.has("^已领取$", (.68, .36, 1, .48)) or "overflow" in o.overlays,
                      name="daily-sign")
        if "overflow" in s.obs.overlays:
            if s.obs.has("先消耗一些饲料|^知道了$"):
                # Device evidence (2026-09-24, run 0ace75): at the 1800g cap
                # Alipay hard-refuses the claim (饲料袋已满; 知道了 /
                # 去帮好友喂食) instead of spec L29's discard-confirm - no
                # room is left to discard into. The mandated 主页-家庭-领饲料
                # order spends feed first (family.feed consumes 180g); if it
                # already ran, dismiss and fail with the actionable cause
                # rather than hunting hungry friends (not spec'd, gated by
                # friend availability). Key on the refusal body or its own
                # 知道了 button, NOT 去帮好友喂食: the near-full confirm
                # (2026-09-25, run 7ecb00) carries that same button.
                s.tap("^知道了$", lambda o:not o.has("先消耗一些饲料|去帮好友喂食"),
                      overlay=True)
                raise AutomationError(
                    "Feed bag full: sign claim blocked; run manor.family.feed first",
                    "BLOCKED")
            # Spec L29 mandates confirming the sign claim dialog, including
            # the near-full variant (2026-09-25, run 7ecb00: 饲料袋快满了 /
            # 现在饲料袋只能装下60g，确认领取吗？ with 去帮好友喂食 + 确认).
            # Anchor the button: the dialog body itself contains 确认
            # (run e5bb6b found 2 unanchored). The frame classifies UNKNOWN
            # behind the dialog (dimming garbles the feed rule to 饲料千务),
            # so allow_unknown; and the first post-tap capture may still
            # show the dialog, so recover=False re-captures until it closes
            # instead of tripping dismiss's overflow task-specific guard on
            # the transition frame.
            s.tap("^确认$|^继续领取$", lambda o:o.page == "feed" and not o.overlays,
                  overlay=True, allow_unknown=True, recover=False, spend=True)
        obs = s.observe("verify-daily-sign")
        if not obs.has("^已领取$", (.68, .36, 1, .48)):
            raise AutomationError("Daily sign-in not verified")
        s.done(obs)

    def quiz(self):
        s = self.s
        obs, _, button = s.row("庄园小课堂", reset=True)
        if re.search("领取|已完成", button.text):
            s.done(obs, already=True)
            return
        s.tap_element(obs, button, lambda o:o.page == "quiz", name="quiz-open")
        obs = s.observe("quiz-options")
        # Options are two stacked, similarly sized colored button backgrounds.
        from screen_perception.vision import quiz_options
        options = quiz_options(obs)
        index = s.config.get("quiz_option", 0)
        if len(options) != 2 or index not in (0,1):
            raise AutomationError("Cannot identify exactly two quiz options")
        s.tap_element(obs, options[index], lambda o:o.page == "quiz" and o.has("答案解析|答对|答错|回答正确|回答错误"),
                      name="quiz-answer", spend=True)
        s.back(("feed",))
        s.complete_row("庄园小课堂")

    def browse(self, title, swipe=False, optional=False, claim=False, instant=False):
        from workflow.shared import browse
        s = self.s
        obs, _, button = s.row(title, required=not optional, reset=True)
        if button is None:
            s.done(obs, skipped=True)
            return
        if re.search("领取|已完成", button.text):
            s.complete_row(title, claim=claim)
            return
        attempts = 1 if instant else s.config.get("ad_entry_attempts", 2)
        for attempt in range(attempts):
            s.tap_element(
                obs,
                button,
                lambda o:o.page in ("ad", "UNKNOWN") or "guess" in o.overlays or o.has("浏览完成"),
                name="browse-open",
            )
            if instant:
                break
            try:
                browse(s, swipe)
                break
            except AutomationError as exc:
                if exc.code != "TIMER_MISSING" or attempt + 1 >= attempts:
                    raise
                s.back(("feed",), allow_unknown=True)
                obs, _, button = s.row(title, reset=True)
                # Device evidence (2026-09-24, run 19d92f): the video really
                # completed during the timer-missed first attempt (its row
                # had flipped to 领取), but the retry tapped that claim
                # button as if it were the entry - claiming the feed and
                # then timing out waiting for an ad page. A claimable row
                # after the re-row means the browse is done: complete it
                # right here instead of tapping again.
                if re.search("领取|已完成", button.text):
                    s.complete_row(title, claim=claim)
                    return
        # Device evidence (2026-09-25, run f4b926): the ad completion view
        # auto-advances (浏览完成 -> 任务已完成/看更多视频>, which matches no ad
        # rule) within ~1s of browse() returning, so a flag computed from
        # s.obs.page reads browse's stale "ad" frame and validate() then
        # refused the fresh UNKNOWN observation ("Cannot act on unknown
        # page"). Back is non-destructive navigation and the ("feed",)
        # target guards the landing, so allow unknown unconditionally -
        # same policy as the TIMER_MISSING retry above.
        # Device evidence (2026-09-27, run e7673b): the member center sits
        # on the 支付宝会员 home, so its back lands "member" (new rule) - the
        # old ("feed",) only waited and starved on page=UNKNOWN. Accept the
        # known intermediate and replan through the canonical router; the
        # direct ad -> feed stacks (run 0a42ca) still return on this Back.
        s.back(("feed", "member"), allow_unknown=True)
        if s.obs.page != "feed":
            s.ensure("feed")
        s.complete_row(title, claim=claim)

    def lottery(self, title):
        from workflow.shared import lottery
        s = self.s
        obs, _, button = s.row(title, reset=True)
        if re.search("领取|已完成", button.text):
            s.done(obs, already=True)
            return
        s.tap_element(obs, button, lambda o:o.page == "lottery", name="lottery-open")
        lottery(s, ads=3, exchange=True)
        s.back(("feed",))
        s.complete_row(title)

    def farm(self):
        s = self.s
        # Device evidence (2026-09-24, run e2c7d1): the row's own
        # description 和小鸡一起去芭芭农场逛一逛，完成即可 embeds the full
        # title text, so the bare 芭芭农场 matched both lines and row()
        # failed closed with Ambiguous task identity. Anchor the title's
        # leading 去 - the description starts with 和 - for a single hit.
        obs, _, button = s.row("^去芭芭农场", reset=True)
        if re.search("领取|已完成", button.text):
            # The task specification defines the parent card becoming
            # claimable as the completion evidence for this daily task.
            s.done(obs, already=True)
            return
        s.tap_element(obs, button, lambda o:o.page in ("farm", "farm_tasks")
                      or o.has("^去绑定淘宝账号$"), name="farm-open")
        if s.obs.has("^去绑定淘宝账号$"):
            # Device evidence (2026-10-09, run 9282ac): the 小号's 芭芭农场
            # opens on its Taobao-binding landing page (支付宝·芭芭农场 /
            # 1分钱领一箱水果 / 去绑定淘宝账号, page UNKNOWN) instead of the
            # farm home, and it held steady for the whole 25s page timeout -
            # the old farm-open predicate failed closed and aborted the chain
            # at manor.feed.farm (frames 0221-0228). Opening the mini-program
            # still satisfies the daily browse: the next run (7ef332) read the
            # parent card as claimable (领取). Route back to the feed and let
            # the claimable check above decide, the same "claimable row after
            # the open means the browse is done" rule browse() applies.
            # Device verification pending: today's card was already claimable,
            # so this path could not be exercised a second time.
            s.ensure("feed")
            obs, _, button = s.row("^去芭芭农场", reset=True)
            if re.search("领取|已完成", button.text):
                s.done(obs, already=True)
                return
            raise AutomationError(
                "Farm opened on the Taobao binding page and its card is not claimable",
                "UNKNOWN")
        # Device evidence (2026-09-24, run ae2e4d): the farm opens behind a
        # daily offer card (headline 领1000肥料奖励, subline 浏览精选好物15s
        # 即可得, CTA 领肥料, bare × centered below the card) that covers the
        # 施肥 button - OCR found no 施肥 while it was up and vision did not
        # tag it as an overlay, so the ^施肥$ search exhausted its refreshes
        # and failed closed. Dismiss it BEFORE the farm_tasks check: the
        # spec's auto-jump to 做任务集肥料 may only fire after the card is
        # gone. The × carries no OCR text, so anchor it on the OCR'd
        # headline (frame 0017: headline [406,1638,1023,1724] center
        # (714,1681); × center (724,2400), r≈45 → headline center + (+10,+719)).
        if s.obs.has(r"领\d+肥料奖励"):
            hx, hy = s.obs.one(r"领\d+肥料奖励").point
            cx, cy = hx + 10, hy + 719
            target = Element("关闭礼遇卡", (cx - 90, cy - 90, cx + 90, cy + 90),
                             s.obs.id)
            s.tap_element(s.obs, target,
                          lambda o:o.page in ("farm", "farm_tasks")
                          and not o.has(r"领\d+肥料奖励"),
                          name="farm-offer-close")
        # Device evidence (2026-09-25, run 9d8f76): spec L67's auto-jump to
        # 做任务集肥料 lands a beat AFTER the farm home renders - the home's
        # 施肥 was OCR'd on the farm-open frame (0012), gone from 0013's
        # transition frame and the drawer was open at 0014 - so the old
        # immediate page check saw the pre-jump home and ^施肥$'s refresh
        # loop then refused to act across the page change (found 0). The
        # jump is spec-guaranteed ("页面会自动跳转至'做任务集肥料'页面"):
        # wait for it, claim the drawer rows, back out, fertilize the
        # settled home.
        s.wait(lambda o:o.page == "farm_tasks", "farm-jump")
        # Device evidence (2026-09-28, run 77dae5): the welcome card's own
        # countdown (签到领肥3s -> 1s, frames 0011/0012) auto-claims the
        # sign before the jump lands, and the drawer's sign strip then
        # renders 已领取 with no 每日签到 row at all - absent from all 34
        # drawer frames while the rest of the OCR reads clean (the strip's
        # day cells 600/600/600 plus 已领取 sit at the drawer top instead).
        # The sign claim is therefore optional; the manure row leads
        # because it is the durable one (title + 领取 paired at frames
        # 0016-0019 today), and the claim verifies by the pill itself
        # flipping - the strip's standing 已领取 would make a plain
        # has("已领取") vacuously true.
        for title in ("蚂蚁庄园小鸡肥料", "每日签到"):
            obs, _, button = s.row(title, required=False, page="farm_tasks")
            if button is None:
                continue
            if button.text == "领取":
                pill = button
                s.tap_element(obs, button,
                              lambda o, pill=pill:o.page == "farm_tasks"
                              and not any(e.text == pill.text
                                          and abs(e.point[1] - pill.point[1]) < 20
                                          for e in o.elements),
                              name="fertilizer-claim", spend=True)
        # Device evidence (2026-09-29, run 5742c4): the spec's exit from the
        # auto-jumped drawer is its top-right X (L67 点击右上角"X"关闭
        # "做任务集肥料"页面) - one Android Back from the drawer closed the
        # whole 芭芭农场 container and landed on feed (the same on 09-27, run
        # 80393d), starving back(("farm",)). The X rides the fixed drawer
        # header: 做任务集肥料 held bounds [533,1085,906,1150] across all 23
        # drawer frames today (scroll included) and the circle sits at title
        # center + (+535,-28) with r≈57 (frame 0296-507a60).
        header = s.obs.one("做任务集肥料")
        cx = int((header.bounds[0] + header.bounds[2]) / 2 + 535)
        cy = int((header.bounds[1] + header.bounds[3]) / 2 - 28)
        target = Element("关闭做任务集肥料", (cx - 60, cy - 60, cx + 60, cy + 60),
                         s.obs.id)
        s.tap_element(s.obs, target, lambda o: o.page == "farm",
                      name="drawer-close")
        if s.obs.has("点击领取"):
            s.tap("点击领取", lambda o:o.page == "farm" and not o.has("点击领取"), spend=True)
        for index in range(2):
            s.tap("^施肥$", lambda o:o.has("[立三主]即领肥|施肥挑战"), spend=True,
                  detail={"fertilization":index+1})
            if s.obs.has("施肥挑战"):
                # Device evidence (2026-10-10, run 016183): with the live
                # 限时挑战 window open (04:45 countdown, opponent matched),
                # the bottom 施肥 key is hijacked into the challenge lobby
                # (健桥(我)/随机对手/施肥0次/开始挑战, frame 0305) and the
                # lobby's Android Back pops the whole 芭芭农场 container out
                # to feed - back(("farm",)) starved on page=feed across eight
                # frames and timed out. The farm home's persistent
                # 参与施肥挑战赢大额奖励 card also satisfies the tap's
                # 施肥挑战 arm on the pre-pour frame (0304), so the branch
                # can fire before the lobby even renders; accept both
                # landings (farm home / feed) and end the fertilize section
                # on the spot - the harvest-gift steps below need a real
                # pour, and one more Back from feed would leave the manor
                # for its home.
                s.back(("farm", "feed"))
                break
            s.tap("[立三主]即领肥", lambda o:o.has("丰收礼包"))
            # Device evidence (2026-09-30, run f427d5): the claim tap finds
            # the popup already classified farm_gift, so it must ride the
            # overlay through (session.tap dismisses overlays before
            # targeting); the exit is the popup's bottom-center X (spec L67
            # 点击"X"关闭"丰收礼包"页面) - one Android Back from the claimed
            # popup left the whole 芭芭农场 container for feed and starved
            # back(("farm",)), so dismiss() taps the farm_gift circle.
            s.tap("[立三主]即领取", lambda o:not o.has("[立三主]即领取"),
                  spend=True, overlay=True)
            from workflow.recovery import dismiss

            s.obs = dismiss(s, s.obs)
        if s.obs.page != "feed":
            s.back(("feed",))
        s.complete_row("^去芭芭农场")

    def kitchen(self):
        s = self.s
        obs, _, button = s.row("小鸡厨房", reset=True)
        if re.search("领取|已完成", button.text):
            s.done(obs, already=True)
            return
        s.tap_element(obs, button, lambda o:o.page == "kitchen", name="kitchen-open")
        # Device evidence (2026-09-26, runs e480ea -> 4a78d9): e480ea's
        # claim timed out behind the pantry dialog and stayed
        # RESULT_UNKNOWN, so store.intent()'s guard rejected the retry's
        # first claim before it could fire (4a78d9 died at the intent).
        # The daily claim affordance is durable evidence of that stale
        # submission's fate: it still offering the claim proves the tap
        # never took effect (cancel), the affordance consumed proves it
        # did (verify so later spends of this task can fire) - the same
        # state-anchored reconciliation the lottery confirm got on 09-25.
        # Any other stale action keeps blocking fail-closed.
        if s.ex.store.unresolved(s.task):
            consumed = not s.obs.has("领今日食材")
            for action_id, name, before_id, run in s.ex.store.pending_frames(s.task):
                if name in ("领今日食材", "领取食材", "pantry-confirm"):
                    s.ex.store.action(action_id, "VERIFIED" if consumed else "CANCELLED",
                                      s.obs.id)
                    continue
                if name != "做美食":
                    continue
                # Device evidence (2026-09-25, runs 3496e7 -> 295962): with
                # the chickens out the 做美食 tap is refused behind a ~2s
                # toast (小鸡不在家哦，等它回来) the runner's cadence missed, so
                # the postcond starved and left RESULT_UNKNOWN that then
                # blocked every later spend of this task. The refusal proof
                # is the submission's own before frame: it records the
                # out-state bubble at tap time, so cancel on that evidence
                # even once the chickens have walked back.
                texts = _load_frame_texts(s, run, before_id)
                if texts is not None and any(
                        re.search(r"主人，我出去啦|小鸡不在家", t) for t in texts):
                    s.ex.store.action(action_id, "CANCELLED", before_id)
                    continue
                # Device evidence (2026-09-26, run 780c45): that run's cook
                # DID succeed - its own post-tap frames carry the result
                # modal (金枪鱼海苔卷制作成功 / 厨余生成了60肥料) - the postcond
                # just asked for text the device never renders. Prove the
                # submission took effect from that durable record and
                # verify it here, before the first spend trips the guard.
                # Anything else stays fail-closed: no proof, no cancel.
                proof = _load_run_proof(s, run, before_id, r"制作成功|厨余生成|查看图鉴")
                if proof is not None:
                    s.ex.store.action(action_id, "VERIFIED", proof)
        for pattern in ("领今日食材", "领取食材"):
            if s.obs.has(pattern):
                # Device evidence (2026-09-26, run e480ea): a nearly-full
                # pantry answers the claim with its own confirm dialog
                # (食材快放不下啦 / 当前仅能装下50g食材 / 确认领取今日食材吗？
                # + 确认 at [665,1814]) whose body leaves the 领今日食材
                # button OCR-visible, so the plain not-has postcondition
                # starved until timeout. Accept the dialog as the claim
                # proceeding, then anchor its own ^确认$ - the body also
                # carries 确认 (run e5bb6b failed that unanchored) - just
                # like the sign near-full confirm; the frame still
                # classifies kitchen behind the dialog, so no allow_unknown.
                s.tap(pattern,
                      lambda o,p=pattern:o.page == "kitchen"
                      and (not o.has(p) or o.has("快放不下|确认领取")),
                      spend=True)
                if s.obs.has("快放不下|确认领取"):
                    s.tap(r"^确认$",
                          lambda o:o.page == "kitchen"
                          and not o.has("快放不下|确认领取"),
                          spend=True, name="pantry-confirm")
        s.tap("爱心食材店", lambda o:o.page == "ingredient_shop")
        # Same affordance-anchored reconciliation for the shop claim: a
        # stale 领10g食材 submission is cancelled while the shop still
        # offers the claim and verified once the affordance is consumed -
        # otherwise it deadlocks the task's later spends with no resolver
        # before done().
        if s.ex.store.unresolved(s.task):
            consumed = not s.obs.has("领10g食材")
            for action_id, name, _, _ in s.ex.store.pending_frames(s.task):
                if name == "领10g食材":
                    s.ex.store.action(action_id, "VERIFIED" if consumed else "CANCELLED",
                                      s.obs.id)
        shop_refused = False
        if s.obs.has("领10g食材"):
            # The shop claim can meet the same near-full dialog family -
            # or, with the bag at its 300g cap, a refusal toast
            # (2026-09-26, run 6bafea: 食材袋放不下了，使用后再领取吧,
            # OCR-split but anchored on 食材袋放不下) that overlays the
            # still-OCR-visible button. Both are answers: accept them as
            # the submission resolved instead of starving for not-has.
            s.tap("领10g食材",
                  lambda o:not o.has("领10g食材")
                  or o.has("快放不下|确认领取|食材袋放不下"),
                  spend=True)
            if s.obs.has("快放不下|确认领取"):
                s.tap(r"^确认$",
                      lambda o:not o.has("快放不下|确认领取"),
                      spend=True, name="pantry-confirm")
            elif s.obs.has("食材袋放不下"):
                # The toast advises using ingredients first - the cooks
                # below free bag space, so take one claim retry after
                # them rather than losing the daily 10g.
                shop_refused = True
        s.back(("kitchen",))
        # The stale 做美食 pendings resolved at entry; the live out-state
        # bubble (kitchen 主人，我出去啦) only skips the cook - never tap
        # into a refusal the app will just reject again.
        if s.obs.has("主人，我出去啦|小鸡不在家"):
            s.done(s.obs, skipped=True)
            return
        for index in range(2):
            if s.obs.page != "kitchen":
                # Device evidence (2026-09-28, run b2acc0): one Back from
                # the cook result left the whole kitchen H5 for the feed
                # (0029 modal still up -> 0030 page=feed), so the
                # modal-only predicate below starved on the very landing
                # it produced. The next cook re-enters through the feed
                # row exactly like the task entry, and a row already
                # claimable or done ends the loop - nothing left to cook.
                obs, _, button = s.row("小鸡厨房", reset=True)
                if re.search("领取|已完成", button.text):
                    break
                s.tap_element(obs, button, lambda o:o.page == "kitchen",
                              name="kitchen-reopen")
            # Device evidence (2026-09-26, run 780c45): the device never
            # renders the spec's 美食图鉴 gallery - the tap cooks directly
            # and answers with a result modal (金枪鱼海苔卷制作成功 +
            # 查看图鉴 + 厨余生成了60肥料, frame 0031). Accept either
            # outcome as the cook's proof.
            s.tap("做美食",
                  lambda o:o.has("美食图鉴") or o.has("制作成功|厨余生成|查看图鉴"),
                  spend=True, detail={"meal":index+1})
            # The modal must actually go before the next tap: its frame
            # can classify kitchen with no 美食图鉴 text, which the old
            # predicate accepted without pressing back - leaving the
            # modal up to swallow the following tap. The landing is
            # kitchen (modal closed in place) or the feed (the H5 exited
            # whole - device 2026-09-28); either ends the dismissal.
            s.back(lambda o:o.page in ("kitchen", "feed")
                   and not o.has("美食图鉴|制作成功|厨余生成|查看图鉴"))
        if shop_refused:
            # The bag-full refusal (above) deferred the free 10g claim
            # until ingredients were used; the cooks just used some, so
            # honor the toast's own advice with a single claim retry.
            # A second refusal is equally an answer - accept and move on.
            s.tap("爱心食材店", lambda o:o.page == "ingredient_shop")
            if s.obs.has("领10g食材"):
                s.tap("领10g食材",
                      lambda o:not o.has("领10g食材")
                      or o.has("快放不下|确认领取|食材袋放不下"),
                      spend=True)
                if s.obs.has("快放不下|确认领取"):
                    s.tap(r"^确认$",
                          lambda o:not o.has("快放不下|确认领取"),
                          spend=True, name="pantry-confirm")
            s.back(("kitchen",))
        if s.obs.page != "feed":
            # Device evidence (2026-09-28, run b2acc0): the cook dismissal
            # can already leave the H5 on the feed - pressing Back again on
            # a satisfied target would exit the whole app instead.
            s.back(("feed",))
        s.complete_row("小鸡厨房")
