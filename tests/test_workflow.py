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

    def force_stop_package(self, package):
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
        return (1440, 3200)


class DonationFakeDevice(FakeDevice):
    def __init__(self):
        super().__init__()
        self.donation_finished = False

    def dump_ui(self, destination):
        source = {
            "home": "alipay_home.xml",
            "manor": "manor_home.xml",
            "family": "manor_family.xml",
            "tasks": "manor_family_tasks_pending.xml",
            "donation": "manor_donation.xml",
            "project": "manor_donation_project.xml",
            "confirm": "manor_donation_confirm.xml",
            "reward": "manor_donation_reward.xml",
            "family_signed": "manor_family_signed.xml",
            "tasks_done": "manor_family_tasks_completed.xml",
        }[self.state]
        destination.write_bytes((FIXTURES / source).read_bytes())
        return destination

    def tap(self, point):
        self.taps.append(point)
        if self.state == "manor" and self.donation_finished:
            self.state = "tasks_done"
            return
        self.state = {
            "home": "manor",
            "manor": "family",
            "family": "tasks",
            "tasks": "donation",
            "donation": "project",
            "project": "confirm",
            "confirm": "reward",
        }[self.state]

    def back(self):
        if self.state == "donation":
            self.donation_finished = True
        self.state = {
            "reward": "project",
            "project": "donation",
            "donation": "manor",
        }[self.state]


def test_manor_workflow_stops_without_guessing_sign_in_success(tmp_path):
    config = Config(
        device=DeviceConfig(),
        runtime=RuntimeConfig(
            artifacts_directory=tmp_path,
            logs_directory=tmp_path / "logs",
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
    run_logs = list((tmp_path / "logs").glob("*.log"))
    assert len(run_logs) == 1
    assert run_logs[0].stem == result.started_at.strftime("%Y%m%d-%H%M%S-%f")
    assert "workflow.finish" in run_logs[0].read_text(encoding="utf-8")
    assert not (result.evidence_directory / "run.log").exists()
    assert (result.evidence_directory / "004-sign_in_after.png").is_file()
    assert (result.evidence_directory / "004-sign_in_after.xml").is_file()
    assert (result.evidence_directory / "004-sign_in_after.json").is_file()


def test_manor_workflow_completes_family_donation_before_missing_feed_entry_stop(tmp_path):
    config = Config(
        device=DeviceConfig(),
        runtime=RuntimeConfig(
            artifacts_directory=tmp_path,
            logs_directory=tmp_path / "logs",
            launch_wait_seconds=0,
            page_timeout_seconds=0.2,
            poll_interval_seconds=0.01,
        ),
    )

    result = ManorDailyWorkflow.create(DonationFakeDevice(), config).run()

    assert result.status is TaskStatus.FAILED
    assert result.error == {
        "type": "failed",
        "message": "Family panel has no help-feed action or completed state",
    }
    assert any(task.name == "family_sign_in" for task in result.tasks)
    donation = next(task for task in result.tasks if task.name == "family_egg_donation")
    assert donation.status is TaskStatus.SUCCESS
    names = [action.name for action in result.actions]
    assert names[names.index("leave_donation_reward"):names.index("leave_donation_projects") + 1] == [
        "leave_donation_reward",
        "leave_donation_project",
        "leave_donation_projects",
    ]
