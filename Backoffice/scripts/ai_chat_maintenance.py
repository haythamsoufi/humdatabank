"""
AI Chat Maintenance Script (archive/purge)

This script is suitable for scheduling (cron/Windows Task Scheduler/Azure WebJob).
It uses the same configuration as the Flask app (env/.env + FLASK_CONFIG).
"""

from __future__ import annotations

import argparse
import logging
import os

from app import create_app

logger = logging.getLogger(__name__)
from app.services.ai_chat_retention import maintain_ai_chat_retention


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive/purge AI chat conversations based on retention policy.")
    parser.add_argument("--archive-days", type=int, default=None, help="Archive conversations older than N days")
    parser.add_argument("--purge-days", type=int, default=None, help="Purge conversations older than N days")
    parser.add_argument("--batch-size", type=int, default=None, help="Batch size per run")
    parser.add_argument("--user-id", type=int, default=None, help="Restrict to a single user_id")
    parser.add_argument("--dry-run", action="store_true", help="Do not write/delete anything")
    args = parser.parse_args()

    app = create_app(os.getenv("FLASK_CONFIG"))
    with app.app_context():
        stats = maintain_ai_chat_retention(
            archive_after_days=args.archive_days,
            purge_after_days=args.purge_days,
            batch_size=args.batch_size,
            dry_run=bool(args.dry_run),
            user_id=args.user_id,
        )
        logger.info("AI chat maintenance completed")
        logger.info("archived_conversations=%s", stats.archived_conversations)
        logger.info("purged_conversations=%s", stats.purged_conversations)
        logger.info("deleted_archives=%s", stats.deleted_archive_objects)
        logger.info("errors=%s", stats.errors)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    raise SystemExit(main())
