import asyncio
import datetime
import logging

import httpx
import pytest
from redis.asyncio import StrictRedis

from ratelimit import RateLimitMiddleware, Rule
from ratelimit.backends.redis import RedisBackend
from ratelimit.backends.slidingredis import SlidingRedisBackend

from .backend_utils import auth_func, base_test_cases, hello_world


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
for handler in logger.handlers:
    handler.addFilter(TimeFilter())
    handler.setFormatter(formatter)


@pytest.mark.asyncio
@pytest.mark.parametrize("redis_backend", [SlidingRedisBackend, RedisBackend])
async def test_redis(redis_backend):
    await StrictRedis().flushdb()
    rate_limit = RateLimitMiddleware(
        hello_world,
        auth_func,
        redis_backend(),
        {
            r"/second_limit": [Rule(second=1), Rule(group="admin")],
            r"/minute.*": [Rule(minute=1), Rule(group="admin")],
            r"/block": [Rule(second=1, block_time=5)],
        },
    )
    async with httpx.AsyncClient(
        app=rate_limit, base_url="http://testserver"
    ) as client:  # type: httpx.AsyncClient

        await base_test_cases(client)


@pytest.mark.asyncio
@pytest.mark.parametrize("redis_backend", [RedisBackend])
async def test_multiple(redis_backend):
    await StrictRedis().flushdb()
    rate_limit = RateLimitMiddleware(
        hello_world,
        auth_func,
        redis_backend(),
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
@pytest.mark.parametrize("redis_backend", [SlidingRedisBackend])
async def test_multiple_with_punitive(redis_backend):
    await StrictRedis().flushdb()
    rate_limit = RateLimitMiddleware(
        hello_world,
        auth_func,
        redis_backend(),
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
