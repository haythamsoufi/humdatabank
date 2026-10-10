"""Database-level guarantees for template versions and the migration that adds them."""

import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.exc import IntegrityError

from app import db
from app.models import FormItem, FormSection, FormTemplateVersion
from app.utils.stable_key import generate_stable_key
from tests.factories import (
    create_test_draft_version,
    create_test_item,
    create_test_section,
    create_test_template,
)

pytestmark = pytest.mark.unit

MIGRATION = (
    Path(__file__).resolve().parents[3]
    / 'migrations' / 'versions' / 'add_template_version_integrity_constraints.py'
)
INDEXES = (
    'uq_form_template_version_single_draft',
    'uq_form_item_version_stable_key',
    'uq_form_section_version_stable_key',
)


def _load_migration():
    spec = importlib.util.spec_from_file_location('add_template_version_integrity', MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _index_names(connection):
    rows = connection.execute(db.text(
        "SELECT indexname FROM pg_indexes WHERE indexname LIKE 'uq_form_%_version_%'"
    ))
    return {row[0] for row in rows}


def _run(connection, step):
    context = MigrationContext.configure(connection)
    with Operations.context(context):
        step()


class TestIndexesEnforceTheRules:
    def test_second_draft_is_rejected(self, db_session, admin_user):
        template = create_test_template(db_session, owner_id=admin_user.id)
        create_test_draft_version(db_session, template)
        db_session.add(FormTemplateVersion(
            template_id=template.id, version_number=99, status='draft', name='second'
        ))
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_drafts_of_different_templates_are_fine(self, db_session, admin_user):
        first = create_test_template(db_session, owner_id=admin_user.id)
        second = create_test_template(db_session, owner_id=admin_user.id)
        create_test_draft_version(db_session, first)
        create_test_draft_version(db_session, second)
        db_session.commit()

    def test_duplicate_item_key_in_one_version_is_rejected(self, db_session, admin_user):
        template = create_test_template(db_session, owner_id=admin_user.id)
        version = template.published_version
        section = create_test_section(db_session, template, version=version)
        first = create_test_item(
            db_session, section, template, version=version, item_type='question', label='A', order=1
        )
        second = create_test_item(
            db_session, section, template, version=version, item_type='question', label='B', order=2
        )
        db_session.commit()
        second.stable_key = first.stable_key
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_same_item_key_in_different_versions_is_the_normal_case(self, db_session, admin_user):
        template = create_test_template(db_session, owner_id=admin_user.id)
        draft = create_test_draft_version(db_session, template)
        key = generate_stable_key()
        for version in (template.published_version, draft):
            section = create_test_section(db_session, template, version=version)
            item = create_test_item(
                db_session, section, template, version=version, item_type='question', label='Q'
            )
            item.stable_key = key
        db_session.commit()
        assert FormItem.query.filter_by(stable_key=key).count() == 2

    def test_duplicate_section_key_in_one_version_is_rejected(self, db_session, admin_user):
        template = create_test_template(db_session, owner_id=admin_user.id)
        version = template.published_version
        first = create_test_section(db_session, template, version=version, name='A', order=1)
        second = create_test_section(db_session, template, version=version, name='B', order=2)
        db_session.commit()
        second.stable_key = first.stable_key
        with pytest.raises(IntegrityError):
            db_session.flush()
        db_session.rollback()

    def test_rows_without_a_key_are_never_in_conflict(self, db_session, admin_user):
        template = create_test_template(db_session, owner_id=admin_user.id)
        version = template.published_version
        for order in (1, 2, 3):
            create_test_section(db_session, template, version=version, name=f'S{order}', order=order)
        db_session.flush()
        db_session.execute(db.text('UPDATE form_section SET stable_key = NULL'))
        db_session.commit()
        assert FormSection.query.filter(FormSection.stable_key.is_(None)).count() == 3


class TestMigration:
    def _drop_indexes(self, connection):
        for name in INDEXES:
            connection.execute(db.text(f'DROP INDEX IF EXISTS {name}'))

    def test_creates_the_indexes_on_clean_data(self, db_session, admin_user):
        create_test_template(db_session, owner_id=admin_user.id)
        db_session.commit()
        connection = db_session.connection()
        self._drop_indexes(connection)
        assert _index_names(connection) == set()

        migration = _load_migration()
        _run(connection, migration.upgrade)
        assert INDEXES == tuple(name for name in INDEXES if name in _index_names(connection))

        _run(connection, migration.downgrade)
        assert _index_names(connection) == set()

    def test_aborts_and_lists_offending_rows_instead_of_failing_halfway(
        self, db_session, admin_user, without_version_integrity_indexes
    ):
        template = create_test_template(db_session, owner_id=admin_user.id)
        first = create_test_draft_version(db_session, template)
        db_session.add(FormTemplateVersion(
            template_id=template.id, version_number=first.version_number + 1,
            status='draft', name='second',
        ))
        version = template.published_version
        section = create_test_section(db_session, template, version=version)
        a = create_test_item(
            db_session, section, template, version=version, item_type='question', label='A', order=1
        )
        b = create_test_item(
            db_session, section, template, version=version, item_type='question', label='B', order=2
        )
        b.stable_key = a.stable_key
        db_session.flush()

        connection = db_session.connection()
        migration = _load_migration()
        with pytest.raises(RuntimeError) as caught:
            _run(connection, migration.upgrade)
        message = str(caught.value)
        assert 'audit_template_versions.py' in message
        assert 'uq_form_template_version_single_draft' in message
        assert 'uq_form_item_version_stable_key' in message
        assert str(a.id) in message and str(b.id) in message
        assert _index_names(connection) == set()

    def test_revision_chain_is_linear(self):
        migration = _load_migration()
        assert migration.down_revision == 'add_ns_category_text'
        assert len(migration.revision) <= 32
