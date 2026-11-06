"""Model-facing tool. Identity comes from the DM binding, never from arguments."""

from __future__ import annotations

import contextvars
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
                "enum": ["export_xlsx", "revoke", "check", "chart_png", "chart_pdf"],
            },
            "base_token": {"type": "string", "description": "Base token, at most 27 letters or digits."},
        },
        "required": ["action"],
    },
}


_DEPS = contextvars.ContextVar("feishu_base_export_deps", default=None)


def active_deps():
    override = _DEPS.get()
    if override is not None:
        return override
    return _production_deps()


def set_deps_override(deps):
    return _DEPS.set(deps)


def reset_deps_override(token) -> None:
    _DEPS.reset(token)


def handle(args, **kwargs) -> str:
    # task_id/session_id/user_task come from the host dispatcher on some builds.
    # They are not the Feishu sender. Only _deps is a test injection.
    action = str((args or {}).get("action") or "")
    if action in CHART_ACTIONS:
        return json.dumps({
            "ok": False, "status": "blocked", "action": action, "reason": CHART_BLOCKED,
        })
    deps = kwargs.get("_deps") or active_deps()
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

    return Deps(
        session={},
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
