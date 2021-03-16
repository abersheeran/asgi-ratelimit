import asyncio

import httpx
import pytest
from aredis import StrictRedis

from ratelimit import RateLimitMiddleware, Rule
from ratelimit.auths import EmptyInformation
from ratelimit.backends.redis import RedisBackend


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
async def test_redis():
    await StrictRedis().flushdb()
    rate_limit = RateLimitMiddleware(
        hello_world,
        auth_func,
        RedisBackend(),
        {
            r"/second_limit": [Rule(second=1), Rule(group="admin")],
            r"/minute.*": [Rule(minute=1), Rule(group="admin")],
            r"/block": [Rule(second=1, block_time=5)],
            r"/multiple": [Rule(second=1, hour=2)]
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

        # multiple 1/s and 2/hour
        # 200 - no wait - 429 - wait 1 - 200 - wait 1 - 429
        response = await client.get(
            "/multiple", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 200
        response = await client.get(
            "/multiple", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 429
        await asyncio.sleep(1)
        response = await client.get(
            "/multiple", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 200
        await asyncio.sleep(1)
        response = await client.get(
            "/multiple", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 429
