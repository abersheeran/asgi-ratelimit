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
            "headers": [[b"content-type", b"text/plain"],],
        }
    )
    await send({"type": "http.response.body", "body": b"Hello world!"})
    await send({"type": "http.response.disconnect"})


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
            "/second_limit": [Rule(second=1), Rule(group="admin")],
            "/minute.*": [Rule(minute=1), Rule(group="admin")],
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
