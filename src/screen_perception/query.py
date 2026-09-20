"""Pure, evidence-preserving element lookup over an existing Observation.

No device I/O, OCR, business decision, or tap occurs here. A query scoped to a
card title cannot accidentally select an identically named button elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass

from domain_data import AutomationError, Element, Observation

Region = tuple[float, float, float, float]
FULL_SCREEN: Region = (0.0, 0.0, 1.0, 1.0)


@dataclass(frozen=True)
class ElementQuery:
    text: str
    region: Region = FULL_SCREEN
    card_title: str | None = None
    row_tolerance: float = 0.035
    require_right_of_title: bool = True


def find_elements(observation: Observation, query: ElementQuery) -> list[Element]:
    """Return all matching elements; the caller must reject ambiguity.

    card_title identifies an OCR/UI-Tree title anchor on the same horizontal
    task row. A missing/ambiguous title never falls back to a global button.
    """
    matches = observation.find(query.text, query.region)
    if query.card_title is None:
        return matches
    titles = observation.find(query.card_title)
    if len(titles) != 1:
        raise AutomationError(
            f"Expected one task-card title {query.card_title}: found {len(titles)}",
            "AMBIGUOUS",
        )
    anchor = titles[0]
    return [element for element in matches
            if element.observation == observation.id
            and abs(element.point[1] - anchor.point[1]) <= observation.height * query.row_tolerance
            and (not query.require_right_of_title or element.point[0] > anchor.point[0])]


def find_one(observation: Observation, query: ElementQuery) -> Element:
    matches = find_elements(observation, query)
    if len(matches) != 1:
        raise AutomationError(
            f"Expected unique element {query.text} in {query.card_title or 'page'}: found {len(matches)}",
            "AMBIGUOUS",
        )
    return matches[0]


def read_text(observation: Observation, pattern: str, region: Region = FULL_SCREEN) -> list[str]:
    """Read recognized text only; interpretation stays in the workflow."""
    return [element.text for element in observation.find(pattern, region)]
