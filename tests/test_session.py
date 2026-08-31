from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
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

    def raw(screen, key, name, expected=(), required_after=(), *_contract):
        calls.append((screen, key))
        if screen is original:
            return ActionResult(name, ActionStatus.REJECTED, observation.id, error="Element not found: diary"), None
        return ActionResult(name, ActionStatus.EXECUTED, observation.id, after.observation.id, (5, 5)), after

    session._tap_raw = raw
    session.observe = lambda _reason: refreshed

    result = session.tap(original, "diary", "manor-open-diary", (Page.MANOR_DIARY,))

    assert result is after
    assert len(calls) == 2


def test_tap_refreshes_an_aged_source_before_sending_coordinates():
    observation = replace(
        make_observation("<?xml version='1.0'?><hierarchy rotation='0' />"),
        captured_at=datetime.now(timezone.utc) - timedelta(seconds=10),
    )
    original = DetectedScreen(
        Page.MANOR_HOME,
        observation,
        {"diary": Element("diary", Bounds(1, 1, 10, 10), observation.id)},
    )
    fresh_observation = make_observation(
        "<?xml version='1.0'?><hierarchy rotation='0' />"
    )
    refreshed = DetectedScreen(
        Page.MANOR_HOME,
        fresh_observation,
        {"diary": Element("diary", Bounds(2, 2, 12, 12), fresh_observation.id)},
    )
    after = DetectedScreen(Page.MANOR_DIARY, fresh_observation)
    session = object.__new__(WorkflowSession)
    session._recovering = False
    session.config = SimpleNamespace(
        runtime=SimpleNamespace(
            poll_interval_seconds=0,
            max_observation_age_seconds=3,
        )
    )
    session.result = SimpleNamespace(actions=[])
    session.current = original
    sent = []

    session.observe = lambda _reason: refreshed

    def raw(screen, key, name, expected=(), required_after=(), *_contract):
        sent.append(screen)
        return (
            ActionResult(
                name,
                ActionStatus.EXECUTED,
                screen.observation.id,
                after.observation.id,
                (7, 7),
            ),
            after,
        )

    session._tap_raw = raw

    result = session.tap(original, "diary", "manor-open-diary", (Page.MANOR_DIARY,))

    assert result is after
    assert sent == [refreshed]
