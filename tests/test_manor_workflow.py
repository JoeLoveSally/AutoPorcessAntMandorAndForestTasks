from __future__ import annotations

from conftest import make_observation

from domain_data import Bounds, DetectedScreen, Element, Page
from workflow.manor.daily import ManorWorkflow


def test_reward_friend_declares_home_postcondition_for_popup_recovery():
    observation = make_observation("<?xml version='1.0'?><hierarchy rotation='0' />")
    screen = DetectedScreen(
        Page.MANOR_HOME,
        observation,
        {"reward_friend": Element("reward_friend", Bounds(1, 1, 10, 10), observation.id)},
    )

    class Session:
        def __init__(self):
            self.expected = []
            self.steps = []

        def tap(self, _screen, key, _name, expected=(), **_kwargs):
            self.expected.append((key, expected))
            return DetectedScreen(Page.MANOR_HOME, observation)

        def add_step(self, *args):
            self.steps.append(args)

    session = Session()
    workflow = object.__new__(ManorWorkflow)
    workflow.session = session

    workflow._home_tasks(screen)

    assert session.expected == [("reward_friend", (Page.MANOR_HOME,))]
