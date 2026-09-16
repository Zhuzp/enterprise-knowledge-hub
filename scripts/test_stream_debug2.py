"""Debug chat 500 with detailed error body."""
import asyncio
import json
import traceback

from httpx import ASGITransport, AsyncClient

from app.main import app


async def main():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=120) as client:
        r = await client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        print("login", r.status_code, r.text[:200])
        if r.status_code != 200:
            return
        token = r.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        r2 = await client.post("/api/v1/chat/sessions", json={"title": "debug2"}, headers=headers)
        print("session", r2.status_code, r2.text[:200])
        sid = r2.json()["id"]

        for path_suffix in ["/messages", "/messages/stream"]:
            try:
                r3 = await client.post(
                    f"/api/v1/chat/sessions/{sid}{path_suffix}",
                    json={"question": "你好"},
                    headers=headers,
                )
                print(f"\n{path_suffix}: status={r3.status_code}")
                print(r3.text[:800])
            except Exception:
                traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
