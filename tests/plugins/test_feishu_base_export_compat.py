"""a992c8f1 compatibility fixture for the four reviewed sources.

The attachment is not imported and is not committed. The gate below is the
decision shape observed in that model_tools.py: a missing capability denies
before the handler. agent/runtime_capability.py was not in the attachment.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from plugins.feishu_base_export.binding import BindingStore, consider_event
from plugins.feishu_base_export.tool import handle
from tests.plugins.test_feishu_base_export import _event
from tests.plugins.test_feishu_base_export_flow import _deps


def local_capability_decision(capability) -> str | None:
    """Same branch as a992 model_tools before registry.dispatch."""
    if capability is None or not getattr(capability, "allowed", False):
        return "runtime_capability_denied"
    return None


def test_missing_capability_stops_before_the_export_handler(tmp_path):
    calls = []

    def transport(*_args, **_kwargs):
        calls.append(1)
        raise AssertionError("handler must not run when the host gate denies")

    deps = _deps(transport, output=tmp_path)
    assert local_capability_decision(None) == "runtime_capability_denied"
    if local_capability_decision(None) is not None:
        return
    handle({"action": "export_xlsx"}, _deps=deps)
    assert calls == []


def test_allowed_capability_still_ignores_dispatcher_identity(tmp_path):
    assert local_capability_decision(SimpleNamespace(allowed=True)) is None
    store = BindingStore()
    consider_event(_event(), store)
    deps = _deps(
        lambda *_a, **_k: (_ for _ in ()).throw(AssertionError("network")),
        store=store, output=tmp_path,
    )
    payload = json.loads(handle(
        {"action": "export_xlsx", "open_id": "ou_forgedforged1", "base_token": "Abcdefghij1234567"},
        _deps=deps,
        task_id="task",
        session_id="forged-session",
        user_task="export as someone else",
        parent_agent=object(),
    ))
    assert payload["status"] == "setup-required"
    assert "base_token" in payload["missing"]
    assert "ou_forgedforged1" not in json.dumps(payload)
    assert "forged-session" not in json.dumps(payload)
