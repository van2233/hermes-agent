"""Admin settings for the bot export. The Base token is not taken from the model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeConfig:
    app_id: str = ""
    app_secret: str = ""
    base_token: str = ""
    api_host: str = "open.feishu.cn"

    def missing(self) -> list[str]:
        missing = []
        if not self.app_id:
            missing.append("FEISHU_APP_ID")
        if not self.app_secret:
            missing.append("FEISHU_APP_SECRET")
        if not self.base_token:
            missing.append("base_token")
        return missing


def production_config() -> RuntimeConfig:
    from agent.secret_scope import get_secret

    settings = _plugin_settings()
    return RuntimeConfig(
        app_id=str(get_secret("FEISHU_APP_ID", "") or ""),
        app_secret=str(get_secret("FEISHU_APP_SECRET", "") or ""),
        base_token=str(settings.get("base_token") or ""),
        api_host=str(settings.get("api_host") or "open.feishu.cn"),
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
