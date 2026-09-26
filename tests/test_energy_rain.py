import cv2
import numpy as np

from device_bridge.realtime import Frame
from workflow.forest.energy_rain import Track, energy_balls, is_game_frame, safe_tap_point


def test_frame_maps_decode_coordinates_to_device():
    frame = Frame(np.zeros((1600, 720, 3), dtype=np.uint8), 1.0, 1, (1440, 3200))
    assert frame.to_device((360, 800)) == (720, 1600)


def test_track_predicts_falling_motion_at_touch_latency():
    track = Track(1, 100, 200, 1.0)
    track.update(102, 220, 1.05)
    assert track.predicted(.08, 1600) == (105, 252)


def test_game_frame_requires_large_blue_sky_board():
    game = np.full((1600, 720, 3), (235, 170, 80), dtype=np.uint8)
    start = np.full((1600, 720, 3), (45, 190, 55), dtype=np.uint8)
    assert is_game_frame(game)
    assert not is_game_frame(start)


def test_ball_detection_is_separate_from_game_frame_gate():
    start = np.full((1600, 720, 3), (35, 35, 35), dtype=np.uint8)
    cv2.circle(start, (360, 700), 55, (30, 240, 120), -1)
    assert energy_balls(start)
    assert not is_game_frame(start)


def test_safe_tap_avoids_menu_and_bottom_controls():
    assert not safe_tap_point((660, 150), 720, 1600)
    assert not safe_tap_point((625, 180), 720, 1600)
    assert not safe_tap_point((300, 1450), 720, 1600)
    assert safe_tap_point((660, 240), 720, 1600)
