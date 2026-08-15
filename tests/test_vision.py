from pathlib import Path

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from ants_automation.perception.vision import match_template
from ants_automation.domain.models import Bounds
from ants_automation.perception.energy import detect_energy_balls


def test_template_match_returns_unique_bounds(tmp_path: Path):
    rng = np.random.default_rng(42)
    template = rng.integers(0, 256, size=(20, 30), dtype=np.uint8)
    screenshot = np.zeros((100, 120), dtype=np.uint8)
    screenshot[40:60, 50:80] = template
    screenshot_path = tmp_path / "screen.png"
    template_path = tmp_path / "template.png"
    cv2.imwrite(str(screenshot_path), screenshot)
    cv2.imwrite(str(template_path), template)

    match = match_template(screenshot_path, template_path)

    assert match is not None
    assert match.bounds == Bounds(50, 40, 80, 60)


def test_template_match_rejects_ambiguous_candidates(tmp_path: Path):
    rng = np.random.default_rng(42)
    template = rng.integers(0, 256, size=(20, 30), dtype=np.uint8)
    screenshot = np.zeros((100, 120), dtype=np.uint8)
    screenshot[10:30, 10:40] = template
    screenshot[60:80, 70:100] = template
    screenshot_path = tmp_path / "screen.png"
    template_path = tmp_path / "template.png"
    cv2.imwrite(str(screenshot_path), screenshot)
    cv2.imwrite(str(template_path), template)

    assert match_template(screenshot_path, template_path) is None


def test_energy_ball_detector_finds_green_circle():
    image = np.zeros((800, 400, 3), dtype=np.uint8)
    cv2.circle(image, (220, 330), 32, (40, 240, 90), -1)
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    points = detect_energy_balls(encoded.tobytes())
    assert len(points) == 1
    assert abs(points[0][0] - 220) <= 2
    assert abs(points[0][1] - 330) <= 2
