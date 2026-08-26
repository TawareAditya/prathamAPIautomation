"""Learner registration -> SCP program enrollment flow.

Implements the sequence documented in
docs/Learner_Registration_SCP_Enrollment_API_Flow:

  1. POST /account/create            create the learner
  1b POST /account/login             log in AS that learner
  2. POST /user-tenant               enrol into Second Chance Program (pending)
  3. PATCH /user/update/{userId}     set the enrollment-status field
  4. GET  /user/read/{userId}        verify it persisted

Findings confirmed on QA, 2026-08-26, that shape these tests:
  * The learner's OWN token is sufficient for steps 2 and 3 — no admin needed.
  * academicyearid is NOT required.
  * Steps 2 and 3 return HTTP 200 (not 201).
  * Enrolling replaces the parent (Pratham) mapping with the child (SCP)
    mapping — the learner ends with one mapping, to SCP. Asserted as observed;
    see test_enrollment_leaves_a_single_scp_mapping for the caveat.
"""

import pytest

from utility.api import api_config, endpoints, payloads
from utility.api.asserts import (
    assert_errmsg_contains,
    assert_failure,
    assert_status,
    assert_success,
)

pytestmark = [pytest.mark.api, pytest.mark.enrollment]


def _read(api, user_id):
    """Read a user back via an admin client (reads need auth + tenant header)."""
    import os

    admin = payloads.login_payload(
        os.getenv("API_ADMIN_USERNAME", "DhuriTekdi19"),
        os.getenv("API_ADMIN_PASSWORD", "88432"),
    )
    from utility.api.client import APIClient

    reader = APIClient()
    token = assert_success(api.post(endpoints.ACCOUNT_LOGIN, json=admin), 200)[
        "access_token"
    ]
    reader.set_token(token)
    reader.session.headers["tenantId"] = api_config.TENANT_ID
    path = endpoints.USER_READ.format(user_id=user_id) + "?fieldvalue=true"
    return assert_success(reader.get(path), 200)["userData"]


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------


@pytest.mark.smoke
def test_learner_can_enroll_themselves_into_scp(logged_in_learner):
    """Step 2: a learner enrols into SCP with their own token."""
    client = logged_in_learner.client()

    response = client.post(
        endpoints.USER_TENANT,
        json=payloads.user_tenant_payload(logged_in_learner.user_id),
    )

    # Enrollment is a 200, not a 201 — it maps an existing user to a tenant.
    assert_success(response, 200)


def test_enrollment_form_sets_status(logged_in_learner):
    """Step 3: the enrollment-status field is written on the learner record."""
    client = logged_in_learner.client()
    client.post(
        endpoints.USER_TENANT,
        json=payloads.user_tenant_payload(logged_in_learner.user_id),
    )

    response = client.patch(
        endpoints.USER_UPDATE.format(user_id=logged_in_learner.user_id),
        json=payloads.enrollment_form_payload(),
    )

    assert_success(response, 200)


def test_full_flow_persists_enrollment(api, logged_in_learner):
    """Steps 2-4: enrol, set status, then read back and confirm both stuck."""
    client = logged_in_learner.client()
    client.post(
        endpoints.USER_TENANT,
        json=payloads.user_tenant_payload(logged_in_learner.user_id),
    )
    client.patch(
        endpoints.USER_UPDATE.format(user_id=logged_in_learner.user_id),
        json=payloads.enrollment_form_payload(),
    )

    user_data = _read(api, logged_in_learner.user_id)

    tenants = {t["tenantId"]: t for t in user_data.get("tenantData", [])}
    assert api_config.SCP_TENANT_ID in tenants, (
        f"Learner is not mapped to SCP after enrollment. "
        f"Mappings: {[t.get('tenantName') for t in user_data.get('tenantData', [])]}"
    )
    assert tenants[api_config.SCP_TENANT_ID]["tenantStatus"] == "pending"

    fields = {f["fieldId"]: f for f in (user_data.get("customFields") or [])}
    assert api_config.ENROLLMENT_FIELD_ID in fields, (
        "Enrollment status field was not persisted on the learner record"
    )
    selected = fields[api_config.ENROLLMENT_FIELD_ID].get("selectedValues") or []
    values = [s.get("value") for s in selected]
    assert api_config.ENROLLMENT_STATUS in values, (
        f"Enrollment field present but value is {values}, "
        f"expected {api_config.ENROLLMENT_STATUS!r}"
    )


def test_enrollment_leaves_a_single_scp_mapping(api, logged_in_learner):
    """Documents observed behaviour: after enrollment the learner has exactly
    one tenant mapping, to SCP — the parent Pratham mapping is replaced, not
    added to.

    If product decides the parent mapping SHOULD persist, this test encodes the
    wrong expectation and should be updated alongside the fix.
    """
    client = logged_in_learner.client()
    client.post(
        endpoints.USER_TENANT,
        json=payloads.user_tenant_payload(logged_in_learner.user_id),
    )

    user_data = _read(api, logged_in_learner.user_id)
    tenant_ids = [t["tenantId"] for t in user_data.get("tenantData", [])]

    assert tenant_ids == [api_config.SCP_TENANT_ID], (
        f"Expected a single SCP mapping, got "
        f"{[t.get('tenantName') for t in user_data.get('tenantData', [])]}"
    )


# --------------------------------------------------------------------------
# Negative / validation
# --------------------------------------------------------------------------


@pytest.mark.negative
def test_duplicate_enrollment_is_rejected(logged_in_learner):
    client = logged_in_learner.client()
    payload = payloads.user_tenant_payload(logged_in_learner.user_id)
    assert_success(client.post(endpoints.USER_TENANT, json=payload), 200)

    response = client.post(endpoints.USER_TENANT, json=payload)

    assert_failure(response, 400)
    assert_errmsg_contains(response, "already has role")


@pytest.mark.negative
def test_enrollment_requires_authentication(fresh_api, logged_in_learner):
    fresh_api.session.headers["tenantid"] = api_config.SCP_TENANT_ID

    response = fresh_api.post(
        endpoints.USER_TENANT,
        json=payloads.user_tenant_payload(logged_in_learner.user_id),
    )

    assert_status(response, 401)


@pytest.mark.negative
def test_enrollment_into_nonexistent_tenant_is_rejected(logged_in_learner):
    client = logged_in_learner.client()

    response = client.post(
        endpoints.USER_TENANT,
        json=payloads.user_tenant_payload(
            logged_in_learner.user_id,
            tenant_id="00000000-0000-0000-0000-000000000000",
        ),
    )

    assert_failure(response, 400)
    assert_errmsg_contains(response, "does not exist")
