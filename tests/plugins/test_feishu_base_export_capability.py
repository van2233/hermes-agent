"""Call the attached a992 evaluator. It is not copied into the fork.

SHA256 798c460405b58e8c8a490318acb1fc42912b10a3bb5bc01f81063b8dbe45f3c5.
The plugin does not set read_only and is not in READ_ONLY_TOOLS, so a
normal allow is only a hash-checked policy verdict.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

_ATTACHMENT = Path("/home/ubuntu/.cursor/projects/workspace/uploads/runtime_capability_ab65.py")
_SHA256 = "798c460405b58e8c8a490318acb1fc42912b10a3bb5bc01f81063b8dbe45f3c5"


def _load(monkeypatch):
    if not _ATTACHMENT.is_file():
        pytest.skip("local runtime_capability attachment is not in this workspace")
    assert hashlib.sha256(_ATTACHMENT.read_bytes()).hexdigest() == _SHA256
    stub = types.ModuleType("agent.gdm_context")
    stub.current_gdm_evidence = lambda: None
    monkeypatch.setitem(sys.modules, "agent.gdm_context", stub)
    spec = importlib.util.spec_from_file_location("a992_runtime_capability_attachment", _ATTACHMENT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_export_tool_is_denied_until_a_verified_policy_allows_it(monkeypatch):
    from hermes_constants import get_hermes_home
    home = get_hermes_home()
    module = _load(monkeypatch)
    assert "feishu_base_export" not in module.READ_ONLY_TOOLS
    denied = module.evaluate_runtime_capability(
        "feishu_base_export", {"action": "export_xlsx"}, read_only=False,
    )
    assert denied.allowed is False
    assert denied.reason == "missing_manifest"

    project = home / "project"
    project.mkdir()
    policy_path = project / "allow_export.py"
    policy_path.write_text(
        "def evaluate(request):\n"
        "    if request.get('tool_name') == 'feishu_base_export':\n"
        "        return {'allowed': True, 'reason': 'owner allows base export'}\n"
        "    return {'allowed': False, 'reason': 'no'}\n",
        encoding="utf-8",
    )
    digest = hashlib.sha256(policy_path.read_bytes()).hexdigest()
    (home / "runtime-policy.json").write_text(json.dumps({
        "project_root": str(project),
        "policy_path": str(policy_path),
        "sha256": digest,
    }), encoding="utf-8")
    allowed = module.evaluate_runtime_capability(
        "feishu_base_export", {"action": "export_xlsx"}, read_only=False,
    )
    assert allowed.allowed is True
    assert allowed.reason == "policy_allow"
    other = module.evaluate_runtime_capability("terminal", {"command": "id"}, read_only=False)
    assert other.allowed is False
    assert other.reason == "policy_deny"
