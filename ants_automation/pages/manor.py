from __future__ import annotations

from pathlib import Path

from ..domain.models import Bounds, DetectedPage, Observation, PageType, UIElement
from ..perception.vision import match_template


_TEMPLATES = Path(__file__).with_name("templates")


def _element(observation: Observation, key: str, label: str) -> UIElement | None:
    tree = observation.ui_tree
    if tree is None:
        return None
    node = tree.find_exact((label,), clickable_only=True)
    if node is None:
        return None
    return UIElement(
        key=key,
        text=node.text or node.content_description,
        bounds=node.bounds,
        clickable=node.action_bounds is not None,
        enabled=node.enabled,
        source="ui_tree",
        observation_timestamp=observation.timestamp,
    )


def _vision_element(
    observation: Observation,
    key: str,
    template_name: str,
    *,
    threshold: float = 0.9,
) -> tuple[UIElement, float] | None:
    if observation.screenshot_path is None:
        return None
    match = match_template(
        observation.screenshot_path,
        _TEMPLATES / template_name,
        threshold=threshold,
    )
    if match is None:
        return None
    return (
        UIElement(
            key=key,
            text=None,
            bounds=match.bounds,
            clickable=True,
            enabled=True,
            source=f"cv_template:{template_name}",
            observation_timestamp=observation.timestamp,
        ),
        match.confidence,
    )


def _vision_action_element(
    observation: Observation,
    key: str,
    template_name: str,
    action_offset: tuple[int, int, int, int] | None = None,
) -> tuple[UIElement, float] | None:
    if observation.screenshot_path is None:
        return None
    match = match_template(observation.screenshot_path, _TEMPLATES / template_name)
    if match is None:
        return None
    if action_offset is None:
        bounds = match.bounds
    else:
        left, top, right, bottom = action_offset
        bounds = Bounds(
            match.bounds.left + left,
            match.bounds.top + top,
            match.bounds.left + right,
            match.bounds.top + bottom,
        )
    return (
        UIElement(
            key=key,
            text=None,
            bounds=bounds,
            clickable=True,
            enabled=True,
            source=f"cv_template:{template_name}",
            observation_timestamp=observation.timestamp,
        ),
        match.confidence,
    )


def detect_feed_full(observation: Observation) -> DetectedPage | None:
    tree = observation.ui_tree
    if observation.package != "com.eg.android.AlipayGphone" or tree is None:
        return None
    if not tree.contains_fragment("饲料袋快满了") and not tree.contains_fragment("只能装下"):
        return None
    return DetectedPage(
        type=PageType.MANOR_FEED_FULL,
        observation=observation,
        evidence=("labels=饲料袋快满了/只能装下*",),
        confidence=1.0,
    )


def _label_element(observation: Observation, key: str, label: str) -> UIElement | None:
    tree = observation.ui_tree
    if tree is None:
        return None
    node = tree.find_exact((label,))
    if node is None:
        return None
    return UIElement(
        key=key,
        text=node.text or node.content_description,
        bounds=node.bounds,
        clickable=True,
        enabled=node.enabled,
        source="ui_tree_label",
        observation_timestamp=observation.timestamp,
    )


def _fragment_marker(observation: Observation, key: str, fragment: str) -> UIElement | None:
    tree = observation.ui_tree
    if tree is None:
        return None
    node = next(
        (
            item
            for item in tree.nodes
            if fragment.lower() in item.searchable_text and item.enabled and item.bounds.valid
        ),
        None,
    )
    if node is None:
        return None
    return UIElement(
        key=key,
        text=node.text or node.content_description,
        bounds=node.bounds,
        clickable=False,
        enabled=True,
        source="ui_tree_state",
        observation_timestamp=observation.timestamp,
    )


def _node_element(
    observation: Observation,
    key: str,
    node,
    *,
    source: str = "ui_tree",
) -> UIElement:
    bounds = node.action_bounds or node.bounds
    return UIElement(
        key=key,
        text=node.text or node.content_description,
        bounds=bounds,
        clickable=node.action_bounds is not None,
        enabled=node.enabled,
        source=source,
        observation_timestamp=observation.timestamp,
    )


def _task_action_element(
    observation: Observation,
    key: str,
    task_fragment: str,
    action_label: str,
) -> UIElement | None:
    tree = observation.ui_tree
    if tree is None:
        return None
    task = next(
        (
            node
            for node in tree.nodes
            if task_fragment in (node.text or node.content_description)
            and node.enabled
            and node.bounds.valid
        ),
        None,
    )
    if task is None:
        return None
    candidates = [
        node
        for node in tree.nodes
        if (node.text == action_label or node.content_description == action_label)
        and node.enabled
        and node.action_bounds is not None
        and node.action_bounds.valid
    ]
    if not candidates:
        return None
    task_y = task.bounds.center[1]
    node = min(candidates, key=lambda item: abs(item.action_bounds.center[1] - task_y))
    return _node_element(observation, key, node, source="ui_tree_task_action")


def detect_feed_tasks(observation: Observation) -> DetectedPage | None:
    tree = observation.ui_tree
    if observation.package != "com.eg.android.AlipayGphone" or tree is None:
        return None
    if not tree.contains(("饲料任务",)) or not tree.contains_fragment("完成任务后会获赠饲料"):
        return None

    elements = {}
    for key, template, offset in (
        ("claim_daily", "feed_daily_claim.png", None),
        ("quiz", "feed_quiz.png", None),
        ("claim_quiz_reward", "feed_quiz_claim.png", None),
        ("video", "feed_video.png", (1090, 140, 1310, 250)),
        ("claim_video_reward", "feed_video_reward.png", (1090, 140, 1310, 250)),
    ):
        match = _vision_action_element(observation, key, template, offset)
        if match is not None:
            element, confidence = match
            elements[key] = element
    daily_done = _fragment_marker(observation, "daily_claim_done", "已领取")
    if daily_done is not None:
        elements[daily_done.key] = daily_done
    lottery_nodes = [
        node for node in tree.nodes
        if "抽抽乐" in (node.text or node.content_description)
        and "去完成" in (node.text or node.content_description)
        and node.enabled and (node.action_bounds or node.bounds).valid
    ]
    for index, node in enumerate(lottery_nodes[:2]):
        elements[f"lottery_{index}"] = _node_element(
            observation, f"lottery_{index}", node, source="ui_tree_lottery_entry"
        )
    return DetectedPage(
        type=PageType.MANOR_FEED_TASKS,
        observation=observation,
        elements=elements,
        evidence=("labels=饲料任务,完成任务后会获赠饲料*",),
        confidence=1.0,
    )


def detect_feed_video_complete(observation: Observation) -> DetectedPage | None:
    if observation.package != "com.eg.android.AlipayGphone":
        return None
    popup = _vision_element(
        observation, "dismiss_video_popup", "feed_video_reward_popup.png"
    )
    complete = _vision_element(
        observation, "video_complete_marker", "feed_video_complete_1440.png"
    ) or _vision_element(
        observation, "video_complete_marker", "feed_video_complete_clear_1440.png"
    ) or _vision_element(
        observation, "video_complete_marker", "feed_video_complete.png"
    )
    # The orange popup button alone is not distinctive enough: donation pages
    # use the same style. A video overlay is valid only with the completion badge.
    if complete is None:
        return None
    elements = {}
    evidence = []
    if popup is not None:
        _, confidence = popup
        elements["dismiss_video_popup"] = UIElement(
            key="dismiss_video_popup",
            text=None,
            bounds=Bounds(1080, 1030, 1200, 1190),
            clickable=True,
            enabled=True,
            source="cv_layout:feed_video_reward_popup.png",
            observation_timestamp=observation.timestamp,
        )
        evidence.append(f"cv=feed_video_reward_popup.png:{confidence:.3f}")
    elif complete is not None:
        marker, confidence = complete
        elements[marker.key] = marker
        elements["leave_video"] = UIElement(
            key="leave_video",
            text=None,
            bounds=Bounds(20, 160, 170, 360),
            clickable=True,
            enabled=True,
            source="cv_layout:video_back",
            observation_timestamp=observation.timestamp,
        )
        evidence.append(f"cv=feed_video_complete:{confidence:.3f}")
    return DetectedPage(
        type=PageType.MANOR_FEED_VIDEO_COMPLETE,
        observation=observation,
        elements=elements,
        evidence=tuple(evidence),
        confidence=1.0,
    )


def detect_quiz(observation: Observation) -> DetectedPage | None:
    tree = observation.ui_tree
    if observation.package != "com.eg.android.AlipayGphone" or tree is None:
        return None
    if not tree.contains_fragment("题目来源"):
        return None
    options = sorted(
        (
            node
            for node in tree.nodes
            if node.class_name == "android.widget.TextView"
            and node.enabled
            and node.bounds.valid
            and 1500 <= node.bounds.top <= 2600
            and (node.text or node.content_description)
        ),
        key=lambda node: node.bounds.top,
    )
    if len(options) != 2:
        return None
    elements = {
        key: UIElement(
            key=key,
            text=node.text or node.content_description,
            bounds=node.bounds,
            clickable=True,
            enabled=True,
            source="ui_tree_quiz_option",
            observation_timestamp=observation.timestamp,
        )
        for key, node in zip(("answer_a", "answer_b"), options, strict=True)
    }
    return DetectedPage(
        type=PageType.MANOR_QUIZ,
        observation=observation,
        elements=elements,
        evidence=("labels=题目来源*,two_options",),
        confidence=1.0,
    )


def detect_quiz_result(observation: Observation) -> DetectedPage | None:
    tree = observation.ui_tree
    if observation.package != "com.eg.android.AlipayGphone" or tree is None:
        return None
    if not tree.contains_fragment("答案：") or not tree.contains(("去领取饲料",)):
        return None
    claim = _label_element(observation, "claim_quiz_feed", "去领取饲料")
    return DetectedPage(
        type=PageType.MANOR_QUIZ_RESULT,
        observation=observation,
        elements={claim.key: claim} if claim else {},
        evidence=("labels=答案：*,去领取饲料",),
        confidence=1.0 if claim else 0.8,
    )
def detect_donation(observation: Observation) -> DetectedPage | None:
    tree = observation.ui_tree
    if observation.package != "com.eg.android.AlipayGphone" or tree is None:
        return None
    if not tree.contains_fragment("我已助力") or not tree.contains(("去捐蛋",)):
        return None
    elements = {}
    first_project = _label_element(observation, "select_project", "去捐蛋")
    if first_project:
        elements[first_project.key] = first_project
    return DetectedPage(
        type=PageType.MANOR_DONATION,
        observation=observation,
        elements=elements,
        evidence=("labels=我已助力*,去捐蛋",),
        confidence=1.0 if first_project else 0.8,
    )


def detect_donation_project(observation: Observation) -> DetectedPage | None:
    tree = observation.ui_tree
    if observation.package != "com.eg.android.AlipayGphone" or tree is None:
        return None
    if (
        not tree.contains(("我要捐赠",))
        or not tree.contains(("立即捐蛋",))
        or not (
            tree.contains_fragment("当前还有")
            or tree.contains_fragment("当前进度")
        )
    ):
        return None
    elements = {}
    donate_now = _label_element(observation, "donate_now", "立即捐蛋")
    if donate_now:
        elements[donate_now.key] = donate_now
    return DetectedPage(
        type=PageType.MANOR_DONATION_PROJECT,
        observation=observation,
        elements=elements,
        evidence=("labels=我要捐赠,立即捐蛋,当前还有*|当前进度*",),
        confidence=1.0 if donate_now else 0.8,
    )


def detect_donation_confirm(observation: Observation) -> DetectedPage | None:
    tree = observation.ui_tree
    if observation.package != "com.eg.android.AlipayGphone" or tree is None:
        return None
    title = tree.find_exact(("捐爱心蛋",))
    unit = tree.find_exact(("颗",))
    buttons = [
        node
        for node in tree.nodes
        if node.text == "立即捐蛋" and node.enabled and node.bounds.valid
    ]
    if title is None or unit is None or not title.bounds.valid or not unit.bounds.valid or not buttons:
        return None
    button = max(buttons, key=lambda node: node.bounds.top)
    confirm = UIElement(
        key="confirm_donation",
        text=button.text,
        bounds=button.bounds,
        clickable=True,
        enabled=True,
        source="ui_tree_label",
        observation_timestamp=observation.timestamp,
    )
    return DetectedPage(
        type=PageType.MANOR_DONATION_CONFIRM,
        observation=observation,
        elements={confirm.key: confirm},
        evidence=("labels=捐爱心蛋,颗,立即捐蛋",),
        confidence=1.0,
    )


def detect_donation_reward(observation: Observation) -> DetectedPage | None:
    tree = observation.ui_tree
    if observation.package != "com.eg.android.AlipayGphone" or tree is None:
        return None
    if not tree.contains_fragment("本次捐了") or not tree.contains(("获取今日份幸运签",)):
        return None
    return DetectedPage(
        type=PageType.MANOR_DONATION_REWARD,
        observation=observation,
        evidence=("labels=本次捐了*,获取今日份幸运签",),
        confidence=1.0,
    )


def detect_family_walk(observation: Observation) -> DetectedPage | None:
    tree = observation.ui_tree
    if observation.package != "com.eg.android.AlipayGphone" or tree is None:
        return None
    if not tree.contains(("一起运动做公益",)) or not tree.contains_fragment("今日全家累计步数"):
        return None
    elements = {}
    donate = _label_element(observation, "donate_steps", "去捐步数")
    done = _fragment_marker(observation, "walk_done", "今日已完成捐步")
    close = _element(observation, "close", "关闭")
    for item in (donate, done, close):
        if item:
            elements[item.key] = item
    return DetectedPage(
        PageType.MANOR_FAMILY_WALK,
        observation,
        elements,
        ("labels=一起运动做公益,今日全家累计步数*",),
        1.0,
    )


def detect_walk_donation(observation: Observation) -> DetectedPage | None:
    tree = observation.ui_tree
    if observation.package != "com.eg.android.AlipayGphone" or tree is None:
        return None
    if not tree.contains(("行走捐",)):
        return None
    elements = {}
    donate = _label_element(observation, "donate_now", "立即捐步")
    dismiss = _label_element(observation, "dismiss_result", "知道了")
    done = _fragment_marker(observation, "walk_donated", "今日兑换公益金")
    for item in (donate, dismiss, done):
        if item:
            elements[item.key] = item
    return DetectedPage(
        PageType.MANOR_WALK_DONATION,
        observation,
        elements,
        ("labels=行走捐",),
        1.0,
    )


def detect_family(observation: Observation) -> DetectedPage | None:
    tree = observation.ui_tree
    if observation.package != "com.eg.android.AlipayGphone" or tree is None:
        return None
    if not tree.contains(("欢乐全家桶",)):
        return None
    elements = {}
    evidence = ["labels=欢乐全家桶"]
    sign_in = _element(observation, "sign_in", "立即签到")
    signed = _element(observation, "signed", "攒亲密度")
    donate = _element(observation, "donate", "去捐蛋")
    donation_done = _fragment_marker(
        observation,
        "donation_done",
        "每日捐蛋做好事(1/1)",
    )
    family_feed = _task_action_element(
        observation, "family_feed_task", "帮喂家人小鸡(0/1)", "去喂食"
    )
    family_feed_done = _fragment_marker(observation, "family_feed_done", "帮喂家人小鸡(1/1)")
    walk = _task_action_element(
        observation, "walk_task", "一起运动做公益(0/1)", "去捐步"
    )
    walk_done = _fragment_marker(observation, "walk_done", "一起运动做公益(1/1)")
    meal = _task_action_element(
        observation, "meal_task", "请家人吃一顿美食", "去请客"
    )
    meal_unavailable = None
    if tree.contains_fragment("请家人吃一顿美食") and meal is None:
        meal_unavailable = _fragment_marker(observation, "meal_unavailable", "请家人吃一顿美食")
    confirm_family_feed = next(
        (node for node in tree.nodes
         if (node.text or node.content_description).startswith("确认")
         and "亲密度+1" in (node.text or node.content_description)
         and node.enabled and node.bounds.valid),
        None,
    )
    if confirm_family_feed is not None:
        elements["confirm_family_feed"] = _node_element(
            observation, "confirm_family_feed", confirm_family_feed,
            source="ui_tree_family_feed_confirm",
        )
    if tree.contains_fragment("已选") and tree.contains(("亲密度+3",)):
        confirm_meal = _label_element(observation, "confirm_meal", "确认")
        if confirm_meal is not None:
            elements[confirm_meal.key] = confirm_meal
    close = _element(observation, "close", "关闭")
    for item in (
        sign_in, signed, donate, donation_done, family_feed, family_feed_done,
        walk, walk_done, meal, meal_unavailable, close,
    ):
        if item:
            elements[item.key] = item
    if "sign_in" not in elements:
        sign_in_match = _vision_element(observation, "sign_in", "family_sign_in.png")
        if sign_in_match:
            sign_in, confidence = sign_in_match
            elements[sign_in.key] = sign_in
            evidence.append(f"cv=family_sign_in.png:{confidence:.3f}")
    if "sign_in" not in elements and "close" not in elements:
        signed_match = _vision_element(observation, "signed", "family_signed.png")
        if signed_match:
            signed, confidence = signed_match
            elements[signed.key] = signed
            evidence.append(f"cv=family_signed.png:{confidence:.3f}")
    return DetectedPage(
        type=PageType.MANOR_FAMILY,
        observation=observation,
        elements=elements,
        evidence=tuple(evidence),
        confidence=1.0,
    )


def detect_manor_home(observation: Observation) -> DetectedPage | None:
    tree = observation.ui_tree
    if observation.package != "com.eg.android.AlipayGphone" or tree is None:
        return None
    if not tree.contains(("蚂蚁庄园",)):
        return None
    elements = {}
    evidence = ["labels=蚂蚁庄园"]
    for key, label in (("family", "家庭"), ("donate", "去捐蛋")):
        item = _element(observation, key, label)
        if item:
            elements[key] = item
    feed_family_nodes = [
        node for node in tree.nodes
        if node.text == "去喂食" or node.content_description == "去喂食"
        if node.enabled and (node.action_bounds or node.bounds).valid
    ]
    for index, node in enumerate(feed_family_nodes[:2]):
        elements[f"feed_family_{index}"] = _node_element(
            observation, f"feed_family_{index}", node, source="ui_tree_family_feed"
        )
    confirm_feed = _element(observation, "confirm_feed", "确认喂食")
    if confirm_feed:
        elements[confirm_feed.key] = confirm_feed
    if "family" not in elements:
        family_match = _vision_element(observation, "family", "manor_family.png")
        if family_match:
            family, confidence = family_match
            elements[family.key] = family
            evidence.append(f"cv=manor_family.png:{confidence:.3f}")
    for key, template_name in (
        ("reward", "manor_reward.png"),
        ("diary", "manor_diary_badge.png"),
        ("feed_tasks", "manor_feed_tasks.png"),
    ):
        threshold = 0.86 if key in {"reward", "feed_tasks"} else 0.9
        match = _vision_element(observation, key, template_name, threshold=threshold)
        if match:
            element, confidence = match
            elements[element.key] = element
            evidence.append(f"cv={template_name}:{confidence:.3f}")
    return DetectedPage(
        type=PageType.MANOR_HOME,
        observation=observation,
        elements=elements,
        evidence=tuple(evidence),
        confidence=0.8 if elements else 0.6,
    )
