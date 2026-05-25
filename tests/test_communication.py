from __future__ import annotations

import subprocess

from investment_forecasting.cli import main as cli_main
from investment_forecasting.communication.imessage import (
    IMessageAdapter,
    build_imessage_applescript,
    verify_imessage_setup,
)
from investment_forecasting.communication.service import FailingAdapter, send_outbound_message
from investment_forecasting.communication.templates import (
    render_jarvis_daily_summary,
    render_jarvis_weekly_summary,
    render_provider_warning,
    send_rendered_notification,
)
from investment_forecasting.db import (
    connect,
    init_db,
    upsert_communication_adapter_config,
    upsert_communication_recipient,
)


def test_dry_run_persists_outbound_message(tmp_path):
    db_path = tmp_path / "communication.sqlite3"
    init_db(db_path)
    with connect(db_path) as conn:
        seed_adapter_and_recipient(conn)

        message = send_outbound_message(
            conn,
            channel="imessage",
            recipient_key="owner_phone",
            template_key="daily_summary",
            subject="Daily research",
            body="今日研究摘要，仅供研究参考，不构成投资建议。",
            payload_summary="daily brief",
            idempotency_key="daily:2026-05-23",
            dry_run=True,
        )

        row = conn.execute("SELECT * FROM outbound_messages WHERE id = ?", (message["id"],)).fetchone()

    assert message["status"] == "dry_run"
    assert message["duplicate"] is False
    assert row["status"] == "dry_run"
    assert row["recipient_key"] == "owner_phone"
    assert row["idempotency_key"] == "daily:2026-05-23"


def test_allowlist_rejection_happens_before_adapter_execution(tmp_path):
    db_path = tmp_path / "communication.sqlite3"
    init_db(db_path)
    with connect(db_path) as conn:
        upsert_communication_adapter_config(conn, {"channel": "imessage", "enabled": 1, "dry_run_default": 0})
        upsert_communication_recipient(
            conn,
            {
                "recipient_key": "blocked",
                "display_name": "Blocked",
                "channel": "imessage",
                "address": "+10000000000",
                "allowlisted": 0,
            },
        )

        message = send_outbound_message(
            conn,
            channel="imessage",
            recipient_key="blocked",
            template_key="alert",
            body="运行失败提醒，仅供研究系统排障。",
            dry_run=False,
            adapter=FailingAdapter("should not execute"),
        )

    assert message["status"] == "recipient_not_allowed"
    assert "should not execute" not in (message["error"] or "")


def test_idempotency_key_does_not_send_duplicate_messages(tmp_path):
    db_path = tmp_path / "communication.sqlite3"
    init_db(db_path)
    with connect(db_path) as conn:
        seed_adapter_and_recipient(conn)
        first = send_outbound_message(
            conn,
            channel="imessage",
            recipient_key="owner_phone",
            template_key="daily_summary",
            body="今日研究摘要，仅供研究参考。",
            idempotency_key="same-key",
            dry_run=True,
        )
        second = send_outbound_message(
            conn,
            channel="imessage",
            recipient_key="owner_phone",
            template_key="daily_summary",
            body="今日研究摘要，仅供研究参考。",
            idempotency_key="same-key",
            dry_run=True,
        )
        count = conn.execute("SELECT COUNT(*) AS count FROM outbound_messages").fetchone()["count"]

    assert first["id"] == second["id"]
    assert second["duplicate"] is True
    assert count == 1


def test_failed_adapter_result_is_persisted(tmp_path):
    db_path = tmp_path / "communication.sqlite3"
    init_db(db_path)
    with connect(db_path) as conn:
        seed_adapter_and_recipient(conn, dry_run_default=0)

        message = send_outbound_message(
            conn,
            channel="imessage",
            recipient_key="owner_phone",
            template_key="alert",
            body="运行失败提醒，仅供研究系统排障。",
            dry_run=False,
            adapter=FailingAdapter("Messages permission missing"),
        )
        row = conn.execute("SELECT * FROM outbound_messages WHERE id = ?", (message["id"],)).fetchone()

    assert message["status"] == "failed"
    assert row["status"] == "failed"
    assert row["error"] == "Messages permission missing"


def test_imessage_dry_run_does_not_invoke_messages(tmp_path):
    db_path = tmp_path / "communication.sqlite3"
    init_db(db_path)

    def fail_runner(*args, **kwargs):
        raise AssertionError("dry run should not execute osascript")

    with connect(db_path) as conn:
        seed_adapter_and_recipient(conn, dry_run_default=0)
        message = send_outbound_message(
            conn,
            channel="imessage",
            recipient_key="owner_phone",
            template_key="dry_run_boundary",
            body="通信链路干跑验证，仅供研究系统使用。",
            dry_run=True,
            adapter=IMessageAdapter(runner=fail_runner, run_system_preflight=False),
        )

    assert message["status"] == "dry_run"


def test_imessage_applescript_command_escapes_message_text():
    script = build_imessage_applescript(
        address='owner"phone@example.com',
        body='研究摘要 "仅供参考"\n不构成投资建议。',
    )

    assert 'tell application "Messages"' in script
    assert 'service type = iMessage' in script
    assert 'buddy "owner\\"phone@example.com"' in script
    assert 'send "研究摘要 \\"仅供参考\\"\\n不构成投资建议。"' in script


def test_imessage_real_send_uses_adapter_boundary_and_persists_sent(tmp_path):
    db_path = tmp_path / "communication.sqlite3"
    init_db(db_path)
    calls = []

    def fake_runner(*args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="", stderr="")

    with connect(db_path) as conn:
        seed_adapter_and_recipient(conn, dry_run_default=0)
        message = send_outbound_message(
            conn,
            channel="imessage",
            recipient_key="owner_phone",
            template_key="real_boundary",
            body="真实发送边界测试，仅供研究系统使用。",
            dry_run=False,
            adapter=IMessageAdapter(runner=fake_runner, run_system_preflight=False),
        )
        row = conn.execute("SELECT * FROM outbound_messages WHERE id = ?", (message["id"],)).fetchone()

    assert message["status"] == "sent"
    assert row["sent_at"] is not None
    assert calls
    assert calls[0][0][0][0] == "osascript"


def test_imessage_permission_failure_maps_to_permission_required(tmp_path):
    db_path = tmp_path / "communication.sqlite3"
    init_db(db_path)

    def permission_runner(*args, **kwargs):
        return subprocess.CompletedProcess(args=args[0], returncode=1, stdout="", stderr="Not authorized to send Apple events to Messages. (-1743)")

    with connect(db_path) as conn:
        seed_adapter_and_recipient(conn, dry_run_default=0)
        message = send_outbound_message(
            conn,
            channel="imessage",
            recipient_key="owner_phone",
            template_key="permission_boundary",
            body="权限失败边界测试，仅供研究系统使用。",
            dry_run=False,
            adapter=IMessageAdapter(runner=permission_runner, run_system_preflight=False),
        )

    assert message["status"] == "permission_required"
    assert "-1743" in message["error"]


def test_verify_imessage_setup_can_skip_system_probe(tmp_path):
    db_path = tmp_path / "communication.sqlite3"
    init_db(db_path)
    with connect(db_path) as conn:
        seed_adapter_and_recipient(conn, dry_run_default=0)
        result = verify_imessage_setup(conn, recipient_key="owner_phone", run_system_probe=False)

    assert result["ok"] is True
    assert result["status"] == "verified"


def test_provider_warning_template_is_safe_and_idempotent(tmp_path):
    db_path = tmp_path / "communication-provider-warning.sqlite3"
    init_db(db_path)
    with connect(db_path) as conn:
        seed_adapter_and_recipient(conn)
        notification = render_provider_warning(
            run_date="2026-05-23",
            provider="AKShare",
            warning="请求被限流，部分资产沿用最近一次已入库数据。",
            next_action="等待下一轮低频重试，必要时检查代理和数据源状态。",
        )
        first = send_rendered_notification(conn, channel="imessage", recipient_key="owner_phone", notification=notification, dry_run=True)
        second = send_rendered_notification(conn, channel="imessage", recipient_key="owner_phone", notification=notification, dry_run=True)

    assert first["status"] == "dry_run"
    assert second["duplicate"] is True
    assert "运行健康提醒" in notification.body
    assert "raw" not in notification.body.lower()


def test_jarvis_summary_template_includes_required_phone_fields():
    notification = render_jarvis_daily_summary(
        {
            "brief_date": "2026-05-23",
            "version": "jarvis_v1",
            "focus_directions": [{"direction": "ETF轮动", "reason": "等待趋势确认"}],
            "one_line_stance": "均衡观察",
            "model_summary": {
                "status": "usable",
                "top_forecasts": [{"asset_name": "沪深300ETF", "expected_return": 0.023, "confidence": 0.67}],
                "model_risk_summary": {"status": "watch_only"},
                "confidence_gates": [{"gate": "weak_bucket_spread", "reason": "分桶价差偏弱，不能放大为强信号。"}],
                "disagreement": {"summary": "模型和专家基本一致"},
            },
            "expert_summary": [
                {"expert_name": "管仲", "action": "no_trade", "score": 70, "risk_state": "正常"},
                {"expert_name": "白圭", "action": "buy", "score": 72, "risk_state": "正常"},
            ],
            "risk_warnings": "仅作研究辅助，注意回撤风险。",
        }
    )

    assert notification.template_key == "jarvis_daily_summary"
    assert "关注：ETF轮动" in notification.body
    assert "结论：均衡观察" in notification.body
    assert "模型：" in notification.body
    assert "风险官:watch_only" in notification.body
    assert "分桶价差偏弱" in notification.body
    assert "专家：" in notification.body
    assert "风险：" in notification.body
    assert "/jarvis" in notification.body


def test_jarvis_weekly_summary_template_is_safe_and_idempotent(tmp_path):
    db_path = tmp_path / "communication-weekly.sqlite3"
    init_db(db_path)
    brief = {
        "brief_date": "2026-05-23",
        "version": "jarvis_v1",
        "focus_directions": [{"direction": "先补证据", "reason": "降低解释强度"}],
        "one_line_stance": "偏防守，先确认数据",
        "model_summary": {
            "status": "neutral",
            "top_forecasts": [{"asset_name": "沪深300ETF", "expected_return": 0.023, "confidence": 0.67}],
            "disagreement": {"summary": "模型和专家基本一致"},
        },
        "expert_summary": [{"expert_name": "管仲", "action": "no_trade", "score": 70, "risk_state": "正常"}],
        "risk_warnings": "仅作研究辅助，注意回撤风险。",
        "missing_evidence": [{"source": "capital_flow_observations"}],
        "stale_evidence": [],
    }
    with connect(db_path) as conn:
        seed_adapter_and_recipient(conn)
        notification = render_jarvis_weekly_summary([brief], period_start="2026-05-17", period_end="2026-05-23")
        first = send_rendered_notification(conn, channel="imessage", recipient_key="owner_phone", notification=notification, dry_run=True)
        second = send_rendered_notification(conn, channel="imessage", recipient_key="owner_phone", notification=notification, dry_run=True)

    assert notification.template_key == "jarvis_weekly_summary"
    assert "Jarvis 投资研究周报" in notification.body
    assert "本消息仅作研究辅助" in notification.body
    assert "不构成真实买卖指令" in notification.body
    assert "raw" not in notification.body.lower()
    assert first["status"] == "dry_run"
    assert second["duplicate"] is True


def test_communication_cli_configures_recipient_and_dry_run(tmp_path, capsys):
    db_path = tmp_path / "communication.sqlite3"

    assert cli_main(["communication", "configure-adapter", "--db", str(db_path), "--channel", "imessage", "--enabled"]) == 0
    assert cli_main(
        [
            "communication",
            "upsert-recipient",
            "--db",
            str(db_path),
            "--recipient-key",
            "owner_phone",
            "--display-name",
            "Owner",
            "--channel",
            "imessage",
            "--address",
            "+10000000000",
            "--allowlisted",
        ]
    ) == 0
    assert cli_main(
        [
            "communication",
            "send-test",
            "--db",
            str(db_path),
            "--recipient-key",
            "owner_phone",
            "--idempotency-key",
            "cli-test",
        ]
    ) == 0
    output = capsys.readouterr().out

    assert '"status": "dry_run"' in output
    assert cli_main(["communication", "list-adapters", "--db", str(db_path)]) == 0
    assert '"channel": "imessage"' in capsys.readouterr().out
    assert cli_main(["communication", "verify-setup", "--db", str(db_path), "--recipient-key", "owner_phone", "--skip-system-probe"]) == 0
    assert '"status": "verified"' in capsys.readouterr().out
    assert cli_main(["communication", "list-messages", "--db", str(db_path)]) == 0
    assert "cli-test" in capsys.readouterr().out


def seed_adapter_and_recipient(conn, dry_run_default: int = 1) -> None:
    upsert_communication_adapter_config(conn, {"channel": "imessage", "enabled": 1, "dry_run_default": dry_run_default})
    upsert_communication_recipient(
        conn,
        {
            "recipient_key": "owner_phone",
            "display_name": "Owner",
            "channel": "imessage",
            "address": "+10000000000",
            "allowlisted": 1,
            "enabled": 1,
            "rate_limit_per_hour": 10,
        },
    )
