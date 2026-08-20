from __future__ import annotations

from ..domain.models import DetectedPage, Observation, PageType, UIElement


def _element(observation: Observation, key: str, labels: tuple[str, ...], fragment=False):
    tree = observation.ui_tree
    if tree is None:
        return None
    if fragment:
        node = next(
            (node for node in tree.nodes if any(label in (node.text or node.content_description) for label in labels)
             and node.enabled and (node.action_bounds or node.bounds).valid),
            None,
        )
    else:
        node = tree.find_exact(labels, clickable_only=True)
    if node is None:
        return None
    return UIElement(
        key, node.text or node.content_description, node.action_bounds or node.bounds,
        True, node.enabled, "ui_tree_forest", observation.timestamp,
    )


def detect_forest_friend_picker(observation: Observation) -> DetectedPage | None:
    tree = observation.ui_tree
    if observation.package != "com.eg.android.AlipayGphone" or tree is None:
        return None
    if not tree.contains_fragment("赠送") or not (
        tree.contains_fragment("更多好友") or tree.contains_fragment("送TA机会")
    ):
        return None
    elements = {}
    for key, labels, fragment in (
        ("friend_xiaobu", ("小布",), True),
        ("more_friends", ("更多好友",), True),
        ("confirm_gift", ("赠送", "确认赠送", "送TA机会"), False),
    ):
        item = _element(observation, key, labels, fragment)
        if item:
            elements[key] = item
    return DetectedPage(PageType.FOREST_FRIEND_PICKER, observation, elements, ("labels=赠送*,好友",), 0.9)


def detect_forest_rain_result(observation: Observation) -> DetectedPage | None:
    tree = observation.ui_tree
    if observation.package != "com.eg.android.AlipayGphone" or tree is None:
        return None
    if not any(tree.contains_fragment(label) for label in ("本次获得", "再来一次", "再玩一次")):
        return None
    elements = {}
    for key, labels in (
        ("again", ("再来一次", "再玩一次")),
        ("close", ("关闭", "完成")),
        ("more_friends", ("更多好友",)),
    ):
        item = _element(observation, key, labels, True)
        if item:
            elements[key] = item
    xiaobu = next(
        (node for node in tree.nodes if "小布" in (node.text or node.content_description)
         and node.enabled and node.bounds.valid),
        None,
    )
    if xiaobu is not None:
        send_nodes = [
            node for node in tree.nodes
            if "送" in (node.text or node.content_description)
            and node.enabled and (node.action_bounds or node.bounds).valid
        ]
        if send_nodes:
            send = min(send_nodes, key=lambda node: abs((node.action_bounds or node.bounds).center[1] - xiaobu.bounds.center[1]))
            elements["friend_xiaobu"] = UIElement(
                "friend_xiaobu", "小布", send.action_bounds or send.bounds,
                True, True, "ui_tree_rain_friend", observation.timestamp,
            )
    return DetectedPage(PageType.FOREST_RAIN_RESULT, observation, elements, ("labels=能量雨,result",), 0.9)


def detect_forest_rain(observation: Observation) -> DetectedPage | None:
    tree = observation.ui_tree
    if observation.package != "com.eg.android.AlipayGphone" or tree is None:
        return None
    if not tree.contains_fragment("能量雨") or not any(
        tree.contains_fragment(label) for label in ("倒计时", "点击绿色能量", "开始", "立即开启")
    ):
        return None
    start = _element(observation, "start", ("开始", "立即开始", "立即开启"), True)
    return DetectedPage(
        PageType.FOREST_RAIN, observation, {"start": start} if start else {}, ("labels=能量雨",), 0.9
    )


def detect_co_plant(observation: Observation) -> DetectedPage | None:
    tree = observation.ui_tree
    if observation.package != "com.eg.android.AlipayGphone" or tree is None:
        return None
    if not tree.contains_fragment("爱情合种"):
        return None
    elements = {}
    water = _element(observation, "water", ("为爱浇灌", "浇水", "立即浇水"), True)
    confirm = _element(observation, "confirm_water", ("浇水", "立即浇水"), False)
    increase = _element(observation, "increase_amount", ("+", "增加"), False)
    reward = _element(observation, "reward_ack", ("我知道啦", "我知道了", "收下"), False)
    amount_nodes = [
        node for node in tree.nodes
        if (node.text or node.content_description).strip() in {"20", "40", "60", "80", "100"}
        and node.bounds.valid
    ]
    amount_node = None
    if amount_nodes and increase is not None:
        amount_node = min(
            amount_nodes,
            key=lambda node: abs(node.bounds.center[1] - increase.bounds.center[1]),
        )
    amount = None
    if amount_node is not None:
        amount = UIElement(
            "amount_value", amount_node.text or amount_node.content_description,
            amount_node.bounds, False, True, "ui_tree_forest", observation.timestamp,
        )
    for item in (water, confirm, increase, reward, amount):
        if item:
            elements[item.key] = item
    return DetectedPage(PageType.FOREST_CO_PLANT, observation, elements, ("labels=爱情合种",), 1.0)


def detect_forest_home(observation: Observation) -> DetectedPage | None:
    tree = observation.ui_tree
    if observation.package != "com.eg.android.AlipayGphone" or tree is None:
        return None
    if not tree.contains(("蚂蚁森林",)):
        return None
    elements = {}
    for key, labels in (
        ("find_energy", ("找能量", "收能量")),
        ("energy_rain", ("能量雨",)),
        ("co_plant", ("合种",)),
        ("lottery", ("森林寻宝", "抽抽乐")),
    ):
        item = _element(observation, key, labels, True)
        if item:
            elements[key] = item
    energy_nodes = [
        node for node in tree.nodes
        if any(fragment in (node.text or node.content_description) for fragment in ("收取", "可收取", "g能量"))
        and node.enabled and (node.action_bounds or node.bounds).valid
    ]
    for index, node in enumerate(energy_nodes[:20]):
        elements[f"energy_{index}"] = UIElement(
            f"energy_{index}", node.text or node.content_description,
            node.action_bounds or node.bounds, True, True, "ui_tree_energy", observation.timestamp,
        )
    return DetectedPage(PageType.FOREST_HOME, observation, elements, ("labels=蚂蚁森林",), 0.8)
