#!/usr/bin/env python3
"""Verify and, when authorized, repair an installed Skill contract."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from tools.platform.sync_skills import apply_files, directory_files, digest, expected_install_files, load_registry, skill_version
except ModuleNotFoundError:  # Direct execution from tools/platform.
    from sync_skills import apply_files, directory_files, digest, expected_install_files, load_registry, skill_version


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="校验并激活 AI爆款内容工厂 Skill 合同")
    parser.add_argument("--root", default=".")
    parser.add_argument("--skill", required=True)
    parser.add_argument("--target", choices=("codex", "workbuddy", "all"), default="codex")
    parser.add_argument("--repair", action="store_true", help="发现安装副本漂移时自动同步并复验")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def _install_root(root: Path, target: str) -> Path:
    return root / ".agents" / "skills" if target == "codex" else Path.home() / ".workbuddy" / "skills"


def activate(root: Path, skill_id: str, target: str, repair: bool) -> dict:
    registry = load_registry(root)
    skill = next((item for item in registry.get("skills", []) if item.get("id") == skill_id), None)
    if skill is None:
        return {"status": "rejected", "reason": f"未注册 Skill：{skill_id}"}
    expected = expected_install_files(root, registry, skill, target)
    install_root = _install_root(root, target)
    destination = install_root / (skill["id"] if target == "codex" else skill["displayName"])
    before_match = digest(directory_files(destination)) == digest(expected)
    repaired = False
    if not before_match and repair:
        apply_files(destination, expected)
        repaired = True
    matched = digest(directory_files(destination)) == digest(expected)
    manifest = json.loads(expected[".generated-manifest.json"].decode("utf-8"))
    peer_results: list[dict] = []
    for peer_id, peer_version in (manifest.get("activation") or {}).get("requiredPeerSkillVersions", {}).items():
        peer = next((item for item in registry.get("skills", []) if item.get("id") == peer_id), None)
        if peer is None:
            peer_results.append({"skill": peer_id, "status": "rejected", "reason": "注册表缺失"})
            continue
        peer_expected = expected_install_files(root, registry, peer, target)
        peer_destination = install_root / (peer["id"] if target == "codex" else peer["displayName"])
        peer_before = digest(directory_files(peer_destination)) == digest(peer_expected)
        if not peer_before and repair:
            apply_files(peer_destination, peer_expected)
        peer_matched = digest(directory_files(peer_destination)) == digest(peer_expected)
        peer_results.append({
            "skill": peer_id,
            "expectedVersion": peer_version,
            "status": "approved" if peer_matched and skill_version(registry, peer) == peer_version else "rejected",
            "repaired": not peer_before and peer_matched,
        })
    approved = matched and all(item["status"] == "approved" for item in peer_results)
    return {
        "status": "approved" if approved else "rejected",
        "skill": skill_id,
        "target": target,
        "contractVersion": skill_version(registry, skill),
        "contractActivation": manifest.get("activation", {}),
        "wasDrifted": not before_match,
        "repaired": repaired,
        "peerSkills": peer_results,
        "installPath": str(destination),
        "reason": "" if approved else "安装副本、同链 Skill 或正式合同未能完成自动同步",
    }


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    targets = ("codex", "workbuddy") if args.target == "all" else (args.target,)
    results = [activate(root, args.skill, target, args.repair) for target in targets]
    payload = {"schema": "ai-traffic-skill-activation-result-v1", "status": "approved" if all(item["status"] == "approved" for item in results) else "rejected", "results": results}
    print(json.dumps(payload, ensure_ascii=False, indent=2) if args.json else "\n".join(f"[{item['status'].upper()}] {item['target']} {item['skill']} {item['contractVersion']}" for item in results))
    return 0 if payload["status"] == "approved" else 1


if __name__ == "__main__":
    raise SystemExit(main())
