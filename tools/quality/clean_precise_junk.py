# -*- coding: utf-8 -*-
"""
精确清理 AI爆款内容工厂 的临时/可再生成垃圾文件。

设计原则（安全优先）：
- 只用「正向白名单垃圾模式」判定，匹配才删，不匹配一律保留。
- 硬保护：02_资产中心/、10_Skills武器库/ 等业务资产目录下，除 __pycache__ 外绝不删。
- 任何 .md/.txt/.jsonl/.xlsx/.png/.pdf 等正式内容文件，即使其他规则匹配也不删
  （仅 PUBLIC_ASSETS_MANIFEST.json 这种明确垃圾 json 例外）。

用法：
    python clean_precise_junk.py            # 实际删除
    python clean_precise_junk.py --dry-run  # 仅列出将删项，不删除
"""
import os
import sys
import shutil
import fnmatch

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ---------- 垃圾模式（正向白名单） ----------

def _is_junk_file(rel):
    """判断一个文件相对路径是否为垃圾（将被删除）。"""
    name = os.path.basename(rel)
    parts = rel.split(os.sep)

    # 明确垃圾 json（发布清单，非业务资产）
    if name == "PUBLIC_ASSETS_MANIFEST.json":
        return True

    # tools/ 下历史迁移/一次性脚本与数据
    if parts[0] == "tools":
        if fnmatch.fnmatch(name, "_migrate_*") or fnmatch.fnmatch(name, "_verify_*") \
           or fnmatch.fnmatch(name, "_batch*_entries.json") \
           or fnmatch.fnmatch(name, "patch_*.json") \
           or fnmatch.fnmatch(name, "rewrites_*.json"):
            return True
        if name in {"migrate.py", "migrate_11to10.py", "transform_11to10.py",
                    "recover.py", "acc.py", "check_audit.py", "validate.py"}:
            return True
        # 这次品牌尾注一次性改写脚本
        if rel == os.path.join("tools", "quality", "swap_brand_footer_30d_to_3h.py"):
            return True

    # .agents/skills/*/.generated-manifest.json（Codex 薄壳运行产物）
    if len(parts) >= 3 and parts[0] == ".agents" and parts[1] == "skills":
        if name == ".generated-manifest.json":
            return True

    # 根级保留名垃圾
    if rel in {"nul", "PUBLIC_ASSETS_MANIFEST.json"}:
        return True

    return False


def _is_junk_dir(rel):
    """判断一个目录相对路径是否为垃圾（整目录删除）。"""
    name = os.path.basename(rel)
    parts = rel.split(os.sep)

    # Python 字节码缓存
    if name == "__pycache__":
        return True
    if name.endswith(".pyc"):
        return True

    # 运行时/工程惯例排除目录
    if rel in {".runtime", ".obsidian",
               os.path.join(".workbuddy", "candidates"),
               os.path.join(".workbuddy", "jinju_split"),
               os.path.join(".workbuddy", "v10_verify")}:
        return True

    return False


# ---------- 硬保护：业务资产目录下的非缓存内容绝不删 ----------
HARD_PROTECT_PREFIXES = (
    os.path.join("02_资产中心", "01_输入库"),
    os.path.join("02_资产中心", "02_处理库"),
    os.path.join("02_资产中心", "03_输出库"),
    os.path.join("10_Skills武器库"),
)

# 正式内容扩展名（即便命中其他规则也保护；PUBLIC_ASSETS_MANIFEST.json 已单独放行）
CONTENT_EXTS = {".md", ".txt", ".jsonl", ".xlsx", ".xls", ".png", ".pdf",
                ".jpg", ".jpeg", ".gif", ".csv", ".docx", ".pptx", ".html"}


def should_delete(rel, is_dir):
    """最终裁决：是否删除该路径。"""
    # Windows 保留设备名（nul/con/prn/aux/com*/lpt*）不是真实文件，
    # 无法物理删除且零磁盘占用，跳过（gitignore 可能匹配到它们）。
    nm = os.path.basename(rel).lower()
    if nm in {"nul", "con", "prn", "aux"} or \
       (len(nm) >= 4 and ((nm[:3] == "com" and nm[3:].isdigit()) or
                           (nm[:3] == "lpt" and nm[3:].isdigit()))):
        return False

    parts = rel.split(os.sep)

    # 业务资产目录：只允许删其中的 __pycache__，其余一律保护
    for pref in HARD_PROTECT_PREFIXES:
        if rel == pref or rel.startswith(pref + os.sep):
            if is_dir and os.path.basename(rel) == "__pycache__":
                return True
            if (not is_dir) and os.path.basename(rel).endswith(".pyc"):
                return True
            return False

    # 正式内容文件硬保护
    if not is_dir and os.path.splitext(rel)[1].lower() in CONTENT_EXTS:
        # PUBLIC_ASSETS_MANIFEST.json 例外
        if os.path.basename(rel) == "PUBLIC_ASSETS_MANIFEST.json":
            return True
        return False

    if is_dir:
        return _is_junk_dir(rel)
    return _is_junk_file(rel)


def collect():
    junk_files = []
    junk_dirs = []
    for cur, dirs, files in os.walk(ROOT, topdown=False):
        if os.path.basename(cur) == ".git":
            continue
        rel_cur = os.path.relpath(cur, ROOT)
        # 目录
        for d in dirs:
            rel = os.path.join(rel_cur, d) if rel_cur != "." else d
            if rel == ".git" or rel.startswith(".git" + os.sep):
                continue
            full = os.path.join(ROOT, rel)
            if not os.path.exists(full):  # 跳过虚拟设备名等不存在项（如 nul）
                continue
            if should_delete(rel, True):
                junk_dirs.append(rel)
        # 文件
        for f in files:
            rel = os.path.join(rel_cur, f) if rel_cur != "." else f
            full = os.path.join(ROOT, rel)
            if not os.path.exists(full):  # 跳过不存在项
                continue
            if should_delete(rel, False):
                junk_files.append(rel)
    return junk_dirs, junk_files


def remove_path(rel):
    full = os.path.join(ROOT, rel)
    if os.path.isdir(full) and not os.path.islink(full):
        shutil.rmtree(full, ignore_errors=True)
    else:
        # nul 是 Windows 保留名，os.remove 可能失败，用 PowerShell 兜底
        try:
            os.remove(full)
        except Exception:
            try:
                import subprocess
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command",
                     "Remove-Item -Force -LiteralPath '%s'" % full],
                    capture_output=True)
            except Exception:
                pass


def main():
    dry = "--dry-run" in sys.argv
    junk_dirs, junk_files = collect()

    # 先删文件，再删目录（topdown=False 已保证子项先处理；这里目录单独删）
    order = sorted(junk_files) + sorted(junk_dirs)
    print("=" * 60)
    print("精确垃圾清理 %s" % ("[DRY-RUN 仅列出]" if dry else "[实际执行]"))
    print("ROOT:", ROOT)
    print("将删文件: %d  将删目录: %d" % (len(junk_files), len(junk_dirs)))
    print("=" * 60)
    for rel in order:
        mark = "[DIR] " if rel in junk_dirs else "[FILE]"
        print("%s %s" % (mark, rel))
        if not dry:
            remove_path(rel)
    print("=" * 60)
    print("完成。删除文件 %d，删除目录 %d。" % (len(junk_files), len(junk_dirs)))


if __name__ == "__main__":
    main()
