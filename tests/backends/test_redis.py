import asyncio
import datetime
import logging

import httpx
import pytest
from aredis import StrictRedis

from ratelimit import FixedRule, RateLimitMiddleware
from ratelimit.auths import EmptyInformation
from ratelimit.backends.redis import RedisBackend
from ratelimit.backends.slidingredis import SlidingRedisBackend
from ratelimit.rule import CustomRule, LimitFrequency


class TimeFilter(logging.Filter):
    def filter(self, record):
        try:
            last = self.last
        except AttributeError:
            last = record.relativeCreated
        delta = datetime.datetime.fromtimestamp(
            record.relativeCreated / 1000.0
        ) - datetime.datetime.fromtimestamp(last / 1000.0)
        record.relative = "{0:.2f}".format(
            delta.seconds + delta.microseconds / 1000000.0
        )
        self.last = record.relativeCreated

        try:
            first = self.first
        except AttributeError:
            first = record.created
            self.first = record.created
        deltastart = datetime.datetime.fromtimestamp(
            record.created
        ) - datetime.datetime.fromtimestamp(first)
        record.relativestart = "{0:.2f}".format(
            deltastart.seconds + deltastart.microseconds / 1000000.0
        )
        return True


logger = logging.getLogger("ratelimit")
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    fmt="Total:%(relativestart)s (+%(relative)s) - %(name)s - %(levelname)s - %(message)s"
)
logger.addHandler(ch)
[hndl.addFilter(TimeFilter()) for hndl in logger.handlers]
[hndl.setFormatter(formatter) for hndl in logger.handlers]


async def hello_world(scope, receive, send):
    assert scope["type"] == "http"
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"text/plain"]],
        }
    )
    await send({"type": "http.response.body", "body": b"Hello world!"})


async def auth_func(scope):
    headers = scope["headers"]
    user, group = None, None
    for name, value in headers:  # type: bytes, bytes
        if name == b"user":
            user = value.decode("utf8")
        if name == b"group":
            group = value.decode("utf8")
    if user is None:
        raise EmptyInformation(scope)
    group = group or "default"
    return user, group


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "redisbackend, retry_after_enabled, retry_after_type",
    [
        (RedisBackend, False, None),
        (SlidingRedisBackend, False, None),
        (SlidingRedisBackend, True, "delay-seconds"),
        (SlidingRedisBackend, True, "http-date"),
    ],
    ids=[
        "retry-after not set RedisBakend",
        "retry-after not set SlidingRedisBakend",
        "retry-after in seconds",
        "retry-after as a http date",
    ],
)
async def test_redis(redisbackend, retry_after_enabled, retry_after_type):
    await StrictRedis().flushdb()
    rate_limit = RateLimitMiddleware(
        hello_world,
        auth_func,
        redisbackend(),
        {
            r"/second_limit": [FixedRule(second=1), FixedRule(group="admin")],
            r"/minute.*": [FixedRule(minute=1), FixedRule(group="admin")],
            r"/block": [FixedRule(second=1, block_time=5)],
        },
        retry_after_enabled=retry_after_enabled,
        retry_after_type=retry_after_type,
    )
    async with httpx.AsyncClient(
        app=rate_limit, base_url="http://testserver"
    ) as client:  # type: httpx.AsyncClient
        response = await client.get("/")
        assert response.status_code == 200

        response = await client.get(
            "/second_limit", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 200

        response = await client.get(
            "/second_limit", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 429
        if retry_after_enabled:
            assert "retry-after" in response.headers

        response = await client.get(
            "/second_limit", headers={"user": "admin-user", "group": "admin"}
        )
        assert response.status_code == 200

        await asyncio.sleep(1)

        response = await client.get(
            "/second_limit", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 200

        response = await client.get(
            "/minute_limit", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 200

        response = await client.get(
            "/minute_limit", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 429
        if retry_after_enabled:
            assert "retry-after" in response.headers

        response = await client.get(
            "/minute_limit", headers={"user": "admin-user", "group": "admin"}
        )
        assert response.status_code == 200

        response = await client.get(
            "/block", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 200

        response = await client.get(
            "/block", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 429
        if retry_after_enabled:
            assert "retry-after" in response.headers

        await asyncio.sleep(1)

        response = await client.get(
            "/block", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 429
        if retry_after_enabled:
            assert "retry-after" in response.headers

        response = await client.get(
            "/block", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 429
        if retry_after_enabled:
            assert "retry-after" in response.headers

        await asyncio.sleep(4)

        response = await client.get(
            "/block", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("redisbackend", [SlidingRedisBackend])
@pytest.mark.parametrize(
    "retry_after_enabled, retry_after_type",
    [(False, None), (True, "delay-seconds"), (True, "http-date")],
    ids=["retry-after not set", "retry-after in seconds", "retry-after as a http date"],
)
async def test_multiple(redisbackend, retry_after_enabled, retry_after_type):
    await StrictRedis().flushdb()
    rate_limit = RateLimitMiddleware(
        hello_world,
        auth_func,
        redisbackend(),
        {
            r"^/multiple$": [FixedRule(second=1, minute=3)],
            r"^/custom$": [CustomRule(rules=[LimitFrequency(limit=3, granularity=2)])],
            r"^/multiple_custom$": [
                CustomRule(
                    rules=[
                        LimitFrequency(limit=3, granularity=2),
                        LimitFrequency(limit=7, granularity=5),
                    ]
                )
            ],
        },
        retry_after_enabled=retry_after_enabled,
        retry_after_type=retry_after_type,
    )
    async with httpx.AsyncClient(
        app=rate_limit, base_url="http://testserver"
    ) as client:  # type: httpx.AsyncClient

        # multiple 1/s and 3/min
        # 1 3
        response = await client.get(
            "/multiple", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 200
        # 1-1 3-1 = 0 2
        response = await client.get(
            "/multiple", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 429
        if retry_after_enabled:
            assert "retry-after" in response.headers
        await asyncio.sleep(1)
        # 0+1 2-1 = 1 1
        response = await client.get(
            "/multiple", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 200
        # 1-1 1-1 = 0 0
        response = await client.get(
            "/multiple", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 429
        if retry_after_enabled:
            assert "retry-after" in response.headers
        await asyncio.sleep(2)
        # 0+1 0+0 = 1 0
        response = await client.get(
            "/multiple", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 429
        if retry_after_enabled:
            assert "retry-after" in response.headers

        # 3 times every 2s
        response = await client.get(
            "/custom", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 200
        response = await client.get(
            "/custom", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 200
        response = await client.get(
            "/custom", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 200
        response = await client.get(
            "/custom", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 429
        if retry_after_enabled:
            assert "retry-after" in response.headers
        await asyncio.sleep(1)
        response = await client.get(
            "/custom", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 429
        if retry_after_enabled:
            assert "retry-after" in response.headers
        await asyncio.sleep(0.9)
        response = await client.get(
            "/custom", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 429
        if retry_after_enabled:
            assert "retry-after" in response.headers
        await asyncio.sleep(0.1)
        response = await client.get(
            "/custom", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 200

        # multiple custom ie 3/2s and 7/5s
        response = await client.get(
            "/multiple_custom", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 200
        response = await client.get(
            "/multiple_custom", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 200
        response = await client.get(
            "/multiple_custom", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 200
        response = await client.get(
            "/multiple_custom", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 429
        if retry_after_enabled:
            assert "retry-after" in response.headers
        # reset the 2s limit, we're at 4 hits
        await asyncio.sleep(2)
        response = await client.get(
            "/multiple_custom", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 200
        response = await client.get(
            "/multiple_custom", headers={"user": "user", "group": "default"}
        )
        await asyncio.sleep(2)
        assert response.status_code == 200
        response = await client.get(
            "/multiple_custom", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 200
        # we're hitting the 7/5s limit
        response = await client.get(
            "/multiple_custom", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 429
        if retry_after_enabled:
            assert "retry-after" in response.headers
