import json

from typer.testing import CliRunner

from cli import main as cli

runner = CliRunner()


def test_request_builds_url_and_headers(monkeypatch):
    captured = {}

    class FakeResp:
        status_code = 200

        def json(self):
            return {"ok": True}

        def raise_for_status(self):
            pass

    def fake_request(method, url, headers=None, json=None, params=None):
        captured.update(method=method, url=url, headers=headers, json=json, params=params)
        return FakeResp()

    monkeypatch.setattr(cli.httpx, "request", fake_request)
    monkeypatch.setenv("AQA_API_URL", "http://x:8000")
    monkeypatch.setenv("AQA_API_KEY", "aqa_test")
    out = cli._request("GET", "/api/v1/projects")
    assert out == {"ok": True}
    assert captured["url"] == "http://x:8000/api/v1/projects"
    assert captured["headers"]["X-API-Key"] == "aqa_test"


def test_project_create_invokes_post(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_request", lambda m, p, **k: calls.append((m, p, k)) or {"id": 1})
    result = runner.invoke(cli.app, ["project", "create", "Demo", "--prefix", "DEMO"])
    assert result.exit_code == 0
    assert calls[0][0] == "POST"
    assert calls[0][1] == "/api/v1/projects"


def test_case_create_from_file(monkeypatch, tmp_path):
    spec = tmp_path / "case.json"
    spec.write_text(json.dumps({"name": "c", "steps": [{"action": "go"}]}))
    calls = []
    monkeypatch.setattr(cli, "_request", lambda m, p, **k: calls.append((m, p, k)) or {"id": 9})
    result = runner.invoke(cli.app, ["case", "create", "5", "--from-file", str(spec)])
    assert result.exit_code == 0
    assert calls[0][2]["json_body"]["name"] == "c"


def test_plan_create_invokes_post(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_request", lambda m, p, **k: calls.append((m, p, k)) or {"id": 1})
    result = runner.invoke(cli.app, ["plan", "create", "5", "--name", "Sprint"])
    assert result.exit_code == 0
    assert calls[0][0] == "POST"
    assert calls[0][1] == "/api/v1/projects/5/plans"
    assert calls[0][2]["json_body"]["name"] == "Sprint"


def test_build_create_invokes_post(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_request", lambda m, p, **k: calls.append((m, p, k)) or {"id": 2})
    result = runner.invoke(cli.app, ["build", "create", "7", "--name", "v1", "--commit", "abc"])
    assert result.exit_code == 0
    assert calls[0][1] == "/api/v1/plans/7/builds"
    assert calls[0][2]["json_body"]["commit_id"] == "abc"


def test_assign_create_invokes_post(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_request", lambda m, p, **k: calls.append((m, p, k)) or {"id": 3})
    result = runner.invoke(
        cli.app,
        ["assign", "create", "4", "--plan", "7", "--to", "9", "--type", "agent"],
    )
    assert result.exit_code == 0
    assert calls[0][1] == "/api/v1/assignments"
    assert calls[0][2]["json_body"]["assignee_id"] == 9


def test_claim_verify_invokes_post(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_request", lambda m, p, **k: calls.append((m, p, k)) or {"id": 1})
    result = runner.invoke(cli.app, ["claim", "verify", "5", "--verdict", "confirmed"])
    assert result.exit_code == 0
    assert calls[0][1] == "/api/v1/claims/5/verify"
    assert calls[0][2]["json_body"]["verdict"] == "confirmed"


def test_context_failure_invokes_get(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_request", lambda m, p, **k: calls.append((m, p, k)) or {})
    result = runner.invoke(cli.app, ["context", "failure", "7"])
    assert result.exit_code == 0
    assert calls[0][1] == "/api/v1/cases/7/failure-context"


def test_req_gaps_invokes_get(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_request", lambda m, p, **k: calls.append((m, p, k)) or [])
    result = runner.invoke(cli.app, ["req", "gaps", "3"])
    assert result.exit_code == 0
    assert calls[0][1] == "/api/v1/projects/3/coverage-gaps"


def test_req_link_coverage_invokes_post(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_request", lambda m, p, **k: calls.append((m, p, k)) or [{"id": 1}])
    result = runner.invoke(cli.app, ["req", "link-coverage", "42", "--case", "9", "--case", "10"])
    assert result.exit_code == 0
    assert calls[0][0] == "POST"
    assert calls[0][1] == "/api/v1/requirements/42/coverage"
    assert calls[0][2]["json_body"]["case_ids"] == [9, 10]


def test_build_timeline_invokes_get(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_request", lambda m, p, **k: calls.append((m, p, k)) or [])
    result = runner.invoke(cli.app, ["build", "timeline", "7"])
    assert result.exit_code == 0
    assert calls[0] == ("GET", "/api/v1/plans/7/build-timeline", {})


def test_build_detail_invokes_get(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_request", lambda m, p, **k: calls.append((m, p, k)) or {})
    result = runner.invoke(cli.app, ["build", "detail", "12"])
    assert result.exit_code == 0
    assert calls[0][1] == "/api/v1/builds/12"


def test_case_history_invokes_get(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_request", lambda m, p, **k: calls.append((m, p, k)) or {})
    result = runner.invoke(cli.app, ["case", "history", "5"])
    assert result.exit_code == 0
    assert calls[0][1] == "/api/v1/cases/5/history"


def test_build_compare_invokes_get(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_request", lambda m, p, **k: calls.append((m, p, k)) or {})
    result = runner.invoke(cli.app, ["build", "compare", "12", "--to", "baseline"])
    assert result.exit_code == 0
    assert calls[0][1] == "/api/v1/builds/12/compare"
    assert calls[0][2]["params"]["to"] == "baseline"


def test_run_record_passes_branch_and_base_commit(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_request", lambda m, p, **k: calls.append((m, p, k)) or {"id": 1})
    result = runner.invoke(
        cli.app,
        ["run", "record", "5", "--plan", "7", "--build", "b1", "--status", "pass",
         "--branch", "feature/x", "--base-commit", "main999"],
    )
    assert result.exit_code == 0
    assert calls[0][2]["json_body"]["branch"] == "feature/x"
    assert calls[0][2]["json_body"]["base_commit"] == "main999"


def test_agent_register_invokes_post(monkeypatch):
    calls = []
    monkeypatch.setattr(
        cli, "_request", lambda m, p, **k: calls.append((m, p, k)) or {"id": 4, "api_key": "x"}
    )
    result = runner.invoke(cli.app, ["agent", "register", "--login", "bot", "--model", "claude"])
    assert result.exit_code == 0
    assert calls[0][0] == "POST"
    assert calls[0][1] == "/api/v1/users/register-agent"
    assert calls[0][2]["json_body"]["login"] == "bot"


def test_plan_manifest_invokes_get_with_build(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_request", lambda m, p, **k: calls.append((m, p, k)) or [])
    result = runner.invoke(cli.app, ["plan", "manifest", "1", "--build", "2"])
    assert result.exit_code == 0
    assert calls[0][:2] == ("GET", "/api/v1/plans/1/manifest")
    assert calls[0][2]["params"] == {"build_id": 2}


def test_case_depends_invokes_post(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_request", lambda m, p, **k: calls.append((m, p, k)) or {})
    result = runner.invoke(cli.app, ["case", "depends", "5", "--on", "3"])
    assert result.exit_code == 0
    assert calls[0][:2] == ("POST", "/api/v1/cases/5/dependencies")
    assert calls[0][2]["json_body"] == {"depends_on_case_id": 3}


def test_run_record_cascade_param(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_request", lambda m, p, **k: calls.append((m, p, k)) or {})
    result = runner.invoke(
        cli.app,
        ["run", "record", "5", "--plan", "1", "--build", "b1", "--status", "fail", "--cascade"],
    )
    assert result.exit_code == 0
    assert calls[0][2]["params"] == {"cascade": True}


def test_agent_list_invokes_get(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_request", lambda m, p, **k: calls.append((m, p, k)) or [])
    assert runner.invoke(cli.app, ["agent", "list"]).exit_code == 0
    assert calls[0][:2] == ("GET", "/api/v1/users/agents")


def test_agent_deactivate_invokes_delete(monkeypatch):
    calls = []
    monkeypatch.setattr(cli, "_request", lambda m, p, **k: calls.append((m, p, k)) or {})
    assert runner.invoke(cli.app, ["agent", "deactivate", "6"]).exit_code == 0
    assert calls[0][:2] == ("DELETE", "/api/v1/users/6")
