from conftest import make_observation

from domain_data import Bounds, DetectedScreen, Element, Page
from workflow.forest.daily import ForestWorkflow


class StubSession:
    def __init__(self):
        self.tapped: list[str] = []
        self.steps = []

    def tap(self, screen, key, name, expected=()):
        self.tapped.append(key)
        remaining = {
            item_key: item
            for item_key, item in screen.elements.items()
            if item_key != key
        }
        self.current = DetectedScreen(Page.FOREST_HOME, screen.observation, remaining)
        return self.current

    def observe(self, reason):
        return self.current

    def add_step(self, *args):
        self.steps.append(args)


def test_collect_own_energy_never_taps_energy_rain_as_a_bubble():
    observation = make_observation("<?xml version='1.0'?><hierarchy rotation='0' />")
    elements = {
        key: Element(key, Bounds(10, 10, 50, 50), observation.id)
        for key in ("energy_0", "energy_rain")
    }
    screen = DetectedScreen(Page.FOREST_HOME, observation, elements)
    session = StubSession()
    session.current = screen
    workflow = object.__new__(ForestWorkflow)
    workflow.session = session

    workflow._collect_own_energy(screen)

    assert session.tapped == ["energy_0"]
