"""Build an HTML email summary from pytest's JUnit XML output.

Newman gets this from newman-reporter-htmlextra; pytest has no equivalent, so
we render one from the JUnit report.

    python -m utility.api.ci_summary reports/junit.xml reports/email-summary.html

Styling is inline on purpose — Gmail, Outlook and most clients strip <style>
blocks, so a stylesheet would arrive as unformatted text.
"""

import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

# xfail arrives as <skipped type="pytest.xfail">, a genuine skip as
# type="pytest.skip". They mean very different things, so keep them apart.
XFAIL_TYPE = "pytest.xfail"

OK = "#1a7f37"
BAD = "#cf222e"
WARN = "#9a6700"
MUTED = "#57606a"
BORDER = "#d0d7de"


def parse(xml_path):
    root = ET.parse(xml_path).getroot()
    suites = root.findall("testsuite") if root.tag == "testsuites" else [root]

    passed, failures, errors, xfails, skips = [], [], [], [], []
    duration = 0.0

    for suite in suites:
        duration += float(suite.get("time") or 0)
        for case in suite.findall("testcase"):
            name = f"{case.get('classname', '')}::{case.get('name', '')}"
            failure = case.find("failure")
            error = case.find("error")
            skipped = case.find("skipped")

            if failure is not None:
                failures.append((name, failure.get("message", "").strip()))
            elif error is not None:
                errors.append((name, error.get("message", "").strip()))
            elif skipped is not None:
                entry = (name, skipped.get("message", "").strip())
                if skipped.get("type") == XFAIL_TYPE:
                    xfails.append(entry)
                else:
                    skips.append(entry)
            else:
                passed.append(name)

    return {
        "passed": passed,
        "failures": failures,
        "errors": errors,
        "xfails": xfails,
        "skips": skips,
        "duration": duration,
    }


def esc(text):
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def tile(label, value, color):
    return (
        f'<td style="padding:10px 16px;border:1px solid {BORDER};'
        f'border-radius:6px;text-align:center;">'
        f'<div style="font-size:22px;font-weight:700;color:{color};">{value}</div>'
        f'<div style="font-size:11px;color:{MUTED};text-transform:uppercase;'
        f'letter-spacing:.4px;">{esc(label)}</div></td>'
    )


def detail_block(title, items, color, note=None):
    if not items:
        return ""
    rows = []
    for name, message in items:
        first_line = (message or "").splitlines()[0][:300] if message else ""
        rows.append(
            f'<div style="padding:8px 10px;border-left:3px solid {color};'
            f'background:#f6f8fa;margin-bottom:6px;">'
            f'<div style="font-family:Consolas,monospace;font-size:12px;'
            f'color:#24292f;word-break:break-all;">{esc(name)}</div>'
            + (
                f'<div style="font-size:12px;color:{MUTED};margin-top:3px;">'
                f"{esc(first_line)}</div>"
                if first_line
                else ""
            )
            + "</div>"
        )
    note_html = (
        f'<p style="font-size:12px;color:{MUTED};margin:0 0 8px;">{esc(note)}</p>'
        if note
        else ""
    )
    return (
        f'<h3 style="font-size:14px;color:{color};margin:20px 0 8px;">'
        f"{esc(title)} ({len(items)})</h3>{note_html}" + "".join(rows)
    )


def render(data, env):
    broken = data["failures"] + data["errors"]
    total = (
        len(data["passed"])
        + len(broken)
        + len(data["xfails"])
        + len(data["skips"])
    )

    if broken:
        headline, color = "Tests failed", BAD
    else:
        headline, color = "All tests passed", OK

    run_url = ""
    if env.get("server_url") and env.get("repository") and env.get("run_id"):
        url = f"{env['server_url']}/{env['repository']}/actions/runs/{env['run_id']}"
        run_url = (
            f'<p style="margin:18px 0 0;"><a href="{esc(url)}" '
            f'style="background:#0969da;color:#fff;padding:9px 16px;'
            f'border-radius:6px;text-decoration:none;font-size:13px;'
            f'display:inline-block;">View run &amp; download reports</a></p>'
        )

    meta_rows = "".join(
        f'<tr><td style="padding:3px 14px 3px 0;color:{MUTED};font-size:12px;">'
        f"{esc(label)}</td>"
        f'<td style="padding:3px 0;font-size:12px;color:#24292f;">{esc(value)}</td></tr>'
        for label, value in [
            ("Target API", env.get("base_url", "-")),
            ("Repository", env.get("repository", "-")),
            ("Branch", env.get("ref_name", "-")),
            ("Trigger", env.get("event_name", "-")),
            ("Commit", (env.get("sha") or "-")[:8]),
            ("Duration", f"{data['duration']:.1f}s"),
            ("Finished", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")),
        ]
        if value
    )

    return f"""<div style="font-family:-apple-system,Segoe UI,Helvetica,Arial,sans-serif;
max-width:720px;color:#24292f;">
  <h2 style="margin:0 0 4px;font-size:19px;color:{color};">{headline}</h2>
  <p style="margin:0 0 16px;color:{MUTED};font-size:13px;">
    API Automation &mdash; {total} tests in {data['duration']:.1f}s</p>

  <table cellspacing="6" cellpadding="0" style="border-collapse:separate;">
    <tr>
      {tile("Passed", len(data["passed"]), OK)}
      {tile("Failed", len(broken), BAD if broken else MUTED)}
      {tile("Known issues", len(data["xfails"]), WARN if data["xfails"] else MUTED)}
      {tile("Skipped", len(data["skips"]), MUTED)}
    </tr>
  </table>

  {detail_block("Failures", broken, BAD)}
  {detail_block(
      "Known issues (expected failures)",
      data["xfails"],
      WARN,
      "These track defects the API has not fixed yet. If one of them starts "
      "FAILING, the bug was fixed and the test should be promoted.",
  )}
  {detail_block("Skipped", data["skips"], MUTED)}

  <h3 style="font-size:14px;margin:22px 0 6px;">Run details</h3>
  <table cellspacing="0" cellpadding="0">{meta_rows}</table>
  {run_url}
</div>"""


def write_step_summary(data, base_url):
    """Append a markdown digest to the GitHub Actions run page, if we're on CI."""
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if not path:
        return
    broken = data["failures"] + data["errors"]
    lines = [
        "## API Automation Tests",
        "",
        f"Target: `{base_url or 'default'}`",
        "",
        "| Passed | Failed | Known issues | Skipped | Duration |",
        "|---|---|---|---|---|",
        f"| {len(data['passed'])} | {len(broken)} | {len(data['xfails'])} "
        f"| {len(data['skips'])} | {data['duration']:.1f}s |",
    ]
    if broken:
        lines += ["", "### Failures", ""]
        for name, message in broken:
            first_line = (message or "").splitlines()[0][:200] if message else ""
            lines.append(f"- `{name}`" + (f" — {first_line}" if first_line else ""))
    if data["xfails"]:
        lines += [
            "",
            f"<details><summary>{len(data['xfails'])} known issues "
            "(expected failures)</summary>",
            "",
        ]
        lines += [f"- `{name}`" for name, _ in data["xfails"]]
        lines += ["", "</details>"]

    with open(path, "a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def main():
    xml_path = sys.argv[1] if len(sys.argv) > 1 else "reports/junit.xml"
    out_path = sys.argv[2] if len(sys.argv) > 2 else "reports/email-summary.html"

    env = {
        "base_url": os.getenv("API_BASE_URL", ""),
        "repository": os.getenv("GITHUB_REPOSITORY", ""),
        "ref_name": os.getenv("GITHUB_REF_NAME", ""),
        "event_name": os.getenv("GITHUB_EVENT_NAME", ""),
        "sha": os.getenv("GITHUB_SHA", ""),
        "run_id": os.getenv("GITHUB_RUN_ID", ""),
        "server_url": os.getenv("GITHUB_SERVER_URL", "https://github.com"),
    }

    try:
        data = parse(xml_path)
    except (OSError, ET.ParseError) as exc:
        # The suite may have crashed before writing XML — still send something
        # useful rather than an empty email.
        html = (
            f'<div style="font-family:Arial,sans-serif;">'
            f'<h2 style="color:{BAD};">Could not read the test report</h2>'
            f"<p>Expected JUnit XML at <code>{esc(xml_path)}</code> but: "
            f"{esc(exc)}</p><p>The run probably failed before tests started. "
            f"Check the workflow logs.</p></div>"
        )
    else:
        html = render(data, env)
        write_step_summary(data, env["base_url"])
        print(
            f"Summary: {len(data['passed'])} passed, "
            f"{len(data['failures']) + len(data['errors'])} failed, "
            f"{len(data['xfails'])} xfailed, {len(data['skips'])} skipped"
        )

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as handle:
        handle.write(html)
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
