"""Dogfood: catalog AQA's own pytest suite inside AQA, and record a run —
through the **front door** (REST), the same surface a Bash-tool agent/CI uses.

Earlier this called the service layer directly; that hid the ergonomics a real
agent hits. Now it speaks HTTP to /api/v1 exactly as `aqa` CLI does, so the
dogfood exercises (and regression-proves) the public surface. It is idempotent:
re-running reuses the AQA project, suites, and cases, and records one fresh
execution per case for the current git build (branch + merge-base included, so
runs off `main` populate the branch/merge-readiness views).

Auth: set AQA_API_KEY (an agent key) — else falls back to admin login
(AQA_ADMIN_LOGIN/PASSWORD, default admin/admin).

Usage:
    python -m pytest --junitxml=dogfood-results.xml   # produce real results
    python -m scripts.dogfood                          # catalog + record run
"""

import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

from scripts._aqaclient import API, auth, get, post

PROJECT_NAME = "AQA"
PROJECT_PREFIX = "AQA"
PLAN_NAME = "CI"
DEFAULT_BRANCH = "main"
JUNIT_PATH = Path("dogfood-results.xml")


def _git(*args: str) -> str | None:
    try:
        return subprocess.check_output(["git", *args], text=True).strip()
    except subprocess.CalledProcessError:
        return None


def _parse_junit(path: Path) -> list[dict]:
    tree = ET.parse(path)
    results = []
    for tc in tree.findall(".//testcase"):
        classname = tc.get("classname", "")
        name = tc.get("name", "")
        suite = classname.rsplit(".", 1)[-1].removeprefix("test_")
        nodeid = f"{classname.replace('.', '/')}.py::{name}"
        tags = {child.tag for child in tc}
        status = "fail" if ("failure" in tags or "error" in tags) else (
            "not_run" if "skipped" in tags else "pass"
        )
        results.append({"suite": suite, "name": name, "nodeid": nodeid, "status": status})
    return results


def main() -> None:
    if not JUNIT_PATH.exists():
        raise SystemExit(f"{JUNIT_PATH} not found — run: python -m pytest --junitxml={JUNIT_PATH}")
    auth()

    sha = _git("rev-parse", "--short", "HEAD") or "local"
    full_sha = _git("rev-parse", "HEAD")
    branch = _git("rev-parse", "--abbrev-ref", "HEAD") or DEFAULT_BRANCH
    # always compute + send the merge-base (on main this == HEAD, i.e. degenerate)
    base_commit = _git("merge-base", "HEAD", DEFAULT_BRANCH)
    tests = _parse_junit(JUNIT_PATH)

    # project (find-or-create by prefix, client-side)
    project = next((p for p in get("/api/v1/projects") if p["prefix"] == PROJECT_PREFIX), None)
    if project is None:
        project = post("/api/v1/projects", {"name": PROJECT_NAME, "prefix": PROJECT_PREFIX})
    pid = project["id"]

    # plan
    plan = next((p for p in get(f"/api/v1/projects/{pid}/plans") if p["name"] == PLAN_NAME), None)
    if plan is None:
        plan = post(f"/api/v1/projects/{pid}/plans", {"name": PLAN_NAME})
    plan_id = plan["id"]

    suite_ids = {s["name"]: s["id"] for s in get(f"/api/v1/projects/{pid}/suites")}
    case_cache: dict[int, dict[str, int]] = {}
    recorded = 0
    for t in tests:
        sname = t["suite"]
        if sname not in suite_ids:
            suite_ids[sname] = post(f"/api/v1/projects/{pid}/suites", {"name": sname})["id"]
        sid = suite_ids[sname]
        if sid not in case_cache:
            case_cache[sid] = {c["name"]: c["id"] for c in get(f"/api/v1/suites/{sid}/cases")}
        if t["name"] not in case_cache[sid]:
            created = post(
                f"/api/v1/suites/{sid}/cases",
                {"name": t["name"], "summary": t["nodeid"], "execution_type": "automated"},
            )
            case_cache[sid][t["name"]] = created["id"]
        body = {
            "case_id": case_cache[sid][t["name"]],
            "plan_id": plan_id,
            "build_name": sha,
            "commit_id": full_sha,
            "branch": branch,
            "status": t["status"],
        }
        if base_commit:
            body["base_commit"] = base_commit
        post("/api/v1/executions", body, cascade=False)
        recorded += 1

    runs = get(f"/api/v1/plans/{plan_id}/executions")
    passed = sum(1 for r in runs if r["status"] == "pass")
    failed = sum(1 for r in runs if r["status"] == "fail")
    print(
        f"project={PROJECT_NAME} (#{pid})  plan={PLAN_NAME} (#{plan_id})  "
        f"build={sha}  branch={branch}"
    )
    print(f"suites={len(suite_ids)}  cases_catalogued={recorded}  (via REST {API})")
    print(f"executions_for_plan={len(runs)}  pass={passed}  fail={failed}")


if __name__ == "__main__":
    main()
