import cv2
import numpy as np

from screen_perception.vision import (
    detect_green_energy_balls,
    detect_love_plant_controls,
    detect_modal_scrim,
    detect_yellow_right_button,
)


def encode(image: np.ndarray) -> bytes:
    ok, content = cv2.imencode(".png", image)
    assert ok
    return content.tobytes()


def promo_scr_image(size: tuple[int, int] = (3200, 1440)) -> np.ndarray:
    """Draw the shared promo signature: dark scrim, raised card, centre X.

    The X blob is mid-gray on dark scrim, matching the forest anniversary
    skin banner and the game-centre cash popups captured on the real device.
    """
    height, width = size
    image = np.full((height, width, 3), 28, dtype=np.uint8)
    cv2.rectangle(image, (200, 860), (1240, 2150), (110, 150, 190), -1)
    cv2.circle(image, (722, 2734), 34, (140, 140, 140), 10)
    return image


def test_detects_tree_energy_ball_but_ignores_bottom_green():
    image = np.zeros((1000, 500, 3), dtype=np.uint8)
    cv2.circle(image, (220, 330), 30, (40, 230, 80), -1)
    cv2.circle(image, (220, 750), 30, (40, 230, 80), -1)
    points = detect_green_energy_balls(encode(image))
    assert len(points) == 1
    assert abs(points[0][0] - 220) <= 2
    assert abs(points[0][1] - 330) <= 2


def test_detects_right_side_one_click_button():
    image = np.zeros((1000, 500, 3), dtype=np.uint8)
    cv2.rectangle(image, (300, 570), (499, 640), (0, 220, 255), -1)
    point = detect_yellow_right_button(encode(image))
    assert point is not None
    assert point[0] > 390
    assert 590 < point[1] < 620


def test_tree_energy_ignores_small_icon_and_far_right_promotion():
    image = np.zeros((1600, 720, 3), dtype=np.uint8)
    cv2.circle(image, (390, 400), 48, (40, 230, 80), -1)
    cv2.circle(image, (370, 470), 13, (40, 230, 80), -1)
    cv2.circle(image, (640, 320), 40, (40, 230, 80), -1)
    points = detect_green_energy_balls(encode(image))
    assert len(points) == 1
    assert abs(points[0][0] - 390) <= 2


def test_modal_scrim_finds_bottom_centre_close_on_dark_scrim():
    point = detect_modal_scrim(encode(promo_scr_image()))
    assert point is not None
    x, y, confidence = point
    assert abs(x - 722) <= 4
    assert abs(y - 2734) <= 4
    assert confidence == 0.90


def test_modal_scrim_ignores_bright_page_and_flat_dark_page():
    assert detect_modal_scrim(encode(np.full((3200, 1440, 3), 200, dtype=np.uint8))) is None
    assert detect_modal_scrim(encode(np.full((3200, 1440, 3), 28, dtype=np.uint8))) is None


def test_modal_scrim_ignores_central_blob_on_bright_surround():
    # A compact central control on a bright page (no scrim) is not a promo.
    image = np.full((3200, 1440, 3), 170, dtype=np.uint8)
    cv2.rectangle(image, (200, 860), (1240, 2150), (225, 235, 240), -1)
    cv2.circle(image, (720, 2734), 34, (250, 250, 250), 10)
    assert detect_modal_scrim(encode(image)) is None


def test_love_plant_finds_centre_purple_pill():
    image = np.full((3200, 1440, 3), (240, 200, 250), dtype=np.uint8)
    cv2.ellipse(image, (720, 1599), (330, 92), 0, 0, 360, (205, 90, 180), -1)
    cv2.rectangle(image, (60, 2180), (1380, 2250), (205, 90, 180), -1)
    controls = detect_love_plant_controls(encode(image))
    assert controls is not None
    x, y, confidence = controls["water"]
    assert abs(x - 720) <= 4
    assert abs(y - 1599) <= 4
    assert confidence == 0.88


def test_love_plant_ignores_small_purple_decorations():
    image = np.full((3200, 1440, 3), (240, 200, 250), dtype=np.uint8)
    cv2.circle(image, (1085, 1862), 60, (205, 90, 180), -1)
    assert detect_love_plant_controls(encode(image)) is None
