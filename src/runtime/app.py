from __future__ import annotations

import time

from device_bridge.adb import AdbDevice
from domain_data import Page, RunResult, StepStatus
from runtime.config import Config
from workflow.forest import ForestWorkflow
from workflow.manor import ManorWorkflow
from workflow.session import WorkflowSession


def connect_device(config: Config) -> AdbDevice:
    return AdbDevice.connect(
        config.device.serial,
        config.device.adb_path,
        config.device.timeout_seconds,
    )


def run_workflow(config: Config, target: str = "daily") -> RunResult:
    device = connect_device(config)
    session = WorkflowSession(target, device, config)
    session.start()
    try:
        device.force_stop_package(config.package)
        device.launch_package(config.package)
        time.sleep(config.runtime.launch_wait_seconds)
        home = session.wait_for(Page.ALIPAY_HOME, "alipay-home")
        if target in ("manor", "daily"):
            manor = ManorWorkflow(session).run(home)
            if target == "daily":
                home = session.back(manor, "manor-return-alipay", (Page.ALIPAY_HOME,))
        if target in ("forest", "daily"):
            ForestWorkflow(session).run(home)
        return session.finish(StepStatus.SUCCESS)
    except Exception as exc:
        session.logger.emit("workflow.error", type=type(exc).__name__, error=str(exc))
        return session.finish(StepStatus.FAILED, str(exc))
