"""App-scoped Feishu open_id checks. Tenant user_id and union_id are not bindings."""

from __future__ import annotations

import re

_OPEN_ID = re.compile(r"^ou[_-][A-Za-z0-9]{8,64}$")


def is_app_open_id(value: object) -> bool:
    return isinstance(value, str) and _OPEN_ID.fullmatch(value) is not None


def _get(obj, name):
    if isinstance(obj, dict):
        return obj.get(name)
    return getattr(obj, name, None)


def extract_sender_open_id(raw_message) -> str | None:
    event = _get(raw_message, "event")
    sender = _get(event, "sender")
    sender_id = _get(sender, "sender_id")
    open_id = _get(sender_id, "open_id")
    if is_app_open_id(open_id):
        return open_id
    return None
