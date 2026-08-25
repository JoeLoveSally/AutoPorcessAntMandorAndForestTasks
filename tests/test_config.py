from pathlib import Path

import pytest

from runtime.config import load_config


def test_config_resolves_project_paths(tmp_path: Path):
    config_directory = tmp_path / "config"
    config_directory.mkdir()
    path = config_directory / "config.toml"
    path.write_text(
        """
        [runtime]
        logs_directory = "logs"
        [quiz]
        fallback_option = 1
        [realtime]
        minimum_hit_rate = 0.8
        """,
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.runtime.logs_directory == tmp_path / "logs"
    assert config.quiz.fallback_option == 1
    assert config.realtime.minimum_hit_rate == 0.8


def test_config_rejects_invalid_fallback(tmp_path: Path):
    path = tmp_path / "config.toml"
    path.write_text("[quiz]\nfallback_option = 2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="fallback_option"):
        load_config(path)
