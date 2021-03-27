import pytest

from ratelimit.auths import EmptyInformation
from ratelimit.auths.session import from_session


@pytest.mark.parametrize(
    "scope, user, group",
    [
        ({"session": {"user": "user-id"}}, "user-id", "default"),
        (
            {"session": {"user": "other-user-id", "group": "group-name"}},
            "other-user-id",
            "group-name",
        ),
    ],
)
@pytest.mark.asyncio
async def test_from_session(scope, user, group):
    assert (await from_session(scope)) == (user, group)


@pytest.mark.parametrize("scope", [{"session": {}}])
@pytest.mark.asyncio
async def test_error(scope):
    with pytest.raises(EmptyInformation):
        await from_session(scope)
