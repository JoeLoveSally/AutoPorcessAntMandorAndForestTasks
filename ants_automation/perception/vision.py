from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..domain.models import Bounds


@dataclass(frozen=True)
class TemplateMatch:
    bounds: Bounds
    confidence: float


def match_template(
    screenshot_path: Path,
    template_path: Path,
    *,
    threshold: float = 0.9,
    ambiguity_margin: float = 0.02,
) -> TemplateMatch | None:
    import cv2

    screenshot = cv2.imread(str(screenshot_path), cv2.IMREAD_GRAYSCALE)
    template = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
    if screenshot is None or template is None:
        return None
    height, width = template.shape
    if height > screenshot.shape[0] or width > screenshot.shape[1]:
        return None

    scores = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
    _, best_score, _, best_location = cv2.minMaxLoc(scores)
    if best_score < threshold:
        return None

    x, y = best_location
    suppressed = scores.copy()
    left = max(0, x - width // 2)
    top = max(0, y - height // 2)
    right = min(suppressed.shape[1], x + width // 2 + 1)
    bottom = min(suppressed.shape[0], y + height // 2 + 1)
    suppressed[top:bottom, left:right] = -1.0
    _, second_score, _, _ = cv2.minMaxLoc(suppressed)
    if second_score >= threshold and best_score - second_score < ambiguity_margin:
        return None

    return TemplateMatch(
        bounds=Bounds(x, y, x + width, y + height),
        confidence=float(best_score),
    )
