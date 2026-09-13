from __future__ import annotations

import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / ".runtime" / "cleanup" / "second_pass_cleanup_manifest.json"
REPARSE_POINT = 0x400


def _resolve_inside(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    path.relative_to(ROOT.resolve())
    return path


def _check_entry(path: Path) -> None:
    if path.is_symlink():
        raise RuntimeError(f"refuse symlink target: {path}")
    if path.exists() and getattr(path.stat(), "st_file_attributes", 0) & REPARSE_POINT:
        raise RuntimeError(f"refuse reparse-point target: {path}")


def _check_tree(path: Path) -> None:
    _check_entry(path)
    if path.is_dir():
        for child in path.rglob("*"):
            _check_entry(child)


def _delete_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def _archive_path(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        raise RuntimeError(f"archive destination already exists: {destination}")
    shutil.move(str(source), str(destination))


def main() -> int:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if data.get("schema_version") != "second-pass-cleanup-manifest-v1":
        raise RuntimeError("unexpected cleanup manifest version")
    changed = {"delete": 0, "archive": 0, "missing": 0}
    for item in data.get("targets", []):
        path = _resolve_inside(item["path"])
        if not path.exists():
            changed["missing"] += 1
            continue
        _check_tree(path)
        if item["kind"] == "file":
            current_bytes = path.stat().st_size
            if current_bytes != item["bytes"]:
                raise RuntimeError(f"target changed after manifest creation: {path}")
        if item["action"] == "delete":
            _delete_path(path)
            changed["delete"] += 1
        elif item["action"] == "archive":
            destination = _resolve_inside(item["archive_path"])
            _archive_path(path, destination)
            changed["archive"] += 1
        else:
            raise RuntimeError(f"unknown action: {item['action']}")
    print(json.dumps(changed, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
