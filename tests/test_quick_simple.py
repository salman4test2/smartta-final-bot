# tests/test_quick_simple.py - Simple focused tests based on your provided examples
import pytest
from uuid import UUID

pytestmark = pytest.mark.anyio

async def test_create_user_success(client):
    resp = await client.post("/users", json={"user_id": "bob", "password": "password123"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == "bob"
    assert "created_at" in data and "updated_at" in data

async def test_create_user_duplicate_returns_400(client):
    # first create
    r1 = await client.post("/users", json={"user_id": "dup", "password": "password123"})
    assert r1.status_code == 200
    # duplicate create
    r2 = await client.post("/users", json={"user_id": "dup", "password": "password123"})
    assert r2.status_code == 400
    assert r2.json()["detail"] == "User already exists"

async def test_login_success_and_invalid(client, user_alice):
    ok = await client.post("/users/login", json=user_alice)
    assert ok.status_code == 200
    body = ok.json()
    assert body["user_id"] == "alice"
    assert body["message"] == "Login successful"

    # wrong password → 401
    bad = await client.post("/users/login", json={"user_id": "alice", "password": "nope"})
    assert bad.status_code == 401

    # unknown user → 401
    bad2 = await client.post("/users/login", json={"user_id": "nouser", "password": "x"})
    assert bad2.status_code == 401

async def test_post_session_new_with_user_association(client, user_alice):
    # Create a named session via POST
    resp = await client.post("/session/new", json={
        "user_id": user_alice["user_id"],
        "session_name": "Diwali Template Creation"
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "session_id" in data
    UUID(data["session_id"])  # validate UUID format
    assert data["session_name"] == "Diwali Template Creation"
    assert data["user_id"] == user_alice["user_id"]

    # List sessions should include the one we just created
    ls = await client.get(f"/users/{user_alice['user_id']}/sessions")
    assert ls.status_code == 200
    payload = ls.json()
    assert payload["user_id"] == user_alice["user_id"]
    assert payload["total_sessions"] == 1
    sess = payload["sessions"][0]
    assert sess["session_id"] == data["session_id"]
    assert sess["session_name"] == "Diwali Template Creation"
    assert sess["message_count"] == 0

async def test_get_session_new_with_name_and_user(client, user_alice):
    # Legacy GET but allow a name (your GET supports session_name)
    resp = await client.get("/session/new", params={
        "user_id": user_alice["user_id"],
        "session_name": "Promo Run"
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_name"] == "Promo Run"
    assert body["user_id"] == user_alice["user_id"]
    UUID(body["session_id"])

    # Verify listing reflects it
    ls = await client.get(f"/users/{user_alice['user_id']}/sessions")
    assert ls.status_code == 200
    assert ls.json()["total_sessions"] == 1

async def test_update_session_name_success_and_validation_errors(client, user_alice):
    # Create
    resp = await client.post("/session/new", json={"user_id": user_alice["user_id"], "session_name": "Old Name"})
    sid = resp.json()["session_id"]

    # Success rename
    ok = await client.put(f"/users/{user_alice['user_id']}/sessions/{sid}/name",
                          json={"session_name": "New Friendly Name"})
    assert ok.status_code == 200
    assert ok.json()["session_name"] == "New Friendly Name"

    # Too long name → 422 (relies on schemas.SessionRename max_length=120)
    long_name = "x" * 121
    bad = await client.put(f"/users/{user_alice['user_id']}/sessions/{sid}/name",
                           json={"session_name": long_name})
    assert bad.status_code == 422

    # Blank name → 422 (min_length=1)
    bad2 = await client.put(f"/users/{user_alice['user_id']}/sessions/{sid}/name",
                            json={"session_name": ""})
    assert bad2.status_code == 422
