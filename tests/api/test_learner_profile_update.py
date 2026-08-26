"""Learner profile update — PATCH /user/update/{userId}.

Runs the full documented chain, then updates the learner's profile as the
final step and verifies it persists:

  1. POST /account/create        create learner
  1b POST /account/login         log in as that learner
  2. POST /user-tenant           enroll into SCP
  3. PATCH /user/update/{id}     enrollment-status form
  4. PATCH /user/update/{id}     full profile update  <-- under test
  5. GET  /user/read/{id}        verify

Findings that shape these tests (QA, 2026-08-26):
  * The learner's own token is sufficient (self-update) and returns HTTP 200.
  * The update MERGES custom fields: values written by registration and
    enrollment survive a later profile update that does not mention them.
"""

import pytest

from utility.api import api_config, endpoints, payloads
from utility.api.asserts import assert_success
from utility.api.client import APIClient

pytestmark = [pytest.mark.api, pytest.mark.enrollment]


def _profile_client(learner):
    """Client authenticated as the learner, with the headers the profile
    update endpoint expects (SCP tenant + academic year)."""
    c = APIClient()
    c.set_token(learner.token)
    c.session.headers["tenantid"] = api_config.SCP_TENANT_ID
    c.session.headers["academicyearid"] = api_config.ACADEMIC_YEAR_ID
    return c


def _read(api, user_id):
    import os

    admin = payloads.login_payload(
        os.getenv("API_ADMIN_USERNAME", "DhuriTekdi19"),
        os.getenv("API_ADMIN_PASSWORD", "88432"),
    )
    reader = APIClient()
    token = assert_success(api.post(endpoints.ACCOUNT_LOGIN, json=admin), 200)[
        "access_token"
    ]
    reader.set_token(token)
    reader.session.headers["tenantId"] = api_config.TENANT_ID
    path = endpoints.USER_READ.format(user_id=user_id) + "?fieldvalue=true"
    return assert_success(reader.get(path), 200)["userData"]


def _field_values(user_data, field_id):
    """Values stored for a custom field. selectedValues entries may be dicts
    ({"value": ...}) or plain strings, depending on the field type."""
    for f in user_data.get("customFields") or []:
        if f.get("fieldId") == field_id:
            return [
                (s.get("value") if isinstance(s, dict) else s)
                for s in (f.get("selectedValues") or [])
            ]
    return None


@pytest.mark.smoke
def test_learner_can_update_own_profile(api, logged_in_learner):
    """A learner updates their own profile — name plus the full SCP profile
    custom-field set — with their own token, and every field is read back.

    Mirrors the reference profile-update cURL captured from the PLP web app.
    """
    client = _profile_client(logged_in_learner)

    body = payloads.profile_update_payload(
        user_data={
            "firstName": "Mahajan",
            "lastName": "Tekdi",
            "mobile": "8888434778",
            "dob": "1991-08-14",
            "gender": "male",
        },
        custom_fields=payloads.full_profile_custom_fields(),
    )
    response = client.patch(
        endpoints.USER_UPDATE.format(user_id=logged_in_learner.user_id),
        json=body,
    )
    assert_success(response, 200)

    user_data = _read(api, logged_in_learner.user_id)
    assert user_data["firstName"] == "Mahajan", (
        f"firstName not updated: {user_data['firstName']!r}"
    )
    assert user_data["lastName"] == "Tekdi"

    # Every profile custom field sent should be stored with the value we sent.
    for label, (field_id, value) in api_config.PROFILE_FIELDS.items():
        expected = value if isinstance(value, list) else [value]
        actual = _field_values(user_data, field_id)
        assert actual == expected, (
            f"Profile field {label!r} did not persist: sent {expected}, "
            f"read back {actual}"
        )


def test_profile_update_preserves_registration_fields(api, logged_in_learner):
    """The update merges: fields set at registration (state/district/...) must
    survive a later profile update that does not mention them."""
    client = _profile_client(logged_in_learner)

    client.patch(
        endpoints.USER_UPDATE.format(user_id=logged_in_learner.user_id),
        json=payloads.profile_update_payload(user_data={"firstName": "Renamed"}),
    )

    user_data = _read(api, logged_in_learner.user_id)
    state = _field_values(user_data, api_config.CUSTOM_FIELDS["state"][0])
    assert state, (
        "State set at registration was lost after a profile update that did "
        f"not mention it. customFields now: "
        f"{[f.get('label') for f in user_data.get('customFields') or []]}"
    )


def test_profile_update_can_change_mobile(api, logged_in_learner):
    """A valid new mobile persists through the update."""
    client = _profile_client(logged_in_learner)

    client.patch(
        endpoints.USER_UPDATE.format(user_id=logged_in_learner.user_id),
        json=payloads.profile_update_payload(user_data={"mobile": "9876543210"}),
    )

    user_data = _read(api, logged_in_learner.user_id)
    assert str(user_data["mobile"]) == "9876543210", (
        f"mobile not updated: {user_data['mobile']!r}"
    )
