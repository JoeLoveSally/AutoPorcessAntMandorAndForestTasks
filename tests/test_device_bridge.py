"""Device bridge hot paths: raw screen capture and adb metrics.

Device cadence (2026-09-28): exec-out screencap -p spends ~2.1s per
capture of which ~0.5s is the device-side PNG encode. frame() reads the
raw stream instead (16-byte RGBA header + payload) and falls back to the
PNG path whenever the header is not the expected layout.
"""
import struct

import cv2
import numpy as np
import pytest

from device_bridge.adb import Device
from domain_data import AutomationError


class FrameDevice(Device):
    def __init__(self, streams, png=b""):
        self.streams = list(streams)
        self.png = png
        self.png_calls = 0

    def run(self, *args, timeout=20):
        return self.streams.pop(0)

    def screenshot(self):
        self.png_calls += 1
        return self.png


def test_frame_decodes_the_raw_screencap_stream():
    header = struct.pack("<4i", 2, 1, 1, 1)
    rgba = bytes([10, 20, 30, 255, 40, 50, 60, 255])
    device = FrameDevice([header + rgba])

    frame = device.frame()

    assert frame.shape == (1, 2, 3)
    assert frame[0, 0].tolist() == [30, 20, 10]
    assert frame[0, 1].tolist() == [60, 50, 40]
    assert device.png_calls == 0


def test_frame_falls_back_to_png_on_an_unexpected_header():
    image = np.zeros((4, 6, 3), np.uint8)
    image[1, 2] = [7, 8, 9]
    png = cv2.imencode(".png", image)[1].tobytes()
    device = FrameDevice([b"\x01\x02\x03"], png=png)

    frame = device.frame()

    assert frame.shape == image.shape
    assert frame[1, 2].tolist() == [7, 8, 9]
    assert device.png_calls == 1


def test_frame_rejects_an_undecodable_screenshot():
    device = FrameDevice([b"not a header........"], png=b"not a png")

    with pytest.raises(AutomationError) as exc:
        device.frame()

    assert exc.value.code == "DEVICE"


def test_metrics_summary_aggregates_per_command():
    device = Device.__new__(Device)
    device.metrics = [
        (("shell", "dumpsys", "activity", "activities"), 1.234),
        (("shell", "dumpsys"), 0.5),
        (("exec-out", "screencap"), 2.0),
        (("shell", "input", "tap"), 0.3),
    ]

    assert device.metrics_summary() == {
        "shell dumpsys": {"count": 2, "total": 1.73, "max": 1.23},
        "exec-out screencap": {"count": 1, "total": 2.0, "max": 2.0},
        "shell input": {"count": 1, "total": 0.3, "max": 0.3},
    }
