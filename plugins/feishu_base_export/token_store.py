"""Per-open_id token file under the existing mcp-tokens deny tree."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


class LoopProtector:
    """Test double. Not DPAPI and not used by production_protector."""

    name = "test-loop"

    def protect(self, data: bytes) -> bytes:
        return bytes(byte ^ 0x5A for byte in data)

    def unprotect(self, data: bytes) -> bytes:
        return self.protect(data)


class TokenStore:
    def __init__(self, home: Path, protector) -> None:
        self._home = Path(home)
        self._protector = protector
        self._dir = self._home / "mcp-tokens" / "feishu-base-export"

    def path_for(self, open_id: str) -> Path:
        digest = hashlib.sha256(open_id.encode("utf-8")).hexdigest()[:32]
        return self._dir / f"{digest}.bin"

    def save(self, open_id: str, payload: dict) -> None:
        raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        wrapped = self._protector.protect(raw)
        path = self.path_for(open_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(path.parent, 0o700)
        path.write_bytes(wrapped)
        os.chmod(path, 0o600)

    def load(self, open_id: str) -> dict:
        wrapped = self.path_for(open_id).read_bytes()
        return json.loads(self._protector.unprotect(wrapped).decode("utf-8"))
