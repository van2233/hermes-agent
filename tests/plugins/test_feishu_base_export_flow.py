"""Mocked authorization-code export and private-DM delivery. Not a live Feishu call."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from plugins.feishu_base_export.binding import BindingStore, consider_event
from plugins.feishu_base_export.tool import SCHEMA, handle
from tests.plugins.test_feishu_base_export import BASE, OPEN_ID, OTHER_ID, _event, _xlsx

def test_chart_actions_stay_blocked_and_do_not_call_feishu():
    actions = SCHEMA["parameters"]["properties"]["action"]["enum"]
    assert "export_xlsx" in actions and "revoke" in actions
    assert "chart_png" in actions and "chart_pdf" in actions
    calls = []

    def transport(*args, **kwargs):
        calls.append(args)
        raise AssertionError("chart fetch must not call Feishu")

    for action in ("chart_png", "chart_pdf"):
        payload = json.loads(handle({"action": action, "open_id": OTHER_ID}, _deps=_deps(transport)))
        assert payload["status"] == "blocked"
        assert "png" in payload["reason"] and "pdf" in payload["reason"]
    assert calls == []


def test_export_requires_setup_then_auth_then_writes_only_the_caller_file(tmp_path):
    from plugins.feishu_base_export.config import RuntimeConfig
    from plugins.feishu_base_export.delivery import reset_ledger, transform_response
    from plugins.feishu_base_export.hooks import on_transform_llm_output

    store = BindingStore()
    consider_event(_event(), store)
    session = {"message_id": "om_1", "chat_id": "oc_1", "chat_type": "dm", "platform": "feishu"}
    empty = _deps(lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")), store, session, tmp_path, RuntimeConfig())
    missing = json.loads(handle({"action": "export_xlsx", "open_id": OTHER_ID, "base_token": BASE}, _deps=empty))
    assert missing["status"] == "setup-required"
    assert "redirect_uri" in missing["missing"]
    assert "FEISHU_APP_ID" in missing["missing"]

    config = RuntimeConfig(app_id="cli_app", app_secret="app-secret-value", redirect_uri="https://cb.example.com/feishu")
    reset_ledger()
    deps = _deps(lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")), store, session, tmp_path, config)
    need = json.loads(handle(
        {"action": "export_xlsx", "base_token": BASE, "open_id": OTHER_ID},
        _deps=deps,
    ))
    assert need["status"] == "need_auth"
    assert need["authorize_url"].startswith("https://accounts.feishu.cn/open-apis/authen/v1/authorize?")
    assert "app-secret-value" not in need["authorize_url"]
    assert OPEN_ID not in need["authorize_url"]
    assert "code_challenge_method=S256" in need["authorize_url"]
    forced = on_transform_llm_output("模型没贴链接", message_id="om_1")
    assert need["authorize_url"] in forced
    assert "MEDIA:" not in forced

    state = need["authorize_url"].split("state=")[1].split("&")[0]
    from urllib.parse import unquote
    state = unquote(state)
    good = _xlsx()
    calls = []

    def transport(method, url, user_token, body):
        calls.append((method, url, user_token, body))
        if url.endswith("/oauth/token"):
            assert body["code_verifier"]
            return SimpleNamespace(status=200, body=json.dumps({
                "code": 0, "access_token": "u-user", "refresh_token": "r-user",
                "expires_in": 7200, "refresh_token_expires_in": 86400, "scope": "drive:export:readonly",
            }).encode())
        if url.endswith("/user_info"):
            assert user_token == "u-user"
            return SimpleNamespace(status=200, body=json.dumps({"code": 0, "data": {"open_id": OPEN_ID}}).encode())
        if method == "POST":
            assert user_token == "u-user"
            assert body.get("type") == "bitable" and "sub_id" not in body
            return SimpleNamespace(status=200, body=json.dumps({"code": 0, "data": {"ticket": "77"}}).encode())
        if "file/" in url:
            return SimpleNamespace(status=200, body=good)
        return SimpleNamespace(status=200, body=json.dumps({"code": 0, "data": {"result": {
            "job_status": 0, "file_token": "boxcnxe5OdjlAkNgSNdsJvabcef", "file_size": len(good),
        }}}).encode())

    pasted = f"https://cb.example.com/feishu?code=one-time-code&state={state}"
    deps.transport = transport
    ready = json.loads(handle(
        {"action": "export_xlsx", "base_token": BASE, "callback_url": pasted, "open_id": OTHER_ID},
        _deps=deps,
    ))
    assert ready["status"] == "ready"
    assert "one-time-code" not in json.dumps(ready)
    assert "u-user" not in json.dumps(ready)
    written = list(tmp_path.glob("*.xlsx"))
    assert len(written) == 1 and written[0].read_bytes().startswith(b"PK")
    delivered = transform_response(f"拿走 MEDIA:{tmp_path / 'other.xlsx'}", message_id="om_1")
    assert f"MEDIA:{written[0]}" in delivered
    assert "other.xlsx" not in delivered
    assert calls[0][1].endswith("/oauth/token")


def test_oauth_rejects_other_open_id_and_revoke_drops_the_token(tmp_path):
    from plugins.feishu_base_export.config import RuntimeConfig

    store = BindingStore()
    consider_event(_event(message_id="om_2"), store)
    session = {"message_id": "om_2", "chat_id": "oc_1", "chat_type": "dm", "platform": "feishu"}
    config = RuntimeConfig(app_id="cli_app", app_secret="app-secret-value", redirect_uri="https://cb.example.com/feishu")
    deps = _deps(lambda *a, **k: (_ for _ in ()).throw(AssertionError("no")), store, session, tmp_path, config)
    need = json.loads(handle({"action": "export_xlsx"}, _deps=deps))
    state = __import__("urllib.parse", fromlist=["unquote"]).unquote(need["authorize_url"].split("state=")[1].split("&")[0])

    def transport(method, url, user_token, body):
        if url.endswith("/oauth/token"):
            return SimpleNamespace(status=200, body=json.dumps({
                "code": 0, "access_token": "u-other", "refresh_token": "r-other",
                "expires_in": 100, "refresh_token_expires_in": 100,
            }).encode())
        return SimpleNamespace(status=200, body=json.dumps({"code": 0, "data": {"open_id": OTHER_ID}}).encode())

    deps.transport = transport
    failed = json.loads(handle(
        {"action": "export_xlsx", "callback_url": f"https://cb.example.com/feishu?code=abc&state={state}"},
        _deps=deps,
    ))
    assert failed["status"] == "oauth-failed"
    assert "同一个飞书应用用户" in failed["reason"]
    assert deps.tokens.load(OPEN_ID) is None
    deps.tokens.save(OPEN_ID, {"access_token": "u-user", "refresh_token": "r-user", "expires_at": 10**12})
    revoked = json.loads(handle({"action": "revoke"}, _deps=deps))
    assert revoked["status"] == "revoked"
    assert deps.tokens.load(OPEN_ID) is None


def test_refresh_replaces_single_use_token_and_private_url_is_rejected(tmp_path):
    from plugins.feishu_base_export.config import RuntimeConfig
    from plugins.feishu_base_export.http_guard import UrlRejected, guarded_request

    store = BindingStore()
    consider_event(_event(message_id="om_3"), store)
    session = {"message_id": "om_3", "chat_id": "oc_1", "chat_type": "dm", "platform": "feishu"}
    config = RuntimeConfig(app_id="cli_app", app_secret="app-secret-value", redirect_uri="https://cb.example.com/feishu")
    good = _xlsx()
    seen = []

    def transport(method, url, user_token, body):
        seen.append((url, user_token, body))
        if url.endswith("/oauth/token"):
            assert body["grant_type"] == "refresh_token"
            assert body["refresh_token"] == "r-old"
            return SimpleNamespace(status=200, body=json.dumps({
                "code": 0, "access_token": "u-new", "refresh_token": "r-new",
                "expires_in": 7200, "refresh_token_expires_in": 86400,
            }).encode())
        if method == "POST":
            assert user_token == "u-new"
            return SimpleNamespace(status=200, body=json.dumps({"code": 0, "data": {"ticket": "5"}}).encode())
        if "file/" in url:
            return SimpleNamespace(status=200, body=good)
        return SimpleNamespace(status=200, body=json.dumps({"code": 0, "data": {"result": {
            "job_status": 0, "file_token": "boxcnxe5OdjlAkNgSNdsJvabcef", "file_size": len(good),
        }}}).encode())

    deps = _deps(transport, store, session, tmp_path, config, now=5_000)
    deps.tokens.save(OPEN_ID, {"access_token": "u-old", "refresh_token": "r-old", "expires_at": 1})
    ready = json.loads(handle({"action": "export_xlsx", "base_token": BASE}, _deps=deps))
    assert ready["status"] == "ready"
    assert deps.tokens.load(OPEN_ID)["refresh_token"] == "r-new"
    with pytest.raises(UrlRejected):
        guarded_request("GET", "https://127.0.0.1/open-apis/drive/v1/export_tasks", "u-x", None)


def _deps(transport, store=None, session=None, output=None, config=None, now=1_700_000_000):
    from pathlib import Path
    from plugins.feishu_base_export.config import RuntimeConfig
    from plugins.feishu_base_export.oauth_state import StateStore
    from plugins.feishu_base_export.service import Deps
    from plugins.feishu_base_export.token_store import LoopProtector, TokenStore

    home = Path(output or "/tmp")
    return Deps(
        session=session or {"message_id": "om_1", "chat_id": "oc_1", "chat_type": "dm", "platform": "feishu"},
        config=config if config is not None else RuntimeConfig(),
        transport=transport,
        tokens=TokenStore(home / "secrets", LoopProtector()),
        bindings=store or BindingStore(),
        states=StateStore(),
        now=now,
        output_dir=home,
    )


