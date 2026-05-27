from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import investment_forecasting.agent_runtime.execution as execution
import investment_forecasting.cli as cli_module
from investment_forecasting.agent_runtime import (
    CodexCliRuntimeAdapter,
    FakeCodexRuntimeAdapter,
    build_launch_request,
    create_or_prepare_agent_run,
    fail_agent_run,
    get_role_tool_manifest,
    jarvis_agent_readiness,
    list_runtime_agent_runs,
    render_expert_agent_prompt,
    render_jarvis_agent_prompt,
)
from investment_forecasting.agent_runtime.models import CodexRuntimePolicy
from investment_forecasting.db import connect, get_agent_run, init_db, update_agent_run
from investment_forecasting.experts.planning import run_expert_agent_plan_from_output
from investment_forecasting.experts.roster import initialize_default_experts, list_roster
from investment_forecasting.mcp.tools import call_agent_tool
from investment_forecasting.mcp.server import create_agent_mcp_server
from tests.test_jarvis import seed_jarvis_synthesis_state


def expert_launch_request():
    return build_launch_request(
        role_type="expert",
        role_key="bai_gui",
        run_date="2026-05-24",
        target_evidence_date="2026-05-24",
        trigger_reason="daily_expert_action",
        overview_skill="investment-expert-agent",
        skill_bundle=[
            "investment-market-data-skill",
            "investment-model-evidence-skill",
            "investment-news-evidence-skill",
            "investment-expert-portfolio-skill",
            "investment-virtual-action-skill",
            "investment-agent-output-contract",
        ],
        prompt_ref={"kind": "persisted", "prompt_hash": "sha256:test", "prompt_snapshot_id": 1},
        tool_manifest_ref={"kind": "inline", "manifest_hash": "sha256:tools"},
        output_contract={"schema_version": "expert_agent_output_v1", "submission_tool": "submit_expert_virtual_action"},
        runtime_policy=CodexRuntimePolicy(timeout_seconds=600, max_tool_calls=20, max_retries=1),
    )


def jarvis_launch_request():
    return build_launch_request(
        role_type="jarvis",
        role_key="jarvis",
        run_date="2026-05-25",
        target_evidence_date="2026-05-24",
        trigger_reason="daily_jarvis_analysis",
        overview_skill="jarvis-daily-agent",
        skill_bundle=[
            "investment-market-data-skill",
            "investment-expert-evidence-skill",
            "investment-jarvis-synthesis-skill",
            "investment-agent-output-contract",
        ],
        prompt_ref={"kind": "persisted", "prompt_hash": "sha256:jarvis"},
        tool_manifest_ref={"kind": "inline", "manifest_hash": "sha256:jarvis-tools"},
        output_contract={"schema_version": "jarvis_agent_output_v1", "submission_tool": "submit_jarvis_daily_brief"},
    )


def test_build_launch_request_is_serializable():
    request = expert_launch_request()

    payload = request.to_dict()
    encoded = json.dumps(payload, ensure_ascii=False)

    assert "codex_agent_runtime_v1" in encoded
    assert payload["overview_skill"] == "investment-expert-agent"
    assert payload["runtime_policy"]["timeout_seconds"] == 600
    assert payload["output_contract"]["submission_tool"] == "submit_expert_virtual_action"


def test_create_and_complete_expert_agent_run_with_fake_adapter(tmp_path):
    db_path = init_db(tmp_path / "agent.sqlite3")
    adapter = FakeCodexRuntimeAdapter(db_path, output={"submission_id": 42})

    prepared = adapter.prepare_run(expert_launch_request())
    running = adapter.start_run(prepared.agent_run_id)
    result = adapter.collect_result(prepared.agent_run_id)

    assert prepared.status == "pending"
    assert running.status == "running"
    assert result.status == "completed"
    with connect(db_path) as conn:
        row = get_agent_run(conn, prepared.agent_run_id)
        launch_request = json.loads(row["launch_request_json"])
    assert launch_request["agent_run_id"] == prepared.agent_run_id
    assert launch_request["skill_bundle"][0] == "investment-market-data-skill"


def test_create_and_fail_jarvis_agent_run(tmp_path):
    db_path = init_db(tmp_path / "jarvis_agent.sqlite3")
    handle = create_or_prepare_agent_run(db_path, jarvis_launch_request())

    result = fail_agent_run(db_path, handle.agent_run_id, error="expert evidence incomplete")

    assert result.status == "failed"
    assert result.failure_reason == "expert evidence incomplete"


def test_duplicate_agent_run_creation_is_idempotent(tmp_path):
    db_path = init_db(tmp_path / "idempotent.sqlite3")
    request = expert_launch_request()

    first = create_or_prepare_agent_run(db_path, request)
    second = create_or_prepare_agent_run(db_path, request)

    assert first.agent_run_id == second.agent_run_id
    rows = list_runtime_agent_runs(db_path, role_type="expert")
    assert len(rows) == 1


def test_fake_adapter_timeout_and_cancel_paths(tmp_path):
    db_path = init_db(tmp_path / "timeout.sqlite3")
    timeout_adapter = FakeCodexRuntimeAdapter(db_path, terminal_status="timed_out")
    prepared = timeout_adapter.prepare_run(expert_launch_request())
    timeout_adapter.start_run(prepared.agent_run_id)

    timed_out = timeout_adapter.collect_result(prepared.agent_run_id)
    assert timed_out.status == "timed_out"

    cancel_adapter = FakeCodexRuntimeAdapter(db_path)
    jarvis = cancel_adapter.prepare_run(jarvis_launch_request())
    cancel_adapter.start_run(jarvis.agent_run_id)
    cancelled = cancel_adapter.cancel_run(jarvis.agent_run_id, "manual stop")
    assert cancelled.status == "cancelled"


class DummyProcess:
    pid = 4242


def test_codex_cli_adapter_prepares_project_artifacts_and_command(tmp_path):
    db_path = init_db(tmp_path / "codex_cli.sqlite3")
    commands = []

    def fake_runner(command, **kwargs):
        commands.append((command, kwargs))
        return DummyProcess()

    adapter = CodexCliRuntimeAdapter(
        db_path,
        project_root=tmp_path,
        codex_bin="codex",
        runner=fake_runner,
        completed_runner=lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout="Logged in using ChatGPT", stderr=""),
    )

    prepared = adapter.prepare_run(expert_launch_request(), prompt="专家运行提示")
    running = adapter.start_run(prepared.agent_run_id)

    assert running.status == "running"
    with connect(db_path) as conn:
        row = get_agent_run(conn, prepared.agent_run_id)
        metadata = json.loads(row["runtime_metadata_json"])
    paths = metadata["artifact_paths"]
    assert paths["run_dir"].endswith(f"data/agent_runtime/runs/{prepared.agent_run_id}")
    assert paths["prompt_md"].endswith("prompt.md")
    assert "sha256:" in metadata["prompt_hash"]
    command = commands[0][0]
    assert command[:5] == ["codex", "--cd", str(tmp_path), "--ask-for-approval", "never"]
    assert "--sandbox" in command
    assert "workspace-write" in command
    assert "--json" in command
    assert any(value.startswith("mcp_servers.investment_forecasting_agent.command=") for value in command)
    assert any(value.startswith("mcp_servers.investment_forecasting_agent.args=") for value in command)
    assert "--role-scoped" in " ".join(command)
    assert str(prepared.agent_run_id) in " ".join(command)
    assert command[-1] == "专家运行提示"


def test_codex_cli_adapter_clears_stale_output_artifacts_on_prepare(tmp_path):
    db_path = init_db(tmp_path / "codex_cli_stale.sqlite3")
    adapter = CodexCliRuntimeAdapter(
        db_path,
        project_root=tmp_path,
        codex_bin="codex",
        runner=lambda *args, **kwargs: DummyProcess(),
        completed_runner=lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout="Logged in using ChatGPT", stderr=""),
    )

    prepared = adapter.prepare_run(expert_launch_request(), prompt="first")
    with connect(db_path) as conn:
        row = get_agent_run(conn, prepared.agent_run_id)
        paths = json.loads(row["runtime_metadata_json"])["artifact_paths"]
    for name in ("last_message", "events_jsonl", "stderr_log", "result_json"):
        path = paths[name]
        open(path, "w", encoding="utf-8").write("stale")

    adapter.prepare_run(expert_launch_request(), prompt="second")

    for name in ("last_message", "events_jsonl", "stderr_log", "result_json"):
        assert open(paths[name], encoding="utf-8").read() == ""


def test_codex_cli_readiness_checks_binary_and_login(tmp_path):
    db_path = init_db(tmp_path / "readiness.sqlite3")
    adapter = CodexCliRuntimeAdapter(
        db_path,
        project_root=tmp_path,
        codex_bin="codex",
        completed_runner=lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout="Logged in using ChatGPT", stderr=""),
    )

    readiness = adapter.readiness()

    assert readiness["ok"] is True
    assert readiness["login"]["ok"] is True


def test_role_tool_manifests_are_bounded_and_distinct():
    expert = get_role_tool_manifest("expert", "bai_gui").to_dict()
    jarvis = get_role_tool_manifest("jarvis", "jarvis").to_dict()

    assert "submit_expert_virtual_action" in expert["tools"]["submission"]
    assert "submit_jarvis_daily_brief" not in expert["tools"]["allowed"]
    assert "submit_jarvis_daily_brief" in jarvis["tools"]["submission"]
    assert expert["skill_bundle"] != jarvis["skill_bundle"]
    for forbidden in ("shell", "sql", "webui_scrape", "live_trade", "send_outbound_message"):
        assert forbidden in expert["tools"]["forbidden"]
        assert forbidden in jarvis["tools"]["forbidden"]


def test_agent_mcp_server_exposes_only_role_scoped_subset(tmp_path):
    db_path = init_db(tmp_path / "agent_mcp.sqlite3")
    handle = create_or_prepare_agent_run(db_path, expert_launch_request())
    server = create_agent_mcp_server(db_path, agent_run_id=handle.agent_run_id, role_type="expert", role_key="bai_gui")

    import anyio

    async def tool_names():
        tools = await server.list_tools()
        return {tool.name for tool in tools}

    names = anyio.run(tool_names)

    assert "get_asset_list" in names
    assert "submit_expert_virtual_action" in names
    assert "submit_jarvis_daily_brief" not in names
    assert "run_forecast" not in names
    assert "send_outbound_message" not in names


def test_agent_tool_call_requires_running_role_and_audits_rejections(tmp_path):
    db_path = init_db(tmp_path / "manifest.sqlite3")
    handle = create_or_prepare_agent_run(db_path, expert_launch_request())
    with connect(db_path) as conn:
        update_agent_run(conn, handle.agent_run_id, status="running")

    rejected = call_agent_tool(
        db_path,
        "submit_jarvis_daily_brief",
        {"agent_run_id": handle.agent_run_id, "role_type": "expert", "role_key": "bai_gui", "idempotency_key": "bad-1"},
    )

    assert rejected["ok"] is False
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM agent_tool_calls WHERE agent_run_id = ?", (handle.agent_run_id,)).fetchone()
    assert row["status"] == "rejected"
    assert row["tool_name"] == "submit_jarvis_daily_brief"


def test_agent_tool_call_allows_manifest_tool_and_records_result(tmp_path):
    db_path = init_db(tmp_path / "allowed_tool.sqlite3")
    handle = create_or_prepare_agent_run(db_path, expert_launch_request())
    with connect(db_path) as conn:
        update_agent_run(conn, handle.agent_run_id, status="running")

    result = call_agent_tool(
        db_path,
        "get_agent_tool_manifest",
        {"agent_run_id": handle.agent_run_id, "role_type": "expert", "role_key": "bai_gui"},
    )

    assert result["ok"] is True
    assert "submit_expert_virtual_action" in result["result"]["tools"]["allowed"]
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM agent_tool_calls WHERE agent_run_id = ?", (handle.agent_run_id,)).fetchone()
    assert row["status"] == "allowed"


def test_submission_tools_require_idempotency_key(tmp_path):
    db_path = init_db(tmp_path / "submission_key.sqlite3")
    handle = create_or_prepare_agent_run(db_path, expert_launch_request())
    with connect(db_path) as conn:
        update_agent_run(conn, handle.agent_run_id, status="running")

    missing_key = call_agent_tool(
        db_path,
        "submit_expert_virtual_action",
        {"agent_run_id": handle.agent_run_id, "role_type": "expert", "role_key": "bai_gui", "payload": {"action": "hold"}},
    )
    submitted = call_agent_tool(
        db_path,
        "submit_expert_virtual_action",
        {
            "agent_run_id": handle.agent_run_id,
            "role_type": "expert",
            "role_key": "bai_gui",
            "idempotency_key": "expert-action-1",
            "payload": {"action": "hold"},
        },
    )

    assert missing_key["ok"] is False
    assert submitted["ok"] is True
    assert submitted["result"]["accepted"] is True


def test_expert_prompt_renders_required_runtime_sections(tmp_path):
    db_path = init_db(tmp_path / "prompt.sqlite3")
    initialize_default_experts(db_path)

    rendered = render_expert_agent_prompt(db_path, expert_key="bai_gui", target_date="2026-05-24")

    prompt = rendered["prompt"]
    assert "investment-market-data-skill" in prompt
    assert "submit_expert_virtual_action" in prompt
    assert "Do not run shell commands" in prompt
    assert "evidence_ids" in json.dumps(rendered["output_schema"], ensure_ascii=False)
    assert rendered["prompt_ref"]["template"] == "expert_agent_prompt_v1"


def test_jarvis_readiness_blocks_pending_expert_agent_runs(tmp_path):
    db_path = init_db(tmp_path / "readiness-gate.sqlite3")
    experts = initialize_default_experts(db_path)

    blocked = jarvis_agent_readiness(db_path, "2026-05-24")
    assert blocked["ready"] is False
    assert set(blocked["pending"]) == {expert["expert_key"] for expert in experts}

    for expert in experts:
        request = build_launch_request(
            role_type="expert",
            role_key=expert["expert_key"],
            run_date="2026-05-24",
            target_evidence_date="2026-05-24",
            trigger_reason="expert_agent_daily_execution",
            overview_skill="investment-expert-agent",
            skill_bundle=get_role_tool_manifest("expert", expert["expert_key"]).skill_bundle,
            prompt_ref={"kind": "test", "prompt_hash": f"sha256:{expert['expert_key']}"},
            tool_manifest_ref={"kind": "inline", "manifest_hash": "sha256:test"},
            output_contract={"schema_version": "expert_agent_output_v1", "submission_tool": "submit_expert_virtual_action"},
        )
        handle = create_or_prepare_agent_run(db_path, request)
        with connect(db_path) as conn:
            update_agent_run(conn, handle.agent_run_id, status="completed")

    ready = jarvis_agent_readiness(db_path, "2026-05-24")
    assert ready["ready"] is True
    assert ready["status"] == "complete"
    assert ready["upstream_evidence_status"]["ready"] is False
    assert "model_post_close" in ready["upstream_evidence_status"]["missing_jobs"]


def test_jarvis_readiness_reports_real_upstream_scheduler_evidence(tmp_path):
    db_path = init_db(tmp_path / "readiness-upstream.sqlite3")
    experts = initialize_default_experts(db_path)
    for expert in experts:
        request = build_launch_request(
            role_type="expert",
            role_key=expert["expert_key"],
            run_date="2026-05-25",
            target_evidence_date="2026-05-25",
            trigger_reason="expert_agent_daily_execution",
            overview_skill="investment-expert-agent",
            skill_bundle=get_role_tool_manifest("expert", expert["expert_key"]).skill_bundle,
            prompt_ref={"kind": "test", "prompt_hash": f"sha256:{expert['expert_key']}"},
            tool_manifest_ref={"kind": "inline", "manifest_hash": "sha256:test"},
            output_contract={"schema_version": "expert_agent_output_v1", "submission_tool": "submit_expert_virtual_action"},
        )
        handle = create_or_prepare_agent_run(db_path, request)
        with connect(db_path) as conn:
            update_agent_run(conn, handle.agent_run_id, status="completed")
    with connect(db_path) as conn:
        scheduler_rows = [
            ("news_hourly_incremental", '{"real_provider_calls": true}'),
            ("market_context_intraday", '{"real_provider_calls": true}'),
            ("price_nav_post_close", '{"real_provider_calls": true}'),
            ("features_post_close", '{"real_calculation": true}'),
            ("model_post_close", '{"real_model_run": true}'),
        ]
        for index, (job_key, metadata) in enumerate(scheduler_rows, start=1):
            conn.execute(
                """
                INSERT INTO scheduler_runs(job_key, scheduled_at, started_at, finished_at, status, metadata_json)
                VALUES (?, '2026-05-25T18:00:00', ?, ?, 'success', ?)
                """,
                (job_key, f"2026-05-25 18:00:0{index}", f"2026-05-25 18:00:1{index}", metadata),
            )

    ready = jarvis_agent_readiness(db_path, "2026-05-25")

    assert ready["ready"] is True
    assert ready["upstream_evidence_status"] == {
        "ready": True,
        "missing_jobs": [],
        "not_success_jobs": [],
        "readiness_only_jobs": [],
    }


def test_expert_agent_output_persists_plan_with_agent_run_evidence(tmp_path):
    db_path = seed_jarvis_synthesis_state(tmp_path)
    expert = next(item for item in list_roster(db_path, lifecycle_state="active") if item["expert_key"] == "bai_gui")
    request = expert_launch_request()
    handle = create_or_prepare_agent_run(db_path, request)
    output = {
        "status": "ok",
        "role": "expert",
        "role_key": expert["expert_key"],
        "outcome": "plan_action",
        "summary": "保持观察，等待证据更充分。",
        "action": "no_trade",
        "reason": "模型证据仍需验证。",
        "analysis": "本轮只把模型和组合信息作为研究辅助。",
        "reflection": "避免在样本不足时扩大暴露。",
        "risk_note": "仅供本地研究辅助，不构成真实投资建议。",
        "evidence_ids": ["prediction:1"],
        "news_evidence_ids": [],
    }

    plan = run_expert_agent_plan_from_output(
        db_path,
        plan_date="2026-05-23",
        expert_key=expert["expert_key"],
        agent_run_id=handle.agent_run_id,
        agent_output=output,
    )

    assert plan["evidence"]["agent_run_id"] == handle.agent_run_id
    assert plan["evidence"]["agent_output"]["role_key"] == "bai_gui"


def test_jarvis_prompt_includes_readiness_and_safe_manifest(tmp_path):
    db_path = init_db(tmp_path / "jarvis-prompt.sqlite3")
    readiness = {"ready": True, "status": "complete", "statuses": {"bai_gui": "completed"}}

    rendered = render_jarvis_agent_prompt(
        db_path,
        run_date="2026-05-25",
        target_evidence_date="2026-05-24",
        readiness=readiness,
    )

    prompt = rendered["prompt"]
    assert "Jarvis" in prompt
    assert "submit_jarvis_daily_brief" in prompt
    assert "submit_expert_virtual_action" not in rendered["manifest"]["tools"]["allowed"]
    assert rendered["prompt_ref"]["template"] == "jarvis_agent_prompt_v1"


def test_jarvis_agent_task_uses_environment_notification_defaults(tmp_path, monkeypatch):
    db_path = init_db(tmp_path / "jarvis-agent-notify.sqlite3")
    monkeypatch.setenv("INVESTMENT_FORECASTING_NOTIFY_RECIPIENT_KEY", "owner_phone")
    monkeypatch.setenv("INVESTMENT_FORECASTING_NOTIFICATION_DRY_RUN", "true")
    captured: dict[str, object] = {}

    class FakeJarvisAdapter:
        def __init__(self, db_path, **kwargs):
            self.db_path = db_path

        def readiness(self):
            return {"ok": True}

        def prepare_run(self, request, **kwargs):
            handle = create_or_prepare_agent_run(self.db_path, request)
            with connect(self.db_path) as conn:
                update_agent_run(conn, handle.agent_run_id, status="running")
            return handle

        def start_run(self, agent_run_id):
            return SimpleNamespace(agent_run_id=agent_run_id, status="running")

    def fake_wait_for_artifact(*args, **kwargs):
        return {
            "ok": True,
            "agent_run_id": args[2],
            "status": "completed_via_artifact",
            "output": {"status": "ok", "outcome": "daily_brief"},
            "artifact_paths": {},
        }

    def fake_generate_jarvis_brief(*args, **kwargs):
        captured.update(kwargs)
        return {"id": 42, "notification": {"status": "dry_run", "template_key": "jarvis_daily_summary"}}

    monkeypatch.setattr(execution, "CodexCliRuntimeAdapter", FakeJarvisAdapter)
    monkeypatch.setattr(execution, "jarvis_agent_readiness", lambda db_path, target_evidence_date: {"ready": True, "status": "complete"})
    monkeypatch.setattr(execution, "_wait_for_artifact", fake_wait_for_artifact)
    monkeypatch.setattr(execution, "generate_jarvis_brief", fake_generate_jarvis_brief)

    result = execution.run_jarvis_codex_agent(db_path, run_date="2026-05-25", target_evidence_date="2026-05-24")

    assert result["ok"] is True
    assert result["runs"][0]["notification"]["status"] == "dry_run"
    assert captured["notify_recipient_key"] == "owner_phone"
    assert captured["notification_channel"] == "imessage"
    assert captured["notification_dry_run"] is True


def test_jarvis_codex_cli_passes_notification_arguments(tmp_path, monkeypatch, capsys):
    db_path = init_db(tmp_path / "jarvis-cli-notify.sqlite3")
    captured: dict[str, object] = {}

    def fake_run_jarvis_codex_agent(*args, **kwargs):
        captured["db_path"] = args[0]
        captured.update(kwargs)
        return {"ok": True, "run_date": "2026-05-26", "runs": []}

    monkeypatch.setattr(cli_module, "run_jarvis_codex_agent", fake_run_jarvis_codex_agent)

    result = cli_module.main(
        [
            "agent-runs",
            "run-jarvis-codex",
            "--db",
            str(db_path),
            "--date",
            "2026-05-26",
            "--target-evidence-date",
            "2026-05-25",
            "--notify-recipient-key",
            "owner_phone",
            "--notification-channel",
            "imessage",
            "--notification-dry-run",
        ]
    )

    assert result == 0
    assert captured["db_path"] == db_path
    assert captured["notify_recipient_key"] == "owner_phone"
    assert captured["notification_channel"] == "imessage"
    assert captured["notification_dry_run"] is True
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_expert_codex_cli_does_not_require_notification_arguments(tmp_path, monkeypatch):
    db_path = init_db(tmp_path / "expert-cli.sqlite3")
    captured: dict[str, object] = {}

    def fake_run_expert_codex_agents(*args, **kwargs):
        captured["db_path"] = args[0]
        captured.update(kwargs)
        return {"ok": True, "run_date": "2026-05-26", "runs": []}

    monkeypatch.setattr(cli_module, "run_expert_codex_agents", fake_run_expert_codex_agents)

    result = cli_module.main(
        [
            "agent-runs",
            "run-experts-codex",
            "--db",
            str(db_path),
            "--date",
            "2026-05-26",
            "--project-root",
            str(tmp_path),
        ]
    )

    assert result == 0
    assert captured["db_path"] == db_path
    assert captured["run_date"] == "2026-05-26"
    assert captured["project_root"] == tmp_path
    assert "notify_recipient_key" not in captured
