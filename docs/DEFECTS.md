# Defect Report — `POST /account/create`

**Service:** Pratham interface API
**Endpoint:** `POST https://qa-interface.prathamdigital.org/interface/v1/account/create`
**Environment:** QA
**Date verified:** 2026-08-19
**Reported by:** QA automation (`prathamAPIautomation`, pytest suite)
**Authorisation:** Testing performed on the team's own QA environment.

Every defect below was reproduced live on the date above. Each has an
automated test in
[`tests/api/test_account_create_known_issues.py`](../tests/api/test_account_create_known_issues.py)
marked `xfail(strict=True)` — the test asserts the *correct* behaviour, so the
day a fix ships the test turns green and the build fails, prompting us to
promote it. Nothing here needs manual re-verification.

## Summary

| ID | Severity | Defect |
|---|---|---|
| [D1](#d1) | ~~High~~ | ~~No password policy~~ — **closed 2026-08-20, intentional** |
| [D2](#d2) | **Medium** | `customFields` is optional — accounts created with no location/medium data |
| [D3](#d3) | **Medium** | Non-numeric `mobile` silently discarded instead of rejected |
| [D4](#d4) | **Low** | Duplicate-username error reports the wrong field |
| [D5](#d5) | **Low** | Gender validation error lists no allowed values |

### Context: the endpoint is unauthenticated

`/account/create` accepts requests with **no `Authorization` header**. The
internal VAPT report dated 2026-05-15 (`SECURITY_FINDINGS.md`) raised this as a
**critical** finding and recommended enforcing auth middleware. It appears
unresolved as of 2026-08-19.

This materially raises the severity of **D1** and **D2**: a defect that needs a
privileged account to exploit is an internal data-quality problem, whereas the
same defect on an endpoint open to the public internet is an abuse vector.

Please confirm whether public self-registration is now an intentional product
feature. If it is, the VAPT finding should be closed with a note. If it is not,
that fix likely takes priority over everything below.

---

<a name="d1"></a>
## D1 — No password policy — CLOSED, NOT A DEFECT

> **Closed 2026-08-20.** Confirmed by the QA lead that the absence of a
> password policy is **intentional**, requested by the client and end users.
> No action required. The automated check has been commented out in
> `test_account_create_known_issues.py`.
>
> The original finding is kept below for the record. Note that it interacts
> with the unauthenticated-endpoint question above: if public self-registration
> is intentional *and* short passwords are intentional, the combination is
> worth a conscious sign-off rather than two separate decisions.

**What happens.** The endpoint accepts any non-empty password. `1234`, `a` and
`password` all create active accounts.

**Reproduce.**

```bash
curl -X POST 'https://qa-interface.prathamdigital.org/interface/v1/account/create' \
  -H 'Content-Type: application/json' \
  -d '{"firstName":"Test","lastName":"User","dob":"1999-08-10","gender":"male",
       "mobile":"8600367304","username":"weakpw001","password":"1234",
       "tenantCohortRoleMapping":[{"roleId":"eea7ddab-bdf9-4db1-a1bb-43ef503d65ef",
       "tenantId":"e39447df-069d-4ccf-b92c-576f70b350f3"}]}'
```

**Actual** — `HTTP 201`, account created:

```json
{"params": {"status": "successful", "err": null, "errmsg": null},
 "responseCode": 201,
 "result": {"userData": {"userId": "e4f93824-ce39-4c19-9048-81a12663539d",
                         "username": "autoQA86492siy", "status": "active"}}}
```

**Expected.** `HTTP 400` with a message describing the policy.

**Why it matters.** Accounts with trivial passwords are trivially
credential-stuffed. Because the endpoint needs no authentication, anyone can
create them at will. `temporaryPassword: true` is returned, but nothing in the
API forces a change before the account is usable.

**Suggested fix.** Apply a password policy at the DTO/validation layer —
minimum length (8+), and reject values on a common-password deny list. Keep the
rule identical to whatever the password-reset flow enforces, so the two cannot
drift.

**Test:** `test_weak_passwords_should_be_rejected[1234|a|password]`

---

<a name="d2"></a>
## D2 — `customFields` is optional (Medium)

**What happens.** Both an omitted `customFields` key and an empty
`customFields: []` are accepted. The account is created with no state,
district, block, village or medium.

**Reproduce.** Send a valid payload with the `customFields` key removed
entirely, then again with `"customFields": []`.

**Actual** — `HTTP 201` in both cases:

```
no customFields key   -> 201, userId 2158558f-0bee-4a5c-858f-c21d6cc385ce
customFields: []      -> 201, userId e1739959-c61b-4263-9538-bff05302a1d9
```

**Expected.** `HTTP 400` if these fields are mandatory for the tenant.

**Why it matters.** The PLP web app always sends all five, so this is
unreachable through the UI — but the API is public, so incomplete profiles can
be created directly. Any reporting, cohort assignment or geography-based
filtering that assumes those fields exist will silently skip or miscount these
users.

**Please confirm:** are these fields genuinely mandatory? If they are optional
by design, this is not a defect and we will close it — but then downstream
consumers need to handle nulls.

**Suggested fix.** If mandatory, validate that every required `fieldId` for the
tenant is present and non-empty, and return `400` naming the missing fields.

**Tests:** `test_missing_custom_fields_should_be_rejected`,
`test_empty_custom_fields_should_be_rejected`

---

<a name="d3"></a>
## D3 — Non-numeric mobile silently discarded (Medium)

**What happens.** `mobile: "abcdefghij"` does not fail validation. The account
is created successfully with `mobile: null`.

Note that numeric validation *does* work — `"123"` (too short) and
`"86003673040000"` (too long) are both correctly rejected with `400`. The gap
is specific to non-numeric input.

**Actual** — `HTTP 201`:

```json
{"params": {"status": "successful"},
 "result": {"userData": {"userId": "efe78936-b2c7-49a5-860d-e3013e60959d",
                         "mobile": null}}}
```

**Expected.** `HTTP 400`, consistent with how out-of-range numeric values are
already handled.

**Why it matters.** This is worse than a plain rejection. The caller receives
`201` and reasonably believes the phone number was saved, when it was silently
thrown away. Any OTP, SMS notification or phone-based recovery for that account
will fail later, far from the cause.

**Suggested fix.** Validate `mobile` as a 10-digit numeric string and reject
non-conforming input rather than coercing it to null.

**Test:** `test_non_numeric_mobile_should_be_rejected_not_dropped`

---

<a name="d4"></a>
## D4 — Duplicate-username error reports the wrong field (Low)

**What happens.** Re-registering an existing username returns `409` — correct —
but the message blames the email, and no email was submitted.

**Actual:**

```
HTTP 409
params.err    : "User exists with same username No email provided"
params.errmsg : "Email already exists"
```

**Expected.** `errmsg` should name the username, e.g.
`"Username already exists"`.

**Why it matters.** `errmsg` is what client applications surface to end users.
Someone registering is told to change an email address they never entered,
while the actual conflict — their chosen username — goes unmentioned. Note also
that `err` and `errmsg` contradict each other; `err` does mention the username.

**Suggested fix.** Return `"Username already exists"` in `errmsg` for a username
conflict, and reserve the email message for genuine email collisions. The
unpunctuated `err` string ("...same username No email provided") reads as two
concatenated messages and is worth tidying at the same time.

**Test:** `test_duplicate_username_error_should_mention_username`

---

<a name="d5"></a>
## D5 — Gender validation error lists no allowed values (Low)

**What happens.** The message is built to list the permitted values but the
list interpolates as empty:

```
HTTP 400
params.errmsg : "gender must be one of the following values: "
```

**Expected.** `"gender must be one of the following values: male, female, other"`

**Why it matters.** Purely a developer-experience issue, but the message is
actively misleading — it looks like *no* value is acceptable. Anyone
integrating against this API has to guess or read the source. The trailing
colon shows the intent was there; the enum just is not reaching the message.

**Suggested fix.** Check the enum passed to the validation decorator. This is
usually a `@IsEnum()` receiving a TypeScript `type` union (erased at runtime)
rather than a runtime `enum` object.

**Test:** `test_gender_error_should_list_allowed_values`

---

## Verifying a fix

The suite runs against QA on every push and weekdays at 10:00 AM IST.

```bash
pytest tests/api -m known_issue -v
```

While a defect exists the test reports `xfail`. Once fixed it reports `XPASS`
and **fails the build** — that is the signal to delete the `xfail` marker and
move the test into `test_account_create.py`. Please leave the marker removal to
the QA side so the promotion is tracked.

## Test data

Verification created these QA accounts, all prefixed `autoQA`:

```
autoQA86492siy   e4f93824-ce39-4c19-9048-81a12663539d   (D1, password "1234")
autoQA11299ggs   2158558f-0bee-4a5c-858f-c21d6cc385ce   (D2a)
autoQA25169srk   e1739959-c61b-4263-9538-bff05302a1d9   (D2b)
autoQA17158nwl   efe78936-b2c7-49a5-860d-e3013e60959d   (D3, mobile null)
autoQA53374spt   —                                       (D4)
```

The scheduled run adds roughly a dozen `autoQA*` accounts per day. If there is
a delete or deactivate endpoint we can call, point us at it and the suite will
clean up after itself.
