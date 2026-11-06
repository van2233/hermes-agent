"""Opt-in Feishu Base export plugin.

Live user-token acquisition, live chart fetch, and outbound file delivery stay
blocked. See docs/superpowers/specs/2026-11-06-feishu-base-export-design.md.
"""

from __future__ import annotations


def register(ctx):
    from plugins.feishu_base_export.binding import on_pre_gateway_dispatch
    from plugins.feishu_base_export.tool import SCHEMA, handle

    ctx.register_tool(
        name="feishu_base_export",
        toolset="feishu_base_export",
        schema=SCHEMA,
        handler=handle,
        description=SCHEMA["description"],
        emoji="📊",
    )
    ctx.register_hook("pre_gateway_dispatch", on_pre_gateway_dispatch)
