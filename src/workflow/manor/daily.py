from __future__ import annotations

from domain_data import DetectedScreen, Page, StepStatus
from runtime.errors import AutomationError
from web_search import QuizSolver
from workflow.session import WorkflowSession
from workflow.shared import ExternalTaskRunner, LotteryRunner


class ManorWorkflow:
    def __init__(self, session: WorkflowSession):
        self.session = session
        self.external = ExternalTaskRunner(session)
        self.lottery = LotteryRunner(session)
        self.quiz = QuizSolver(session.config.quiz)

    def run(self, alipay_home: DetectedScreen) -> DetectedScreen:
        manor = self.session.tap(alipay_home, "manor", "manor-open", (Page.MANOR_HOME,))
        manor = self._home_tasks(manor)
        manor = self._family_tasks(manor)
        manor = self._feed_tasks(manor)
        self.session.add_step("manor", StepStatus.SUCCESS, "single pass completed")
        return manor

    def _home_tasks(self, manor: DetectedScreen) -> DetectedScreen:
        rewarded = 0
        while manor.element("reward_friend") and rewarded < 10:
            manor = self.session.tap(manor, "reward_friend", f"manor-reward-friend-{rewarded + 1}")
            rewarded += 1
        self.session.add_step(
            "manor.reward_friends",
            StepStatus.SUCCESS if rewarded else StepStatus.NOT_AVAILABLE,
            f"rewarded {rewarded}",
        )
        if manor.element("find_chicken"):
            friend = self.session.tap(manor, "find_chicken", "manor-find-chicken")
            if friend.element("bring_home"):
                manor = self.session.tap(friend, "bring_home", "manor-bring-chicken-home", (Page.MANOR_HOME,))
            else:
                raise AutomationError("Chicken location opened without a bring-home target")
            self.session.add_step("manor.bring_chicken_home", StepStatus.SUCCESS)
        else:
            self.session.add_step("manor.bring_chicken_home", StepStatus.NOT_AVAILABLE)
        if manor.element("diary"):
            diary = self.session.tap(manor, "diary", "manor-open-diary", (Page.MANOR_DIARY,))
            if diary.element("attach"):
                diary = self.session.tap(
                    diary,
                    "attach",
                    "manor-attach-chicken",
                    (Page.MANOR_DIARY,),
                )
                if diary.element("diary_done"):
                    self.session.add_step("manor.attach_chicken", StepStatus.SUCCESS)
                else:
                    self.session.add_step(
                        "manor.attach_chicken",
                        StepStatus.NOT_AVAILABLE,
                        "verified tap did not change the diary action",
                    )
            elif diary.element("diary_done"):
                self.session.add_step("manor.attach_chicken", StepStatus.ALREADY_DONE)
            else:
                raise AutomationError("Diary has neither attach nor completed state")
            manor = self.session.back(diary, "manor-leave-diary", (Page.MANOR_HOME,))
        else:
            self.session.add_step("manor.attach_chicken", StepStatus.ALREADY_DONE, "diary entry absent")
        return manor

    def _family_tasks(self, manor: DetectedScreen) -> DetectedScreen:
        family = self.session.tap(manor, "family", "family-open", (Page.MANOR_FAMILY, Page.MANOR_FAMILY_TASKS))
        if family.page is Page.MANOR_FAMILY and family.element("sign_in"):
            tasks = self.session.tap(family, "sign_in", "family-sign-in", (Page.MANOR_FAMILY_TASKS,))
            self.session.add_step("family.sign_in", StepStatus.SUCCESS)
        elif family.page is Page.MANOR_FAMILY and family.element("tasks"):
            tasks = self.session.tap(family, "tasks", "family-open-tasks", (Page.MANOR_FAMILY_TASKS,))
            self.session.add_step("family.sign_in", StepStatus.ALREADY_DONE)
        elif family.page is Page.MANOR_FAMILY_TASKS:
            tasks = family
            self.session.add_step("family.sign_in", StepStatus.ALREADY_DONE)
        else:
            raise AutomationError("Family page has no sign-in or task entry")
        tasks = self._donate(tasks)
        tasks = self._simple_family_task(
            tasks, "meal", "meal_unavailable", "family.meal", "family-confirm-meal"
        )
        tasks = self._simple_family_task(
            tasks, "feed", "feed_done", "family.feed", "family-confirm-feed"
        )
        if tasks.element("close"):
            family = self.session.tap(tasks, "close", "family-close-tasks", (Page.MANOR_FAMILY,))
            return self.session.back(family, "family-leave", (Page.MANOR_HOME,))
        self.session.device.back()
        current = self.session.wait_for((Page.MANOR_FAMILY, Page.MANOR_HOME), "family-return")
        return current if current.page is Page.MANOR_HOME else self.session.back(current, "family-leave", (Page.MANOR_HOME,))

    def _donate(self, tasks: DetectedScreen) -> DetectedScreen:
        if tasks.element("donation_done"):
            self.session.add_step("family.donate_egg", StepStatus.ALREADY_DONE)
            return tasks
        if not tasks.element("donate"):
            self.session.add_step("family.donate_egg", StepStatus.NOT_AVAILABLE)
            return tasks
        projects = self.session.tap(tasks, "donate", "donation-open", (Page.MANOR_DONATION_PROJECTS,))
        detail = self.session.tap(projects, "first_project", "donation-first-project", (Page.MANOR_DONATION_DETAIL,))
        confirm = self.session.tap(detail, "donate_now", "donation-open-confirm", (Page.MANOR_DONATION_CONFIRM,))
        success = self.session.tap(
            confirm, "confirm_donation", "donation-confirm-one", (Page.MANOR_DONATION_SUCCESS,)
        )
        detail = self.session.back(success, "donation-leave-success", (Page.MANOR_DONATION_DETAIL,))
        projects = self.session.back(detail, "donation-leave-detail", (Page.MANOR_DONATION_PROJECTS,))
        self.session.device.back()
        manor = self.session.wait_for(Page.MANOR_HOME, "donation-return-manor")
        family = self.session.tap(manor, "family", "family-reopen", (Page.MANOR_FAMILY,))
        tasks = self.session.tap(family, "tasks", "family-reopen-tasks", (Page.MANOR_FAMILY_TASKS,))
        if not tasks.element("donation_done"):
            raise AutomationError("Donation returned without the (1/1) completion marker")
        self.session.add_step("family.donate_egg", StepStatus.SUCCESS, "donated and verified 1 egg")
        return tasks

    def _simple_family_task(
        self,
        tasks: DetectedScreen,
        action_key: str,
        done_key: str,
        step_name: str,
        action_name: str,
    ) -> DetectedScreen:
        if tasks.element(done_key):
            self.session.add_step(step_name, StepStatus.ALREADY_DONE)
            return tasks
        if not tasks.element(action_key):
            self.session.add_step(step_name, StepStatus.NOT_AVAILABLE)
            return tasks
        confirm = self.session.tap(tasks, action_key, f"{action_name}-open", (Page.MANOR_FAMILY_TASKS,))
        key = "confirm" if confirm.element("confirm") else None
        if key is None:
            raise AutomationError(f"{step_name} confirmation is missing")
        after = self.session.tap(confirm, key, action_name, (Page.MANOR_FAMILY_TASKS,))
        if not after.element(done_key):
            raise AutomationError(f"{step_name} returned without its completion marker")
        self.session.add_step(step_name, StepStatus.SUCCESS)
        return after

    def _feed_tasks(self, manor: DetectedScreen) -> DetectedScreen:
        tasks = self.session.tap(manor, "feed_tasks", "feed-tasks-open", (Page.MANOR_FEED_TASKS,))
        tasks = self._daily_claim(tasks)
        tasks = self._quiz(tasks)
        tasks = self._external_feed(tasks, "video", "feed.video", False)
        tasks = self._external_feed(tasks, "store", "feed.store", True)
        for index in range(2):
            key = f"lottery_{index}"
            tasks = self._locate_feed(tasks, key, required=False)
            if not tasks.element(key):
                self.session.add_step(f"feed.lottery_{index + 1}", StepStatus.NOT_AVAILABLE)
                continue
            lottery = self.session.tap(tasks, key, f"feed-lottery-{index + 1}-open", (Page.LOTTERY,))
            lottery = self.lottery.run(lottery, f"feed-lottery-{index + 1}")
            tasks = self.session.back(lottery, f"feed-lottery-{index + 1}-leave", (Page.MANOR_FEED_TASKS,))
        for key, name, claim_to_refresh in (
            ("farm", "feed.baba_farm", False),
            ("family_browse", "feed.family_browse", False),
            ("kitchen", "feed.kitchen", False),
            ("forest_browse", "feed.forest_browse", False),
            ("grain_browse", "feed.grain_browse", True),
            ("village_browse", "feed.village_browse", True),
            ("member_browse", "feed.member_browse", True),
        ):
            tasks = self._locate_feed(tasks, key, required=False)
            if not tasks.element(key):
                self.session.add_step(name, StepStatus.NOT_AVAILABLE)
                continue
            if (
                not claim_to_refresh
                and tasks.element(key).text
                and "领取" in tasks.element(key).text
            ):
                self.session.add_step(
                    name,
                    StepStatus.ALREADY_DONE,
                    "task reward intentionally left unclaimed",
                )
                continue
            if key == "farm":
                tasks = self._baba_farm(tasks)
            elif key == "kitchen":
                tasks = self._kitchen(tasks)
            else:
                tasks = self.external.run(
                    tasks, key, name.replace(".", "-"), Page.MANOR_FEED_TASKS,
                    swipe_to_progress=False, immediate_return=True,
                )
            if claim_to_refresh:
                tasks = self._locate_feed(tasks, key, required=False)
                if tasks.element(key) and tasks.element(key).text and "领取" in tasks.element(key).text:
                    tasks = self.session.tap(tasks, key, f"{name}-claim", (Page.MANOR_FEED_TASKS,))
            self.session.add_step(name, StepStatus.SUCCESS)
        self.session.device.back()
        return self.session.wait_for(Page.MANOR_HOME, "feed-tasks-leave")

    def _daily_claim(self, tasks: DetectedScreen) -> DetectedScreen:
        if not tasks.element("daily_claim"):
            self.session.add_step("feed.daily_claim", StepStatus.ALREADY_DONE)
            return tasks
        after = self.session.tap(tasks, "daily_claim", "feed-daily-claim")
        if after.element("confirm_overflow"):
            after = self.session.tap(after, "confirm_overflow", "feed-confirm-overflow", (Page.MANOR_FEED_TASKS,))
        if after.page is not Page.MANOR_FEED_TASKS:
            after = self.session.wait_for(Page.MANOR_FEED_TASKS, "feed-after-daily-claim")
        self.session.add_step("feed.daily_claim", StepStatus.SUCCESS)
        return after

    def _quiz(self, tasks: DetectedScreen) -> DetectedScreen:
        tasks = self._locate_feed(tasks, "quiz", required=False)
        if not tasks.element("quiz"):
            self.session.add_step("feed.quiz", StepStatus.ALREADY_DONE)
            return tasks
        page = self.session.tap(tasks, "quiz", "quiz-open", (Page.MANOR_QUIZ,))
        tree = page.observation.ui_tree
        options = tuple(
            element.text or ""
            for key, element in sorted(page.elements.items())
            if key.startswith("option_")
        )
        question = ""
        if tree:
            candidates = [
                node.text
                for node in tree.nodes
                if len(node.text.strip()) >= 8 and "题目来源" not in node.text
            ]
            question = max(candidates, key=len, default="")
        answer = self.quiz.solve(question, options[:2]) if len(options) >= 2 else None
        index = answer.option_index if answer else self.session.config.quiz.fallback_option
        result = self.session.tap(page, f"option_{index}", "quiz-answer", (Page.MANOR_QUIZ_RESULT,))
        tasks = self.session.back(result, "quiz-leave", (Page.MANOR_FEED_TASKS,))
        self.session.add_step(
            "feed.quiz",
            StepStatus.SUCCESS,
            f"option={index + 1}, source={answer.source if answer else 'fixed_fallback'}",
        )
        return tasks

    def _external_feed(self, tasks, key, name, swipe):
        tasks = self._locate_feed(tasks, key, required=False)
        if not tasks.element(key):
            self.session.add_step(name, StepStatus.ALREADY_DONE)
            return tasks
        try:
            tasks = self.external.run(
                tasks,
                key,
                name.replace(".", "-"),
                Page.MANOR_FEED_TASKS,
                swipe_to_progress=swipe,
                timeout_seconds=45,
            )
        except AutomationError:
            if (
                key != "video"
                or self.session.current is None
                or self.session.current.page is not Page.UNKNOWN
            ):
                raise
            tasks = self.session.return_from_unclassified(
                Page.MANOR_FEED_TASKS, "feed-video-missing-timer-return"
            )
            tasks = self.external.run(
                tasks,
                key,
                "feed-video-retry",
                Page.MANOR_FEED_TASKS,
                swipe_to_progress=False,
                timeout_seconds=45,
            )
        self.session.add_step(name, StepStatus.SUCCESS)
        return tasks

    def _baba_farm(self, tasks):
        # Spec: 支付宝每日任务文字描述.txt line 67. Opening the farm auto-
        # redirects to the 做任务集肥料 sub-page; collect its sub-tasks and close
        # back to the farm main page, claim the daily free fertilizer, then run
        # two fertilise → 立即领肥 → 丰收礼包 rounds before returning to the feed
        # task list. Text markers are calibration points (see detector.py).
        farm = self.session.tap(
            tasks, "farm", "baba-farm-open", (Page.BABA_FARM, Page.BABA_FARM_TASKS)
        )
        farm = self._dismiss_farm_popup(farm)
        if farm.page is Page.BABA_FARM_TASKS:
            farm = self._baba_farm_tasks(farm)
        if farm.element("free_fertilizer"):
            farm = self.session.tap(
                farm, "free_fertilizer", "baba-free-fertilizer", (Page.BABA_FARM,)
            )
            farm = self._dismiss_farm_popup(farm)
        for index in range(2):
            # With one-key fertilising enabled, the first action may already
            # unlock the next harvest. Do not spend more fertilizer when the
            # current page is ready to claim.
            if not farm.element("claim_now"):
                if not farm.element("fertilize"):
                    raise AutomationError("Baba Farm lost the fertilise action mid-flow")
                farm = self.session.tap(
                    farm, "fertilize", f"baba-fertilize-{index + 1}", (Page.BABA_FARM,)
                )
                farm = self._dismiss_farm_popup(farm)
            if farm.element("claim_now"):
                farm = self.session.tap(
                    farm, "claim_now", f"baba-claim-now-{index + 1}", (Page.BABA_FARM_HARVEST,)
                )
                farm = self._baba_harvest(farm)
        self.session.device.back()
        return self.session.wait_for(Page.MANOR_FEED_TASKS, "baba-farm-return")

    def _baba_farm_tasks(self, farm):
        if farm.element("daily_sign_claim"):
            farm = self.session.tap(farm, "daily_sign_claim", "baba-tasks-daily-sign")
        farm = self._locate_in_page(
            farm, "chicken_feed_claim", Page.BABA_FARM_TASKS,
            "baba-tasks-chicken-feed", required=False,
        )
        if farm.element("chicken_feed_claim"):
            farm = self.session.tap(farm, "chicken_feed_claim", "baba-tasks-chicken-feed")
        if farm.element("close"):
            farm = self.session.tap(farm, "close", "baba-tasks-close", (Page.BABA_FARM,))
        return farm

    def _baba_harvest(self, farm):
        if farm.element("claim"):
            farm = self.session.tap(
                farm,
                "claim",
                "baba-harvest-claim",
                (Page.BABA_FARM_HARVEST, Page.BABA_FARM),
            )
        if farm.element("close"):
            farm = self.session.tap(farm, "close", "baba-harvest-close", (Page.BABA_FARM,))
        return farm

    def _dismiss_farm_popup(self, farm):
        # 去蚂蚁森林收能量 / 施肥挑战 popups sit over the farm after an action;
        # close them so they don't block the next step. (Calibration point.)
        if farm.page in (Page.BABA_FARM, Page.BABA_FARM_TASKS) and farm.element("close_reward"):
            return self.session.tap(
                farm,
                "close_reward",
                "baba-dismiss-popup",
                (farm.page,),
            )
        return farm

    def _locate_in_page(self, current, key, page, name, *, required=True):
        if current.element(key):
            return current
        size = self.session.device.size()
        for index in range(8):
            current = self.session.swipe(
                current,
                f"{name}-locate-{index + 1}",
                (size.width // 2, int(size.height * 0.78)),
                (size.width // 2, int(size.height * 0.35)),
                450,
            )
            if current.page is not page:
                raise AutomationError(f"Left {page.value} while locating {key}")
            if current.element(key):
                return current
        if required:
            raise AutomationError(f"{key} was not found on {page.value}")
        return current

    def _kitchen(self, tasks):
        # Spec: line 77. Claim daily ingredients, open the 爱心食材店 sub-page to
        # collect 领10g食材, then cook twice (each cook shows a 美食图鉴 closed via X).
        kitchen = self.session.tap(tasks, "kitchen", "kitchen-open", (Page.CHICKEN_KITCHEN,))
        for key in ("daily_ingredient", "claim_ingredient"):
            if kitchen.element(key):
                kitchen = self.session.tap(kitchen, key, f"kitchen-{key}")
        if kitchen.element("donate_shop"):
            kitchen = self._kitchen_donate(kitchen)
        for index in range(2):
            if not kitchen.element("cook"):
                raise AutomationError("Kitchen cook action disappeared before two meals")
            kitchen = self.session.tap(kitchen, "cook", f"kitchen-cook-{index + 1}")
            if kitchen.element("close"):
                kitchen = self.session.tap(
                    kitchen, "close", f"kitchen-close-book-{index + 1}", (Page.CHICKEN_KITCHEN,)
                )
        self.session.device.back()
        return self.session.wait_for(Page.MANOR_FEED_TASKS, "kitchen-return")

    def _kitchen_donate(self, kitchen):
        donate = self.session.tap(
            kitchen, "donate_shop", "kitchen-donate-open", (Page.KITCHEN_DONATE,)
        )
        if donate.element("claim"):
            donate = self.session.tap(donate, "claim", "kitchen-donate-claim", (Page.KITCHEN_DONATE,))
        self.session.device.back()
        return self.session.wait_for(Page.CHICKEN_KITCHEN, "kitchen-donate-return")

    def _locate_feed(self, current: DetectedScreen, key: str, required: bool = True) -> DetectedScreen:
        if current.element(key):
            return current
        size = self.session.device.size()
        for index in range(8):
            current = self.session.swipe(
                current,
                f"feed-locate-{key}-{index + 1}",
                (size.width // 2, int(size.height * 0.78)),
                (size.width // 2, int(size.height * 0.35)),
                450,
            )
            if current.page is not Page.MANOR_FEED_TASKS:
                raise AutomationError(f"Left feed task list while locating {key}")
            if current.element(key):
                return current
        if required:
            raise AutomationError(f"Feed task was not found: {key}")
        return current
