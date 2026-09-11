from domain_data import AutomationError


def dismiss(session):
    for _ in range(6):
        obs = session.observe("overlay")
        if not obs.overlays:
            return obs
        if "guess" in obs.overlays:
            session.tap("放弃奖励", lambda o: "guess" not in o.overlays, overlay=True)
        elif "manor_ad" in obs.overlays:
            # Homepage ads retain the manor page underneath. The close circle
            # is created by the current observation's vision rule, so its
            # coordinate cannot become stale across stacked ads.
            close = next((e for e in obs.elements if e.text == "广告关闭"), None)
            if close is None:
                raise AutomationError("Homepage ad has no verified close control", "OVERLAY")
            session.ex.tap(obs, close, lambda o: "manor_ad" not in o.overlays,
                           "close-manor-ad", session.task, allow_overlay=True)
        elif "reward" in obs.overlays and obs.has("开心收下|我知道啦"):
            session.tap("开心收下|我知道啦", lambda o: "reward" not in o.overlays, overlay=True)
        else:
            # Back is permitted only for a recognized dismissible reward, never a pending submission.
            if session.ex.store.unresolved(session.task) or "confirm" in obs.overlays or "overflow" in obs.overlays:
                raise AutomationError("Overlay requires task-specific handling", "OVERLAY")
            session.back(lambda o: not o.overlays and o.page != "UNKNOWN")
    raise AutomationError("Overlay recovery budget exhausted", "TIMEOUT")
