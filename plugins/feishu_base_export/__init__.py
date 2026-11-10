"""Opt-in bot export of one configured Feishu Base into the current private chat."""

from __future__ import annotations


def register(ctx):
    from .hooks import on_pre_gateway_dispatch, on_transform_llm_output
    from .tool import SCHEMA, handle

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
