from __future__ import annotations

import re
import time

from domain_data import AutomationError, Element
from screen_perception.query import ElementQuery, find_elements

# Real-device evidence (2026-09-23) and demo video 01:08: the forest
# lottery's 每日签到 card exposes an exact "签到" button (its signed state
# "已签到" must still resolve as the row button so re-visits skip cleanly).
# Anchored so the card title 每日签到 itself never matches the button query.
TASK_BUTTON = ("去完成|去答题|去逛逛|去捐蛋|去请客|去喂食|领取|明天再来|"
               "已完成|已领取|点后|^签到$|^已签到$")


class Session:
    def __init__(self, executor, config):
        self.ex = executor
        self.config = config
        self.task = "navigation"
        self.obs = None
        self.ex.interruption_handler = self._recover_interruption

    def _recover_interruption(self, observation):
        from workflow.recovery import dismiss

        return dismiss(self, observation)

    def observe(self, reason="observe"):
        self.obs = self.ex.observer.capture(reason)
        self.ex.budget.check()
        return self.obs

    def wait(self, predicate, reason="wait", timeout=None):
        self.obs = self.ex.wait(predicate, timeout or self.config.get("page_timeout", 25), reason)
        return self.obs

    def tap(self, pattern, predicate, *, region=(0,0,1,1), spend=False, detail=None,
            overlay=False, allow_unknown=False, name=None, recover=True):
        obs = self.observe("before-" + (name or pattern))
        if obs.overlays and not overlay:
            from workflow.recovery import dismiss

            obs = dismiss(self, obs)
        matches = obs.find(pattern, region)
        for _ in range(2):
            if matches:
                break
            page = obs.page
            obs = self.observe("refresh-missing-" + (name or pattern))
            if obs.page != page or obs.overlays:
                break
            matches = obs.find(pattern, region)
        if len(matches) != 1:
            raise AutomationError(
                f"Expected unique target {pattern}: found {len(matches)}", "AMBIGUOUS"
            )
        element = matches[0]
        try:
            self.obs = self.ex.tap(obs, element, predicate, name or pattern, self.task,
                                  irreversible=spend, detail=detail, allow_overlay=overlay,
                                  allow_unknown=allow_unknown, recover=recover)
        except AutomationError as exc:
            # Device evidence (2026-09-23): OCR grouped the summary page's
            # animated chevron into 去抽奖>, so the pixel guard saw the
            # button change between capture and tap - re-find the pattern on
            # a fresh frame like tap_element does instead of failing the
            # whole task on a target that merely moved.
            if exc.code != "STALE":
                raise
            fresh = self.observe("refresh-stale-" + (name or pattern))
            if fresh.page != obs.page or fresh.overlays != obs.overlays:
                raise AutomationError("Page changed while refreshing stale target",
                                      "STALE") from exc
            candidates = fresh.find(pattern, region)
            if not candidates:
                raise
            replacement = min(
                candidates,
                key=lambda item: (item.point[0] - element.point[0]) ** 2
                + (item.point[1] - element.point[1]) ** 2,
            )
            distance = ((replacement.point[0] - element.point[0]) ** 2
                        + (replacement.point[1] - element.point[1]) ** 2) ** .5
            if distance > max(fresh.width, fresh.height) * .1:
                raise AutomationError("Stale target moved too far", "STALE") from exc
            # The OCR re-find above already verified text and position on a
            # fresh frame, so skip the pixel diff - animated CTAs (device
            # 2026-09-24: the lottery result close button, crop diff 39.3
            # against a 28 threshold) would fail it twice in a row.
            self.obs = self.ex.tap(
                fresh, replacement, predicate, name or pattern, self.task,
                irreversible=spend, detail=detail, allow_overlay=overlay,
                allow_unknown=allow_unknown, recover=recover, pixel_guard=False,
            )
        return self.obs

    def tap_element(self, obs, element, predicate, *, name, spend=False, detail=None,
                    overlay=False, allow_unknown=False, recover=True):
        try:
            self.obs = self.ex.tap(obs, element, predicate, name, self.task,
                                  irreversible=spend, detail=detail, allow_overlay=overlay,
                                  allow_unknown=allow_unknown, recover=recover)
        except AutomationError as exc:
            if exc.code != "STALE":
                raise
            fresh = self.observe("refresh-stale-" + name)
            if fresh.page != obs.page or fresh.overlays != obs.overlays:
                raise AutomationError("Page changed while refreshing stale target", "STALE") from exc
            candidates = [item for item in fresh.elements if item.text == element.text]
            if not candidates:
                raise
            replacement = min(
                candidates,
                key=lambda item: (item.point[0] - element.point[0]) ** 2
                + (item.point[1] - element.point[1]) ** 2,
            )
            distance = ((replacement.point[0] - element.point[0]) ** 2
                        + (replacement.point[1] - element.point[1]) ** 2) ** .5
            if distance > max(fresh.width, fresh.height) * .1:
                raise AutomationError("Stale target moved too far", "STALE") from exc
            # Fresh OCR re-find just verified text and position; skip the
            # pixel diff for animated CTAs (device 2026-09-24, see tap()).
            self.obs = self.ex.tap(
                fresh, replacement, predicate, name, self.task,
                irreversible=spend, detail=detail, allow_overlay=overlay,
                allow_unknown=allow_unknown, recover=recover, pixel_guard=False,
            )
        return self.obs

    def back(self, target, allow_unknown=False):
        obs = self.observe("before-back")
        return self.back_observation(obs, target, allow_unknown=allow_unknown)

    def back_observation(self, obs, target, allow_unknown=False, recover=True):
        predicate = (lambda o: o.page in target) if not callable(target) else target
        self.obs = self.ex.back(obs, predicate, "return", allow_unknown, recover=recover)
        return self.obs

    def scroll(self, region=(.5,.72,.5,.48), *, target=None, allow_unknown=False,
               obs=None):
        # Device cadence (2026-09-23): a fresh capture costs ~3-4s of
        # screenshot+OCR. Swipes validate without an element box, so a
        # caller's previous frame can serve as the before-frame while it is
        # inside the 12s freshness window. An expired frame is recaptured
        # here because validate() would only reject it mid-swipe; the 10s
        # margin leaves room for validate()'s own foreground() round-trip.
        if obs is None or time.monotonic() - obs.captured > 10:
            obs = self.observe("before-scroll")
        self.obs = self.ex.swipe(obs, region, target, allow_unknown=allow_unknown)
        return self.obs

    @staticmethod
    def same_view(before, after):
        """Compare stable OCR layout while ignoring status/navigation bars."""
        if before.page != after.page:
            return False

        def signature(obs):
            return tuple(sorted(
                (e.text, round(e.point[0] / max(obs.width, 1), 2),
                 round(e.point[1] / max(obs.height, 1), 2))
                for e in obs.elements
                if .08 <= e.point[1] / max(obs.height, 1) <= .94
            ))

        return signature(before) == signature(after)

    def done(self, obs=None, already=False, skipped=False):
        obs = obs or self.obs
        if obs is None:
            raise AutomationError("Missing task completion evidence")
        status = "SKIPPED" if skipped else "ALREADY_DONE" if already else "SUCCESS"
        self.ex.store.task(self.task, status, {"observation": obs.id, "page": obs.page,
                                               "text": [e.text for e in obs.elements]})
        if not skipped:
            self.ex.store.reconcile(self.task, obs.id)

    def ensure(self, target):
        obs = self.observe("entry")
        if obs.page == target and not obs.overlays:
            return obs
        if obs.package != self.config["package"]:
            self.ex.device.launch(self.config["package"])
            obs = self.wait(lambda o: o.page != "UNKNOWN", "launch")
        elif obs.page == "UNKNOWN":
            # The package already matches, but one glitchy OCR frame must not
            # abort navigation before the screen is recognized at all.
            try:
                obs = self.wait(lambda o: o.page != "UNKNOWN", "recognize", timeout=8)
            except AutomationError:
                # Device evidence (2026-09-23): the deck's 支付宝会员签到
                # promo card classifies UNKNOWN and holds steady, so the
                # wait can never resolve it; fall through to the routing
                # loop, whose Back branch navigates out instead.
                pass
        if obs.overlays:
            from workflow.recovery import dismiss
            obs = dismiss(self)
        parents = {"diary": "manor", "feed": "alipay", "family": "manor",
                   "manor_friend": "manor",
                   "family_tasks": "manor", "quiz": "feed", "kitchen": "feed",
                   "farm": "feed", "farm_tasks": "farm", "ingredient_shop": "kitchen",
                   "donate_success": "donate_detail", "donate_quantity": "donate_detail",
                   "donate_detail": "donate_projects",
                   "donate_projects": "manor", "manor": "alipay", "forest": "alipay",
                   "love": "forest", "cooperate": "forest", "rain": "forest",
                   # Real-device evidence (2026-09-23): interrupted runs left
                   # the screen on a friend forest and on the lottery page;
                   # Back is the only route out of these detour pages (the
                   # lottery exits to the treasure ad, then to the forest).
                   # The energy summary page also opens from the forest
                   # home (device probe 2026-09-23), so Back covers it too.
                   "forest_friend": "forest", "treasure": "forest",
                   "forest_summary": "forest", "lottery": "treasure",
                   # Device evidence (2026-09-23, run 105813): a crashed
                   # ad-browse left the entry on the market ad page after
                   # its guess modal was dismissed; Back is the only route
                   # out (proven by every completed ad run, which backs to
                   # the lottery), and the accepted-any-landing replan
                   # covers stacks opened from the manor feed instead.
                   "ad": "lottery",
                   # Device evidence (2026-09-27, run e7673b): the member
                   # task center sits under the 支付宝会员 home, so an
                   # interrupted browse leaves the entry on that home (now
                   # classifiable, its promo layer included); Back walks it
                   # out to the feed that opened it.
                   "member": "feed"}
        for _ in range(8):
            if obs.page == target and not obs.overlays:
                return obs
            if obs.page == "UNKNOWN":
                # Device evidence (2026-09-23): the deck's 支付宝会员签到
                # promo card classifies UNKNOWN and holds steady, so the
                # entry recognize-wait cannot resolve it; Back is the only
                # generic route out (its own refresh pass handles any
                # transition frame it lands on).
                obs = self.back(lambda o: o.page != "UNKNOWN",
                                allow_unknown=True)
                continue
            route = {
                ("alipay", "manor"): ("^蚂蚁庄园$", "manor"),
                ("alipay", "forest"): ("^蚂蚁森林$", "forest"),
                ("manor", "feed"): ("^领饲料$", "feed"),
                ("manor", "diary"): ("小鸡日记|^日记$", "diary"),
                ("manor", "family"): ("^家庭$", "family"),
                ("manor", "family_tasks"): ("^家庭$", "family"),
                ("family", "family_tasks"): ("[立三主]即签到|^攒亲密度$", "family_tasks"),
                # Device evidence (2026-09-23): with every friend harvested,
                # 找能量 opens the energy summary page; its 返回森林首页
                # button is the deterministic route home (Back would depend
                # on where the stack was left).
                ("forest_summary", "forest"): ("返回森林首页", "forest"),
            }
            if (obs.page, target) in route:
                pattern, destination = route[obs.page, target]
                obs = self.tap(pattern, lambda o, destination=destination: o.page == destination)
            elif obs.page == "alipay":
                group = "forest" if target in ("forest", "love", "cooperate", "rain") else "manor"
                pattern = "^蚂蚁森林$" if group == "forest" else "^蚂蚁庄园$"
                obs = self.tap(pattern, lambda o, group=group: o.page == group)
            elif obs.page in parents:
                # The page reached by Back depends on the app's live activity
                # stack (family_tasks has landed on manor, feed on alipay), so
                # the configured parent is only a hint. Accept any newly
                # recognized page and re-plan the route from observed reality.
                start = obs.page
                # Device evidence (2026-09-28, run d1da54): the donation's
                # follow-up Back re-observed the detail page mid-re-render
                # as UNKNOWN (0022 donate_detail -> 0023 UNKNOWN) and the
                # validator refused to press at all. Back is
                # non-destructive navigation and the predicate guards the
                # landing (it still excludes UNKNOWN), so a transient
                # departure frame is pressable - the same stance as the
                # UNKNOWN branch above.
                obs = self.back(
                    lambda o, start=start: o.page != start and o.page != "UNKNOWN",
                    allow_unknown=True
                )
            else:
                raise AutomationError(f"No verified navigation from {obs.page} to {target}", "UNKNOWN")
        raise AutomationError(f"Navigation budget exhausted for {target}", "TIMEOUT")

    def row(self, title, required=True, reset=False, page="feed"):
        obs = self.ensure(page)
        if reset:
            no_progress = 0
            for _ in range(self.config.get("max_reset_scrolls", 8)):
                before = obs
                obs = self.scroll((.5,.4,.5,.82), obs=obs)
                if obs.has("^签到$|庄园小课堂|每日捐蛋"):
                    break
                no_progress = no_progress + 1 if self.same_view(before, obs) else 0
                if no_progress >= 2:
                    break
        no_progress = 0
        for _ in range(self.config.get("max_scrolls", 16)):
            titles = obs.find(title)
            if len(titles) > 1:
                raise AutomationError(f"Ambiguous task identity {title}", "AMBIGUOUS")
            if titles:
                anchor = titles[0]
                buttons = find_elements(obs, ElementQuery(TASK_BUTTON, card_title=title))
                if len(buttons) == 1:
                    return obs, anchor, buttons[0]
                if re.search("[（(]1/1[）)]", anchor.text):
                    return obs, anchor, anchor
                # Device evidence (2026-09-25, run e22b56): the sesame row
                # first rendered at y3103 of the 3200px screen, its pill
                # column past the fold (only the x60g chip drew at
                # y3100-3172), so the no-scroll refresh retries below
                # never exposed a button and complete_row rejected the
                # synthetic column fallback with "Task completion not
                # verified". A failed pairing on a title inside the bottom
                # fold means the pill is off-screen: lift the list once
                # and pair again on the raised frame.
                if anchor.point[1] > obs.height * .93:
                    obs = self.scroll(obs=obs)
                    titles = obs.find(title)
                    if len(titles) > 1:
                        raise AutomationError(f"Ambiguous task identity {title}", "AMBIGUOUS")
                    if titles:
                        anchor = titles[0]
                        buttons = find_elements(obs, ElementQuery(TASK_BUTTON, card_title=title))
                        if len(buttons) == 1:
                            return obs, anchor, buttons[0]
                        if re.search("[（(]1/1[）)]", anchor.text):
                            return obs, anchor, anchor
                # Device evidence (2026-09-23): the first frame after the
                # lottery side switch still had the market row's title
                # drawn but not its 去逛逛 button, and pairing once on a
                # mid-render capture failed the whole friends task; give the
                # panel fresh frames before declaring the row unusable.
                for _ in range(3):
                    time.sleep(1.5)
                    obs = self.observe("row-refresh")
                    fresh = obs.find(title)
                    if not fresh:
                        continue
                    anchor = fresh[0]
                    buttons = find_elements(obs, ElementQuery(TASK_BUTTON, card_title=title))
                    if len(buttons) == 1:
                        return obs, anchor, buttons[0]
                    if re.search("[（(]1/1[）)]", anchor.text):
                        return obs, anchor, anchor
                # Device evidence (2026-09-23): the forest lottery's market
                # row button stayed visible in every frame yet OCR returned
                # nothing for it across five captures (its identical twins
                # on the rows below were read fine), so a zero-button
                # pairing falls back to the right-aligned button column
                # those twins pin down - text center x within .77-.94 of the
                # width, center 35px below the title's. An ambiguous
                # (two-or-more) pairing still fails closed.
                present = obs.find(title)
                if present and not find_elements(
                        obs, ElementQuery(TASK_BUTTON, card_title=title)):
                    anchor = present[0]
                    column = int(obs.width * .77), int(obs.width * .94)
                    slot = anchor.point[1] + 35
                    return (obs, anchor,
                            Element(f"{anchor.text} [button-column]",
                                    (column[0], slot - 30, column[1], slot + 30),
                                    obs.id))
                raise AutomationError(f"No unambiguous button for {title}", "UNKNOWN")
            # Device evidence (2026-09-25, run 7a53ce): the feed list's
            # tail now reads 完成任务后会获赠饲料，超过当天24点未领取会
            # 消失哦 - pinned from frame 0032 until the budget died at
            # 0040 - while the demo-era end markers never appeared, so an
            # absent optional row (去蚂蚁森林逛一逛 really was not
            # assigned that day) burned the whole scan and failed instead
            # of skipping. The footer renders once, after the last row,
            # so it closes the scan like its siblings.
            if obs.has("没有更多|已到底|全部任务已展示"
                       "|完成任务后会获赠饲料"):
                if not required:
                    return obs, None, None
                raise AutomationError(f"Required task missing: {title}")
            before = obs
            obs = self.scroll(obs=obs)
            no_progress = no_progress + 1 if self.same_view(before, obs) else 0
            if no_progress >= 2:
                if not required:
                    return obs, None, None
                raise AutomationError(f"Required task missing after complete scan: {title}")
        # Device evidence (2026-09-28, run 77dae5): the farm drawer's
        # rotating campaign banner rewrites the frame signature on every
        # capture, so no_progress never reaches 2 and the scroll budget
        # dies on the loop head with the row genuinely absent - the same
        # "not there" verdict as the two confirmed paths above, which
        # already let an optional row skip.
        if not required:
            return obs, None, None
        raise AutomationError(f"Cannot confirm complete scan for {title}", "UNKNOWN")

    def complete_row(self, title, page="feed", claim=False):
        obs, _, button = self.row(title, reset=True, page=page)
        # Device evidence (2026-09-24, run ed9ed9): with the donation row
        # parked at the list bottom, OCR returned only the done title
        # 每日捐蛋做好事(1/1) and no side button; row() legitimately falls
        # back to that title as its button (its own (1/1) check guarantees
        # the marker), so the counter must count as completion evidence.
        if not re.search("领取|明天再来|已完成|已领取|点后|[（(]1/1[）)]", button.text):
            raise AutomationError(f"Task completion not verified: {title}")
        if claim and button.text == "领取":
            before = button
            obs = self.tap_element(obs, button,
                                   lambda o: o.page == page and not any(
                                       e.text == before.text and abs(e.point[1]-before.point[1]) < 20
                                       for e in o.elements), name="required-reward", spend=True)
        self.done(obs)
        return obs
