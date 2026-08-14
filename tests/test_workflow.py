from pathlib import Path

from ants_automation.device.adb import AndroidDevice
from ants_automation.domain.models import TaskStatus
from ants_automation.runtime.config import Config, DeviceConfig, RuntimeConfig
from ants_automation.workflows.manor_daily import ManorDailyWorkflow


FIXTURES = Path(__file__).parent / "fixtures"


class FakeDevice:
    serial = "fake"

    def __init__(self):
        self.state = "home"
        self.taps: list[tuple[int, int]] = []

    def launch_package(self, package):
        assert package == "com.eg.android.AlipayGphone"

    def current_package_activity(self):
        return "com.eg.android.AlipayGphone", self.state

    def screenshot(self, destination):
        destination.write_bytes(b"fake-png")
        return destination

    def dump_ui(self, destination):
        source = {
            "home": "alipay_home.xml",
            "manor": "manor_home.xml",
            "family": "manor_family.xml",
        }[self.state]
        destination.write_bytes((FIXTURES / source).read_bytes())
        return destination

    def tap(self, point):
        self.taps.append(point)
        self.state = {"home": "manor", "manor": "family", "family": "family"}[self.state]

    def swipe(self, start, end, duration_ms=400):
        raise AssertionError("not used")

    def back(self):
        raise AssertionError("not used")

    def screen_size(self):
        return (1080, 2400)


def test_manor_workflow_stops_without_guessing_sign_in_success(tmp_path):
    config = Config(
        device=DeviceConfig(),
        runtime=RuntimeConfig(
            artifacts_directory=tmp_path,
            launch_wait_seconds=0,
            page_timeout_seconds=0.2,
            poll_interval_seconds=0.01,
        ),
    )
    result = ManorDailyWorkflow.create(FakeDevice(), config).run()
    assert result.status is TaskStatus.UNKNOWN
    assert result.error is not None
    assert result.evidence_directory is not None
    assert (result.evidence_directory / "result.json").is_file()
