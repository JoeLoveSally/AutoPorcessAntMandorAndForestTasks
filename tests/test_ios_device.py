"""WebDriverAgent client behaviour against a stub endpoint.

WDA's REST surface is the only contract between this repo and an iPhone -
bring-up (docs/ios_bringup.md) has to verify the endpoint names against the
deployed WDA build, so the client funnels every path through one _call and
these tests pin the payloads it sends and the reply shapes it accepts.
"""

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import cv2
import numpy as np
import pytest

from device_bridge.ios import IosDevice
from domain_data import AutomationError


class StubWda:
    """Replay canned JSON replies per path and record every request."""

    def __init__(self, replies):
        self.replies = replies
        self.requests = []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def _serve(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                stub.requests.append((self.command, self.path,
                                      json.loads(body) if body else None))
                payload = json.dumps(stub.replies.get(self.path, {})).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = do_POST = _serve

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()


def test_foreground_reads_the_active_bundle_id():
    with StubWda({"/wda/activeAppInfo": {"value": {"bundleId": "com.alipay.iphoneclient"}}}) as stub:
        device = IosDevice(stub.url, "udid-test")

        assert device.foreground() == "com.alipay.iphoneclient"
        assert stub.requests[0][:2] == ("GET", "/wda/activeAppInfo")


def test_frame_decodes_the_wda_screenshot_to_bgr():
    png = cv2.imencode(".png", np.full((4, 6, 3), (10, 20, 30), np.uint8))[1].tobytes()
    with StubWda({"/screenshot": {"value": base64.b64encode(png).decode()}}) as stub:
        device = IosDevice(stub.url, "udid-test")

        frame = device.frame()

    assert frame.shape == (4, 6, 3)
    # WDA screenshots are ordinary PNGs; the pipeline needs BGR.
    assert frame[0, 0].tolist() == [10, 20, 30]


def test_tap_and_launch_send_their_coordinate_payloads():
    with StubWda({"/wda/tap": {"value": None},
                  "/wda/apps/launch": {"value": {"pid": 42}}}) as stub:
        device = IosDevice(stub.url, "udid-test")

        device.tap((300, 1400))
        device.launch("com.alipay.iphoneclient")

    assert stub.requests[0][:2] == ("POST", "/wda/tap")
    assert stub.requests[0][2] == {"x": 300, "y": 1400}
    assert stub.requests[1][2] == {"bundleId": "com.alipay.iphoneclient"}


def test_back_swipes_from_the_left_edge_in_native_scale():
    with StubWda({"/window/size": {"value": {"width": 390, "height": 844}},
                  "/wda/drag": {"value": None}}) as stub:
        device = IosDevice(stub.url, "udid-test")

        device.back()

    method, path, payload = stub.requests[-1]
    assert (method, path) == ("POST", "/wda/drag")
    assert payload["fromX"] <= 4 and payload["toX"] > 200
    assert payload["fromY"] == payload["toY"] == 422


def test_swipe_contracts_milliseconds_to_wdas_seconds():
    with StubWda({"/wda/drag": {"value": None}}) as stub:
        IosDevice(stub.url, "udid-test").swipe((0, 100), (0, 400), duration=700)

    assert stub.requests[0][2]["duration"] == pytest.approx(0.7)


def test_tree_declares_itself_unavailable_for_ocr_only_observation():
    device = IosDevice("http://127.0.0.1:9", "udid-test")

    with pytest.raises(AutomationError, match="OCR-only"):
        device.tree()


def test_realtime_channels_declare_themselves_unsupported():
    device = IosDevice("http://127.0.0.1:9", "udid-test")

    with pytest.raises(AutomationError, match="energy rain"):
        device.screen_stream((1080, 2400))
    with pytest.raises(AutomationError, match="energy rain"):
        device.touch_channel()


def test_unreachable_agent_fails_as_a_device_error():
    device = IosDevice("http://127.0.0.1:9", "udid-test", timeout=.5)

    with pytest.raises(AutomationError, match="WebDriverAgent unreachable"):
        device.foreground()
