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


def detect_home(observation: Observation) -> DetectedPage | None:
    if observation.package != "com.eg.android.AlipayGphone" or observation.ui_tree is None:
        return None
    tree = observation.ui_tree
    if not tree.contains(("蚂蚁庄园",)) or not tree.contains(("蚂蚁森林",)):
        return None
    elements = {}
    manor = _element(observation, "manor", "蚂蚁庄园")
    forest = _element(observation, "forest", "蚂蚁森林")
    if manor:
        elements[manor.key] = manor
    if forest:
        elements[forest.key] = forest
    return DetectedPage(
        type=PageType.ALIPAY_HOME,
        observation=observation,
        elements=elements,
        evidence=("package=com.eg.android.AlipayGphone", "labels=蚂蚁庄园,蚂蚁森林"),
        confidence=1.0,
    )
