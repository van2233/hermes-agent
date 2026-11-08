"""Model-facing tool. The Base and the recipient come from admin config and the DM event."""

from __future__ import annotations

import contextvars
import json

from plugins.feishu_base_export.blocked import CHART_BLOCKED
from plugins.feishu_base_export.service import CHART_ACTIONS, run_action

SCHEMA = {
    "name": "feishu_base_export",
    "description": (
        "Export the one admin-configured Feishu Base to xlsx with the bot tenant token "
        "and return it in the current private chat. chart_png and chart_pdf are not connected. "
        "Do not pass open_id, chat_id, or a different base."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["export_xlsx", "check", "chart_png", "chart_pdf"],
            },
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
    action = str((args or {}).get("action") or "")
    if action in CHART_ACTIONS:
        return json.dumps({
            "ok": False, "status": "blocked", "action": action, "reason": CHART_BLOCKED,
        })
    deps = kwargs.get("_deps") or active_deps()
    return json.dumps(run_action(args or {}, deps))


def _production_deps():
    from plugins.feishu_base_export.binding import default_store
    from plugins.feishu_base_export.config import production_config
    from plugins.feishu_base_export.delivery import default_output_dir
    from plugins.feishu_base_export.http_guard import guarded_request
    from plugins.feishu_base_export.service import Deps, clock

    return Deps(
        session={},
        config=production_config(),
        transport=guarded_request,
        bindings=default_store(),
        now=clock(),
        output_dir=default_output_dir(),
    )
