from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True, slots=True)
class DeviceConfig:
    serial: str = ""
    adb_path: str = "adb"
    timeout_seconds: float = 20.0


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    logs_directory: Path = Path("logs")
    screenshots_directory: Path = Path("screenshots/runs")
    state_database: Path = Path("runtime/task_state.db")
    cache_directory: Path = Path("runtime/cache")
    launch_wait_seconds: float = 5.0
    page_timeout_seconds: float = 15.0
    poll_interval_seconds: float = 0.5
    settle_seconds: float = 1.0
    max_observation_age_seconds: float = 6.0
    max_recovery_attempts: int = 2
    max_task_iterations: int = 50


@dataclass(frozen=True, slots=True)
class PerceptionConfig:
    template_directory: Path = Path("screenshots/template")
    template_threshold: float = 0.88
    template_ambiguity_margin: float = 0.04
    enable_ocr: bool = False


@dataclass(frozen=True, slots=True)
class QuizConfig:
    search_url: str = "https://api.bochaai.com/v1/web-search"
    api_key_env: str = "WEB_SEARCH_API_KEY"
    env_file: Path | None = None
    fallback_option: int = 0
    cache_file: Path = Path("runtime/cache/quiz_answers.json")


@dataclass(frozen=True, slots=True)
class RealtimeConfig:
    scrcpy_path: str = "scrcpy"
    server_path: Path = Path("/usr/share/scrcpy/scrcpy-server")
    max_size: int = 1440
    bit_rate: int = 8_000_000
    max_fps: int = 60
    rain_duration_seconds: float = 22.0
    minimum_hit_rate: float = 0.80
    dedup_radius_pixels: int = 70
    track_ttl_seconds: float = 0.45
    diagnostic_frame_interval: int = 30


@dataclass(frozen=True, slots=True)
class Config:
    package: str = "com.eg.android.AlipayGphone"
    device: DeviceConfig = field(default_factory=DeviceConfig)
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    perception: PerceptionConfig = field(default_factory=PerceptionConfig)
    quiz: QuizConfig = field(default_factory=QuizConfig)
    realtime: RealtimeConfig = field(default_factory=RealtimeConfig)


def _path(base: Path, value: str | Path) -> Path:
    result = Path(value).expanduser()
    return result if result.is_absolute() else base / result


def load_config(path: Path) -> Config:
    with path.open("rb") as stream:
        raw = tomllib.load(stream)
    base = path.resolve().parent.parent if path.parent.name == "config" else path.resolve().parent
    device = raw.get("device", {})
    runtime = raw.get("runtime", {})
    perception = raw.get("perception", {})
    quiz = raw.get("quiz", {})
    realtime = raw.get("realtime", {})
    env_value = str(quiz.get("env_file", "")).strip()
    fallback = int(quiz.get("fallback_option", 0))
    if fallback not in (0, 1):
        raise ValueError("quiz.fallback_option must be 0 or 1")
    minimum_hit_rate = float(realtime.get("minimum_hit_rate", 0.80))
    if not 0 < minimum_hit_rate <= 1:
        raise ValueError("realtime.minimum_hit_rate must be in (0, 1]")
    return Config(
        package=str(raw.get("package", "com.eg.android.AlipayGphone")),
        device=DeviceConfig(
            serial=str(device.get("serial", "")),
            adb_path=str(device.get("adb_path", "adb")),
            timeout_seconds=float(device.get("timeout_seconds", 20.0)),
        ),
        runtime=RuntimeConfig(
            logs_directory=_path(base, runtime.get("logs_directory", "logs")),
            screenshots_directory=_path(base, runtime.get("screenshots_directory", "screenshots/runs")),
            state_database=_path(base, runtime.get("state_database", "runtime/task_state.db")),
            cache_directory=_path(base, runtime.get("cache_directory", "runtime/cache")),
            launch_wait_seconds=float(runtime.get("launch_wait_seconds", 5.0)),
            page_timeout_seconds=float(runtime.get("page_timeout_seconds", 15.0)),
            poll_interval_seconds=float(runtime.get("poll_interval_seconds", 0.5)),
            settle_seconds=float(runtime.get("settle_seconds", 1.0)),
            max_observation_age_seconds=float(
                runtime.get("max_observation_age_seconds", 6.0)
            ),
            max_recovery_attempts=int(runtime.get("max_recovery_attempts", 2)),
            max_task_iterations=int(runtime.get("max_task_iterations", 50)),
        ),
        perception=PerceptionConfig(
            template_directory=_path(base, perception.get("template_directory", "screenshots/template")),
            template_threshold=float(perception.get("template_threshold", 0.88)),
            template_ambiguity_margin=float(perception.get("template_ambiguity_margin", 0.04)),
            enable_ocr=bool(perception.get("enable_ocr", False)),
        ),
        quiz=QuizConfig(
            search_url=str(quiz.get("search_url", "https://api.bochaai.com/v1/web-search")),
            api_key_env=str(quiz.get("api_key_env", "WEB_SEARCH_API_KEY")),
            env_file=_path(base, env_value) if env_value else None,
            fallback_option=fallback,
            cache_file=_path(base, quiz.get("cache_file", "runtime/cache/quiz_answers.json")),
        ),
        realtime=RealtimeConfig(
            scrcpy_path=str(realtime.get("scrcpy_path", "scrcpy")),
            server_path=_path(base, realtime.get("server_path", "/usr/share/scrcpy/scrcpy-server")),
            max_size=int(realtime.get("max_size", 1440)),
            bit_rate=int(realtime.get("bit_rate", 8_000_000)),
            max_fps=int(realtime.get("max_fps", 60)),
            rain_duration_seconds=float(realtime.get("rain_duration_seconds", 22.0)),
            minimum_hit_rate=minimum_hit_rate,
            dedup_radius_pixels=int(realtime.get("dedup_radius_pixels", 70)),
            track_ttl_seconds=float(realtime.get("track_ttl_seconds", 0.45)),
            diagnostic_frame_interval=max(
                1, int(realtime.get("diagnostic_frame_interval", 30))
            ),
        ),
    )
