"""Fixtures for the API suite.

Scoped to tests/api/ only — the browser `page` fixture in the parent conftest
is untouched, so UI tests keep working exactly as before.
"""

import logging
import os
from pathlib import Path

import pytest

from utility.api import api_config, endpoints, payloads
from utility.api.asserts import assert_success
from utility.api.client import APIClient

logger = logging.getLogger("api")


def _load_dotenv():
    """Load a local .env (repo root) into the environment for local runs.

    Deliberately dependency-free and non-overriding: real environment
    variables (e.g. CI secrets) always win over the file. Used so a developer
    can `pytest tests/api` locally and pick up the DB config without exporting
    variables each time. The file is gitignored.
    """
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv()


@pytest.fixture(scope="session")
def api():
    """Shared client. The registration endpoint is public, so no auth here."""
    return APIClient()


@pytest.fixture
def fresh_api():
    """Function-scoped client for tests that need to change headers."""
    return APIClient()


@pytest.fixture(scope="session")
def registered_user(api):
    """One successfully registered account, reused across the session.

    Returned as (payload, result) so tests can log in as this user or try to
    re-register them without each paying for another account.
    """
    payload = payloads.registration_payload()
    response = api.post(endpoints.ACCOUNT_CREATE, json=payload)
    result = assert_success(response, 201)
    logger.info("Session user registered: %s", payload["username"])
    return payload, result


@pytest.fixture(scope="session", autouse=True)
def announce_target():
    logger.info("API under test: %s", api_config.BASE_URL)
    yield


@pytest.fixture
def logged_in_learner(api):
    """A freshly registered learner, already logged in, not yet enrolled.

    Function-scoped: enrollment tests mutate tenant state, so each needs a
    clean learner of its own.
    """
    from utility.api.learners import new_logged_in_learner

    return new_logged_in_learner(api)


@pytest.fixture(scope="session")
def db_conn():
    """Read-only connection to the QA pratham DB.

    Skips the whole test if the DB is not configured or unreachable, so the
    suite stays green in environments without DB access (e.g. plain CI).
    """
    from utility.api import db as dbmod

    if not dbmod.is_configured():
        pytest.skip(dbmod.missing_reason())
    # Fast, cached TCP check first — an unreachable DB (e.g. a CI runner the
    # firewall blocks) skips in ~3s once, not a 10s connect timeout per test.
    if not dbmod.reachable():
        pytest.skip(
            f"DB not reachable at {os.getenv('POSTGRES_HOST')}:"
            f"{os.getenv('POSTGRES_PORT', '5432')} (firewall / not on network)"
        )
    try:
        with dbmod.connection() as conn:
            yield conn
    except Exception as exc:  # auth failure or dropped connection
        pytest.skip(f"DB connection failed: {type(exc).__name__}: {exc}")
