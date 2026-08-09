"""One-time reconcile linked AIDocument rows with their source SubmittedDocument metadata."""
from __future__ import annotations

import argparse

from app import create_app


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mirror SubmittedDocument privacy/metadata onto linked AIDocument rows."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count linked rows without committing changes.",
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        from app.extensions import db
        from app.models.documents import SubmittedDocument
        from app.models.embeddings import AIDocument
        from app.services.ai.documents.ingest import sync_ai_document_from_submitted

        pairs = (
            db.session.query(SubmittedDocument, AIDocument)
            .join(AIDocument, AIDocument.submitted_document_id == SubmittedDocument.id)
            .all()
        )
        synced = 0
        for submitted, ai_doc in pairs:
            if args.dry_run:
                synced += 1
                continue
            if sync_ai_document_from_submitted(submitted, ai_doc=ai_doc):
                synced += 1

        if args.dry_run:
            print(f"Dry run: would sync {synced} linked AI document(s).")
            return 0

        db.session.commit()
        print(f"Synced {synced} linked AI document(s).")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
