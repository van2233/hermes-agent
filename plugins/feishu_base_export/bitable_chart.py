"""Aggregate one configured Base table with the documented records API.

Dashboard block data is not a documented public HTTP API. The list-dashboards
endpoint only returns block ids and names:
https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/reference/bitable-v1/app-dashboard/list
Records are read with the documented search API:
https://open.feishu.cn/document/docs/bitable-v1/app-table-record/search
Table names are resolved with:
https://open.feishu.cn/document/server-docs/docs/bitable-v1/app-table/list
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlencode

from .bitable_xlsx import ExportError
from .chart_data import ChartTable, EmptyAggregate, PayloadBoundsError
from .http_guard import parse_official_https
from .redact import redact

_TABLE_ID = re.compile(r"^tbl[A-Za-z0-9]{4,30}$")
_AGGS = frozenset({"sum", "count", "avg"})
_PAGE = 500
_MAX_RECORDS = 2000
_MAX_BARS = 40


def check_chart_args(table: str, category: str, value: str, agg: str) -> None:
    kind = agg or "sum"
    if kind not in _AGGS:
        raise ExportError("agg")
    _label(table)
    _label(category)
    if kind != "count":
        _label(value)


def chart_table(transport, *, token: str, base_token: str, host: str, table: str, category: str, value: str, agg: str) -> ChartTable:
    check_chart_args(table, category, value, agg)
    kind = agg or "sum"
    category = _label(category)
    value_name = _label(value) if kind != "count" or value else ""
    table_id = _table_id(transport, token, base_token, host, _label(table))
    rows = _records(transport, token, base_token, host, table_id)
    return _aggregate(rows, category=category, value=value_name, agg=kind, measure=value_name or category)


def _table_id(transport, token: str, base_token: str, host: str, table: str) -> str:
    if _TABLE_ID.fullmatch(table):
        return table
    payload = _json(transport, token, "GET", f"https://{host}/open-apis/bitable/v1/apps/{base_token}/tables?page_size=100", None)
    matches = []
    for item in ((payload.get("data") or {}).get("items") or []):
        if isinstance(item, dict) and item.get("name") == table and _TABLE_ID.fullmatch(str(item.get("table_id") or "")):
            matches.append(item["table_id"])
    if len(matches) != 1:
        raise ExportError("table")
    return matches[0]


def _records(transport, token: str, base_token: str, host: str, table_id: str) -> list[dict]:
    rows = []
    page = ""
    while True:
        query = {"page_size": _PAGE}
        if page:
            query["page_token"] = page
        url = f"https://{host}/open-apis/bitable/v1/apps/{base_token}/tables/{table_id}/records/search?{urlencode(query)}"
        payload = _json(transport, token, "POST", url, {})
        data = payload.get("data") or {}
        items = data.get("items") or []
        if not isinstance(items, list):
            raise ExportError("records")
        rows.extend(item for item in items if isinstance(item, dict))
        if len(rows) > _MAX_RECORDS:
            raise ExportError("too many records")
        if not data.get("has_more"):
            return rows
        page = str(data.get("page_token") or "")
        if not page:
            raise ExportError("page")


def _aggregate(rows: list[dict], *, category: str, value: str, agg: str, measure: str) -> ChartTable:
    buckets: dict[str, list[float]] = {}
    for row in rows:
        fields = row.get("fields") if isinstance(row.get("fields"), dict) else {}
        label = _cell_text(fields.get(category))
        if not label:
            continue
        buckets.setdefault(label, [])
        if agg == "count":
            buckets[label].append(1.0)
            continue
        number = _cell_number(fields.get(value))
        if number is not None:
            buckets[label].append(number)
    if not buckets:
        raise EmptyAggregate("no rows")
    if len(buckets) > _MAX_BARS:
        raise PayloadBoundsError("bars")
    labels = tuple(buckets)
    if agg == "avg":
        values = tuple(sum(items) / len(items) if items else 0.0 for items in buckets.values())
    else:
        values = tuple(sum(items) for items in buckets.values())
    return ChartTable(labels=labels, values=values, dimension=category, measure=measure)


def _json(transport, token: str, method: str, url: str, body) -> dict:
    safe = parse_official_https(url)
    try:
        response = transport(method, safe, token, body)
    except ExportError:
        raise
    except Exception as exc:
        raise ExportError(redact(str(exc), secrets=[token])) from None
    if int(getattr(response, "status", 0)) != 200:
        raise ExportError("chart http")
    try:
        payload = json.loads(getattr(response, "body", b"").decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise ExportError("chart response") from None
    if not isinstance(payload, dict) or payload.get("code") != 0:
        raise ExportError("chart response")
    return payload


def _label(value: str) -> str:
    text = str(value or "").strip()
    if not text or len(text) > 80 or "://" in text or "/" in text or "\\" in text:
        raise ExportError("field")
    return text


def _cell_text(value) -> str:
    if value is None or isinstance(value, bool):
        return ""
    if isinstance(value, str):
        return value.strip()[:200]
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        return _cell_text(value.get("text", value.get("name", value.get("value"))))
    if isinstance(value, list):
        return "".join(_cell_text(item) for item in value)[:200]
    return ""


def _cell_number(value) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    if isinstance(value, dict):
        return _cell_number(value.get("value", value.get("text")))
    if isinstance(value, list) and value:
        return _cell_number(value[0])
    return None
