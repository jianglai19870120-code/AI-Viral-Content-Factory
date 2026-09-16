"""Idempotent Feishu publisher for the fixed VIP wiki page.

The member page is deliberately treated as user-authored content: publishing
may replace its one ZIP attachment, but never creates pages or rewrites text.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import requests


API_ROOT = "https://open.feishu.cn/open-apis"
WIKI_TOKEN = re.compile(r"/(?:wiki|space)/([^/?#]+)")


class FeishuError(RuntimeError):
    """A Feishu API operation could not be completed safely."""


class HttpClient(Protocol):
    def request(self, method: str, url: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class FeishuConfig:
    app_id: str
    app_secret: str
    root_url: str

    @classmethod
    def from_environment(cls) -> "FeishuConfig":
        values = {
            "app_id": os.environ.get("AI_VIRAL_FEISHU_APP_ID", "").strip(),
            "app_secret": os.environ.get("AI_VIRAL_FEISHU_APP_SECRET", "").strip(),
            "root_url": os.environ.get("AI_VIRAL_FEISHU_ROOT_URL", "").strip(),
        }
        missing = [name for name, value in values.items() if not value]
        if missing:
            labels = {
                "app_id": "AI_VIRAL_FEISHU_APP_ID",
                "app_secret": "AI_VIRAL_FEISHU_APP_SECRET",
                "root_url": "AI_VIRAL_FEISHU_ROOT_URL",
            }
            raise FeishuError("飞书发布未配置：" + "、".join(labels[name] for name in missing))
        return cls(**values)


def root_token(root_url: str) -> str:
    match = WIKI_TOKEN.search(root_url)
    if not match:
        raise FeishuError("AI_VIRAL_FEISHU_ROOT_URL 必须是飞书知识库页面链接")
    return match.group(1)


class FeishuPublisher:
    """Replace the one ZIP embedded in a fixed Feishu wiki document."""

    def __init__(self, config: FeishuConfig, client: HttpClient | None = None) -> None:
        self.config = config
        self.client = client or requests.Session()
        self._token = ""

    def _request(self, method: str, path: str, *, headers: dict[str, str] | None = None, **kwargs: Any) -> dict[str, Any]:
        all_headers = {"Authorization": f"Bearer {self._access_token()}", **(headers or {})}
        try:
            response = self.client.request(method, API_ROOT + path, headers=all_headers, timeout=30, **kwargs)
        except requests.RequestException as exc:
            raise FeishuError(f"飞书网络请求失败 {method} {path}: {exc}") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise FeishuError(f"飞书接口返回非 JSON：{path}") from exc
        if not getattr(response, "ok", False) or int(payload.get("code", 0)) != 0:
            message = str(payload.get("msg") or getattr(response, "text", "") or "未知错误")
            raise FeishuError(f"飞书接口失败 {method} {path}: {message}")
        return payload.get("data") or {}

    def _access_token(self) -> str:
        if self._token:
            return self._token
        try:
            response = self.client.request(
                "POST", API_ROOT + "/auth/v3/tenant_access_token/internal", timeout=30,
                json={"app_id": self.config.app_id, "app_secret": self.config.app_secret},
            )
        except requests.RequestException as exc:
            raise FeishuError(f"飞书应用鉴权网络失败：{exc}") from exc
        try:
            payload = response.json()
        except ValueError as exc:
            raise FeishuError("飞书鉴权接口返回非 JSON") from exc
        token = str(payload.get("tenant_access_token") or "")
        if not getattr(response, "ok", False) or int(payload.get("code", 0)) != 0 or not token:
            raise FeishuError("飞书应用鉴权失败，请检查 App ID、App Secret 和应用启用状态")
        self._token = token
        return token

    def resolve_root(self) -> dict[str, str]:
        data = self._request("GET", "/wiki/v2/spaces/get_node", params={"token": root_token(self.config.root_url)})
        node = data.get("node") or data
        space_id = str(node.get("space_id") or "")
        node_token = str(node.get("node_token") or "")
        document_id = str(node.get("obj_token") or "")
        if not space_id or not node_token or node.get("obj_type") != "docx" or not document_id:
            raise FeishuError("知识库根页面必须是可编辑的新版云文档（docx）")
        return {"space_id": space_id, "node_token": node_token, "document_id": document_id}

    def _list_blocks(self, document_id: str) -> list[dict[str, Any]]:
        data = self._request("GET", f"/docx/v1/documents/{document_id}/blocks", params={"page_size": 500})
        blocks = data.get("items") or data.get("blocks") or []
        if not isinstance(blocks, list):
            raise FeishuError("飞书文档块响应格式异常")
        return [block for block in blocks if isinstance(block, dict)]

    def _vip_file_block(self, document_id: str) -> dict[str, str]:
        candidates: list[dict[str, str]] = []
        for block in self._list_blocks(document_id):
            file_data = block.get("file") or {}
            name = str(file_data.get("name") or "")
            block_id = str(block.get("block_id") or "")
            token = str(file_data.get("token") or "")
            if block.get("block_type") == 23 and block_id and name.lower().endswith(".zip"):
                candidates.append({"block_id": block_id, "file_token": token, "name": name})
        if len(candidates) != 1:
            raise FeishuError(f"固定知识库页面必须且只能有一个 ZIP 附件，当前找到 {len(candidates)} 个")
        return candidates[0]

    def upload_delivery(self, archive: Path, file_block_id: str) -> dict[str, str]:
        if not archive.is_file():
            raise FeishuError(f"会员交付包不存在：{archive}")
        with archive.open("rb") as stream:
            data = self._request(
                "POST", "/drive/v1/medias/upload_all",
                data={"file_name": archive.name, "parent_type": "docx_file", "parent_node": file_block_id, "size": str(archive.stat().st_size)},
                files={"file": (archive.name, stream, "application/zip")},
            )
        file_token = str(data.get("file_token") or data.get("file", {}).get("token") or "")
        if not file_token:
            raise FeishuError("飞书上传成功响应缺少 file_token")
        return {"file_token": file_token}

    def _replace_file_block(self, document_id: str, block_id: str, file_token: str) -> None:
        self._request(
            "PATCH", f"/docx/v1/documents/{document_id}/blocks/{block_id}",
            params={"document_revision_id": -1}, json={"replace_file": {"token": file_token}},
        )

    def publish_version(self, *, version: str, github_url: str, archive: Path, archive_sha256: str, state: dict[str, Any]) -> dict[str, Any]:
        """Replace only the existing ZIP block; user-authored text stays intact."""
        del github_url  # The fixed page's explanatory copy is never rewritten.
        root = self.resolve_root()
        releases = state.setdefault("feishu", {}).setdefault("releases", {})
        target = self._vip_file_block(root["document_id"])
        known = releases.get(version)
        if isinstance(known, dict) and known.get("archive_sha256") == archive_sha256:
            if known.get("file_block_id") == target["block_id"] and known.get("file_token") == target["file_token"]:
                return known
            raise FeishuError("会员 ZIP 已被人工变更，拒绝覆盖；请使用新版本号或核对发布状态")
        uploaded = self.upload_delivery(archive, target["block_id"])
        self._replace_file_block(root["document_id"], target["block_id"], uploaded["file_token"])
        verified = self._vip_file_block(root["document_id"])
        if verified["block_id"] != target["block_id"] or verified["file_token"] != uploaded["file_token"] or verified["name"] != archive.name:
            raise FeishuError("飞书 ZIP 替换后校验失败，停止发布；请保留现场并从该阶段重试")
        result = {
            "version": version,
            "archive_sha256": archive_sha256,
            "document_id": root["document_id"],
            "file_block_id": target["block_id"],
            "file_token": uploaded["file_token"],
            "previous_file_name": target["name"],
            "current_file_name": verified["name"],
        }
        releases[version] = result
        return result
