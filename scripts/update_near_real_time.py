#!/usr/bin/env python3
"""Generate a BADIA AI near-real-time snapshot without overwriting the saved demo."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.earth_engine_source import EarthEngineUnavailable  # noqa: E402
from backend.app.live_builder import build_live_snapshot  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ee-project", default=os.getenv("BADIA_EE_PROJECT", ""))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=REPO_ROOT / "data" / "near_real_time",
        help="Generated files go here; the historical demo is never overwritten by default.",
    )
    args = parser.parse_args()
    if not args.ee_project:
        print(
            "BADIA_EE_PROJECT is missing. Complete Earth Engine access once, then set "
            "BADIA_EE_PROJECT to your Google Cloud/Earth Engine project ID.",
            file=sys.stderr,
        )
        return 2
    try:
        result = build_live_snapshot(REPO_ROOT, args.ee_project, args.output_dir.resolve())
    except EarthEngineUnavailable as exc:
        print(str(exc), file=sys.stderr)
        return 3
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
