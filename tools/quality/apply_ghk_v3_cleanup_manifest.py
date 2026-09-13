from __future__ import annotations

import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / ".runtime" / "cleanup" / "ghk_v3_cleanup_manifest.json"


def _resolve_inside(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    path.relative_to(ROOT.resolve())
    return path


def main() -> int:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if data.get("schema_version") != "ghk-v3-cleanup-manifest-v2":
        raise RuntimeError("unexpected cleanup manifest version")
    changed = {"delete": 0, "archive": 0, "missing": 0}
    for item in data.get("targets", []):
        path = _resolve_inside(item["path"])
        if not path.exists():
            changed["missing"] += 1
            continue
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"refuse non-regular cleanup target: {path}")
        if path.stat().st_file_attributes & 0x400:
            raise RuntimeError(f"refuse reparse-point cleanup target: {path}")
        if path.stat().st_size != item["bytes"]:
            raise RuntimeError(f"target changed after manifest creation: {path}")
        if item["action"] == "delete":
            path.unlink()
            changed["delete"] += 1
        elif item["action"] == "archive":
            destination = _resolve_inside(item["archive_path"])
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                raise RuntimeError(f"archive destination already exists: {destination}")
            shutil.move(str(path), str(destination))
            changed["archive"] += 1
        else:
            raise RuntimeError(f"unknown action: {item['action']}")
    print(json.dumps(changed, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
