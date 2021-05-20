import random
import time

import pytest

from ratelimit.backends import BaseBackend
from ratelimit.rule import RULENAMES, Rule


@pytest.fixture
def last_timestamps():
    return [random.choice([time.time() - 60 ** i, None]) for i in range(len(RULENAMES))]


@pytest.mark.parametrize("second", [2, None])
@pytest.mark.parametrize("minute", [2, None])
@pytest.mark.parametrize("hour", [2, None])
@pytest.mark.parametrize("day", [2, None])
@pytest.mark.parametrize("month", [2, None])
def test_calc_incr_value(last_timestamps, second, minute, hour, day, month):
    result = {}
    if second:
        result.update({"second": {"value": second - 1, "ttl": 1 + 1}})
    if minute:
        result.update({"minute": {"value": minute - 1, "ttl": 60 + 1}})
    if hour:
        result.update({"hour": {"value": hour - 1, "ttl": 60 * 60 + 1}})
    if day:
        result.update({"day": {"value": day - 1, "ttl": 60 * 60 * 24 + 1}})
    if month:
        result.update({"month": {"value": month - 1, "ttl": 60 * 60 * 24 * 31 + 1}})

    assert (
        BaseBackend.calc_incr_value(
            last_timestamps, Rule("default", second, minute, hour, day, month)
        )
        == result
    )
