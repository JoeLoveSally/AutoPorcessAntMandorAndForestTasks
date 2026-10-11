from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request

import cv2
import numpy as np

from domain_data import AutomationError


class IosDevice:
    """Drive an iPhone through a running WebDriverAgent instance.

    WebDriverAgent is the only touch-injection surface iOS exposes without
    a jailbreak, and its REST protocol is identical over USB port forwards
    and Wi-Fi - this client only needs the reachable base URL. Installing
    and forwarding the agent on a Windows/Linux host (no Mac) is bring-up
    work documented in docs/ios_bringup.md; every endpoint name below is
    part of that checklist to verify against the deployed build.
    """

    def __init__(self, base_url: str, serial: str, timeout: float = 10.0):
        self.base_url, self.serial, self.timeout = base_url.rstrip("/"), serial, timeout
        self._size = None

    def _call(self, path, payload=None):
        """One request to the agent; every endpoint funnels through here."""
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            self.base_url + path, data=data,
            method="POST" if data is not None else "GET",
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise AutomationError(
                f"WebDriverAgent unreachable at {self.base_url}: {exc}", "DEVICE") from exc
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise AutomationError(f"Malformed WDA reply for {path}", "DEVICE") from exc

    def foreground(self):
        value = self._call("/wda/activeAppInfo").get("value") or {}
        return value.get("bundleId") or ""

    def _png(self):
        value = self._call("/screenshot").get("value")
        if not isinstance(value, str):
            raise AutomationError("Malformed WDA screenshot reply", "DEVICE")
        try:
            return base64.b64decode(value)
        except (ValueError, TypeError) as exc:
            raise AutomationError("Malformed WDA screenshot payload", "DEVICE") from exc

    def frame(self):
        image = cv2.imdecode(np.frombuffer(self._png(), np.uint8), cv2.IMREAD_COLOR)
        if image is None:
            raise AutomationError("Cannot decode screenshot", "DEVICE")
        return image

    def screenshot(self):
        return self._png()

    def tree(self):
        # XCTest exposes no uiautomator-style hierarchy dump; the observer
        # logs tree.unavailable and runs OCR-only, which is what the iOS
        # perception pipeline has to be validated against.
        raise AutomationError("UI tree unavailable on iOS; observation is OCR-only", "UI_TREE")

    def launch(self, package):
        # Activates by bundle id - the config's `package` holds the iOS
        # bundle id when platform = "ios" (see docs/ios_bringup.md).
        self._call("/wda/apps/launch", {"bundleId": package})

    def tap(self, point):
        self._call("/wda/tap", {"x": round(point[0]), "y": round(point[1])})

    def swipe(self, start, end, duration=350):
        # WDA measures drag duration in seconds; the shared contract keeps
        # adb's millisecond language.
        self._call("/wda/drag", {"fromX": round(start[0]), "fromY": round(start[1]),
                                 "toX": round(end[0]), "toY": round(end[1]),
                                 "duration": duration / 1000})

    def window_size(self):
        if self._size is None:
            value = self._call("/window/size").get("value") or {}
            try:
                self._size = (int(value["width"]), int(value["height"]))
            except (KeyError, TypeError, ValueError) as exc:
                raise AutomationError("Malformed WDA window size reply", "DEVICE") from exc
        return self._size

    def back(self):
        """Leave the current page the way iOS itself does: edge swipe back.

        iOS has no system back key; the app's own header 返回 control -
        which the executor prefers whenever OCR finds one - covers most
        mini-program pages, so this gesture is the fallback for the
        containers that do not label a control.
        """
        width, height = self.window_size()
        self.swipe((2, height // 2), (round(width * .8), height // 2), duration=300)

    def screen_stream(self, device_size, **_options):
        raise AutomationError("iOS has no realtime screen stream yet (energy rain)",
                              "REALTIME")

    def touch_channel(self, **_options):
        raise AutomationError("iOS has no realtime touch channel yet (energy rain)",
                              "REALTIME")

    def info(self):
        value = self._call("/").get("value") or {}
        build = value.get("build") or {}
        width, height = self.window_size()
        return {"serial": self.serial, "model": value.get("name", ""),
                "ios": build.get("version", ""), "size": f"{width}x{height}",
                "density": "", "display": ""}

    def metrics_summary(self):
        # WDA reports no per-command timings; the agent's own latency shows
        # up in observation cadence instead.
        return {}
