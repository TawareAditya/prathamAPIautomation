"""Known defects in the SCP enrollment flow.

Same convention as test_account_create_known_issues: each test asserts the
CORRECT behaviour and is marked xfail(strict=True). While the bug exists the
test xfails and the build stays green; once fixed it XPASSes and the build
fails, prompting promotion.
"""

import pytest

from utility.api import api_config, endpoints, payloads
from utility.api.asserts import assert_status
from utility.api.learners import new_logged_in_learner
from utility.api.client import APIClient

pytestmark = [pytest.mark.api, pytest.mark.enrollment, pytest.mark.known_issue]


@pytest.mark.xfail(
    strict=True,
    reason="SECURITY (IDOR): POST /user-tenant does not verify that the userId "
    "in the body belongs to the caller's token. Learner A can enrol Learner B "
    "into a program using A's own token — a broken-access-control flaw. "
    "Confirmed on QA 2026-08-26.",
)
def test_learner_cannot_enroll_another_learner(api):
    """A learner using their own token must not be able to modify a DIFFERENT
    learner's tenant mappings."""
    attacker = new_logged_in_learner(api)
    victim = new_logged_in_learner(api)

    client = attacker.client()
    response = client.post(
        endpoints.USER_TENANT,
        json=payloads.user_tenant_payload(victim.user_id),
    )

    # Correct behaviour: the server rejects an attempt to act on someone else's
    # account. 403 Forbidden is the expected response.
    assert_status(response, 403)


@pytest.mark.xfail(
    strict=True,
    reason="SECURITY (IDOR): PATCH /user/update/{userId} does not verify that "
    "the target userId belongs to the caller's token. Learner A can overwrite "
    "Learner B's profile fields using A's own token. Confirmed on QA "
    "2026-08-26 (firstName overwritten to a foreign value). See ATM-94.",
)
def test_learner_cannot_edit_another_learners_profile(api):
    """A learner using their own token must not be able to modify a DIFFERENT
    learner's profile via the update endpoint."""
    attacker = new_logged_in_learner(api)
    victim = new_logged_in_learner(api)

    client = APIClient()
    client.set_token(attacker.token)
    client.session.headers["tenantid"] = api_config.TENANT_ID

    response = client.patch(
        endpoints.USER_UPDATE.format(user_id=victim.user_id),
        json={"userData": {"firstName": "NotYours"}, "customFields": []},
    )

    # Correct behaviour: the server rejects editing someone else's account.
    assert_status(response, 403)
