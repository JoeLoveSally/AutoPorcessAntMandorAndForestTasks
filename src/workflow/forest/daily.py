from __future__ import annotations

import time

from domain_data import DetectedScreen, Page, StepStatus
from runtime.errors import AutomationError
from workflow.forest.energy_rain import EnergyRainPlayer
from workflow.session import WorkflowSession
from workflow.shared import LotteryRunner


class ForestWorkflow:
    def __init__(self, session: WorkflowSession):
        self.session = session
        self.lottery = LotteryRunner(session)
        self.rain = EnergyRainPlayer(session.config, session.logger)

    def run(self, alipay_home: DetectedScreen) -> DetectedScreen:
        forest = self.session.tap(alipay_home, "forest", "forest-open", (Page.FOREST_HOME,))
        time.sleep(max(2.0, self.session.config.runtime.settle_seconds))
        forest = self.session.wait_for(Page.FOREST_HOME, "forest-stable")
        forest = self._collect_own_energy(forest)
        forest = self._settled(forest)
        forest = self._collect_friend_energy(forest)
        forest = self._water(forest)
        forest = self._energy_rain(forest)
        self.session.add_step("forest", StepStatus.SUCCESS, "single pass completed")
        return forest

    def _settled(self, forest: DetectedScreen) -> DetectedScreen:
        """Re-observe a page whose tree collapsed to nothing.

        Right after a collect animation the home classifies as forest_home
        with no elements at all; every availability decision made on that
        frame would skip the remaining tasks, and a carousel swipe on it can
        land on the anniversary campaign page.
        """
        if forest.elements or forest.overlays:
            return forest
        time.sleep(max(1.0, self.session.config.runtime.settle_seconds))
        settled = self.session.observe("forest-settle")
        if len(settled.elements) >= len(forest.elements):
            return settled
        return forest

    def _collect_own_energy(self, forest: DetectedScreen) -> DetectedScreen:
        collected = 0
        for scan in range(4):
            keys = sorted(
                key
                for key in forest.elements
                if key.startswith("energy_") and key.removeprefix("energy_").isdigit()
            )
            if not keys:
                break
            for key in keys:
                if not forest.element(key):
                    continue
                forest = self.session.tap(forest, key, f"forest-own-energy-{collected + 1}", (Page.FOREST_HOME,))
                collected += 1
            forest = self.session.observe(f"forest-own-energy-scan-{scan + 1}")
        if forest.element("energy_sign"):
            reward = self.session.tap(
                forest,
                "energy_sign",
                "forest-energy-sign",
                (Page.FOREST_SIGN_REWARD,),
            )
            size = self.session.device.size()
            reward = self.session.swipe(
                reward,
                "forest-energy-sign-scroll",
                (size.width // 2, int(size.height * 0.75)),
                (size.width // 2, int(size.height * 0.35)),
            )
            if reward.element("claim"):
                reward = self.session.tap(
                    reward,
                    "claim",
                    "forest-energy-sign-claim",
                    (Page.FOREST_SIGN_REWARD,),
                )
            forest = self.session.tap(
                reward,
                "close_reward",
                "forest-energy-sign-close",
                (Page.FOREST_HOME,),
            )
        self.session.add_step(
            "forest.collect_own_energy",
            StepStatus.SUCCESS if collected else StepStatus.ALREADY_DONE,
            f"collected {collected} bubbles",
        )
        return forest

    def _collect_friend_energy(self, forest: DetectedScreen) -> DetectedScreen:
        if not forest.element("find_energy"):
            self.session.add_step("forest.collect_friend_energy", StepStatus.NOT_AVAILABLE)
            return forest
        current = self.session.tap(
            forest,
            "find_energy",
            "forest-find-energy",
            (Page.FOREST_FRIEND, Page.FOREST_TREASURE),
        )
        friends = 0
        size = self.session.device.size()
        for index in range(self.session.config.runtime.max_task_iterations):
            if current.page is Page.FOREST_TREASURE:
                break
            if current.page is not Page.FOREST_FRIEND or not current.element("one_click"):
                raise AutomationError(f"Friend page {index + 1} has no one-click collection")
            current = self.session.tap(
                current,
                "one_click",
                f"forest-friend-one-click-{index + 1}",
                (Page.FOREST_FRIEND,),
            )
            friends += 1
            current = self.session.swipe(
                current,
                f"forest-next-friend-{index + 1}",
                (size.width // 2, int(size.height * 0.76)),
                (size.width // 2, int(size.height * 0.30)),
                450,
            )
            if current.page not in (Page.FOREST_FRIEND, Page.FOREST_TREASURE):
                current = self.session.wait_for(
                    (Page.FOREST_FRIEND, Page.FOREST_TREASURE),
                    f"forest-friend-settle-{index + 1}",
                )
        else:
            raise AutomationError("Friend energy loop reached its iteration budget")
        current = self._forest_lotteries(current)
        self.session.add_step(
            "forest.collect_friend_energy",
            StepStatus.SUCCESS,
            f"visited {friends} friends and completed lotteries",
        )
        return current

    def _forest_lotteries(self, lottery: DetectedScreen) -> DetectedScreen:
        if lottery.page is not Page.FOREST_TREASURE or not lottery.element("enter_lottery"):
            raise AutomationError("Friend loop did not finish on the forest treasure entry")
        lottery = self.session.tap(
            lottery,
            "enter_lottery",
            "forest-treasure-enter-lottery",
            (Page.FOREST_LOTTERY,),
        )
        current = self.lottery.run(
            lottery,
            "forest-lottery-right",
            page_type=Page.FOREST_LOTTERY,
            store_repetitions=2,
            exchange_feed=False,
        )
        if current.element("switch"):
            current = self.session.tap(
                current,
                "switch",
                "forest-lottery-switch-left",
                (Page.FOREST_LOTTERY,),
            )
            current = self.lottery.run(
                current,
                "forest-lottery-left",
                page_type=Page.FOREST_LOTTERY,
                store_repetitions=0,
                exchange_feed=False,
            )
        self.session.device.back()
        current = self.session.wait_for(
            (Page.FOREST_TREASURE, Page.FOREST_HOME), "forest-lottery-return-1"
        )
        if current.page is Page.FOREST_TREASURE:
            current = self.session.back(current, "forest-lottery-return-2", (Page.FOREST_HOME,))
        return current

    def _water(self, forest: DetectedScreen) -> DetectedScreen:
        forest = self._locate_carousel(forest, "love_plant")
        if forest.element("love_plant"):
            page = self.session.tap(
                forest, "love_plant", "forest-love-plant-open", (Page.FOREST_LOVE_PLANT,)
            )
            if page.element("close_reward"):
                page = self.session.tap(page, "close_reward", "forest-love-plant-reward-close", (Page.FOREST_LOVE_PLANT,))
            page = self.session.tap(page, "water", "forest-love-plant-amount", (Page.FOREST_LOVE_PLANT,))
            for index in range(8):
                page = self.session.tap(page, "plus", f"forest-love-plant-plus-{index + 1}", (Page.FOREST_LOVE_PLANT,))
            page = self.session.tap(
                page, "confirm", "forest-love-plant-confirm", (Page.FOREST_LOVE_PLANT,), irreversible=True,
            )
            if page.element("close_reward"):
                page = self.session.tap(page, "close_reward", "forest-love-plant-finish-reward", (Page.FOREST_LOVE_PLANT,))
            forest = self.session.back(page, "forest-love-plant-leave", (Page.FOREST_HOME,))
            self.session.add_step("forest.water_love_plant", StepStatus.SUCCESS, "100g")
        else:
            self.session.add_step("forest.water_love_plant", StepStatus.NOT_AVAILABLE)
        forest = self._locate_carousel(forest, "co_plant")
        if forest.element("co_plant"):
            page = self.session.tap(forest, "co_plant", "forest-co-plant-open", (Page.FOREST_CO_PLANT,))
            page = self.session.tap(page, "water", "forest-co-plant-amount", (Page.FOREST_CO_PLANT,))
            page = self.session.tap(
                page, "confirm", "forest-co-plant-confirm", (Page.FOREST_CO_PLANT,), irreversible=True,
            )
            forest = self.session.back(page, "forest-co-plant-leave", (Page.FOREST_HOME,))
            self.session.add_step("forest.water_co_plant", StepStatus.SUCCESS, "520g")
        else:
            self.session.add_step("forest.water_co_plant", StepStatus.NOT_AVAILABLE)
        return forest

    def _energy_rain(self, forest: DetectedScreen) -> DetectedScreen:
        forest = self._locate_carousel(forest, "energy_rain")
        if not forest.element("energy_rain"):
            self.session.add_step("forest.energy_rain", StepStatus.NOT_AVAILABLE)
            return forest
        rain = self.session.tap(forest, "energy_rain", "energy-rain-open", (Page.ENERGY_RAIN,))
        rounds = []
        for round_number in (1, 2):
            start = rain.element("start")
            if start is None:
                raise AutomationError(f"Energy rain round {round_number} has no start action")
            stats = self.rain.play(self.session.device, start.center)
            rounds.append(stats)
            result = self.session.wait_for(
                (Page.ENERGY_RAIN_GIFT, Page.ENERGY_RAIN_RESULT),
                f"energy-rain-result-{round_number}",
                timeout=8,
            )
            if stats.hit_rate < self.session.config.realtime.minimum_hit_rate:
                raise AutomationError(
                    f"Energy rain hit rate {stats.hit_rate:.1%} is below "
                    f"{self.session.config.realtime.minimum_hit_rate:.1%}"
                )
            if round_number == 1:
                if result.page is not Page.ENERGY_RAIN_GIFT or not result.element("gift_first"):
                    raise AutomationError("First energy rain did not offer the first-friend gift")
                rain = self.session.tap(
                    result,
                    "gift_first",
                    "energy-rain-gift-first-friend",
                    (Page.ENERGY_RAIN,),
                )
            else:
                forest = self.session.back(result, "energy-rain-leave", (Page.FOREST_HOME,))
        self.session.add_step(
            "forest.energy_rain",
            StepStatus.SUCCESS,
            ", ".join(f"round {index + 1}: {item.hit_rate:.1%}" for index, item in enumerate(rounds)),
        )
        return forest

    def _locate_carousel(self, forest: DetectedScreen, key: str) -> DetectedScreen:
        if forest.element(key):
            return forest
        forest = self._settled(forest)
        if forest.element(key):
            return forest
        size = self.session.device.size()
        current = forest
        for index in range(4):
            current = self.session.swipe(
                current,
                f"forest-carousel-{key}-{index + 1}",
                (int(size.width * 0.80), int(size.height * 0.78)),
                (int(size.width * 0.25), int(size.height * 0.78)),
                500,
            )
            if current.page is not Page.FOREST_HOME:
                raise AutomationError(f"Left forest home while locating {key}")
            if current.element(key):
                return current
        return current
