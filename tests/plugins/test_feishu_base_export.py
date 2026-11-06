"""Behavior contracts for the opt-in Feishu Base export plugin.

These tests run against commit 5eb99eb2's tree plus this plugin. They do not
claim the caller's two local commits (plugins.py, registry, model_tools,
tool_executor) still behave the same way.
"""

from __future__ import annotations

import contextvars
import io
import json
import threading
import zipfile
from types import SimpleNamespace

import pytest

from agent.file_safety import get_read_block_error
from hermes_constants import get_hermes_home
from plugins.feishu_base_export.binding import BindingStore, TurnBinding, consider_event
from plugins.feishu_base_export.chart_draw import render_chart, render_pixels
from plugins.feishu_base_export.chart_data import EmptyAggregate, PayloadBoundsError, parse_aggregate
from plugins.feishu_base_export.dpapi import DpapiUnavailable, WindowsDpapiProtector, production_protector
from plugins.feishu_base_export.bitable_xlsx import ExportError, export_bitable_xlsx
from plugins.feishu_base_export.http_guard import UrlRejected, parse_official_https
from plugins.feishu_base_export.identity import extract_sender_open_id, is_app_open_id
from plugins.feishu_base_export.oauth_state import StateStore, pkce_pair
from plugins.feishu_base_export.redact import redact
from plugins.feishu_base_export.token_store import LoopProtector, TokenStore
from plugins.feishu_base_export.tool import SCHEMA, handle
from plugins.feishu_base_export.xlsx_safe import UnsafeFile, assert_safe_xlsx

OPEN_ID = "ou_abc1234567890"
OTHER_ID = "ou_zzz9876543210"
BASE = "Abcdefghij1234567"  # 17 chars, within the documented 27


def _event(*, open_id=OPEN_ID, chat_type="dm", raw_chat="p2p", message_id="om_1", chat_id="oc_1", platform="feishu"):
    sender_id = SimpleNamespace(open_id=open_id, user_id="u_tenant", union_id="on_union")
    raw = SimpleNamespace(
        event=SimpleNamespace(
            sender=SimpleNamespace(sender_id=sender_id),
            message=SimpleNamespace(chat_type=raw_chat, chat_id=chat_id),
        )
    )
    return SimpleNamespace(
        message_id=message_id,
        text="export",
        source=SimpleNamespace(platform=SimpleNamespace(value=platform), chat_id=chat_id, chat_type=chat_type, user_id="u_tenant"),
        raw_message=raw,
    )


def test_app_open_id_accepts_documented_shapes_and_rejects_tenant_id():
    assert is_app_open_id("ou_abc1234567890")
    assert is_app_open_id("ou-caecc734c2e3328a62489fe0648c4b98779515d3")
    assert not is_app_open_id("u_tenant")
    assert not is_app_open_id("on_union")
    assert not is_app_open_id("ou_")
    assert extract_sender_open_id(_event().raw_message) == OPEN_ID


def test_binding_uses_raw_open_id_not_session_user_id_and_refuses_groups():
    store = BindingStore()
    binding = consider_event(_event(), store)
    assert isinstance(binding, TurnBinding)
    assert binding.open_id == OPEN_ID
    assert binding.open_id != "u_tenant"
    assert consider_event(_event(chat_type="group", raw_chat="group", message_id="om_g"), store) is None
    assert consider_event(_event(open_id="u_tenant", message_id="om_bad"), store) is None
    assert store.match(message_id="om_1", chat_id="oc_1", chat_type="dm", platform="feishu").open_id == OPEN_ID
    assert store.match(message_id="om_1", chat_id="oc_other", chat_type="dm", platform="feishu") is None
    assert store.match(message_id="", chat_id="oc_1", chat_type="dm", platform="feishu") is None


def test_concurrent_bindings_do_not_cross():
    store = BindingStore()
    barrier = threading.Barrier(2)

    def put(open_id, message_id, chat_id):
        barrier.wait()
        consider_event(_event(open_id=open_id, message_id=message_id, chat_id=chat_id), store)

    threads = [
        threading.Thread(target=put, args=(OPEN_ID, "om_a", "oc_a")),
        threading.Thread(target=put, args=(OTHER_ID, "om_b", "oc_b")),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert store.match(message_id="om_a", chat_id="oc_a", chat_type="dm", platform="feishu").open_id == OPEN_ID
    assert store.match(message_id="om_b", chat_id="oc_b", chat_type="dm", platform="feishu").open_id == OTHER_ID


def test_oauth_state_is_opaque_one_time_and_pkce_is_s256():
    store = StateStore()
    state = store.issue(open_id=OPEN_ID, now=1000)
    assert OPEN_ID not in state
    assert "secret" not in state.lower()
    record = store.consume(state, now=1001)
    assert record.open_id == OPEN_ID
    assert store.consume(state, now=1002) is None
    assert store.consume("missing", now=1002) is None
    verifier, challenge = pkce_pair()
    assert 43 <= len(verifier) <= 128
    assert verifier != challenge
    expired = store.issue(open_id=OPEN_ID, now=0, ttl_seconds=1)
    assert store.consume(expired, now=5) is None


def test_token_store_keeps_plaintext_out_of_the_mcp_tokens_file(tmp_path):
    home = tmp_path / "home"
    store = TokenStore(home, LoopProtector())
    store.save(OPEN_ID, {"access_token": "u-secret-value", "refresh_token": "r-secret"})
    path = store.path_for(OPEN_ID)
    assert path.is_relative_to(home / "mcp-tokens" / "feishu-base-export")
    assert OPEN_ID not in path.name
    raw = path.read_bytes()
    assert b"u-secret-value" not in raw
    assert store.load(OPEN_ID)["access_token"] == "u-secret-value"


@pytest.mark.linux_only
def test_posix_refuses_to_pretend_dpapi_worked():
    with pytest.raises(DpapiUnavailable):
        WindowsDpapiProtector().protect(b"token")
    with pytest.raises(DpapiUnavailable):
        production_protector()


@pytest.mark.windows_only
def test_windows_dpapi_roundtrip_is_real_cryptprotect():
    protector = production_protector()
    blob = protector.protect(b"token-bytes")
    assert blob != b"token-bytes"
    assert protector.unprotect(blob) == b"token-bytes"


def test_read_tool_blocks_token_file_and_names_the_terminal_gap():
    home = get_hermes_home()
    path = home / "mcp-tokens" / "feishu-base-export" / "abc.bin"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"ciphertext")
    message = get_read_block_error(str(path))
    assert message is not None
    assert "cannot be read" in message
    assert "terminal" in message
    assert "not a security boundary" in message


def test_pin_worker_thread_sees_parent_contextvar():
    """Upstream 5eb99eb2 copies contextvars into tool workers.

    This is not evidence about a992c8f1: that commit's tool_executor.py and
    model_tools.py were not available to compare.
    """
    from tools.thread_context import propagate_context_to_thread

    var = contextvars.ContextVar("feishu_base_export_probe", default="")
    var.set("from-parent")
    seen = {}

    def target():
        seen["value"] = var.get()

    propagate_context_to_thread(target)()
    assert seen["value"] == "from-parent"


def test_official_hosts_only_and_no_private_or_redirect_targets():
    assert parse_official_https("https://open.feishu.cn/open-apis/drive/v1/export_tasks").startswith("https://open.feishu.cn/")
    for bad in (
        "http://open.feishu.cn/open-apis/drive/v1/export_tasks",
        "https://user:pw@open.feishu.cn/x",
        "https://127.0.0.1/x",
        "https://10.1.2.3/x",
        "https://open.feishu.cn.evil.example/x",
        "https://evil.example/x",
        "https://open.feishu.cn:444/x",
    ):
        with pytest.raises(UrlRejected):
            parse_official_https(bad)


def _xlsx(name="[Content_Types].xml", payload=b"<Types/>", extra=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(name, payload)
        if extra:
            for item_name, item_payload in extra:
                archive.writestr(item_name, item_payload)
    return buffer.getvalue()


def test_xlsx_guard_rejects_bad_magic_traversal_and_highly_compressible_bomb():
    with pytest.raises(UnsafeFile):
        assert_safe_xlsx(b"not-a-zip")
    with pytest.raises(UnsafeFile):
        assert_safe_xlsx(_xlsx("../evil.xml", b"x"))
    bomb = _xlsx("[Content_Types].xml", b"\0" * 1_200_000)
    with pytest.raises(UnsafeFile):
        assert_safe_xlsx(bomb)
    assert_safe_xlsx(_xlsx())


class _Script:
    def __init__(self, steps):
        self.steps = list(steps)
        self.calls = []

    def __call__(self, method, url, user_token, body):
        self.calls.append((method, url, user_token, body))
        status, payload = self.steps.pop(0)
        location = payload if isinstance(payload, str) and status in range(300, 400) else None
        data = payload if isinstance(payload, bytes) else b""
        return SimpleNamespace(status=status, body=data, location=location)


def test_export_omits_sub_id_refuses_redirects_and_redacts_tokens():
    good = _xlsx()
    script = _Script([
        (200, json.dumps({"code": 0, "data": {"ticket": "12345"}}).encode()),
        (200, json.dumps({"code": 0, "data": {"result": {"job_status": 2}}}).encode()),
        (200, json.dumps({"code": 0, "data": {"result": {
            "job_status": 0, "file_token": "boxcnxe5OdjlAkNgSNdsJvabcef", "file_size": len(good),
        }}}).encode()),
        (200, good),
    ])
    data = export_bitable_xlsx(user_token="u-secret-value", base_token=BASE, transport=script, sleep=lambda _s: None)
    assert data[:2] == b"PK"
    assert script.calls[0][0] == "POST"
    assert script.calls[0][2] == "u-secret-value"
    assert "sub_id" not in script.calls[0][3]
    assert script.calls[0][3]["type"] == "bitable"
    assert script.calls[0][3]["file_extension"] == "xlsx"
    assert all(call[1].startswith("https://open.feishu.cn/") for call in script.calls)
    assert "u-secret-value" not in script.calls[0][1]

    redirected = _Script([(302, "https://127.0.0.1/steal")])
    with pytest.raises(ExportError) as caught:
        export_bitable_xlsx(user_token="u-secret-value", base_token=BASE, transport=redirected, sleep=lambda _s: None)
    assert "u-secret-value" not in str(caught.value)
    assert len(redirected.calls) == 1

    def explode(method, url, user_token, body):
        raise RuntimeError(f"Bearer {user_token} code=abc refresh_token=r1")

    with pytest.raises(ExportError) as caught:
        export_bitable_xlsx(user_token="u-secret-value", base_token=BASE, transport=explode, sleep=lambda _s: None)
    text = str(caught.value)
    assert "u-secret-value" not in text
    assert "refresh_token=r1" not in text
    assert redact("Bearer u-secret-value", secrets=["u-secret-value"]) == "Bearer [redacted]"


def test_permission_failure_does_not_download():
    script = _Script([
        (200, json.dumps({"code": 0, "data": {"ticket": "9"}}).encode()),
        (200, json.dumps({"code": 0, "data": {"result": {"job_status": 110, "job_error_msg": "no perm u-secret-value"}}}).encode()),
    ])
    with pytest.raises(ExportError) as caught:
        export_bitable_xlsx(user_token="u-secret-value", base_token=BASE, transport=script, sleep=lambda _s: None)
    assert len(script.calls) == 2
    assert "u-secret-value" not in str(caught.value)
    assert "110" in str(caught.value)


def test_chart_parser_bounds_and_renderer_emits_png_and_pdf():
    with pytest.raises(EmptyAggregate):
        parse_aggregate({"dimensions": [{"field_name": "城市", "alias": "dim_a"}], "measures": [{"field_name": "数", "alias": "me_a", "aggregation": "sum"}], "main_data": []})
    parsed = parse_aggregate({
        "dimensions": [{"field_name": "城市", "alias": "dim_a"}],
        "measures": [{"field_name": "数", "alias": "me_a", "aggregation": "sum"}],
        "main_data": [{"dim_a": "杭州", "me_a": 3}, {"dim_a": "宁波", "me_a": 1}],
    })
    png = render_chart(parsed, "png")
    pdf = render_chart(parsed, "pdf")
    assert png.startswith(b"\x89PNG")
    assert pdf.startswith(b"%PDF")
    width, _height, raw = render_pixels(parsed)
    ink = raw[((12 * width) + 66) * 3:((12 * width) + 66) * 3 + 3]
    assert ink != b"\xff\xff\xff"
    oversized = {
        "dimensions": [{"field_name": "x", "alias": "d"}],
        "measures": [{"field_name": "y", "alias": "m", "aggregation": "sum"}],
        "main_data": [{"d": "n", "m": 1}] * 501,
    }
    with pytest.raises(PayloadBoundsError):
        parse_aggregate(oversized)


def test_register_records_binding_without_dropping_the_message():
    from plugins.feishu_base_export import register
    from plugins.feishu_base_export.binding import default_store, reset_default_store

    reset_default_store()

    class Ctx:
        def __init__(self):
            self.tools = []
            self.hooks = []

        def register_tool(self, **kwargs):
            self.tools.append(kwargs)

        def register_hook(self, name, callback):
            self.hooks.append((name, callback))

    ctx = Ctx()
    register(ctx)
    assert ctx.tools[0]["name"] == "feishu_base_export"
    names = [name for name, _callback in ctx.hooks]
    assert names == ["pre_gateway_dispatch", "transform_llm_output"]
    assert ctx.hooks[0][0] == "pre_gateway_dispatch"
    assert ctx.hooks[0][1](event=_event(message_id="om_hook")) is None
    found = default_store().match(message_id="om_hook", chat_id="oc_1", chat_type="dm", platform="feishu")
    assert found is not None and found.open_id == OPEN_ID
