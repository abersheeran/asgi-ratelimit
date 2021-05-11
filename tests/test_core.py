from contextlib import suppress as do_not_raise

import httpx
import pytest

from ratelimit import FixedRule, RateLimitMiddleware
from ratelimit.auths import EmptyInformation
from ratelimit.backends.redis import RedisBackend
from ratelimit.backends.slidingredis import SlidingRedisBackend


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


@pytest.mark.asyncio
async def test_on_auth_error_default():
    rate_limit = RateLimitMiddleware(
        hello_world,
        auth_func,
        RedisBackend(),
        {
            r"/": [FixedRule(group="admin")],
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
            r"/": [FixedRule(group="admin")],
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "backend, retry_after_enabled, retry_after_type, expectation",
    [
        (RedisBackend, True, None, pytest.raises(ValueError)),
        (RedisBackend, True, "seconds", pytest.raises(ValueError)),
        (RedisBackend, True, "httpdate", pytest.raises(ValueError)),
        (RedisBackend, False, None, do_not_raise()),
        (SlidingRedisBackend, False, None, do_not_raise()),
        (SlidingRedisBackend, True, None, pytest.raises(ValueError)),
        (SlidingRedisBackend, True, "seconds", do_not_raise()),
        (SlidingRedisBackend, True, "httpdate", do_not_raise()),
        (SlidingRedisBackend, True, "no", pytest.raises(ValueError)),
    ],
)
async def test_error_if_retry_after_set_incorrectly(
    backend, retry_after_enabled, retry_after_type, expectation
):
    with expectation:
        RateLimitMiddleware(
            hello_world,
            auth_func,
            backend(),
            {},
            retry_after_enabled=retry_after_enabled,
            retry_after_type=retry_after_type,
        )
