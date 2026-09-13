"""
Workflow Orchestrator 公共模块

提供：
- dispatch gate 封装（调度记录门禁）
- 状态管理（pipeline 进度追踪）
- 日志输出（统一格式）
- 目录路径常量
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from workflow.runtime import runtime_root
from workflow.asset_paths import resolve as asset_resolve
from typing import Any

# ---- 路径常量 ----

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DISPATCH_DIR = PROJECT_ROOT / "01_Agent系统" / "01_小姜-CEO助理Agent" / "99_本地运行记录" / "调度记录"
RUNTIME_ROOT = runtime_root()
STATE_DIR = RUNTIME_ROOT / "state"
STATE_FILE = STATE_DIR / "pipeline_state.json"
LOCAL_ONLY_ROOT = PROJECT_ROOT / ".workbuddy" / "local_only"
LOCAL_RUN_REPORT_ROOT = LOCAL_ONLY_ROOT / "reports"
INPUT_DIR = PROJECT_ROOT / "02_资产中心" / "01_输入库"
PROCESS_DIR = PROJECT_ROOT / "02_资产中心" / "02_处理库"
OUTPUT_DIR = PROJECT_ROOT / "02_资产中心" / "03_输出库"
IMA_SYNC_STATE = STATE_DIR / "ima_sync_state.json"

MEMBER_EXCLUSIVE_SUFFIX = "（会员专享）"


def resolve_member_child(parent: Path, name: str) -> Path:
    """Return the local directory, accepting either plain or member-exclusive names."""
    plain = parent / name
    if plain.exists():
        return plain
    if name.endswith(MEMBER_EXCLUSIVE_SUFFIX):
        return plain
    member = parent / f"{name}{MEMBER_EXCLUSIVE_SUFFIX}"
    if member.exists():
        return member
    return plain


def resolve_member_path(base: Path, *parts: str) -> Path:
    current = base
    for part in parts:
        current = resolve_member_child(current, part)
    return current


TOPICS_DIR = asset_resolve(PROJECT_ROOT, "topics.tables")
STRUCTURE_DIR = asset_resolve(PROJECT_ROOT, "output.structures.dry_goods")
DRAFT_DIR = asset_resolve(PROJECT_ROOT, "output.copies.dry_goods")
THINKING_MODULE_ROOT = asset_resolve(PROJECT_ROOT, "process.cases")
THINKING_DIR = THINKING_MODULE_ROOT / "01_案例卡"
THINKING_INDEX = THINKING_MODULE_ROOT / "02_案例卡索引" / "案例卡索引.jsonl"  # 现役案例卡只读索引；历史 TH 卡不参与新链路

ALLOWED_STEP_STATUSES = {
    "pending",
    "running",
    "needs-agent",
    "needs-user",
    "completed",
    "rejected",
    "blocked",
}

# ---- 品牌尾注 ----

# ⚠️ 硬规则：三行文案不允许改写，append_brand_footer() 是全局唯一品牌尾注写入入口
BRAND_FOOTER = """---

• 带你3小时跑通用AI做IP，批量出爆款。
• 有任何使用问题，可加入我们会员答疑群。
• 我是姜来已来，微信： lact175

---
"""

BRAND_FOOTER_SENTINEL = "带你3小时跑通用AI做IP，批量出爆款。"

# 兼容历史尾注：允许缺少前后分隔线，以及“微信：lact175”少一个空格。
# 只匹配完整三行品牌文案，避免误删正文中单独出现的品牌句。
_BRAND_FOOTER_VARIANT_RE = re.compile(
    r"(?:\r?\n[ \t]*)?(?:---[ \t]*\r?\n(?:[ \t]*\r?\n)?)?"
    r"•[ \t]*带你(?:30天|3小时)跑通用AI做IP，批量出爆款。[ \t]*\r?\n"
    r"•[ \t]*有任何使用问题，可加入我们会员答疑群。[ \t]*\r?\n"
    r"•[ \t]*我是姜来已来，微信：[ \t]*lact175[ \t]*"
    r"(?:\r?\n(?:[ \t]*\r?\n)?[ \t]*---[ \t]*)?",
    re.MULTILINE,
)


def _normalize_brand_footer_text(text: str) -> str:
    """移除全部完整三行尾注变体，并在文件末尾追加唯一规范尾注。"""
    body = _BRAND_FOOTER_VARIANT_RE.sub("", text).rstrip()
    return body + "\n\n" + BRAND_FOOTER


def append_brand_footer(filepath: Path) -> bool:
    """
    在 Markdown 文件末尾追加品牌尾注。

    自动去重并规范化历史变体：最终只保留一个规范尾注。
    返回 True 表示文件发生追加/规范化，False 表示原文件已完全规范。
    """
    try:
        text = filepath.read_text(encoding="utf-8")
    except (FileNotFoundError, PermissionError):
        return False

    normalized = _normalize_brand_footer_text(text)
    if normalized == text:
        return False
    filepath.write_text(normalized, encoding="utf-8")
    return True


def append_brand_footer_text(text: str) -> str:
    """
    字符串入 / 字符串出的品牌尾注拼接版（供内存中组装后由调用方自己 write 的脚本使用）。

    与 append_brand_footer() 共用同一份 BRAND_FOOTER 常量（单一来源，三行文案不允许改写）。
    自动去重并规范化历史三行尾注变体，最终只保留一个规范尾注。
    """
    return _normalize_brand_footer_text(text)


def append_brand_footer_to_dir(directory: Path, glob_pattern: str = "*.md", recursive: bool = False) -> int:
    """
    批量对目录下的 Markdown 文件追加品牌尾注。

    返回成功追加的文件数量（不含跳过的）。
    """
    count = 0
    pattern = f"**/{glob_pattern}" if recursive else glob_pattern
    for filepath in directory.glob(pattern):
        if append_brand_footer(filepath):
            count += 1
    return count


# ---- 调度记录门禁 ----

@dataclass(frozen=True)
class DispatchRecord:
    path: Path
    task_name: str
    task_type: str
    target_agent: str
    input_source: str
    requires_audit: str
    created_at: str


def create_dispatch_record(
    task_name: str,
    task_type: str,
    target_agent: str,
    input_source: str,
    requires_audit: str = "是",
) -> DispatchRecord:
    """创建小姜正式分配记录 .md 文件"""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    safe_name = task_name.replace(" ", "_").replace("/", "_").replace(":", "_").replace("？", "").replace("？", "")[:40]

    content = f"""# 小姜正式分配记录

- 任务名称：{task_name}
- 任务类型：{task_type}
- 目标 Agent：{target_agent}
- 输入来源：{input_source}
- 是否需要小审：{requires_audit}
- 创建时间：{now}

## 分配结论

小姜已将「{task_name}」分配给 {target_agent}。
{target_agent} 请按自身能力清单和调用规则执行。
"""

    DISPATCH_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{timestamp}_小姜正式分配_{target_agent}_{safe_name}.md"
    filepath = DISPATCH_DIR / filename
    filepath.write_text(content, encoding="utf-8")

    # 追加品牌尾注
    append_brand_footer(filepath)

    return DispatchRecord(
        path=filepath,
        task_name=task_name,
        task_type=task_type,
        target_agent=target_agent,
        input_source=input_source,
        requires_audit=requires_audit,
        created_at=now,
    )


def verify_dispatch_record(task_type: str, target_agent: str, input_keyword: str) -> DispatchRecord:
    """验证是否存在对应的调度记录，不存在则抛异常"""
    import re

    if not DISPATCH_DIR.exists():
        raise RuntimeError(
            f"调度记录目录不存在: {DISPATCH_DIR}\n"
            f"请先运行 create_dispatch_record() 创建小姜正式分配记录。"
        )

    for path in sorted(DISPATCH_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        text = path.read_text(encoding="utf-8", errors="ignore")

        t_type = _read_field(text, "任务类型")
        t_agent = _read_field(text, "目标 Agent")

        if task_type not in t_type:
            continue
        if target_agent not in t_agent:
            continue
        if input_keyword not in text:
            continue

        return DispatchRecord(
            path=path,
            task_name=_read_field(text, "任务名称"),
            task_type=t_type,
            target_agent=t_agent,
            input_source=_read_field(text, "输入来源"),
            requires_audit=_read_field(text, "是否需要小审"),
            created_at=_read_field(text, "创建时间"),
        )

    raise RuntimeError(
        f"未找到匹配的调度记录: task_type={task_type}, agent={target_agent}, keyword={input_keyword}\n"
        f"请先在 {DISPATCH_DIR} 创建小姜正式分配记录。"
    )


def _read_field(text: str, label: str) -> str:
    import re
    pattern = rf"^- {re.escape(label)}：\s*(?P<value>.+?)\s*$"
    match = re.search(pattern, text, flags=re.MULTILINE)
    return match.group("value").strip() if match else ""


# ---- 管道状态管理 ----

@dataclass
class PipelineState:
    pipeline_name: str
    steps: list[dict] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    error: str = ""

    def add_step(self, agent: str, action: str):
        self.steps.append({
            "agent": agent,
            "action": action,
            "status": "pending",
            "started_at": "",
            "finished_at": "",
            "error": "",
        })

    def start_step(self, index: int):
        if index < len(self.steps):
            self.steps[index]["status"] = "running"
            self.steps[index]["started_at"] = datetime.now().strftime("%H:%M:%S")

    def complete_step(self, index: int):
        if index < len(self.steps):
            self.steps[index]["status"] = "completed"
            self.steps[index]["finished_at"] = datetime.now().strftime("%H:%M:%S")

    def set_step_status(self, index: int, status: str, error: str = ""):
        if status not in ALLOWED_STEP_STATUSES:
            raise ValueError(f"非法工作流状态：{status}")
        if index < len(self.steps):
            self.steps[index]["status"] = status
            self.steps[index]["error"] = error
            if status in {"completed", "rejected", "blocked"}:
                self.steps[index]["finished_at"] = datetime.now().strftime("%H:%M:%S")

    def fail_step(self, index: int, error: str):
        self.set_step_status(index, "rejected", error)

    def save(self):
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "pipeline_name": self.pipeline_name,
            "steps": self.steps,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "error": self.error,
        }
        temp = STATE_FILE.with_suffix(".json.tmp")
        temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, STATE_FILE)

    @classmethod
    def load(cls, pipeline_name: str) -> PipelineState:
        if STATE_FILE.exists():
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            return cls(
                pipeline_name=data.get("pipeline_name", pipeline_name),
                steps=data.get("steps", []),
                started_at=data.get("started_at", ""),
                finished_at=data.get("finished_at", ""),
                error=data.get("error", ""),
            )
        return cls(pipeline_name=pipeline_name)


# ---- 日志 ----

def log(agent: str, msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] [{agent}] {msg}", flush=True)


def log_step(step_num: int, total: int, agent: str, action: str):
    ts = datetime.now().strftime("%H:%M:%S")
    bar = "▌" * step_num + "─" * (total - step_num)
    print(f"\n[{ts}] {bar}", flush=True)
    print(f"[{ts}] 步骤 {step_num}/{total} | {agent} | {action}", flush=True)


def log_error(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{ts}] ❌ 错误: {msg}", flush=True)


def log_done(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{ts}] ✅ {msg}", flush=True)
