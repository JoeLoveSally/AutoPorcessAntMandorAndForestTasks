from __future__ import annotations

import time

import cv2
import numpy as np

from domain_data import AutomationError
from state_machine import Budget


class Executor:
    def __init__(self, device, observer, logger, store, package, budget):
        self.device, self.observer, self.logger, self.store = device, observer, logger, store
        self.package, self.budget = package, budget
        self.interruption_handler = None

    def validate(self, obs, element=None, allow_overlay=False, allow_unknown=False,
                 pixel_guard=True):
        self.budget.check()
        if obs.package != self.package or self.device.foreground() != self.package:
            raise AutomationError("Foreground package changed", "CONTEXT_CHANGED")
        if obs.page == "UNKNOWN" and not allow_unknown:
            raise AutomationError("Cannot act on unknown page", "UNKNOWN")
        if obs.overlays and not allow_overlay:
            raise AutomationError(f"Overlay blocks action: {obs.overlays}", "OVERLAY")
        if time.monotonic() - obs.captured > 12:
            raise AutomationError("Observation expired; reacquire target", "STALE")
        if element:
            if element.observation != obs.id:
                raise AutomationError("Element belongs to another observation", "STALE")
            x, y = element.point
            if not 0 <= x < obs.width or not 0 <= y < obs.height:
                raise AutomationError("Target outside display", "BOUNDS")
            if pixel_guard:
                current = self.device.frame()
                if current.shape != obs.image.shape:
                    raise AutomationError("Display geometry changed", "STALE")
                x1, y1, x2, y2 = element.bounds
                a, b = obs.image[max(0,y1):y2, max(0,x1):x2], current[max(0,y1):y2, max(0,x1):x2]
                threshold = 70 if element.source == "vision.manor_diary" else 28
                if not a.size or np.mean(cv2.absdiff(a, b)) > threshold:
                    # Device evidence (2026-09-24, run 081743): the lottery
                    # result view's 做任务继续抽 CTA animates (crop diff 39.3
                    # against this 28 threshold), so the diff can never hold
                    # for it; the session stale retries re-find the target by
                    # OCR on a fresh frame first and pass pixel_guard=False.
                    raise AutomationError("Target changed since observation", "STALE")

    def wait(self, predicate, timeout=25, reason="verify", *, recover=True):
        budget = Budget(timeout, self.budget)
        latest = None
        while budget.remaining:
            latest = self.observer.capture(reason)
            if predicate(latest):
                return latest
            if recover and latest.overlays and self.interruption_handler:
                latest = self.interruption_handler(latest)
                if predicate(latest):
                    return latest
            time.sleep(min(.4, budget.remaining))
        raise AutomationError(f"Postcondition failed: {reason}; page={latest.page if latest else 'none'}", "TIMEOUT")

    def tap(self, obs, element, predicate, name, task, irreversible=False, detail=None,
            allow_overlay=False, allow_unknown=False, timeout=25, recover=True,
            pixel_guard=True):
        self.validate(obs, element, allow_overlay, allow_unknown, pixel_guard)
        action = None
        if irreversible:
            action = self.store.intent(task, name, obs.id, detail or {"target": element.text})
        self.logger.emit("action.intent", task=task, name=name, before=obs.id,
                         point=element.point, irreversible=irreversible)
        try:
            self.device.tap(element.point)
            if action:
                self.store.action(action, "SENT")
            after = self.wait(predicate, timeout, name, recover=recover)
            if action:
                self.store.action(action, "VERIFIED", after.id)
            self.logger.emit("action.verified", task=task, name=name, before=obs.id, after=after.id)
            return after
        except BaseException:
            if action:
                self.store.action(action, "RESULT_UNKNOWN")
            raise

    def back(self, obs, predicate, name, allow_unknown=False, *, recover=True):
        self.validate(obs, allow_overlay=True, allow_unknown=allow_unknown)
        self.logger.emit("action.back", before=obs.id, name=name)
        # Alipay mini-app pages expose their own navigation control. On some
        # builds the Android back key is consumed by the embedded webview and
        # leaves the page unchanged, so prefer the bounded, accessibility
        # labelled control when it is present in the app header.
        header_back = [
            item for item in obs.elements
            if item.text == "返回"
            and item.point[0] <= obs.width * .2
            and item.point[1] <= obs.height * .2
        ]
        if len(header_back) == 1:
            self.device.tap(header_back[0].point)
            try:
                return self.wait(predicate, reason=name, recover=recover)
            except AutomationError as exc:
                if exc.code != "TIMEOUT":
                    raise
        self.device.back()
        return self.wait(predicate, reason=name, recover=recover)

    def swipe(self, obs, region=(.5, .78, .5, .35), predicate=None, *, allow_unknown=False,
              timeout=10):
        self.validate(obs, allow_unknown=allow_unknown)
        x1,y1,x2,y2 = region
        self.logger.emit("action.swipe", before=obs.id,
                         start=(int(x1*obs.width), int(y1*obs.height)),
                         end=(int(x2*obs.width), int(y2*obs.height)))
        self.device.swipe((int(x1*obs.width), int(y1*obs.height)),
                          (int(x2*obs.width), int(y2*obs.height)), duration=700)
        expected = predicate or (lambda after: after.page == obs.page)
        return self.wait(expected, timeout, "swipe")
