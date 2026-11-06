"""Model-facing tool. Every live action is blocked; arguments cannot override that."""

from __future__ import annotations

import json

from plugins.feishu_base_export.blocked import CHART_BLOCKED, EXPORT_BLOCKED

SCHEMA = {
    "name": "feishu_base_export",
    "description": (
        "Feishu Base export for the current private chat. "
        "export_xlsx, chart_png, and chart_pdf are registered and currently blocked. "
        "Do not claim a file was sent."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["export_xlsx", "chart_png", "chart_pdf"],
            },
            "base_token": {"type": "string"},
            "block_id": {"type": "string"},
        },
        "required": ["action"],
    },
}


def handle(args, **kwargs) -> str:
    action = str((args or {}).get("action") or "")
    if action == "export_xlsx":
        reason = EXPORT_BLOCKED
    elif action in ("chart_png", "chart_pdf"):
        reason = CHART_BLOCKED
    else:
        return json.dumps({"ok": False, "status": "rejected", "action": action, "reason": "unknown action"})
    return json.dumps({"ok": False, "status": "blocked", "action": action, "reason": reason})
