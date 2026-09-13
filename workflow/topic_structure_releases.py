"""Topic-table bindings and release evidence for copy-structure publishing.

The topic table is deliberately not a storage location for structure links.
This module supplies the immutable row binding used in the runtime handoff and
the append-only, hash-verified release index used to derive table status.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TOPIC_DIR = ROOT / "02_资产中心" / "04_选题库" / "02_选题分类"
INDEX_PATH = ROOT / "04_数据中心" / "03_查询索引" / "topic-structure-release-index.json"
TOPIC_HEADER = ["核心关键词", "选题", "原爆款元素", "博主名", "点赞数", "链接", "是否选中", "对标复刻拆解编号", "状态"]
TOPIC_FILES = (
    "01_科学创业选题表.md", "02_能力成长选题表.md", "03_赚钱财富选题表.md",
    "04_个人IP选题表.md", "05_AI科技选题表.md", "99_其他类型选题表.md",
)
from workflow.benchmark_cases import CASE_ID

OWNER_FREEZE_SCHEMA = "owner-structure-four-freeze-v1"
STRUCTURE_CANDIDATE_SCHEMAS = {"copy-structure-v14", "copy-structure-v15", "copy-structure-v16"}
RELEASE_CANDIDATE_SCHEMAS = {"copy-structure-v8", "copy-structure-v9", "copy-structure-v13", *STRUCTURE_CANDIDATE_SCHEMAS}


def parse_benchmark_case_ids(value: str) -> tuple[str, ...]:
    """Parse the one-or-more case IDs stored in a single Markdown cell."""
    parts = [item.strip() for item in re.split(r"<br\s*/?>|\r?\n", str(value or ""), flags=re.IGNORECASE) if item.strip()]
    if not parts or any(not CASE_ID.fullmatch(item) for item in parts):
        raise ValueError("目标选题缺少合法对标复刻拆解编号；每行一个 <类型代码>-<三位流水号>")
    if len(set(parts)) != len(parts):
        raise ValueError("目标选题的对标复刻拆解编号不能重复")
    return tuple(parts)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _markdown_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _owner_confirmed_path(path: Path) -> bool:
    return path.name.lstrip().startswith(("√", "✓"))


def _structure_markdown_identity(path: Path) -> tuple[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    title = next((line.removeprefix("# 文案结构｜").strip() for line in lines if line.startswith("# 文案结构｜")), "")
    case = next((line.removeprefix("对标复刻拆解：").strip() for line in lines if line.startswith("对标复刻拆解：")), "")
    if not title or not CASE_ID.fullmatch(case):
        raise ValueError("人工冻结结构缺少合法标题或对标复刻拆解编号")
    return title, case


def _frozen_structure_four_rows(path: Path) -> list[dict[str, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    section = next((index for index, line in enumerate(lines) if line.strip() == "## 结构四"), None)
    if section is None:
        raise ValueError("人工冻结结构缺少结构四章节")
    header = ["编号", "核心大框架", "核心内容"]
    starts = [index for index, line in enumerate(lines[section + 1:], section + 1) if _markdown_row(line) == header]
    if len(starts) != 1:
        raise ValueError("结构四必须且只能有一张 FNN 核心框架表")
    rows: list[dict[str, str]] = []
    index = starts[0] + 2
    while index < len(lines) and lines[index].lstrip().startswith("|"):
        values = _markdown_row(lines[index])
        if len(values) != 3 or not all(values):
            raise ValueError("结构四每个核心 FNN 框架必须填写非空核心内容")
        rows.append({"framework_id": values[0], "framework_label": values[1], "frozen_content": values[2]})
        index += 1
    if not rows:
        raise ValueError("结构四没有可冻结的核心框架")
    return rows


def _candidate_payload(candidate: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _expected_structure_four(candidate: Path) -> list[dict[str, Any]]:
    payload = _candidate_payload(candidate)
    if payload is None or payload.get("schema") not in STRUCTURE_CANDIDATE_SCHEMAS:
        raise ValueError("人工冻结结构缺少可用的已审核结构候选")
    structure_four = ((payload.get("structures") or {}).get("structure_four") or {})
    rows = structure_four.get("core_frameworks") if isinstance(structure_four, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError("已审核结构候选缺少结构四核心框架")
    return [row for row in rows if isinstance(row, dict)]


def _validate_owner_structure_four(path: Path, entry: dict[str, Any], candidate: Path) -> None:
    if not path.is_file() or not _owner_confirmed_path(path):
        raise ValueError("人工冻结结构必须是存在且文件名带 √ 的正式 Markdown")
    title, case = _structure_markdown_identity(path)
    if title != str(entry.get("topic") or "") or case != str(entry.get("benchmark_case_id") or ""):
        raise ValueError("人工冻结结构的标题或对标编号与已审核结构候选不一致")
    actual = _frozen_structure_four_rows(path)
    expected = _expected_structure_four(candidate)
    expected_ids = [str(row.get("framework_block_id") or "") for row in expected]
    expected_labels = [str(row.get("framework_label") or "") for row in expected]
    if [row["framework_id"] for row in actual] != expected_ids or [row["framework_label"] for row in actual] != expected_labels:
        raise ValueError("人工结构四的核心 FNN 编号或名称与已审核正文骨架不一致")


def relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return str(path.resolve())


def split_row(line: str) -> list[str]:
    value = line.strip()
    if value.startswith("|"):
        value = value[1:]
    if value.endswith("|"):
        value = value[:-1]
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in value:
        if char == "|" and not escaped:
            cells.append("".join(current).strip().replace("\\|", "|"))
            current = []
        else:
            current.append(char)
        escaped = char == "\\" and not escaped
        if char != "\\":
            escaped = False
    cells.append("".join(current).strip().replace("\\|", "|"))
    return cells


def _is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def topic_rows(topic_dir: Path = TOPIC_DIR) -> list[dict[str, Any]]:
    """Read only the six v4.2 tables; legacy headers are a hard refusal."""
    rows: list[dict[str, Any]] = []
    for filename in TOPIC_FILES:
        path = topic_dir / filename
        if not path.is_file():
            raise ValueError(f"选题表不存在：{filename}")
        lines = path.read_text(encoding="utf-8").splitlines()
        header_index = next((i for i, line in enumerate(lines) if line.strip().startswith("|") and split_row(line) == TOPIC_HEADER), None)
        if header_index is None:
            raise ValueError(f"{filename} 不是 benchmark-topic-v4.2 九列合同")
        if header_index + 1 >= len(lines) or not _is_separator(split_row(lines[header_index + 1])):
            raise ValueError(f"{filename} 缺少合法表格分隔行")
        for line_number, line in enumerate(lines[header_index + 2:], start=header_index + 3):
            if not line.strip().startswith("|"):
                break
            cells = split_row(line)
            if len(cells) != len(TOPIC_HEADER):
                raise ValueError(f"{filename} 第{line_number}行不是九列")
            row = dict(zip(TOPIC_HEADER, cells))
            row.update({"topic_table_path": str(path.resolve()), "topic_table_relative_path": relative(path), "topic_table_line": line_number})
            row["row_fingerprint"] = row_fingerprint(row)
            rows.append(row)
    return rows


def row_fingerprint(row: dict[str, Any]) -> str:
    # 状态是发布后的派生字段；把它纳入指纹会导致首次回写“已生成结构”后，
    # 下一次刷新无法再匹配同一条已发布记录。
    stable = {
        key: str(row.get(key) or "").strip()
        for key in TOPIC_HEADER
        if key != "状态"
    }
    stable["topic_table_relative_path"] = str(row.get("topic_table_relative_path") or "").replace("\\", "/")
    return hashlib.sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def resolve_selected_topic(topic: str, topic_dir: Path = TOPIC_DIR, benchmark_case_id: str | None = None) -> dict[str, Any]:
    wanted = topic.strip()
    if not wanted:
        raise ValueError("必须指定非空选题")
    matched = [row for row in topic_rows(topic_dir) if str(row["选题"]).strip() == wanted]
    if not matched:
        raise ValueError(f"六张选题表没有精确选题：{wanted}")
    if len(matched) != 1:
        locations = "；".join(f"{row['topic_table_relative_path']}:{row['topic_table_line']}" for row in matched)
        raise ValueError(f"选题存在多个候选，必须人工消歧：{locations}")
    result = matched[0]
    if result["是否选中"].strip() != "是":
        raise ValueError("目标选题尚未标记为“是否选中=是”")
    benchmark_ids = parse_benchmark_case_ids(result["对标复刻拆解编号"])
    requested = str(benchmark_case_id or "").strip()
    if requested:
        if not CASE_ID.fullmatch(requested) or requested not in benchmark_ids:
            raise ValueError("指定的对标复刻拆解编号不在该选题行的绑定列表中")
        benchmark_id = requested
    elif len(benchmark_ids) == 1:
        benchmark_id = benchmark_ids[0]
    else:
        raise ValueError("目标选题绑定多个对标复刻拆解编号；必须显式指定其中一个编号")
    from workflow.benchmark_cases import approved_case
    approved_case(benchmark_id)
    return {**result, "selected_benchmark_case_id": benchmark_id, "benchmark_case_ids": list(benchmark_ids)}


def handoff_binding(row: dict[str, Any]) -> dict[str, str | int | list[str]]:
    return {
        "topic_table_path": str(row["topic_table_path"]),
        "topic_table_relative_path": str(row["topic_table_relative_path"]),
        "topic_table_line": int(row["topic_table_line"]),
        "row_fingerprint": str(row["row_fingerprint"]),
        "topic": str(row["选题"]).strip(),
        "benchmark_case_id": str(row.get("selected_benchmark_case_id") or row["对标复刻拆解编号"]).strip(),
        "benchmark_case_ids": list(row.get("benchmark_case_ids") or parse_benchmark_case_ids(row["对标复刻拆解编号"])),
    }


def _empty_index() -> dict[str, Any]:
    return {"schema": "topic-structure-release-index-v1", "entries": []}


def load_release_index(path: Path = INDEX_PATH) -> dict[str, Any]:
    if not path.is_file():
        return _empty_index()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"选题—结构发布索引不可读：{path}") from exc
    if payload.get("schema") != "topic-structure-release-index-v1" or not isinstance(payload.get("entries"), list):
        raise ValueError("选题—结构发布索引合同错误")
    return payload


def _receipt_approves_candidate(receipt: Path, candidate: Path) -> bool:
    try:
        data = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    subject = data.get("subject") if isinstance(data.get("subject"), dict) else {}
    try:
        candidate_schema = json.loads(candidate.read_text(encoding="utf-8")).get("schema")
    except (OSError, json.JSONDecodeError):
        return False
    # Historical structure releases remain verifiable, even though only
    # V14–V16 candidates may be consumed by the current final-copy contract.
    expected_type = {
        "copy-structure-v8": "copy-structure-v8", "copy-structure-v9": "copy-structure-v9",
        "copy-structure-v13": "copy-structure-v13", "copy-structure-v14": "copy-structure-v14",
        "copy-structure-v15": "copy-structure-v15", "copy-structure-v16": "copy-structure-v16",
    }.get(candidate_schema)
    return data.get("schema") == "audit-receipt-v3" and expected_type is not None and data.get("artifactType") == expected_type and data.get("status") == "approved" and subject.get("candidateSha256") == digest(candidate)


def _release_plan_approved_for_entry(entry: dict[str, Any], candidate: Path, receipt: Path) -> bool:
    """Verify the complete direct-topic release bundle, including its handoff."""
    plan_path = Path(str(entry.get("release_plan_path") or ""))
    if not plan_path.is_file() or entry.get("release_plan_sha256") != digest(plan_path):
        return False
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        receipt_data = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    binding = {key: entry.get(key) for key in ("topic_table_path", "topic_table_relative_path", "topic_table_line", "row_fingerprint", "topic", "benchmark_case_id")}
    plan_binding = plan.get("topic_table_binding")
    handoff = Path(str(plan.get("handoff_path") or ""))
    if (
        plan.get("schema") != "copy-structure-release-plan-v1"
        or not isinstance(plan_binding, dict)
        or any(plan_binding.get(key) != value for key, value in binding.items())
        or plan.get("candidate_sha256") != digest(candidate)
        or Path(str(plan.get("candidate_path") or "")).resolve() != candidate.resolve()
        or Path(str(plan.get("planned_output_path") or "")).resolve() != Path(str(entry.get("output_path") or "")).resolve()
        or not handoff.is_file()
        or plan.get("handoff_sha256") != digest(handoff)
    ):
        return False
    subject = receipt_data.get("subject") if isinstance(receipt_data.get("subject"), dict) else {}
    return subject.get("handoffSha256") == digest(handoff) and subject.get("releasePlanSha256") == digest(plan_path)


def _approved_structure_evidence(entry: dict[str, Any]) -> tuple[Path, Path] | None:
    """Validate the immutable producer/auditor evidence without reading its old output file.

    A later owner freeze is allowed to replace that file's path and structure-four
    contents, but never its candidate, release plan, or audit receipt.
    """
    candidate = Path(str(entry.get("candidate_path") or ""))
    receipt = Path(str(entry.get("audit_receipt_path") or ""))
    if not candidate.is_file() or not receipt.is_file() or entry.get("candidate_sha256") != digest(candidate):
        return None
    if not _receipt_approves_candidate(receipt, candidate) or not _release_plan_approved_for_entry(entry, candidate, receipt):
        return None
    payload = _candidate_payload(candidate)
    binding = payload.get("topic_table_binding") if payload else None
    expected_binding = {key: entry.get(key) for key in ("topic_table_path", "topic_table_relative_path", "topic_table_line", "row_fingerprint", "topic", "benchmark_case_id")}
    if (
        payload is None
        or payload.get("schema") not in RELEASE_CANDIDATE_SCHEMAS
        or not isinstance(binding, dict)
        or any(binding.get(key) != value for key, value in expected_binding.items())
        or str(payload.get("topic") or "").strip() != str(entry.get("topic") or "").strip()
        or str(payload.get("benchmark_case_id") or "").strip() != str(entry.get("benchmark_case_id") or "").strip()
    ):
        return None
    return candidate, receipt


def _owner_freeze_is_current(entry: dict[str, Any], candidate: Path, receipt: Path) -> bool:
    freeze = entry.get("owner_structure_four")
    if not isinstance(freeze, dict) or freeze.get("schema") != OWNER_FREEZE_SCHEMA or freeze.get("status") != "owner-approved":
        return False
    path = Path(str(freeze.get("structure_markdown_path") or ""))
    if (
        freeze.get("topic") != entry.get("topic")
        or freeze.get("benchmark_case_id") != entry.get("benchmark_case_id")
        or freeze.get("candidate_sha256") != digest(candidate)
        or Path(str(freeze.get("audit_receipt_path") or "")).resolve() != receipt.resolve()
        or not path.is_file()
        or freeze.get("structure_markdown_sha256") != digest(path)
    ):
        return False
    try:
        _validate_owner_structure_four(path, entry, candidate)
    except ValueError:
        return False
    return True


def _receipt_approves_final_copy(receipt: Path, candidate: Path) -> bool:
    try:
        data = json.loads(receipt.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    subject = data.get("subject") if isinstance(data.get("subject"), dict) else {}
    return data.get("schema") == "audit-receipt-v3" and data.get("artifactType") in {"final-copy-v2", "final-copy-v3"} and data.get("status") == "approved" and subject.get("candidateSha256") == digest(candidate)


def verified_final_copy(entry: dict[str, Any]) -> bool:
    """A final-copy status requires explicit index evidence, never a filename scan."""
    final = entry.get("final_copy")
    if not isinstance(final, dict):
        return False
    output = Path(str(final.get("output_path") or ""))
    candidate = Path(str(final.get("candidate_path") or ""))
    receipt = Path(str(final.get("audit_receipt_path") or ""))
    return (
        output.is_file()
        and candidate.is_file()
        and receipt.is_file()
        and final.get("output_sha256") == digest(output)
        and final.get("candidate_sha256") == digest(candidate)
        and _receipt_approves_final_copy(receipt, candidate)
    )


def verified_release_bindings(path: Path = INDEX_PATH) -> dict[tuple[str, str], dict[str, Any]]:
    """Return current, evidence-backed topic/benchmark-case bindings only.

    No filename is inspected here: status depends entirely on an index entry,
    its formal output hash, candidate hash and approved audit receipt.
    """
    result: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in load_release_index(path).get("entries", []):
        if not isinstance(entry, dict):
            continue
        topic, case = str(entry.get("topic") or "").strip(), str(entry.get("benchmark_case_id") or "").strip()
        if not topic or not CASE_ID.fullmatch(case):
            continue
        evidence = _approved_structure_evidence(entry)
        if evidence is None:
            continue
        candidate, receipt = evidence
        if _owner_freeze_is_current(entry, candidate, receipt):
            freeze = entry["owner_structure_four"]
            effective = dict(entry)
            # Keep the immutable structure-release output path separately.  The
            # effective path is the owner's current Structure 4, while the
            # release plan must remain bound to the original audited output.
            effective["base_release_output_path"] = str(entry.get("output_path") or "")
            effective["base_release_output_sha256"] = str(entry.get("output_sha256") or "")
            effective["output_path"] = str(Path(str(freeze["structure_markdown_path"])).resolve())
            effective["output_sha256"] = str(freeze["structure_markdown_sha256"])
            effective["structure_four_frozen"] = True
            effective["structure_input_authority"] = "owner-frozen"
            result[(topic, case)] = effective
            continue
        output = Path(str(entry.get("output_path") or ""))
        if output.is_file() and entry.get("output_sha256") == digest(output):
            result[(topic, case)] = entry
    return result


def record_owner_frozen_structure(*, structure_markdown: Path, path: Path = INDEX_PATH) -> dict[str, Any]:
    """Append the owner's current structure-four authority without rewriting history."""
    structure_markdown = structure_markdown.resolve()
    topic, case = _structure_markdown_identity(structure_markdown)
    candidates = [
        entry for entry in load_release_index(path).get("entries", [])
        if isinstance(entry, dict) and entry.get("topic") == topic and entry.get("benchmark_case_id") == case
    ]
    for base in reversed(candidates):
        evidence = _approved_structure_evidence(base)
        if evidence is None:
            continue
        candidate, receipt = evidence
        _validate_owner_structure_four(structure_markdown, base, candidate)
        updated = dict(base)
        updated["owner_structure_four"] = {
            "schema": OWNER_FREEZE_SCHEMA,
            "status": "owner-approved",
            "structure_markdown_path": str(structure_markdown),
            "structure_markdown_sha256": digest(structure_markdown),
            "confirmed_at": datetime.now(timezone.utc).astimezone().isoformat(),
            "topic": topic,
            "benchmark_case_id": case,
            "candidate_sha256": digest(candidate),
            "audit_receipt_path": str(receipt.resolve()),
        }
        write_release_index_entry(updated, path)
        return updated
    raise ValueError("未找到可供人工结构四冻结继承的已审核结构候选、发布计划和小审回执")


def build_release_entry(*, binding: dict[str, Any], output_path: Path, candidate_path: Path, audit_receipt_path: Path, release_plan_path: Path, published_at: str | None = None) -> dict[str, str | int]:
    if not _receipt_approves_candidate(audit_receipt_path, candidate_path):
        raise ValueError("发布索引仅接受当前候选对应的 approved 小审回执")
    entry = {
        "topic_table_path": str(binding["topic_table_path"]),
        "topic_table_relative_path": str(binding["topic_table_relative_path"]),
        "topic_table_line": int(binding["topic_table_line"]),
        "row_fingerprint": str(binding["row_fingerprint"]),
        "topic": str(binding["topic"]),
        "benchmark_case_id": str(binding["benchmark_case_id"]),
        "output_path": str(output_path.resolve()),
        "output_sha256": digest(output_path),
        "candidate_path": str(candidate_path.resolve()),
        "candidate_sha256": digest(candidate_path),
        "audit_receipt_path": str(audit_receipt_path.resolve()),
        "release_plan_path": str(release_plan_path.resolve()),
        "release_plan_sha256": digest(release_plan_path),
        "published_at": published_at or datetime.now(timezone.utc).astimezone().isoformat(),
    }
    if not _release_plan_approved_for_entry(entry, candidate_path, audit_receipt_path):
        raise ValueError("发布索引仅接受已锁定 handoff、候选、输出文件且获小审批准的发布计划")
    return entry


def write_release_index_entry(entry: dict[str, Any], path: Path = INDEX_PATH) -> None:
    payload = load_release_index(path)
    # 保留每次受控重生的历史；verified_release_bindings 按写入顺序选择最后一条
    # 当前且可核验的绑定。
    entries = list(payload["entries"])
    entries.append(entry)
    rendered = json.dumps({"schema": "topic-structure-release-index-v1", "entries": entries}, ensure_ascii=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=path.parent, suffix=".tmp") as handle:
        handle.write(rendered)
        temporary = Path(handle.name)
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def append_final_copy_binding(*, topic: str, benchmark_case_id: str, output_path: Path,
                              candidate_path: Path, audit_receipt_path: Path,
                              path: Path = INDEX_PATH) -> None:
    """Append final-copy evidence to the current structural release binding.

    This explicit operation is the sole route to `已生成正文`; it rejects
    missing hashes or a non-approved final-copy receipt.
    """
    current = verified_release_bindings(path).get((topic.strip(), benchmark_case_id.strip()))
    if current is None:
        raise ValueError("正文发布前必须存在当前、可核验的选题—结构发布绑定")
    if not output_path.is_file() or not candidate_path.is_file() or not _receipt_approves_final_copy(audit_receipt_path, candidate_path):
        raise ValueError("正文发布绑定缺少正式正文、候选或 approved 小审回执")
    updated = dict(current)
    if isinstance(updated.get("owner_structure_four"), dict):
        base_path = str(updated.pop("base_release_output_path", "") or "")
        base_sha = str(updated.pop("base_release_output_sha256", "") or "")
        if base_path and base_sha:
            updated["output_path"] = base_path
            updated["output_sha256"] = base_sha
    updated["final_copy"] = {
        "output_path": str(output_path.resolve()),
        "output_sha256": digest(output_path),
        "candidate_path": str(candidate_path.resolve()),
        "candidate_sha256": digest(candidate_path),
        "audit_receipt_path": str(audit_receipt_path.resolve()),
    }
    write_release_index_entry(updated, path)


def mark_structure_four_frozen(*, topic: str, benchmark_case_id: str,
                               output_path: Path, path: Path = INDEX_PATH) -> None:
    """Record the user's explicit structure-four freeze without guessing from text.

    The user may edit the released Markdown while filling structure four, so this
    appends a new checksum for that same formal output.  A partial edit can never
    become `已手动优化` merely because it contains a few non-empty cells.
    """
    current = verified_release_bindings(path).get((topic.strip(), benchmark_case_id.strip()))
    if current is None:
        raise ValueError("冻结结构四前必须存在当前、可核验的选题—结构发布绑定")
    if output_path.resolve() != Path(str(current["output_path"])).resolve() or not output_path.is_file():
        raise ValueError("冻结结构四必须针对当前发布索引绑定的正式结构文件")
    updated = dict(current)
    updated["output_sha256"] = digest(output_path)
    updated["structure_four_frozen"] = True
    updated["structure_four_frozen_at"] = datetime.now(timezone.utc).astimezone().isoformat()
    write_release_index_entry(updated, path)
