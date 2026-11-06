"""Model-facing tool. Identity comes from the DM binding, never from arguments."""

from __future__ import annotations

import json

from plugins.feishu_base_export.blocked import CHART_BLOCKED
from plugins.feishu_base_export.oauth_state import StateStore
from plugins.feishu_base_export.service import CHART_ACTIONS, run_action

SCHEMA = {
    "name": "feishu_base_export",
    "description": (
        "Export the whole Feishu Base as xlsx into the current private chat, "
        "using that sender's own user token. chart_png and chart_pdf stay blocked "
        "until an official chart-data API with scopes is confirmed. "
        "Do not pass open_id or a destination chat."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["export_xlsx", "revoke", "chart_png", "chart_pdf"],
            },
            "base_token": {"type": "string", "description": "Base token, at most 27 letters or digits."},
            "callback_url": {"type": "string", "description": "Full OAuth redirect URL pasted by the same user."},
        },
        "required": ["action"],
    },
}


def handle(args, **kwargs) -> str:
    # task_id/session_id/user_task come from the host dispatcher on some builds.
    # They are not the Feishu sender. Only _deps is a test injection.
    action = str((args or {}).get("action") or "")
    if action in CHART_ACTIONS:
        return json.dumps({
            "ok": False, "status": "blocked", "action": action, "reason": CHART_BLOCKED,
        })
    deps = kwargs.get("_deps")
    if deps is None:
        deps = _production_deps()
    return json.dumps(run_action(args or {}, deps))


def _production_deps():
    from pathlib import Path

    from plugins.feishu_base_export.binding import default_store
    from plugins.feishu_base_export.config import production_config
    from plugins.feishu_base_export.delivery import default_output_dir
    from plugins.feishu_base_export.dpapi import production_protector
    from plugins.feishu_base_export.http_guard import guarded_request
    from plugins.feishu_base_export.oauth_state import StateStore
    from plugins.feishu_base_export.service import Deps, clock
    from plugins.feishu_base_export.token_store import TokenStore
    from hermes_constants import get_hermes_home
    from gateway.session_context import get_session_env

    return Deps(
        session={
            "message_id": get_session_env("HERMES_SESSION_MESSAGE_ID", ""),
            "chat_id": get_session_env("HERMES_SESSION_CHAT_ID", ""),
            "chat_type": get_session_env("HERMES_SESSION_CHAT_TYPE", ""),
            "platform": get_session_env("HERMES_SESSION_PLATFORM", ""),
        },
        config=production_config(),
        transport=guarded_request,
        tokens=TokenStore(Path(get_hermes_home()), production_protector()),
        bindings=default_store(),
        states=_states(),
        now=clock(),
        output_dir=default_output_dir(),
    )


_STATE = StateStore()


def _states() -> StateStore:
    return _STATE
