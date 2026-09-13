from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(os.environ.get("AI_TRAFFIC_FACTORY_ROOT") or Path(__file__).resolve().parents[3]).resolve()
sys.path.insert(0, str(ROOT))
from workflow.common import resolve_member_child

INPUT_ROOT = ROOT / "02_资产中心" / "01_输入库"

# 一级分类 -> 输入库目录名
TYPE_DIR = {
    "书籍": "01_推荐好书-源文件",
    "播客": "02_热门播客-源文件",
    "事件": "03_热点事件-源文件",
    "对标": "04_选题库/01_对标账号",
    "复盘": "99_今日复盘-源文件（会员专享）",
}

# 这些类型在标准化时统一转成 .md；其余（如 xlsx）保留原格式只做命名清洗
MD_TYPES = {"书籍", "播客", "事件", "复盘"}
ILLEGAL = re.compile(r'[\\/:*?"<>|]')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="把原始资料标准化为正式入库文件")
    parser.add_argument("source", help="待标准化文件或目录（任意格式）")
    parser.add_argument("--type", required=True, choices=list(TYPE_DIR), help="单一主分类（资料类型）")
    parser.add_argument("--subcat", default="", help="子分类目录名，如 科学创业 / 能力成长（书籍常用，其他类型一般留空）")
    parser.add_argument("--ocr", action="store_true", help="对扫描型 PDF 启用 OCR（需 rapidocr_onnxruntime）")
    parser.add_argument("--move", action="store_true", help="处理完成后移动源文件（默认复制，保留源）")
    parser.add_argument("--apply", action="store_true", help="真正写入；默认仅预演打印")
    return parser.parse_args()


def clean_name(stem: str, mtype: str) -> str:
    text = stem.strip()
    text = text.replace("\u3000", " ")
    text = re.sub(r"\s+", " ", text)
    # 去除常见自动生成前缀
    text = re.sub(r"^\[English \(auto-generated\)\]\s*", "", text, flags=re.I)
    text = re.sub(r"^播客样本[-_ ]*", "", text)
    text = ILLEGAL.sub("", text).strip(" .")
    if mtype == "书籍":
        # 书名统一《》形态
        text = re.sub(r"^《(.+?)》$", r"\1", text)
        text = "《%s》" % text
    return text or "未命名资料"


def extract_pdf_text(src: Path, do_ocr: bool) -> str:
    try:
        from pypdf import PdfReader
    except ImportError:
        try:
            from PyPDF2 import PdfReader  # type: ignore
        except ImportError:
            return "[需要 pypdf 才能提取 PDF 文本；请安装后重试]"
    reader = PdfReader(str(src))
    parts = [(p.extract_text() or "") for p in reader.pages]
    text = "\n\n".join(parts).strip()
    if text:
        return text
    if do_ocr:
        return ocr_file(src)
    return "[PDF 未提取到文本，疑似扫描件；加 --ocr 启用 OCR]"


def ocr_file(src: Path) -> str:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        return "[OCR 依赖 rapidocr_onnxruntime 未安装，跳过 OCR]"
    engine = RapidOCR()
    result, _ = engine(str(src))
    if not result:
        return "[OCR 未识别出文字]"
    lines = [line[1] for line in result if line and len(line) > 1]
    return "\n".join(lines).strip()


def extract_with_lib(src: Path, ext: str) -> str:
    if ext == ".epub":
        try:
            import ebooklib  # type: ignore
            from ebooklib import epub  # type: ignore
            from bs4 import BeautifulSoup  # type: ignore
        except ImportError:
            return "[需要 ebooklib + beautifulsoup4 才能解析 epub]"
        book = epub.read_epub(str(src))
        out = []
        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                soup = BeautifulSoup(item.get_content(), "html.parser")
                out.append(soup.get_text("\n"))
        return "\n".join(out).strip()
    if ext in (".docx", ".doc"):
        try:
            import docx  # type: ignore
        except ImportError:
            return "[需要 python-docx 才能解析 docx]"
        document = docx.Document(str(src))
        return "\n".join(p.text for p in document.paragraphs).strip()
    return ""


def standardize_file(src: Path, mtype: str, subcat: str, do_ocr: bool, do_move: bool, apply: bool) -> str:
    clean = clean_name(src.stem, mtype)
    type_dir = TYPE_DIR[mtype]
    if type_dir.startswith("04_选题库/"):
        dest_dir = ROOT / "02_资产中心" / type_dir
    else:
        dest_dir = resolve_member_child(INPUT_ROOT, type_dir)
    if subcat:
        dest_dir = dest_dir / subcat
    dest_dir.mkdir(parents=True, exist_ok=True)

    ext = src.suffix.lower()
    if mtype in MD_TYPES and ext not in (".md",):
        # 转 md
        if ext == ".txt":
            text = src.read_text(encoding="utf-8", errors="ignore")
        elif ext == ".pdf":
            text = extract_pdf_text(src, do_ocr)
        elif ext in (".epub", ".docx", ".doc"):
            text = extract_with_lib(src, ext)
        else:
            text = "[不支持的源格式，原样复制]"
        dest = dest_dir / ("%s.md" % clean)
        note = "转md"
    else:
        # 保留原格式（xlsx / 已为 md 等）
        dest = dest_dir / ("%s%s" % (clean, ext))
        text = None
        note = "归位"

    action = "移动" if do_move else "复制"
    if apply:
        if text is not None:
            dest.write_text(text, encoding="utf-8")
        else:
            shutil.copy2(src, dest)
        if do_move and dest != src:
            src.unlink()
        return "[已%s] %s -> %s" % (action, src, dest)
    return "[预演·%s] %s -> %s" % (action, src, dest)


def type_destination(mtype: str) -> Path:
    """Resolve the actual local target, including a member-only folder suffix."""
    type_dir = TYPE_DIR[mtype]
    if type_dir.startswith("04_选题库/"):
        return ROOT / "02_资产中心" / type_dir
    return resolve_member_child(INPUT_ROOT, type_dir)


def main() -> int:
    args = parse_args()
    src = Path(args.source)
    if not src.exists():
        print("源不存在: %s" % src)
        return 1
    targets = [src] if src.is_file() else [p for p in sorted(src.rglob("*")) if p.is_file()]
    if not targets:
        print("未找到可处理的文件")
        return 1
    for t in targets:
        msg = standardize_file(t, args.type, args.subcat, args.ocr, args.move, args.apply)
        print(msg)
    destination = type_destination(args.type).relative_to(ROOT / "02_资产中心")
    print("\n标准化完成：资料已归位到 %s 下。请按规则交小审审核后，再由对应拆解 Skill 处理。" % destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
