"""Bot tenant token. This path never requests a user access token."""

from __future__ import annotations

import json

from .bitable_xlsx import ExportError
from .http_guard import parse_official_https
from .redact import redact

_TENANT = "/open-apis/auth/v3/tenant_access_token/internal"


def tenant_access_token(transport, config) -> str:
    url = parse_official_https(f"https://{config.api_host}{_TENANT}")
    secret = config.app_secret
    try:
        response = transport("POST", url, "", {"app_id": config.app_id, "app_secret": secret})
    except Exception as exc:
        raise ExportError(redact(str(exc), secrets=[secret])) from None
    if int(getattr(response, "status", 0)) != 200:
        raise ExportError("tenant token http")
    try:
        payload = json.loads(getattr(response, "body", b"").decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError):
        raise ExportError("tenant token response") from None
    token = payload.get("tenant_access_token") if isinstance(payload, dict) else ""
    if payload.get("code") != 0 or not isinstance(token, str) or not token:
        raise ExportError("tenant token missing")
    return token
