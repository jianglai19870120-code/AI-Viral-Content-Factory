#!/usr/bin/env python3
"""Report a verified milestone from a user-visible Codex Desktop task."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


def main() -> int:
    parser = argparse.ArgumentParser(description="向 AI爆款内容工厂工作台回写可见 Codex 任务状态")
    parser.add_argument("--session", required=True, help="工作台任务包 ID")
    parser.add_argument(
        "--event",
        required=True,
        choices=("started", "repairing", "reconnecting", "waiting-user", "waiting-audit", "released", "rejected", "blocked"),
        help="配图退回使用 repairing；外部异常使用 reconnecting，均不会终止恢复链。",
    )
    parser.add_argument("--message", default="", help="不含密钥或正文内容的简短阶段说明")
    parser.add_argument("--completion-basis", choices=("audit-approved", "no-pending"), default="", help="今日刷新任务正式完成的依据")
    parser.add_argument("--audit-receipt", default="", help="审核放行时对应的正式小审回执项目相对路径")
    parser.add_argument("--recovery-state", default="", help="工作包 render-state.json 路径，仅 reconnecting/repairing 回写")
    parser.add_argument("--next-retry-at", default="", help="控制器给出的下一次自动恢复 ISO 时间")
    parser.add_argument("--failure-class", default="", help="外部异常类别，如 image-service 或 desktop-bridge")
    parser.add_argument("--port", type=int, default=8766, help="本机工作台端口")
    args = parser.parse_args()

    # The one-time signature is never placed in the Codex prompt. This local
    # helper reads it from the workbench runtime created for the same session.
    runtime_roots: list[Path] = []
    configured = os.environ.get("AI_VIRAL_WORKBENCH_RUNTIME", "")
    if configured:
        runtime_roots.append(Path(configured))
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        runtime_roots.append(Path(local_app_data) / "AI-Viral-Content-Factory" / "workbench")
    # The persistent workbench service can run as SYSTEM while Codex runs in
    # the signed-in user session.  Its intentionally shared ProgramData
    # runtime is the authoritative fallback for the per-task local token.
    program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
    runtime_roots.append(Path(program_data) / "AI-Viral-Content-Factory" / "workbench")
    token_file = None
    report_token = ""
    for runtime_root in runtime_roots:
        candidate = runtime_root / "bridge-tokens" / f"{args.session}.token"
        try:
            report_token = candidate.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        token_file = candidate
        break
    if not token_file:
        print("工作台回写签名不可用：未找到当前任务的本机签名文件")
        return 1
    if not report_token:
        print("工作台回写签名不可用")
        return 1

    payload = json.dumps(
        {
            "sessionId": args.session,
            "reportToken": report_token,
            "event": args.event,
            "message": args.message,
            "completionBasis": args.completion_basis,
            "auditReceiptPath": args.audit_receipt,
            "recoveryStatePath": args.recovery_state,
            "recoveryNextAt": args.next_retry_at,
            "recoveryFailureClass": args.failure_class,
        }, ensure_ascii=False
    ).encode("utf-8")
    request = Request(
        f"http://127.0.0.1:{args.port}/api/visible-task-event",
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (URLError, OSError, json.JSONDecodeError) as exc:
        print(f"工作台事件回写失败：{exc}")
        return 1
    print(f"工作台已记录：{result.get('id', '')} · {result.get('status', '')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
