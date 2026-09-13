#!/usr/bin/env python3
"""Install this portable skill into the current user's Codex skill directory."""
from __future__ import annotations
import shutil
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
TARGETS = [Path.home() / ".codex" / "skills" / "copy-structure-generation", SOURCE.parents[1] / ".agents" / "skills" / "copy-structure-generation"]

for target in TARGETS:
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(SOURCE, target, ignore=shutil.ignore_patterns("__pycache__", "dist"))
    print(target)
