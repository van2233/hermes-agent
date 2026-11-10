"""Bot export through the real hook dispatcher and a tool worker thread."""

from __future__ import annotations

import json
from types import SimpleNamespace
from urllib.parse import unquote

from gateway.session_context import clear_session_vars, set_session_vars
from hermes_cli.plugins import PluginContext, PluginManager
from plugins.feishu_base_export import register
from plugins.feishu_base_export.binding import default_store, reset_default_store
from plugins.feishu_base_export.config import RuntimeConfig
from plugins.feishu_base_export.delivery import reset_ledger
from plugins.feishu_base_export.tool import handle, reset_deps_override, set_deps_override
from tests.plugins.test_feishu_base_export import OPEN_ID, _event, _xlsx
from tests.plugins.test_feishu_base_export_flow import TARGET, _deps
from tools.thread_context import propagate_context_to_thread


def test_hook_and_tool_thread_export_the_configured_base_to_the_dm(tmp_path):
    reset_default_store()
    reset_ledger()
    good = _xlsx()
    calls = []

    def transport(method, url, token, body):
        calls.append((method, str(url), token))
        if str(url).endswith("/tenant_access_token/internal"):
            return SimpleNamespace(status=200, body=json.dumps({
                "code": 0, "tenant_access_token": "t-bot",
            }).encode())
        if method == "POST":
            assert token == "t-bot" and body["token"] == TARGET
            return SimpleNamespace(status=200, body=json.dumps({"code": 0, "data": {"ticket": "77"}}).encode())
        if "file/" in str(url):
            return SimpleNamespace(status=200, body=good)
        return SimpleNamespace(status=200, body=json.dumps({"code": 0, "data": {"result": {
            "job_status": 0, "file_token": "boxcnxe5OdjlAkNgSNdsJvabcef", "file_size": len(good),
        }}}).encode())

    deps = _deps(
        transport, store=default_store(), output=tmp_path,
        config=RuntimeConfig(app_id="cli_app", app_secret="app-secret-value", base_token=TARGET),
        session={},
    )
    token = set_deps_override(deps)
    session_tokens = set_session_vars(
        platform="feishu", chat_id="oc_1", chat_type="dm",
        user_id="u_tenant_not_open", message_id="om_live",
    )
    manager = PluginManager()
    register(PluginContext(SimpleNamespace(name="feishu-base-export", key="feishu-base-export"), manager))
    try:
        assert manager.invoke_hook("pre_gateway_dispatch", event=_event(message_id="om_live", open_id=OPEN_ID)) == []
        seen = {}

        def _ask(args):
            seen["body"] = handle(args)

        propagate_context_to_thread(_ask)({"action": "export_xlsx", "open_id": "ou_forgedforged1", "base_token": "https://evil.example/x"})
        payload = json.loads(seen["body"])
        assert payload["status"] == "rejected"
        assert calls == []
        propagate_context_to_thread(_ask)({"action": "export_xlsx", "open_id": "ou_forgedforged1"})
        ready = json.loads(seen["body"])
        assert ready["status"] == "ready"
        assert "t-bot" not in seen["body"]
        delivered = manager.invoke_hook(
            "transform_llm_output", response_text="MEDIA:/tmp/stolen.xlsx",
            session_id="s", model="m", platform="feishu",
        )
        text = delivered[0]
        assert "stolen.xlsx" not in text and "MEDIA:" in text
        path = text.split("MEDIA:", 1)[1].strip()
        assert path.startswith(str(tmp_path))
        assert open(path, "rb").read().startswith(b"PK")
        assert any(call[2] == "t-bot" and call[0] == "POST" and "export_tasks" in call[1] for call in calls)
        assert not any("/authen/" in call[1] for call in calls)
        assert unquote("t-bot") == "t-bot"
    finally:
        reset_deps_override(token)
        clear_session_vars(session_tokens)
        reset_default_store()
        reset_ledger()
