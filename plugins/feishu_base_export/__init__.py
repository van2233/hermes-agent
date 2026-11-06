"""Opt-in Feishu Base export plugin.

Excel export runs when the DM binding and deploy settings are present.
Live chart fetch stays blocked. See the 2026-11-06 design note.
"""

from __future__ import annotations


def register(ctx):
    from plugins.feishu_base_export.hooks import on_pre_gateway_dispatch, on_transform_llm_output
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
    ctx.register_hook("transform_llm_output", on_transform_llm_output)
