# Defect Report — User Registration API

**Endpoint:** `POST https://qa-interface.prathamdigital.org/interface/v1/account/create`
**Environment:** QA
**Last verified:** 2026-08-20
**Raised by:** QA automation ([`prathamAPIautomation`](https://github.com/TawareAditya/prathamAPIautomation))
**Authorisation:** Testing performed on the team's own QA environment.

---

## How to read this report

Each defect has two parts:

- **In plain terms** — what is wrong, no technical knowledge assumed.
- **Technical detail** — reproduction steps, actual vs expected response, and a
  suggested fix, written for the developer who will pick it up.

Every finding was reproduced live on the date above, and every one has an
automated test. Those tests assert the **correct** behaviour and are marked
`xfail`, meaning "we expect this to fail until it's fixed". When a fix ships,
the test starts passing and **the build turns red** — that is the signal the
defect is resolved and the test should be promoted to the main suite. Nothing
here needs manual re-checking.

---

## Open defects

| ID | Priority | Defect | Product decision needed? |
|---|---|---|---|
| [D2](#d2) | **1 — Highest** | Location and language answers are not required; accounts can be created with an empty profile | **Yes** — are these fields mandatory? |
| [D3](#d3) | **2** | A mobile number typed as text is silently discarded; the account is created with no phone number | No |
| [D4](#d4) | 3 | Duplicate-username error blames the email address instead | No |
| [D5](#d5) | 4 | Gender error message does not say which values are allowed | No |
| [D6](#d6) | 2 | A constrained custom field accepts invalid values (stored in the DB) while the API read hides them | No |

**Closed:** [D1 — no password policy](#d1) — confirmed intentional, no action required.

**Jira:** D2→ATM-90, D3→ATM-91, D4→ATM-92, D5→ATM-93, IDOR→ATM-94.
D6 is **not yet filed** (Atlassian connector was down when found) — file under ATM-89.

D2 and D3 both cause **real data loss**. D4 and D5 are message-wording issues
that mislead people but lose nothing.

---

## Important context: this endpoint requires no login

`/account/create` accepts requests with **no authentication whatsoever**.
Anyone who knows the address can create real accounts.

The internal VAPT report of 2026-05-15 (`SECURITY_FINDINGS.md`) raised this as a
**critical** finding and recommended enforcing authentication. As of
2026-08-20 it appears unresolved.

This matters for the defects below. A validation gap reachable only by trusted
internal staff is a data-quality problem. The same gap on an endpoint open to
the public internet is something that can be exploited at scale.

**Question for the team:** is public self-registration now an intentional
product feature? If yes, the VAPT finding should be formally closed with that
reasoning. If no, fixing it likely outranks everything in this report.

---

<a name="d2"></a>
## D2 — Location and language answers are not required

**Priority 1 · Needs a product decision**

### In plain terms

When someone registers on the PLP website, the form asks more than name and
password. It also asks **where they live** — state, district, block, village —
and **which language they prefer**. Those five answers travel to the server
together in a section of the request called `customFields`.

The server does not insist on that section. If a registration request arrives
without it, the server accepts it and creates the account anyway, leaving all
five answers blank.

You would never see this by using the website, because the web form always
fills those answers in. But the registration service can be called directly,
without going through the form — and doing so needs no login at all. That is
how an account with no location ends up in the system.

**Why it matters.** Those five answers are how a learner is placed on the map.
A learner with no state or district cannot be counted in district reports, will
not appear in location filters, and cannot be routed to the right centre or
batch. The record exists but is invisible to anything organised by geography.

### Evidence

Three accounts created minutes apart on 2026-08-19, with consecutive enrolment
IDs. All three are active learner accounts in the Pratham tenant.

| Account | Enrolment ID | `customFields` sent | Stored on the account |
|---|---|---|---|
| `autoQA86492siy` | PLP-032341 | all five | **5 values** ✅ |
| `autoQA11299ggs` | PLP-032342 | key omitted | **0 values** ❌ |
| `autoQA25169srk` | PLP-032343 | `[]` (empty list) | **0 values** ❌ |

The first account stored, correctly:

```
STATE                            = Andaman And Nicobar Islands
DISTRICT                         = Nicobars
BLOCK                            = Campbell Bay
VILLAGE                          = Afra Bay
WHAT_IS_YOUR_PREFERRED_LANGUAGE  = english
```

The other two stored nothing at all.

### Technical detail

**Reproduce** — take any valid registration payload and either remove the
`customFields` key or set it to `[]`:

```bash
curl -X POST 'https://qa-interface.prathamdigital.org/interface/v1/account/create' \
  -H 'Content-Type: application/json' \
  -d '{"firstName":"Test","lastName":"User","dob":"1999-08-10","gender":"male",
       "mobile":"8600367304","username":"cfprobe001","password":"Test@1234",
       "customFields":[],
       "tenantCohortRoleMapping":[{"roleId":"eea7ddab-bdf9-4db1-a1bb-43ef503d65ef",
       "tenantId":"e39447df-069d-4ccf-b92c-576f70b350f3"}]}'
```

**Actual:** `HTTP 201`, `params.status: "successful"`, account created.
**Expected:** `HTTP 400` naming the missing fields — *if* they are mandatory.

**To confirm what was stored:**

```bash
GET /interface/v1/user/read/{userId}?fieldvalue=true
```

Note the `?fieldvalue=true` query parameter is **required**. Without it the
response omits `customFields` entirely, whether or not values exist — which
makes the problem invisible during casual checking.

**Field reference** (labels confirmed from the server's own read response):

| `fieldId` | Server label |
|---|---|
| `6469c3ac-8c46-49d7-852a-00f9589737c5` | STATE |
| `b61edfc6-3787-4079-86d3-37262bf23a9e` | DISTRICT |
| `4aab68ae-8382-43aa-a45a-e9b239319857` | BLOCK |
| `8e9bb321-ff99-4e2e-9269-61e863dd0c54` | VILLAGE |
| `7735e603-ce0e-4b1d-95f4-7d4b67267777` | WHAT_IS_YOUR_PREFERRED_LANGUAGE |

**Suggested fix.** If these fields are mandatory for the tenant, validate that
every required `fieldId` is present with a non-empty value, and return `400`
listing the ones missing. Drive it from the tenant's field configuration rather
than a hardcoded list, so the rule follows the config.

**If they are optional by design**, this is not a defect and we will close it —
but downstream reporting and cohort assignment then need to handle learners
with no location data, and that should be confirmed explicitly.

**Automated tests:** `test_missing_custom_fields_should_be_rejected`,
`test_empty_custom_fields_should_be_rejected`

---

<a name="d3"></a>
## D3 — A mobile number typed as text is silently discarded

**Priority 2**

### In plain terms

The registration form asks for a mobile number. If letters are sent instead of
digits, the server replies **"User created successfully"** — but it does not
save what was sent. It throws the value away and stores the phone number as
blank, while telling the caller everything worked.

**Why it matters.** Refusing bad input would be fine. Accepting it and quietly
discarding it is the problem, because everyone downstream believes a number was
saved. For that learner:

- password recovery by SMS will not work — there is no number to send to
- OTP login will not work
- nobody can contact them
- the failure only surfaces weeks later, with nothing linking it back to
  registration

The person registering saw a success message, so they have no idea anything
went wrong.

### Evidence

Account `autoQA17158nwl` (**PLP-032344**), created 2026-08-19 by sending
`"mobile": "abcdefghij"`. Read back on 2026-08-20:

```
username     : 'autoQA17158nwl'
enrollmentId : 'PLP-032344'
mobile       : None
email        : None
```

This account has **no contact route of any kind**.

### Technical detail

What makes this a bug rather than a design choice is that mobile validation
*does* exist — it is just incomplete:

| Value sent | Length | Result |
|---|---|---|
| `123` | 3 digits | `400` rejected ✅ correct |
| `86003673040000` | 14 digits | `400` rejected ✅ correct |
| `abcdefghij` | **10 characters** | **`201` accepted, stored as `null`** ❌ |

The pattern suggests the check tests **length** but not whether the value is
numeric. `abcdefghij` is ten characters, so it passes the length rule, then
fails conversion to a number — and that failure becomes `null` instead of an
error.

**Actual:** `HTTP 201` with `result.userData.mobile: null`.
**Expected:** `HTTP 400`, consistent with how out-of-range values already
behave.

**Suggested fix.** Validate `mobile` as a 10-digit numeric string and reject
non-conforming input rather than coercing it to `null`. If a blank mobile is
legitimately permitted, that should require the field to be **absent or
explicitly null** — never the silent result of discarding what the user typed.

**Automated test:** `test_non_numeric_mobile_should_be_rejected_not_dropped`

---

<a name="d4"></a>
## D4 — Duplicate-username error blames the email address

**Priority 3**

### In plain terms

If someone tries to register with a username that is already taken, the server
correctly refuses — but the message it sends back says **"Email already
exists"**, even when no email address was entered at all.

Someone registering is therefore told to change an email they never typed,
while the real problem — their chosen username — is never mentioned. It is a
wording problem, not data loss, but it sends users down the wrong path.

### Technical detail

```
HTTP 409
params.err    : "User exists with same username No email provided"
params.errmsg : "Email already exists"
```

`errmsg` is the field client applications surface to end users, and it names
the wrong field. Note also that `err` and `errmsg` **contradict each other** —
`err` correctly mentions the username.

**Expected:** `errmsg` should read `"Username already exists"` for a username
conflict, reserving the email wording for genuine email collisions.

**Suggested fix.** Return the message matching the field that actually clashed.
The `err` string ("...same username No email provided") also reads as two
sentences concatenated without punctuation and is worth tidying at the same
time.

**Automated test:** `test_duplicate_username_error_should_mention_username`

---

<a name="d5"></a>
## D5 — Gender error does not say which values are allowed

**Priority 4**

### In plain terms

If an invalid gender value is submitted, the server refuses — correctly — but
the message stops mid-sentence:

> `gender must be one of the following values: `

It never says what the acceptable values are. Anyone building against this API
has to guess. It looks as though *no* value is acceptable.

### Technical detail

```
HTTP 400
params.errmsg : "gender must be one of the following values: "
```

The trailing colon shows the message was designed to list the permitted values;
the list simply is not reaching it.

**Expected:** `"gender must be one of the following values: male, female, other"`

**Suggested fix.** Check the enum passed to the validation decorator. This is
typically an `@IsEnum()` receiving a TypeScript union *type* — which is erased
at runtime and yields an empty list — rather than a runtime `enum` object.

**Automated test:** `test_gender_error_should_list_allowed_values`

---

<a name="d1"></a>
## D1 — No password policy — CLOSED, not a defect

> **Closed 2026-08-20.** Confirmed that the absence of a password policy is
> **intentional**, requested by the client and end users. Short passwords such
> as `1234` are accepted by design. No action required.
>
> The automated check has been commented out (not deleted) in
> `test_account_create_known_issues.py`, so the decision stays on record and
> the test can be restored if the requirement changes.

**One point worth a conscious sign-off.** Public self-registration and
deliberately permissive passwords are each defensible on their own. The
combination — anyone on the public internet able to create accounts with a
password of `1234` — is worth one explicit product decision rather than two
separate ones. Flagging it for visibility, not as a defect.

---

<a name="d6"></a>
## D6 — Constrained custom field stores invalid values; the API read hides them

**Priority 2 · Found via direct DB verification, 2026-08-27**

### In plain terms

Some profile fields are meant to accept only a fixed list of options (like a
dropdown). The update API doesn't enforce that — it accepts **any** text and
writes it to the database. Worse, the API's own read-back then **hides** the
invalid value, so through the API everything looks fine while the database
holds junk. This is invisible without looking at the database directly, which
is exactly what the DB verification tests are for.

Note: this corrects an earlier, API-only reading of the enrollment-status
field that mistook this for a "silent discard" like D3. The value is **not**
discarded — it **is** stored; the read simply omits it.

### Evidence (QA, 2026-08-27)

Sent to the enrollment-status field
(`fieldId f8dc1d5f-9b2b-412e-a22a-351bd8f14963`, label `INTERESTED_TO_JOIN`)
via `PATCH /user/update/{userId}`:

```
sent invalid value : "approved_xyz"
API PATCH response : HTTP 200 "successful"
DB FieldValues     : ['approved_xyz']     <- garbage stored, no validation
API /user/read     : []                   <- read hides what the DB holds
```

### Technical detail

Two defects, one root cause (no option-set validation on write):

1. **Write:** `PATCH /user/update/{userId}` accepts a value outside the field's
   allowed option set and stores it. Expected: `HTTP 400`.
2. **Read:** `GET /user/read/{userId}?fieldvalue=true` omits the stored value
   because it can't resolve it to a known option, so the API read disagrees
   with the database.

**Impact.** Constrained fields can be corrupted with arbitrary data through the
API, and the corruption is invisible via the API read — anyone trusting
`/user/read` sees an empty field while the database holds an invalid value.

**Suggested fix.** Validate custom-field values against the field's allowed
options on write and return `400` on mismatch; make the read surface stored
values consistently rather than filtering out unrecognised ones.

**Automated test:**
`tests/api/test_db_verification.py::test_invalid_option_value_should_not_be_stored`
(xfail — asserts the DB does not store an out-of-set value).

---

## Verifying a fix

The suite runs against QA on every push and weekdays at 10:00 AM IST.

```bash
pytest tests/api -m known_issue -v
```

| Report shows | Meaning |
|---|---|
| `XFAIL` | Defect still present. Build stays green. |
| `XPASS` + build **fails** | Defect fixed — remove the `xfail` marker and promote the test. |

Please leave marker removal to QA so promotions stay tracked.

---

## Test data on QA

Verification created these accounts, all prefixed `autoQA`:

```
autoQA86492siy   PLP-032341   D2 control — all five fields present
autoQA11299ggs   PLP-032342   D2 — customFields omitted
autoQA25169srk   PLP-032343   D2 — customFields empty
autoQA17158nwl   PLP-032344   D3 — mobile and email both null
```

The scheduled run adds roughly a dozen `autoQA*` accounts per day and there is
currently **no cleanup**.

**Request:** if a delete or deactivate endpoint exists that QA may call, please
point us at it and the suite will remove its own data after each run. Without
one, these accumulate indefinitely and will eventually distort learner counts
on QA.

---

## Open questions for the team

1. **Is public unauthenticated registration intentional?** Changes the priority
   of everything above. *(Owner: product / security)*
2. **Are the five location and language fields mandatory?** Determines whether
   D2 is a defect or expected behaviour. *(Owner: product)*
3. **Is there an endpoint QA can use to delete test accounts?**
   *(Owner: API team)*
