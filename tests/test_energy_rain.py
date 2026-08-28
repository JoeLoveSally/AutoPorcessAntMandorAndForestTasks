from __future__ import annotations

import cv2
import numpy as np

from workflow.forest.energy_rain import _balls, _is_game_frame


def test_game_frame_requires_large_blue_sky_board():
    game = np.full((1600, 720, 3), (235, 170, 80), dtype=np.uint8)
    start = np.full((1600, 720, 3), (45, 190, 55), dtype=np.uint8)

    assert _is_game_frame(game)
    assert not _is_game_frame(start)


def test_ball_detector_can_be_gated_away_from_green_start_page():
    start = np.full((1600, 720, 3), (35, 35, 35), dtype=np.uint8)
    cv2.circle(start, (360, 700), 55, (30, 240, 120), -1)

    assert _balls(start)
    assert not _is_game_frame(start)
