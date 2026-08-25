from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from device_bridge.realtime import AdbScreenrecordFrameStream
from logger import RunLogger
from runtime.app import connect_device, run_workflow
from runtime.config import load_config
from runtime.doctor import run_doctor
from screen_perception import ObservationCollector, ScreenDetector


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(prog="ants-auto")
    result.add_argument("--config", type=Path, default=Path("config/config.toml"))
    subcommands = result.add_subparsers(dest="command", required=True)
    subcommands.add_parser("doctor", help="check tools, paths and the connected phone")
    subcommands.add_parser("capture", help="capture and classify the current phone screen")
    probe = subcommands.add_parser("probe", help="measure non-mutating ADB observation latency")
    probe.add_argument("--samples", type=int, default=5)
    stream_test = subcommands.add_parser("stream-test", help="verify the real-time frame channel")
    stream_test.add_argument("--frames", type=int, default=5)
    subcommands.add_parser("manor", help="run one Ant Manor pass")
    subcommands.add_parser("forest", help="run one Ant Forest pass")
    subcommands.add_parser("daily", help="run one Manor then Forest pass")
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        config = load_config(arguments.config)
        if arguments.command == "doctor":
            checks = run_doctor(config)
            for check in checks:
                print(f"[{'ok' if check.ok else 'failed'}] {check.name}: {check.detail}")
            return 0 if all(check.ok for check in checks) else 1
        if arguments.command == "capture":
            device = connect_device(config)
            logger = RunLogger(config.runtime.logs_directory, "capture")
            observation = ObservationCollector(device, logger).capture(
                config.runtime.screenshots_directory / "capture", "manual-capture"
            )
            screen = ScreenDetector(config.package, config.perception.template_directory).detect(observation)
            print(json.dumps({
                "page": screen.page.value,
                "overlays": [item.type.value for item in screen.overlays],
                "elements": sorted(screen.elements),
                "evidence": list(screen.evidence),
                "errors": list(observation.errors),
            }, ensure_ascii=False, indent=2))
            return 0 if screen.page.value != "unknown" else 2
        if arguments.command == "probe":
            device = connect_device(config)
            report = {
                operation: {
                    "p50_ms": round(metrics.p50_ms, 2),
                    "p95_ms": round(metrics.p95_ms, 2),
                    "samples_ms": [round(value, 2) for value in metrics.samples_ms],
                }
                for operation in ("activity", "screenshot", "ui_dump")
                if (metrics := device.measure(operation, arguments.samples))
            }
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        if arguments.command == "stream-test":
            device = connect_device(config)
            started = time.monotonic()
            frames = []
            with AdbScreenrecordFrameStream(
                device.serial,
                device.size(),
                config.device.adb_path,
                bit_rate=config.realtime.bit_rate,
            ) as stream:
                for _ in range(arguments.frames):
                    frames.append(stream.next_frame(timeout=25 if not frames else 3))
            elapsed = time.monotonic() - started
            print(json.dumps({
                "frames": len(frames),
                "first_sequence": frames[0].sequence if frames else None,
                "last_sequence": frames[-1].sequence if frames else None,
                "shape": list(frames[-1].image.shape) if frames else None,
                "elapsed_seconds": round(elapsed, 3),
            }, ensure_ascii=False, indent=2))
            return 0
        result = run_workflow(config, arguments.command)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if result.status.value == "success" else 1
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
