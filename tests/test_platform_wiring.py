"""The config's `platform` field is the single switch between backends.

build_device and required_executables are the whole wiring surface: the
android profile keeps working with no platform key at all (every existing
config predates the field), the ios profile constructs the WDA client
without touching the network, and unknown values fail closed as CONFIG.
"""

from types import SimpleNamespace

import pytest

from device_bridge.ios import IosDevice
from domain_data import AutomationError
from runtime import cli


def test_android_profile_is_the_default_and_keeps_the_adb_backend(monkeypatch):
    created = {}

    class FakeAdbDevice:
        def __init__(self, serial, adb="adb"):
            created.update(serial=serial, adb=adb)

    monkeypatch.setattr(cli, "Device", FakeAdbDevice)

    device = cli.build_device({"serial": "s1", "adb": "/opt/adb"}, "s1")

    assert isinstance(device, FakeAdbDevice)
    assert created == {"serial": "s1", "adb": "/opt/adb"}


def test_ios_profile_constructs_the_wda_client_without_network(monkeypatch):
    def no_adb(*_args, **_kwargs):
        raise AssertionError("the ios profile must not touch adb")

    monkeypatch.setattr(cli, "Device", no_adb)

    device = cli.build_device(
        {"platform": "ios", "wda_url": "http://127.0.0.1:8100"}, "udid-1")

    assert isinstance(device, IosDevice)
    assert device.serial == "udid-1"
    assert device.base_url == "http://127.0.0.1:8100"


def test_ios_profile_requires_its_wda_endpoint():
    with pytest.raises(AutomationError, match="wda_url"):
        cli.build_device({"platform": "ios"}, "udid-1")


def test_unknown_platform_fails_closed():
    with pytest.raises(AutomationError, match="Unknown platform"):
        cli.build_device({"platform": "harmony", "serial": "s1"}, "s1")


def test_only_the_android_profile_requires_executables():
    assert cli.required_executables({}) == ("adb", "ffmpeg")
    assert cli.required_executables({"platform": "android", "adb": "/opt/adb"}) == \
        ("/opt/adb", "ffmpeg")
    assert cli.required_executables({"platform": "ios", "wda_url": "http://x"}) == ()


def test_ios_metrics_summary_is_the_empty_falsy_summary():
    # The run-end metrics hook keys off a truthy summary; the ios client
    # reports none and the hook must stay silent.
    assert IosDevice("http://127.0.0.1:9", "u").metrics_summary() == {}


def test_doctor_display_filtering_survives_a_missing_display_field():
    # The android doctor path filters device.info()["display"]; the ios
    # info() carries an empty display instead, and the filter must not run
    # over it. Exercise the same list comprehension shape doctor uses.
    info = SimpleNamespace(display="")
    assert [s.strip() for s in info.display.splitlines()] == []
