"""Stage one private-DM attachment and force it into the final reply text.

The gateway sends MEDIA tags in the final response to the inbound chat_id.
Auto-append only trusts text_to_speech and image_generate, so this plugin
writes its own single tag here instead of editing that core allowlist.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from pathlib import Path

from hermes_constants import get_hermes_dir

_MEDIA = re.compile(r"MEDIA:\S+")
_ledger_lock = threading.Lock()
_ledger: dict[str, "Staged"] = {}


@dataclass(frozen=True)
class Staged:
    kind: str
    text: str
    path: str = ""


def default_output_dir() -> Path:
    return get_hermes_dir("cache/documents", "document_cache") / "feishu-base-export"


def stage_text(message_id: str, text: str) -> None:
    _put(message_id, Staged(kind="text", text=text))


def stage_file(message_id: str, path: str, caption: str) -> None:
    _put(message_id, Staged(kind="file", text=caption, path=path))


def reset_ledger() -> None:
    with _ledger_lock:
        _ledger.clear()


def transform_response(response_text: str, *, message_id: str) -> str | None:
    staged = _pop(message_id)
    if staged is None:
        return None
    if staged.kind == "text":
        return staged.text
    cleaned = _MEDIA.sub("", response_text or "").strip()
    return f"{cleaned}\n{staged.text}\nMEDIA:{staged.path}".strip()


def _put(message_id: str, staged: Staged) -> None:
    if not message_id:
        return
    with _ledger_lock:
        _ledger[message_id] = staged


def _pop(message_id: str) -> Staged | None:
    if not message_id:
        return None
    with _ledger_lock:
        return _ledger.pop(message_id, None)
