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

    def validate(self, obs, element=None, allow_overlay=False, allow_unknown=False):
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
            current = cv2.imdecode(np.frombuffer(self.device.screenshot(), np.uint8), cv2.IMREAD_COLOR)
            if current is None or current.shape != obs.image.shape:
                raise AutomationError("Display geometry changed", "STALE")
            x1, y1, x2, y2 = element.bounds
            a, b = obs.image[max(0,y1):y2, max(0,x1):x2], current[max(0,y1):y2, max(0,x1):x2]
            if not a.size or np.mean(cv2.absdiff(a, b)) > 28:
                raise AutomationError("Target changed since observation", "STALE")

    def wait(self, predicate, timeout=25, reason="verify"):
        budget = Budget(timeout, self.budget)
        latest = None
        while budget.remaining:
            latest = self.observer.capture(reason)
            if predicate(latest):
                return latest
            time.sleep(min(.4, budget.remaining))
        raise AutomationError(f"Postcondition failed: {reason}; page={latest.page if latest else 'none'}", "TIMEOUT")

    def tap(self, obs, element, predicate, name, task, irreversible=False, detail=None,
            allow_overlay=False, allow_unknown=False, timeout=25):
        self.validate(obs, element, allow_overlay, allow_unknown)
        action = None
        if irreversible:
            action = self.store.intent(task, name, obs.id, detail or {"target": element.text})
        self.logger.emit("action.intent", task=task, name=name, before=obs.id,
                         point=element.point, irreversible=irreversible)
        try:
            self.device.tap(element.point)
            if action:
                self.store.action(action, "SENT")
            after = self.wait(predicate, timeout, name)
            if action:
                self.store.action(action, "VERIFIED", after.id)
            self.logger.emit("action.verified", task=task, name=name, before=obs.id, after=after.id)
            return after
        except BaseException:
            if action:
                self.store.action(action, "RESULT_UNKNOWN")
            raise

    def back(self, obs, predicate, name, allow_unknown=False):
        self.validate(obs, allow_overlay=True, allow_unknown=allow_unknown)
        self.logger.emit("action.back", before=obs.id, name=name)
        self.device.back()
        return self.wait(predicate, reason=name)

    def swipe(self, obs, region=(.5, .78, .5, .35)):
        self.validate(obs)
        x1,y1,x2,y2 = region
        self.device.swipe((int(x1*obs.width), int(y1*obs.height)),
                          (int(x2*obs.width), int(y2*obs.height)))
        after = self.observer.capture("swipe")
        if after.page != obs.page:
            raise AutomationError(f"Unexpected swipe destination {after.page}", "CONTEXT_CHANGED")
        return after
