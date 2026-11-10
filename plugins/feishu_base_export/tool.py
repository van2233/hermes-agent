"""Model-facing tool. The Base and the recipient come from admin config and the DM event."""

from __future__ import annotations

import contextvars
import json

from plugins.feishu_base_export.service import run_action

SCHEMA = {
    "name": "feishu_base_export",
    "description": (
        "Using the bot tenant token and the one admin-configured Base, export xlsx "
        "or redraw a bar chart as PNG or PDF into the current private chat. "
        "The chart is aggregated from table records and is not the original Feishu image. "
        "Do not pass open_id, chat_id, or a different base."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["export_xlsx", "check", "chart_png", "chart_pdf"],
            },
            "table": {"type": "string", "description": "Table name or tbl id in the configured Base."},
            "category": {"type": "string", "description": "Category field for the bar chart."},
            "value": {"type": "string", "description": "Numeric field. Omit when agg is count."},
            "agg": {"type": "string", "enum": ["sum", "count", "avg"], "description": "Aggregation. Default sum."},
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
