from typing import Dict, Sequence, Tuple, Callable

from .types import ASGIApp, Scope, Receive, Send
from .backends import BaseBackend
from .rule import Rule, RULENAMES


class RateLimitMiddleware:
    """
    rate limit middleware
    """

    def __init__(
        self,
        app: ASGIApp,
        authenticate: Callable[[Scope], Tuple[str, str]],
        backend: BaseBackend,
        config: Dict[str, Sequence[Rule]],
    ) -> None:
        self.app = app
        self.authenticate = authenticate
        self.backend = backend
        self.config = config

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        url_path = scope["path"]
        if url_path not in self.config:
            return await self.app(scope, receive, send)

        user, group = self.authenticate(scope)

        for rule in self.config[url_path]:
            if group == rule.group:
                break

        has_rule = bool([name for name in RULENAMES if getattr(rule, name) is not None])

        if not has_rule or await self.backend.allow_request(url_path, user, rule):
            return await self.app(scope, receive, send)

        await send({"type": "http.response.start", "status": 429})
        await send({"type": "http.response.body", "body": b"", "more_body": False})
        await send({"type": "http.response.disconnect"})
