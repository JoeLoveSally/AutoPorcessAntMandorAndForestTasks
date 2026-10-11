"""The platform contract both device backends satisfy.

The stack above device_bridge (Observer, Executor, Session, the flows)
talks to devices through the DeviceLike shape only, so `platform` in the
config is the single switch between an adb-driven Android phone and a
WebDriverAgent-driven iPhone. These tests pin that both concrete backends
carry every member the stack relies on.
"""

import inspect

from device_bridge.adb import Device
from device_bridge.common import DeviceLike
from device_bridge.ios import IosDevice

# Members the stack above device_bridge calls (see the DeviceLike docstring).
CONTRACT = ("serial", "foreground", "frame", "screenshot", "tree", "launch",
            "tap", "back", "swipe", "screen_stream", "touch_channel",
            "info", "metrics_summary")


def backends():
    # Construction would shell out to adb (android) - the contract is about
    # the class surface, so build bare instances and stamp the one member
    # that lives on the instance (serial) instead of the class.
    android, ios = object.__new__(Device), object.__new__(IosDevice)
    android.serial = ios.serial = "contract-test"
    return android, ios


def test_both_backends_satisfy_the_runtime_contract():
    android, ios = backends()

    assert isinstance(android, DeviceLike)
    assert isinstance(ios, DeviceLike)


def test_contract_members_exist_on_both_backends():
    android, ios = backends()

    for member in CONTRACT:
        assert hasattr(android, member), member
        assert hasattr(ios, member), member


def test_swipe_speaks_the_same_millisecond_language_on_both_platforms():
    # The contract keeps adb's millisecond duration; the ios client
    # converts to WDA's seconds internally.
    android, ios = backends()

    for backend in (android, ios):
        assert inspect.signature(backend.swipe).parameters["duration"].default == 350
