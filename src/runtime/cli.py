from __future__ import annotations

import argparse
import json
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("doctor", "capture", "daily", "debug"))
    parser.add_argument("--config", type=Path)
    parser.add_argument("--serial")
    parser.add_argument("--module")
    parser.add_argument("--task")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    config_path = args.config or root / "config/config.example.toml"
    config = tomllib.loads(config_path.read_text())
    serial = args.serial or config["serial"]
    run = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    logger = Logger(root, run)
    store = None
    manager = None
    try:
        store = Store(root / "runtime", serial, run)
        device = Device(serial, config.get("adb", "adb"))
        if args.command == "doctor":
            info = device.info()
            info["display"] = [s.strip() for s in info["display"].splitlines()
                               if "SurfaceOrientation" in s or "SurfaceWidth" in s or "SurfaceHeight" in s]
            print(json.dumps(info, ensure_ascii=False, indent=2))
            return 0
        observer = Observer(device, root / "screenshots/runs" / run, logger)
        if args.command == "capture":
            obs = observer.capture("capture", full=True)
            print(json.dumps(dict(run=run, page=obs.page, overlays=obs.overlays,
                                  text=[e.text for e in obs.elements]), ensure_ascii=False, indent=2))
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
        print(json.dumps(dict(run=run, status="SUCCESS", tasks=manager.completed)))
        return 0
    except (AutomationError, KeyboardInterrupt) as exc:
        logger.emit("run.failed", error=str(exc), code=getattr(exc, "code", "INTERRUPTED"),
                    current_task=manager.current_task if manager else None)
        print(f"FAILED: {exc}\nLog: {logger.path}", file=sys.stderr)
        return 1
    finally:
        if store:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
