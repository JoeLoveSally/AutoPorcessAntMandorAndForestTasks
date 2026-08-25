import cv2
import numpy as np

from screen_perception.vision import detect_green_energy_balls, detect_yellow_right_button


def encode(image: np.ndarray) -> bytes:
    ok, content = cv2.imencode(".png", image)
    assert ok
    return content.tobytes()


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
