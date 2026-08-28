from __future__ import annotations

from types import SimpleNamespace

from conftest import make_observation

from domain_data import ActionResult, ActionStatus, Bounds, DetectedScreen, Element, Page
from workflow.session import WorkflowSession


def test_tap_refreshes_same_page_when_element_was_redrawn():
    observation = make_observation("<?xml version='1.0'?><hierarchy rotation='0' />")
    original = DetectedScreen(Page.MANOR_HOME, observation)
    refreshed = DetectedScreen(
        Page.MANOR_HOME,
        observation,
        {"diary": Element("diary", Bounds(1, 1, 10, 10), observation.id)},
    )
    after = DetectedScreen(Page.MANOR_DIARY, observation)

    session = object.__new__(WorkflowSession)
    session._recovering = False
    session.config = SimpleNamespace(runtime=SimpleNamespace(poll_interval_seconds=0))
    session.result = SimpleNamespace(actions=[])
    session.current = None
    calls = []

    def raw(screen, key, name, expected=(), required_after=()):
        calls.append((screen, key))
        if screen is original:
            return ActionResult(name, ActionStatus.REJECTED, observation.id, error="Element not found: diary"), None
        return ActionResult(name, ActionStatus.EXECUTED, observation.id, after.observation.id, (5, 5)), after

    session._tap_raw = raw
    session.observe = lambda _reason: refreshed

    result = session.tap(original, "diary", "manor-open-diary", (Page.MANOR_DIARY,))

    assert result is after
    assert len(calls) == 2
