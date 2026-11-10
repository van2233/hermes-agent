"""Load the plugin the way a profile user plugin is loaded, not as repo code."""

from __future__ import annotations

import importlib
import shutil
import sys
from pathlib import Path

import pytest
import yaml

from hermes_constants import get_hermes_home
from toolsets import TOOLSETS, _HERMES_CORE_TOOLS


def test_profile_plugin_registers_without_the_repo_on_sys_path():
    builtin = set(_HERMES_CORE_TOOLS)
    for spec in TOOLSETS.values():
        builtin.update(spec.get("tools") or [])
    assert "feishu_base_export" not in builtin

    root = Path(__file__).resolve().parents[2]
    home = get_hermes_home()
    dest = home / "plugins" / "feishu_base_export"
    shutil.copytree(
        root / "plugins" / "feishu_base_export", dest,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (home / "config.yaml").write_text(
        yaml.safe_dump({"plugins": {"enabled": ["feishu-base-export"]}}),
        encoding="utf-8",
    )

    sys.path[:] = [entry for entry in sys.path if not _is_repo_root(entry, root)]
    assert not any(_is_repo_root(entry, root) for entry in sys.path)
    for name in list(sys.modules):
        if name == "plugins" or name.startswith("plugins."):
            del sys.modules[name]
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("plugins.feishu_base_export")

    from hermes_cli.plugins import PluginManager

    manager = PluginManager()
    manager.discover_and_load()
    loaded = manager._plugins["feishu-base-export"]
    assert loaded.enabled, loaded.error
    assert loaded.tools_registered == ["feishu_base_export"]
    assert "pre_gateway_dispatch" in loaded.hooks_registered
    assert "transform_llm_output" in loaded.hooks_registered
    assert "hermes_plugins.feishu_base_export" in sys.modules


def _is_repo_root(entry: str, root: Path) -> bool:
    if not entry:
        return False
    try:
        return Path(entry).resolve() == root
    except OSError:
        return False
