#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def _is_link(path: Path) -> bool:
    is_junction = getattr(os.path, "isjunction", lambda _: False)
    return path.is_symlink() or bool(is_junction(path))


def main() -> int:
    parser = argparse.ArgumentParser(description="按已确认精确清单执行深度清理")
    parser.add_argument("--root", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    manifest = Path(args.manifest).resolve()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    targets: list[Path] = []
    errors: list[str] = []
    for record in data.get("records", []):
        relative = Path(record["path"])
        if relative.is_absolute() or ".." in relative.parts:
            errors.append(f"非法相对路径：{relative}")
            continue
        target = (root / relative).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            errors.append(f"越界路径：{target}")
            continue
        current = target.parent
        while current != root:
            if _is_link(current):
                errors.append(f"路径经过链接或联接点：{target}")
                break
            current = current.parent
        else:
            if target.exists() and not target.is_file():
                errors.append(f"清单目标不是文件：{target}")
            elif target.exists():
                targets.append(target)
    summary = {"manifestRecords": len(data.get("records", [])), "existingTargets": len(targets), "errors": errors, "apply": args.apply}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if errors:
        return 1
    if args.apply:
        for target in targets:
            target.unlink()
        result = root / ".runtime/cleanup-result.json"
        result.write_text(json.dumps({**summary, "deleted": len(targets)}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
