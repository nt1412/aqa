"""Load the STAGED bug corpus into an isolated AQA project via the REST front door.

Reads originals.json (Subagent A: O1..O20) and recurrences.json (Subagent B: R1..R10),
each a JSON array of {"id","text"}. Creates project BUGCORPUS (prefix BUGS), one plan,
one suite, one case per id (case name == id), and records a FAILED execution per id with
reasoning={"root_cause": text} so the real embedding path fires.

Run: python -m scripts.bugcorpus.load
"""

import json
from pathlib import Path

from scripts._aqaclient import API, auth, get, post

HERE = Path(__file__).parent
PREFIX = "BUGS"


def _load(name: str) -> list[dict]:
    items = json.loads((HERE / name).read_text())
    assert isinstance(items, list) and all("id" in i and "text" in i for i in items), name
    return items


def main() -> None:
    auth()
    items = _load("originals.json") + _load("recurrences.json")
    ids = [i["id"] for i in items]
    assert len(ids) == len(set(ids)), "duplicate ids across files"
    print(f"loaded {len(items)} reasoning notes ({len(_load('originals.json'))} O + "
          f"{len(_load('recurrences.json'))} R)")

    project = next((p for p in get("/api/v1/projects") if p["prefix"] == PREFIX), None)
    if project is None:
        project = post("/api/v1/projects", {"name": "BUGCORPUS", "prefix": PREFIX})
    pid = project["id"]

    plan = next((p for p in get(f"/api/v1/projects/{pid}/plans") if p["name"] == "recall"), None)
    if plan is None:
        plan = post(f"/api/v1/projects/{pid}/plans", {"name": "recall"})
    plan_id = plan["id"]

    suite = next((s for s in get(f"/api/v1/projects/{pid}/suites") if s["name"] == "bugs"), None)
    if suite is None:
        suite = post(f"/api/v1/projects/{pid}/suites", {"name": "bugs"})
    sid = suite["id"]

    existing = {c["name"]: c["id"] for c in get(f"/api/v1/suites/{sid}/cases")}
    recorded = 0
    for it in items:
        if it["id"] not in existing:
            created = post(
                f"/api/v1/suites/{sid}/cases",
                {"name": it["id"], "summary": it["id"], "execution_type": "automated"},
            )
            existing[it["id"]] = created["id"]
        post(
            "/api/v1/executions",
            {
                "case_id": existing[it["id"]],
                "plan_id": plan_id,
                "build_name": "b1",
                "status": "fail",
                "reasoning": {"root_cause": it["text"]},
            },
            cascade=False,
        )
        recorded += 1
    print(f"project=BUGCORPUS (#{pid}) plan=recall (#{plan_id}) suite=bugs (#{sid})  "
          f"recorded={recorded} (via REST {API})")


if __name__ == "__main__":
    main()
