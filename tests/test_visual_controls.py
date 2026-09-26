import cv2
import numpy as np

from domain_data import Observation
from screen_perception.vision import manor_diary_entry, roaming_chicken_target


def test_diary_entry_detects_red_book_in_calibrated_home_band():
    image = np.zeros((1600, 720, 3), dtype=np.uint8)
    cv2.rectangle(image, (485, 808), (545, 860), (20, 30, 235), -1)
    obs = Observation("home", 0.0, 720, 1600, "alipay", [], page="manor", image=image)

    target = manor_diary_entry(obs)

    assert target is not None
    assert target.text == "小鸡日记"
    assert target.observation == obs.id
    assert 485 <= target.point[0] <= 545


def test_diary_entry_ignores_red_objects_outside_calibrated_band():
    image = np.zeros((1600, 720, 3), dtype=np.uint8)
    cv2.rectangle(image, (100, 808), (180, 880), (20, 30, 235), -1)
    obs = Observation("home", 0.0, 720, 1600, "alipay", [], page="manor", image=image)

    assert manor_diary_entry(obs) is None


def test_roaming_chicken_uses_transient_hand_cue_to_choose_left_target():
    stable_image = np.zeros((1600, 720, 3), dtype=np.uint8)
    hint_image = stable_image.copy()
    cv2.rectangle(hint_image, (275, 1135), (415, 1270), (255, 255, 255), -1)
    hint = Observation("hint", 0.0, 720, 1600, "alipay", [],
                       page="manor_friend", image=hint_image)
    stable = Observation("stable", 1.0, 720, 1600, "alipay", [],
                         page="manor_friend", image=stable_image)

    target = roaming_chicken_target(hint, stable)

    assert target is not None
    assert target.observation == stable.id
    assert target.point[0] < stable.width / 2
    assert target.point[1] == round(stable.height * .69)
