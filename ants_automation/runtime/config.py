from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import tomllib


@dataclass(frozen=True)
class DeviceConfig:
    serial: str = ""
    adb_path: str = "adb"
    timeout_seconds: float = 20.0


@dataclass(frozen=True)
class RuntimeConfig:
    artifacts_directory: Path = Path("artifacts")
    launch_wait_seconds: float = 5.0
    page_timeout_seconds: float = 15.0
    poll_interval_seconds: float = 0.5


@dataclass(frozen=True)
class Config:
    package: str = "com.eg.android.AlipayGphone"
    device: DeviceConfig = field(default_factory=DeviceConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)


def load_config(path: Path) -> Config:
    with path.open("rb") as stream:
        raw = tomllib.load(stream)
    base = path.resolve().parent
    device = raw.get("device", {})
    runtime = raw.get("runtime", {})
    artifacts = Path(runtime.get("artifacts_directory", "artifacts"))
    if not artifacts.is_absolute():
        artifacts = base / artifacts
    return Config(
        package=raw.get("package", "com.eg.android.AlipayGphone"),
        device=DeviceConfig(**device),
        runtime=RuntimeConfig(
            artifacts_directory=artifacts,
            launch_wait_seconds=float(runtime.get("launch_wait_seconds", 5.0)),
            page_timeout_seconds=float(runtime.get("page_timeout_seconds", 15.0)),
            poll_interval_seconds=float(runtime.get("poll_interval_seconds", 0.5)),
        ),
    )
