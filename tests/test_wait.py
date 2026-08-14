from datetime import datetime, timezone

import pytest

from ants_automation.domain.models import Observation
from ants_automation.runtime.errors import TimeoutError
from ants_automation.runtime.wait import wait_until


def test_wait_until_returns_matching_observation():
    current = Observation(datetime.now(timezone.utc), "test", None, None, None, None, None)
    assert wait_until(lambda: current, lambda item: item is current, 0.1, 0.01) is current


def test_wait_until_times_out():
    with pytest.raises(TimeoutError):
        wait_until(lambda: Observation(datetime.now(timezone.utc), "test", None, None, None, None, None), lambda _: False, 0.02, 0.01)
