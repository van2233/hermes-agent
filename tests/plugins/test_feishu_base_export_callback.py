"""Loopback callback, dry-run, and an additive policy fragment. No public bind."""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest

from plugins.feishu_base_export.callback import describe_setup, handle_callback, start_loopback
from plugins.feishu_base_export.config import RuntimeConfig
from plugins.feishu_base_export.policy_fragment import allow_feishu_base_export
from plugins.feishu_base_export.prepare_profile import main
from plugins.feishu_base_export.tool import handle
from tests.plugins.test_feishu_base_export import OPEN_ID, OTHER_ID
from tests.plugins.test_feishu_base_export_flow import _deps


def _config(**overrides):
    values = dict(
        app_id="cli_app", app_secret="secret",
        redirect_uri="https://cb.example.com/feishu", callback_enabled=True,
    )
    values.update(overrides)
    return RuntimeConfig(**values)


def test_check_and_public_bind_do_not_listen(tmp_path):
    deps = _deps(lambda *a, **k: None, output=tmp_path, config=_config())
    report = json.loads(handle({"action": "check"}, _deps=deps))
    assert report["listening"] is False and report["status"] == "dry-run"
    assert start_loopback(_config(listen_host="0.0.0.0"), deps) is None
    assert "redirect_uri_https" in _config(redirect_uri="https://127.0.0.1/feishu").callback_problems()
    assert describe_setup(_config(callback_enabled=False))["missing"]


def test_wrong_open_id_does_not_save(tmp_path):
    ready = _issued(tmp_path, open_id=OTHER_ID)
    status, body = handle_callback(
        {"code": "abc", "state": ready.state}, deps=ready.deps, now=ready.deps.now,
    )
    assert status == 400 and body == "授权失败" and "abc" not in body
    assert ready.deps.tokens.load(OPEN_ID) is None


def test_http_callback_body_and_log_omit_the_code(tmp_path):
    store_deps = _issued(tmp_path, open_id=OPEN_ID)
    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    log = logging.getLogger("plugins.feishu_base_export.callback")
    handler = Capture()
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    try:
        status, body = handle_callback(
            {"code": "one-time-code", "state": store_deps.state},
            deps=store_deps.deps, now=store_deps.deps.now,
        )
    finally:
        log.removeHandler(handler)
    assert status == 200 and body == "授权成功，请回到飞书私聊。"
    assert "one-time-code" not in body
    assert not any("one-time-code" in line for line in records)
    again, replay = handle_callback(
        {"code": "one-time-code", "state": store_deps.state},
        deps=store_deps.deps, now=store_deps.deps.now,
    )
    assert again == 400 and "one-time-code" not in replay


def test_prepare_profile_requires_an_explicit_home_and_dry_run_writes_nothing(tmp_path):
    with pytest.raises(SystemExit):
        main([])
    assert main(["--profile-home", str(tmp_path)]) == 0
    assert not (tmp_path / "plugins").exists()
    assert main(["--profile-home", str(tmp_path), "--apply"]) == 0
    assert (tmp_path / "plugins" / "feishu_base_export" / "plugin.yaml").is_file()


def test_policy_fragment_allows_only_the_export_tool():
    def previous(request):
        if request["tool_name"] == "terminal":
            return {"allowed": True, "reason": "kept"}
        return {"allowed": False, "reason": "policy_deny"}

    assert allow_feishu_base_export({"tool_name": "feishu_base_export"}, previous)["allowed"] is True
    assert allow_feishu_base_export({"tool_name": "terminal"}, previous)["reason"] == "kept"
    denied = allow_feishu_base_export({"tool_name": "write_file"}, previous)
    assert denied["allowed"] is False and denied["reason"] == "policy_deny"


def _issued(tmp_path, *, open_id: str):
    from plugins.feishu_base_export.binding import BindingStore, consider_event
    from tests.plugins.test_feishu_base_export import _event

    store = BindingStore()
    consider_event(_event(), store)
    session = {"message_id": "om_1", "chat_id": "oc_1", "chat_type": "dm", "platform": "feishu"}
    deps = _deps(lambda *a, **k: None, store, session, tmp_path, _config())
    issued = json.loads(handle({"action": "export_xlsx", "base_token": "B"}, _deps=deps))
    state = __import__("urllib.parse", fromlist=["unquote"]).unquote(
        issued["authorize_url"].split("state=")[1].split("&")[0]
    )

    def transport(method, url, user_token, body):
        if str(url).endswith("/oauth/token"):
            return SimpleNamespace(status=200, body=json.dumps({
                "code": 0, "access_token": "u-user", "refresh_token": "r-user",
                "expires_in": 100, "refresh_token_expires_in": 100,
            }).encode())
        return SimpleNamespace(status=200, body=json.dumps({"code": 0, "data": {"open_id": open_id}}).encode())

    deps.transport = transport
    return SimpleNamespace(deps=deps, state=state)
