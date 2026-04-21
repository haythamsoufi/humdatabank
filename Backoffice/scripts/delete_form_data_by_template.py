#!/usr/bin/env python3
"""
Script to delete all FormData records linked to a specific template ID.

Usage:
    python scripts/delete_form_data_by_template.py [--template-id TEMPLATE_ID] [--dry-run] [--force]

Options:
    --template-id   The template ID to delete data for (default: 21)
    --dry-run       Preview what would be deleted without making changes
    --force         Skip confirmation prompt (for automated use)
"""

import argparse
import logging
import os
import sys

logger = logging.getLogger(__name__)

# Add the Backoffice directory to Python path
script_dir = os.path.dirname(os.path.abspath(__file__))
backoffice_dir = os.path.dirname(script_dir)
if backoffice_dir not in sys.path:
    sys.path.insert(0, backoffice_dir)

# Set up environment
if 'FLASK_CONFIG' not in os.environ:
    os.environ['FLASK_CONFIG'] = 'development'


def main():
    parser = argparse.ArgumentParser(
        description='Delete all FormData records linked to a specific template ID.'
    )
    parser.add_argument(
        '--template-id',
        type=int,
        default=21,
        help='Template ID to delete data for (default: 21)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview what would be deleted without making changes'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Skip confirmation prompt'
    )

    args = parser.parse_args()
    template_id = args.template_id
    dry_run = args.dry_run
    force = args.force

    try:
        from app import create_app
        from app.models.forms import FormData
        from app.models.form_items import FormItem
        from app.extensions import db

        app = create_app()

        with app.app_context():
            # First, let's count and preview what will be deleted
            # Find all FormItem IDs for this template
            form_item_ids = db.session.query(FormItem.id).filter(
                FormItem.template_id == template_id
            ).all()
            form_item_ids = [item_id for (item_id,) in form_item_ids]

            if not form_item_ids:
                logger.info("No FormItem records found for template_id=%s", template_id)
                return 0

            logger.info("Found %d FormItem records linked to template_id=%s", len(form_item_ids), template_id)

            # Count FormData records to be deleted
            form_data_count = FormData.query.filter(
                FormData.form_item_id.in_(form_item_ids)
            ).count()

            if form_data_count == 0:
                logger.info("No FormData records found for template_id=%s", template_id)
                return 0

            logger.info("Found %d FormData records to delete", form_data_count)

            if dry_run:
                logger.info("[DRY RUN] No changes made. Run without --dry-run to delete records.")

                # Show some sample data that would be deleted
                sample_data = FormData.query.filter(
                    FormData.form_item_id.in_(form_item_ids)
                ).limit(5).all()

                if sample_data:
                    logger.info("Sample records that would be deleted:")
                    for fd in sample_data:
                        val_preview = fd.value[:50] if fd.value else 'None'
                        logger.info("  - FormData(id=%s, form_item_id=%s, value=%s...)", fd.id, fd.form_item_id, val_preview)

                return 0

            # Confirmation prompt
            if not force:
                logger.warning("WARNING: This will permanently delete %d FormData records.", form_data_count)
                confirmation = input("Type 'DELETE' to confirm: ")
                if confirmation != 'DELETE':
                    logger.info("Aborted.")
                    return 1

            # Perform the deletion
            logger.info("Deleting %d FormData records...", form_data_count)

            # Use bulk delete for efficiency
            deleted_count = FormData.query.filter(
                FormData.form_item_id.in_(form_item_ids)
            ).delete(synchronize_session=False)

            db.session.commit()

            logger.info("Successfully deleted %d FormData records linked to template_id=%s", deleted_count, template_id)
            return 0

    except Exception as e:
        logger.error("Error: %s", e)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    sys.exit(main())
