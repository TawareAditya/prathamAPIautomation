"""Request payload builders.

Usernames are generated per call so a run never collides with data left behind
by an earlier run.
"""

import random
import string

from utility.api import api_config


def random_token(digits=5, letters=3):
    return "".join(random.choices(string.digits, k=digits)) + "".join(
        random.choices(string.ascii_lowercase, k=letters)
    )


def unique_username():
    """e.g. autoQA48213xkq — prefixed so QA test data is easy to identify."""
    return f"{api_config.USERNAME_PREFIX}{random_token()}"


def default_custom_fields():
    return [
        {"fieldId": field_id, "value": [value]}
        for field_id, value in api_config.CUSTOM_FIELDS.values()
    ]


def registration_payload(**overrides):
    """A valid /account/create body.

    Pass overrides to build negative cases. A value of None removes the field
    entirely, which is how the "missing required field" tests are built:

        registration_payload(username=None)
        registration_payload(gender="banana")
    """
    payload = {
        "customFields": default_custom_fields(),
        "firstName": "ABhi",
        "lastName": "Kalshetti",
        "dob": "1999-08-10",
        "gender": "male",
        "mobile": "8600367304",
        "username": unique_username(),
        "password": api_config.DEFAULT_PASSWORD,
        "tenantCohortRoleMapping": [
            {"roleId": api_config.ROLE_ID, "tenantId": api_config.TENANT_ID}
        ],
    }
    for key, value in overrides.items():
        if value is None:
            payload.pop(key, None)
        else:
            payload[key] = value
    return payload


def login_payload(username, password):
    return {"username": username, "password": password}
