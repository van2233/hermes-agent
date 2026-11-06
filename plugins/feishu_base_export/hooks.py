"""Gateway hooks. The raw event is the only source of the sender open_id."""

from __future__ import annotations

from plugins.feishu_base_export.binding import consider_event, default_store
from plugins.feishu_base_export.delivery import transform_response
from plugins.feishu_base_export.service import finish_callback


def on_pre_gateway_dispatch(event=None, **kwargs):
    if event is None:
        return None
    try:
        binding = consider_event(event, default_store())
    except (AttributeError, TypeError, ValueError):
        return None
    deps = kwargs.get("_deps")
    text = getattr(event, "text", "") if not isinstance(event, dict) else event.get("text", "")
    if binding is None or deps is None or not text:
        return None
    if "code=" not in text or "state=" not in text:
        return None
    result = finish_callback(text, binding=binding, deps=deps)
    if result.get("status") == "authorized":
        return {"action": "rewrite", "text": "飞书授权已完成。请再说一次要导出的多维表格。"}
    reason = str(result.get("reason") or "授权失败")
    return {"action": "rewrite", "text": reason}


def on_transform_llm_output(response_text: str = "", **kwargs):
    message_id = str(kwargs.get("message_id") or "")
    if not message_id:
        message_id = _session_message_id()
    rendered = transform_response(response_text, message_id=message_id)
    return rendered


def _session_message_id() -> str:
    try:
        from gateway.session_context import get_session_env
    except Exception:
        return ""
    return str(get_session_env("HERMES_SESSION_MESSAGE_ID", "") or "")
