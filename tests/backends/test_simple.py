import httpx
import pytest

from ratelimit import RateLimitMiddleware, Rule
from ratelimit.backends.simple import MemoryBackend

from .backend_utils import auth_func, base_test_cases, hello_world


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
            r"/block": [Rule(second=1, block_time=5)],
        },
    )
    async with httpx.AsyncClient(
        app=rate_limit, base_url="http://testserver"
    ) as client:  # type: httpx.AsyncClient
        await base_test_cases(client)
