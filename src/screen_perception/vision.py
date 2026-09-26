import re

import cv2
import numpy as np

from domain_data import Element


def quiz_options(obs):
    """Locate the two stacked answer pills of the daily quiz.

    Device evidence (2026-09-24, run a8c506): the 答答星球-themed question
    rendered both pills near-white (below the saturation-35 mask), so the
    color-contour path found zero boxes while OCR read both option texts
    cleanly (吸收热辐射 y0.59 / 反射热辐射 y0.68). The pills are always
    bottom-anchored below the question and above the 题目来源 footer, so a
    centered OCR text band in y(.42,.88) is the primary signal; the legacy
    colored geometry stays as the fallback for variants whose pills carry
    color but whose option text OCR missed. Anything other than exactly two
    candidates is returned as-is so the caller keeps its fail-closed guard.
    """
    band = sorted(
        (element for element in obs.elements
         if obs.height * .42 < element.point[1] < obs.height * .88
         and obs.width * .15 < element.point[0] < obs.width * .85
         and re.match(r"^[0-9A-Za-z一-鿿]", element.text.strip())),
        key=lambda element: element.point[1],
    )
    if len(band) == 2:
        return band
    colored = _colored_quiz_pills(obs)
    return colored if len(colored) == 2 else band


def _colored_quiz_pills(obs):
    if obs.image is None:
        return []
    hsv = cv2.cvtColor(obs.image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, 35, 130), (179, 255, 255))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for contour in contours:
        x,y,w,h = cv2.boundingRect(contour)
        if w > obs.width*.5 and obs.height*.025 < h < obs.height*.12 and obs.height*.25 < y < obs.height*.85:
            texts = [e for e in obs.elements if x < e.point[0] < x+w and y < e.point[1] < y+h]
            if texts:
                boxes.append(Element(" ".join(e.text for e in texts), (x,y,x+w,y+h), obs.id, "ocr+geometry"))
    return sorted(boxes, key=lambda e:e.point[1])


def manor_diary_entry(obs):
    """Locate the red diary book only within its calibrated manor-home band."""
    image = obs.image
    if image is None:
        return None
    height, width = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    red = cv2.bitwise_or(
        cv2.inRange(hsv, (0, 90, 115), (12, 255, 255)),
        cv2.inRange(hsv, (165, 80, 100), (179, 255, 255)),
    )
    count, _, stats, centers = cv2.connectedComponentsWithStats(red)
    candidates = []
    for (left, top, item_width, item_height, area), (x, y) in zip(
        stats[1:count], centers[1:count], strict=True
    ):
        if not (
            width * .65 < x < width * .88
            and height * .40 < y < height * .62
            and area > width * height * .0005
            and width * .035 < item_width < width * .16
            and height * .012 < item_height < height * .09
        ):
            continue
        candidates.append((int(area), round(x), round(y), left, top, item_width, item_height))
    if not candidates:
        return None
    # The notification badge is above the book; choose the lower substantial
    # red component to keep the tap inside the diary control.
    _, x, y, left, top, item_width, item_height = (
        int(value) for value in max(candidates, key=lambda item: item[2])
    )
    padding = max(8, width // 100)
    return Element(
        "小鸡日记",
        (max(0, left-padding), max(0, top-padding),
         min(width, left+item_width+padding), min(height, top+item_height+padding)),
        obs.id,
        "vision.manor_diary",
        .78,
    )


def roaming_chicken_target(hint_obs, stable_obs):
    """Infer which lower chicken the transient pointing-hand cue selected."""
    if hint_obs.image is None or stable_obs.image is None:
        return None
    if hint_obs.image.shape != stable_obs.image.shape:
        return None
    height, width = stable_obs.image.shape[:2]
    left, top = int(width * .15), int(height * .58)
    right, bottom = int(width * .85), int(height * .84)
    hsv = cv2.cvtColor(hint_obs.image, cv2.COLOR_BGR2HSV)
    warm = cv2.inRange(hsv, (0, 35, 170), (22, 210, 255))
    warm[:int(height * .68)] = 0
    warm[int(height * .84):] = 0
    warm[:, :left] = 0
    warm[:, right:] = 0

    def components(mask, min_area):
        count, _, stats, centers = cv2.connectedComponentsWithStats(mask)
        found = []
        for stat, center in zip(stats[1:count], centers[1:count], strict=True):
            _, y, item_width, item_height, area = stat
            if (
                area > width * height * min_area
                and width * .08 < item_width < width * .40
                and height * .05 < item_height < height * .20
                and top <= y < bottom
            ):
                found.append((area, center))
        return found

    cues = components(warm, .003)
    if not cues:
        difference = cv2.absdiff(hint_obs.image, stable_obs.image)
        changed = cv2.threshold(cv2.cvtColor(difference, cv2.COLOR_BGR2GRAY), 35, 255,
                                cv2.THRESH_BINARY)[1]
        clipped = np.zeros_like(changed)
        clipped[top:bottom, left:right] = changed[top:bottom, left:right]
        cues = components(clipped, .004)
    if not cues:
        return None
    _, (cue_x, _) = max(cues, key=lambda item: item[0])
    if abs(cue_x - width / 2) < width * .01:
        return None
    target_x = width * (.37 if cue_x < width / 2 else .76)
    target_y = height * .69
    half_width, half_height = width * .045, height * .035
    return Element(
        "外出小鸡",
        (round(target_x - half_width), round(target_y - half_height),
         round(target_x + half_width), round(target_y + half_height)),
        stable_obs.id,
        "vision.roaming_chicken",
        .75,
    )
