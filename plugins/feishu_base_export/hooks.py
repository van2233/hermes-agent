"""Record the DM sender. The model does not choose the chat that receives the file."""

from __future__ import annotations

from plugins.feishu_base_export.binding import consider_event, default_store
from plugins.feishu_base_export.delivery import transform_response


def on_pre_gateway_dispatch(event=None, **kwargs):
    if event is None:
        return None
    try:
        consider_event(event, default_store())
    except (AttributeError, TypeError, ValueError):
        return None
    return None


def on_transform_llm_output(response_text: str = "", **kwargs):
    message_id = str(kwargs.get("message_id") or "") or _session_message_id()
    return transform_response(response_text, message_id=message_id)


def _session_message_id() -> str:
    try:
        from gateway.session_context import get_session_env
    except Exception:
        return ""
    return str(get_session_env("HERMES_SESSION_MESSAGE_ID", "") or "")
