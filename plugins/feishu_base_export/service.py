"""Export one admin-configured Base with the bot tenant token, back to the current DM."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from plugins.feishu_base_export.bitable_chart import chart_table, check_chart_args
from plugins.feishu_base_export.bitable_xlsx import ExportError, export_bitable_xlsx
from plugins.feishu_base_export.bot_token import tenant_access_token
from plugins.feishu_base_export.chart_data import EmptyAggregate, PayloadBoundsError
from plugins.feishu_base_export.chart_draw import CHART_CAPTION, render_chart
from plugins.feishu_base_export.config import RuntimeConfig
from plugins.feishu_base_export.delivery import stage_file

CHART_ACTIONS = ("chart_png", "chart_pdf")
_TABLE_PERMISSION = (
    "机器人对目标多维表格没有表权限（bitable_no_table_permission）。"
    "这不是 scope 不足，也不会改用用户身份。"
)


@dataclass
class Deps:
    session: dict
    config: RuntimeConfig
    transport: object
    bindings: object
    now: float
    output_dir: object


def run_action(args: dict, deps: Deps) -> dict:
    action = str((args or {}).get("action") or "")
    if action == "check":
        return {
            "ok": True, "status": "dry-run", "listening": False, "auth_ready": False,
            "missing": deps.config.missing(),
        }
    binding = _binding(deps)
    if binding is None:
        return {"ok": False, "status": "unavailable", "action": action, "reason": "没有已核验的飞书私聊，拒绝导出。"}
    if action not in {"export_xlsx", *CHART_ACTIONS}:
        return {"ok": False, "status": "rejected", "action": action, "reason": "unknown action"}
    missing = deps.config.missing()
    if missing:
        return {"ok": False, "status": "setup-required", "action": action, "missing": missing}
    supplied = str((args or {}).get("base_token") or "")
    if supplied and supplied != deps.config.base_token:
        return {"ok": False, "status": "rejected", "action": action, "reason": "只导出管理员配置的那一个多维表格。"}
    if action in CHART_ACTIONS:
        return _chart(action, args or {}, binding, deps)
    try:
        token = tenant_access_token(deps.transport, deps.config)
        blob = export_bitable_xlsx(
            access_token=token, base_token=deps.config.base_token,
            transport=deps.transport, host=deps.config.api_host, sleep=lambda _s: None,
        )
    except ExportError as exc:
        text = str(exc)
        if "bitable_no_table_permission" in text:
            return {"ok": False, "status": "base-permission", "action": action, "reason": _TABLE_PERMISSION}
        return {"ok": False, "status": "export-failed", "action": action, "reason": text}
    path = deps.output_dir / f"{uuid.uuid4().hex}.xlsx"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    stage_file(binding.message_id, str(path), "已用机器人身份导出管理员指定的整个多维表格（xlsx）。")
    return {"ok": True, "status": "ready", "action": action, "delivery": "private-dm"}


def _chart(action: str, args: dict, binding, deps: Deps) -> dict:
    fmt = "png" if action == "chart_png" else "pdf"
    try:
        check_chart_args(
            str(args.get("table") or ""), str(args.get("category") or ""),
            str(args.get("value") or ""), str(args.get("agg") or "sum"),
        )
        token = tenant_access_token(deps.transport, deps.config)
        table = chart_table(
            deps.transport, token=token, base_token=deps.config.base_token, host=deps.config.api_host,
            table=str(args.get("table") or ""), category=str(args.get("category") or ""),
            value=str(args.get("value") or ""), agg=str(args.get("agg") or "sum"),
        )
        blob = render_chart(table, fmt)
    except (ExportError, EmptyAggregate, PayloadBoundsError) as exc:
        text = str(exc)
        if "bitable_no_table_permission" in text:
            return {"ok": False, "status": "base-permission", "action": action, "reason": _TABLE_PERMISSION}
        return {"ok": False, "status": "chart-failed", "action": action, "reason": text}
    path = deps.output_dir / f"{uuid.uuid4().hex}.{fmt}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    stage_file(binding.message_id, str(path), CHART_CAPTION)
    return {"ok": True, "status": "ready", "action": action, "delivery": "private-dm", "redrawn": True}


def _session_from_env() -> dict:
    from gateway.session_context import get_session_env
    return {
        "message_id": get_session_env("HERMES_SESSION_MESSAGE_ID", ""),
        "chat_id": get_session_env("HERMES_SESSION_CHAT_ID", ""),
        "chat_type": get_session_env("HERMES_SESSION_CHAT_TYPE", ""),
        "platform": get_session_env("HERMES_SESSION_PLATFORM", ""),
    }


def _binding(deps: Deps):
    session = deps.session or _session_from_env()
    return deps.bindings.match(
        message_id=str(session.get("message_id") or ""),
        chat_id=str(session.get("chat_id") or ""),
        chat_type=str(session.get("chat_type") or ""),
        platform=str(session.get("platform") or ""),
    )


def clock() -> float:
    return time.time()
