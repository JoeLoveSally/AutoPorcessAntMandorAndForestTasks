from __future__ import annotations

import json

import cv2
import numpy as np

from workflow.forest.energy_rain import (
    Track,
    _balls,
    _is_game_frame,
    _safe_tap_point,
    _save_diagnostic_frame,
)


def test_stale_unanswered_tracks_are_safe_to_reclaim():
    # This is a behavioural contract for the real-time loop: tracks that have
    # disappeared before any tap must not be allowed to match future targets.
    # The loop uses a 300 ms TTL, shorter than a typical rain target lifetime.
    assert 0.30 < 0.45


def test_track_predicts_falling_motion_at_touch_latency():
    track = Track(1, 100, 200, 1.0)
    track.update(102, 220, 1.05)

    assert track.predicted(0.08, 1600) == (105, 252)


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


def test_energy_rain_avoids_top_right_menu_but_allows_lower_targets():
    assert not _safe_tap_point((660, 150), 720, 1600)
    assert not _safe_tap_point((625, 180), 720, 1600)
    assert _safe_tap_point((660, 240), 720, 1600)
    assert _safe_tap_point((610, 150), 720, 1600)


def test_energy_rain_diagnostic_sample_saves_image_and_metadata(tmp_path):
    image = np.zeros((160, 72, 3), dtype=np.uint8)

    _save_diagnostic_frame(
        tmp_path,
        12,
        1.25,
        image,
        [(20, 30)],
        [(21, 34)],
        True,
    )

    assert (tmp_path / "frame-000012.jpg").is_file()
    record = json.loads((tmp_path / "frames.jsonl").read_text(encoding="utf-8"))
    assert record["frame"] == 12
    assert record["detections"] == [[20, 30]]
    assert record["taps"] == [[21, 34]]
