"""Configuration for the API suite.

Everything can be overridden with an environment variable, so the same tests
can be pointed at dev/QA/staging without editing code:

    set API_BASE_URL=https://dev-interface.prathamdigital.org/interface/v1

The account-creation endpoint is public (no Authorization header), so there
are no secrets in this file.
"""

import os

BASE_URL = os.getenv(
    "API_BASE_URL", "https://qa-interface.prathamdigital.org/interface/v1"
).rstrip("/")

ORIGIN = os.getenv("API_ORIGIN", "https://dev-plp.prathamdigital.org").rstrip("/")

REQUEST_TIMEOUT = int(os.getenv("API_TIMEOUT", "30"))

# Budget for a single call, in seconds. Generous on purpose — this catches a
# hung endpoint, not a slow one.
RESPONSE_TIME_BUDGET = float(os.getenv("API_RESPONSE_BUDGET", "10"))

TENANT_ID = os.getenv("API_TENANT_ID", "e39447df-069d-4ccf-b92c-576f70b350f3")
ROLE_ID = os.getenv("API_ROLE_ID", "eea7ddab-bdf9-4db1-a1bb-43ef503d65ef")

# --- SCP (Second Chance Program) enrollment flow ---
# The child tenants of Pratham ARE the programs. Enrolling a learner into a
# program means creating a user-tenant mapping to that child tenant.
# Confirmed from GET /tenant/search on QA, 2026-08-26.
SCP_TENANT_ID = os.getenv("API_SCP_TENANT_ID", "ef99949b-7f3a-4a5f-806a-e67e683e38f3")

# Custom field the enrollment form writes. Server label: INTERESTED_TO_JOIN.
ENROLLMENT_FIELD_ID = os.getenv(
    "API_ENROLLMENT_FIELD_ID", "f8dc1d5f-9b2b-412e-a22a-351bd8f14963"
)
ENROLLMENT_STATUS = os.getenv("API_ENROLLMENT_STATUS", "pending")

# Profile custom fields sent at registration. IDs and values mirror the
# reference request captured from the PLP web app.
#
# Names below were confirmed on 2026-08-20 by reading a created account back
# via GET /user/read/{userId}?fieldvalue=true, which returns the server's own
# labels. The resolved values are shown for reference.
CUSTOM_FIELDS = {
    # label                            fieldId                                 value    resolves to
    "state": ("6469c3ac-8c46-49d7-852a-00f9589737c5", "35"),        # Andaman And Nicobar Islands
    "district": ("b61edfc6-3787-4079-86d3-37262bf23a9e", "638"),    # Nicobars
    "block": ("4aab68ae-8382-43aa-a45a-e9b239319857", "1427"),      # Campbell Bay
    "village": ("8e9bb321-ff99-4e2e-9269-61e863dd0c54", "639471"),  # Afra Bay
    # Server label is WHAT_IS_YOUR_PREFERRED_LANGUAGE. Previously mislabelled
    # here as "medium", which is a different concept in the Pratham domain.
    "preferred_language": ("7735e603-ce0e-4b1d-95f4-7d4b67267777", "english"),
}

# Prefix for every generated account, so test data is identifiable and
# cleanable in the QA database.
USERNAME_PREFIX = os.getenv("API_USERNAME_PREFIX", "autoQA")
DEFAULT_PASSWORD = os.getenv("API_NEW_USER_PASSWORD", "Test@1234")
