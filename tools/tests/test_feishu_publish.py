from __future__ import annotations

import tempfile
import unittest
import zipfile
import json
from pathlib import Path
from unittest.mock import patch

import requests

from tools.release.feishu_publish import FeishuConfig, FeishuError, FeishuPublisher, root_token
from tools.release.build_feishu_delivery import MEMBER_CASE_REGISTRY, build_from_public_stage
from tools.release import publish_release
from tools.release.publish_release import execute, inspect_preflight, preflight


class Response:
    def __init__(self, payload: dict, ok: bool = True) -> None:
        self.payload, self.ok, self.text = payload, ok, ""

    def json(self) -> dict:
        return self.payload


class Client:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.file_token = "old-file"
        self.file_name = "AI爆款内容工厂-VIP-v3.0.1.zip"
        self.part_requests: list[dict[str, object]] = []

    def request(self, method: str, url: str, **kwargs: object) -> Response:
        self.calls.append((method, url))
        if url.endswith("tenant_access_token/internal"):
            return Response({"code": 0, "tenant_access_token": "tenant-token"})
        if url.endswith("/wiki/v2/spaces/get_node"):
            return Response({"code": 0, "data": {"node": {"space_id": "space-1", "node_token": "root-1", "obj_type": "docx", "obj_token": "doc-1"}}})
        if url.endswith("/docx/v1/documents/doc-1/blocks"):
            return Response({"code": 0, "data": {"items": [{"block_type": 23, "block_id": "file-block", "file": {"token": self.file_token, "name": self.file_name}}]}})
        if url.endswith("/drive/v1/medias/upload_all"):
            self.file_name = str(kwargs["data"]["file_name"])  # type: ignore[index]
            return Response({"code": 0, "data": {"file_token": "file-1"}})
        if url.endswith("/drive/v1/medias/upload_prepare"):
            return Response({"code": 0, "data": {"upload_id": "upload-1", "block_size": 3, "block_num": 2}})
        if url.endswith("/drive/v1/medias/upload_part"):
            self.part_requests.append(dict(kwargs))
            return Response({"code": 0, "data": {}})
        if url.endswith("/drive/v1/medias/upload_finish"):
            return Response({"code": 0, "data": {"file_token": "file-1"}})
        if url.endswith("/docx/v1/documents/doc-1/blocks/file-block"):
            self.file_token = str(kwargs["json"]["replace_file"]["token"])  # type: ignore[index]
            return Response({"code": 0, "data": {}})
        return Response({"code": 0, "data": {}})


class FeishuPublishTests(unittest.TestCase):
    def config(self) -> FeishuConfig:
        return FeishuConfig("app", "secret", "https://example.feishu.cn/wiki/root-token")

    def test_url_tokens_are_extracted_without_leaking_credentials(self) -> None:
        self.assertEqual(root_token("https://example.feishu.cn/wiki/root-token?from=copy"), "root-token")

    def test_missing_environment_configuration_is_actionable(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(FeishuError, "AI_VIRAL_FEISHU_APP_ID"):
                FeishuConfig.from_environment()

    def test_fixed_page_zip_replacement_is_idempotent_for_same_archive_hash(self) -> None:
        client = Client()
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "vip.zip"
            archive.write_bytes(b"vip")
            state = {"feishu": {"releases": {}}}
            publisher = FeishuPublisher(self.config(), client)
            first = publisher.publish_version(version="v3.1.0", github_url="https://github.com/example/release", archive=archive, archive_sha256="abc", state=state)
            calls_after_first = len(client.calls)
            second = publisher.publish_version(version="v3.1.0", github_url="https://github.com/example/release", archive=archive, archive_sha256="abc", state=state)
        self.assertEqual(first["file_block_id"], "file-block")
        self.assertEqual(first["previous_file_name"], "AI爆款内容工厂-VIP-v3.0.1.zip")
        self.assertEqual(first["current_file_name"], "vip.zip")
        self.assertEqual(first, second)
        self.assertEqual(calls_after_first + 2, len(client.calls))  # Root and ZIP block are revalidated; no mutation.

    def test_network_and_permission_failures_are_reported_as_release_errors(self) -> None:
        class OfflineClient:
            def request(self, *args: object, **kwargs: object) -> Response:
                raise requests.ConnectionError("offline")

        with self.assertRaisesRegex(FeishuError, "网络失败"):
            FeishuPublisher(self.config(), OfflineClient()).resolve_root()

        class DeniedClient(Client):
            def request(self, method: str, url: str, **kwargs: object) -> Response:
                if url.endswith("/wiki/v2/spaces/get_node"):
                    return Response({"code": 99991672, "msg": "permission denied"}, ok=False)
                return super().request(method, url, **kwargs)

        with self.assertRaisesRegex(FeishuError, "permission denied"):
            FeishuPublisher(self.config(), DeniedClient()).resolve_root()

    def test_large_archives_use_prepare_part_finish_upload(self) -> None:
        client = Client()
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "vip.zip"
            archive.write_bytes(b"abcde")
            result = FeishuPublisher(self.config(), client)._upload_delivery_multipart(archive, "file-block")
        self.assertEqual(result["file_token"], "file-1")
        self.assertEqual(len(client.part_requests), 2)
        self.assertEqual(client.part_requests[0]["data"]["seq"], "0")  # type: ignore[index]
        self.assertEqual(client.part_requests[1]["data"]["seq"], "1")  # type: ignore[index]

    def test_release_preflight_and_dry_run_are_non_mutating(self) -> None:
        root = Path(__file__).resolve().parents[2]
        preflight(root, "v3.2.2")
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            result = execute(root, "v3.2.2", dry_run=True, skip_gates=True, branch="main", state_path=state)
        self.assertEqual(result["status"], "dry-run")
        self.assertFalse(state.exists())

    def test_read_only_preflight_checks_page_without_saving_state(self) -> None:
        class ReadyPublisher:
            def resolve_root(self) -> dict[str, str]:
                return {"document_id": "doc-1"}

            def _vip_file_block(self, document_id: str) -> dict[str, str]:
                self_document_id = document_id
                return {"name": "VIP.zip", "block_id": self_document_id, "file_token": "file-1"}

        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / "state.json"
            with patch.object(publish_release, "audit_staged_package", return_value=[]), \
                 patch.object(publish_release, "git", return_value="https://github.com/example/factory.git"), \
                 patch.object(publish_release.FeishuConfig, "from_environment", return_value=self.config()), \
                 patch.object(publish_release, "FeishuPublisher", return_value=ReadyPublisher()):
                result = inspect_preflight(root, "v3.2.2", state)
        self.assertEqual(result["status"], "preflight-passed")
        self.assertEqual(result["feishu_page"]["zip_name"], "VIP.zip")
        self.assertFalse(state.exists())

    def test_vip_package_overlays_only_member_assets_on_public_projection(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "workspace"
            stage = Path(directory) / "public"
            output = Path(directory) / "vip.zip"
            (root / "00_系统说明").mkdir(parents=True)
            (stage / "00_系统说明").mkdir(parents=True)
            registry = '{"system":{"displayName":"测试工厂","version":"3.1.0"}}\n'
            (root / "00_系统说明/system-registry.json").write_text(registry, encoding="utf-8")
            (stage / "00_系统说明/system-registry.json").write_text(registry, encoding="utf-8")
            (root / MEMBER_CASE_REGISTRY).write_text(
                json.dumps({"schema": "benchmark-case-registry-v1", "typeCodes": {"晒成果型": "SCHX"}, "cases": [{"caseId": "SCHX-001"}]}, ensure_ascii=False),
                encoding="utf-8",
            )
            (stage / MEMBER_CASE_REGISTRY).write_text(
                json.dumps({"schema": "benchmark-case-registry-v1", "typeCodes": {}, "cases": []}, ensure_ascii=False),
                encoding="utf-8",
            )
            (stage / "README.md").write_text("public", encoding="utf-8")
            member = root / "02_资产中心/资料（会员专享）"
            member.mkdir(parents=True)
            (member / "vip.md").write_text("vip", encoding="utf-8")
            result = build_from_public_stage(root, stage, output, baseline="test")
            with zipfile.ZipFile(output) as archive:
                names = archive.namelist()
                registry_name = next(name for name in names if name.endswith(MEMBER_CASE_REGISTRY.as_posix()))
                delivered_case_registry = json.loads(archive.read(registry_name).decode("utf-8"))
        self.assertTrue(any(name.endswith("README.md") for name in names))
        self.assertTrue(any(name.endswith("资料（会员专享）/vip.md") for name in names))
        self.assertEqual(result["localMemberFilesOverlaid"], 2)
        self.assertEqual(delivered_case_registry["cases"][0]["caseId"], "SCHX-001")


if __name__ == "__main__":
    unittest.main()
