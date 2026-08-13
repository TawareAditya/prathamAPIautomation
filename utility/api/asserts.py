"""Assertion helpers for the Sunbird-style response envelope.

Every response from this API looks like:

    {
      "id": "api.user.create",
      "ver": "1.0",
      "ts": "...",
      "params": {"resmsgid": "...", "status": "successful|failed",
                 "err": null, "errmsg": null},
      "responseCode": 201,
      "result": {...}
    }

These helpers keep the failing payload in the assertion message — a bare
`assert r.status_code == 201` tells you nothing about why the server said no.
"""

import uuid

ENVELOPE_KEYS = ("id", "ver", "ts", "params", "responseCode", "result")


def _context(response):
    from utility.api.client import body_text

    return (
        f"{response.request.method} {response.request.url}\n"
        f"  status: {response.status_code}\n"
        f"  body:   {body_text(response)[:800]}"
    )


def json_body(response):
    try:
        return response.json()
    except ValueError:
        raise AssertionError(
            f"Response body is not valid JSON.\n{_context(response)}"
        ) from None


def assert_status(response, expected):
    allowed = {expected} if isinstance(expected, int) else set(expected)
    assert response.status_code in allowed, (
        f"Expected HTTP {sorted(allowed)}, got {response.status_code}.\n"
        f"{_context(response)}"
    )


def assert_envelope(response):
    """Every response must carry the standard envelope keys."""
    payload = json_body(response)
    missing = [key for key in ENVELOPE_KEYS if key not in payload]
    assert not missing, (
        f"Response envelope is missing {missing}. Present: {list(payload.keys())}\n"
        f"{_context(response)}"
    )
    assert payload["responseCode"] == response.status_code, (
        f"Envelope responseCode ({payload['responseCode']}) disagrees with the "
        f"HTTP status ({response.status_code}).\n{_context(response)}"
    )
    return payload


def assert_success(response, expected_status=201):
    """Assert a successful envelope and return `result`."""
    assert_status(response, expected_status)
    payload = assert_envelope(response)
    params = payload["params"]
    assert params.get("status") == "successful", (
        f"params.status is {params.get('status')!r}, expected 'successful'.\n"
        f"{_context(response)}"
    )
    assert not params.get("err"), (
        f"params.err should be empty on success, got {params.get('err')!r}.\n"
        f"{_context(response)}"
    )
    return payload["result"]


def assert_failure(response, expected_status):
    """Assert a failed envelope and return `params` for message checks."""
    assert_status(response, expected_status)
    payload = assert_envelope(response)
    params = payload["params"]
    assert params.get("status") == "failed", (
        f"params.status is {params.get('status')!r}, expected 'failed'.\n"
        f"{_context(response)}"
    )
    assert params.get("errmsg"), (
        f"A failed response must explain itself, but errmsg is "
        f"{params.get('errmsg')!r}.\n{_context(response)}"
    )
    assert not payload.get("result"), (
        f"result should be empty on failure, got {payload.get('result')!r}.\n"
        f"{_context(response)}"
    )
    return params


def assert_errmsg_contains(response, fragment):
    params = json_body(response).get("params", {})
    errmsg = (params.get("errmsg") or "") + " " + (params.get("err") or "")
    assert fragment.lower() in errmsg.lower(), (
        f"Expected the error to mention {fragment!r}, got {errmsg.strip()!r}.\n"
        f"{_context(response)}"
    )


def assert_is_uuid(value, label="value"):
    try:
        uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        raise AssertionError(f"{label} is not a valid UUID: {value!r}") from None


def assert_faster_than(response, seconds):
    elapsed = response.elapsed.total_seconds()
    assert elapsed < seconds, (
        f"Request took {elapsed:.2f}s, budget is {seconds}s.\n{_context(response)}"
    )


def assert_no_secret_leak(response, password=None):
    """The API must never echo a password back, hashed or otherwise."""
    body = response.text
    for marker in ("access_token", "refresh_token"):
        assert marker not in body.lower(), (
            f"Response leaks {marker!r} where none should exist.\n"
            f"{_context(response)}"
        )
    if password:
        assert password not in body, (
            f"Response echoes the submitted password back to the caller.\n"
            f"{_context(response)}"
        )
