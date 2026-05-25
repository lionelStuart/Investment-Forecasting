from __future__ import annotations

import json
import hashlib
from dataclasses import dataclass
from typing import Any

from investment_forecasting.communication.service import send_outbound_message


@dataclass(frozen=True)
class RenderedNotification:
    template_key: str
    subject: str
    body: str
    severity: str
    payload_summary: str
    idempotency_key: str


def send_rendered_notification(
    conn,
    *,
    channel: str,
    recipient_key: str,
    notification: RenderedNotification,
    dry_run: bool | None = None,
) -> dict[str, Any]:
    return send_outbound_message(
        conn,
        channel=channel,
        recipient_key=recipient_key,
        template_key=notification.template_key,
        subject=notification.subject,
        body=notification.body,
        severity=notification.severity,
        payload_summary=notification.payload_summary,
        idempotency_key=notification.idempotency_key,
        dry_run=dry_run,
    )


def render_daily_success(conn, *, run_date: str, steps: dict[str, Any]) -> RenderedNotification:
    brief = _latest_jarvis_brief(conn, run_date)
    advice = _latest_daily_advice(conn, run_date)
    stance = brief["one_line_stance"] if brief else (advice["market_summary"] if advice else "日常研究流程已完成。")
    watch = _watch_condition(brief, advice)
    completed = "、".join(key for key in steps.keys() if key != "notification") or "workflow"
    body = "\n".join(
        [
            f"投资研究支持通知：{run_date} 日常研究流程已完成。",
            f"摘要：{_clip(stance, 120)}",
            f"关注：{_clip(watch, 90)}",
            f"完成环节：{completed}。",
            "仅供研究辅助，不构成真实买卖指令；请回到本地 WebUI 复核证据与风险。",
        ]
    )
    return RenderedNotification(
        template_key="daily_workflow_success",
        subject=f"Daily research ready {run_date}",
        body=body,
        severity="info",
        payload_summary=f"daily workflow success for {run_date}",
        idempotency_key=f"mobile:daily_success:{run_date}",
    )


def render_daily_failure(*, run_date: str, completed_steps: dict[str, Any], error: str) -> RenderedNotification:
    completed = "、".join(completed_steps.keys()) if completed_steps else "尚无完成环节"
    body = "\n".join(
        [
            f"投资研究支持通知：{run_date} 日常研究流程失败。",
            f"已完成：{completed}。",
            f"影响：今日研究摘要可能缺少最新数据、预测或建议。",
            f"错误：{_clip(error, 120)}",
            "请在本地 WebUI 的日志页或 CLI task_logs 中复核；本消息不构成投资建议。",
        ]
    )
    return RenderedNotification(
        template_key="daily_workflow_failure",
        subject=f"Daily research failed {run_date}",
        body=body,
        severity="critical",
        payload_summary=f"daily workflow failure for {run_date}",
        idempotency_key=f"mobile:daily_failure:{run_date}",
    )


def render_provider_warning(*, run_date: str, provider: str, warning: str, next_action: str) -> RenderedNotification:
    body = "\n".join(
        [
            f"投资研究支持通知：{run_date} 数据源 {provider} 出现警告。",
            f"警告：{_clip(warning, 120)}",
            f"建议处理：{_clip(next_action, 100)}",
            "核心研究流程应以已入库证据为准；本消息仅用于运行健康提醒。",
        ]
    )
    return RenderedNotification(
        template_key="provider_warning",
        subject=f"Provider warning {provider}",
        body=body,
        severity="warning",
        payload_summary=f"provider warning {provider} for {run_date}",
        idempotency_key=f"mobile:provider_warning:{provider}:{run_date}:{_stable_digest(warning)}",
    )


def render_expert_plan_ready(conn, *, plan_date: str) -> RenderedNotification:
    plans = _expert_plans(conn, plan_date)
    action_counts: dict[str, int] = {}
    lines = []
    for plan in plans:
        action_counts[plan["action"]] = action_counts.get(plan["action"], 0) + 1
        asset = plan["asset_name"] or "现金/观察"
        lines.append(f"{plan['expert_name']}：{_action_label(plan['action'])} {asset}，{plan['execution_status']}")
    body = "\n".join(
        [
            f"虚拟专家委员会通知：{plan_date} 专家计划已生成。",
            f"概况：{len(plans)} 位专家，操作分布 {_format_counts(action_counts)}。",
            *_clip_lines(lines, 4, 80),
            "以上仅为虚拟研究组合模拟，不是现实账户买卖指令；请在专家页查看证据、reason、分析与反思。",
        ]
    )
    return RenderedNotification(
        template_key="expert_plan_ready",
        subject=f"Expert plans ready {plan_date}",
        body=body,
        severity="info",
        payload_summary=f"expert plan ready for {plan_date}",
        idempotency_key=f"mobile:expert_plan_ready:{plan_date}",
    )


def render_expert_probation(conn, *, review_date: str) -> RenderedNotification:
    reviews = _expert_reviews(conn, review_date, decisions=("warn", "probation"))
    lines = [
        f"{row['expert_name']}：{row['decision']}，{_clip(row['rationale'], 70)}"
        for row in reviews
    ]
    body = "\n".join(
        [
            f"虚拟专家委员会通知：{review_date} 出现专家观察/ probation 信号。",
            *_clip_lines(lines, 4, 90),
            "这是虚拟研究组合的生命周期管理提醒，不构成真实投资操作建议。",
        ]
    )
    return RenderedNotification(
        template_key="expert_probation",
        subject=f"Expert review warning {review_date}",
        body=body,
        severity="warning",
        payload_summary=f"expert probation warning for {review_date}",
        idempotency_key=f"mobile:expert_probation:{review_date}",
    )


def render_expert_retirement(conn, *, review_date: str) -> RenderedNotification:
    reviews = _expert_reviews(conn, review_date, decisions=("retire", "hire_replacement"))
    lines = [
        f"{row['expert_name']}：{row['decision']}，{_clip(row['rationale'], 70)}"
        for row in reviews
    ]
    body = "\n".join(
        [
            f"虚拟专家委员会通知：{review_date} 专家退休/补位完成。",
            *_clip_lines(lines, 5, 90),
            "该通知仅说明虚拟专家体系调整；真实资金决策仍需回到本地证据页复核。",
        ]
    )
    return RenderedNotification(
        template_key="expert_retirement",
        subject=f"Expert lifecycle change {review_date}",
        body=body,
        severity="warning",
        payload_summary=f"expert retirement or replacement for {review_date}",
        idempotency_key=f"mobile:expert_retirement:{review_date}",
    )


def render_jarvis_daily_summary(brief: dict[str, Any]) -> RenderedNotification:
    focus = _jarvis_focus_line(brief.get("focus_directions") or [])
    model_signal = _jarvis_model_signal(brief.get("model_summary") or {})
    expert_signal = _jarvis_expert_signal(brief.get("expert_summary") or [], brief.get("model_summary") or {})
    risk = _clip(brief.get("risk_warnings") or "请复核本地 Jarvis 页面中的风险边界。", 96)
    brief_date = brief["brief_date"]
    body = "\n".join(
        [
            f"Jarvis 投资研究摘要：{brief_date}",
            f"关注：{focus}",
            f"结论：{_clip(brief.get('one_line_stance') or '暂无结论', 88)}",
            f"模型：{model_signal}",
            f"专家：{expert_signal}",
            f"风险：{risk}",
            "请回到本地 WebUI /jarvis 查看证据入口；本消息仅作研究辅助，不构成真实买卖指令。",
        ]
    )
    return RenderedNotification(
        template_key="jarvis_daily_summary",
        subject=f"Jarvis daily summary {brief_date}",
        body=body,
        severity="info",
        payload_summary=f"Jarvis daily summary for {brief_date}",
        idempotency_key=f"mobile:jarvis_daily_summary:{brief_date}:{brief.get('version') or 'jarvis_v1'}",
    )


def render_jarvis_weekly_summary(
    briefs: list[dict[str, Any]],
    *,
    period_start: str,
    period_end: str,
) -> RenderedNotification:
    latest = briefs[-1] if briefs else {}
    focus = _jarvis_focus_line(latest.get("focus_directions") or [])
    model_signal = _jarvis_model_signal(latest.get("model_summary") or {})
    expert_signal = _jarvis_expert_signal(latest.get("expert_summary") or [], latest.get("model_summary") or {})
    missing_count = sum(len(brief.get("missing_evidence") or []) for brief in briefs)
    stale_count = sum(len(brief.get("stale_evidence") or []) for brief in briefs)
    risk = _clip(latest.get("risk_warnings") or "请复核本地 Jarvis 页面中的风险边界。", 96)
    stance = latest.get("one_line_stance") or "暂无周度结论"
    body = "\n".join(
        [
            f"Jarvis 投资研究周报：{period_start} 至 {period_end}",
            f"本周结论：{_clip(stance, 88)}",
            f"最新关注：{focus}",
            f"覆盖：{len(briefs)} 份日简报；缺失证据 {missing_count}，过期证据 {stale_count}。",
            f"模型：{model_signal}",
            f"专家：{expert_signal}",
            f"风险：{risk}",
            "请回到本地 WebUI /jarvis 和 /evidence 查看完整证据；本消息仅作研究辅助，不构成真实买卖指令。",
        ]
    )
    return RenderedNotification(
        template_key="jarvis_weekly_summary",
        subject=f"Jarvis weekly summary {period_start} to {period_end}",
        body=body,
        severity="info",
        payload_summary=f"Jarvis weekly summary for {period_start} to {period_end}",
        idempotency_key=f"mobile:jarvis_weekly_summary:{period_start}:{period_end}",
    )


def _latest_jarvis_brief(conn, run_date: str):
    return conn.execute(
        """
        SELECT *
        FROM jarvis_daily_briefs
        WHERE brief_date <= ?
        ORDER BY brief_date DESC, updated_at DESC, id DESC
        LIMIT 1
        """,
        (run_date,),
    ).fetchone()


def _latest_daily_advice(conn, run_date: str):
    return conn.execute(
        """
        SELECT *
        FROM daily_advice
        WHERE advice_date <= ?
        ORDER BY advice_date DESC, updated_at DESC, id DESC
        LIMIT 1
        """,
        (run_date,),
    ).fetchone()


def _watch_condition(brief, advice) -> str:
    if brief:
        try:
            focus = json.loads(brief["focus_directions_json"])
        except json.JSONDecodeError:
            focus = []
        if focus:
            first = focus[0]
            if isinstance(first, dict):
                return str(first.get("watch_condition") or first.get("direction") or first)
            return str(first)
        return brief["combined_recommendation"]
    if advice:
        return f"风险等级 {advice['risk_level']}；请复核建议与风险提示。"
    return "请复核本地 WebUI 的运行健康和最新证据。"


def _expert_plans(conn, plan_date: str):
    return conn.execute(
        """
        SELECT p.*, e.name AS expert_name, a.name AS asset_name
        FROM expert_plans p
        JOIN experts e ON e.id = p.expert_id
        LEFT JOIN assets a ON a.id = p.target_asset_id
        WHERE p.plan_date = ?
        ORDER BY e.name
        """,
        (plan_date,),
    ).fetchall()


def _expert_reviews(conn, review_date: str, *, decisions: tuple[str, ...]):
    placeholders = ",".join("?" for _ in decisions)
    return conn.execute(
        f"""
        SELECT rv.*, e.name AS expert_name
        FROM expert_reviews rv
        JOIN experts e ON e.id = rv.expert_id
        WHERE rv.review_date = ?
          AND rv.decision IN ({placeholders})
        ORDER BY rv.id
        """,
        (review_date, *decisions),
    ).fetchall()


def _action_label(action: str) -> str:
    return {"buy": "虚拟买入", "sell": "虚拟卖出", "hold": "持有", "no_trade": "观察"}.get(action, action)


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "暂无计划"
    return "、".join(f"{_action_label(key)}{value}" for key, value in sorted(counts.items()))


def _jarvis_focus_line(focus_directions: list[Any]) -> str:
    if not focus_directions:
        return "暂无明确关注方向"
    first = focus_directions[0]
    if isinstance(first, dict):
        direction = first.get("direction") or first.get("title") or first.get("name") or str(first)
        reason = first.get("reason") or first.get("watch_condition") or ""
        return _clip(f"{direction} - {reason}" if reason else str(direction), 88)
    return _clip(str(first), 88)


def _jarvis_model_signal(model_summary: dict[str, Any]) -> str:
    status = model_summary.get("status") or "unknown"
    gates = model_summary.get("confidence_gates") or []
    risk_summary = model_summary.get("model_risk_summary") or {}
    forecasts = model_summary.get("top_forecasts") or model_summary.get("horizons") or []
    if forecasts:
        first = forecasts[0]
        if isinstance(first, dict):
            name = first.get("asset_name") or first.get("name") or f"{first.get('horizon_days', '')}日"
            expected = first.get("expected_return")
            confidence = first.get("confidence")
            parts = [str(name)]
            if expected is not None:
                parts.append(f"预期{float(expected):+.2%}")
            if confidence is not None:
                parts.append(f"置信{float(confidence):.0%}")
            if gates:
                reason = gates[0].get("reason") if isinstance(gates[0], dict) else "触发信心门"
                parts.append(f"风险官:{risk_summary.get('status') or '观察'}")
                parts.append(_clip(str(reason), 32))
            return _clip(f"{status}，" + "，".join(parts), 90)
    return _clip(str(model_summary.get("summary") or f"模型状态 {status}"), 90)


def _jarvis_expert_signal(expert_summary: list[Any], model_summary: dict[str, Any]) -> str:
    if not expert_summary:
        return "缺少专家证据"
    action_counts: dict[str, int] = {}
    weak = 0
    for row in expert_summary:
        if not isinstance(row, dict):
            continue
        action = str(row.get("action") or "unknown")
        action_counts[action] = action_counts.get(action, 0) + 1
        risk_state = str(row.get("risk_state") or "")
        if "样本不足" in risk_state or row.get("score") in (None, ""):
            weak += 1
    disagreement = (model_summary.get("disagreement") or {}).get("summary") if isinstance(model_summary.get("disagreement"), dict) else None
    signal = f"{len(expert_summary)}位专家，{_format_counts(action_counts)}"
    if weak:
        signal += f"，{weak}位证据偏弱"
    if disagreement:
        signal += f"；{disagreement}"
    return _clip(signal, 110)


def _clip_lines(lines: list[str], limit: int, width: int) -> list[str]:
    if not lines:
        return ["暂无可发送明细，请在本地系统查看。"]
    clipped = [_clip(line, width) for line in lines[:limit]]
    if len(lines) > limit:
        clipped.append(f"另有 {len(lines) - limit} 条明细，请回到本地 WebUI 查看。")
    return clipped


def _clip(text: str, width: int) -> str:
    cleaned = " ".join(str(text).split())
    return cleaned if len(cleaned) <= width else cleaned[: width - 1] + "..."


def _stable_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
