"""Copy this plugin's source files into an operator-supplied directory.

Dry-run is the default. This script never reads or writes config.yaml, .env,
or runtime-policy.json. Enabling the plugin and setting redirect_uri are
separate official commands: `hermes plugins enable` and `hermes config set`.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

_SKIP = {"__pycache__", ".pyc"}


def plan_copy(profile_home: Path, source: Path | None = None) -> list[Path]:
    if not str(profile_home):
        raise ValueError("profile home is required")
    root = source or Path(__file__).resolve().parent
    names = []
    for path in sorted(root.iterdir()):
        if path.name.startswith(".") or path.name in _SKIP or path.suffix == ".pyc":
            continue
        if path.suffix not in {".py", ".yaml", ".yml", ".md", ".txt"}:
            continue
        names.append(path)
    return names


def apply_copy(profile_home: Path, source: Path | None = None) -> Path:
    files = plan_copy(profile_home, source)
    dest = Path(profile_home) / "plugins" / "feishu_base_export"
    dest.mkdir(parents=True, exist_ok=True)
    for path in files:
        shutil.copy2(path, dest / path.name)
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Stage the Feishu Base export plugin")
    parser.add_argument("--profile-home", required=True, help="Profile directory from hermes config path's parent")
    parser.add_argument("--apply", action="store_true", help="Copy files. Omit for a dry-run that writes nothing.")
    args = parser.parse_args(argv)
    home = Path(args.profile_home)
    files = plan_copy(home)
    print(f"profile_home={home}")
    print(f"files={len(files)}")
    print("dry_run=" + ("false" if args.apply else "true"))
    if not args.apply:
        return 0
    dest = apply_copy(home)
    print(f"copied_to={dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
