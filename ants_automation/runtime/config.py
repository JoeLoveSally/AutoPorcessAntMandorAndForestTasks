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
    logs_directory: Path = Path("logs")
    launch_wait_seconds: float = 5.0
    page_timeout_seconds: float = 15.0
    poll_interval_seconds: float = 0.5
    external_task_timeout_seconds: float = 40.0
    external_swipe_interval_seconds: float = 3.0
    energy_rain_seconds: float = 20.0
    energy_rain_min_seconds: float = 12.0
    energy_rain_idle_seconds: float = 1.5


@dataclass(frozen=True)
class QuizConfig:
    search_url: str = "https://api.bochaai.com/v1/web-search"
    api_key_env: str = "WEB_SEARCH_API_KEY"
    env_file: Path | None = None
    cache_file: Path = Path("data/quiz_answers.json")


@dataclass(frozen=True)
class Config:
    package: str = "com.eg.android.AlipayGphone"
    device: DeviceConfig = field(default_factory=DeviceConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    quiz: QuizConfig = field(default_factory=QuizConfig)


def load_config(path: Path) -> Config:
    with path.open("rb") as stream:
        raw = tomllib.load(stream)
    base = path.resolve().parent
    device = raw.get("device", {})
    runtime = raw.get("runtime", {})
    quiz = raw.get("quiz", {})
    artifacts = Path(runtime.get("artifacts_directory", "artifacts"))
    logs = Path(runtime.get("logs_directory", "logs"))
    if not artifacts.is_absolute():
        artifacts = base / artifacts
    if not logs.is_absolute():
        logs = base / logs
    cache = Path(quiz.get("cache_file", "data/quiz_answers.json"))
    if not cache.is_absolute():
        cache = base / cache
    env_file_value = quiz.get("env_file")
    env_file = Path(env_file_value).expanduser() if env_file_value else None
    if env_file is not None and not env_file.is_absolute():
        env_file = base / env_file
    return Config(
        package=raw.get("package", "com.eg.android.AlipayGphone"),
        device=DeviceConfig(**device),
        runtime=RuntimeConfig(
            artifacts_directory=artifacts,
            logs_directory=logs,
            launch_wait_seconds=float(runtime.get("launch_wait_seconds", 5.0)),
            page_timeout_seconds=float(runtime.get("page_timeout_seconds", 15.0)),
            poll_interval_seconds=float(runtime.get("poll_interval_seconds", 0.5)),
            external_task_timeout_seconds=float(runtime.get("external_task_timeout_seconds", 40.0)),
            external_swipe_interval_seconds=float(runtime.get("external_swipe_interval_seconds", 3.0)),
            energy_rain_seconds=float(runtime.get("energy_rain_seconds", 20.0)),
            energy_rain_min_seconds=float(runtime.get("energy_rain_min_seconds", 12.0)),
            energy_rain_idle_seconds=float(runtime.get("energy_rain_idle_seconds", 1.5)),
        ),
        quiz=QuizConfig(
            search_url=str(quiz.get("search_url", "https://api.bochaai.com/v1/web-search")),
            api_key_env=str(quiz.get("api_key_env", "WEB_SEARCH_API_KEY")),
            env_file=env_file,
            cache_file=cache,
        ),
    )
