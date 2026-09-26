from pathlib import Path

import pytest

from domain_data import AutomationError
from runtime.cli import config_path


def test_default_config_is_local_file(tmp_path):
    local = tmp_path / "config" / "config.toml"
    local.parent.mkdir()
    local.write_text('serial = "device"')

    assert config_path(tmp_path) == local


def test_missing_local_config_fails_instead_of_using_example(tmp_path):
    example = tmp_path / "config" / "config.example.toml"
    example.parent.mkdir()
    example.write_text('serial = "sample"')

    with pytest.raises(AutomationError) as raised:
        config_path(tmp_path)

    assert raised.value.code == "CONFIG"


def test_explicit_config_is_supported(tmp_path):
    explicit = tmp_path / "phone.toml"
    explicit.write_text('serial = "device"')

    assert config_path(Path("/unused"), explicit) == explicit
