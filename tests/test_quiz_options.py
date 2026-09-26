"""quiz_options calibrated against the 2026-09-24 white-pill quiz frame.

Run a8c506: the 答答星球-themed question rendered both answer pills
near-white (HSV saturation below the legacy mask's 35), so the color
contours found zero boxes while OCR read both option texts cleanly. The
pills are bottom-anchored between the question and the 题目来源 footer,
which makes a centered OCR text band the primary detector.
"""

from domain_data import Element, Observation
from screen_perception.vision import quiz_options


def observation(elements):
    return Observation(
        "fixture", 0.0, 1440, 3200, "alipay", list(elements), "quiz"
    )


def test_white_pill_options_are_found_from_the_ocr_band():
    obs = observation([
        Element("3:32", (106, 58, 200, 104), "fixture"),
        Element("我们和地球", (591, 814, 850, 867), "fixture"),
        Element("为什么大多数热水瓶的内胆是银色的", (189, 962, 1251, 1025),
                "fixture"),
        Element("吸收热辐射", (556, 1861, 883, 1920), "fixture"),
        Element("反射热辐射", (554, 2106, 885, 2174), "fixture"),
        Element("题目来源一答答星球", (528, 2988, 914, 3032), "fixture"),
    ])

    options = quiz_options(obs)

    assert [element.text for element in options] == ["吸收热辐射", "反射热辐射"]


def test_single_character_judgement_options_survive_the_band_filter():
    obs = observation([
        Element("对", (600, 1861, 700, 1920), "fixture"),
        Element("错", (600, 2106, 700, 2174), "fixture"),
    ])

    assert [element.text for element in quiz_options(obs)] == ["对", "错"]


def test_a_stray_band_element_passes_through_for_the_fail_closed_guard():
    obs = observation([
        Element("吸收热辐射", (556, 1861, 883, 1920), "fixture"),
        Element("反射热辐射", (554, 2106, 885, 2174), "fixture"),
        Element("换一题", (620, 2400, 820, 2470), "fixture"),
    ])

    # No image means no color fallback; three candidates stay three so the
    # caller's exact-two guard still fails closed instead of guessing.
    assert len(quiz_options(obs)) == 3
