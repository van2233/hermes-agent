"""Authorization-code + PKCE against the documented Feishu user-token endpoints."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlencode, urlsplit

from plugins.feishu_base_export.config import RuntimeConfig
from plugins.feishu_base_export.http_guard import parse_official_https
from plugins.feishu_base_export.redact import redact

_ACCOUNTS = frozenset({"accounts.feishu.cn", "accounts.larksuite.com"})


class OAuthError(RuntimeError):
    pass


def build_authorize_url(config: RuntimeConfig, *, state: str, challenge: str) -> str:
    if config.accounts_host not in _ACCOUNTS:
        raise OAuthError("accounts host")
    query = urlencode({
        "client_id": config.app_id,
        "response_type": "code",
        "redirect_uri": config.redirect_uri,
        "scope": config.scopes,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    return f"https://{config.accounts_host}/open-apis/authen/v1/authorize?{query}"


def parse_callback(text: str, redirect_uri: str) -> tuple[str, str] | None:
    prefix = urlsplit(redirect_uri)
    for match in _urls(text):
        parts = urlsplit(match)
        if parts.scheme != prefix.scheme or parts.netloc != prefix.netloc:
            continue
        if not parts.path.startswith(prefix.path or "/"):
            continue
        query = parse_qs(parts.query)
        code = (query.get("code") or [""])[0]
        state = (query.get("state") or [""])[0]
        if code and state:
            return code, state
    return None


def exchange_code(transport, config: RuntimeConfig, *, code: str, verifier: str) -> dict:
    return _token_call(transport, config, {
        "grant_type": "authorization_code",
        "client_id": config.app_id,
        "client_secret": config.app_secret,
        "code": code,
        "redirect_uri": config.redirect_uri,
        "code_verifier": verifier,
    }, secrets=(config.app_secret, code))


def refresh_access(transport, config: RuntimeConfig, refresh_token: str) -> dict:
    return _token_call(transport, config, {
        "grant_type": "refresh_token",
        "client_id": config.app_id,
        "client_secret": config.app_secret,
        "refresh_token": refresh_token,
    }, secrets=(config.app_secret, refresh_token))


def user_open_id(transport, config: RuntimeConfig, access_token: str) -> str:
    url = parse_official_https(f"https://{config.api_host}/open-apis/authen/v1/user_info")
    payload = _json_body(transport, "GET", url, access_token, None, secrets=(access_token,))
    data = payload.get("data") if isinstance(payload, dict) else None
    open_id = data.get("open_id") if isinstance(data, dict) else ""
    if payload.get("code") != 0 or not isinstance(open_id, str) or not open_id:
        raise OAuthError("user_info failed")
    return open_id


def _token_call(transport, config: RuntimeConfig, body: dict, *, secrets) -> dict:
    url = parse_official_https(f"https://{config.api_host}/open-apis/authen/v2/oauth/token")
    payload = _json_body(transport, "POST", url, "", body, secrets=secrets)
    access = payload.get("access_token") if isinstance(payload, dict) else None
    refresh = payload.get("refresh_token") if isinstance(payload, dict) else None
    if payload.get("code") not in (0, None) or not access or not refresh:
        raise OAuthError("token exchange failed")
    return {
        "access_token": str(access),
        "refresh_token": str(refresh),
        "expires_in": int(payload.get("expires_in") or 0),
        "refresh_expires_in": int(payload.get("refresh_token_expires_in") or 0),
        "scope": str(payload.get("scope") or ""),
    }


def _json_body(transport, method, url, user_token, body, *, secrets) -> dict:
    try:
        response = transport(method, url, user_token, body)
    except OAuthError:
        raise
    except Exception as exc:
        raise OAuthError(redact(str(exc), secrets=secrets)) from None
    status = int(getattr(response, "status", 0))
    if 300 <= status < 400:
        raise OAuthError("redirect refused")
    if status != 200:
        raise OAuthError(f"http {status}")
    raw = getattr(response, "body", b"")
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError, AttributeError):
        raise OAuthError("oauth response") from None
    if not isinstance(parsed, dict):
        raise OAuthError("oauth response")
    return parsed


def _urls(text: str):
    import re
    for match in re.finditer(r"https?://\S+", text or ""):
        yield match.group(0).rstrip(").,，")
