"""Detached P&B report build entrypoint — survives Flask dev-server restarts."""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    args = list(argv or sys.argv[1:])
    if len(args) < 2:
        print("usage: python -m app.pb_progress.build_runner <job_id> <language>", file=sys.stderr)
        return 2

    job_id = args[0].strip()
    language = args[1].strip() or "all"
    if not job_id:
        print("job_id is required", file=sys.stderr)
        return 2

    backoffice_dir = Path(__file__).resolve().parents[2]
    os.chdir(backoffice_dir)

    from app import create_app
    from app.pb_progress.service import PBProgressService

    config = os.getenv("FLASK_CONFIG") or "development"
    app = create_app(config)
    with app.app_context():
        PBProgressService.execute_build(job_id, language)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
