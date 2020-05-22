import pytest

from ratelimit.auths.ip import client_ip


@pytest.mark.parametrize(
    "scope, real_ip",
    [
        ({"client": ("127.0.0.1", 8000), "headers": tuple()}, "no-ip-client"),
        ({"client": ("172.18.81.1", 8000), "headers": tuple()}, "no-ip-client"),
        ({"client": ("1.1.1.1", 8000), "headers": tuple()}, "1.1.1.1"),
        (
            {
                "client": ("127.0.0.1", 8000),
                "headers": (
                    (b"x-forwarded-for", b"1.1.1.1, 70.41.3.18, 150.172.238.178"),
                    (b"x-real-ip", b"70.41.3.18"),
                ),
            },
            "1.1.1.1",
        ),
        (
            {
                "client": ("127.0.0.1", 8000),
                "headers": (
                    (b"x-real-ip", b"70.41.3.18"),
                    (b"x-forwarded-for", b"1.1.1.1, 70.41.3.18, 150.172.238.178"),
                ),
            },
            "70.41.3.18",
        ),
    ],
)
def test_client_ip(scope, real_ip):
    assert client_ip(scope)[0] == real_ip
