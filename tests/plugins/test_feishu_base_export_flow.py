"""Bot-identity export with a mocked tenant token. Not a live Feishu call."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from plugins.feishu_base_export.binding import BindingStore, consider_event
from plugins.feishu_base_export.config import RuntimeConfig
from plugins.feishu_base_export.delivery import transform_response
from plugins.feishu_base_export.service import Deps
from plugins.feishu_base_export.tool import SCHEMA, handle
from tests.plugins.test_feishu_base_export import BASE, OPEN_ID, _event, _xlsx

TARGET = "E6OpbISaeaZAVRsojtacOU9rnjf"


def test_chart_actions_stay_unconnected():
    actions = SCHEMA["parameters"]["properties"]["action"]["enum"]
    assert "export_xlsx" in actions and "chart_png" in actions and "chart_pdf" in actions
    for action in ("chart_png", "chart_pdf"):
        payload = json.loads(handle({"action": action, "open_id": "ou_forged"}))
        assert payload["status"] == "blocked"
        assert "png" in payload["reason"] and "pdf" in payload["reason"]
        assert "未接通" in payload["reason"]


def test_bot_export_uses_the_configured_base_and_the_current_dm(tmp_path):
    store = BindingStore()
    consider_event(_event(), store)
    empty = _deps(lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("network")), store, tmp_path, RuntimeConfig())
    missing = json.loads(handle({"action": "export_xlsx", "base_token": "https://evil.example/base"}, _deps=empty))
    assert missing["status"] == "setup-required"
    assert "base_token" in missing["missing"]

    calls = []
    good = _xlsx()

    def transport(method, url, token, body):
        calls.append((method, url, token, body))
        if url.endswith("/tenant_access_token/internal"):
            assert body["app_id"] == "cli_app"
            assert "grant_type" not in body
            return SimpleNamespace(status=200, body=json.dumps({
                "code": 0, "tenant_access_token": "t-bot", "expire": 7200,
            }).encode())
        if method == "POST":
            assert token == "t-bot"
            assert body["token"] == TARGET and body["type"] == "bitable" and "sub_id" not in body
            return SimpleNamespace(status=200, body=json.dumps({"code": 0, "data": {"ticket": "77"}}).encode())
        if "file/" in url:
            return SimpleNamespace(status=200, body=good)
        return SimpleNamespace(status=200, body=json.dumps({"code": 0, "data": {"result": {
            "job_status": 0, "file_token": "boxcnxe5OdjlAkNgSNdsJvabcef", "file_size": len(good),
        }}}).encode())

    config = RuntimeConfig(app_id="cli_app", app_secret="app-secret-value", base_token=TARGET)
    deps = _deps(transport, store, tmp_path, config)
    rejected = json.loads(handle({"action": "export_xlsx", "base_token": BASE, "open_id": "ou_forged"}, _deps=deps))
    assert rejected["status"] == "rejected"
    assert calls == []
    ready = json.loads(handle({"action": "export_xlsx", "chat_id": "oc_other"}, _deps=deps))
    assert ready["status"] == "ready" and ready["delivery"] == "private-dm"
    assert "t-bot" not in json.dumps(ready) and "app-secret-value" not in json.dumps(ready)
    written = list(tmp_path.glob("*.xlsx"))
    assert len(written) == 1 and written[0].read_bytes().startswith(b"PK")
    delivered = transform_response("MEDIA:/tmp/other.xlsx", message_id="om_1")
    assert f"MEDIA:{written[0]}" in delivered and "other.xlsx" not in delivered
    assert calls[0][1].endswith("/tenant_access_token/internal")
    assert not any("/authen/" in call[1] for call in calls)


def test_table_permission_does_not_fall_back_to_a_user_token(tmp_path):
    store = BindingStore()
    consider_event(_event(), store)
    calls = []

    def transport(method, url, token, body):
        calls.append(url)
        if url.endswith("/tenant_access_token/internal"):
            return SimpleNamespace(status=200, body=json.dumps({
                "code": 0, "tenant_access_token": "t-bot",
            }).encode())
        if method == "POST":
            return SimpleNamespace(status=200, body=json.dumps({"code": 0, "data": {"ticket": "7705632562430135490"}}).encode())
        return SimpleNamespace(status=200, body=json.dumps({"code": 0, "data": {"result": {
            "job_status": 3, "job_error_msg": "bitable_no_table_permission",
        }}}).encode())

    config = RuntimeConfig(app_id="cli_app", app_secret="app-secret-value", base_token=TARGET)
    payload = json.loads(handle({"action": "export_xlsx"}, _deps=_deps(transport, store, tmp_path, config)))
    assert payload["status"] == "base-permission"
    assert "不会改用用户身份" in payload["reason"]
    assert not any("/authen/" in url or "oauth" in url for url in calls)
    assert list(tmp_path.glob("*.xlsx")) == []


def _deps(transport, store=None, output=None, config=None, session=None, now=1_700_000_000):
    if session is None:
        session = {"message_id": "om_1", "chat_id": "oc_1", "chat_type": "dm", "platform": "feishu"}
    return Deps(
        session=session,
        config=config if config is not None else RuntimeConfig(),
        transport=transport,
        bindings=store or BindingStore(),
        now=now,
        output_dir=Path(output or "/tmp"),
    )
