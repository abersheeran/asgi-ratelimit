from .types import ASGIApp, Receive, Scope, Send


def _on_blocked(retry_after: int) -> ASGIApp:
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
        await send(
            {"type": "http.response.body", "body": b"", "more_body": False})

    return default_429
