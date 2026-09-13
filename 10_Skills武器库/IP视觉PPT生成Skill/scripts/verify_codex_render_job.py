#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
import pathlib
from typing import Any



def load_render_job(workdir: pathlib.Path) -> dict[str, Any]:
    job_path = workdir / "codex-render-job.json"
    if not job_path.exists():
        raise FileNotFoundError(f"找不到 render job 文件: {job_path}")
    return json.loads(job_path.read_text(encoding="utf-8"))


def main() -> None:
    ap = argparse.ArgumentParser(description="核对 Codex render job 对应的正式成品目录是否已写齐目标 PNG")
    ap.add_argument("--workdir", required=True, help="当前 v4.1 工作包目录")
    args = ap.parse_args()

    workdir = pathlib.Path(args.workdir).expanduser().resolve()

    job = load_render_job(workdir)
    expected_outputs = [pathlib.Path(item).resolve() for item in job.get("expected_outputs", [])]
    missing = [str(path) for path in expected_outputs if not path.exists()]
    result = {
        "job_type": job.get("job_type"),
        "deck_title": job.get("deck_title"),
        "work_package_dir": str(workdir),
        "archive_dir": job.get("archive_dir"),
        "expected_output_count": len(expected_outputs),
        "complete": not missing,
        "missing_outputs": missing,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
