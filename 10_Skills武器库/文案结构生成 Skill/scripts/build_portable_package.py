#!/usr/bin/env python3
from __future__ import annotations
import shutil
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
DIST = SOURCE / "dist"
DIST.mkdir(exist_ok=True)
archive = shutil.make_archive(str(DIST / "copy-structure-generation"), "zip", root_dir=SOURCE.parent, base_dir=SOURCE.name)
print(archive)
