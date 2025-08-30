# tests/test_users.py
import pytest

pytestmark = pytest.mark.anyio

async def test_create_user_success(client):
    resp = await client.post("/users", json={"user_id": "bob", "password": "p@ssw0rd123"})
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

async def test_create_user_validation_errors(client):
    # Test short password (< 8 chars) - should fail with our new schema validation
    resp = await client.post("/users", json={"user_id": "test", "password": "short"})
    assert resp.status_code == 422  # Validation error
    
    # Test empty user_id - should fail
    resp = await client.post("/users", json={"user_id": "", "password": "validpass123"})
    assert resp.status_code == 422  # Validation error
    
    # Test too long user_id (> 50 chars) - should fail
    long_user_id = "a" * 51
    resp = await client.post("/users", json={"user_id": long_user_id, "password": "validpass123"})
    assert resp.status_code == 422  # Validation error

async def test_create_user_whitespace_stripping(client):
    # Test that whitespace is stripped from user_id
    resp = await client.post("/users", json={"user_id": "  testuser  ", "password": "validpass123"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == "testuser"  # Should be stripped

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
    bad2 = await client.post("/users/login", json={"user_id": "nouser", "password": "validpass123"})
    assert bad2.status_code == 401

async def test_login_whitespace_stripping(client, user_alice):
    # Test that whitespace is stripped during login
    ok = await client.post("/users/login", json={
        "user_id": "  alice  ",  # Should be stripped to "alice"
        "password": user_alice["password"]
    })
    assert ok.status_code == 200
    body = ok.json()
    assert body["user_id"] == "alice"

async def test_get_user_sessions_empty(client, user_alice):
    # Test getting sessions for user with no sessions
    resp = await client.get(f"/users/{user_alice['user_id']}/sessions")
    assert resp.status_code == 200
    data = resp.json()
    assert data["user_id"] == user_alice["user_id"]
    assert data["sessions"] == []
    assert data["total_sessions"] == 0
    assert data["limit"] == 50  # Default limit
    assert data["offset"] == 0
    assert data["has_more"] is False

async def test_get_user_sessions_nonexistent_user(client):
    # Test getting sessions for non-existent user
    resp = await client.get("/users/nonexistent/sessions")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "User not found"
