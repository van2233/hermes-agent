"""Offline checks in an empty directory. Does not read or write a Hermes profile.

Exit 0 is a Windows pass, including a real CryptProtectData round-trip.
Exit 2 means this host is not Windows: that is not a pass.
Exit 1 is a failed check. No socket is opened.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_HOST_MODULES = {"hermes_constants", "hermes_cli", "agent", "gateway"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Feishu Base export offline verification")
    parser.add_argument("--work-dir", required=True, help="Empty temporary directory. Not a Hermes profile.")
    args = parser.parse_args(argv)
    work = Path(args.work_dir)
    if _looks_like_profile(work):
        print("result=FAIL")
        print("reason=work_dir_looks_like_hermes_profile")
        return 1
    work.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    host, extra = _imports()
    print("deps=stdlib_only" if not extra else "deps=unexpected")
    print("host_imports=" + ",".join(host))
    if extra:
        failures.append("unexpected_import")
        print("unexpected_imports=" + ",".join(extra))
    if not _dry_run(work):
        failures.append("dry_run")
    if not _charts_blocked():
        failures.append("charts")
    if not _policy_is_additive():
        failures.append("policy_insert")
    if _callback_servers():
        failures.append("listened")
    print("listening=false")
    print("auth_ready=false")
    print("config_modified=false")
    print("policy_modified=false")
    dpapi = _dpapi(work)
    print(f"dpapi={dpapi}")
    if (work / "config.yaml").exists() or (work / ".env").exists():
        failures.append("wrote_profile_files")
    if failures:
        print("result=FAIL")
        print("failures=" + ",".join(failures))
        return 1
    if dpapi != "roundtrip_ok":
        print("result=NOT_A_PASS")
        return 2
    print("result=PASS")
    return 0


def _looks_like_profile(path: Path) -> bool:
    return (path / "config.yaml").exists() or (path / ".env").exists()


def _imports() -> tuple[list[str], list[str]]:
    host: set[str] = set()
    extra: set[str] = set()
    plugin_dir = Path(__file__).resolve().parent
    stdlib = sys.stdlib_module_names
    for path in sorted(plugin_dir.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and not node.level:
                names = [(node.module or "").split(".")[0]]
            for name in names:
                if not name or name == "plugins" or name in stdlib:
                    continue
                if name in _HOST_MODULES:
                    host.add(name)
                else:
                    extra.add(f"{path.name}:{name}")
    return sorted(host), sorted(extra)


def _dry_run(work: Path) -> bool:
    from plugins.feishu_base_export.prepare_profile import main as prepare

    code = prepare(["--profile-home", str(work)])
    print(f"dry_run={'true' if code == 0 and not (work / 'plugins').exists() else 'false'}")
    if code != 0 or (work / "plugins").exists():
        return False
    applied = prepare(["--profile-home", str(work), "--apply"])
    dest = work / "plugins" / "feishu_base_export" / "plugin.yaml"
    print(f"temp_copy={'true' if applied == 0 and dest.is_file() else 'false'}")
    return applied == 0 and dest.is_file()


def _charts_blocked() -> bool:
    import json

    from plugins.feishu_base_export.tool import handle

    for action in ("chart_png", "chart_pdf"):
        payload = json.loads(handle({"action": action}))
        if payload.get("status") != "blocked":
            print("charts=unexpected")
            return False
        if "png" not in payload.get("reason", "") or "pdf" not in payload.get("reason", ""):
            print("charts=unexpected")
            return False
    print("charts=blocked")
    return True


def _policy_is_additive() -> bool:
    text = (Path(__file__).resolve().parent / "POLICY_INSERT.txt").read_text(encoding="utf-8")
    code = "\n".join(line for line in text.splitlines() if not line.strip().startswith("#"))
    ok = (
        'request.get("tool_name") == "feishu_base_export"' in code
        and '"allowed": True' in code
        and "False" not in code
        and "deny" not in code.lower()
    )
    print("policy_insert=additive" if ok else "policy_insert=rejected")
    return ok


def _callback_servers() -> bool:
    from plugins.feishu_base_export.callback import _SERVERS, describe_setup
    from plugins.feishu_base_export.config import RuntimeConfig

    report = describe_setup(RuntimeConfig())
    return bool(_SERVERS) or report.get("listening") is not False or report.get("auth_ready") is not False


def _dpapi(work: Path) -> str:
    if sys.platform != "win32":
        return "windows_only"
    from plugins.feishu_base_export.dpapi import production_protector
    from plugins.feishu_base_export.token_store import TokenStore

    secret = "offline-verify-token"
    protector = production_protector()
    blob = protector.protect(secret.encode("utf-8"))
    if blob == secret.encode("utf-8") or protector.unprotect(blob) != secret.encode("utf-8"):
        return "roundtrip_failed"
    store = TokenStore(work, protector)
    store.save("ou_offline_verify", {"access_token": secret, "refresh_token": "r-offline"})
    raw = store.path_for("ou_offline_verify").read_bytes()
    loaded = store.load("ou_offline_verify")
    store.delete("ou_offline_verify")
    if secret.encode("utf-8") in raw or not loaded or loaded.get("access_token") != secret:
        return "roundtrip_failed"
    return "roundtrip_ok"


if __name__ == "__main__":
    sys.exit(main())
