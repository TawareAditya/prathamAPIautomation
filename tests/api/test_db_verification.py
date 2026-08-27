"""Database-level verification of the API flows.

These tests do NOT trust the API response. For a learner driven through the
real flow, they read the QA `pratham` database directly and assert the stored
rows match what was sent. This is the layer that catches "API said 200 but
stored nothing" bugs (see ATM-91).

Requires the POSTGRES_* environment variables (see utility/api/db.py); the
whole module skips cleanly when they are absent, so CI without DB access still
passes.
"""

import pytest

from utility.api import api_config, db, endpoints, payloads
from utility.api.asserts import assert_success
from utility.api.client import APIClient

pytestmark = [pytest.mark.api, pytest.mark.db]


def _value_contains(stored, expected):
    """FieldValues stores the raw code, sometimes wrapped (e.g. "['35']").
    Assert the expected code appears in the stored representation."""
    return expected in str(stored)


def test_registered_user_exists_in_db(api, db_conn):
    """A registered learner has a real Users row with matching identity."""
    payload = payloads.registration_payload()
    result = assert_success(api.post(endpoints.ACCOUNT_CREATE, json=payload), 201)
    user_id = result["userData"]["userId"]

    user = db.get_user(db_conn, user_id)

    assert user is not None, f"No Users row for {user_id} the API said it created"
    assert user["username"] == payload["username"]
    assert user["firstName"] == payload["firstName"]
    assert user["lastName"] == payload["lastName"]


def test_registration_custom_fields_persisted_in_db(api, db_conn):
    """The location/language codes sent at registration are stored verbatim in
    FieldValues — the check the API cannot be trusted to report (ATM-90/91)."""
    payload = payloads.registration_payload()
    result = assert_success(api.post(endpoints.ACCOUNT_CREATE, json=payload), 201)
    user_id = result["userData"]["userId"]

    stored = db.get_field_values(db_conn, user_id)

    for label, (field_id, sent_value) in api_config.CUSTOM_FIELDS.items():
        assert field_id in stored, (
            f"{label} ({field_id}) sent at registration but no FieldValues row"
        )
        assert _value_contains(stored[field_id]["value"], sent_value), (
            f"{label}: sent {sent_value!r}, DB stored {stored[field_id]['value']!r}"
        )


def test_enrollment_mapping_persisted_in_db(db_conn, logged_in_learner):
    """After enrolling into SCP, UserTenantMapping has the SCP row."""
    client = APIClient()
    client.set_token(logged_in_learner.token)
    client.session.headers["tenantid"] = api_config.SCP_TENANT_ID
    client.post(
        endpoints.USER_TENANT,
        json=payloads.user_tenant_payload(logged_in_learner.user_id),
    )

    mappings = db.get_tenant_mappings(db_conn, logged_in_learner.user_id)
    names = [m["tenantName"] for m in mappings]

    assert any("Second Chance" in (n or "") for n in names), (
        f"SCP enrollment not found in UserTenantMapping. Rows: {mappings}"
    )


def test_profile_update_persisted_in_db(db_conn, logged_in_learner):
    """A profile update's field values land in the database."""
    client = APIClient()
    client.set_token(logged_in_learner.token)
    client.session.headers["tenantid"] = api_config.SCP_TENANT_ID
    client.session.headers["academicyearid"] = api_config.ACADEMIC_YEAR_ID
    client.patch(
        endpoints.USER_UPDATE.format(user_id=logged_in_learner.user_id),
        json=payloads.profile_update_payload(
            custom_fields=payloads.full_profile_custom_fields()
        ),
    )

    stored = db.get_field_values(db_conn, logged_in_learner.user_id)

    field_id, value = api_config.PROFILE_FIELDS["mode_of_learning"]
    assert field_id in stored, "mode_of_learning not stored in FieldValues"
    assert _value_contains(stored[field_id]["value"], value), (
        f"mode_of_learning: sent {value!r}, DB stored {stored[field_id]['value']!r}"
    )
