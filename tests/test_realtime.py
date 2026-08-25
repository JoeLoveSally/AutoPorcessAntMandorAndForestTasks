from workflow.forest.energy_rain import Track


def test_track_predicts_falling_position():
    track = Track(1, 100, 200, 1.0)
    track.update(100, 240, 1.1)
    x, y = track.predicted(0.1, 1000)
    assert x == 100
    assert y == 280
