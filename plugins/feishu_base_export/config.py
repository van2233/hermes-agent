"""Deploy-time settings. Missing values are setup-required, not a silent export."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_SCOPES = "offline_access drive:export:readonly docs:document:export"


@dataclass(frozen=True)
class RuntimeConfig:
    app_id: str = ""
    app_secret: str = ""
    redirect_uri: str = ""
    api_host: str = "open.feishu.cn"
    accounts_host: str = "accounts.feishu.cn"
    scopes: str = DEFAULT_SCOPES

    def missing(self) -> list[str]:
        missing = []
        if not self.app_id:
            missing.append("FEISHU_APP_ID")
        if not self.app_secret:
            missing.append("FEISHU_APP_SECRET")
        if not self.redirect_uri:
            missing.append("redirect_uri")
        return missing


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
    )


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
