"""Tests for VersionDeployMigrationService."""

import pytest

from app import db
from app.models import FormData, FormItem, FormSection, FormTemplateVersion
from app.services.version_deploy_migration_service import VersionDeployMigrationService
from app.utils.stable_key import generate_stable_key
from tests.factories import (
    create_test_item,
    create_test_section,
    create_test_template,
    create_test_draft_version,
)


pytestmark = pytest.mark.unit


def _make_published_with_draft(db_session, admin_user):
    template = create_test_template(db_session, owner_id=admin_user.id)
    published = template.published_version
    draft = create_test_draft_version(db_session, template)
    draft.based_on_version_id = published.id
    db_session.commit()
    return template, published, draft


def test_migrate_submission_fks_moves_form_data(db_session, admin_user):
    template, published, draft = _make_published_with_draft(db_session, admin_user)
    pub_section = create_test_section(db_session, template, version=published)
    draft_section = create_test_section(db_session, template, version=draft)
    shared_key = generate_stable_key()

    pub_item = create_test_item(
        db_session, pub_section, template, version=published, item_type='question', label='Q1'
    )
    pub_item.stable_key = shared_key
    draft_item = create_test_item(
        db_session, draft_section, template, version=draft, item_type='question', label='Q1'
    )
    draft_item.stable_key = shared_key

    from tests.factories import create_test_assignment_entity_status
    aes = create_test_assignment_entity_status(db_session, template=template)
    row = FormData(
        assignment_entity_status_id=aes.id,
        form_item_id=pub_item.id,
        value='42',
    )
    db_session.add(row)
    db_session.commit()

    summary = VersionDeployMigrationService.migrate_submission_fks(
        published.id, draft.id, template.id
    )
    db_session.commit()

    assert summary['remapped_rows'] >= 1
    db.session.refresh(row)
    assert row.form_item_id == draft_item.id


def test_migrate_leaves_orphan_data_and_archives_old_item(db_session, admin_user):
    template, published, draft = _make_published_with_draft(db_session, admin_user)
    pub_section = create_test_section(db_session, template, version=published)
    create_test_section(db_session, template, version=draft)

    orphan_key = generate_stable_key()
    pub_item = create_test_item(
        db_session, pub_section, template, version=published, item_type='question', label='Removed'
    )
    pub_item.stable_key = orphan_key

    from tests.factories import create_test_assignment_entity_status
    aes = create_test_assignment_entity_status(db_session, template=template)
    row = FormData(
        assignment_entity_status_id=aes.id,
        form_item_id=pub_item.id,
        value='99',
    )
    db_session.add(row)
    db_session.commit()

    summary = VersionDeployMigrationService.migrate_submission_fks(
        published.id, draft.id, template.id
    )
    db_session.commit()

    db.session.refresh(row)
    assert row.form_item_id == pub_item.id
    db.session.refresh(pub_item)
    assert pub_item.archived is True
    assert summary['orphaned_items'] >= 1


def test_align_mismatched_keys_then_remaps_form_data(db_session, admin_user):
    """Simulates clone before_insert bug: draft has random key, published has NULL."""
    template, published, draft = _make_published_with_draft(db_session, admin_user)
    pub_section = create_test_section(db_session, template, version=published, order=1)
    draft_section = create_test_section(db_session, template, version=draft, order=1)

    pub_item = create_test_item(
        db_session, pub_section, template, version=published, item_type='question', label='Q1', order=1
    )
    draft_item = create_test_item(
        db_session, draft_section, template, version=draft, item_type='question', label='Q1', order=1
    )
    pub_item.stable_key = None
    draft_item.stable_key = generate_stable_key()
    db_session.commit()
    from tests.factories import create_test_assignment_entity_status
    aes = create_test_assignment_entity_status(db_session, template=template)
    row = FormData(
        assignment_entity_status_id=aes.id,
        form_item_id=pub_item.id,
        value='42',
    )
    db_session.add(row)
    db_session.commit()

    summary = VersionDeployMigrationService.migrate_submission_fks(
        published.id, draft.id, template.id
    )
    db_session.commit()

    assert summary['remapped_rows'] >= 1
    db.session.refresh(row)
    db.session.refresh(pub_item)
    db.session.refresh(draft_item)
    assert pub_item.stable_key == draft_item.stable_key
    assert row.form_item_id == draft_item.id


def test_first_deploy_returns_empty_summary(db_session, admin_user):
    template = create_test_template(db_session, owner_id=admin_user.id)
    draft = create_test_draft_version(db_session, template)
    summary = VersionDeployMigrationService.migrate_submission_fks(
        draft.id, draft.id, template.id
    )
    assert summary['remapped_rows'] == 0


def test_build_field_comparison_exact_match(db_session, admin_user):
    template, published, draft = _make_published_with_draft(db_session, admin_user)
    pub_section = create_test_section(db_session, template, version=published, name='S1', order=1)
    draft_section = create_test_section(db_session, template, version=draft, name='S1', order=1)
    shared_key = generate_stable_key()
    pub_item = create_test_item(
        db_session, pub_section, template, version=published, item_type='question', label='Q1', order=1
    )
    pub_item.stable_key = shared_key
    draft_item = create_test_item(
        db_session, draft_section, template, version=draft, item_type='question', label='Q1', order=1
    )
    draft_item.stable_key = shared_key
    db_session.commit()

    rows = VersionDeployMigrationService.build_field_comparison(
        published.id, draft.id, template.id
    )
    item_rows = [r for r in rows if r['entity_type'] == 'item' and r['draft_item']]
    assert len(item_rows) == 1
    assert item_rows[0]['confidence'] == 'exact'


def test_build_field_comparison_suggested_on_label_change(db_session, admin_user):
    template, published, draft = _make_published_with_draft(db_session, admin_user)
    pub_section = create_test_section(db_session, template, version=published, name='S1', order=1)
    draft_section = create_test_section(db_session, template, version=draft, name='S1', order=1)
    pub_key = generate_stable_key()
    pub_item = create_test_item(
        db_session, pub_section, template, version=published, item_type='question', label='Old label', order=1
    )
    pub_item.stable_key = pub_key
    draft_item = create_test_item(
        db_session, draft_section, template, version=draft, item_type='question', label='New label', order=1
    )
    draft_item.stable_key = generate_stable_key()
    db_session.commit()

    rows = VersionDeployMigrationService.build_field_comparison(
        published.id, draft.id, template.id
    )
    item_rows = [r for r in rows if r['entity_type'] == 'item' and r['draft_item']]
    assert item_rows[0]['confidence'] == 'suggested'
    summary = VersionDeployMigrationService.count_field_mapping_summary(
        published.id, draft.id, template.id
    )
    assert summary['suggested_items'] >= 1


def test_precondition_aborts_when_draft_has_section_submission_rows(db_session, admin_user):
    from app.models import RepeatGroupInstance
    from app.services.version_deploy_migration_service import VersionDeployMigrationError
    from tests.factories import create_test_assignment_entity_status

    template, published, draft = _make_published_with_draft(db_session, admin_user)
    pub_section = create_test_section(db_session, template, version=published)
    draft_section = create_test_section(db_session, template, version=draft)
    shared_key = generate_stable_key()
    pub_item = create_test_item(
        db_session, pub_section, template, version=published, item_type='question', label='Q1'
    )
    pub_item.stable_key = shared_key
    draft_item = create_test_item(
        db_session, draft_section, template, version=draft, item_type='question', label='Q1'
    )
    draft_item.stable_key = shared_key
    aes = create_test_assignment_entity_status(db_session, template=template)
    db_session.add(
        RepeatGroupInstance(
            section_id=draft_section.id,
            instance_number=1,
            assignment_entity_status_id=aes.id,
            created_by_user_id=admin_user.id,
        )
    )
    db_session.commit()

    with pytest.raises(VersionDeployMigrationError):
        VersionDeployMigrationService.migrate_submission_fks(
            published.id, draft.id, template.id
        )
