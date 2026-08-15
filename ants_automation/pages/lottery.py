from __future__ import annotations

from ..domain.models import DetectedPage, Observation, PageType, UIElement


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
    tasks = [node for node in tree.nodes if fragment in (node.text or node.content_description)]
    actions = [
        node for node in tree.nodes
        if (node.text in labels or node.content_description in labels)
        and node.enabled and (node.action_bounds or node.bounds).valid
    ]
    if not tasks or not actions:
        return None
    y = tasks[0].bounds.center[1]
    return min(actions, key=lambda node: abs((node.action_bounds or node.bounds).center[1] - y))


def detect_lottery_reward(observation: Observation) -> DetectedPage | None:
    tree = observation.ui_tree
    if observation.package != "com.eg.android.AlipayGphone" or tree is None:
        return None
    if not any(tree.contains_fragment(label) for label in ("恭喜获得", "获得奖励", "恭喜抽中")):
        return None
    node = tree.find_exact(
        ("确认", "开心收下", "收下", "我知道了", "做任务继续抽"), clickable_only=True
    )
    elements = {"confirm_reward": _from_node(observation, "confirm_reward", node)} if node else {}
    return DetectedPage(PageType.LOTTERY_REWARD, observation, elements, ("labels=reward",), 1.0)


def detect_lottery(observation: Observation) -> DetectedPage | None:
    tree = observation.ui_tree
    if observation.package != "com.eg.android.AlipayGphone" or tree is None:
        return None
    lottery_markers = ("立即抽奖", "抽奖", "抽抽乐", "森林寻宝", "剩余抽奖")
    if not any(tree.contains_fragment(marker) for marker in lottery_markers):
        return None
    elements: dict[str, UIElement] = {}
    no_draws = tree.contains_fragment("剩余0次") or tree.contains_fragment("0次抽奖")
    draw = None if no_draws else tree.find_exact(("立即抽奖", "抽奖"), clickable_only=True)
    if draw:
        elements["draw"] = _from_node(observation, "draw", draw)
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
    for key, fragment in (
        ("task_store", "去杂货铺逛一逛"),
        ("task_market", "去森林集市逛一逛"),
    ):
        node = _find_action(observation, fragment, ("去完成", "去逛逛"))
        if node:
            elements[key] = _from_node(observation, key, node)
    return DetectedPage(
        PageType.LOTTERY,
        observation,
        elements,
        tuple(f"label={marker}*" for marker in lottery_markers if tree.contains_fragment(marker)),
        0.9,
    )
