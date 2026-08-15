from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys

from .device.adb import AdbDevice
from .runtime.config import load_config
from .runtime.errors import AutomationError
from .workflows.manor_daily import ManorDailyWorkflow
from .workflows.forest_daily import ForestDailyWorkflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Alipay Ant Manor and Ant Forest automation")
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="check ADB and device connection")
    commands.add_parser("manor-daily", help="run the evidence-driven Manor workflow")
    commands.add_parser("forest-daily", help="run the evidence-driven Forest workflow")
    commands.add_parser("daily", help="run Manor and Forest workflows in sequence")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    args = build_parser().parse_args(argv)
    if not args.config.is_file():
        print(f"config not found: {args.config}", file=sys.stderr)
        return 2
    try:
        config = load_config(args.config)
        device = AdbDevice.connect(config.device.serial, config.device.adb_path, config.device.timeout_seconds)
        if args.command == "doctor":
            print(json.dumps({"status": "ok", "device": device.serial}, ensure_ascii=False))
            return 0
        if args.command == "daily":
            results = [
                ManorDailyWorkflow.create(device, config).run(),
                ForestDailyWorkflow.create(device, config).run(),
            ]
            print(json.dumps([item.to_dict() for item in results], ensure_ascii=False, indent=2))
            return 0 if all(item.status.value in {"success", "already_done", "skipped"} for item in results) else 3
        workflow = ManorDailyWorkflow if args.command == "manor-daily" else ForestDailyWorkflow
        result = workflow.create(device, config).run()
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if result.status.value in {"success", "already_done", "skipped"} else 3
    except AutomationError as exc:
        print(f"automation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
