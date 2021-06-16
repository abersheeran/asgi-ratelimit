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

The following example will limit users under the `"default"` group to access `/towns` at most once per second and `/forests` at most once per minute. And the users in the `"admin"` group have no restrictions.

```python
from typing import Tuple

from ratelimit import RateLimitMiddleware, Rule
from ratelimit.auths import EmptyInformation
from ratelimit.backends.redis import RedisBackend


rate_limit = RateLimitMiddleware(
    ASGI_APP,
    AUTH_FUNCTION,
    RedisBackend(),
    {
        r"^/towns": [Rule(second=1, group="default"), Rule(group="admin")],
        r"^/forests": [Rule(minute=1, group="default"), Rule(group="admin")],
    },
)

# Or if using Starlette, FastApi, or index.py framework
app.add_middleware(
    RateLimitMiddleware,
    authenticate=AUTH_FUNCTION,
    backend=RedisBackend(),
    config={
        r"^/towns": [Rule(second=1, group="default"), Rule(group="admin")],
        r"^/forests": [Rule(minute=1, group="default"), Rule(group="admin")],
    },
)
```

> :warning: **The pattern's order is important, rules are set on the first match**: Be careful here !

Next, provide a custom authenticate function, or use one of the [existing auth methods](#built-in-auth-functions).

```python
async def AUTH_FUNCTION(scope: Scope) -> Tuple[str, str]:
    """
    Resolve the user's unique identifier and the user's group from ASGI SCOPE.

    If there is no user information, it should raise `EmptyInformation`.
    If there is no group information, it should return "default".
    """
    # FIXME
    # You must write the logic of this function yourself,
    # or use the function in the following document directly.
    return USER_UNIQUE_ID, GROUP_NAME

rate_limit = RateLimitMiddleware(
    ASGI_APP,
    AUTH_FUNCTION,
    ...
)
```

The `Rule` type takes a time unit (e.g. `"second"`) and/or a `"group"`, as a param. If the `"group"` param is not specified then the `"authenticate"` method needs to return the "default group".

Example:
```python
    ...
    config={
        r"^/towns": [Rule(second=1), Rule(second=10, group="admin")],
    }
    ...


async def AUTH_FUNCTION(scope: Scope) -> Tuple[str, str]:
    ...
    # no group information about this user
    if user not in admins_group:
        return user_unique_id, 'default'

    return user_unique_id, user_group
```

### Customizable rules

It is possible to mix the rules to obtain higher level of control.

The below example will allow up to 10 requests per second and no more than 200 requests per minute, for everyone, for the same API endpoint.

```python
    ...
    config={
        r"^/towns": [Rule(minute=200, second=10)],
    }
    ...
```

Example for a "admin" group with higher limits.

```python
    ...
    config={
        r"^/towns": [
            Rule(day=400, minute=200, second=10),
            Rule(minute=500, second=25, group="admin"),
        ],
    }
    ...
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

Note: this auth method will not work if your IP address (such as 127.0.0.1 etc) is not allocated for public networks.

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

### Custom auth error handler

Normally exceptions raised in the authentication function result in an Internal Server Error, but you can pass a function to handle the errors and send the appropriate response back to the user. For example, if you're using FastAPI or Starlette:

```python
from fastapi.responses import JSONResponse
from ratelimit.types import ASGIApp

async def handle_auth_error(exc: Exception) -> ASGIApp:
    return JSONResponse({"message": "Unauthorized access."}, status_code=401)

RateLimitMiddleware(..., on_auth_error=handle_auth_error)
```

For advanced usage you can handle the response completely by yourself:

```python
from fastapi.responses import JSONResponse
from ratelimit.types import ASGIApp, Scope, Receive, Send

async def handle_auth_error(exc: Exception) -> ASGIApp:
    async def response(scope: Scope, receive: Receive, send: Send):
        # do something here e.g.
        # await send({"type": "http.response.start", "status": 429})
    return response
```
