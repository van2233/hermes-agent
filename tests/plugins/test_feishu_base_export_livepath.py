"""Excel path through the real hook dispatcher and a tool worker thread.

LoopProtector stands in for DPAPI. This file does not claim a Windows
CryptProtectData round-trip.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from urllib.parse import unquote

from gateway.session_context import clear_session_vars, set_session_vars
from hermes_cli.plugins import PluginContext, PluginManager
from plugins.feishu_base_export import register
from plugins.feishu_base_export.binding import default_store, reset_default_store
from plugins.feishu_base_export.delivery import reset_ledger
from plugins.feishu_base_export.tool import handle, reset_deps_override, set_deps_override
from tests.plugins.test_feishu_base_export import BASE, OPEN_ID, _event, _xlsx
from tests.plugins.test_feishu_base_export_flow import _deps
from tools.thread_context import propagate_context_to_thread


def test_hook_and_tool_thread_export_only_the_event_open_id(tmp_path):
    reset_default_store()
    reset_ledger()
    good = _xlsx()
    calls = []

    def transport(method, url, user_token, body):
        calls.append((method, url, user_token, None if body is None else dict(body)))
        if str(url).endswith("/oauth/token") and body and body.get("grant_type") == "authorization_code":
            assert body["code"] == "one-time-code"
            return SimpleNamespace(status=200, body=json.dumps({
                "code": 0, "access_token": "u-user", "refresh_token": "r-user",
                "expires_in": 7200, "refresh_token_expires_in": 86400,
            }).encode())
        if str(url).endswith("/user_info"):
            assert user_token == "u-user"
            return SimpleNamespace(status=200, body=json.dumps({
                "code": 0, "data": {"open_id": OPEN_ID},
            }).encode())
        if method == "POST":
            assert user_token == "u-user"
            assert body.get("type") == "bitable" and "sub_id" not in (body or {})
            return SimpleNamespace(status=200, body=json.dumps({"code": 0, "data": {"ticket": "77"}}).encode())
        if "file/" in str(url):
            return SimpleNamespace(status=200, body=good)
        return SimpleNamespace(status=200, body=json.dumps({"code": 0, "data": {"result": {
            "job_status": 0, "file_token": "boxcnxe5OdjlAkNgSNdsJvabcef", "file_size": len(good),
        }}}).encode())

    from plugins.feishu_base_export.config import RuntimeConfig
    deps = _deps(
        transport,
        store=default_store(),
        session=None,
        output=tmp_path,
        config=RuntimeConfig(
            app_id="cli_app", app_secret="app-secret-value",
            redirect_uri="https://cb.example.com/feishu",
        ),
    )
    # Session fields are read inside the worker from the copied context, not from this object.
    deps.session = {}
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

        propagate_context_to_thread(_ask)({"action": "export_xlsx", "base_token": BASE, "open_id": "ou_forgedforged1"})
        first = json.loads(seen["body"])
        assert first["status"] == "need_auth"
        assert "app-secret-value" not in first["authorize_url"]
        assert OPEN_ID not in first["authorize_url"]
        shown = manager.invoke_hook(
            "transform_llm_output", response_text="模型漏了链接 MEDIA:/tmp/stolen.xlsx",
            session_id="s", model="m", platform="feishu",
        )
        assert first["authorize_url"] in shown[0]
        assert "stolen.xlsx" not in shown[0]
        state = unquote(first["authorize_url"].split("state=")[1].split("&")[0])
        pasted = _event(message_id="om_live")
        pasted.text = f"https://cb.example.com/feishu?code=one-time-code&state={state}"
        rewritten = manager.invoke_hook("pre_gateway_dispatch", event=pasted)
        assert rewritten and rewritten[0]["action"] == "rewrite"
        assert "one-time-code" not in rewritten[0]["text"]
        assert default_store().match(
            message_id="om_live", chat_id="oc_1", chat_type="dm", platform="feishu",
        ).open_id == OPEN_ID
        assert deps.tokens.load(OPEN_ID)["access_token"] == "u-user"
        assert deps.tokens.load("u_tenant_not_open") is None

        propagate_context_to_thread(_ask)({"action": "export_xlsx", "base_token": BASE, "open_id": "ou_forgedforged1"})
        ready = json.loads(seen["body"])
        assert ready["status"] == "ready"
        assert "u-user" not in seen["body"]
        delivered = manager.invoke_hook(
            "transform_llm_output", response_text="MEDIA:/tmp/stolen.xlsx",
            session_id="s", model="m", platform="feishu",
        )
        text = delivered[0]
        assert "stolen.xlsx" not in text
        assert "MEDIA:" in text
        path = text.split("MEDIA:", 1)[1].strip()
        assert path.startswith(str(tmp_path))
        assert open(path, "rb").read().startswith(b"PK")
        assert any(call[2] == "u-user" and call[0] == "POST" and "export_tasks" in call[1] for call in calls)
    finally:
        reset_deps_override(token)
        clear_session_vars(session_tokens)
        reset_default_store()
        reset_ledger()
