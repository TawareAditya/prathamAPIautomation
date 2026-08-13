# Pratham API Automation

Automated API tests for the Pratham interface API, built on pytest + requests.
No browser required — the full suite runs in about 7 seconds.

[![API Automation Tests](https://github.com/TawareAditya/prathamAPIautomation/actions/workflows/api-tests.yml/badge.svg)](https://github.com/TawareAditya/prathamAPIautomation/actions/workflows/api-tests.yml)

## Quick start

```bash
git clone https://github.com/TawareAditya/prathamAPIautomation.git
cd prathamAPIautomation

python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

pytest tests/api -v
```

Expected result: **26 passed, 9 xfailed**.

The suite needs no credentials — the endpoint under test is public.

## Common commands

```bash
pytest tests/api -v                    # everything
pytest tests/api -m smoke              # 2-test health check
pytest tests/api -m known_issue -v     # just the tracked defects
pytest tests/api -m negative           # error-handling cases

# with reports
pytest tests/api --html=reports/api-report.html --self-contained-html \
                 --junitxml=reports/junit.xml
python -m utility.api.ci_summary reports/junit.xml reports/email-summary.html
```

## Targeting another environment

Config is environment-driven; no code changes needed.

```bash
set API_BASE_URL=https://dev-interface.prathamdigital.org/interface/v1
pytest tests/api
```

Full list of variables: [utility/api/api_config.py](utility/api/api_config.py).

## Layout

```
tests/api/                      test cases
  test_account_create.py          26 tests covering correct behaviour
  test_account_create_known_issues.py   9 xfail defect trackers
  conftest.py                     fixtures (api, fresh_api, registered_user)
utility/api/                    framework
  client.py                       requests wrapper, masked logging
  api_config.py                   env-driven settings
  payloads.py                     request builders
  asserts.py                      envelope-aware assertions
  endpoints.py                    path constants
  ci_summary.py                   JUnit XML -> HTML email summary
.github/workflows/api-tests.yml CI pipeline
```

Adding a negative case is a one-line override — `None` removes a field:

```python
payloads.registration_payload(username=None)     # missing field
payloads.registration_payload(gender="banana")   # invalid value
```

## CI

Runs on every push, on PRs to `main`, and **weekdays at 10:00 AM IST**
(`cron: "30 4 * * 1-5"` — GitHub cron is UTC, IST is UTC+5:30).

Scheduled runs email an HTML summary. Required repository secrets:

| Secret | Example |
|---|---|
| `MAIL_SERVER` | `smtp.gmail.com` |
| `MAIL_PORT` | `465` |
| `MAIL_USERNAME` | sending address |
| `MAIL_PASSWORD` | app password, **not** the account password |
| `MAIL_RECIPIENTS` | comma-separated, no spaces |

Without these the tests still run and reports still upload — only the email
step is skipped.

Note: GitHub disables scheduled workflows after 60 days of repository
inactivity, and cron firing times are best-effort (expect 10:00–10:20).

## Known issues

`test_account_create_known_issues.py` asserts the behaviour we believe is
**correct**, marked `xfail(strict=True)`:

- while the bug exists → reported `xfail`, build stays green
- once fixed → reported `XPASS` and the build **fails**, so nothing lands silently

When one starts failing, delete the marker and move the test into
`test_account_create.py`.

| # | Issue |
|---|---|
| 1 | `customFields` is optional — users can register with no state/district/block/village/medium |
| 2 | An empty `customFields: []` is likewise accepted |
| 3 | Duplicate username returns `"Email already exists"` even when no email was sent |
| 4 | Gender error lists no allowed values: `"must be one of the following values: "` |
| 5 | No password policy — `"1234"`, `"a"`, `"password"` all accepted on a public endpoint |
| 6 | Non-numeric `mobile` is silently dropped (`201` with `mobile: null`) instead of rejected |
| 7 | `mobile` is sent as a string but returned as a number — leading zeros would be corrupted |

### Open question: should this endpoint be public at all?

`POST /account/create` currently accepts **unauthenticated** requests. An
internal VAPT report dated 2026-05-15 flagged exactly this as a **critical**
finding and recommended enforcing auth middleware.

This suite currently asserts that unauthenticated creation **succeeds**. If the
VAPT finding still stands, these tests are pointed the wrong way and should be
converted to `xfail` tests expecting `401`. Confirm with the API owner before
relying on this suite as a security gate.

## Test data

Each run registers roughly a dozen accounts on the target environment, all
prefixed `autoQA` (set `API_USERNAME_PREFIX` to change). No delete endpoint is
wired up — if one exists, add it to `endpoints.py` and clean up in the
`registered_user` fixture teardown.
