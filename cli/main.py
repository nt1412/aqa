import json
import os
from pathlib import Path

import httpx
import typer


def _env(key: str, default=None):
    """Read AQA_* env, falling back to the legacy AGENTQA_* name (rename compat)."""
    v = os.environ.get(key)
    if v is None:
        v = os.environ.get(key.replace("AQA_", "AGENTQA_", 1))
    return v if v is not None else default


app = typer.Typer(help="AQA CLI")
project_app = typer.Typer(help="Manage projects")
suite_app = typer.Typer(help="Manage suites")
case_app = typer.Typer(help="Manage test cases")
run_app = typer.Typer(help="Record/inspect executions")
plan_app = typer.Typer(help="Manage test plans")
build_app = typer.Typer(help="Manage builds")
milestone_app = typer.Typer(help="Manage milestones")
assign_app = typer.Typer(help="Manage assignments")
evidence_app = typer.Typer(help="Evidence & artifacts")
claim_app = typer.Typer(help="Claims & verification")
context_app = typer.Typer(help="Self-correction context")
req_app = typer.Typer(help="Requirements & coverage")
agent_app = typer.Typer(help="Agent identities")
app.add_typer(project_app, name="project")
app.add_typer(suite_app, name="suite")
app.add_typer(case_app, name="case")
app.add_typer(run_app, name="run")
app.add_typer(plan_app, name="plan")
app.add_typer(build_app, name="build")
app.add_typer(milestone_app, name="milestone")
app.add_typer(assign_app, name="assign")
app.add_typer(evidence_app, name="evidence")
app.add_typer(claim_app, name="claim")
app.add_typer(context_app, name="context")
app.add_typer(req_app, name="req")
app.add_typer(agent_app, name="agent")


def _request(method: str, path: str, *, json_body=None, params=None) -> dict:
    base = _env("AQA_API_URL", "http://localhost:8000")
    headers = {}
    api_key = _env("AQA_API_KEY")
    if api_key:
        headers["X-API-Key"] = api_key
    resp = httpx.request(method, base + path, headers=headers, json=json_body, params=params)
    resp.raise_for_status()
    return resp.json()


def _print(data) -> None:
    typer.echo(json.dumps(data, indent=2, default=str))


@project_app.command("list")
def project_list():
    _print(_request("GET", "/api/v1/projects"))


@project_app.command("create")
def project_create(name: str, prefix: str = typer.Option(..., "--prefix")):
    _print(_request("POST", "/api/v1/projects", json_body={"name": name, "prefix": prefix}))


@project_app.command("get")
def project_get(project_id: int):
    _print(_request("GET", f"/api/v1/projects/{project_id}"))


@suite_app.command("create")
def suite_create(
    project_id: int,
    name: str = typer.Option(..., "--name"),
    parent: int | None = typer.Option(None, "--parent"),
):
    _print(
        _request(
            "POST",
            f"/api/v1/projects/{project_id}/suites",
            json_body={"name": name, "parent_id": parent},
        )
    )


@suite_app.command("tree")
def suite_tree(suite_id: int):
    _print(_request("GET", f"/api/v1/suites/{suite_id}/tree"))


@case_app.command("create")
def case_create(
    suite_id: int,
    name: str = typer.Option(None, "--name"),
    from_file: Path = typer.Option(None, "--from-file"),  # noqa: B008
):
    if from_file:
        body = json.loads(from_file.read_text())
    elif name:
        body = {"name": name}
    else:
        raise typer.BadParameter("provide --name or --from-file")
    _print(_request("POST", f"/api/v1/suites/{suite_id}/cases", json_body=body))


@case_app.command("get")
def case_get(case_id: int):
    _print(_request("GET", f"/api/v1/cases/{case_id}"))


@case_app.command("depends")
def case_depends(case_id: int, on: int = typer.Option(..., "--on")):
    """Record that this case depends on another (a prerequisite, for run gating)."""
    _print(
        _request(
            "POST",
            f"/api/v1/cases/{case_id}/dependencies",
            json_body={"depends_on_case_id": on},
        )
    )


@run_app.command("record")
def run_record(
    case_id: int,
    plan: int = typer.Option(..., "--plan"),
    build: str = typer.Option(..., "--build"),
    status: str = typer.Option(..., "--status"),
    from_file: Path = typer.Option(None, "--steps-file"),  # noqa: B008
    notes: str = typer.Option(None, "--notes"),
    commit: str = typer.Option(None, "--commit"),
    branch: str = typer.Option(None, "--branch"),
    base_commit: str = typer.Option(None, "--base-commit"),
    cascade: bool = typer.Option(False, "--cascade/--no-cascade"),
):
    body = {"case_id": case_id, "plan_id": plan, "build_name": build, "status": status}
    if from_file:
        body["step_results"] = json.loads(from_file.read_text())
    if notes:
        body["notes"] = notes
    if commit:
        body["commit_id"] = commit
    if branch:
        body["branch"] = branch
    if base_commit:
        body["base_commit"] = base_commit
    _print(_request("POST", "/api/v1/executions", json_body=body, params={"cascade": cascade}))


@run_app.command("list")
def run_list(case: int = typer.Option(..., "--case")):
    _print(_request("GET", f"/api/v1/cases/{case}/executions"))


@build_app.command("timeline")
def build_timeline(plan_id: int):
    """Builds for a plan, newest first, each with its pass/fail/blocked/not_run rollup."""
    _print(_request("GET", f"/api/v1/plans/{plan_id}/build-timeline"))


@build_app.command("detail")
def build_detail(build_id: int):
    """Build header + rollup + each case's latest result in the build."""
    _print(_request("GET", f"/api/v1/builds/{build_id}"))


@case_app.command("history")
def case_history(case_id: int):
    """A case's latest result per build, chronological, with broke/fixed transitions."""
    _print(_request("GET", f"/api/v1/cases/{case_id}/history"))


@build_app.command("compare")
def build_compare(build_id: int, to: str = typer.Option("baseline", "--to")):
    """Diff a build vs another build (--to <id>) or its baseline (--to baseline)."""
    _print(_request("GET", f"/api/v1/builds/{build_id}/compare", params={"to": to}))


@plan_app.command("create")
def plan_create(project_id: int, name: str = typer.Option(..., "--name")):
    _print(_request("POST", f"/api/v1/projects/{project_id}/plans", json_body={"name": name}))


@plan_app.command("list")
def plan_list(project_id: int):
    _print(_request("GET", f"/api/v1/projects/{project_id}/plans"))


@plan_app.command("add-case")
def plan_add_case(
    plan_id: int,
    case: int = typer.Option(..., "--case"),
    urgency: int = typer.Option(2, "--urgency"),
):
    _print(
        _request(
            "POST",
            f"/api/v1/plans/{plan_id}/cases",
            json_body={"case_ids": [case], "urgency": urgency},
        )
    )


@plan_app.command("manifest")
def plan_manifest(plan_id: int, build: int = typer.Option(None, "--build")):
    """Ordered, dependency-gated run list. --build scopes gating to one build."""
    params = {"build_id": build} if build else None
    _print(_request("GET", f"/api/v1/plans/{plan_id}/manifest", params=params))


@build_app.command("create")
def build_create(
    plan_id: int,
    name: str = typer.Option(..., "--name"),
    tag: str = typer.Option(None, "--tag"),
    commit: str = typer.Option(None, "--commit"),
):
    body = {"name": name}
    if tag:
        body["tag"] = tag
    if commit:
        body["commit_id"] = commit
    _print(_request("POST", f"/api/v1/plans/{plan_id}/builds", json_body=body))


@build_app.command("list")
def build_list(plan_id: int):
    _print(_request("GET", f"/api/v1/plans/{plan_id}/builds"))


@milestone_app.command("create")
def milestone_create(plan_id: int, name: str = typer.Option(..., "--name")):
    _print(_request("POST", f"/api/v1/plans/{plan_id}/milestones", json_body={"name": name}))


@assign_app.command("create")
def assign_create(
    case_id: int,
    plan: int = typer.Option(..., "--plan"),
    to: int = typer.Option(..., "--to"),
    type_: str = typer.Option("human", "--type"),
):
    _print(
        _request(
            "POST",
            "/api/v1/assignments",
            json_body={
                "case_id": case_id,
                "plan_id": plan,
                "assignee_id": to,
                "assignee_type": type_,
            },
        )
    )


@assign_app.command("list")
def assign_list(
    plan: int = typer.Option(None, "--plan"),
    assignee: int = typer.Option(None, "--assignee"),
):
    params = {}
    if plan is not None:
        params["plan_id"] = plan
    if assignee is not None:
        params["assignee_id"] = assignee
    _print(_request("GET", "/api/v1/assignments", params=params))


@evidence_app.command("bundle")
def evidence_bundle(case_id: int):
    _print(_request("GET", f"/api/v1/cases/{case_id}/evidence"))


@claim_app.command("unverified")
def claim_unverified(plan: int = typer.Option(None, "--plan")):
    params = {"plan_id": plan} if plan is not None else None
    _print(_request("GET", "/api/v1/claims/unverified", params=params))


@claim_app.command("verify")
def claim_verify(claim_id: int, verdict: str = typer.Option(..., "--verdict")):
    _print(_request("POST", f"/api/v1/claims/{claim_id}/verify", json_body={"verdict": verdict}))


@context_app.command("failure")
def context_failure(case_id: int, plan: int = typer.Option(None, "--plan")):
    params = {"plan_id": plan} if plan is not None else None
    _print(_request("GET", f"/api/v1/cases/{case_id}/failure-context", params=params))


@context_app.command("similar")
def context_similar(case_id: int, n: int = typer.Option(5, "--n")):
    _print(_request("GET", f"/api/v1/cases/{case_id}/similar-failures", params={"n": n}))


@req_app.command("spec-create")
def req_spec_create(
    project_id: int,
    doc_id: str = typer.Option(..., "--doc-id"),
    name: str = typer.Option(..., "--name"),
):
    _print(
        _request(
            "POST",
            f"/api/v1/projects/{project_id}/req-specs",
            json_body={"doc_id": doc_id, "name": name},
        )
    )


@req_app.command("create")
def req_create(
    spec_id: int,
    doc_id: str = typer.Option(..., "--doc-id"),
    name: str = typer.Option(..., "--name"),
):
    _print(
        _request(
            "POST",
            f"/api/v1/req-specs/{spec_id}/requirements",
            json_body={"req_doc_id": doc_id, "name": name},
        )
    )


@req_app.command("link-coverage")
def req_link_coverage(
    req_id: int,
    case: list[int] = typer.Option(..., "--case", help="case id (repeatable)"),  # noqa: B008
):
    """Link a requirement to test cases as coverage (after the requirement exists)."""
    _print(
        _request(
            "POST",
            f"/api/v1/requirements/{req_id}/coverage",
            json_body={"case_ids": case},
        )
    )


@req_app.command("gaps")
def req_gaps(project_id: int):
    _print(_request("GET", f"/api/v1/projects/{project_id}/coverage-gaps"))


@req_app.command("traceability")
def req_traceability(project_id: int):
    _print(_request("GET", f"/api/v1/projects/{project_id}/traceability"))


@agent_app.command("register")
def agent_register(
    login: str = typer.Option(..., "--login"),
    model: str = typer.Option(None, "--model"),
    email: str = typer.Option(None, "--email"),
    name: str = typer.Option(None, "--name"),
):
    """Create an agent identity; prints a one-time API key. Pass the returned
    id as the tester for attributable runs."""
    body = {"login": login, "agent_model": model, "email": email, "display_name": name}
    _print(_request("POST", "/api/v1/users/register-agent", json_body=body))


@agent_app.command("list")
def agent_list():
    """List agent identities (find probe/stale ones to clean up)."""
    _print(_request("GET", "/api/v1/users/agents"))


@agent_app.command("deactivate")
def agent_deactivate(user_id: int):
    """Soft-delete an agent identity (mark inactive); its recorded work stays."""
    _print(_request("DELETE", f"/api/v1/users/{user_id}"))


if __name__ == "__main__":
    app()
