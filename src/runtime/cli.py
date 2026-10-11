from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import tomllib
import uuid
from pathlib import Path

from action_executor import Executor
from device_bridge.adb import Device
from domain_data import AutomationError
from logger import Logger
from runtime.store import Store
from screen_perception import Observer
from state_machine import Budget
from state_machine.task_manager import TaskManager, TaskSpec, select_tasks


def config_path(root, explicit=None):
    path = explicit or root / "config/config.toml"
    if not path.is_file():
        raise AutomationError(f"Missing local config: {path}", "CONFIG")
    return path


def required_executables(config):
    """External binaries the chosen platform needs on PATH.

    adb and ffmpeg drive Android shell, screencap and the realtime stream;
    the iOS client speaks HTTP to WebDriverAgent and shells out to nothing.
    """
    if config.get("platform", "android") != "android":
        return ()
    return (config.get("adb", "adb"), config.get("ffmpeg", "ffmpeg"))


def build_device(config, serial):
    """Construct the backend the config's platform asks for."""
    platform = config.get("platform", "android")
    if platform == "android":
        return Device(serial, config.get("adb", "adb"))
    if platform == "ios":
        from device_bridge.ios import IosDevice

        if not config.get("wda_url"):
            raise AutomationError("platform=ios requires wda_url", "CONFIG")
        return IosDevice(config["wda_url"], serial, config.get("wda_timeout", 10.0))
    raise AutomationError(f"Unknown platform: {platform}", "CONFIG")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("doctor", "capture", "daily", "debug"))
    parser.add_argument("--config", type=Path)
    parser.add_argument("--serial")
    parser.add_argument("--module")
    parser.add_argument("--task")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    run = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    logger = Logger(root, run)
    store = None
    manager = None
    device = None
    try:
        selected_config = config_path(root, args.config)
        config = tomllib.loads(selected_config.read_text())
        serial = args.serial or config["serial"]
        platform = config.get("platform", "android")
        if platform not in ("android", "ios"):
            raise AutomationError(f"Unknown platform: {platform}", "CONFIG")
        for executable in required_executables(config):
            if shutil.which(executable) is None:
                raise AutomationError(f"Required executable not found: {executable}", "CONFIG")
        store = Store(root / "runtime", serial, run, config.get("account", ""))
        device = build_device(config, serial)
        if args.command == "doctor":
            info = device.info()
            info["platform"] = platform
            if platform == "android":
                info["tools"] = {
                    "adb": shutil.which(config.get("adb", "adb")),
                    "ffmpeg": shutil.which(config.get("ffmpeg", "ffmpeg")),
                }
                info["display"] = [s.strip() for s in info["display"].splitlines()
                                   if "SurfaceOrientation" in s or "SurfaceWidth" in s or "SurfaceHeight" in s]
            else:
                info["tools"] = {"wda": config.get("wda_url")}
            print(json.dumps(info, ensure_ascii=False, indent=2))
            return 0
        observer = Observer(device, root / "screenshots/runs" / run, logger)
        if args.command == "capture":
            obs = observer.capture("capture", full=True)
            print(json.dumps({"run": run, "page": obs.page, "overlays": obs.overlays,
                              "text": [e.text for e in obs.elements]}, ensure_ascii=False, indent=2))
            return 0
        from workflow.session import Session
        from workflow.tasks import build_tasks
        executor = Executor(device, observer, logger, store, config["package"],
                            Budget(config.get("run_timeout", 2400)))
        session = Session(executor, config)
        tasks = [TaskSpec(name, module, fn) for name, module, fn in build_tasks(session)]
        if args.command == "debug" and not (args.module or args.task):
            parser.error("debug requires --module or --task")
        selected = select_tasks(tasks, args.command, module=args.module, task=args.task)
        manager = TaskManager(store, logger, session)
        manager.run(selected)
        print(json.dumps({"run": run, "status": "SUCCESS", "tasks": manager.completed}))
        return 0
    except (AutomationError, KeyboardInterrupt) as exc:
        logger.emit("run.failed", error=str(exc), code=getattr(exc, "code", "INTERRUPTED"),
                    current_task=manager.current_task if manager else None)
        print(f"FAILED: {exc}\nLog: {logger.path}", file=sys.stderr)
        return 1
    finally:
        metrics = device.metrics_summary() if device is not None else {}
        if metrics:
            # Per-command ADB timings: the split that shows where each
            # ~3.4s observation goes (dumpsys vs screencap vs input).
            logger.emit("device.metrics", calls=metrics)
        if store:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
