# ASGI RateLimit

Limit user access frequency. Base on ASGI.

100% coverage. High performance. Support regular matching. Customizable.

## Install

```
# Only install
pip install asgi-ratelimit

# Use redis
pip install asgi-ratelimit[redis]

# Use jwt
pip install asgi-ratelimit[jwt]

# Install all
pip install asgi-ratelimit[full]
```

## Usage

The following example will limit users under the `"default"` group to access `/second_limit` at most once per second and `/minute_limit` at most once per minute. And the users in the `"admin"` group have no restrictions.

```python
from typing import Tuple

from ratelimit import RateLimitMiddleware, Rule
from ratelimit.auths import EmptyInformation
from ratelimit.backends.redis import RedisBackend


async def AUTH_FUNCTION(scope) -> Tuple[str, str]:
    """
    Resolve the user's unique identifier and the user's group from ASGI SCOPE.

    If there is no user information, it should raise `EmptyInformation`.
    If there is no group information, it should return "default".
    """
    return USER_UNIQUE_ID, GROUP_NAME


rate_limit = RateLimitMiddleware(
    ASGI_APP,
    AUTH_FUNCTION,
    RedisBackend(),
    {
        r"^/second_limit": [Rule(second=1), Rule(group="admin")],
        r"^/minute_limit": [Rule(minute=1), Rule(group="admin")],
    },
)

# Or in starlette/fastapi/index.py
app.add_middleware(
    RateLimitMiddleware,
    authenticate=AUTH_FUNCTION,
    backend=RedisBackend(),
    config={
        r"^/second_limit": [Rule(second=1), Rule(group="admin")],
        r"^/minute_limit": [Rule(minute=1), Rule(group="admin")],
    },
)
```

### Block time

When the user's request frequency triggers the upper limit, all requests in the following period of time will be returned with a `429` status code.

Example: `Rule(second=5, block_time=60)`, this rule will limit the user to a maximum of 5 visits per second. Once this limit is exceeded, all requests within the next 60 seconds will return `429`.

### Custom block handler

Just specify `on_blocked` and you can customize the asgi application that is called when blocked.

```python
async def yourself_429(scope: Scope, receive: Receive, send: Send) -> None:
    await send({"type": "http.response.start", "status": 429})
    await send({"type": "http.response.body", "body": b"429 page", "more_body": False})


RateLimitMiddleware(..., on_blocked=yourself_429)
```

### Built-in auth functions

#### Client IP

```python
from ratelimit.auths.ip import client_ip
```

Obtain user IP through `scope["client"]` or `X-Real-IP`.

#### Starlette Session

```python
from ratelimit.auths.session import from_session
```

Get `user` and `group` from `scope["session"]`.

If key `group` not in session, will return `default`. If key `user` not in session, will raise a `EmptyInformation`.

#### Json Web Token

```python
from ratelimit.auths.jwt import create_jwt_auth

jwt_auth = create_jwt_auth("KEY", "HS256")
```

Get `user` and `group` from JWT that in `Authorization` header.
