import re
import sys
from datetime import datetime
from typing import Awaitable, Callable, Dict, Optional, Sequence, Tuple, Union

if sys.version_info >= (3, 8):  # pragma: no cover
    from typing import Literal
else:
    from typing_extensions import Literal  # pragma: no cover


from .backends import BaseBackend
from .backends.slidingredis import SlidingRedisBackend
from .rule import RULENAMES, CustomRule, FixedRule
from .types import ASGIApp, Receive, Scope, Send


async def default_429(scope: Scope, receive: Receive, send: Send) -> None:

    await send(
        {"type": "http.response.start", "status": 429, "headers": scope["headers"]}
    )
    await send({"type": "http.response.body", "body": b"", "more_body": False})


class RateLimitMiddleware:
    """
    rate limit middleware
    """

    def __init__(
        self,
        app: ASGIApp,
        authenticate: Callable[[Scope], Awaitable[Tuple[str, str]]],
        backend: BaseBackend,
        config: Dict[str, Sequence[Union[FixedRule, CustomRule]]],
        *,
        on_auth_error: Optional[Callable[[Exception], Awaitable[ASGIApp]]] = None,
        on_blocked: ASGIApp = default_429,
        retry_after_enabled: bool = False,
        retry_after_type: Optional[Literal["delay-seconds", "http-date"]] = None,
    ) -> None:
        self.app = app
        self.authenticate = authenticate
        self.backend = backend
        self.config: Dict[re.Pattern, Sequence[Union[FixedRule, CustomRule]]] = {
            re.compile(path): value for path, value in config.items()
        }
        self.on_auth_error = on_auth_error
        self.on_blocked = on_blocked
        self.retry_after_enabled = retry_after_enabled
        self.retry_after_type = retry_after_type
        if self.retry_after_enabled and self.retry_after_type not in [
            "delay-seconds",
            "http-date",
        ]:
            raise ValueError(
                "retry_after_type must be set to either 'delay-seconds' or 'http-date' if retry_after_enabled is True"
            )
        if self.retry_after_enabled and not isinstance(
            self.backend, SlidingRedisBackend
        ):
            raise ValueError("retry-after implemented on SlidingRedisBackend only")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":  # pragma: no cover
            return await self.app(scope, receive, send)

        url_path = scope["path"]
        for pattern, rules in self.config.items():
            if pattern.match(url_path):
                # After finding the first rule that can match the path,
                # calculate the user ID and group
                try:
                    user, group = await self.authenticate(scope)
                except Exception as exc:
                    if self.on_auth_error is not None:
                        reponse = await self.on_auth_error(exc)
                        return await reponse(scope, receive, send)
                    raise exc

                # Select the first rule that can be matched
                _rules = [rule for rule in rules if group == rule.group]
                if _rules:
                    rule = _rules[0]
                    break
        else:  # If no rule can match, run `self.app` and return
            return await self.app(scope, receive, send)

        if isinstance(rule, FixedRule):
            has_rule = bool(
                [name for name in RULENAMES if getattr(rule, name) is not None]
            )
        elif isinstance(rule, CustomRule):  # pragma: no cover
            has_rule = True

        if self.retry_after_enabled and isinstance(self.backend, SlidingRedisBackend):
            allow, limits = await self.backend.allow_request(url_path, user, rule)
            if not has_rule or allow:
                return await self.app(scope, receive, send)
            else:
                rah = self.limit_to_header(limits["epoch"], max(limits["expire_in"]))
                return await self.retry_after_response(
                    scope, receive, send, retry_after_header=rah
                )
        else:
            allow, limits = await self.backend.allow_request(url_path, user, rule)
            if not has_rule or allow:
                return await self.app(scope, receive, send)

        return await self.on_blocked(scope, receive, send)

    async def retry_after_response(
        self, scope: Scope, receive: Receive, send: Send, retry_after_header: bytes
    ) -> None:
        headers = scope["headers"]
        headers.append((b"retry-after", retry_after_header))
        await self.on_blocked(scope, receive, send)

    def limit_to_header(self, epoch: float, limit: float) -> bytes:
        if self.retry_after_type == "http-date":
            dt_value = datetime.utcfromtimestamp(epoch + limit)
            header_value = dt_value.strftime("%a, %d %b %Y %H:%M:%S UTC").encode()
        elif self.retry_after_type == "delay-seconds":
            header_value = str(int(limit) + 1).encode()
        else:
            raise ValueError()
        return header_value
