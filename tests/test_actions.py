from datetime import datetime, timezone

from ants_automation.actions.executor import ActionExecutor
from ants_automation.domain.models import Bounds, DetectedPage, Observation, PageType, UIElement


class FakeDevice:
    serial = "test"

    def __init__(self):
        self.points = []

    def screen_size(self):
        return (1080, 2400)

    def tap(self, point):
        self.points.append(point)


def test_action_rejects_unknown_page():
    now = datetime.now(timezone.utc)
    observation = Observation(now, "test", "com.eg.android.AlipayGphone", "A", None, None, None)
    element = UIElement("x", "x", Bounds(0, 0, 10, 10), True, True, "test", now)
    page = DetectedPage(PageType.UNKNOWN, observation, {"x": element})
    result = ActionExecutor(FakeDevice()).tap(page, "x")
    assert result.status.value == "rejected"
