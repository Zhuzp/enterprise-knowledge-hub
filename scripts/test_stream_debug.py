"""Debug script for stream chat 500 error."""
import json
import sys
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000/api/v1"


def req(method: str, path: str, body: dict | None = None, token: str | None = None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=120) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def main():
    # Try login with common test credentials
    for creds in [
        {"username": "admin", "password": "admin123"},
        {"username": "test", "password": "test123"},
        {"username": "demo", "password": "demo123"},
    ]:
        status, body = req("POST", "/auth/login", creds)
        if status == 200:
            token = json.loads(body)["access_token"]
            print(f"Logged in as {creds['username']}")
            break
    else:
        # Register new user
        import random
        u = f"testuser{random.randint(1000,9999)}"
        status, body = req("POST", "/auth/register", {"username": u, "password": "test123"})
        print(f"Register {u}: {status} {body[:200]}")
        status, body = req("POST", "/auth/login", {"username": u, "password": "test123"})
        if status != 200:
            print("Cannot login:", status, body)
            sys.exit(1)
        token = json.loads(body)["access_token"]

    status, body = req("POST", "/chat/sessions", {"title": "debug"}, token)
    print(f"Create session: {status} {body[:200]}")
    session_id = json.loads(body)["id"]

    # Non-stream test
    status, body = req(
        "POST",
        f"/chat/sessions/{session_id}/messages",
        {"question": "你好"},
        token,
    )
    print(f"Non-stream: {status} {body[:300]}")

    # Stream test
    status, body = req(
        "POST",
        f"/chat/sessions/{session_id}/messages/stream",
        {"question": "你好"},
        token,
    )
    print(f"Stream: {status}")
    print(body[:500] if body else "(empty)")


if __name__ == "__main__":
    main()
