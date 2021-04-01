import asyncio
import datetime
import logging

import httpx
import pytest
from aredis import StrictRedis

from ratelimit import RateLimitMiddleware, Rule
from ratelimit.auths import EmptyInformation
from ratelimit.backends.redis import RedisBackend
from ratelimit.backends.slidingredis import SlidingRedisBackend


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
        return True


logger = logging.getLogger("ratelimit")
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    fmt="+%(relative)s - %(name)s - %(levelname)s - %(message)s"
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
@pytest.mark.parametrize("redisbackend", [SlidingRedisBackend, RedisBackend])
async def test_redis(redisbackend):
    await StrictRedis().flushdb()
    rate_limit = RateLimitMiddleware(
        hello_world,
        auth_func,
        redisbackend(),
        {
            r"/second_limit": [Rule(second=1), Rule(group="admin")],
            r"/minute.*": [Rule(minute=1), Rule(group="admin")],
            r"/block": [Rule(second=1, block_time=5)],
        },
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

        await asyncio.sleep(1)

        response = await client.get(
            "/block", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 429

        response = await client.get(
            "/block", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 429

        await asyncio.sleep(4)

        response = await client.get(
            "/block", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 200


@pytest.mark.asyncio
@pytest.mark.parametrize("redisbackend", [RedisBackend])
async def test_multiple_(redisbackend):
    await StrictRedis().flushdb()
    rate_limit = RateLimitMiddleware(
        hello_world,
        auth_func,
        redisbackend(),
        {r"/multiple": [Rule(second=1, minute=3)]},
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
        await asyncio.sleep(1)
        # 0+1 2+0 = 1 2
        response = await client.get(
            "/multiple", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 200
        # 1-1 2-1 = 0 1
        response = await client.get(
            "/multiple", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 429
        await asyncio.sleep(2)
        # 0+1 1+0 = 1 1
        response = await client.get(
            "/multiple", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 200
        # 1-1 1-1 = 0 0


@pytest.mark.asyncio
@pytest.mark.parametrize("redisbackend", [SlidingRedisBackend])
async def test_multiple(redisbackend):
    await StrictRedis().flushdb()
    rate_limit = RateLimitMiddleware(
        hello_world,
        auth_func,
        redisbackend(),
        {r"/multiple": [Rule(second=1, minute=3)]},
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
        await asyncio.sleep(2)
        # 0+1 0+0 = 1 0
        response = await client.get(
            "/multiple", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 429
