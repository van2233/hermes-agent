"""Opaque one-time OAuth state plus PKCE. The state string does not carry open_id."""

from __future__ import annotations

import base64
import hashlib
import secrets
import threading
from dataclasses import dataclass

from plugins.feishu_base_export.identity import is_app_open_id


@dataclass(frozen=True)
class StateRecord:
    open_id: str
    verifier: str
    challenge: str


class StateStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: dict[str, tuple[StateRecord, float]] = {}

    def issue(self, *, open_id: str, now: float, ttl_seconds: int = 300) -> str:
        if not is_app_open_id(open_id):
            raise ValueError("open_id")
        verifier, challenge = pkce_pair()
        record = StateRecord(open_id=open_id, verifier=verifier, challenge=challenge)
        state = secrets.token_urlsafe(32)
        if open_id in state:
            state = secrets.token_urlsafe(32)
        with self._lock:
            self._items[state] = (record, now + ttl_seconds)
        return state

    def peek(self, state: str, *, now: float) -> StateRecord | None:
        with self._lock:
            item = self._items.get(state)
        if item is None:
            return None
        record, expires_at = item
        if now >= expires_at:
            return None
        return record

    def challenge_of(self, state: str) -> str | None:
        with self._lock:
            item = self._items.get(state)
        if item is None:
            return None
        return item[0].challenge

    def consume(self, state: str, *, now: float) -> StateRecord | None:
        with self._lock:
            item = self._items.pop(state, None)
        if item is None:
            return None
        record, expires_at = item
        if now >= expires_at:
            return None
        return record


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    if not 43 <= len(verifier) <= 128:
        raise RuntimeError("pkce verifier length")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge
