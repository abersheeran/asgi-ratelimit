import jwt
import pytest

from ratelimit.auths import EmptyInformation
from ratelimit.auths.jwt import create_jwt_auth


@pytest.mark.parametrize(
    "scope, user, group",
    [
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
        (
            {
                "headers": (
                    (
                        b"authorization",
                        b"Bearer " + jwt.encode({"user": "user"}, "test-key", "HS256"),
                    ),
                ),
            },
            "user",
            "default",
        )
    ],
)
@pytest.mark.asyncio
async def test_jwt_auth(scope, user, group):
    assert (await create_jwt_auth("test-key", ["HS256", "HS512"])(scope)) == (
        user,
        group,
    )


@pytest.mark.parametrize(
    "scope, user, group",
    [
        (
            {
                "headers": (
                    (
                        b"authorization",
                        b"Bearer " + jwt.encode({"user_id": "user"}, "test-key", "HS256"),
                    ),
                ),
            },
            "user",
            "default",
        ),
    ]
)
@pytest.mark.asyncio
async def test_jwt_auth_other_user_key(scope, user, group):
    val = await create_jwt_auth(
        "test-key", ["HS256", "HS512"], user_key="user_id"
    )(scope)
    assert val == (
        user,
        group,
    )


@pytest.mark.parametrize(
    "scope",
    [
        {"headers": ()},
        {
            "headers": (
                (
                    b"wrongkey",
                    b"Bearer " + jwt.encode({"username": "user"}, "test-key", "HS256"),
                ),
            ),
        },
        {
            "headers": (
                (
                    b"authorization",
                    b"Bearer " + jwt.encode({"username": "user"}, "test-key", "HS256"),
                ),
            ),
        },
    ],
)
@pytest.mark.asyncio
async def test_error(scope):
    with pytest.raises(EmptyInformation):
        await create_jwt_auth("test-key", ["HS256", "HS512"])(scope)
