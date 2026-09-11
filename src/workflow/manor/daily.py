from __future__ import annotations

import re

from domain_data import AutomationError


class Manor:
    def __init__(self, session):
        self.s = session

    def reward_friends(self):
        s = self.s
        obs = s.ensure("manor")
        for _ in range(30):
            matches = obs.find("^打赏$", (0,.55,.55,.9))
            if not matches:
                confirmed = s.observe("reward-absence-confirm")
                if confirmed.page != "manor" or confirmed.overlays or confirmed.has("^打赏$", (0,.55,.55,.9)):
                    obs = confirmed
                    continue
                s.done(confirmed, skipped=True)
                return
            element = obs.one("^打赏$", (0,.55,.55,.9))
            before = tuple(e.text for e in obs.find(".", (0,.55,.55,.9)))
            obs = s.tap_element(obs, element, lambda o: o.page == "manor" and tuple(
                e.text for e in o.find(".", (0,.55,.55,.9))) != before,
                name="reward-friend", spend=True)
        raise AutomationError("Reward loop exhausted without completion")

    def bring_home(self):
        s = self.s
        obs = s.ensure("manor")
        if not obs.has("马上去找|小鸡外出"):
            confirmed = s.observe("home-confirm")
            if confirmed.page != "manor" or confirmed.overlays or confirmed.has("马上去找|小鸡外出"):
                raise AutomationError("Cannot confirm chicken home")
            s.done(confirmed, skipped=True)
            return
        s.tap("马上去找", lambda o: o.page == "manor_friend")
        s.tap("带小鸡回家|带小鸡回家", lambda o: o.page == "manor" and not o.has("马上去找|小鸡外出"))
        s.done()

    def diary(self):
        s = self.s
        obs = s.ensure("diary")
        if obs.has("明日再来"):
            s.done(obs, already=True)
        else:
            s.tap("^贴贴小鸡$", lambda o: o.page == "diary" and o.has("明日再来"), spend=True)
            s.done()
        s.back(("manor",))

    def family_donate(self):
        s = self.s
        obs, title, button = s.row("每日捐蛋|捐蛋做好事", page="family_tasks")
        if "明天再来" in button.text or re.search(r"[（(]1/1[）)]", title.text):
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
        s.tap("^立即捐蛋$", lambda o:o.page == "donate_quantity")
        obs = s.observe("donation-quantity")
        if not obs.has("^1$|^1颗$", (0,.5,1,1)):
            raise AutomationError("Donation quantity is not verified as one", "QUANTITY")
        s.tap("^立即捐蛋$", lambda o:o.page == "donate_success", region=(0,.7,1,1),
              spend=True, detail={"eggs":1})
        s.back(("donate_detail",))
        s.back(("donate_projects",))
        s.back(("family", "family_tasks"))
        s.complete_row("每日捐蛋|捐蛋做好事", page="family_tasks")

    def family_action(self, kind):
        s = self.s
        title_pattern = "请家人.*美食|请家人吃" if kind == "meal" else "帮家人喂"
        obs, title, button = s.row(title_pattern, page="family_tasks")
        if re.search("明天再来|点后|已完成", button.text) or re.search(r"[（(]1/1[）)]", title.text):
            s.done(obs, already=True)
            return
        prompt = "选择美食" if kind == "meal" else "确认喂食"
        s.tap_element(obs, button, lambda o:o.has(prompt), name="family-"+kind)
        s.tap("^确认$", lambda o:o.page == "family_tasks" and not o.has(prompt),
              overlay=True, spend=True)
        s.complete_row(title_pattern, page="family_tasks")

    def sign(self):
        s = self.s
        obs, _, button = s.row("^签到$|^每日签到$", reset=True)
        if button.text == "已领取":
            s.done(obs, already=True)
            return
        s.tap_element(obs, button, lambda o:o.has("已领取") or "overflow" in o.overlays,
                      name="daily-sign")
        if "overflow" in s.obs.overlays:
            s.tap("确认|继续领取", lambda o:o.page == "feed" and not o.overlays,
                  overlay=True, spend=True)
        obs, _, button = s.row("^签到$|^每日签到$", reset=True)
        if button.text != "已领取":
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
        s.tap_element(obs, button, lambda o:o.page != "feed" or o.has("浏览完成"), name="browse-open")
        if not instant:
            browse(s, swipe)
        s.back(("feed",), allow_unknown=instant)
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
        obs, _, button = s.row("芭芭农场", reset=True)
        if re.search("领取|已完成", button.text):
            # Parent completion does not prove the fertilizer work was done.
            raise AutomationError("Farm parent complete; fertilizer subtasks need independent evidence", "RESULT_UNKNOWN")
        s.tap_element(obs, button, lambda o:o.page in ("farm", "farm_tasks"), name="farm-open")
        if s.obs.page == "farm_tasks":
            for title in ("每日签到", "蚂蚁庄园小鸡肥料"):
                obs, _, button = s.row(title, page="farm_tasks")
                if button.text == "领取":
                    s.tap_element(obs, button, lambda o:o.page == "farm_tasks" and o.has("已领取"),
                                  name="fertilizer-claim", spend=True)
            s.back(("farm",))
        if s.obs.has("点击领取"):
            s.tap("点击领取", lambda o:o.page == "farm" and not o.has("点击领取"), spend=True)
        for index in range(2):
            s.tap("^施肥$", lambda o:o.has("立即领肥|施肥挑战"), spend=True,
                  detail={"fertilization":index+1})
            if s.obs.has("施肥挑战"):
                s.back(("farm",))
            s.tap("立即领肥", lambda o:o.has("丰收礼包"))
            s.tap("立即领取", lambda o:not o.has("立即领取"), spend=True)
            s.back(("farm",))
        s.back(("feed",))
        s.complete_row("芭芭农场")

    def kitchen(self):
        s = self.s
        obs, _, button = s.row("小鸡厨房", reset=True)
        if re.search("领取|已完成", button.text):
            raise AutomationError("Kitchen parent complete; two meals require independent evidence", "RESULT_UNKNOWN")
        s.tap_element(obs, button, lambda o:o.page == "kitchen", name="kitchen-open")
        for pattern in ("领今日食材", "领取食材"):
            if s.obs.has(pattern):
                s.tap(pattern, lambda o,p=pattern:o.page == "kitchen" and not o.has(p), spend=True)
        s.tap("爱心食材店", lambda o:o.page == "ingredient_shop")
        if s.obs.has("领10g食材"):
            s.tap("领10g食材", lambda o:not o.has("领10g食材"), spend=True)
        s.back(("kitchen",))
        for index in range(2):
            s.tap("做美食", lambda o:o.has("美食图鉴"), spend=True, detail={"meal":index+1})
            s.back(lambda o:o.page == "kitchen" and not o.has("美食图鉴"))
        s.back(("feed",))
        s.complete_row("小鸡厨房")
