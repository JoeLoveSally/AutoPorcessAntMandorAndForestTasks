from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from domain_data import Bounds


@dataclass(frozen=True, slots=True)
class TemplateMatch:
    bounds: Bounds
    confidence: float
    second_confidence: float


def decode_png(content: bytes) -> np.ndarray:
    image = cv2.imdecode(np.frombuffer(content, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Invalid PNG data")
    return image


def match_template(
    screenshot: bytes,
    template_path: Path,
    threshold: float = 0.88,
    ambiguity_margin: float = 0.04,
) -> TemplateMatch | None:
    image = decode_png(screenshot)
    template = cv2.imread(str(template_path), cv2.IMREAD_COLOR)
    if template is None or template.shape[0] > image.shape[0] or template.shape[1] > image.shape[1]:
        return None
    values = cv2.matchTemplate(image, template, cv2.TM_CCOEFF_NORMED)
    _, maximum, _, location = cv2.minMaxLoc(values)
    suppressed = values.copy()
    x, y = location
    height, width = template.shape[:2]
    suppressed[max(0, y - height // 2) : y + height, max(0, x - width // 2) : x + width] = -1
    _, second, _, _ = cv2.minMaxLoc(suppressed)
    if maximum < threshold or maximum - second < ambiguity_margin:
        return None
    return TemplateMatch(Bounds(x, y, x + width, y + height), float(maximum), float(second))


def detect_green_energy_balls(content: bytes, rain: bool = False) -> list[tuple[int, int, float]]:
    image = decode_png(content)
    height, width = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (35, 75, 85), (90, 255, 255))
    if rain:
        mask[: int(height * 0.08), :] = 0
        mask[int(height * 0.88) :, :] = 0
    else:
        mask[: int(height * 0.17), :] = 0
        mask[int(height * 0.52) :, :] = 0
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    minimum = width * height * (0.00009 if rain else 0.00015)
    maximum = width * height * 0.015
    result: list[tuple[int, int, float]] = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if not minimum <= area <= maximum:
            continue
        (x, y), radius = cv2.minEnclosingCircle(contour)
        if radius <= 0:
            continue
        if not rain and (radius < width * 0.04 or not width * 0.10 < x < width * 0.85):
            continue
        fill = area / (math.pi * radius * radius)
        if fill < 0.38:
            continue
        result.append((round(x), round(y), float(fill)))
    result.sort(key=lambda point: (-point[1], -point[2]))
    return result


def detect_yellow_right_button(content: bytes) -> tuple[int, int] | None:
    image = decode_png(content)
    height, width = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (15, 90, 130), (45, 255, 255))
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask)
    candidates: list[tuple[int, tuple[int, int]]] = []
    for left, top, item_width, item_height, area in stats[1:count]:
        center = (left + item_width // 2, top + item_height // 2)
        if left + item_width < width * 0.88:
            continue
        if not height * 0.45 < center[1] < height * 0.80:
            continue
        if item_width < width * 0.12 or item_height < height * 0.025:
            continue
        candidates.append((int(area), center))
    return max(candidates, default=(0, None))[1]


def detect_manor_home_controls(content: bytes) -> dict[str, tuple[int, int, float]]:
    image = decode_png(content)
    height, width = image.shape[:2]
    result: dict[str, tuple[int, int, float]] = {
        "feed_tasks": (round(width * 0.282), round(height * 0.922), 0.90),
        "family": (round(width * 0.445), round(height * 0.922), 0.90),
    }
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    red = cv2.bitwise_or(
        cv2.inRange(hsv, (0, 90, 115), (12, 255, 255)),
        cv2.inRange(hsv, (165, 80, 100), (179, 255, 255)),
    )
    count, _, stats, centers = cv2.connectedComponentsWithStats(red)
    reward_candidates: list[tuple[int, tuple[int, int]]] = []
    diary_candidates: list[tuple[int, tuple[int, int]]] = []
    for (_left, _top, item_width, item_height, area), (x, y) in zip(
        stats[1:count], centers[1:count], strict=True
    ):
        if (
            width * 0.25 < x < width * 0.55
            and height * 0.70 < y < height * 0.84
            and width * 0.06 < item_width < width * 0.22
            and height * 0.01 < item_height < height * 0.05
        ):
            reward_candidates.append((int(area), (round(x), round(y))))
        if (
            width * 0.55 < x < width * 0.85
            and height * 0.40 < y < height * 0.62
            and area > width * height * 0.0005
        ):
            diary_candidates.append((int(area), (round(x), round(y))))
    if reward_candidates:
        point = max(reward_candidates)[1]
        result["reward_friend"] = (*point, 0.82)
    if diary_candidates:
        # The notification badge sits above the red diary book and can have a
        # larger red area.  The book itself is the lower substantial component.
        point = max(diary_candidates, key=lambda item: item[1][1])[1]
        result["diary"] = (*point, 0.78)
    return result


def detect_family_task_controls(content: bytes) -> dict[str, tuple[int, int, float]]:
    image = decode_png(content)
    height, width = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    red = cv2.bitwise_or(
        cv2.inRange(hsv, (0, 75, 140), (15, 255, 255)),
        cv2.inRange(hsv, (160, 60, 120), (179, 255, 255)),
    )
    count, _, stats, centers = cv2.connectedComponentsWithStats(red)
    candidates: list[tuple[float, tuple[int, int], int, float]] = []
    for (left, top, item_width, item_height, area), (x, y) in zip(
        stats[1:count], centers[1:count], strict=True
    ):
        if (
            x > width * 0.72
            and width * 0.14 < item_width < width * 0.30
            and height * 0.018 < item_height < height * 0.065
            and height * 0.44 < y < height * 0.82
        ):
            region = hsv[
                max(0, top + item_height // 4) : min(height, top + item_height * 3 // 4),
                max(0, left + item_width // 8) : min(width, left + item_width * 7 // 8),
            ]
            saturation = float(np.median(region[:, :, 1])) if region.size else 0.0
            candidates.append((float(y / height), (round(x), round(y)), int(area), saturation))
    result: dict[str, tuple[int, int, float]] = {
        "close": (round(width * 0.95), round(height * 0.415), 0.88)
    }
    bands = {
        # The panel order is meal, feed, walking, donation.  Walking is
        # intentionally outside this project's single-pass task scope.
        "meal": (0.50, "meal_unavailable"),
        "feed": (0.595, "feed_done"),
        "donate": (0.776, "donation_done"),
    }
    for key, (expected, disabled_key) in bands.items():
        options = [item for item in candidates if abs(item[0] - expected) < 0.045]
        if options:
            _, point, _, saturation = max(options, key=lambda item: item[2])
            result[key if saturation >= 120 else disabled_key] = (*point, 0.86)
    return result


def detect_modal_scrim(content: bytes) -> tuple[int, int, float] | None:
    """Detect a Canvas-drawn modal: dimmed page, raised card, bottom-centre X.

    Alipay activity promos (forest anniversary skins, game-centre cash popups,
    the kitchen recipe card) render as one image, so the accessibility tree
    cannot see them and taps on the page underneath are swallowed by the scrim.
    The shared real-device signature is a dimmed frame, a brighter centre, and
    one compact X blob on the vertical centreline below the card, sitting on
    dark scrim.  Returns the X control centre so the overlay can be dismissed
    without coordinate guessing, or ``None`` when the signature does not match.
    """
    image = decode_png(content)
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    card = gray[int(height * 0.27) : int(height * 0.67), int(width * 0.14) : int(width * 0.86)]
    corners = np.concatenate(
        (
            gray[: int(height * 0.12), : int(width * 0.18)].ravel(),
            gray[: int(height * 0.12), int(width * 0.82) :].ravel(),
        )
    )
    if not (card.size and corners.size):
        return None
    if np.mean(corners) >= 95 or np.mean(card) <= np.mean(corners) + 40:
        return None
    band = gray[int(height * 0.70) : int(height * 0.92), int(width * 0.44) : int(width * 0.56)]
    if not band.size:
        return None
    _, thresholded = cv2.threshold(band, 110, 255, cv2.THRESH_BINARY)
    count, _, stats, centers = cv2.connectedComponentsWithStats(thresholded)
    candidates = [
        ((x, y), (left, top, box_width, box_height, area))
        for (left, top, box_width, box_height, area), (x, y) in zip(
            stats[1:count], centers[1:count], strict=True
        )
        # The X is compact; large page controls and full-width text lines do
        # not fit this box, and neither do tiny texture specks.
        if 30 <= box_width <= 200
        and 30 <= box_height <= 200
        and area >= 600
    ]
    if not candidates:
        return None
    # The X sits below every other central element (pagination dots, notice
    # text), so take the southernmost candidate.
    (x, y), (left, top, box_width, box_height, _area) = max(
        candidates, key=lambda item: item[0][1]
    )
    surround = band[
        max(0, top - 30) : top + box_height + 30,
        max(0, left - 30) : left + box_width + 30,
    ]
    if float(np.mean(surround)) >= 95:
        return None
    absolute_x = int(width * 0.44) + round(x)
    absolute_y = int(height * 0.70) + round(y)
    return absolute_x, absolute_y, 0.90


def detect_chicken_kitchen_controls(
    content: bytes,
) -> dict[str, tuple[int, int, float]] | None:
    """Detect the Canvas-only chicken-kitchen page and its visible controls.

    Alipay exposes this mini-app as one WebView image, so neither the page title
    nor its buttons appear in the accessibility tree.  The kitchen has a
    stable responsive layout: a large orange cook button in the bottom-right,
    an ingredient tree in the upper-left, and an optional recipe card over a
    dimmed background.  Coordinates are expressed as screen ratios so the
    detector is not tied to the calibration phone's pixel resolution.
    """
    image = decode_png(content)
    height, width = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    orange = cv2.inRange(hsv, (5, 85, 120), (38, 255, 255))
    count, _, stats, centers = cv2.connectedComponentsWithStats(orange)

    cook_candidates: list[tuple[int, tuple[int, int]]] = []
    for (_left, _top, item_width, item_height, area), (x, y) in zip(
        stats[1:count], centers[1:count], strict=True
    ):
        if (
            x > width * 0.62
            and y > height * 0.86
            and item_width > width * 0.25
            and item_height > height * 0.035
        ):
            cook_candidates.append((int(area), (round(x), round(y))))

    # The recipe card is a different modal family: its X floats over the light
    # kitchen bottom panel instead of a dark scrim, so it keeps the narrow
    # close-region signature that was calibrated on the real page.
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    close_region = gray[
        int(height * 0.80) : int(height * 0.88),
        int(width * 0.43) : int(width * 0.57),
    ]
    scrim = None
    if (
        close_region.size
        and np.mean(close_region > 225) > 0.03
        and np.mean(close_region < 70) > 0.30
    ):
        bright_rows, bright_columns = np.nonzero(close_region > 225)
        if bright_rows.size:
            scrim = (
                int(width * 0.43) + round(float(bright_columns.mean())),
                int(height * 0.80) + round(float(bright_rows.mean())),
                0.90,
            )
        else:
            scrim = (round(width * 0.50), round(height * 0.84), 0.90)
    if not cook_candidates and scrim is None:
        return None

    result: dict[str, tuple[int, int, float]] = {
        "donate_shop": (round(width * 0.17), round(height * 0.36), 0.82),
    }
    if cook_candidates:
        point = max(cook_candidates)[1]
        result["cook"] = (*point, 0.90)
    ingredient_orange = cv2.inRange(hsv, (5, 120, 150), (30, 255, 255))
    ingredient_region = ingredient_orange[
        int(height * 0.15) : int(height * 0.24),
        int(width * 0.22) : int(width * 0.38),
    ]
    if (
        ingredient_region.size
        and cv2.countNonZero(ingredient_region) / ingredient_region.size > 0.08
    ):
        result["claim_ingredient"] = (
            round(width * 0.292),
            round(height * 0.188),
            0.84,
        )

    red = cv2.bitwise_or(
        cv2.inRange(hsv, (0, 100, 150), (12, 255, 255)),
        cv2.inRange(hsv, (168, 90, 130), (179, 255, 255)),
    )
    red_count, _, red_stats, red_centers = cv2.connectedComponentsWithStats(red)
    daily_candidates: list[tuple[int, tuple[int, int]]] = []
    for (_left, _top, item_width, item_height, area), (x, y) in zip(
        red_stats[1:red_count], red_centers[1:red_count], strict=True
    ):
        if (
            x > width * 0.72
            and height * 0.68 < y < height * 0.83
            and item_width > width * 0.14
            and item_height > height * 0.025
        ):
            daily_candidates.append((int(area), (round(x), round(y))))
    if daily_candidates:
        point = max(daily_candidates)[1]
        result["daily_ingredient"] = (*point, 0.86)
    if scrim is not None:
        result = {"close": scrim}
    return result


def detect_kitchen_donate_controls(
    content: bytes,
) -> dict[str, tuple[int, int, float]] | None:
    """Detect the Canvas-only love-ingredient shop and its optional claim."""
    image = decode_png(content)
    height, width = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    lower = hsv[int(height * 0.32) :, :, :]
    brown = cv2.inRange(lower, (0, 75, 25), (28, 255, 190))
    if brown.size == 0 or cv2.countNonZero(brown) / brown.size < 0.42:
        return None

    result: dict[str, tuple[int, int, float]] = {}
    red = cv2.bitwise_or(
        cv2.inRange(hsv, (0, 110, 150), (12, 255, 255)),
        cv2.inRange(hsv, (168, 100, 140), (179, 255, 255)),
    )
    count, _, stats, centers = cv2.connectedComponentsWithStats(red)
    candidates: list[tuple[int, tuple[int, int]]] = []
    for (_left, _top, item_width, item_height, area), (x, y) in zip(
        stats[1:count], centers[1:count], strict=True
    ):
        if (
            x > width * 0.55
            and height * 0.22 < y < height * 0.38
            and item_width > width * 0.14
            and item_height > height * 0.025
        ):
            candidates.append((int(area), (round(x), round(y))))
    if candidates:
        point = max(candidates)[1]
        result["claim"] = (*point, 0.88)
    return result
