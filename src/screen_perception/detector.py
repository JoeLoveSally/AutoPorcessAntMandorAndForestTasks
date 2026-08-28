from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from domain_data import Bounds, DetectedScreen, Element, Observation, Overlay, OverlayType, Page
from screen_perception.ui_tree import UiTree
from screen_perception.vision import (
    detect_chicken_kitchen_controls,
    detect_family_task_controls,
    detect_green_energy_balls,
    detect_kitchen_donate_controls,
    detect_love_plant_controls,
    detect_manor_home_controls,
    detect_modal_scrim,
    detect_yellow_right_button,
    match_template,
)

# The 10th-anniversary campaign family (watering page, certificate story,
# retrospective) shows 蚂蚁森林 and lottery markers inside its Canvas, so both
# the forest-home and lottery rules must exclude it explicitly.
_CAMPAIGN_MARKERS = (
    "上滑种树",
    "浇水加入",
    "十年之约",
    "蚂蚁森林10周年",
    "10周年种树",
    "去种下",
    "我们的十年",
    "限定保护罩",
)


class ScreenDetector:
    def __init__(
        self,
        package: str = "com.eg.android.AlipayGphone",
        template_directory: Path = Path("screenshots/template"),
    ):
        self.package = package
        self.template_directory = template_directory

    def detect(self, observation: Observation) -> DetectedScreen:
        if observation.package != self.package:
            return DetectedScreen(
                Page.UNKNOWN,
                observation,
                evidence=(f"unexpected_package:{observation.package}",),
            )
        tree: UiTree | None = observation.ui_tree
        labels = tree.labels() if tree else ()
        overlays = tuple(self._overlays(observation, tree))
        for detector in (
            self._energy_rain,
            self._external,
            self._alipay_home,
            self._forest,
            self._manor,
        ):
            result = detector(observation, tree, labels, overlays)
            if result is not None:
                return self._with_promo_overlay(observation, result)
        return self._with_promo_overlay(
            observation,
            DetectedScreen(
                Page.UNKNOWN,
                observation,
                overlays=overlays,
                evidence=tuple(observation.errors) or ("no_page_rule_matched",),
            ),
        )

    def _with_promo_overlay(
        self,
        observation: Observation,
        result: DetectedScreen,
    ) -> DetectedScreen:
        """Attach a Canvas promo scrim, when present, as a dismissible overlay.

        Activity promos cover the page with a touch-swallowing scrim that the
        accessibility tree cannot see (forest anniversary skins, game-centre
        popups).  Publishing them as an overlay lets the executor refuse taps
        on the covered page elements and recovery dismiss them.  Pages that
        already expose their own modal controls (harvest pack, recipe card)
        keep their tree-provided elements and get no second overlay.
        """
        if not observation.screenshot:
            return result
        # These pages deliberately present a dimmed, centred task modal whose
        # semantic controls are already exposed by the accessibility tree.
        # The generic scrim signature must not reclassify that normal modal as
        # an advertisement and block its plus/confirm actions.
        if result.page in (Page.FOREST_LOVE_PLANT, Page.FOREST_CO_PLANT) and any(
            key in result.elements for key in ("plus", "confirm")
        ):
            return result
        dismiss_keys = ("close", "close_reward", "abandon_reward", "confirm_overflow")
        if any(key in result.elements for key in dismiss_keys):
            return result
        if any(key in overlay.elements for overlay in result.overlays for key in dismiss_keys):
            return result
        # Manor home has several circular bottom-navigation controls in the
        # same band as a Canvas promo close button. The generic scrim heuristic
        # can mistake those controls for an X and navigate into a task page;
        # rely on semantic manor overlays there instead.
        if result.page is Page.MANOR_HOME:
            return result
        scrim = detect_modal_scrim(observation.screenshot)
        if scrim is None:
            return result
        x, y, confidence = scrim
        close = Element(
            "close",
            Bounds(x - 70, y - 70, x + 70, y + 70),
            observation.id,
            "关闭",
            source="cv:modal_scrim_close",
            confidence=confidence,
        )
        return DetectedScreen(
            result.page,
            result.observation,
            result.elements,
            (*result.overlays, Overlay(OverlayType.PROMO, {"close": close}, ("cv:modal_scrim",), confidence)),
            result.evidence,
            result.confidence,
        )

    def _external(self, observation, tree, labels, overlays):
        if tree is None:
            return None
        # Generic task-card descriptions such as "浏览15秒" remain visible in
        # several task-list WebViews.  They do not prove that navigation has
        # reached the external timed page; require a rendered progress marker.
        if _visible(
            tree,
            "任务 浏览完成",
            "已完成 可领饲料",
            "已完成 可领奖励",
            "滑动浏览",
            "任务倒计时",
        ):
            return self._screen(Page.EXTERNAL_BROWSE, observation, tree, overlays, {
                "close": ("关闭",), "back": ("返回",), "abandon_reward": ("放弃奖励",),
            })
        return None

    def _alipay_home(self, observation, tree, labels, overlays):
        if tree is None:
            return None
        manor = tree.element(observation.id, "manor", "蚂蚁庄园", fragment=True)
        forest = tree.element(observation.id, "forest", "蚂蚁森林", fragment=True)
        if not (manor and forest):
            return None
        return DetectedScreen(
            Page.ALIPAY_HOME,
            observation,
            {"manor": manor, "forest": forest},
            overlays,
            ("ui:蚂蚁庄园", "ui:蚂蚁森林"),
            0.99,
        )

    def _manor(self, observation, tree, labels, overlays):
        if tree is None:
            return None
        joined = " ".join(labels)
        # Chicken Kitchen and its donation shop are Canvas-only on current
        # Alipay builds: the UI tree contains one unlabelled Image node.  Use
        # the visual layout before text rules so the workflow can also observe
        # recipe popups and already-claimed states.
        if observation.screenshot:
            if controls := detect_chicken_kitchen_controls(observation.screenshot):
                return DetectedScreen(
                    Page.CHICKEN_KITCHEN,
                    observation,
                    {
                        key: _point_element(
                            observation, key, (x, y), f"cv_layout:kitchen_{key}", confidence
                        )
                        for key, (x, y, confidence) in controls.items()
                    },
                    overlays,
                    ("cv:kitchen_canvas",),
                    0.88,
                )
            donate_controls = detect_kitchen_donate_controls(observation.screenshot)
            if donate_controls is not None:
                return DetectedScreen(
                    Page.KITCHEN_DONATE,
                    observation,
                    {
                        key: _point_element(
                            observation,
                            key,
                            (x, y),
                            f"cv_layout:kitchen_donate_{key}",
                            confidence,
                        )
                        for key, (x, y, confidence) in donate_controls.items()
                    },
                    overlays,
                    ("cv:kitchen_donate_canvas",),
                    0.86,
                )
        if "我已助力" in joined and "去捐蛋" in joined:
            return self._screen(
                Page.MANOR_DONATION_PROJECTS,
                observation,
                tree,
                overlays,
                {"first_project": ("去捐蛋",)},
            )
        if observation.screenshot:
            diary_page = self.template_directory / "diary_page.png"
            page_match = (
                match_template(
                    observation.screenshot, diary_page, threshold=0.86, ambiguity_margin=0.03
                )
                if diary_page.is_file()
                else None
            )
            if page_match:
                elements: dict[str, Element] = {}
                attach_template = self.template_directory / "diary_attach.png"
                attach_match = (
                    match_template(
                        observation.screenshot,
                        attach_template,
                        threshold=0.84,
                        ambiguity_margin=0.03,
                    )
                    if attach_template.is_file()
                    else None
                )
                if attach_match:
                    elements["attach"] = Element(
                        "attach",
                        attach_match.bounds,
                        observation.id,
                        "贴贴小鸡",
                        source="cv_template:diary_attach.png",
                        confidence=attach_match.confidence,
                    )
                else:
                    elements["diary_done"] = _point_element(
                        observation,
                        "diary_done",
                        (observation.width // 2, round(observation.height * 0.94)),
                        "cv:diary_page_without_attach",
                        0.82,
                    )
                return DetectedScreen(
                    Page.MANOR_DIARY,
                    observation,
                    elements,
                    overlays,
                    ("cv_template:diary_page.png",),
                    0.90,
                )
        # The family panel reorders completed rows.  Bind actions to the
        # accessibility text instead of assuming fixed vertical positions.
        if _has(joined, "请家人吃一顿美食", "帮喂家人小鸡", "每日捐蛋做好事"):
            return self._family_tasks(observation, tree, overlays)
        if "欢乐全家桶" in joined:
            elements: dict[str, Element] = {}
            if any(
                overlay.type in (OverlayType.FOOD_SELECTION, OverlayType.CONFIRMATION)
                and "confirm" in overlay.elements
                for overlay in overlays
            ):
                return DetectedScreen(
                    Page.MANOR_FAMILY_TASKS,
                    observation,
                    elements,
                    overlays,
                    ("ui:family_confirmation",),
                    0.96,
                )
            family_controls = (
                detect_family_task_controls(observation.screenshot)
                if observation.screenshot
                else {}
            )
            if any(
                key in family_controls
                for key in (
                    "donate", "donation_done", "meal", "meal_unavailable", "feed", "feed_done"
                )
            ):
                for key, (x, y, confidence) in family_controls.items():
                    elements[key] = _point_element(
                        observation,
                        key,
                        (x, y),
                        f"cv_layout:family_{key}",
                        confidence,
                    )
                return DetectedScreen(
                    Page.MANOR_FAMILY_TASKS,
                    observation,
                    elements,
                    overlays,
                    ("cv:family_task_panel",),
                    0.88,
                )
            sign_template = self.template_directory / "family_sign_in.png"
            sign_match = (
                match_template(
                    observation.screenshot,
                    sign_template,
                    threshold=0.80,
                    ambiguity_margin=0.02,
                )
                if observation.screenshot and sign_template.is_file()
                else None
            )
            if sign_match:
                elements["sign_in"] = Element(
                    "sign_in",
                    sign_match.bounds,
                    observation.id,
                    "立即签到",
                    source="cv_template:family_sign_in.png",
                    confidence=sign_match.confidence,
                )
            else:
                elements["tasks"] = _point_element(
                    observation,
                    "tasks",
                    (round(observation.width * 0.5), round(observation.height * 0.92)),
                    "cv_layout:family_tasks",
                    0.72,
                )
            return DetectedScreen(
                Page.MANOR_FAMILY,
                observation,
                elements,
                overlays,
                ("ui:欢乐全家桶",),
                0.90,
            )
        if _has(joined, "贴贴小鸡", "明日再来"):
            return self._screen(Page.MANOR_DIARY, observation, tree, overlays, {
                "attach": ("贴贴小鸡",), "diary_done": ("明日再来",), "close": ("关闭",),
            })
        if _visible(tree, "捐蛋成功", "感谢你的爱心", "本次捐了") and _visible(
            tree, "获取今日份幸运签", "完成", "关闭"
        ):
            return self._screen(Page.MANOR_DONATION_SUCCESS, observation, tree, overlays, {
                "close": ("关闭", "完成"),
            })
        if _visible(tree, "捐爱心蛋", "选择捐蛋数量") and _visible(tree, "立即捐蛋"):
            return self._screen(Page.MANOR_DONATION_CONFIRM, observation, tree, overlays, {
                "confirm_donation": ("立即捐蛋",),
            })
        if _visible(tree, "本期目标", "项目介绍", "当前进度") and _visible(tree, "立即捐蛋", "去捐蛋"):
            return self._screen(Page.MANOR_DONATION_DETAIL, observation, tree, overlays, {
                "donate_now": ("立即捐蛋", "去捐蛋"),
            })
        if _has(joined, "捐蛋详情", "公益项目") and "去捐蛋" in joined:
            return self._screen(Page.MANOR_DONATION_PROJECTS, observation, tree, overlays, {
                "first_project": ("去捐蛋",),
            })
        if _has(joined, "攒亲密度", "每日捐蛋做好事", "帮家人喂小鸡"):
            return self._family_tasks(observation, tree, overlays)
        if "立即签到" in joined or ("家庭" in joined and "攒亲密度" in joined):
            return self._screen(Page.MANOR_FAMILY, observation, tree, overlays, {
                "sign_in": ("立即签到",), "tasks": ("攒亲密度",),
            })
        if "去领取饲料" in joined and _has(joined, "回答正确", "回答错误", "答案", "解析"):
            return self._quiz(observation, tree, overlays, result=True)
        if "题目来源" in joined:
            return self._quiz(
                observation,
                tree,
                overlays,
                result=_has(joined, "正确答案", "回答正确", "回答错误", "答案解析"),
            )
        if _has(joined, "庄园小课堂", "题目") and _has(joined, "A.", "B.", "正确答案"):
            return self._quiz(observation, tree, overlays, result="正确答案" in joined)
        if _has(joined, "饲料任务", "领饲料"):
            return self._feed_tasks(observation, tree, overlays)
        # The anniversary campaign shows 活动剩余时间 but is not a lottery;
        # leave it unclassified so recovery backs out of it.
        if _has(joined, "抽奖机会", "立即抽奖", "活动剩余时间") and not _visible(
            tree, *_CAMPAIGN_MARKERS
        ):
            return self._lottery(Page.LOTTERY, observation, tree, overlays)
        # Baba Farm (spec: 支付宝每日任务文字描述.txt line 67). The harvest
        # pack is a full-screen layer that masks the main-page markers, so it
        # is detected first; the 做任务集肥料 sub-page next; then the main page.
        # All text fragments are calibration points verified against the spec
        # and must be confirmed on a real UI dump.
        if _has(joined, "丰收礼包"):
            return self._screen(Page.BABA_FARM_HARVEST, observation, tree, overlays, {
                "claim": ("立即领取",), "close": ("关闭", "知道了"),
            })
        if _has(joined, "做任务集肥料"):
            elements: dict[str, Element] = self._elements(observation, tree, {"close": ("关闭",)})
            if action := tree.task_action(observation.id, "daily_sign_claim", ("每日签到",), ("领取",)):
                elements["daily_sign_claim"] = action
            if action := tree.task_action(
                observation.id, "chicken_feed_claim", ("蚂蚁庄园小鸡肥料",), ("领取",)
            ):
                elements["chicken_feed_claim"] = action
            return DetectedScreen(
                Page.BABA_FARM_TASKS, observation, elements, overlays, ("ui:做任务集肥料",), 0.90
            )
        if _has(joined, "芭芭农场") and _visible(tree, "施肥"):
            elements = self._elements(observation, tree, {
                "free_fertilizer": ("点击领取",),
                "claim_now": ("立即领肥",),
            })
            # The real farm exposes banner copy containing "施肥" but not the
            # large Canvas fertilise button. Prefer an exact accessibility
            # action when available; otherwise use the calibrated main-button
            # position, never the first text fragment containing "施肥".
            if fertilize := tree.element(observation.id, "fertilize", "施肥"):
                elements["fertilize"] = fertilize
            elif observation.screenshot:
                elements["fertilize"] = _point_element(
                    observation,
                    "fertilize",
                    (round(observation.width * 0.50), round(observation.height * 0.77)),
                    "cv_layout:baba_farm_fertilize",
                    0.86,
                )
            return DetectedScreen(
                Page.BABA_FARM,
                observation,
                elements,
                overlays,
                ("ui:芭芭农场",),
                0.90,
            )
        # Chicken Kitchen (spec line 77). The 献爱心 sub-page is detected before
        # the main kitchen page; the main page is keyed on "小鸡厨房" so it still
        # matches after 领今日食材 has been claimed and its text disappears.
        if _has(joined, "献爱心") and _has(joined, "得食材"):
            return self._screen(Page.KITCHEN_DONATE, observation, tree, overlays, {
                "claim": ("领10g食材",),
            })
        if _has(joined, "小鸡厨房") and _visible(tree, "做美食"):
            return self._screen(Page.CHICKEN_KITCHEN, observation, tree, overlays, {
                "cook": ("做美食",),
                "daily_ingredient": ("领今日食材",),
                "claim_ingredient": ("领取食材",),
                "donate_shop": ("爱心食材店",),
                "close": ("关闭",),
            })
        if _has(joined, "蚂蚁庄园") or _has(joined, "家庭", "领饲料", "去捐蛋"):
            elements = self._elements(observation, tree, {
                "family": ("家庭",), "feed_tasks": ("领饲料",), "find_chicken": ("马上去找TA",),
                "reward_friend": ("打赏",), "diary": ("小鸡日记", "日记"),
                "bring_home": ("带小鸡回家",),
            })
            if observation.screenshot:
                for key, (x, y, confidence) in detect_manor_home_controls(observation.screenshot).items():
                    elements[key] = _point_element(
                        observation, key, (x, y), f"cv_layout:manor_{key}", confidence
                    )
            return DetectedScreen(Page.MANOR_HOME, observation, elements, overlays, ("manor_marker",), 0.80)
        return None

    def _forest(self, observation, tree, labels, overlays):
        if tree is None:
            return None
        joined = " ".join(labels)
        # When no collectible friend remains, 找能量 can route to an Alipay
        # membership task page.  It still contains 蚂蚁森林 and green Canvas
        # decorations, but is not the forest home.  Keep it UNKNOWN so the
        # workflow's post-condition recovery backs out to the real home page.
        if _visible(tree, "支付宝会员签到") and _has(
            joined, "养绿植得能量", "找能量共获得"
        ):
            return DetectedScreen(
                Page.UNKNOWN,
                observation,
                overlays=overlays,
                evidence=("ui:支付宝会员签到", "not:forest_home"),
            )
        if _has(joined, "我的活力值") and _visible(tree, "关闭奖励弹窗"):
            return self._screen(Page.FOREST_SIGN_REWARD, observation, tree, overlays, {
                "close_reward": ("关闭奖励弹窗",),
                "claim": ("立即领取",),
            })
        if _visible(tree, "送TA机会") and _has(joined, "送好友能量雨次数", "能量雨"):
            return self._screen(Page.ENERGY_RAIN_GIFT, observation, tree, overlays, {
                "gift_first": ("送TA机会",),
            })
        if _visible(tree, "为爱攒能量"):
            return self._screen(Page.FOREST_LOVE_PLANT, observation, tree, overlays, {
                "water": ("为爱攒能量", "攒能量"), "plus": ("+",), "confirm": ("攒能量",),
            })
        # The amount selector is a modal over the love-plant Canvas.  Its
        # background still exposes the forest title, so the generic home rule
        # would otherwise win once the Canvas button is replaced by the modal.
        # Require the modal-specific copy before binding the exact controls.
        if _visible(tree, "你当前有", "喊TA来攒") and _visible(tree, "攒能量"):
            return self._screen(Page.FOREST_LOVE_PLANT, observation, tree, overlays, {
                "water": ("攒能量",), "plus": ("+",), "confirm": ("攒能量",),
            })
        # The love-plant page renders 为爱攒能量 as Canvas; only 真爱合种 and
        # calendar fragments reach the tree. Do not bind water from tree text:
        # fragments such as 累计一起攒能量 would win over the real button, so
        # the purple-pill signature is the only source for it.
        if _visible(tree, "真爱合种") and observation.screenshot:
            if controls := detect_love_plant_controls(observation.screenshot):
                elements = {
                    key: _point_element(
                        observation, key, (x, y), f"cv_layout:love_plant_{key}", confidence
                    )
                    for key, (x, y, confidence) in controls.items()
                }
                return DetectedScreen(
                    Page.FOREST_LOVE_PLANT,
                    observation,
                    elements,
                    overlays,
                    ("ui:真爱合种", "cv:love_plant_water"),
                    0.88,
                )
        if _visible(tree, "浇水") and _visible(tree, "合种") and "真爱合种" not in joined:
            return self._screen(Page.FOREST_CO_PLANT, observation, tree, overlays, {
                "water": ("浇水",), "confirm": ("浇水",),
            })
        if _visible(tree, "森林寻宝") and _visible(tree, "立即抽奖"):
            return self._screen(Page.FOREST_TREASURE, observation, tree, overlays, {
                "enter_lottery": ("立即抽奖",),
            })
        if _visible(tree, "森林市集", "抽奖机会") and _visible(tree, "立即抽奖", "签到"):
            return self._lottery(Page.FOREST_LOTTERY, observation, tree, overlays)
        if _visible(tree, "TA待收的能量", "一键收"):
            # Friend WebViews retain the preceding friend's hidden 一键收 node
            # after a swipe. Bind the action only when the bright yellow
            # right-edge button is present in the current screenshot. A gift
            # bubble elsewhere on the tree is intentionally ignored.
            elements: dict[str, Element] = {}
            if observation.screenshot:
                if point := detect_yellow_right_button(observation.screenshot):
                    elements["one_click"] = _point_element(
                        observation, "one_click", point, "cv:yellow_right"
                    )
            return DetectedScreen(Page.FOREST_FRIEND, observation, elements, overlays, ("friend_energy_marker",), 0.90)
        # The 10th-anniversary campaign page is a full-screen Canvas whose tree
        # also contains 蚂蚁森林 (浇水给蚂蚁森林十年之约林); without this guard
        # it classifies as the forest home and every carousel swipe runs on the
        # wrong page.
        if _visible(tree, "蚂蚁森林") and not _visible(
            tree, *_CAMPAIGN_MARKERS
        ):
            elements = self._elements(observation, tree, {
                "find_energy": ("找能量",), "energy_rain": ("天天能量雨", "能量雨"),
                "love_plant": ("真爱合种",),
                "energy_sign": ("能量签到",),
            })
            if co_plant := tree.element(observation.id, "co_plant", "合种"):
                elements["co_plant"] = co_plant
            if observation.screenshot:
                if "find_energy" not in elements:
                    if point := detect_yellow_right_button(observation.screenshot):
                        elements["find_energy"] = _point_element(
                            observation, "find_energy", point, "cv:yellow_right"
                        )
                energy_index = 0
                for x, y, confidence in detect_green_energy_balls(observation.screenshot):
                    if x < observation.width * 0.45 and y < observation.height * 0.24:
                        elements["energy_sign"] = _point_element(
                            observation, "energy_sign", (x, y), "cv:energy_sign", confidence
                        )
                        continue
                    # Real bubbles are pure Canvas; a green blob inside the
                    # bounds of a labelled content node is page UI such as the
                    # anniversary banner's 去种树 pill. The root WebView node
                    # spans the whole screen, so near-full-screen bounds do
                    # not count as content.
                    screen_area = observation.width * observation.height
                    if any(
                        node.bounds.valid
                        and node.bounds.left <= x <= node.bounds.right
                        and node.bounds.top <= y <= node.bounds.bottom
                        and (node.bounds.right - node.bounds.left)
                        * (node.bounds.bottom - node.bounds.top)
                        <= screen_area * 0.20
                        for node in tree.nodes
                        if node.text or node.description
                    ):
                        continue
                    key = f"energy_{energy_index}"
                    energy_index += 1
                    elements[key] = _point_element(
                        observation, key, (x, y), "cv:green_ball", confidence
                    )
            return DetectedScreen(Page.FOREST_HOME, observation, elements, overlays, ("ui:蚂蚁森林",), 0.90)
        return None

    def _energy_rain(self, observation, tree, labels, overlays):
        joined = " ".join(labels)
        if tree is not None and (
            (_visible(tree, "恭喜获得") and _has(joined, "绿色能量", "能量雨机会"))
            or (_visible(tree, "今日累计获取") and _has(joined, "绿色能量"))
        ):
            # After the first round the result page offers a friend gift. It
            # is a distinct workflow state: tapping the first gift unlocks
            # the second round, while tapping the stale "立即开启" label would
            # only reopen this same result page.
            if _visible(tree, "送TA机会"):
                return self._screen(Page.ENERGY_RAIN_GIFT, observation, tree, overlays, {
                    "gift_first": ("送TA机会",), "close": ("返回",),
                })
            return self._screen(Page.ENERGY_RAIN_RESULT, observation, tree, overlays, {
                "close": ("返回",),
            })
        if tree is not None and _visible(tree, "立即开始", "立即开启"):
            return self._screen(Page.ENERGY_RAIN, observation, tree, overlays, {
                "start": ("立即开始", "立即开启"),
            })
        if tree is not None and _visible(tree, "本次获得", "能量雨结束"):
            return self._screen(Page.ENERGY_RAIN_RESULT, observation, tree, overlays, {
                "close": ("关闭", "返回"),
            })
        if observation.screenshot and not joined and detect_green_energy_balls(observation.screenshot, rain=True):
            return DetectedScreen(Page.ENERGY_RAIN_GAME, observation, overlays=overlays, evidence=("cv:rain_balls",), confidence=0.75)
        return None

    def _family_tasks(self, observation: Observation, tree: UiTree, overlays):
        mapping = {
            "donate": ("去捐蛋",),
            "donation_done": ("每日捐蛋做好事（1/1）", "每日捐蛋做好事(1/1)"),
            "meal": ("去请客",),
            "meal_unavailable": (
                "11点后可来请客", "请家人吃一顿美食（1/3）", "请家人吃一顿美食(1/3)"
            ),
            "feed": ("去喂食",),
            "feed_done": ("帮喂家人小鸡（1/1）", "帮喂家人小鸡(1/1)"),
            "confirm": ("确认",), "close": ("关闭",),
        }
        return DetectedScreen(
            Page.MANOR_FAMILY_TASKS,
            observation,
            self._elements(observation, tree, mapping),
            overlays,
            ("family_task_markers",),
            0.95,
        )

    def _feed_tasks(self, observation: Observation, tree: UiTree, overlays):
        mapping = {
            "quiz": ("去答题",), "video": ("看庄园小视频",),
            "store": ("去杂货铺逛一逛",), "farm": ("去芭芭农场逛一逛",),
            "family_browse": ("去家庭逛一逛",), "kitchen": ("小鸡厨房",),
            "forest_browse": ("去蚂蚁森林逛一逛",), "grain_browse": ("去芝麻攒粒攻略逛一逛",),
            "village_browse": ("去蚂蚁新村逛一逛",), "member_browse": ("去支付宝会员签到",),
        }
        elements = self._elements(observation, tree, mapping)
        daily_nodes = [
            node
            for node in tree.nodes
            if node.bounds.valid
            and node.searchable_text.startswith("领取")
            and "饲料" in node.searchable_text
        ]
        if daily_nodes:
            node = max(daily_nodes, key=lambda item: item.bounds.left)
            elements["daily_claim"] = Element(
                "daily_claim",
                node.action_node.bounds,
                observation.id,
                node.text or node.description,
                True,
                node.enabled,
                "ui_tree:daily_claim",
            )
        for key, fragments in mapping.items():
            if action := tree.task_action(observation.id, key, fragments):
                elements[key] = action
        lottery_nodes = [
            node
            for node in tree.nodes
            if node.bounds.valid
            and "抽抽乐" in node.searchable_text
            and node.bounds.left < observation.width * 0.25
            and node.bounds.right < observation.width * 0.85
        ]
        for index, node in enumerate(lottery_nodes[:2]):
            actions = [
                candidate
                for candidate in tree.nodes
                if candidate.bounds.valid
                and candidate.bounds.left > observation.width * 0.70
                and abs(candidate.bounds.center[1] - node.bounds.center[1]) < 180
                and _has(candidate.searchable_text, "去完成", "去抽奖", "领取")
            ]
            action = max(actions, key=lambda item: item.bounds.left, default=node).action_node
            elements[f"lottery_{index}"] = Element(
                f"lottery_{index}", action.bounds, observation.id, node.text or node.description,
                action.clickable or action is node, action.enabled, "ui_tree"
            )
        return DetectedScreen(Page.MANOR_FEED_TASKS, observation, elements, overlays, ("ui:饲料任务",), 0.95)

    def _quiz(self, observation: Observation, tree: UiTree, overlays, result: bool):
        page = Page.MANOR_QUIZ_RESULT if result else Page.MANOR_QUIZ
        elements = self._elements(observation, tree, {"close": ("关闭",), "claim": ("去领取饲料",)})
        candidates = [
            node for node in tree.nodes
            if (node.text.startswith("A") or node.text.startswith("B")) and node.bounds.valid
        ]
        if len(candidates) < 2:
            candidates = [
                node
                for node in tree.nodes
                if node.bounds.valid
                and 0 < len(node.text.strip()) <= 20
                and observation.height * 0.50 < node.bounds.center[1] < observation.height * 0.78
                and observation.width * 0.25 < node.bounds.center[0] < observation.width * 0.75
                and "题目来源" not in node.text
            ]
        for index, node in enumerate(candidates[:2]):
            action = node.action_node
            elements[f"option_{index}"] = Element(
                f"option_{index}", action.bounds, observation.id, node.text, True, action.enabled, "ui_tree"
            )
        return DetectedScreen(page, observation, elements, overlays, ("quiz_markers",), 0.90)

    def _lottery(self, page: Page, observation: Observation, tree: UiTree, overlays):
        mapping = {
            "exchange": ("消耗饲料换机会", "去完成"),
            "confirm_exchange": ("确认兑换",), "draw": ("立即抽奖",), "close_reward": ("开心收下", "关闭"),
            "switch": ("切换",),
        }
        elements = self._elements(observation, tree, mapping)
        if action := tree.task_action(
            observation.id, "sign", ("每日签到",), ("签到", "领取")
        ):
            if "已" not in (action.text or ""):
                elements["sign"] = action
        if action := tree.task_action(
            observation.id,
            "store",
            ("去杂货铺逛一逛", "去森林市集逛一逛"),
            ("去逛逛", "去完成", "领取"),
        ):
            key = "claim" if "领取" in (action.text or "") else "store"
            elements[key] = action
        if action := tree.task_action(
            observation.id, "exchange", ("消耗饲料换机会",), ("去完成",)
        ):
            elements["exchange"] = action
        return DetectedScreen(page, observation, elements, overlays, ("lottery_markers",), 0.90)

    def _screen(self, page, observation, tree, overlays, mapping):
        return DetectedScreen(page, observation, self._elements(observation, tree, mapping), overlays, (f"rule:{page.value}",), 0.90)

    def _elements(self, observation: Observation, tree: UiTree, mapping: dict[str, tuple[str, ...]]):
        result: dict[str, Element] = {}
        for key, labels in mapping.items():
            if element := tree.element(observation.id, key, *labels, fragment=True):
                result[key] = element
        return result

    def _overlays(self, observation: Observation, tree: UiTree | None) -> Iterable[Overlay]:
        if tree is None:
            return ()
        joined = " ".join(tree.labels())
        definitions = (
            (OverlayType.FEED_OVERFLOW, ("饲料袋", "超出上限"), {"confirm_overflow": ("确认", "继续领取")}),
            (OverlayType.PRODUCT_QUIZ, ("猜价格赢饲料", "猜价格赢抽奖"), {"abandon_reward": ("放弃奖励",)}),
            (OverlayType.REWARD, ("获得奖励", "去蚂蚁森林收能量", "施肥挑战"), {"close_reward": ("我知道啦", "开心收下", "关闭")}),
            (OverlayType.CONFIRMATION, ("确认兑换", "确认喂食"), {"confirm": ("确认兑换", "确认")}),
            (
                OverlayType.FOOD_SELECTION,
                ("选择美食", "份美食请客吃饭"),
                {"confirm": ("确认",)},
            ),
        )
        result: list[Overlay] = []
        for overlay_type, markers, mapping in definitions:
            if any(marker in joined for marker in markers):
                elements = self._elements(observation, tree, mapping)
                # WebViews often expose several controls containing "关闭" at
                # once.  For modal dismissal prefer an exact visible label so
                # a task-list close button is not selected behind the popup.
                if "close_reward" in mapping:
                    exact = _modal_exact_element(
                        observation,
                        tree,
                        "close_reward",
                        mapping["close_reward"],
                    )
                    if exact is not None:
                        elements["close_reward"] = exact
                    elif overlay_type is OverlayType.REWARD and not _visible(tree, "获得奖励"):
                        # "施肥挑战" also exists as a persistent farm banner.
                        # Without a modal action away from the app bar it is
                        # background content, not an overlay.
                        continue
                result.append(Overlay(overlay_type, elements, markers, 0.95))
        return result


def _has(text: str, *markers: str) -> bool:
    return any(marker in text for marker in markers)


def _visible(tree: UiTree, *markers: str) -> bool:
    return any(
        node.bounds.valid and any(marker in node.searchable_text for marker in markers)
        for node in tree.nodes
    )


def _point_element(
    observation: Observation,
    key: str,
    point: tuple[int, int],
    source: str,
    confidence: float = 0.85,
) -> Element:
    x, y = point
    radius = max(28, observation.width // 40)
    return Element(
        key,
        Bounds(max(0, x - radius), max(0, y - radius), min(observation.width, x + radius), min(observation.height, y + radius)),
        observation.id,
        source=source,
        confidence=confidence,
    )


def _modal_exact_element(
    observation: Observation,
    tree: UiTree,
    key: str,
    labels: tuple[str, ...],
) -> Element | None:
    wanted = {label.strip() for label in labels}
    nodes = [
        node
        for node in tree.nodes
        if node.bounds.valid
        and observation.height * 0.15 < node.bounds.center[1] < observation.height * 0.95
        and (node.text.strip() in wanted or node.description.strip() in wanted)
    ]
    if not nodes:
        return None
    node = nodes[0]
    action = node.action_node
    return Element(
        key,
        action.bounds,
        observation.id,
        node.text or node.description,
        action.clickable or action is node,
        action.enabled,
        "ui_tree:modal_exact",
    )
