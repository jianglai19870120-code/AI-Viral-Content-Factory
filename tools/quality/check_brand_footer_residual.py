"""复查品牌尾注 30天->3小时 的残留与双尾注。"""
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OLD = "带你30天跑通用AI做IP，批量出爆款。"
NEW = "带你3小时跑通用AI做IP，批量出爆款。"
OLD_RE = re.compile(r"带你30天跑通用AI做IP，批量出爆款。")
NEW_RE = re.compile(r"带你3小时跑通用AI做IP，批量出爆款。")

# 排除：输入库原始资料（按规则本不该带尾注，且其中大量"30天"是业务内容）
INPUT_LIB = os.path.join(ROOT, "02_资产中心", "01_输入库")

old_md, both, new_only_but_old_present = [], [], []
old_scripts = []
double_footer_md = []

# 双尾注检测：尾注块正则（兼容新旧）
BLOCK_RE = re.compile(r"---\s*\n\s*• (?:带你(?:30天|3小时)跑通用AI做IP，批量出爆款。)", re.MULTILINE)

for dirpath, dirnames, filenames in os.walk(ROOT):
    # 跳过隐藏与工作区内部
    parts = dirpath.split(os.sep)
    if any(p in (".git", ".workbuddy", "__pycache__", ".runtime") for p in parts):
        continue
    for fn in filenames:
        ext = fn.rsplit(".", 1)[-1].lower() if "." in fn else ""
        full = os.path.join(dirpath, fn)
        try:
            with open(full, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception:
            continue
        if ext == "md":
            if INPUT_LIB in dirpath:
                # 输入库：只统计带"尾注形态"的（含 lact175 的整块）
                if "lact175" in text and (OLD_RE.search(text) or NEW_RE.search(text)):
                    old_md.append(full)
                continue
            has_old = OLD_RE.search(text)
            has_new = NEW_RE.search(text)
            if has_old and has_new:
                both.append(full)
            elif has_old:
                old_md.append(full)
            # 双尾注：匹配到>=2个尾注块
            blocks = BLOCK_RE.findall(text)
            if len(blocks) >= 2:
                double_footer_md.append(full)
        elif ext in ("py", "html", "json"):
            if OLD_RE.search(text):
                old_scripts.append(full)

print("=== 仍含旧尾注的 .md（非输入库）===")
for p in old_md:
    print(p)
print(f"[count old_md={len(old_md)}]")

print("\n=== 同时含新旧尾注（混合/双尾注风险）.md ===")
for p in both:
    print(p)
print(f"[count both={len(both)}]")

print("\n=== 检测到>=2个尾注块（双尾注）.md ===")
for p in double_footer_md:
    print(p)
print(f"[count double={len(double_footer_md)}]")

print("\n=== 仍含旧尾注的脚本/数据 (py/html/json) ===")
for p in old_scripts:
    print(p)
print(f"[count old_scripts={len(old_scripts)}]")
