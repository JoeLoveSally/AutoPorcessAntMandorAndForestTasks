from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from domain_data import Bounds, Element

_BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


@dataclass(slots=True)
class UiNode:
    text: str
    description: str
    resource_id: str
    class_name: str
    bounds: Bounds
    clickable: bool
    enabled: bool
    parent: UiNode | None = field(default=None, repr=False)
    children: list[UiNode] = field(default_factory=list, repr=False)

    @property
    def searchable_text(self) -> str:
        return " ".join(value for value in (self.text, self.description, self.resource_id) if value)

    @property
    def action_node(self) -> UiNode:
        node: UiNode | None = self
        while node is not None:
            if node.clickable and node.enabled and node.bounds.valid:
                return node
            node = node.parent
        return self


class UiTree:
    def __init__(self, roots: list[UiNode]):
        self.roots = roots
        self.nodes = list(_walk(roots))

    @classmethod
    def from_bytes(cls, content: bytes) -> UiTree:
        root = ET.fromstring(content)
        roots = [_parse_node(item, None) for item in root if item.tag == "node"]
        return cls(roots)

    def labels(self) -> tuple[str, ...]:
        return tuple(node.searchable_text for node in self.nodes if node.searchable_text)

    def find_exact(self, *labels: str) -> UiNode | None:
        wanted = {label.strip() for label in labels}
        matches = [
            node
            for node in self.nodes
            if node.text.strip() in wanted or node.description.strip() in wanted
        ]
        return _prefer_visible(matches)

    def find_fragment(self, *fragments: str) -> UiNode | None:
        matches = [
            node
            for node in self.nodes
            if any(fragment in node.searchable_text for fragment in fragments)
        ]
        return _prefer_visible(matches, fragments)

    def find_all_fragment(self, *fragments: str) -> list[UiNode]:
        return [node for node in self.nodes if any(fragment in node.searchable_text for fragment in fragments)]

    def contains(self, *fragments: str) -> bool:
        return self.find_fragment(*fragments) is not None

    def element(self, observation_id: str, key: str, *labels: str, fragment: bool = False) -> Element | None:
        node = self.find_fragment(*labels) if fragment else self.find_exact(*labels)
        if node is None or not node.bounds.valid:
            return None
        action = node.action_node
        return Element(
            key=key,
            text=node.text or node.description,
            bounds=action.bounds,
            clickable=action.clickable or action is node,
            enabled=action.enabled,
            source="ui_tree",
            observation_id=observation_id,
        )

    def task_action(
        self,
        observation_id: str,
        key: str,
        task_fragments: tuple[str, ...],
        action_labels: tuple[str, ...] = ("去完成", "去逛逛", "去答题", "领取", "签到"),
    ) -> Element | None:
        task = self.find_fragment(*task_fragments)
        if task is None or not task.bounds.valid:
            return None
        candidates = [
            node
            for node in self.nodes
            if any(label in node.searchable_text for label in action_labels)
            and node.enabled
            and node.bounds.valid
            and node.bounds.left >= task.bounds.left
            and abs(node.bounds.center[1] - task.bounds.center[1]) <= max(180, task.bounds.bottom - task.bounds.top)
        ]
        if not candidates:
            return self.element(observation_id, key, *task_fragments, fragment=True)
        # Task cards often repeat the action text in the left description.
        # The actual action control is the rightmost matching node on the row.
        node = max(candidates, key=lambda item: (item.bounds.left, -abs(item.bounds.center[1] - task.bounds.center[1])))
        action = node.action_node
        return Element(
            key,
            action.bounds,
            observation_id,
            node.text or node.description,
            action.clickable or action is node,
            action.enabled,
            "ui_tree:task_action",
        )


def _walk(nodes: list[UiNode]):
    for node in nodes:
        yield node
        yield from _walk(node.children)


def _prefer_visible(nodes: list[UiNode], fragments: tuple[str, ...] = ()) -> UiNode | None:
    """Prefer the rendered copy when a WebView keeps hidden DOM nodes alive."""
    candidates = [node for node in nodes if node.bounds.valid] or nodes
    if not candidates or not fragments:
        return candidates[0] if candidates else None
    wanted = {fragment.strip() for fragment in fragments}

    def rank(node: UiNode) -> tuple[int, int]:
        exact = node.text.strip() in wanted or node.description.strip() in wanted
        action = node.action_node
        area = (action.bounds.right - action.bounds.left) * (
            action.bounds.bottom - action.bounds.top
        )
        # An exact label beats a fragment match inside promotional copy, and a
        # small tappable target beats a full-width banner: the alipay home
        # banner desc 来参加蚂蚁森林十周年啦 contains 蚂蚁森林, and tapping its
        # bounds opens the campaign instead of the forest.
        return (0 if exact else 1, area)

    return sorted(candidates, key=rank)[0]


def _parse_node(item: ET.Element, parent: UiNode | None) -> UiNode:
    match = _BOUNDS.fullmatch(item.attrib.get("bounds", ""))
    bounds = Bounds(*(map(int, match.groups()))) if match else Bounds(0, 0, 0, 0)
    node = UiNode(
        text=item.attrib.get("text", ""),
        description=item.attrib.get("content-desc", ""),
        resource_id=item.attrib.get("resource-id", ""),
        class_name=item.attrib.get("class", ""),
        bounds=bounds,
        clickable=item.attrib.get("clickable") == "true",
        enabled=item.attrib.get("enabled", "true") == "true",
        parent=parent,
    )
    node.children = [_parse_node(child, node) for child in item if child.tag == "node"]
    return node
