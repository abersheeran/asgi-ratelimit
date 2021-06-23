import re
from typing import Awaitable, Callable, Dict, Optional, Sequence, Tuple

from .backends import BaseBackend
from .rule import RULENAMES, Rule
from .types import ASGIApp, Receive, Scope, Send


def on_blocked(retry_after: int) -> ASGIApp:
    async def default_429(scope: Scope, receive: Receive, send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 429,
                "headers": [
                    (b"retry-after", str(retry_after).encode("ascii")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    return default_429


class RateLimitMiddleware:
    """
    rate limit middleware
    """

    def __init__(
        self,
        app: ASGIApp,
        authenticate: Callable[[Scope], Awaitable[Tuple[str, str]]],
        backend: BaseBackend,
        config: Dict[str, Sequence[Rule]],
        *,
        on_auth_error: Optional[Callable[[Exception], Awaitable[ASGIApp]]] = None,
        on_blocked: Callable[[int], ASGIApp] = on_blocked,
    ) -> None:
        self.app = app
        self.authenticate = authenticate
        self.backend = backend
        self.config: Dict[re.Pattern, Sequence[Rule]] = {
            re.compile(path): value for path, value in config.items()
        }
        self.on_auth_error = on_auth_error
        self.on_blocked = on_blocked

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

        if not [name for name in RULENAMES if getattr(rule, name) is not None]:
            return await self.app(scope, receive, send)

        retry_after = await self.backend.retry_after(url_path, user, rule)
        if retry_after == 0:
            return await self.app(scope, receive, send)

        return await self.on_blocked(retry_after)(scope, receive, send)
