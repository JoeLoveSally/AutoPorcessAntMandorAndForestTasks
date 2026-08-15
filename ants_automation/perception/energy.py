from __future__ import annotations


def detect_energy_balls(png: bytes) -> list[tuple[int, int]]:
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("Energy-rain detection requires the vision dependencies") from exc

    image = cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return []
    height, width = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (35, 90, 100), (90, 255, 255))
    mask[: max(80, int(height * 0.05)), :] = 0
    mask[int(height * 0.82) :, :] = 0
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    found: list[tuple[int, int, float]] = []
    min_area = max(300.0, width * height * 0.00012)
    max_area = width * height * 0.012
    for contour in contours:
        area = cv2.contourArea(contour)
        if not min_area <= area <= max_area:
            continue
        (x, y), radius = cv2.minEnclosingCircle(contour)
        if radius < width * 0.018 or radius > width * 0.09:
            continue
        circularity = area / max(1.0, 3.14159 * radius * radius)
        if circularity >= 0.45:
            found.append((int(x), int(y), area))
    found.sort(key=lambda item: (-item[1], -item[2]))
    return [(x, y) for x, y, _ in found[:10]]
