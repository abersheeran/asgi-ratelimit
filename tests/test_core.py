import re

import httpx
import pytest

from ratelimit import RateLimitMiddleware, Rule
from ratelimit.auths import EmptyInformation
from ratelimit.backends.redis import RedisBackend
from ratelimit.types import Receive, Scope, Send


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
    assert group in ["default", "admin"], "Invalid group"
    group = group or "default"
    return user, group


async def handle_auth_error(exc):
    async def send_response(scope, receive, send):
        await send({"type": "http.response.start", "status": 401})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    return send_response


def test_invalid_init_config():
    # invalid path regexp
    with pytest.raises(re.error):
        RateLimitMiddleware(
            hello_world,
            auth_func,
            RedisBackend(),
            {
                r"??.*": [Rule(group="admin")],
            },
        )

    # invalid authenticate
    with pytest.raises(AssertionError):
        RateLimitMiddleware(
            hello_world,
            "123",
            RedisBackend(),
            {
                r"/test": [Rule(group="admin")],
            },
        )

    # invalid backend
    with pytest.raises(AssertionError):
        RateLimitMiddleware(
            hello_world,
            auth_func,
            None,
            {
                r"/test": [Rule(group="admin")],
            },
        )


@pytest.mark.asyncio
async def test_on_auth_error_default():
    rate_limit = RateLimitMiddleware(
        hello_world,
        auth_func,
        RedisBackend(),
        {
            r"/": [Rule(group="admin")],
        },
    )
    async with httpx.AsyncClient(
        app=rate_limit, base_url="http://testserver"
    ) as client:  # type: httpx.AsyncClient

        response = await client.get("/", headers={"user": "test", "group": "default"})
        assert response.status_code == 200
        assert response.text == "Hello world!"

        # No headers result in EmptyInformation
        with pytest.raises(EmptyInformation):
            await client.get("/", headers=None)

        # Raise the right exception
        with pytest.raises(AssertionError):
            await client.get("/", headers={"user": "test", "group": "-"})


@pytest.mark.asyncio
async def test_on_auth_error_with_handler():
    rate_limit = RateLimitMiddleware(
        hello_world,
        auth_func,
        RedisBackend(),
        {
            r"/": [Rule(group="admin")],
        },
        on_auth_error=handle_auth_error,
    )
    async with httpx.AsyncClient(
        app=rate_limit, base_url="http://testserver"
    ) as client:  # type: httpx.AsyncClient

        response = await client.get("/", headers={"user": "test", "group": "default"})
        assert response.status_code == 200
        assert response.text == "Hello world!"

        response = await client.get("/", headers=None)
        assert response.status_code == 401
        assert response.text == ""


def yourself_429(retry_after: int):
    async def inside_yourself_429(scope: Scope, receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 429})
        await send(
            {
                "type": "http.response.body",
                "body": b"custom 429 page",
                "more_body": False,
            }
        )

    return inside_yourself_429


@pytest.mark.asyncio
async def test_custom_blocked():
    rate_limit = RateLimitMiddleware(
        hello_world,
        authenticate=auth_func,
        backend=RedisBackend(),
        config={r"/": [Rule(second=1), Rule(group="admin")]},
        on_blocked=yourself_429,
    )

    async with httpx.AsyncClient(
        app=rate_limit, base_url="http://testserver"
    ) as client:  # type: httpx.AsyncClient

        response = await client.get("/", headers={"user": "user", "group": "default"})
        assert response.status_code == 200

        response = await client.get("/", headers={"user": "user", "group": "default"})
        assert response.status_code == 429
        assert response.content == b"custom 429 page"


@pytest.mark.asyncio
async def test_rule_zone():
    rate_limit = RateLimitMiddleware(
        hello_world,
        auth_func,
        RedisBackend(),
        {
            r"/message": [Rule(second=1, zone="common")],
            r"/\d+": [Rule(second=1, zone="common")],
        },
    )
    async with httpx.AsyncClient(
        app=rate_limit, base_url="http://testserver"
    ) as client:  # type: httpx.AsyncClient

        response = await client.get("/10", headers={"user": "user", "group": "default"})
        assert response.status_code == 200

        response = await client.get(
            "/message", headers={"user": "user", "group": "default"}
        )
        assert response.status_code == 429
