# ASGI RateLimit

Limit user access frequency to specified URL. Base on ASGI.

## Install

```
# Only install
pip install asgi-ratelimit

# Use redis
pip install asgi-ratelimit[redis]
```

## Usage

The following example will limit users under the `"default"` group to access `/second_limit` at most once per second and `/minute_limit` at most once per minute. And the users in the `"admin"` group have no restrictions.

```python
from typing import Tuple

from ratelimit import RateLimitMiddleware, Rule
from ratelimit.backends.redis import RedisBackend

def auth_function(scope) -> Tuple[str, str]:
    """
    Resolve the user's unique identifier and the user's group from ASGI SCOPE.

    If there is no group information, it should return "default".
    """
    return USER_UNIQUE_ID, GROUP_NAME


rate_limit = RateLimitMiddleware(
    ASGI_APP,
    AUTH_FUNCTION,
    RedisBackend(),
    {
        "/second_limit": [Rule(second=1), Rule(group="admin")],
        "/minute_limit": [Rule(minute=1), Rule(group="admin")],
    },
)
```
