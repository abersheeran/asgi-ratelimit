import asyncio

import httpx
import pytest

from ratelimit import RateLimitMiddleware, Rule
from ratelimit.backends.simple import MemoryBackend

from .backend_utils import auth_func, base_test_cases, base_test_multi, hello_world


@pytest.mark.asyncio
@pytest.mark.parametrize("memory_backend", [MemoryBackend])
async def test_simple(memory_backend):
    rate_limit = RateLimitMiddleware(
        hello_world,
        auth_func,
        memory_backend(),
        {
            r"/second_limit": [Rule(second=1), Rule(group="admin")],
            r"/minute.*": [Rule(minute=1), Rule(group="admin")],
            r"/multi-minute": [Rule(minute=2), Rule(group="admin")],
            r"/block": [Rule(second=1, block_time=5)],
        },
    )
    async with httpx.AsyncClient(
        app=rate_limit, base_url="http://testserver"
    ) as client:  # type: httpx.AsyncClient
        await base_test_cases(client)
        await base_test_multi(client)


@pytest.mark.asyncio
@pytest.mark.parametrize("memory_backend", [MemoryBackend])
async def test_other(memory_backend):
    rate_limit = RateLimitMiddleware(
        hello_world,
        auth_func,
        memory_backend(),
        {
            r"/second_limit": [Rule(second=1, block_time=50)],
        },
    )
    async with httpx.AsyncClient(
        app=rate_limit,
        base_url="http://testserver",
        headers={"user": "user", "group": "default"},
    ) as client:  # type: httpx.AsyncClient

        path = "/second_limit"

        response = await client.get(path)
        assert response.status_code == 200

        response = await client.get(path)
        assert response.status_code == 429

        await asyncio.sleep(1)

        response = await client.get(path)
        assert response.status_code == 429

        assert rate_limit.backend.remove_user("user")
        assert rate_limit.backend.remove_rule(path, f"{path}:user:second")

        response = await client.get("/second_limit")
        assert response.status_code == 200
