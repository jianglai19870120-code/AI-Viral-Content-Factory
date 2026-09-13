"""Build independent, auditable source inventories for the workbench."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from workflow.input_inventory import TYPES  # noqa: E402
from workflow.inventory_refresh import refresh_input_lists  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", choices=tuple(TYPES), help="仅重建指定来源类型的清单")
    args = parser.parse_args()
    result = refresh_input_lists(ROOT, [args.only] if args.only else TYPES)
    print(__import__("json").dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
