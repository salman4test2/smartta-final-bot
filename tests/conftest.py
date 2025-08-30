# tests/conftest.py
import os
import importlib
import pathlib
import pytest
from httpx import AsyncClient, ASGITransport

@pytest.fixture(scope="session")
def test_db_url(tmp_path_factory):
    db_dir = tmp_path_factory.mktemp("db")
    db_path = db_dir / "test.db"
    return f"sqlite+aiosqlite:///{db_path.as_posix()}"

@pytest.fixture(scope="session", autouse=True)
def setup_test_env(test_db_url):
    """
    Set up test environment variables before importing the app.
    """
    os.environ["ENVIRONMENT"] = "test"
    os.environ["DATABASE_URL"] = test_db_url
    # Optional: point to a minimal config if you want
    # os.environ["CONFIG_PATH"] = "tests/fixtures/whatsapp.yaml"

@pytest.fixture(scope="session")
def app_module(setup_test_env):
    """
    Import the FastAPI app AFTER wiring test env vars.
    Set APP_IMPORT=my_pkg.main if your package path differs.
    """
    module_path = os.getenv("APP_IMPORT", "app.main")
    mod = importlib.import_module(module_path)
    return mod

@pytest.fixture(scope="session")
def app(app_module):
    # The FastAPI app object must be named "app" in your module
    return app_module.app

@pytest.fixture(autouse=True)
async def _reset_db(app_module):
    """
    Hard reset DB before each test.
    """
    # Expect engine & Base at app package: app.db.engine, app.db.Base
    db_mod = importlib.import_module(app_module.__package__ + ".db")
    engine = db_mod.engine
    Base = db_mod.Base

    async with engine.begin() as conn:
        # Drop all tables and indexes to avoid conflicts
        await conn.run_sync(Base.metadata.drop_all)
        # Recreate everything fresh
        await conn.run_sync(Base.metadata.create_all)
    yield

@pytest.fixture
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

# Helpers
async def _create_user(client, user_id="alice", password="secret123"):
    resp = await client.post("/users", json={"user_id": user_id, "password": password})
    return resp

@pytest.fixture
async def user_alice(client):
    resp = await _create_user(client, "alice", "secret123")
    assert resp.status_code == 200, resp.text
    return {"user_id": "alice", "password": "secret123"}
