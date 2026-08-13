"""POST /account/create — public self-registration.

Covers the behaviour the API gets right. Cases where the API looks wrong are
in test_account_create_known_issues.py so they stay visible rather than being
quietly encoded as "expected" here.
"""

import re

import pytest

from utility.api import api_config, endpoints, payloads
from utility.api.asserts import (
    assert_content_type,
    assert_envelope,
    assert_errmsg_contains,
    assert_failure,
    assert_faster_than,
    assert_is_uuid,
    assert_iso_timestamp,
    assert_no_secret_leak,
    assert_status,
    assert_success,
)

pytestmark = pytest.mark.api


# --------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------


@pytest.mark.smoke
def test_register_user_returns_201_with_user_id(api):
    payload = payloads.registration_payload()

    response = api.post(endpoints.ACCOUNT_CREATE, json=payload)

    result = assert_success(response, 201)
    user_data = result["userData"]
    assert_is_uuid(user_data["userId"], "userId")
    assert user_data["username"] == payload["username"]
    assert user_data["status"] == "active"
    assert user_data["createFailures"] == [], (
        f"Account created with partial failures: {user_data['createFailures']}"
    )


def test_registration_echoes_submitted_profile_fields(api):
    payload = payloads.registration_payload()

    response = api.post(endpoints.ACCOUNT_CREATE, json=payload)

    user_data = assert_success(response, 201)["userData"]
    assert user_data["firstName"] == payload["firstName"]
    assert user_data["lastName"] == payload["lastName"]
    assert user_data["gender"] == payload["gender"]
    # dob comes back as a full ISO timestamp, so compare the date part only.
    assert user_data["dob"].startswith(payload["dob"]), (
        f"dob round-tripped as {user_data['dob']!r}, expected it to start "
        f"with {payload['dob']!r}"
    )


@pytest.mark.smoke
def test_registered_user_can_log_in(api, registered_user):
    """Registration is only real if the credentials actually work."""
    payload, _ = registered_user

    response = api.post(
        endpoints.ACCOUNT_LOGIN,
        json=payloads.login_payload(payload["username"], payload["password"]),
    )

    result = assert_success(response, 200)
    token = result.get("access_token")
    assert token, f"No access_token returned for a freshly registered user: {result}"
    assert token.count(".") == 2, f"Expected a JWT, got: {token[:40]}..."


def test_new_account_is_flagged_as_temporary_password(api, registered_user):
    """The UI relies on this flag to force a password change on first login."""
    _, result = registered_user

    assert result["userData"]["temporaryPassword"] is True


def test_registration_completes_within_budget(api):
    payload = payloads.registration_payload()

    response = api.post(endpoints.ACCOUNT_CREATE, json=payload)

    assert_status(response, 201)
    assert_faster_than(response, api_config.RESPONSE_TIME_BUDGET)


# --------------------------------------------------------------------------
# Response envelope contract
#
# Ported from the Postman collection's post-response tests, so both suites
# hold the API to the same contract.
# --------------------------------------------------------------------------


def test_success_envelope_metadata(api):
    """id / ver / ts / resmsgid / successmessage on a successful create."""
    response = api.post(
        endpoints.ACCOUNT_CREATE, json=payloads.registration_payload()
    )

    assert_status(response, 201)
    assert_content_type(response)
    body = assert_envelope(response)

    assert body["id"] == "api.user.create"
    assert body["ver"] == "1.0"
    assert_iso_timestamp(body["ts"], "envelope ts")

    params = body["params"]
    assert params["successmessage"] == "User created successfully"
    assert_is_uuid(params["resmsgid"], "params.resmsgid")
    assert params["err"] is None, f"params.err should be null, got {params['err']!r}"
    assert params["errmsg"] is None, (
        f"params.errmsg should be null, got {params['errmsg']!r}"
    )


def test_user_data_timestamps(api):
    """createdAt/updatedAt are ISO timestamps and identical at creation."""
    response = api.post(
        endpoints.ACCOUNT_CREATE, json=payloads.registration_payload()
    )

    user_data = assert_success(response, 201)["userData"]
    assert_iso_timestamp(user_data["createdAt"], "createdAt")
    assert_iso_timestamp(user_data["updatedAt"], "updatedAt")
    assert user_data["createdAt"] == user_data["updatedAt"], (
        f"A freshly created user should not already be modified: "
        f"createdAt={user_data['createdAt']} updatedAt={user_data['updatedAt']}"
    )
    assert_iso_timestamp(user_data["dob"], "dob")


def test_unsupplied_optional_fields_are_present_and_null(api):
    """The response shape must be stable — absent values come back as explicit
    nulls, not missing keys, so consumers can rely on the field existing."""
    payload = payloads.registration_payload()
    assert "middleName" not in payload and "email" not in payload

    response = api.post(endpoints.ACCOUNT_CREATE, json=payload)

    user_data = assert_success(response, 201)["userData"]
    for field in [
        "middleName",
        "email",
        "name",
        "address",
        "pincode",
        "deviceId",
        "createdBy",
        "updatedBy",
        "reason",
        "lastLogin",
    ]:
        assert field in user_data, f"Response is missing the {field!r} key entirely"
        assert user_data[field] is None, (
            f"{field} was not submitted, so it should be null, "
            f"got {user_data[field]!r}"
        )


def test_mobile_is_ten_digits(api):
    payload = payloads.registration_payload()

    response = api.post(endpoints.ACCOUNT_CREATE, json=payload)

    user_data = assert_success(response, 201)["userData"]
    assert re.fullmatch(r"\d{10}", str(user_data["mobile"])), (
        f"mobile should round-trip as 10 digits, got {user_data['mobile']!r}"
    )


def test_gender_is_a_known_value(api, registered_user):
    _, result = registered_user

    assert result["userData"]["gender"] in ("male", "female", "other")


# --------------------------------------------------------------------------
# Duplicate handling
# --------------------------------------------------------------------------


@pytest.mark.negative
def test_duplicate_username_is_rejected(api, registered_user):
    payload, _ = registered_user
    duplicate = payloads.registration_payload(username=payload["username"])

    response = api.post(endpoints.ACCOUNT_CREATE, json=duplicate)

    assert_failure(response, 409)


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


@pytest.mark.negative
@pytest.mark.parametrize(
    "field", ["username", "password", "firstName", "lastName", "gender"]
)
def test_missing_required_field_is_rejected(api, field):
    payload = payloads.registration_payload(**{field: None})

    response = api.post(endpoints.ACCOUNT_CREATE, json=payload)

    assert_failure(response, 400)
    assert_errmsg_contains(response, field)


@pytest.mark.negative
@pytest.mark.parametrize("field", ["username", "password", "firstName", "lastName"])
def test_empty_string_in_required_field_is_rejected(api, field):
    payload = payloads.registration_payload(**{field: ""})

    response = api.post(endpoints.ACCOUNT_CREATE, json=payload)

    assert_failure(response, 400)


@pytest.mark.negative
def test_empty_body_is_rejected(api):
    response = api.post(endpoints.ACCOUNT_CREATE, json={})

    params = assert_failure(response, 400)
    assert params["err"] == "BadRequestException"


@pytest.mark.negative
@pytest.mark.parametrize("gender", ["banana", "MALE", "123", ""])
def test_invalid_gender_is_rejected(api, gender):
    payload = payloads.registration_payload(gender=gender)

    response = api.post(endpoints.ACCOUNT_CREATE, json=payload)

    assert_failure(response, 400)
    assert_errmsg_contains(response, "gender")


@pytest.mark.negative
@pytest.mark.parametrize("mobile", ["123", "86003673040000"])
def test_invalid_mobile_is_rejected(api, mobile):
    payload = payloads.registration_payload(mobile=mobile)

    response = api.post(endpoints.ACCOUNT_CREATE, json=payload)

    assert_failure(response, 400)


@pytest.mark.negative
def test_unknown_custom_field_id_is_rejected(api):
    payload = payloads.registration_payload(
        customFields=[
            {"fieldId": "00000000-0000-0000-0000-000000000000", "value": ["x"]}
        ]
    )

    response = api.post(endpoints.ACCOUNT_CREATE, json=payload)

    assert_failure(response, 400)
    assert_errmsg_contains(response, "Field not found")


@pytest.mark.negative
def test_malformed_json_is_rejected(api):
    response = api.post(endpoints.ACCOUNT_CREATE, data="{not valid json")

    assert_status(response, [400, 415])


# --------------------------------------------------------------------------
# Contract / security
# --------------------------------------------------------------------------


def test_error_responses_keep_the_standard_envelope(api):
    """A failure must still be machine-readable, not a raw stack trace."""
    response = api.post(endpoints.ACCOUNT_CREATE, json={})

    payload = assert_envelope(response)
    assert payload["id"] == "api.user.create"
    assert payload["params"]["resmsgid"], "Missing resmsgid — errors are untraceable"


def test_password_is_never_echoed_back(api):
    payload = payloads.registration_payload()

    response = api.post(endpoints.ACCOUNT_CREATE, json=payload)

    assert_status(response, 201)
    assert_no_secret_leak(response, password=payload["password"])
