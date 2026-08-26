"""Helpers for building learner accounts and enrolling them.

Keeps the register -> login -> enrol chain in one place so tests read as
intent rather than plumbing.
"""

from dataclasses import dataclass

from utility.api import api_config, endpoints, payloads
from utility.api.asserts import assert_success
from utility.api.client import APIClient


@dataclass
class Learner:
    user_id: str
    username: str
    password: str
    token: str

    def client(self):
        """A client authenticated as this learner, with the SCP tenant header
        the enrollment endpoints expect."""
        c = APIClient()
        c.set_token(self.token)
        c.session.headers["tenantid"] = api_config.SCP_TENANT_ID
        return c


def register_learner(api):
    """Create a learner and return (payload, result)."""
    payload = payloads.registration_payload()
    response = api.post(endpoints.ACCOUNT_CREATE, json=payload)
    result = assert_success(response, 201)
    return payload, result


def login_learner(api, username, password):
    response = api.post(endpoints.ACCOUNT_LOGIN, json=payloads.login_payload(username, password))
    result = assert_success(response, 200)
    return result["access_token"]


def new_logged_in_learner(api):
    """Register a learner, log in as them, and return a Learner with a token."""
    payload, result = register_learner(api)
    token = login_learner(api, payload["username"], payload["password"])
    return Learner(
        user_id=result["userData"]["userId"],
        username=payload["username"],
        password=payload["password"],
        token=token,
    )
