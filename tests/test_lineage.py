import pytest

from app.models.plan import Build
from app.schemas.execution import ExecutionCreate
from app.schemas.project import ProjectCreate
from app.schemas.suite import SuiteCreate
from app.schemas.testcase import TestCaseCreate
from app.services import executions, lineage, plans, projects, suites, testcases


async def _project_with_cases(session, prefix, n=3):
    from app.models.plan import TestPlan

    p = await projects.create_project(session, ProjectCreate(name="P", prefix=prefix))
    suite = await suites.create_suite(session, p.id, SuiteCreate(name="Root"))
    cases = [
        await testcases.create_test_case(session, suite.id, TestCaseCreate(name=f"c{i}"))
        for i in range(n)
    ]
    plan = TestPlan(project_id=p.id, name="Plan")
    session.add(plan)
    await session.commit()
    await session.refresh(plan)
    return p, suite, cases, plan


async def _record(session, case_id, plan_id, build_name, status, **kw):
    return await executions.record_execution(
        session,
        ExecutionCreate(
            case_id=case_id, plan_id=plan_id, build_name=build_name, status=status, **kw
        ),
        tester_id=None,
    )


# ---------- recorder: branch + base_commit on the build ----------


@pytest.mark.asyncio
async def test_record_persists_branch_and_base_commit(session):
    _, _, cases, plan = await _project_with_cases(session, "LINREC")
    ex = await _record(
        session,
        cases[0].id,
        plan.id,
        "b1",
        "pass",
        branch="feature/x",
        commit_id="abc123",
        base_commit="main999",
    )
    build = await session.get(Build, ex.build_id)
    assert build.branch == "feature/x"
    assert build.commit_id == "abc123"
    assert build.base_commit == "main999"


# ---------- build rollup (latest-per-case collapse + not_run denominator) ----------


@pytest.mark.asyncio
async def test_build_rollup_counts_latest_per_case(session):
    _, _, cases, plan = await _project_with_cases(session, "ROLL", n=3)
    await plans.add_cases(session, plan.id, [c.id for c in cases])  # 3 cases in plan
    # case0: fail then pass in the SAME build → must collapse to latest=pass
    await _record(session, cases[0].id, plan.id, "b1", "fail")
    ex = await _record(session, cases[0].id, plan.id, "b1", "pass")
    # case1: fail in b1
    await _record(session, cases[1].id, plan.id, "b1", "fail")
    # case2: never run in b1 → not_run

    roll = await lineage.build_rollup(session, ex.build_id)
    assert roll["pass"] == 1  # case0 collapsed to pass (not counted twice, not fail)
    assert roll["fail"] == 1  # case1
    assert roll["blocked"] == 0
    assert roll["not_run"] == 1  # case2 in plan, no result this build
    assert roll["plan_cases"] == 3
    assert roll["pass_rate"] == 33  # round(100 * 1/3)


# ---------- build detail ----------


@pytest.mark.asyncio
async def test_build_detail_lists_latest_per_case(session):
    _, _, cases, plan = await _project_with_cases(session, "DET", n=2)
    await plans.add_cases(session, plan.id, [c.id for c in cases])
    await _record(session, cases[0].id, plan.id, "b1", "fail")
    ex = await _record(session, cases[0].id, plan.id, "b1", "pass", commit_id="sha1", branch="main")

    detail = await lineage.build_detail(session, ex.build_id)
    assert detail["build"]["commit_id"] == "sha1"
    assert detail["build"]["branch"] == "main"
    assert detail["rollup"]["pass"] == 1
    by_case = {c["case_id"]: c for c in detail["cases"]}
    assert by_case[cases[0].id]["status"] == "pass"  # collapsed to latest
    assert by_case[cases[0].id]["external_id"] == cases[0].external_id


# ---------- case history + broke/fixed derivation ----------


@pytest.mark.asyncio
async def test_case_history_derives_broke_and_fixed(session):
    _, _, cases, plan = await _project_with_cases(session, "HIST", n=1)
    c = cases[0]
    await plans.add_cases(session, plan.id, [c.id])
    await _record(session, c.id, plan.id, "b1", "pass", commit_id="s1")
    await _record(session, c.id, plan.id, "b2", "fail", commit_id="s2")  # broke at s2
    await _record(session, c.id, plan.id, "b3", "pass", commit_id="s3")  # fixed at s3

    hist = await lineage.case_history(session, c.id)
    assert [e["status"] for e in hist["executions"]] == ["pass", "fail", "pass"]
    assert [e["commit_id"] for e in hist["executions"]] == ["s1", "s2", "s3"]
    kinds = {(t["type"], t["commit_id"]) for t in hist["transitions"]}
    assert ("broke", "s2") in kinds
    assert ("fixed", "s3") in kinds


# ---------- enriched builds timeline ----------


@pytest.mark.asyncio
async def test_list_builds_enriched_has_rollup_and_commit(session):
    _, _, cases, plan = await _project_with_cases(session, "BLDS", n=1)
    await plans.add_cases(session, plan.id, [cases[0].id])
    await _record(session, cases[0].id, plan.id, "b1", "pass", commit_id="sha1", branch="main")

    builds = await lineage.list_builds_enriched(session, plan.id)
    assert len(builds) == 1
    assert builds[0]["commit_id"] == "sha1"
    assert builds[0]["branch"] == "main"
    assert builds[0]["rollup"]["pass"] == 1
    assert builds[0]["rollup"]["pass_rate"] == 100


# ---------- REST surface ----------


@pytest.mark.asyncio
async def test_rest_build_timeline_detail_history(session, client, auth_headers):
    _, _, cases, plan = await _project_with_cases(session, "REST1", n=2)
    await plans.add_cases(session, plan.id, [c.id for c in cases])
    ex = await _record(session, cases[0].id, plan.id, "b1", "pass", commit_id="sha1", branch="main")

    r = await client.get(f"/api/v1/plans/{plan.id}/build-timeline", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()[0]["commit_id"] == "sha1"
    assert r.json()[0]["rollup"]["pass"] == 1

    r = await client.get(f"/api/v1/builds/{ex.build_id}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["build"]["branch"] == "main"
    assert r.json()["rollup"]["pass"] == 1

    r = await client.get(f"/api/v1/cases/{cases[0].id}/history", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["executions"][0]["commit_id"] == "sha1"


# ---------- baseline resolution ----------


@pytest.mark.asyncio
async def test_resolve_baseline_precise_then_fallback(session):
    _, _, cases, plan = await _project_with_cases(session, "BASE", n=1)
    c = cases[0]
    await plans.add_cases(session, plan.id, [c.id])
    await _record(session, c.id, plan.id, "main-1", "pass", commit_id="m1", branch="main")
    await _record(session, c.id, plan.id, "main-2", "pass", commit_id="m2", branch="main")

    # precise: base_commit pins the baseline to m1 even though m2 is newer
    br = await _record(
        session, c.id, plan.id, "feat-1", "fail",
        commit_id="f1", branch="feature/x", base_commit="m1",
    )
    base = await lineage.resolve_baseline(session, await session.get(Build, br.build_id))
    assert base is not None and base.commit_id == "m1"

    # fallback: no base_commit → latest main build before this one = m2
    br2 = await _record(session, c.id, plan.id, "feat-2", "fail", commit_id="f2", branch="feature/y")
    base2 = await lineage.resolve_baseline(session, await session.get(Build, br2.build_id))
    assert base2 is not None and base2.commit_id == "m2"


@pytest.mark.asyncio
async def test_resolve_baseline_none_when_no_default_branch_builds(session):
    _, _, cases, plan = await _project_with_cases(session, "BASE0", n=1)
    c = cases[0]
    await plans.add_cases(session, plan.id, [c.id])
    # only a branch build exists; no main builds to compare against
    br = await _record(session, c.id, plan.id, "feat-1", "fail", commit_id="f1", branch="feature/x")
    base = await lineage.resolve_baseline(session, await session.get(Build, br.build_id))
    assert base is None


# ---------- compare / diff classification ----------


@pytest.mark.asyncio
async def test_compare_classifies_each_case(session):
    _, _, cases, plan = await _project_with_cases(session, "CMP", n=5)
    a, b, c, d, e = cases
    await plans.add_cases(session, plan.id, [x.id for x in cases])
    # baseline (main): a pass, b fail, c pass, e pass  (d never run)
    for cid, st in [(a.id, "pass"), (b.id, "fail"), (c.id, "pass"), (e.id, "pass")]:
        await _record(session, cid, plan.id, "main-1", st, commit_id="m1", branch="main")
    # branch build (base_commit pins baseline to main-1):
    #   a pass→fail = regression ; b fail→pass = fixed ; c pass→pass = still_passing
    #   d no baseline result = new_test ; e in baseline but not run here = removed
    br = await _record(
        session, a.id, plan.id, "feat-1", "fail",
        commit_id="f1", branch="feature/x", base_commit="m1",
    )
    await _record(session, b.id, plan.id, "feat-1", "pass", commit_id="f1", branch="feature/x")
    await _record(session, c.id, plan.id, "feat-1", "pass", commit_id="f1", branch="feature/x")
    await _record(session, d.id, plan.id, "feat-1", "pass", commit_id="f1", branch="feature/x")

    diff = await lineage.compare(session, br.build_id, "baseline")
    assert diff["baseline_build_id"] is not None
    cls = {k: {x["case_id"] for x in v} for k, v in diff["classes"].items()}
    assert a.id in cls["regression"]
    assert b.id in cls["fixed"]
    assert c.id in cls["still_passing"]
    assert d.id in cls["new_test"]  # NOT a regression — no baseline result
    assert e.id in cls["removed"]


@pytest.mark.asyncio
async def test_compare_no_baseline_all_new(session):
    _, _, cases, plan = await _project_with_cases(session, "CMP0", n=2)
    await plans.add_cases(session, plan.id, [c.id for c in cases])
    br = await _record(session, cases[0].id, plan.id, "feat-1", "fail", branch="feature/x")
    diff = await lineage.compare(session, br.build_id, "baseline")
    assert diff["baseline_build_id"] is None
    assert {x["case_id"] for x in diff["classes"]["new_test"]} == {cases[0].id}
    assert diff["classes"]["regression"] == []  # no baseline → never a regression
