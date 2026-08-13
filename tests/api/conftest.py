"""Fixtures for the API suite.

Scoped to tests/api/ only — the browser `page` fixture in the parent conftest
is untouched, so UI tests keep working exactly as before.
"""

import logging

import pytest

from utility.api import api_config, endpoints, payloads
from utility.api.asserts import assert_success
from utility.api.client import APIClient

logger = logging.getLogger("api")


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
