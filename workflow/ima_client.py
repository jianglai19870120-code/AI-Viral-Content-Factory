"""
ima 知识库客户端

⚠️ 关键架构事实（2026-08-12 实测确认，务必先读）：
- 本客户端当前实现**完全依赖本地网关** `http://127.0.0.1:18060`（见 MCP_BASE_URL）。
  无论是否配置 IMA_OPENAPI 凭证（mode 分支只是多塞两个 header），所有请求都打到这个本地端口，
  **而不是腾讯 IMA OpenAPI 的远端地址**。文档注释里写的「独立 HTTP 调用 Tencent IMA OpenAPI」
  在当前代码里**并未实现**——这是个历史误导，不要信。
- 当前 WorkBuddy 的 ima-mcp 连接器是 **stdio（进程内）连接器**，**不在本机监听 HTTP 端口**。
  已在「App 开着 + ima-mcp 已连接」的实时会话中实测：127.0.0.1:18060 处于 CLOSED（连接被拒绝）。
- 因此：本 ImaClient（含「OpenAPI 凭证通道」与「无凭证本地通道」两个分支）在**无头/子脚本**
  场景下**均无法连通**，会直接连接拒绝。**配置 OpenAPI 钥匙也救不了**——因为代码根本没去打腾讯远端。
- 真正能从 ima 取数的唯一可用路径，是 **agent 在对话内直接调用 ima-mcp 的 MCP 工具**
  （mcp__ima-mcp__get_knowledge_list / fetch_media_content），再由流水线读「本轮 ima-mcp 执行回执」
  （IMA_MCP_EXECUTION_RECEIPT，Path B）判定 S1 结果。这也是分发零配置（用户只需在 App 里
  点一下连接 ima-mcp、开着 App 跑）的根基。

若要给无头定时任务做「真正无人值守」的 S1 同步，须把本客户端重写为**真正调用腾讯 IMA OpenAPI
远端 REST 接口**（带 clientId/apiKey 直接打远端域名），而非 localhost:18060。在那之前，
不要指望 ImaClient / sync_incremental.py（Path A）能跑通——它不是「缺钥匙」，是「指错了路」。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import requests


@dataclass
class ImaNote:
    """ima 知识库笔记数据结构"""
    note_id: str
    title: str
    content: str = ""
    tags: list[str] = field(default_factory=list)
    notebook: str = ""
    created_at: str = ""
    updated_at: str = ""

    @classmethod
    def from_api_item(cls, item: dict) -> ImaNote:
        """从API返回的原始item构造"""
        raw_tags = item.get("tags") or item.get("labels") or []
        parsed_tags: list[str] = []
        for t in raw_tags:
            if isinstance(t, str):
                parsed_tags.append(t)
            elif isinstance(t, dict):
                parsed_tags.append(t.get("name", str(t)))

        return cls(
            note_id=str(item.get("note_id") or item.get("id") or item.get("noteId") or ""),
            title=item.get("title", "未命名笔记"),
            content=item.get("content") or item.get("text") or item.get("markdown") or "",
            tags=parsed_tags,
            notebook=item.get("notebook") or item.get("notebook_name") or item.get("kb_name") or "",
            created_at=item.get("created_at") or item.get("create_time") or "",
            updated_at=item.get("updated_at") or item.get("update_time") or "",
        )


class ImaClient:
    """ima 知识库历史本地网关客户端。

    这个类不是腾讯 ima 远端 OpenAPI 客户端。它只会访问 `IMA_MCP_BASE_URL`
    指向的历史 HTTP 网关，默认是 `http://127.0.0.1:18060`。

    WorkBuddy / Codex 的 `ima-mcp` 通常是对话内 stdio 连接器，不会暴露这个
    HTTP 端口。若当前会话没有 `mcp__ima-mcp__*` 工具，本客户端不能替代连接器。
    """

    MCP_BASE_URL = os.environ.get("IMA_MCP_BASE_URL", "http://127.0.0.1:18060")
    MAX_RETRIES = 3
    RETRY_DELAY = 2.0  # seconds
    DEFAULT_PAGE_SIZE = 50

    def __init__(self):
        self.client_id = os.environ.get("IMA_OPENAPI_CLIENTID", "")
        self.api_key = os.environ.get("IMA_OPENAPI_APIKEY", "")
        self.credentialed = bool(self.client_id and self.api_key)

        self.session = requests.Session()
        if self.credentialed:
            self.session.headers.update({
                "Content-Type": "application/json",
                "X-IMA-Client-ID": self.client_id,
                "X-IMA-API-Key": self.api_key,
            })
            mode = "历史本地网关鉴权模式（已读取环境变量，但仍经 IMA_MCP_BASE_URL，非直连腾讯）"
        else:
            # 降级分支：试图打 127.0.0.1:18060，但当前部署 ima-mcp 是 stdio 连接器、
            # 未暴露该端口，实测 CLOSED，故通常连接拒绝。仅供历史兼容，不可用。
            self.session.headers.update({"Content-Type": "application/json"})
            mode = "历史本地网关无凭证模式（当前连接器通常不暴露 HTTP 端口，可能连接失败）"
        print(f"[ima_client] 接入模式: {mode}")

    # ---- 底层请求 ----

    def _call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """调用 ima-mcp 工具，带自动重试"""
        url = f"{self.MCP_BASE_URL}/tools/{tool_name}"
        last_error = None

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                resp = self.session.post(url, json={"arguments": arguments}, timeout=60)
                resp.raise_for_status()
                data = resp.json()

                # 统一兼容多种返回格式
                if isinstance(data, dict):
                    if data.get("code") == 0 or data.get("success") is True:
                        return data.get("data", data)
                    if "result" in data:
                        return data.get("result")
                    if "content" in data:
                        # MCP 标准 content 字段
                        return data.get("content")

                return data
            except requests.exceptions.HTTPError as e:
                status = e.response.status_code if e.response is not None else "?"
                last_error = f"HTTP {status}: {e}"
                if status == 401 or status == 403:
                    raise RuntimeError(f"ima 知识库 API 鉴权失败: {last_error}")
            except requests.exceptions.RequestException as e:
                last_error = f"网络错误: {e}"

            if attempt < self.MAX_RETRIES:
                time.sleep(self.RETRY_DELAY * attempt)

        raise RuntimeError(
            f"ima 知识库请求失败（重试{self.MAX_RETRIES}次后）: {last_error}。"
            "当前客户端只支持历史本地 HTTP 网关；如果你使用的是 WorkBuddy/Codex 连接器，"
            "请在对话内调用已暴露的 ima-mcp 工具，而不是依赖本脚本。"
        )

    # ---- 公开接口 ----

    def list_notebooks(self) -> list[dict]:
        """列出当前账号下的知识库"""
        result = self._call_tool("ima_list_notebooks", {})
        if isinstance(result, list):
            return result
        if isinstance(result, dict):
            return result.get("notebooks", result.get("items", []))
        return []

    def list_notes(self, notebook_id: str, page: int = 1, page_size: int | None = None) -> list[ImaNote]:
        """拉取指定知识库的笔记列表（单页）"""
        ps = page_size or self.DEFAULT_PAGE_SIZE
        data = self._call_tool("ima_list_notes", {
            "notebook_id": notebook_id,
            "page": page,
            "page_size": ps,
        })
        items = data if isinstance(data, list) else data.get("notes", data.get("items", []))
        return [ImaNote.from_api_item(it) for it in items]

    def get_note_content(self, note_id: str) -> ImaNote:
        """获取单篇笔记的完整内容"""
        data = self._call_tool("ima_get_note_content", {"note_id": note_id})
        if isinstance(data, dict):
            return ImaNote.from_api_item(data)
        return ImaNote(note_id=note_id, title="未知", content=str(data))

    def fetch_all_notes(self, notebook_id: str) -> list[ImaNote]:
        """全量拉取指定知识库笔记（自动分页，去重）"""
        all_notes: list[ImaNote] = []
        seen_ids: set[str] = set()
        page = 1

        while True:
            notes = self.list_notes(notebook_id=notebook_id, page=page)
            if not notes:
                break

            for note in notes:
                if note.note_id and note.note_id not in seen_ids:
                    seen_ids.add(note.note_id)
                    all_notes.append(note)

            if len(notes) < self.DEFAULT_PAGE_SIZE:
                break
            page += 1

        return all_notes


# ---- 同步状态管理 ----

@dataclass
class SyncState:
    """同步状态"""
    last_sync_at: str = ""
    total_synced: int = 0
    note_ids: list[str] = field(default_factory=list)

    @classmethod
    def load(cls, state_file: Path) -> SyncState:
        if state_file.exists():
            data = json.loads(state_file.read_text(encoding="utf-8"))
            return cls(
                last_sync_at=data.get("last_sync_at", ""),
                total_synced=data.get("total_synced", 0),
                note_ids=data.get("note_ids", []),
            )
        return cls()

    def save(self, state_file: Path):
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps({
            "last_sync_at": self.last_sync_at,
            "total_synced": self.total_synced,
            "note_ids": self.note_ids,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    def has_note(self, note_id: str) -> bool:
        return note_id in self.note_ids

    def add_note(self, note_id: str):
        if not self.has_note(note_id):
            self.note_ids.append(note_id)
            self.total_synced = len(self.note_ids)


# ---- 笔记保存 ----

def save_note_to_markdown(note: ImaNote, output_dir: Path) -> Path:
    """将笔记保存为标准化的 Markdown 文件"""
    output_dir.mkdir(parents=True, exist_ok=True)

    # 文件名：{日期}_{时间}_{标题}.md
    ts = note.created_at or note.updated_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ts_clean = ts.replace(":", "-").replace(" ", "_")[:16]
    safe_title = note.title.replace("/", "-").replace("\\", "-").replace(":", "：")[:50]
    filename = f"{ts_clean}_{safe_title}.md"

    # 如果存在同名文件但 note_id 不同，追加 note_id 尾号
    filepath = output_dir / filename
    if filepath.exists():
        short_id = note.note_id[-6:] if len(note.note_id) > 6 else note.note_id
        filename = f"{ts_clean}_{safe_title}_{short_id}.md"
        filepath = output_dir / filename

    content_parts = [
        f"# {note.title}",
        "",
        f"- ima知识库 note_id: {note.note_id}",
        f"- 创建时间: {note.created_at}",
        f"- 更新时间: {note.updated_at}",
        f"- 标签: {', '.join(note.tags) if note.tags else '无'}",
        f"- 知识库: {note.notebook or '未知'}",
        "",
        "## 原文",
        "",
        note.content or "（无原文内容）",
        "",
        "---",
        f"同步时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "via ima 知识库 OpenAPI",
    ]

    filepath.write_text("\n".join(content_parts), encoding="utf-8")

    # 追加品牌尾注
    from workflow.common import append_brand_footer
    append_brand_footer(filepath)

    return filepath
