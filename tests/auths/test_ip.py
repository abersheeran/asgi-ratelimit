import pytest

from ratelimit.auths import EmptyInformation
from ratelimit.auths.ip import client_ip


@pytest.mark.parametrize(
    "scope, real_ip",
    [
        ({"client": ("1.1.1.1", 8000), "headers": tuple()}, "1.1.1.1"),
        (
            {
                "client": ("127.0.0.1", 8000),
                "headers": (
                    (b"x-forwarded-for", b"1.1.1.1, 70.41.3.18, 150.172.238.178"),
                    (b"x-real-ip", b"70.41.3.18"),
                ),
            },
            "70.41.3.18",
        ),
    ],
)
@pytest.mark.asyncio
async def test_client_ip(scope, real_ip):
    assert (await client_ip(scope))[0] == real_ip


@pytest.mark.parametrize(
    "scope",
    [
        {"client": ("127.0.0.1", 8000), "headers": ((b"host", b"example.com"),)},
        {"client": ("172.18.81.1", 8000), "headers": tuple()},
    ],
)
@pytest.mark.asyncio
async def test_error(scope):
    with pytest.raises(EmptyInformation):
        await client_ip(scope)
