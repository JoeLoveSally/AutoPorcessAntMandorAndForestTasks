from __future__ import annotations

from ..domain.models import DetectedPage, Observation, PageType, UIElement


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


def detect_family(observation: Observation) -> DetectedPage | None:
    tree = observation.ui_tree
    if observation.package != "com.eg.android.AlipayGphone" or tree is None:
        return None
    if not tree.contains(("欢乐全家桶",)):
        return None
    elements = {}
    sign_in = _element(observation, "sign_in", "立即签到")
    donate = _element(observation, "donate", "去捐蛋")
    for item in (sign_in, donate):
        if item:
            elements[item.key] = item
    return DetectedPage(
        type=PageType.MANOR_FAMILY,
        observation=observation,
        elements=elements,
        evidence=("labels=欢乐全家桶",),
        confidence=1.0,
    )


def detect_manor_home(observation: Observation) -> DetectedPage | None:
    tree = observation.ui_tree
    if observation.package != "com.eg.android.AlipayGphone" or tree is None:
        return None
    if not tree.contains(("蚂蚁庄园",)):
        return None
    elements = {}
    for key, label in (("family", "家庭"), ("donate", "去捐蛋")):
        item = _element(observation, key, label)
        if item:
            elements[key] = item
    return DetectedPage(
        type=PageType.MANOR_HOME,
        observation=observation,
        elements=elements,
        evidence=("labels=蚂蚁庄园",),
        confidence=0.8 if elements else 0.6,
    )
