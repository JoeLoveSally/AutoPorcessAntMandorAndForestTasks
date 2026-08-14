from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .device.adb import AdbDevice
from .runtime.config import load_config
from .runtime.errors import AutomationError
from .workflows.manor_daily import ManorDailyWorkflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Alipay Ant Manor and Ant Forest automation")
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="check ADB and device connection")
    commands.add_parser("manor-daily", help="run the evidence-driven Manor workflow")
    return parser


def main(argv: list[str] | None = None) -> int:
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
        result = ManorDailyWorkflow.create(device, config).run()
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if result.status.value in {"success", "already_done", "skipped"} else 3
    except AutomationError as exc:
        print(f"automation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
