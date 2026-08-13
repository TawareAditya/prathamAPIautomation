# API Test Suite

API-level tests for the Pratham interface API. No browser — these run in
seconds and are safe to run on every commit.

## Running

```bash
# everything
venv\Scripts\python.exe -m pytest tests/api -v

# quick health check (2 tests, ~1s)
venv\Scripts\python.exe -m pytest tests/api -m smoke

# only the known-defect tests
venv\Scripts\python.exe -m pytest tests/api -m known_issue -v

# skip API tests and run only the UI suite, as before
venv\Scripts\python.exe -m pytest tests -m "not api"

# with an HTML report
venv\Scripts\python.exe -m pytest tests/api --html=reports/api.html --self-contained-html
```

## CI

[.github/workflows/api-tests.yml](../../.github/workflows/api-tests.yml) runs
the suite on every push, on PRs to `main`, and at 09:30 IST on weekdays.

Reproduce a CI run locally:

```bash
venv\Scripts\python.exe -m pytest tests/api --html=reports/api-report.html ^
  --self-contained-html --junitxml=reports/junit.xml
venv\Scripts\python.exe -m utility.api.ci_summary reports/junit.xml reports/email-summary.html
```

Required repository secrets for the email step: `MAIL_SERVER`, `MAIL_PORT`,
`MAIL_USERNAME`, `MAIL_PASSWORD`, `MAIL_RECIPIENTS` (comma-separated). Without
them the tests still run and reports still upload — only the email is skipped.

## Pointing at another environment

Everything is environment-driven; no code changes needed.

```bash
set API_BASE_URL=https://dev-interface.prathamdigital.org/interface/v1
set API_TENANT_ID=<tenant-uuid>
venv\Scripts\python.exe -m pytest tests/api
```

See [utility/api/api_config.py](../../utility/api/api_config.py) for the full
list. `POST /account/create` is public, so the suite needs no credentials.

## Layout

| File | Purpose |
|---|---|
| `utility/api/client.py` | `requests.Session` wrapper — base URL, timeout, masked logging |
| `utility/api/api_config.py` | Env-driven config (base URL, tenant/role, custom field IDs) |
| `utility/api/payloads.py` | Payload builders; `registration_payload(**overrides)` |
| `utility/api/asserts.py` | Envelope-aware assertions that print the failing body |
| `utility/api/endpoints.py` | Path constants |
| `tests/api/conftest.py` | `api`, `fresh_api`, `registered_user` fixtures |

Building a negative case is a single override — `None` drops the field:

```python
payloads.registration_payload(username=None)     # missing field
payloads.registration_payload(gender="banana")   # invalid value
```

## Known issues

`test_account_create_known_issues.py` asserts the behaviour we believe is
**correct**, marked `xfail(strict=True)`:

- while the bug exists → `xfail`, run stays green
- once it's fixed → `XPASS` and the run **fails**, so the fix can't land unnoticed

When one starts failing the build, delete the marker and move the test into
`test_account_create.py`.

Currently tracked against `POST /account/create`:

| # | Issue |
|---|---|
| 1 | `customFields` is optional — users can register with no state/district/block/village/medium |
| 2 | An empty `customFields: []` is likewise accepted |
| 3 | Duplicate username returns `"Email already exists"` even when no email was sent |
| 4 | Gender error lists no allowed values: `"must be one of the following values: "` |
| 5 | No password policy — `"1234"`, `"a"`, `"password"` all accepted on a public endpoint |
| 6 | Non-numeric `mobile` is silently dropped (`201` with `mobile: null`) instead of rejected |
| 7 | `mobile` is sent as a string but returned as a number — leading zeros would be corrupted |

## Test data

Each run registers roughly a dozen accounts on the target environment, prefixed
`autoQA` (configurable via `API_USERNAME_PREFIX`) so they can be identified
and purged. No delete endpoint is wired up yet — if one exists, add it to
`endpoints.py` and clean up in a `registered_user` teardown.
