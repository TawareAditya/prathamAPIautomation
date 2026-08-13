"""Known defects in POST /account/create.

Each test asserts the behaviour we believe is CORRECT and is marked
`xfail(strict=True)`. That means:

  * while the bug exists  -> reported as xfail, the run stays green
  * the moment it is fixed -> reported as XPASS and the run FAILS

So a fix can't land silently. When one of these starts failing the build,
delete the xfail marker and move the test into test_account_create.py.

Run just these:  pytest tests/api -m known_issue -v
"""

import pytest

from utility.api import endpoints, payloads
from utility.api.asserts import assert_failure, assert_success

pytestmark = [pytest.mark.api, pytest.mark.known_issue]


@pytest.mark.xfail(
    strict=True,
    reason="BUG: customFields is optional — a user can register with no "
    "state/district/block/village/medium at all, leaving an incomplete profile.",
)
def test_missing_custom_fields_should_be_rejected(api):
    payload = payloads.registration_payload(customFields=None)

    response = api.post(endpoints.ACCOUNT_CREATE, json=payload)

    assert_failure(response, 400)


@pytest.mark.xfail(
    strict=True,
    reason="BUG: an empty customFields array is accepted, same gap as above.",
)
def test_empty_custom_fields_should_be_rejected(api):
    payload = payloads.registration_payload(customFields=[])

    response = api.post(endpoints.ACCOUNT_CREATE, json=payload)

    assert_failure(response, 400)


@pytest.mark.xfail(
    strict=True,
    reason="BUG: a username clash returns errmsg 'Email already exists' even "
    "when no email was submitted. The message should name the username.",
)
def test_duplicate_username_error_should_mention_username(api, registered_user):
    payload, _ = registered_user
    duplicate = payloads.registration_payload(username=payload["username"])

    response = api.post(endpoints.ACCOUNT_CREATE, json=duplicate)

    params = assert_failure(response, 409)
    assert "username" in params["errmsg"].lower(), (
        f"Duplicate-username error says {params['errmsg']!r}, "
        f"which points the caller at the wrong field."
    )


@pytest.mark.xfail(
    strict=True,
    reason="BUG: the gender validation error ends with an empty list — "
    "'gender must be one of the following values: ' — so callers can't tell "
    "what is actually allowed.",
)
def test_gender_error_should_list_allowed_values(api):
    payload = payloads.registration_payload(gender="banana")

    response = api.post(endpoints.ACCOUNT_CREATE, json=payload)

    params = assert_failure(response, 400)
    errmsg = params["errmsg"]
    marker = "following values:"
    assert marker in errmsg, f"Unexpected gender error format: {errmsg!r}"
    listed = errmsg.split(marker, 1)[1].strip()
    assert listed, f"No allowed values listed after {marker!r}: {errmsg!r}"


@pytest.mark.xfail(
    strict=True,
    reason="SECURITY: no password policy on a public unauthenticated endpoint "
    "— '1234' is accepted, so accounts can be created with trivial passwords.",
)
@pytest.mark.parametrize("weak_password", ["1234", "a", "password"])
def test_weak_passwords_should_be_rejected(api, weak_password):
    payload = payloads.registration_payload(password=weak_password)

    response = api.post(endpoints.ACCOUNT_CREATE, json=payload)

    assert_failure(response, 400)


@pytest.mark.xfail(
    strict=True,
    reason="BUG: a non-numeric mobile is silently discarded rather than "
    "rejected — the account is created 201 with mobile: null, so the caller "
    "believes a phone number was saved when none was.",
)
def test_non_numeric_mobile_should_be_rejected_not_dropped(api):
    payload = payloads.registration_payload(mobile="abcdefghij")

    response = api.post(endpoints.ACCOUNT_CREATE, json=payload)

    assert_failure(response, 400)


@pytest.mark.xfail(
    strict=True,
    reason="BUG: mobile is submitted as a string but returned as a number, so "
    "any number with a leading zero would be corrupted on round-trip.",
)
def test_mobile_should_round_trip_as_a_string(api):
    payload = payloads.registration_payload()

    response = api.post(endpoints.ACCOUNT_CREATE, json=payload)

    user_data = assert_success(response, 201)["userData"]
    assert isinstance(user_data["mobile"], str), (
        f"mobile came back as {type(user_data['mobile']).__name__} "
        f"({user_data['mobile']!r}), not a string"
    )
