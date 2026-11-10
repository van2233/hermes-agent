"""Strip credentials from errors before they reach logs or the model."""

from __future__ import annotations

import re
from collections.abc import Sequence

_BEARER = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-+/=]+")
_PARAM = re.compile(
    r"(?i)\b(access_token|refresh_token|client_secret|device_code|code|user_code)=([^&\s]+)"
)


def redact(text: str, secrets: Sequence[str] = ()) -> str:
    out = text or ""
    for secret in secrets:
        if isinstance(secret, str) and len(secret) >= 6:
            out = out.replace(secret, "[redacted]")
    out = _BEARER.sub(r"\1[redacted]", out)
    return _PARAM.sub(r"\1=[redacted]", out)
