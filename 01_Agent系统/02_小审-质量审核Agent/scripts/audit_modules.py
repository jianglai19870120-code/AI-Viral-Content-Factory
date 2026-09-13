from __future__ import annotations

import argparse
import collections
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "tools"))
import sys
from pathlib import Path
_SELF = Path(__file__).resolve()
for _p in _SELF.parents:
    if (_p / "workflow" / "common.py").exists():
        if str(_p) not in sys.path:
            sys.path.insert(0, str(_p))
        break
from workflow.common import append_brand_footer_text as append_brand_footer


ROOT = Path(__file__).resolve().parents[3]
PRIVATE_MODULE_ROOT = ROOT / "02_资产中心" / "02_处理库" / "01_观点_内容模块" / "01_推荐好书"
PRIVATE_AUDIT_DIR = ROOT / "01_Agent系统" / "02_小审-质量审核Agent" / "99_审核记录"
PRIVATE_PROVENANCE_DIR = ROOT / "01_Agent系统" / "04_小拆-内容拆解Agent" / "06_正式产物来源"
CONTRACT_VERSION = "book_module_v6_independent_mistake_step"
SOURCE_WORDS = ("这本书", "本书", "作者", "书中", "原文", "依据", "提到", "认为", "强调", "相关依据")
EXEMPT_META_PREFIXES = ("- 来源文件：", "- 一级分类：")
TEMPLATE_PATTERNS = ("可以靠想象直接做对", "变成可验证的行动", "要先被验证", "要靠行动验证")
BAD_TITLE_FRAGMENTS = ("我", "他", "她", "我们", "他们", "那个", "这个", "在本章", "创始人", "首席执行官", "CEO", "Gumroad", "Calendly")
QUESTION_PREFIXES = ("怎么", "如何", "为什么", "为何", "什么时候", "何时", "是否", "怎样")
INVALID_TOPIC_TERMS = {
    "北京",
    "比如",
    "自己",
    "我们",
    "他们",
    "这个",
    "那个",
    "如果",
    "因为",
    "所以",
    "但是",
    "时候",
    "什么",
    "进行",
    "通过",
    "不是",
    "没有",
    "可以",
    "一个",
    "因此",
    "然后",
    "最后",
    "或者",
    "以及",
    "问题",
    "老师",
    "樊登",
    "樊登老师",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="小审正式模块放行审核")
    parser.add_argument("--title", required=True, help="书名，如 低风险创业")
    parser.add_argument("--candidate-root", default="", help="候选产物目录；为空时审核正式模块库")
    parser.add_argument("--write-report", action="store_true", help="写入正式审核记录")
    return parser.parse_args()


def module_root(candidate_root: str) -> Path:
    return Path(candidate_root) if candidate_root else PRIVATE_MODULE_ROOT


def provenance_path(title: str, base: Path, candidate_mode: bool) -> Path:
    if candidate_mode:
        return base / "_provenance" / f"{title}.json"
    return PRIVATE_PROVENANCE_DIR / f"{title}.json"


def sufficiency_path(title: str, base: Path, candidate_mode: bool) -> Path:
    if candidate_mode:
        return base / "_sufficiency" / f"{title}.json"
    return PRIVATE_PROVENANCE_DIR / f"{title}_充分拆解记录.json"


def han_len(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def source_word_hits(text: str) -> list[str]:
    hits: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(EXEMPT_META_PREFIXES):
            continue
        for word in SOURCE_WORDS:
            if word in stripped:
                hits.append(f"`{word}` 出现在正文：{stripped[:80]}")
    return hits


def sentence_count(text: str) -> int:
    return len([p for p in re.split(r"[。！？!?]+", text) if re.sub(r"\s+", "", p)])


def load_json(path: Path) -> tuple[dict | None, str | None]:
    if not path.exists():
        return None, "文件不存在"
    try:
        return json.loads(path.read_text(encoding="utf-8", errors="ignore")), None
    except Exception as exc:
        return None, f"文件不可读：{exc}"


def load_provenance(title: str, base: Path, candidate_mode: bool) -> tuple[dict | None, list[str]]:
    payload, error = load_json(provenance_path(title, base, candidate_mode))
    if error:
        return None, [f"未按正式拆解 Skill 执行：缺少或无法读取正式产物来源记录（{error}）"]
    issues: list[str] = []
    expected_status = "candidate_skill_output" if candidate_mode else "formal_skill_output"
    if payload.get("source_status") != expected_status:
        issues.append(f"未按正式拆解 Skill 执行：来源状态不是 {expected_status}")
    if payload.get("contract_version") != CONTRACT_VERSION:
        issues.append(f"来源合法但产物合同不合格：不是 {CONTRACT_VERSION}")
    if payload.get("module_contract") != "three_modules_independent_mistakes_steps_no_pairing":
        issues.append("来源合法但模块合同不合格：不是误区步骤独立拆解合同")
    if payload.get("body_expression_contract") != "direct_short_video_asset_no_source_narration":
        issues.append("来源合法但表达合同缺失：未声明正文区禁止来源叙述")
    return payload, issues


def load_sufficiency(title: str, base: Path, candidate_mode: bool) -> tuple[dict | None, list[str]]:
    payload, error = load_json(sufficiency_path(title, base, candidate_mode))
    if error:
        return None, [f"缺少充分拆解记录：{error}"]
    issues: list[str] = []
    if payload.get("contract_version") != CONTRACT_VERSION:
        issues.append(f"充分拆解记录合同不合格：不是 {CONTRACT_VERSION}")
    if payload.get("generation_strategy") != "independent_mistake_step_evidence_pools":
        issues.append("模板化生成：充分拆解记录不是误区候选池和步骤候选池独立生成")
    if payload.get("sufficient_breakdown") is not True:
        issues.append("拆解不充分：充分拆解记录未标记通过")
    for key in ("raw_char_count", "paragraph_count", "mistake_candidate_count", "step_candidate_count", "quote_candidate_count"):
        if int(payload.get(key, 0) or 0) <= 0:
            issues.append(f"未覆盖整本书：充分拆解记录缺少 {key}")
    if not isinstance(payload.get("mistake_candidate_pool"), list):
        issues.append("缺少误区候选池：无法判断误区是否独立提炼")
    if not isinstance(payload.get("step_candidate_pool"), list):
        issues.append("缺少步骤候选池：无法判断步骤是否独立提炼")
    return payload, issues


def quote_body(line: str, title: str) -> str:
    body = line.strip()[2:] if line.strip().startswith("- ") else line.strip()
    return body.split(f"——《{title}》", 1)[0].strip("。！？!? ")


def scan_quote_module(base: Path, title: str) -> tuple[int, list[str]]:
    issues: list[str] = []
    quote_dir = base / "01_金句模块"
    bullets: list[str] = []
    if not quote_dir.exists():
        return 0, ["金句模块目录不存在"]
    for path in quote_dir.glob("*.md"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        marker = f"## 《{title}》"
        if marker not in text:
            continue
        section = text.split(marker, 1)[1]
        next_match = re.search(r"\n## 《[^》]+》", section)
        if next_match:
            section = section[: next_match.start()]
        if "### #" not in section:
            issues.append(f"{path.name} 金句没有按二级分类分组")
        bullets.extend([line.strip() for line in section.splitlines() if line.strip().startswith("- ")])
    if len(bullets) < 10:
        issues.append("金句数量明显不足，至少需要 10 条可传播表达")
    for line in bullets:
        if f"——《{title}》" not in line:
            issues.append("金句存在来源引用不完整")
        body = quote_body(line, title)
        if han_len(body) > 30:
            issues.append(f"金句正文超过 30 个汉字：{body}")
        if han_len(body) < 4:
            issues.append(f"金句过短，疑似普通标签或残句：{body}")
        if any(word in body for word in SOURCE_WORDS):
            issues.append(f"金句含来源叙述词：{body}")
        if re.search(r"[A-Za-z]{3,}|https?://|www\\.|\\d{3,}", body):
            issues.append(f"金句含英文链接、年份或脚注残片：{body}")
        if any(word in body for word in ("我", "您", "下面", "示例", "访谈", "链接", "发布", "声明", "问题：", "希弗斯", "阿斯克")):
            issues.append(f"金句像原文说明或案例残片：{body}")
        if "：" in body or ":" in body or "“" in body or "”" in body:
            issues.append(f"金句含引文或说明符号，疑似未清洗：{body}")
        if body.endswith(("的", "了", "和", "与", "及")):
            issues.append(f"金句不是完整笃定句：{body}")
        if any(word in body for word in ("通过", "进行", "一个", "一种", "内容", "资料")) and han_len(body) > 18:
            issues.append(f"金句像普通说明句：{body}")
    return len(bullets), issues


def numbered_blocks(text: str, label: str) -> list[tuple[str, str]]:
    pattern = re.compile(rf"\*\*{label}(\d+)[：:](.*?)\*\*\s*(.*?)(?=\n\*\*{label}\d+[：:]|\n- 一级分类|\n- 来源文件|$)", re.S)
    blocks: list[tuple[str, str]] = []
    for match in pattern.finditer(text):
        heading = re.sub(r"\s+", "", match.group(2)).strip("。！？!? ")
        body = match.group(3).strip()
        blocks.append((heading, body))
    return blocks


def body_repeats_heading(heading: str, body: str) -> bool:
    body_compact = re.sub(r"\s+", "", body).strip("。！？!? ")
    heading_compact = re.sub(r"\s+", "", heading).strip("。！？!? ")
    return bool(heading_compact and body_compact.startswith(heading_compact))


def template_hits(text: str) -> list[str]:
    return [pattern for pattern in TEMPLATE_PATTERNS if pattern in text]


def title_quality_issues(title: str) -> list[str]:
    issues: list[str] = []
    compact = re.sub(r"\s+", "", title)
    if any(fragment in compact for fragment in BAD_TITLE_FRAGMENTS):
        issues.append("标题像原文截句或案例残片，不是抽象后的模块标题")
    if len(re.findall(r"[A-Za-z]", compact)) >= 6:
        issues.append("标题包含过多英文名词，疑似直接截取原文案例")
    if compact.endswith(("的", "了", "而", "时", "候", "和", "与", "甚", "可")):
        issues.append("标题被截断，语义不完整")
    if "如何处理" in compact and not any(word in compact for word in ("方法", "流程", "动作", "反馈", "客户", "验证", "定位", "交付")):
        issues.append("步骤标题是套壳处理句，没有明确执行问题")
    if re.fullmatch(r"怎么[\u4e00-\u9fff]{2,8}[？?]?", compact):
        issues.append("步骤标题是泛主题疑问句，没有明确执行对象")
    return issues


def classify_step_title_shape(title: str) -> str:
    compact = re.sub(r"\s+", "", title).strip("。！？!? ")
    for prefix in QUESTION_PREFIXES:
        if compact.startswith(prefix):
            return prefix
    if compact.startswith(("从", "用", "先", "让", "把")):
        return "动作式"
    if "还是" in compact:
        return "选择判断"
    return "其他"


def scan_mistake_modules(base: Path, title: str) -> tuple[list[Path], list[str]]:
    files = sorted((base / "02_误区模块").glob(f"《{title}》_*.md"))
    issues: list[str] = []
    signals: list[str] = []
    if not files:
        return files, ["误区模块不存在"]
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        first_line = next((line.strip("# ").strip() for line in text.splitlines() if line.strip()), "")
        title_probe = first_line or path.stem
        for issue in title_quality_issues(title_probe):
            issues.append(f"{path.name} {issue}")
        hits = template_hits(path.name + "\n" + text)
        if hits:
            issues.append(f"{path.name} 命中模板化硬伤：" + "、".join(sorted(set(hits))))
        match = re.search(r"以为(.+?)可以靠想象", path.stem)
        if match:
            signal = match.group(1)
            signals.append(signal)
            if signal in INVALID_TOPIC_TERMS:
                issues.append(f"{path.name} 使用无效主题词：{signal}")
        issues.extend([f"{path.name} 来源叙述残留：{hit}" for hit in source_word_hits(text)])
        if f"- 来源文件：《{title}》.md" not in text:
            issues.append(f"{path.name} 缺少来源文件")
        if "**错误观点**" not in text and "错误观点：" not in text:
            issues.append(f"{path.name} 缺少错误观点")
        blocks = numbered_blocks(text, "误区")
        if not 2 <= len(blocks) <= 3:
            issues.append(f"{path.name} 误区编号数量应为 2-3 个，当前 {len(blocks)} 个")
        for idx, (heading, body) in enumerate(blocks, start=1):
            if sentence_count(body) < 3:
                issues.append(f"{path.name} 误区{idx} 正文少于 3 句拓展")
            if body_repeats_heading(heading, body):
                issues.append(f"{path.name} 误区{idx} 正文重复标题")
        if not any(word in text for word in ("错", "问题", "继续", "真正", "不是", "而是", "会")):
            issues.append(f"{path.name} 不像认知纠偏文案")
    duplicated = [item for item, count in collections.Counter(signals).items() if count > 1]
    for signal in duplicated:
        issues.append(f"误区模块主题重复：{signal}")
    return files, issues


def scan_step_modules(base: Path, title: str) -> tuple[list[Path], list[str]]:
    files = sorted((base / "03_步骤模块").glob(f"《{title}》_*.md"))
    issues: list[str] = []
    signals: list[str] = []
    title_shapes: list[str] = []
    if not files:
        return files, ["步骤模块不存在"]
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        first_line = next((line.strip("# ").strip() for line in text.splitlines() if line.strip()), "")
        compact_title = re.sub(r"\s+", "", first_line)
        title_shapes.append(classify_step_title_shape(first_line))
        for issue in title_quality_issues(first_line):
            issues.append(f"{path.name} {issue}")
        if "怎么怎么" in compact_title or "如何怎么" in compact_title:
            issues.append(f"{path.name} 标题存在重复问句前缀")
        if compact_title.startswith("怎么") and han_len(compact_title) <= 8:
            issues.append(f"{path.name} 标题过于泛化，像统一套壳问句")
        if compact_title.startswith(("如何处理", "怎么处理")) and not any(word in compact_title for word in ("验证", "反馈", "增长", "客户", "产品", "交付", "转型", "核算", "引擎")):
            issues.append(f"{path.name} 标题只有处理壳，没有明确执行对象")
        hits = template_hits(first_line + "\n" + text)
        if hits:
            issues.append(f"{path.name} 命中模板化硬伤：" + "、".join(sorted(set(hits))))
        match = re.search(r"怎么把(.+?)变成", first_line)
        if match:
            signal = match.group(1)
            signals.append(signal)
            if signal in INVALID_TOPIC_TERMS:
                issues.append(f"{path.name} 使用无效主题词：{signal}")
        issues.extend([f"{path.name} 来源叙述残留：{hit}" for hit in source_word_hits(text)])
        if "？" not in first_line and "?" not in first_line and not any(word in first_line for word in ("怎么", "如何", "为什么", "什么时候", "怎样")) and not compact_title.startswith(("从", "用", "先", "让", "把")):
            issues.append(f"{path.name} 标题不是具体问题或疑问句")
        blocks = numbered_blocks(text, "步骤")
        if not 2 <= len(blocks) <= 4:
            issues.append(f"{path.name} 步骤编号数量应为 2-4 个，当前 {len(blocks)} 个")
        if f"- 来源文件：《{title}》.md" not in text:
            issues.append(f"{path.name} 缺少来源文件")
        for idx, (heading, body) in enumerate(blocks, start=1):
            if sentence_count(body) < 3:
                issues.append(f"{path.name} 步骤{idx} 正文少于 3 句拓展")
            if body_repeats_heading(heading, body):
                issues.append(f"{path.name} 步骤{idx} 正文重复标题")
        body = re.sub(r"\s+", "", text)
        if not any(word in body for word in ("先", "再", "然后", "最后", "越", "不要", "把")):
            issues.append(f"{path.name} 不像完整行动文案")
    duplicated = [item for item, count in collections.Counter(signals).items() if count > 1]
    for signal in duplicated:
        issues.append(f"步骤模块主题重复：{signal}")
    if len(files) >= 4:
        counts = collections.Counter(title_shapes)
        dominant_shape, dominant_count = counts.most_common(1)[0]
        if dominant_shape in QUESTION_PREFIXES and dominant_count / len(files) >= 0.8:
            issues.append(f"步骤标题问法过于单一：{dominant_shape} 开头占比 {dominant_count}/{len(files)}")
    return files, issues


def scan_index(base: Path, title: str, expected_min: int) -> tuple[int, list[str]]:
    path = base / "05_模块索引" / "模块索引.jsonl"
    if not path.exists():
        return 0, ["模块索引不存在"]
    count = 0
    issues: list[str] = []
    forbidden_types = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except Exception:
            issues.append("模块索引存在不可解析 JSON 行")
            continue
        if obj.get("source_title") == title:
            count += 1
            if obj.get("module_type") == "故事":
                forbidden_types.append("故事")
    if count < expected_min:
        issues.append("模块索引记录少于通过审核的模块数量")
    if forbidden_types:
        issues.append("模块索引仍包含故事模块记录")
    return count, issues


def scan_sufficiency(suff: dict | None, quote_count: int, mis_count: int, step_count: int) -> list[str]:
    issues: list[str] = []
    if not suff:
        return ["缺少充分拆解记录"]
    if int(suff.get("final_mistake_file_count", -1)) != mis_count:
        issues.append("充分拆解记录与误区文件数量不一致")
    if int(suff.get("final_step_file_count", -1)) != step_count:
        issues.append("充分拆解记录与步骤文件数量不一致")
    if int(suff.get("final_quote_count", -1)) != quote_count:
        issues.append("充分拆解记录与金句数量不一致")
    if mis_count == step_count and mis_count >= 4:
        issues.append(f"模板化生成：误区和步骤数量完全同步（{mis_count}+{step_count}），疑似配平生成")
    if int(suff.get("mistake_candidate_count", 0) or 0) < mis_count:
        issues.append("拆解不充分：误区候选数量小于入库数量，候选池记录异常")
    if int(suff.get("step_candidate_count", 0) or 0) < step_count:
        issues.append("拆解不充分：步骤候选数量小于入库数量，候选池记录异常")
    if suff.get("source_coverage") != "full_book_scan":
        issues.append("未覆盖整本书：充分拆解记录不是 full_book_scan")
    selected_topics = suff.get("selected_topics")
    if isinstance(selected_topics, list):
        invalid = [
            str(item)
            for item in selected_topics
            if str(item) in INVALID_TOPIC_TERMS or str(item).endswith(("老师", "先生", "作者"))
        ]
        duplicated = [str(item) for item, count in collections.Counter(map(str, selected_topics)).items() if count > 1]
        if invalid:
            issues.append("模板化生成：充分拆解主题池包含无效主题词：" + "、".join(invalid))
        if duplicated:
            issues.append("拆解不充分：充分拆解主题池包含重复主题：" + "、".join(duplicated))
    mistake_pool = suff.get("mistake_candidate_pool")
    step_pool = suff.get("step_candidate_pool")
    if isinstance(mistake_pool, list) and isinstance(step_pool, list):
        mistake_set = set(map(str, mistake_pool))
        step_set = set(map(str, step_pool))
        if mistake_set and mistake_set == step_set:
            issues.append("模板化生成：误区候选池和步骤候选池完全同源")
        if mistake_set and step_set:
            overlap = mistake_set & step_set
            if len(overlap) / max(1, min(len(mistake_set), len(step_set))) > 0.8:
                issues.append("模板化生成：误区候选池和步骤候选池高度重合")
    discarded = suff.get("discarded_reasons")
    if not isinstance(discarded, list) or not discarded:
        issues.append("缺少被丢弃候选的主要原因")
    return issues


def write_report(title: str, passed: bool, findings: dict[str, list[str]], counts: dict[str, int], candidate_mode: bool) -> Path:
    PRIVATE_AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    suffix = "候选充分拆解审核" if candidate_mode else ("正式充分拆解放行审核" if passed else "撤销通过并退回")
    path = PRIVATE_AUDIT_DIR / f"{stamp}_{suffix}_{title}.md"
    lines = [
        "# 小审审核记录",
        "",
        f"- 审核时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"- 审核对象：《{title}》三类干货模块",
        f"- 审核模式：{'候选产物审核' if candidate_mode else '正式产物审核'}",
        f"- 审核结论：{'通过' if passed else '退回'}",
        "- 审核标准：正式模块放行审核标准.md",
        "- 审核顺序：先验来源，再审充分性，再审结构，再审表达",
        "",
        "## 模块数量",
        "",
        f"- 金句模块：{counts['quotes']}",
        f"- 误区模块：{counts['mis']}",
        f"- 步骤模块：{counts['steps']}",
        f"- 模块索引：{counts['index']}",
        "",
        "## 发现",
        "",
    ]
    if passed:
        lines.append("- 未发现阻断问题，充分性审核通过，允许晋升正式模块库。" if candidate_mode else "- 未发现阻断问题，充分性审核通过，允许进入正式模块库。")
    else:
        for section, issues in findings.items():
            if not issues:
                continue
            lines.append(f"### {section}")
            lines.append("")
            lines.extend(f"- {issue}" for issue in issues)
            lines.append("")
        lines.extend(["## 退回建议", "", "- 退回给小拆按 `书籍内容模块拆解Skill` 充分拆解合同重拆。", "- 未通过前，不允许进入正式文案调用。", ""])
    path.write_text(append_brand_footer("\n".join(lines)), encoding="utf-8")
    return path


def refresh_dashboard() -> None:
    script = ROOT / "tools" / "build_xiaojiang_dashboard.py"
    if not script.exists():
        return
    subprocess.run([sys.executable, str(script)], check=False)


def main() -> int:
    args = parse_args()
    base = module_root(args.candidate_root)
    candidate_mode = bool(args.candidate_root)
    _, provenance_issues = load_provenance(args.title, base, candidate_mode)
    suff, suff_load_issues = load_sufficiency(args.title, base, candidate_mode)
    quote_count, quote_issues = scan_quote_module(base, args.title)
    mis_files, mis_issues = scan_mistake_modules(base, args.title)
    step_files, step_issues = scan_step_modules(base, args.title)
    expected_min = quote_count + len(mis_files) + len(step_files)
    index_count, index_issues = scan_index(base, args.title, expected_min)
    sufficiency_issues = suff_load_issues + scan_sufficiency(suff, quote_count, len(mis_files), len(step_files))
    findings = {
        "来源合法性": provenance_issues,
        "充分性审核": sufficiency_issues,
        "金句模块": quote_issues,
        "误区模块": mis_issues,
        "步骤模块": step_issues,
        "模块索引": index_issues,
    }
    counts = {"quotes": quote_count, "mis": len(mis_files), "steps": len(step_files), "index": index_count}
    passed = all(not issues for issues in findings.values())
    print(f"[正式模块放行审核] title={args.title} mode={'候选' if candidate_mode else '正式'} result={'通过' if passed else '退回'}")
    for section, issues in findings.items():
        for issue in issues:
            print(f"{section}\t{issue}")
    if args.write_report:
        report = write_report(args.title, passed, findings, counts, candidate_mode)
        print(f"report\t{report}")
        refresh_dashboard()
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
