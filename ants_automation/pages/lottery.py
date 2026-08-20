from __future__ import annotations

from pathlib import Path
import re

from ..domain.models import Bounds, DetectedPage, Observation, PageType, UIElement
from ..perception.vision import match_template


_TEMPLATES = Path(__file__).with_name("templates")


def _from_node(observation: Observation, key: str, node) -> UIElement:
    return UIElement(
        key=key,
        text=node.text or node.content_description,
        bounds=node.action_bounds or node.bounds,
        clickable=True,
        enabled=node.enabled,
        source="ui_tree_lottery",
        observation_timestamp=observation.timestamp,
    )


def _find_action(observation: Observation, fragment: str, labels: tuple[str, ...]):
    tree = observation.ui_tree
    if tree is None:
        return None
    tasks = [
        node for node in tree.nodes
        if fragment in (node.text or node.content_description) and node.bounds.valid
    ]
    actions = [
        node for node in tree.nodes
        if (node.text in labels or node.content_description in labels)
        and node.enabled and (node.action_bounds or node.bounds).valid
    ]
    if not tasks or not actions:
        return None
    y = tasks[0].bounds.center[1]
    selected = min(actions, key=lambda node: abs((node.action_bounds or node.bounds).center[1] - y))
    if abs((selected.action_bounds or selected.bounds).center[1] - y) > 180:
        return None
    return selected


def detect_lottery_reward(observation: Observation) -> DetectedPage | None:
    tree = observation.ui_tree
    if observation.package != "com.eg.android.AlipayGphone" or tree is None:
        return None
    if tree.contains_fragment("件奖品") and tree.contains(("我知道了",)):
        return DetectedPage(
            PageType.LOTTERY_REWARD,
            observation,
            {"confirm_reward": UIElement(
                "confirm_reward", "我知道了", Bounds(356, 2124, 1084, 2284),
                True, True, "cv_layout:manor_lottery_reward_confirm",
                observation.timestamp,
            )},
            ("labels=*件奖品,我知道了",),
            1.0,
        )
    if not any(tree.contains_fragment(label) for label in ("恭喜获得", "获得奖励", "恭喜抽中")):
        return None
    node = tree.find_exact(
        ("确认", "开心收下", "收下", "我知道了", "做任务继续抽"), clickable_only=True
    )
    elements = {"confirm_reward": _from_node(observation, "confirm_reward", node)} if node else {}
    return DetectedPage(PageType.LOTTERY_REWARD, observation, elements, ("labels=reward",), 1.0)


def detect_external_browse(observation: Observation) -> DetectedPage | None:
    if observation.package != "com.eg.android.AlipayGphone" or observation.screenshot_path is None:
        return None
    complete = match_template(
        observation.screenshot_path,
        _TEMPLATES / "external_browse_complete.png",
        threshold=0.9,
    )
    product_popup = match_template(
        observation.screenshot_path,
        _TEMPLATES / "product_quiz_popup.png",
        threshold=0.9,
    )
    abandon = match_template(
        observation.screenshot_path,
        _TEMPLATES / "abandon_reward.png",
        threshold=0.78,
    )
    if abandon is not None and not (
        450 <= abandon.bounds.left <= 700
        and 2600 <= abandon.bounds.top <= 2920
    ):
        abandon = None
    if complete is None and product_popup is None and abandon is None:
        return None
    elements: dict[str, UIElement] = {}
    if complete is not None:
        elements["browse_complete"] = UIElement(
            "browse_complete", None, complete.bounds, False, True,
            "cv_template:external_browse_complete.png", observation.timestamp,
        )
    if product_popup is not None or abandon is not None:
        elements["abandon_reward"] = UIElement(
            "abandon_reward", "放弃奖励", Bounds(540, 2725, 900, 2875), True, True,
            "cv_layout:product_quiz_popup.png", observation.timestamp,
        )
    evidence = tuple(
        item for item in (
            f"cv=external_browse_complete.png:{complete.confidence:.3f}" if complete else None,
            f"cv=product_quiz_popup.png:{product_popup.confidence:.3f}"
            if product_popup else None,
            f"cv=abandon_reward.png:{abandon.confidence:.3f}" if abandon else None,
        ) if item is not None
    )
    return DetectedPage(PageType.EXTERNAL_TASK_COMPLETE, observation, elements, evidence, 1.0)


def detect_lottery(observation: Observation) -> DetectedPage | None:
    tree = observation.ui_tree
    if observation.package != "com.eg.android.AlipayGphone" or tree is None:
        return None
    confirm_exchange = tree.find_exact(("确认兑换",), clickable_only=True)
    if confirm_exchange is not None and tree.contains_fragment("消耗180g饲料"):
        return DetectedPage(
            PageType.LOTTERY,
            observation,
            {"confirm_exchange": _from_node(
                observation, "confirm_exchange", confirm_exchange
            )},
            ("labels=消耗180g饲料,确认兑换",),
            1.0,
        )

    lottery_markers = ("立即抽奖", "抽奖", "抽抽乐", "森林寻宝", "剩余抽奖")
    if not any(tree.contains_fragment(marker) for marker in lottery_markers):
        return None
    elements: dict[str, UIElement] = {}
    remaining = next(
        (
            match
            for node in tree.nodes
            if (match := re.search(r"还剩\s*(\d+)\s*次机会", node.text or node.content_description))
        ),
        None,
    )
    no_draws = tree.contains_fragment("剩余0次") or tree.contains_fragment("0次抽奖")
    draw = None if no_draws else tree.find_exact(("立即抽奖", "抽奖"), clickable_only=True)
    if draw:
        elements["draw"] = _from_node(observation, "draw", draw)
    elif remaining is not None and int(remaining.group(1)) > 0:
        elements["draw"] = UIElement(
            "draw", "立即抽奖", Bounds(430, 1830, 1010, 2070), True, True,
            "cv_layout:manor_lottery_draw", observation.timestamp,
        )
    if remaining is not None:
        elements["draw_count"] = UIElement(
            "draw_count", remaining.group(1), Bounds(740, 1816, 1048, 1880),
            False, True, "ui_tree_lottery_count", observation.timestamp,
        )
    if no_draws:
        marker = next(
            node for node in tree.nodes
            if "剩余0次" in node.searchable_text or "0次抽奖" in node.searchable_text
        )
        elements["draws_done"] = UIElement(
            "draws_done", marker.text or marker.content_description, marker.bounds,
            False, True, "ui_tree_lottery_state", observation.timestamp,
        )
    next_wheel = tree.find_exact(("下一个抽奖", "继续抽奖", "去另一个抽抽乐", "继续寻宝"), clickable_only=True)
    if next_wheel is None:
        next_wheel = next(
            (node for node in tree.nodes
             if "FE电动力" in (node.text or node.content_description)
             and node.enabled and node.action_bounds is not None and node.action_bounds.valid),
            None,
        )
    if next_wheel:
        elements["next_wheel"] = _from_node(observation, "next_wheel", next_wheel)
    exchange = _find_action(observation, "消耗饲料换机会", ("去完成",))
    if exchange:
        elements["exchange_feed"] = _from_node(
            observation, "exchange_feed", exchange
        )
    else:
        exchange_task = next(
            (node for node in tree.nodes
             if "消耗饲料换机会" in (node.text or node.content_description)
             and node.bounds.valid),
            None,
        )
        exchange_done = exchange_task is not None and any(
            (node.text or node.content_description).strip() == "已完成"
            and node.bounds.valid
            and abs(node.bounds.center[1] - exchange_task.bounds.center[1]) <= 180
            for node in tree.nodes
        )
        if exchange_done:
            elements["exchange_feed_done"] = UIElement(
                "exchange_feed_done", exchange_task.text or exchange_task.content_description,
                exchange_task.bounds, False, True, "ui_tree_lottery_state",
                observation.timestamp,
            )
    daily_claim = _find_action(observation, "每日签到", ("领取",))
    if daily_claim:
        elements["claim_daily_chance"] = _from_node(
            observation, "claim_daily_chance", daily_claim
        )
    else:
        daily_task = next(
            (node for node in tree.nodes
             if "每日签到" in (node.text or node.content_description)
             and node.bounds.valid),
            None,
        )
        daily_done = daily_task is not None and any(
            (node.text or node.content_description).strip() == "已完成"
            and node.bounds.valid
            and abs(node.bounds.center[1] - daily_task.bounds.center[1]) <= 180
            for node in tree.nodes
        )
        if daily_done:
            elements["daily_chance_done"] = UIElement(
                "daily_chance_done", daily_task.text or daily_task.content_description,
                daily_task.bounds, False, True, "ui_tree_lottery_state",
                observation.timestamp,
            )
    for key, claim_key, fragment in (
        ("task_store", "claim_task_store", "去杂货铺逛一逛"),
        ("task_market", "claim_task_market", "去森林集市逛一逛"),
    ):
        node = _find_action(observation, fragment, ("去完成", "去逛逛"))
        if node:
            elements[key] = _from_node(observation, key, node)
        claim = _find_action(observation, fragment, ("领取",))
        if claim:
            elements[claim_key] = _from_node(observation, claim_key, claim)
        task_text = next(
            (node.text or node.content_description for node in tree.nodes
             if fragment in (node.text or node.content_description)),
            "",
        )
        progress = re.search(r"[（(]\s*(\d+)\s*/\s*(\d+)\s*[）)]", task_text)
        if progress is not None and progress.group(1) == progress.group(2):
            marker = next(
                node for node in tree.nodes
                if fragment in (node.text or node.content_description)
            )
            elements[f"{key}_done"] = UIElement(
                f"{key}_done", task_text, marker.bounds, False, True,
                "ui_tree_lottery_state", observation.timestamp,
            )
    return DetectedPage(
        PageType.LOTTERY,
        observation,
        elements,
        tuple(f"label={marker}*" for marker in lottery_markers if tree.contains_fragment(marker)),
        0.9,
    )
