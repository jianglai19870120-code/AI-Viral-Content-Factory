"""V12 案例卡拆解合同冒烟测试。

直接调用 Skill 自带的 self_test_v12.py（在临时根目录内校验候选、
晋升并写索引，不污染真实资产），再调用参考案例合同校验。

旧版 V11 及更早的案例卡合同已废弃。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _find_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "02_资产中心").exists() and (parent / "10_Skills武器库").exists():
            return parent
    raise RuntimeError("未找到项目根")


ROOT = _find_root()
SKILL = ROOT / "10_Skills武器库" / "今日复盘-案例卡拆解Skill（会员专享）"
SELF_TEST = SKILL / "scripts" / "self_test_v12.py"


def main() -> int:
    if not SELF_TEST.exists():
        print("FAIL: self_test_v12.py 不存在")
        return 1
    print("== 运行 self_test_v12.py ==")
    rc = subprocess.run([sys.executable, str(SELF_TEST)], cwd=str(SKILL)).returncode
    if rc != 0:
        return rc
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
