# tests/test_sessions.py
import pytest
from uuid import UUID

pytestmark = pytest.mark.anyio

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

async def test_post_session_new_without_name(client, user_alice):
    # Create session without name
    resp = await client.post("/session/new", json={
        "user_id": user_alice["user_id"]
    })
    assert resp.status_code == 201
    data = resp.json()
    assert "session_id" in data
    UUID(data["session_id"])
    assert data["session_name"] is None
    assert data["user_id"] == user_alice["user_id"]

async def test_post_session_new_whitespace_stripping(client, user_alice):
    # Test that session name whitespace is stripped
    resp = await client.post("/session/new", json={
        "user_id": user_alice["user_id"],
        "session_name": "  My Test Session  "
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["session_name"] == "My Test Session"  # Should be stripped

async def test_post_session_new_validation_errors(client, user_alice):
    # Test too long session name (> 120 chars)
    long_name = "x" * 121
    resp = await client.post("/session/new", json={
        "user_id": user_alice["user_id"],
        "session_name": long_name
    })
    assert resp.status_code == 422  # Validation error
    
    # Test empty session name - should fail with min_length=1
    resp = await client.post("/session/new", json={
        "user_id": user_alice["user_id"],
        "session_name": ""
    })
    assert resp.status_code == 422  # Validation error

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

async def test_get_session_fetch_data(client, user_alice):
    # Create
    resp = await client.post("/session/new", json={"user_id": user_alice["user_id"], "session_name": "Draft A"})
    sid = resp.json()["session_id"]

    # Fetch session data
    got = await client.get(f"/session/{sid}")
    assert got.status_code == 200
    data = got.json()
    assert data["session_id"] == sid
    assert isinstance(data["messages"], list)
    assert isinstance(data["draft"], dict)
    assert isinstance(data["memory"], dict)
    # last_action can be null/None at start
    assert "last_action" in data
    assert "updated_at" in data

async def test_get_session_nonexistent(client):
    # Test getting non-existent session
    resp = await client.get("/session/nonexistent-id")
    assert resp.status_code == 404

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

async def test_update_session_name_whitespace_stripping(client, user_alice):
    # Create session
    resp = await client.post("/session/new", json={"user_id": user_alice["user_id"], "session_name": "Original"})
    sid = resp.json()["session_id"]

    # Update with whitespace - should be stripped
    ok = await client.put(f"/users/{user_alice['user_id']}/sessions/{sid}/name",
                          json={"session_name": "  Updated Name  "})
    assert ok.status_code == 200
    assert ok.json()["session_name"] == "Updated Name"  # Should be stripped

async def test_update_session_name_nonexistent_session(client, user_alice):
    # Try to update non-existent session
    resp = await client.put(f"/users/{user_alice['user_id']}/sessions/nonexistent/name",
                            json={"session_name": "New Name"})
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Session not found for this user"

async def test_list_user_sessions_pagination(client, user_alice):
    # Create 3 sessions
    ids = []
    for i in range(3):
        r = await client.post("/session/new", json={
            "user_id": user_alice["user_id"],
            "session_name": f"Session {i}"
        })
        assert r.status_code == 201
        ids.append(r.json()["session_id"])

    # page 1: limit=2, offset=0
    p1 = await client.get(f"/users/{user_alice['user_id']}/sessions", params={"limit": 2, "offset": 0})
    assert p1.status_code == 200
    d1 = p1.json()
    assert len(d1["sessions"]) == 2
    assert d1["total_sessions"] == 3
    assert d1["limit"] == 2
    assert d1["offset"] == 0
    assert d1["has_more"] is True

    # page 2: limit=2, offset=2
    p2 = await client.get(f"/users/{user_alice['user_id']}/sessions", params={"limit": 2, "offset": 2})
    assert p2.status_code == 200
    d2 = p2.json()
    assert len(d2["sessions"]) == 1
    assert d2["total_sessions"] == 3
    assert d2["limit"] == 2
    assert d2["offset"] == 2
    assert d2["has_more"] is False

async def test_session_creation_anonymous(client):
    # Test creating session without user_id (anonymous session)
    resp = await client.post("/session/new", json={})
    assert resp.status_code == 201
    data = resp.json()
    assert "session_id" in data
    UUID(data["session_id"])
    assert data["user_id"] is None
    assert data["session_name"] is None
