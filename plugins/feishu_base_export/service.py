"""Wire a verified DM binding to authorization-code export. Charts stay blocked."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass

from plugins.feishu_base_export.bitable_xlsx import export_bitable_xlsx
from plugins.feishu_base_export.blocked import CHART_BLOCKED
from plugins.feishu_base_export.config import RuntimeConfig
from plugins.feishu_base_export.delivery import stage_file, stage_text
from plugins.feishu_base_export.oauth_flow import OAuthError, build_authorize_url, refresh_access
from plugins.feishu_base_export.oauth_state import StateStore

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()
CHART_ACTIONS = ("chart_png", "chart_pdf")


@dataclass
class Deps:
    session: dict
    config: RuntimeConfig
    transport: object
    tokens: object
    bindings: object
    states: StateStore
    now: float
    output_dir: object


def run_action(args: dict, deps: Deps) -> dict:
    action = str((args or {}).get("action") or "")
    if action in CHART_ACTIONS:
        return {"ok": False, "status": "blocked", "action": action, "reason": CHART_BLOCKED}
    if action == "check":
        from plugins.feishu_base_export.callback import describe_setup
        return describe_setup(deps.config)
    binding = _binding(deps)
    if binding is None:
        return {"ok": False, "status": "unavailable", "action": action, "reason": "没有已核验的飞书私聊身份，拒绝导出。"}
    if action == "revoke":
        with _lock(binding.open_id):
            deps.tokens.delete(binding.open_id)
        return {
            "ok": True, "status": "revoked", "action": action,
            "reason": "已删除本机保存的该用户 token。这不是飞书侧撤销授权。",
        }
    if action != "export_xlsx":
        return {"ok": False, "status": "rejected", "action": action, "reason": "unknown action"}
    missing = deps.config.callback_problems()
    if missing:
        return {"ok": False, "status": "setup-required", "action": action, "missing": missing}
    stored = _usable_token(binding.open_id, deps)
    if stored is None:
        return _need_auth(binding, deps)
    try:
        blob = export_bitable_xlsx(
            user_token=stored, base_token=str((args or {}).get("base_token") or ""),
            transport=deps.transport, host=deps.config.api_host, sleep=lambda _s: None,
        )
    except Exception as exc:
        return {"ok": False, "status": "export-failed", "action": action, "reason": str(exc)}
    _sweep(deps.output_dir, deps.now)
    path = deps.output_dir / f"{uuid.uuid4().hex}.xlsx"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(blob)
    caption = "已按你的飞书账号导出整个多维表格（xlsx，不是单个数据表）。"
    stage_file(binding.message_id, str(path), caption)
    return {"ok": True, "status": "ready", "action": action, "delivery": "private-dm"}


def _need_auth(binding, deps: Deps) -> dict:
    state = deps.states.issue(open_id=binding.open_id, now=deps.now)
    challenge = deps.states.challenge_of(state)
    url = build_authorize_url(deps.config, state=state, challenge=challenge or "")
    text = "请在浏览器打开这个链接完成授权。不要把回调地址或授权码发到聊天里。\n" + url
    stage_text(binding.message_id, text)
    return {"ok": False, "status": "need_auth", "action": "export_xlsx", "authorize_url": url, "reason": text}


def _usable_token(open_id: str, deps: Deps) -> str | None:
    with _lock(open_id):
        stored = deps.tokens.load(open_id)
        if not stored:
            return None
        if float(stored.get("expires_at") or 0) > deps.now + 30:
            return str(stored["access_token"])
        try:
            issued = refresh_access(deps.transport, deps.config, str(stored["refresh_token"]))
        except OAuthError:
            deps.tokens.delete(open_id)
            return None
        save_issued(open_id, issued, deps)
        return issued["access_token"]


def save_issued(open_id: str, issued: dict, deps: Deps) -> None:
    deps.tokens.save(open_id, {
        "access_token": issued["access_token"],
        "refresh_token": issued["refresh_token"],
        "expires_at": deps.now + int(issued.get("expires_in") or 0),
        "refresh_expires_at": deps.now + int(issued.get("refresh_expires_in") or 0),
        "scope": issued.get("scope") or "",
    })


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


def _lock(open_id: str) -> threading.Lock:
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(open_id, threading.Lock())


def _sweep(directory, now: float) -> None:
    cutoff = now - 2 * 60 * 60
    if not getattr(directory, "is_dir", lambda: False)():
        return
    for child in directory.iterdir():
        try:
            if child.is_file() and child.stat().st_mtime < cutoff:
                child.unlink()
        except OSError:
            continue


def clock() -> float:
    return time.time()
