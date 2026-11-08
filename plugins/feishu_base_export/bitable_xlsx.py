"""Whole-Base xlsx export against the documented Drive export-task API.

https://open.feishu.cn/document/server-docs/docs/drive-v1/export_task/create
Query and download pages are the other two steps. CSV sub_id is never sent.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from plugins.feishu_base_export.http_guard import OFFICIAL_HOSTS, parse_official_https
from plugins.feishu_base_export.redact import redact
from plugins.feishu_base_export.xlsx_safe import MAX_BYTES, assert_safe_xlsx

_BASE_TOKEN = re.compile(r"^[A-Za-z0-9]{1,27}$")
_TICKET = re.compile(r"^[0-9]{1,32}$")
_FILE_TOKEN = re.compile(r"^[A-Za-z0-9]{1,64}$")
_CREATE = "/open-apis/drive/v1/export_tasks"


class ExportError(RuntimeError):
    pass


def export_bitable_xlsx(*, access_token: str, base_token: str, transport: Callable, host: str = "open.feishu.cn", sleep: Callable[[float], None] = lambda _seconds: None, attempts: int = 6) -> bytes:
    if host not in OFFICIAL_HOSTS or not _BASE_TOKEN.fullmatch(base_token or "") or not access_token:
        raise ExportError("rejected request")
    created = _json_call(
        transport, access_token, "POST", f"https://{host}{_CREATE}",
        {"file_extension": "xlsx", "token": base_token, "type": "bitable"},
    )
    ticket = str((created.get("data") or {}).get("ticket") or "")
    if created.get("code") != 0 or not _TICKET.fullmatch(ticket):
        detail = str(created.get("msg") or "")
        raise ExportError(redact(f"export create failed: {detail}".strip(), secrets=[access_token]))
    for _ in range(attempts):
        polled = _json_call(
            transport, access_token, "GET",
            f"https://{host}{_CREATE}/{ticket}?token={base_token}", None,
        )
        result = ((polled.get("data") or {}).get("result") or {}) if polled.get("code") == 0 else {}
        status = result.get("job_status")
        if status in (1, 2):
            sleep(1)
            continue
        if status != 0:
            detail = str(result.get("job_error_msg") or "")
            raise ExportError(redact(f"export job failed: {status} {detail}".strip(), secrets=[access_token]))
        return _download(transport, access_token, host, result)
    raise ExportError("export timed out")


def _download(transport, access_token: str, host: str, result: dict) -> bytes:
    file_token = str(result.get("file_token") or "")
    file_size = int(result.get("file_size") or 0)
    if not _FILE_TOKEN.fullmatch(file_token) or file_size <= 0 or file_size > MAX_BYTES:
        raise ExportError("export file rejected")
    blob = _call(
        transport, access_token, "GET",
        f"https://{host}{_CREATE}/file/{file_token}/download", None,
    )
    if len(blob) != file_size:
        raise ExportError("size mismatch")
    assert_safe_xlsx(blob)
    return blob


def _json_call(transport, access_token: str, method: str, url: str, body) -> dict:
    raw = _call(transport, access_token, method, url, body)
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise ExportError("export response") from None
    if not isinstance(parsed, dict):
        raise ExportError("export response")
    return parsed


def _call(transport, access_token: str, method: str, url: str, body) -> bytes:
    safe_url = parse_official_https(url)
    try:
        response = transport(method, safe_url, access_token, body)
    except ExportError:
        raise
    except Exception as exc:
        raise ExportError(redact(str(exc), secrets=[access_token])) from None
    status = int(getattr(response, "status", 0))
    if 300 <= status < 400:
        raise ExportError("redirect refused")
    if status != 200:
        raise ExportError(f"http {status}")
    data = getattr(response, "body", b"")
    if not isinstance(data, bytes):
        raise ExportError("export response")
    return data
