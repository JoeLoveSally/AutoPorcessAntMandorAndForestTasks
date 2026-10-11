"""The platform contract every device backend implements.

The stack above device_bridge - Observer, Executor, Session, the flows -
talks to devices through this shape only, so `platform` in the config is
the single switch between an adb-driven Android phone and a
WebDriverAgent-driven iPhone. Structural typing on purpose: the test suite
stubs devices with SimpleNamespace, and runtime_checkable keeps isinstance
available for the concrete backends without forcing inheritance.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class DeviceLike(Protocol):
    """Members the stack above device_bridge may rely on.

    - serial: stable device identity - the adb serial on Android, the udid
      on iOS. It keys the run lock and the progress namespaces, so it must
      identify one physical device.
    - foreground(): the id of the app owning the screen (package name on
      Android, bundle id on iOS); "" when it cannot be read.
    - frame(): the screen as a BGR array; screenshot(): the same pixels as
      PNG bytes.
    - tree(): a UI hierarchy XML for element merging, or raise
      AutomationError("UI_TREE") - the observer then logs
      tree.unavailable and runs OCR-only (the iOS path: XCTest exposes no
      uiautomator-style dump).
    - launch(): bring the given app id to the front.
    - tap()/back()/swipe(): the three input primitives. back() is the
      platform's own route out of a page (Android's key event 4, iOS's
      edge-swipe-back) and only runs when the header 返回 control is
      absent, so each platform keeps its navigation semantics here.
    - screen_stream()/touch_channel(): the realtime pair the energy-rain
      game needs; platforms without a continuous capture/touch pipeline
      raise AutomationError("REALTIME") and the flow fails closed there.
    - info()/metrics_summary(): doctor diagnostics.
    """

    serial: str

    def foreground(self) -> str: ...

    def frame(self): ...

    def screenshot(self) -> bytes: ...

    def tree(self) -> bytes: ...

    def launch(self, package: str) -> None: ...

    def tap(self, point) -> None: ...

    def back(self) -> None: ...

    def swipe(self, start, end, duration: int = 350) -> None: ...

    def screen_stream(self, device_size, **options): ...

    def touch_channel(self): ...

    def info(self) -> dict: ...

    def metrics_summary(self) -> dict: ...
