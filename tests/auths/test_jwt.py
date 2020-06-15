import pytest
import jwt

from ratelimit.auths.jwt import create_jwt_auth


@pytest.mark.parametrize(
    "scope, user, group",
    [
        ({"headers": ()}, "no-jwt-client", "dont-found-jwt"),
        (
            {
                "headers": (
                    (
                        b"authorization",
                        b"Bearer "
                        + jwt.encode(
                            {"user": "user", "group": "group"}, "test-key", "HS256"
                        ),
                    ),
                ),
            },
            "user",
            "group",
        ),
        (
            {
                "headers": (
                    (
                        b"authorization",
                        b"Bearer "
                        + jwt.encode(
                            {"user": "user", "group": "group"}, "test-key", "HS512"
                        ),
                    ),
                ),
            },
            "user",
            "group",
        ),
    ],
)
@pytest.mark.asyncio
async def test_jwt_auth(scope, user, group):
    assert (await create_jwt_auth("test-key", ["HS256", "HS512"])(scope)) == (
        user,
        group,
    )
