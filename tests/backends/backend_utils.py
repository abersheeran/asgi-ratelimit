import asyncio

from ratelimit.auths import EmptyInformation


async def hello_world(scope, receive, send):
    assert scope["type"] == "http"
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"content-type", b"text/plain"]],
        }
    )
    await send({"type": "http.response.body", "body": b"Hello world!"})


async def auth_func(scope):
    headers = scope["headers"]
    user, group = None, None
    for name, value in headers:  # type: bytes, bytes
        if name == b"user":
            user = value.decode("utf8")
        if name == b"group":
            group = value.decode("utf8")
    if user is None:
        raise EmptyInformation(scope)
    group = group or "default"
    return user, group


async def base_test_multi(client):
    response = await client.get(
        "/multi-minute", headers={"user": "user", "group": "default"}
    )
    assert response.status_code == 200

    response = await client.get(
        "/multi-minute", headers={"user": "user", "group": "default"}
    )
    assert response.status_code == 200

    response = await client.get(
        "/multi-minute", headers={"user": "user", "group": "default"}
    )
    assert response.status_code == 429


async def base_test_cases(client):
    response = await client.get("/")
    assert response.status_code == 200

    # ========== Test second ===============

    response = await client.get(
        "/second_limit", headers={"user": "user", "group": "default"}
    )
    assert response.status_code == 200

    response = await client.get(
        "/second_limit", headers={"user": "user", "group": "default"}
    )
    assert response.status_code == 429
    assert response.headers["retry-after"] == "1"

    response = await client.get(
        "/second_limit", headers={"user": "admin-user", "group": "admin"}
    )
    assert response.status_code == 200

    await asyncio.sleep(1)
    response = await client.get(
        "/second_limit", headers={"user": "user", "group": "default"}
    )
    assert response.status_code == 200

    # ========== Test minute ===============

    response = await client.get(
        "/minute_limit", headers={"user": "user", "group": "default"}
    )
    assert response.status_code == 200

    response = await client.get(
        "/minute_limit", headers={"user": "user", "group": "default"}
    )
    assert response.status_code == 429

    response = await client.get(
        "/minute_limit", headers={"user": "admin-user", "group": "admin"}
    )
    assert response.status_code == 200

    # ========== Test block ===============

    response = await client.get("/block", headers={"user": "user", "group": "default"})
    assert response.status_code == 200

    response = await client.get("/block", headers={"user": "user", "group": "default"})
    assert response.status_code == 429
    assert response.headers["retry-after"] == "5"

    await asyncio.sleep(1)

    response = await client.get("/block", headers={"user": "user", "group": "default"})
    assert response.status_code == 429

    response = await client.get("/block", headers={"user": "user", "group": "default"})
    assert response.status_code == 429

    await asyncio.sleep(4)

    response = await client.get("/block", headers={"user": "user", "group": "default"})
    assert response.status_code == 200
