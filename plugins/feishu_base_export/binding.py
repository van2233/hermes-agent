"""Explicit DM binding. The model cannot supply the open_id that selects a token."""

from __future__ import annotations

import threading
from dataclasses import dataclass

from .identity import extract_sender_open_id, is_app_open_id

_store_lock = threading.Lock()
_default: "BindingStore | None" = None


@dataclass(frozen=True)
class TurnBinding:
    message_id: str
    open_id: str
    chat_id: str
    chat_type: str
    platform: str


class BindingStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, TurnBinding] = {}

    def put(self, binding: TurnBinding) -> None:
        if binding.platform != "feishu" or binding.chat_type != "dm":
            raise ValueError("refused")
        if not is_app_open_id(binding.open_id) or not binding.message_id or not binding.chat_id:
            raise ValueError("refused")
        with self._lock:
            self._items[binding.message_id] = binding

    def match(self, *, message_id: str, chat_id: str, chat_type: str, platform: str) -> TurnBinding | None:
        if not message_id or chat_type != "dm" or platform != "feishu":
            return None
        with self._lock:
            found = self._items.get(message_id)
        if found is None:
            return None
        if found.chat_id != chat_id or found.chat_type != chat_type or found.platform != platform:
            return None
        return found


def default_store() -> BindingStore:
    global _default
    with _store_lock:
        if _default is None:
            _default = BindingStore()
        return _default


def reset_default_store() -> None:
    global _default
    with _store_lock:
        _default = BindingStore()


def _text(obj, name) -> str:
    if isinstance(obj, dict):
        value = obj.get(name)
    else:
        value = getattr(obj, name, None)
    platform_value = getattr(value, "value", value)
    return str(platform_value or "")


def consider_event(event, store: BindingStore) -> TurnBinding | None:
    source = event.get("source") if isinstance(event, dict) else getattr(event, "source", None)
    if _text(source, "platform").lower() != "feishu":
        return None
    if _text(source, "chat_type") != "dm":
        return None
    raw = event.get("raw_message") if isinstance(event, dict) else getattr(event, "raw_message", None)
    raw_event = raw.get("event") if isinstance(raw, dict) else getattr(raw, "event", None)
    message = raw_event.get("message") if isinstance(raw_event, dict) else getattr(raw_event, "message", None)
    raw_chat = _text(message, "chat_type") if message is not None else ""
    if raw_chat and raw_chat != "p2p":
        return None
    open_id = extract_sender_open_id(raw)
    message_id = _text(event, "message_id")
    chat_id = _text(source, "chat_id")
    if not open_id or not message_id or not chat_id:
        return None
    binding = TurnBinding(
        message_id=message_id, open_id=open_id, chat_id=chat_id, chat_type="dm", platform="feishu",
    )
    store.put(binding)
    return binding


def on_pre_gateway_dispatch(event=None, **kwargs):
    """Record a DM binding when the raw event has an app open_id. Never drops the message."""
    if event is None:
        return None
    try:
        consider_event(event, default_store())
    except (AttributeError, TypeError, ValueError):
        return None
    return None
