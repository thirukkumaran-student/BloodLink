"""Shared test fixtures (owner: D1).

By default the suite runs against a throwaway SQLite file so it exercises the real
engine, models and API stack — the same code path as development.

To run the exact same suite against PostgreSQL (recommended before a release,
see ``docs/database.md``):

    BLOODLINK_TEST_DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/bloodlink_test \
        python3 -m pytest -q

The database name must contain ``test``: the fixture drops **every table** in it
between runs, and that guard is what stops a misconfigured URL from wiping a real
database.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
for extra in ("apps/api", "apps/web", "packages/config", "packages/contracts", "packages/validation"):
    sys.path.insert(0, str(PROJECT_ROOT / extra))

TEST_DB = PROJECT_ROOT / "tests" / ".tmp" / "test_bloodlink.db"
#: Set to run against a server database (PostgreSQL) instead of the SQLite file.
EXTERNAL_TEST_URL = os.environ.get("BLOODLINK_TEST_DATABASE_URL")

if EXTERNAL_TEST_URL:
    database_name = EXTERNAL_TEST_URL.rsplit("/", 1)[-1].split("?")[0]
    if "test" not in database_name:
        raise RuntimeError(
            "BLOODLINK_TEST_DATABASE_URL must point at a database whose name contains "
            f"'test' — the suite drops every table in it (got {database_name!r})."
        )

os.environ.setdefault("BLOODLINK_ENV", "test")
os.environ["BLOODLINK_DATABASE_URL"] = EXTERNAL_TEST_URL or f"sqlite:///{TEST_DB}"
os.environ["BLOODLINK_SECRET_KEY"] = "test-secret-key-please-change-1234567890"
os.environ["BLOODLINK_SEED_ON_STARTUP"] = "false"
os.environ["BLOODLINK_PUSH_TRANSPORT"] = "log"
os.environ["BLOODLINK_RATE_LIMIT_NOTIFICATIONS_PER_HOUR"] = "500"

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from bloodlink_api.core.settings import reset_settings_cache  # noqa: E402
from bloodlink_api.db.session import reset_engine  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database() -> None:
    """Fresh schema + demo data for the whole test session."""
    reset_settings_cache()
    reset_engine()

    if EXTERNAL_TEST_URL:
        # Server database: recreate the schema instead of deleting a file.
        from bloodlink_api.db.session import create_all, drop_all

        drop_all()
        create_all()
    else:
        TEST_DB.parent.mkdir(parents=True, exist_ok=True)
        if TEST_DB.exists():
            TEST_DB.unlink()

        from bloodlink_api.db.session import create_all

        create_all()

    from bloodlink_api.seed import seed_demo_data

    assert seed_demo_data() is True
    yield
    reset_engine()
    if not EXTERNAL_TEST_URL and TEST_DB.exists():
        TEST_DB.unlink()


@pytest.fixture(scope="session")
def app(_database):
    from bloodlink_api.main import app as fastapi_app

    return fastapi_app


@pytest_asyncio.fixture
async def client(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://bloodlink.test") as async_client:
        yield async_client


DEMO_PASSWORD = "Bloodlink#2026"

DEMO_ACCOUNTS = {
    "admin": "admin@bloodlink.dev",
    "hospital": "apollo.staff@bloodlink.dev",
    "hospital_pending": "pend.staff@bloodlink.dev",
    "blood_centre": "redcross.staff@bloodlink.dev",
    "donor": "priya@bloodlink.dev",
    "donor_second": "arjun@bloodlink.dev",
    "individual": "meera@bloodlink.dev",
}


async def login(client: httpx.AsyncClient, account: str) -> dict:
    """Sign in a demo account and return ``{"headers", "user", "refreshToken"}``."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": DEMO_ACCOUNTS[account], "password": DEMO_PASSWORD},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    return {
        "headers": {"Authorization": f"Bearer {data['accessToken']}"},
        "user": data["user"],
        "refreshToken": data["refreshToken"],
        "accessToken": data["accessToken"],
    }


@pytest_asyncio.fixture
async def admin(client):
    return await login(client, "admin")


@pytest_asyncio.fixture
async def hospital(client):
    return await login(client, "hospital")


@pytest_asyncio.fixture
async def donor(client):
    return await login(client, "donor")


@pytest_asyncio.fixture
async def donor_second(client):
    """Arjun — A+, not compatible with the seeded O- request."""
    return await login(client, "donor_second")


@pytest_asyncio.fixture
async def individual(client):
    return await login(client, "individual")


@pytest_asyncio.fixture
async def blood_centre(client):
    return await login(client, "blood_centre")
