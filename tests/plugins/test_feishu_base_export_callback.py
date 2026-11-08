"""Copy stays dry-run, and the policy insert does not deny other tools."""

from __future__ import annotations

import json

import pytest

from plugins.feishu_base_export.policy_fragment import allow_feishu_base_export
from plugins.feishu_base_export.prepare_profile import main
from plugins.feishu_base_export.tool import handle
from tests.plugins.test_feishu_base_export_flow import _deps


def test_check_does_not_listen_or_call_feishu(tmp_path):
    calls = []

    def transport(*args, **kwargs):
        calls.append(args)
        raise AssertionError("check must not call Feishu")

    payload = json.loads(handle({"action": "check"}, _deps=_deps(transport, output=tmp_path)))
    assert payload["listening"] is False and payload["auth_ready"] is False
    assert "base_token" in payload["missing"]
    assert calls == []


def test_prepare_profile_dry_run_writes_nothing(tmp_path):
    with pytest.raises(SystemExit):
        main([])
    assert main(["--profile-home", str(tmp_path)]) == 0
    assert not (tmp_path / "plugins").exists()
    assert not (tmp_path / "config.yaml").exists()


def test_policy_fragment_allows_only_the_export_tool():
    def previous(request):
        if request["tool_name"] == "terminal":
            return {"allowed": True, "reason": "kept"}
        return {"allowed": False, "reason": "policy_deny"}

    assert allow_feishu_base_export({"tool_name": "feishu_base_export"}, previous)["allowed"] is True
    assert allow_feishu_base_export({"tool_name": "terminal"}, previous)["reason"] == "kept"
    denied = allow_feishu_base_export({"tool_name": "write_file"}, previous)
    assert denied["allowed"] is False and denied["reason"] == "policy_deny"
