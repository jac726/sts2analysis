"""
Save file parser for Slay the Spire 2.
Save files are plain JSON with schema_version tracking.
Default save location: Steam/userdata/<steam_id>/2868840/remote/profile1/saves/history/
"""
import json
from pathlib import Path
from typing import Any


def load_run(path: str | Path) -> dict[str, Any]:
    """Load a single .run file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data["_source_file"] = str(path)
    return data


def load_all_runs(saves_dir: str | Path) -> list[dict[str, Any]]:
    """Load all .run files from a history directory."""
    saves_dir = Path(saves_dir)
    runs = []
    for path in sorted(saves_dir.glob("*.run")):
        try:
            runs.append(load_run(path))
        except Exception as e:
            print(f"[warn] Could not parse {path.name}: {e}")
    return runs


def find_default_saves_dir() -> Path | None:
    """Try to find the STS2 saves directory automatically on Windows."""
    import os
    steam_base = Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")) / "Steam/userdata"
    if not steam_base.exists():
        return None
    for user_dir in steam_base.iterdir():
        candidate = user_dir / "2868840/remote/profile1/saves/history"
        if candidate.exists():
            return candidate
    return None
