from __future__ import annotations

import re

from domain_data import AutomationError


class Session:
    def __init__(self, executor, config):
        self.ex = executor
        self.config = config
        self.task = "navigation"
        self.obs = None

    def observe(self, reason="observe"):
        self.obs = self.ex.observer.capture(reason)
        self.ex.budget.check()
        return self.obs

    def wait(self, predicate, reason="wait", timeout=None):
        self.obs = self.ex.wait(predicate, timeout or self.config.get("page_timeout", 25), reason)
        return self.obs

    def tap(self, pattern, predicate, *, region=(0,0,1,1), spend=False, detail=None,
            overlay=False, name=None):
        obs = self.observe("before-" + (name or pattern))
        element = obs.one(pattern, region)
        self.obs = self.ex.tap(obs, element, predicate, name or pattern, self.task,
                              irreversible=spend, detail=detail, allow_overlay=overlay)
        return self.obs

    def tap_element(self, obs, element, predicate, *, name, spend=False, detail=None):
        self.obs = self.ex.tap(obs, element, predicate, name, self.task,
                              irreversible=spend, detail=detail)
        return self.obs

    def back(self, target, allow_unknown=False):
        obs = self.observe("before-back")
        predicate = (lambda o: o.page in target) if not callable(target) else target
        self.obs = self.ex.back(obs, predicate, "return", allow_unknown)
        return self.obs

    def scroll(self, region=(.5,.78,.5,.35)):
        obs = self.observe("before-scroll")
        self.obs = self.ex.swipe(obs, region)
        return self.obs

    def done(self, obs=None, already=False, skipped=False):
        obs = obs or self.obs
        if obs is None:
            raise AutomationError("Missing task completion evidence")
        status = "SKIPPED" if skipped else "ALREADY_DONE" if already else "SUCCESS"
        self.ex.store.task(self.task, status, dict(observation=obs.id, page=obs.page,
                                                 text=[e.text for e in obs.elements]))
        if not skipped:
            self.ex.store.reconcile(self.task, obs.id)

    def ensure(self, target):
        obs = self.observe("entry")
        if obs.page == target and not obs.overlays:
            return obs
        if obs.package != self.config["package"]:
            self.ex.device.launch(self.config["package"])
            obs = self.wait(lambda o: o.page != "UNKNOWN", "launch")
        if obs.overlays:
            from workflow.recovery import dismiss
            obs = dismiss(self)
        parents = {"diary": "manor", "feed": "manor", "family": "manor",
                   "family_tasks": "family", "quiz": "feed", "kitchen": "feed",
                   "farm": "feed", "farm_tasks": "farm", "ingredient_shop": "kitchen",
                   "donate_success": "donate_detail", "donate_detail": "donate_projects",
                   "donate_projects": "family", "manor": "alipay", "forest": "alipay",
                   "love": "forest", "cooperate": "forest", "rain": "forest"}
        for _ in range(8):
            if obs.page == target and not obs.overlays:
                return obs
            route = {
                ("alipay", "manor"): ("^蚂蚁庄园$", "manor"),
                ("alipay", "forest"): ("^蚂蚁森林$", "forest"),
                ("manor", "feed"): ("^领饲料$", "feed"),
                ("manor", "diary"): ("小鸡日记|^日记$", "diary"),
                ("manor", "family"): ("^家庭$", "family"),
                ("manor", "family_tasks"): ("^家庭$", "family"),
                ("family", "family_tasks"): ("立即签到|攒亲密度", "family_tasks"),
            }
            if (obs.page, target) in route:
                pattern, destination = route[obs.page, target]
                obs = self.tap(pattern, lambda o: o.page == destination)
            elif obs.page == "alipay":
                group = "forest" if target in ("forest", "love", "cooperate", "rain") else "manor"
                pattern = "^蚂蚁森林$" if group == "forest" else "^蚂蚁庄园$"
                obs = self.tap(pattern, lambda o: o.page == group)
            elif obs.page in parents:
                parent = parents[obs.page]
                obs = self.back((parent,))
            else:
                raise AutomationError(f"No verified navigation from {obs.page} to {target}", "UNKNOWN")
        raise AutomationError(f"Navigation budget exhausted for {target}", "TIMEOUT")

    def row(self, title, required=True, reset=False, page="feed"):
        obs = self.ensure(page)
        if reset:
            for _ in range(3):
                obs = self.scroll((.5,.4,.5,.82))
                if obs.has("^签到$|庄园小课堂|每日捐蛋"):
                    break
        for _ in range(self.config.get("max_scrolls", 16)):
            titles = obs.find(title)
            if len(titles) > 1:
                raise AutomationError(f"Ambiguous task identity {title}", "AMBIGUOUS")
            if titles:
                anchor = titles[0]
                x, y = anchor.point
                buttons = [e for e in obs.elements if e.point[0] > x
                           and abs(e.point[1] - y) < obs.height*.035
                           and re.search("去完成|去答题|去逛逛|去捐蛋|去请客|去喂食|领取|明天再来|已完成|已领取|点后", e.text)]
                if len(buttons) == 1:
                    return obs, anchor, buttons[0]
                if re.search("[（(]1/1[）)]", anchor.text):
                    return obs, anchor, anchor
                raise AutomationError(f"No unambiguous button for {title}", "UNKNOWN")
            if obs.has("没有更多|已到底|全部任务已展示"):
                if not required:
                    return obs, None, None
                raise AutomationError(f"Required task missing: {title}")
            obs = self.scroll()
        raise AutomationError(f"Cannot confirm complete scan for {title}", "UNKNOWN")

    def complete_row(self, title, page="feed", claim=False):
        obs, _, button = self.row(title, reset=True, page=page)
        if not re.search("领取|明天再来|已完成|已领取|点后", button.text):
            raise AutomationError(f"Task completion not verified: {title}")
        if claim and button.text == "领取":
            before = button
            obs = self.tap_element(obs, button,
                                   lambda o: o.page == page and not any(
                                       e.text == before.text and abs(e.point[1]-before.point[1]) < 20
                                       for e in o.elements), name="required-reward", spend=True)
        self.done(obs)
        return obs
