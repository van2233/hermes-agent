"""Deploy-time settings. Missing HTTPS callback settings are setup-required."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit

DEFAULT_SCOPES = "offline_access drive:export:readonly"
CALLBACK_PATH = "/feishu/oauth/callback"


@dataclass(frozen=True)
class RuntimeConfig:
    app_id: str = ""
    app_secret: str = ""
    redirect_uri: str = ""
    api_host: str = "open.feishu.cn"
    accounts_host: str = "accounts.feishu.cn"
    scopes: str = DEFAULT_SCOPES
    listen_host: str = "127.0.0.1"
    listen_port: int = 8766
    callback_enabled: bool = False

    def missing(self) -> list[str]:
        missing = []
        if not self.app_id:
            missing.append("FEISHU_APP_ID")
        if not self.app_secret:
            missing.append("FEISHU_APP_SECRET")
        if not self.redirect_uri:
            missing.append("redirect_uri")
        return missing

    def callback_problems(self) -> list[str]:
        problems = self.missing()
        kind = redirect_class(self.redirect_uri, self.listen_port)
        if self.redirect_uri and not kind:
            problems.append("redirect_uri_https")
        if kind == "local" and self.listen_host != "127.0.0.1":
            problems.append("listen_redirect_mismatch")
        if not loopback_host(self.listen_host):
            problems.append("listen_host_loopback")
        if not isinstance(self.listen_port, int) or not 1 <= self.listen_port <= 65535:
            problems.append("listen_port")
        if not self.callback_enabled:
            problems.append("callback_enabled")
        return problems


def loopback_host(host: str) -> bool:
    value = (host or "").strip().lower()
    if value in {"localhost", "127.0.0.1", "::1"}:
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def redirect_class(uri: str, listen_port: int) -> str:
    """``local`` is same-machine HTTP. ``remote`` is a public HTTPS name. Otherwise empty."""
    parts = urlsplit(uri or "")
    if parts.username or parts.password or parts.query or parts.fragment:
        return ""
    if parts.scheme == "http" and (parts.hostname or "").lower() == "127.0.0.1":
        if parts.port == listen_port and parts.path == CALLBACK_PATH:
            return "local"
        return ""
    if public_https(uri):
        return "remote"
    return ""


def public_https(uri: str) -> bool:
    parts = urlsplit(uri or "")
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or not parts.path or parts.path == "/":
        return False
    if loopback_host(host):
        return False
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return True
    return False


def production_config() -> RuntimeConfig:
    from agent.secret_scope import get_secret

    settings = _plugin_settings()
    return RuntimeConfig(
        app_id=str(get_secret("FEISHU_APP_ID", "") or ""),
        app_secret=str(get_secret("FEISHU_APP_SECRET", "") or ""),
        redirect_uri=str(settings.get("redirect_uri") or ""),
        api_host=str(settings.get("api_host") or "open.feishu.cn"),
        accounts_host=str(settings.get("accounts_host") or "accounts.feishu.cn"),
        scopes=str(settings.get("scopes") or DEFAULT_SCOPES),
        listen_host=str(settings.get("listen_host") or "127.0.0.1"),
        listen_port=_port(settings.get("listen_port")),
        callback_enabled=_flag(settings.get("callback_enabled")),
    )


def _flag(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes"}


def _port(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 8766


def _plugin_settings() -> dict:
    try:
        from hermes_cli.config import load_config
    except Exception:
        return {}
    loaded = load_config() or {}
    entries = (loaded.get("plugins") or {}).get("entries") or {}
    for key in ("feishu-base-export", "feishu_base_export"):
        entry = entries.get(key) or {}
        settings = entry.get("settings") or entry.get("config") or {}
        if isinstance(settings, dict):
            return settings
    return {}
