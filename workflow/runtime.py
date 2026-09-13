"""Resolve local-only runtime storage without coupling it to a checkout."""
from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def runtime_root() -> Path:
    """Return the configured runtime root, preserving the legacy default."""
    configured = os.environ.get("AI_TRAFFIC_RUNTIME_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return PROJECT_ROOT / ".runtime"
