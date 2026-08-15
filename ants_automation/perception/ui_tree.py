from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from ..domain.models import Bounds

_BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


@dataclass(frozen=True)
class UiNode:
    text: str
    content_description: str
    resource_id: str
    class_name: str
    clickable: bool
    enabled: bool
    bounds: Bounds
    action_bounds: Bounds | None = None

    @property
    def searchable_text(self) -> str:
        return " ".join((self.text, self.content_description, self.resource_id)).lower()


class UiTree:
    def __init__(self, nodes: list[UiNode]):
        self.nodes = nodes

    @classmethod
    def from_file(cls, path: Path) -> "UiTree":
        return cls.from_xml(path.read_bytes())

    @classmethod
    def from_xml(cls, content: bytes | str) -> "UiTree":
        root = ET.fromstring(content)
        nodes: list[UiNode] = []

        def visit(element: ET.Element, inherited_action: Bounds | None = None) -> None:
            if element.tag != "node":
                for child in element:
                    visit(child, inherited_action)
                return
            match = _BOUNDS.fullmatch(element.attrib.get("bounds", ""))
            if not match:
                for child in element:
                    visit(child, inherited_action)
                return
            bounds = Bounds(*(int(value) for value in match.groups()))
            clickable = element.attrib.get("clickable") == "true"
            enabled = element.attrib.get("enabled", "true") == "true"
            action_bounds = bounds if clickable and enabled else inherited_action
            node = UiNode(
                text=element.attrib.get("text", ""),
                content_description=element.attrib.get("content-desc", ""),
                resource_id=element.attrib.get("resource-id", ""),
                class_name=element.attrib.get("class", ""),
                clickable=clickable,
                enabled=enabled,
                bounds=bounds,
                action_bounds=action_bounds,
            )
            nodes.append(node)
            for child in element:
                visit(child, action_bounds)

        visit(root)
        return cls(nodes)

    def find_exact(self, labels: tuple[str, ...], *, clickable_only: bool = False) -> UiNode | None:
        normalized = {label.strip().lower() for label in labels}
        candidates = [
            node for node in self.nodes
            if node.enabled and node.bounds.valid
            and (not clickable_only or node.action_bounds is not None)
            and (node.text.strip().lower() in normalized
                 or node.content_description.strip().lower() in normalized)
        ]
        if not candidates:
            return None
        node = sorted(candidates, key=lambda item: (not item.clickable, item.bounds.top))[0]
        if clickable_only and node.action_bounds is not None:
            return UiNode(
                text=node.text,
                content_description=node.content_description,
                resource_id=node.resource_id,
                class_name=node.class_name,
                clickable=True,
                enabled=True,
                bounds=node.action_bounds,
                action_bounds=node.action_bounds,
            )
        return node

    def contains(self, labels: tuple[str, ...]) -> bool:
        normalized = {label.strip().lower() for label in labels}
        return any(
            node.text.strip().lower() in normalized
            or node.content_description.strip().lower() in normalized
            for node in self.nodes
        )

    def contains_fragment(self, fragment: str) -> bool:
        normalized = fragment.strip().lower()
        return any(normalized in node.searchable_text for node in self.nodes)

    def visible_labels(self) -> tuple[str, ...]:
        values: list[str] = []
        for node in self.nodes:
            value = node.text or node.content_description
            if value and value not in values:
                values.append(value)
        return tuple(values)
