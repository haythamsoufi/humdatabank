"""Extended tests for VersionDeployMigrationService (template version deploy).

These cover the data-continuity contract of deploying a template version:

* identity of fields/sections is the ``stable_key``, never position, once a key exists
* every submission table is carried forward, orphans are kept (and archived), nothing is lost
* per-page workflow status and cross-template variable references follow their fields
* rolling back to a previously published version restores what a deploy archived
"""

import pytest

from app import db
from app.models import (
    DynamicIndicatorData,
    DynamicSectionContext,
    FormData,
    FormItem,
    FormPage,
    FormSection,
    FormTemplateVersion,
    IndicatorBank,
    RepeatGroupData,
    RepeatGroupInstance,
)
from app.models.assignments import AssignmentPageStatus
from app.models.documents import SubmittedDocument
from app.services.platform.version_deploy_migration_service import (
    VersionDeployMigrationError,
    VersionDeployMigrationService,
)
from app.utils.stable_key import generate_stable_key
from tests.factories import (
    create_test_assignment_entity_status,
    create_test_draft_version,
    create_test_item,
    create_test_section,
    create_test_template,
)

pytestmark = pytest.mark.unit

Service = VersionDeployMigrationService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _versions(db_session, admin_user):
    template = create_test_template(db_session, owner_id=admin_user.id)
    published = template.published_version
    draft = create_test_draft_version(db_session, template)
    draft.based_on_version_id = published.id
    db_session.commit()
    return template, published, draft


def _pair(db_session, template, published, draft, *, order=1, section_name='S', item_order=1,
          label='Q', item_type='question', section_key=None, item_key=None):
    """Create one section + one question in each version sharing identity keys."""
    section_key = section_key or generate_stable_key()
    item_key = item_key or generate_stable_key()
    pub_section = create_test_section(db_session, template, version=published, name=section_name, order=order)
    drf_section = create_test_section(db_session, template, version=draft, name=section_name, order=order)
    pub_section.stable_key = drf_section.stable_key = section_key
    pub_item = create_test_item(
        db_session, pub_section, template, version=published, item_type=item_type,
        label=label, order=item_order,
    )
    drf_item = create_test_item(
        db_session, drf_section, template, version=draft, item_type=item_type,
        label=label, order=item_order,
    )
    pub_item.stable_key = drf_item.stable_key = item_key
    db_session.commit()
    return pub_section, drf_section, pub_item, drf_item


def _form_data(db_session, aes, item, value='1'):
    row = FormData(assignment_entity_status_id=aes.id, form_item_id=item.id, value=value)
    db_session.add(row)
    db_session.commit()
    return row


def _migrate(db_session, template, old, new, **kwargs):
    summary = Service.migrate_submission_fks(old.id, new.id, template.id, **kwargs)
    db_session.commit()
    return summary


def _bank(db_session, name='Indicator'):
    bank = IndicatorBank(name=f'{name} {generate_stable_key()[:8]}', type='number', archived=False)
    db_session.add(bank)
    db_session.commit()
    return bank


# ---------------------------------------------------------------------------
# Identity is the stable_key, not position
# ---------------------------------------------------------------------------

class TestKeyIdentityIsNotOverwrittenByPosition:
    def test_replaced_field_does_not_inherit_removed_fields_data(self, db_session, admin_user):
        """Delete question B, add an unrelated question C in its slot: B's data must not move to C."""
        template, published, draft = _versions(db_session, admin_user)
        pub_section, drf_section, pub_a, drf_a = _pair(
            db_session, template, published, draft, label='A', item_order=1
        )
        pub_b = create_test_item(
            db_session, pub_section, template, version=published, item_type='question',
            label='B', order=2,
        )
        new_c = create_test_item(
            db_session, drf_section, template, version=draft, item_type='question',
            label='C (unrelated)', order=2,
        )
        db_session.commit()
        b_key = pub_b.stable_key
        c_key = new_c.stable_key
        assert b_key != c_key

        aes = create_test_assignment_entity_status(db_session, template=template)
        a_row = _form_data(db_session, aes, pub_a, 'a')
        b_row = _form_data(db_session, aes, pub_b, 'b')

        summary = _migrate(db_session, template, published, draft)

        db_session.refresh(a_row)
        db_session.refresh(b_row)
        db_session.refresh(new_c)
        assert a_row.form_item_id == drf_a.id
        assert b_row.form_item_id == pub_b.id, "B's data must stay on B, not be cross-wired to C"
        assert new_c.stable_key == c_key
        assert summary['orphaned_items'] == 1
        db_session.refresh(pub_b)
        assert pub_b.archived is True

    def test_reordered_fields_keep_their_own_data(self, db_session, admin_user):
        """Swapping the order of two fields must not swap their submissions."""
        template, published, draft = _versions(db_session, admin_user)
        pub_section, drf_section, pub_a, drf_a = _pair(
            db_session, template, published, draft, label='A', item_order=1
        )
        pub_b = create_test_item(
            db_session, pub_section, template, version=published, item_type='question', label='B', order=2
        )
        drf_b = create_test_item(
            db_session, drf_section, template, version=draft, item_type='question', label='B', order=1
        )
        drf_b.stable_key = pub_b.stable_key
        drf_a.order = 2
        db_session.commit()

        aes = create_test_assignment_entity_status(db_session, template=template)
        a_row = _form_data(db_session, aes, pub_a, 'value-of-a')
        b_row = _form_data(db_session, aes, pub_b, 'value-of-b')

        _migrate(db_session, template, published, draft)

        db_session.refresh(a_row)
        db_session.refresh(b_row)
        assert a_row.form_item_id == drf_a.id
        assert b_row.form_item_id == drf_b.id
        assert (a_row.value, b_row.value) == ('value-of-a', 'value-of-b')

    def test_item_marked_as_new_field_stays_new_and_old_data_is_retained(self, db_session, admin_user):
        template, published, draft = _versions(db_session, admin_user)
        pub_section, drf_section, pub_a, drf_a = _pair(
            db_session, template, published, draft, label='A', item_order=1
        )
        pub_b = create_test_item(
            db_session, pub_section, template, version=published, item_type='question', label='B', order=2
        )
        drf_b = create_test_item(
            db_session, drf_section, template, version=draft, item_type='question', label='B', order=2
        )
        drf_b.stable_key = generate_stable_key()  # editor chose "this is a new field"
        db_session.commit()
        new_key = drf_b.stable_key

        aes = create_test_assignment_entity_status(db_session, template=template)
        a_row = _form_data(db_session, aes, pub_a)
        b_row = _form_data(db_session, aes, pub_b)

        _migrate(db_session, template, published, draft)

        db_session.refresh(a_row)
        db_session.refresh(b_row)
        db_session.refresh(drf_b)
        assert a_row.form_item_id == drf_a.id
        assert b_row.form_item_id == pub_b.id
        assert drf_b.stable_key == new_key

    def test_item_moved_to_another_section_keeps_data(self, db_session, admin_user):
        template, published, draft = _versions(db_session, admin_user)
        pub_s1, drf_s1, pub_item, drf_item = _pair(
            db_session, template, published, draft, order=1, section_name='One'
        )
        drf_s2 = create_test_section(db_session, template, version=draft, name='Two', order=2)
        drf_item.section_id = drf_s2.id
        db_session.commit()

        aes = create_test_assignment_entity_status(db_session, template=template)
        row = _form_data(db_session, aes, pub_item)

        _migrate(db_session, template, published, draft)
        db_session.refresh(row)
        assert row.form_item_id == drf_item.id


class TestLegacyKeyBackfillByPosition:
    def test_missing_keys_are_filled_from_position(self, db_session, admin_user):
        template, published, draft = _versions(db_session, admin_user)
        pub_section = create_test_section(db_session, template, version=published, order=1)
        drf_section = create_test_section(db_session, template, version=draft, order=1)
        pub_item = create_test_item(
            db_session, pub_section, template, version=published, item_type='question', label='Q', order=1
        )
        drf_item = create_test_item(
            db_session, drf_section, template, version=draft, item_type='question', label='Q', order=1
        )
        for row in (pub_section, drf_section, pub_item, drf_item):
            row.stable_key = None
        db_session.commit()

        aes = create_test_assignment_entity_status(db_session, template=template)
        data = _form_data(db_session, aes, pub_item)

        summary = _migrate(db_session, template, published, draft)
        for row in (pub_section, drf_section, pub_item, drf_item):
            db_session.refresh(row)
        db_session.refresh(data)

        assert pub_item.stable_key and pub_item.stable_key == drf_item.stable_key
        assert pub_section.stable_key == drf_section.stable_key
        assert data.form_item_id == drf_item.id
        assert summary['stable_key_alignment']['items'] == 1
        assert summary['stable_key_alignment']['sections'] == 1

    def test_legacy_indicators_are_paired_by_bank_entry(self, db_session, admin_user):
        template, published, draft = _versions(db_session, admin_user)
        bank = _bank(db_session)
        pub_section = create_test_section(db_session, template, version=published, order=1)
        drf_section = create_test_section(db_session, template, version=draft, order=1)
        pub_ind = create_test_item(
            db_session, pub_section, template, version=published, item_type='indicator',
            indicator_bank_id=bank.id, order=1,
        )
        drf_ind = create_test_item(
            db_session, drf_section, template, version=draft, item_type='indicator',
            indicator_bank_id=bank.id, order=5,
        )
        for row in (pub_section, drf_section, pub_ind, drf_ind):
            row.stable_key = None
        db_session.commit()

        aes = create_test_assignment_entity_status(db_session, template=template)
        data = _form_data(db_session, aes, pub_ind)

        summary = _migrate(db_session, template, published, draft)
        db_session.refresh(data)
        assert data.form_item_id == drf_ind.id
        assert summary['stable_key_alignment']['indicators'] == 1

    def test_ambiguous_positions_are_not_guessed(self, db_session, admin_user):
        """Two same-type fields at the same order on one side must not be paired arbitrarily."""
        template, published, draft = _versions(db_session, admin_user)
        pub_section = create_test_section(db_session, template, version=published, order=1)
        drf_section = create_test_section(db_session, template, version=draft, order=1)
        pub_section.stable_key = drf_section.stable_key = generate_stable_key()
        pub_1 = create_test_item(
            db_session, pub_section, template, version=published, item_type='question', label='P1', order=1
        )
        pub_2 = create_test_item(
            db_session, pub_section, template, version=published, item_type='question', label='P2', order=1
        )
        drf_1 = create_test_item(
            db_session, drf_section, template, version=draft, item_type='question', label='D1', order=1
        )
        for row in (pub_1, pub_2, drf_1):
            row.stable_key = None
        db_session.commit()

        section_matches, item_matches = Service._compute_positional_matches(
            published.id, draft.id, template.id
        )
        assert drf_1.id not in item_matches

    def test_every_row_has_a_key_after_deploy(self, db_session, admin_user):
        template, published, draft = _versions(db_session, admin_user)
        pub_section, drf_section, pub_item, drf_item = _pair(db_session, template, published, draft)
        extra_old = create_test_item(
            db_session, pub_section, template, version=published, item_type='question', label='old only', order=9
        )
        extra_new = create_test_item(
            db_session, drf_section, template, version=draft, item_type='question', label='new only', order=7
        )
        extra_old.stable_key = None
        extra_new.stable_key = None
        db_session.commit()

        _migrate(db_session, template, published, draft)
        for item in FormItem.query.filter(FormItem.template_id == template.id).all():
            assert item.stable_key, f'{item.label} was left without a stable_key'
        for section in FormSection.query.filter(FormSection.template_id == template.id).all():
            assert section.stable_key


# ---------------------------------------------------------------------------
# Safety guards
# ---------------------------------------------------------------------------

class TestDeploySafetyGuards:
    def test_duplicate_item_keys_in_new_version_abort_deploy(self, db_session, admin_user):
        template, published, draft = _versions(db_session, admin_user)
        pub_section, drf_section, pub_item, drf_item = _pair(db_session, template, published, draft)
        twin = create_test_item(
            db_session, drf_section, template, version=draft, item_type='question', label='twin', order=2
        )
        twin.stable_key = drf_item.stable_key
        db_session.commit()

        aes = create_test_assignment_entity_status(db_session, template=template)
        row = _form_data(db_session, aes, pub_item)

        with pytest.raises(VersionDeployMigrationError, match='shared by more than one field'):
            Service.migrate_submission_fks(published.id, draft.id, template.id)
        db_session.rollback()
        db_session.refresh(row)
        assert row.form_item_id == pub_item.id

    def test_duplicate_section_keys_in_new_version_abort_deploy(self, db_session, admin_user):
        template, published, draft = _versions(db_session, admin_user)
        pub_section, drf_section, _pi, _di = _pair(db_session, template, published, draft)
        twin = create_test_section(db_session, template, version=draft, name='twin', order=5)
        twin.stable_key = drf_section.stable_key
        db_session.commit()

        with pytest.raises(VersionDeployMigrationError, match='section'):
            Service.migrate_submission_fks(published.id, draft.id, template.id)

    def test_nothing_matches_but_old_version_has_data_aborts(self, db_session, admin_user):
        template, published, draft = _versions(db_session, admin_user)
        pub_section = create_test_section(db_session, template, version=published, order=1)
        pub_item = create_test_item(
            db_session, pub_section, template, version=published, item_type='question', order=1
        )
        create_test_section(db_session, template, version=draft, order=4)
        aes = create_test_assignment_entity_status(db_session, template=template)
        _form_data(db_session, aes, pub_item)

        with pytest.raises(VersionDeployMigrationError, match='no fields could be matched'):
            Service.migrate_submission_fks(published.id, draft.id, template.id)

    def test_same_version_is_a_noop(self, db_session, admin_user):
        template, published, _draft = _versions(db_session, admin_user)
        summary = Service.migrate_submission_fks(published.id, published.id, template.id)
        assert summary['remapped_rows'] == 0
        assert summary['per_table'] == {}

    def test_rows_on_unmatched_target_section_do_not_block(self, db_session, admin_user):
        """Only sections that actually receive remapped rows must be empty."""
        template, published, draft = _versions(db_session, admin_user)
        pub_section, drf_section, pub_item, drf_item = _pair(db_session, template, published, draft)
        stray = create_test_section(db_session, template, version=draft, name='stray', order=8)
        aes = create_test_assignment_entity_status(db_session, template=template)
        db_session.add(RepeatGroupInstance(
            section_id=stray.id, instance_number=1,
            assignment_entity_status_id=aes.id, created_by_user_id=admin_user.id,
        ))
        _form_data(db_session, aes, pub_item)
        db_session.commit()

        summary = _migrate(db_session, template, published, draft)
        assert summary['remapped_rows'] == 1


# ---------------------------------------------------------------------------
# Every submission table follows its field/section
# ---------------------------------------------------------------------------

class TestAllSubmissionTablesAreRemapped:
    def test_each_table_is_carried_forward(self, db_session, admin_user):
        template, published, draft = _versions(db_session, admin_user)
        pub_section, drf_section, pub_item, drf_item = _pair(db_session, template, published, draft)
        pub_repeat = create_test_section(
            db_session, template, version=published, name='Repeat', order=2, section_type='repeat'
        )
        drf_repeat = create_test_section(
            db_session, template, version=draft, name='Repeat', order=2, section_type='repeat'
        )
        pub_dynamic = create_test_section(
            db_session, template, version=published, name='Dyn', order=3, section_type='dynamic_indicators'
        )
        drf_dynamic = create_test_section(
            db_session, template, version=draft, name='Dyn', order=3, section_type='dynamic_indicators'
        )
        for pub, drf in ((pub_repeat, drf_repeat), (pub_dynamic, drf_dynamic)):
            pub.stable_key = drf.stable_key = generate_stable_key()
        pub_rep_item = create_test_item(
            db_session, pub_repeat, template, version=published, item_type='question', label='R', order=1
        )
        drf_rep_item = create_test_item(
            db_session, drf_repeat, template, version=draft, item_type='question', label='R', order=1
        )
        pub_rep_item.stable_key = drf_rep_item.stable_key = generate_stable_key()
        pub_doc = create_test_item(
            db_session, pub_section, template, version=published, item_type='document_field', label='Doc', order=2
        )
        drf_doc = create_test_item(
            db_session, drf_section, template, version=draft, item_type='document_field', label='Doc', order=2
        )
        pub_doc.stable_key = drf_doc.stable_key = generate_stable_key()
        bank = _bank(db_session)
        db_session.commit()

        aes = create_test_assignment_entity_status(db_session, template=template)
        fd = _form_data(db_session, aes, pub_item)
        instance = RepeatGroupInstance(
            section_id=pub_repeat.id, instance_number=1,
            assignment_entity_status_id=aes.id, created_by_user_id=admin_user.id,
        )
        db_session.add(instance)
        db_session.flush()
        rgd = RepeatGroupData(repeat_instance_id=instance.id, form_item_id=pub_rep_item.id, value='x')
        dyn = DynamicIndicatorData(
            assignment_entity_status_id=aes.id, section_id=pub_dynamic.id,
            indicator_bank_id=bank.id, added_by_user_id=admin_user.id,
        )
        ctx = DynamicSectionContext(
            assignment_entity_status_id=aes.id, section_id=pub_dynamic.id,
            provider_id='emergency_operations', context_key='MDR1',
        )
        doc = SubmittedDocument(
            assignment_entity_status_id=aes.id, form_item_id=pub_doc.id,
            filename='f.pdf', uploaded_by_user_id=admin_user.id,
        )
        db_session.add_all([rgd, dyn, ctx, doc])
        db_session.commit()

        summary = _migrate(db_session, template, published, draft)

        for row in (fd, instance, rgd, dyn, ctx, doc):
            db_session.refresh(row)
        assert fd.form_item_id == drf_item.id
        assert instance.section_id == drf_repeat.id
        assert rgd.form_item_id == drf_rep_item.id
        assert dyn.section_id == drf_dynamic.id
        assert ctx.section_id == drf_dynamic.id
        assert doc.form_item_id == drf_doc.id
        assert summary['remapped_rows'] == 6
        assert summary['orphaned_items'] == 0
        assert summary['orphaned_sections'] == 0

    def test_all_entities_data_is_carried_forward(self, db_session, admin_user):
        template, published, draft = _versions(db_session, admin_user)
        _ps, _ds, pub_item, drf_item = _pair(db_session, template, published, draft)
        rows = []
        for period in ('2024', '2025'):
            aes = create_test_assignment_entity_status(db_session, template=template, period_name=period)
            rows.append(_form_data(db_session, aes, pub_item, period))
        summary = _migrate(db_session, template, published, draft)
        for row in rows:
            db_session.refresh(row)
            assert row.form_item_id == drf_item.id
        assert summary['per_table']['form_data'] == 2

    def test_orphaned_section_is_archived_and_keeps_its_instances(self, db_session, admin_user):
        template, published, draft = _versions(db_session, admin_user)
        _pair(db_session, template, published, draft)
        pub_orphan = create_test_section(
            db_session, template, version=published, name='Removed', order=7, section_type='repeat'
        )
        aes = create_test_assignment_entity_status(db_session, template=template)
        instance = RepeatGroupInstance(
            section_id=pub_orphan.id, instance_number=1,
            assignment_entity_status_id=aes.id, created_by_user_id=admin_user.id,
        )
        db_session.add(instance)
        db_session.commit()

        summary = _migrate(db_session, template, published, draft)
        db_session.refresh(instance)
        db_session.refresh(pub_orphan)
        assert instance.section_id == pub_orphan.id
        assert pub_orphan.archived is True
        assert summary['orphaned_sections'] == 1

    def test_estimate_matches_actual_migration(self, db_session, admin_user):
        template, published, draft = _versions(db_session, admin_user)
        _ps, _ds, pub_item, _di = _pair(db_session, template, published, draft)
        aes = create_test_assignment_entity_status(db_session, template=template)
        _form_data(db_session, aes, pub_item)
        estimate = Service.estimate_migration_counts(published.id, draft.id, template.id)
        assert estimate['remappable_rows'] == 1
        assert estimate['matched_items'] == 1
        assert estimate['orphaned_items'] == 0
        summary = _migrate(db_session, template, published, draft)
        assert summary['remapped_rows'] == estimate['remappable_rows']


# ---------------------------------------------------------------------------
# Several versions in a row
# ---------------------------------------------------------------------------

class TestVersionChains:
    def test_data_follows_the_field_across_three_deploys(self, db_session, admin_user):
        template, v1, v2 = _versions(db_session, admin_user)
        _s1, s2, i1, i2 = _pair(db_session, template, v1, v2)
        aes = create_test_assignment_entity_status(db_session, template=template)
        row = _form_data(db_session, aes, i1, 'persisted')

        _migrate(db_session, template, v1, v2)
        v1.status, v2.status = 'archived', 'published'
        template.published_version_id = v2.id
        v3 = create_test_draft_version(db_session, template)
        s3 = create_test_section(db_session, template, version=v3, name='S', order=1)
        s3.stable_key = s2.stable_key
        i3 = create_test_item(db_session, s3, template, version=v3, item_type='question', label='Q', order=1)
        i3.stable_key = i2.stable_key
        db_session.commit()

        _migrate(db_session, template, v2, v3)
        db_session.refresh(row)
        assert row.form_item_id == i3.id
        assert row.value == 'persisted'

    def test_rollback_returns_data_and_restores_orphaned_fields(self, db_session, admin_user):
        template, v1, v2 = _versions(db_session, admin_user)
        pub_section, drf_section, kept_v1, kept_v2 = _pair(db_session, template, v1, v2, label='Kept')
        removed_v1 = create_test_item(
            db_session, pub_section, template, version=v1, item_type='question', label='Removed in v2', order=2
        )
        added_v2 = create_test_item(
            db_session, drf_section, template, version=v2, item_type='question', label='Added in v2', order=3
        )
        db_session.commit()
        aes = create_test_assignment_entity_status(db_session, template=template)
        kept_row = _form_data(db_session, aes, kept_v1, 'kept')
        removed_row = _form_data(db_session, aes, removed_v1, 'removed')

        # deploy v1 -> v2
        forward = _migrate(db_session, template, v1, v2)
        v1.status, v2.status = 'archived', 'published'
        template.published_version_id = v2.id
        db_session.commit()
        db_session.refresh(removed_v1)
        assert removed_v1.archived is True
        assert forward['orphaned_items'] == 1

        added_row = _form_data(db_session, aes, added_v2, 'added')

        # roll back v2 -> v1
        backward = _migrate(db_session, template, v2, v1, restore_archived=True)
        v1.status, v2.status = 'published', 'archived'
        template.published_version_id = v1.id
        db_session.commit()

        for row in (kept_row, removed_row, added_row, removed_v1, added_v2):
            db_session.refresh(row)
        assert kept_row.form_item_id == kept_v1.id
        assert removed_row.form_item_id == removed_v1.id
        assert removed_v1.archived is False, 'field removed by v2 must be visible again after rollback'
        assert backward['restored_items'] == 1
        assert added_row.form_item_id == added_v2.id, 'data of a v2-only field stays on v2'
        assert added_v2.archived is True

    def test_forward_deploy_does_not_unarchive_editor_archived_items(self, db_session, admin_user):
        template, published, draft = _versions(db_session, admin_user)
        _ps, drf_section, _pi, _di = _pair(db_session, template, published, draft)
        parked = create_test_item(
            db_session, drf_section, template, version=draft, item_type='question',
            label='parked', order=4, archived=True,
        )
        db_session.commit()
        summary = _migrate(db_session, template, published, draft)
        db_session.refresh(parked)
        assert parked.archived is True
        assert summary['restored_items'] == 0

    def test_rollback_keeps_editor_archived_item_present_in_both_versions(self, db_session, admin_user):
        template, v1, v2 = _versions(db_session, admin_user)
        pub_section, drf_section, _pi, _di = _pair(db_session, template, v1, v2)
        parked_v1 = create_test_item(
            db_session, pub_section, template, version=v1, item_type='question',
            label='parked', order=4, archived=True,
        )
        parked_v2 = create_test_item(
            db_session, drf_section, template, version=v2, item_type='question',
            label='parked', order=4, archived=True,
        )
        parked_v2.stable_key = parked_v1.stable_key
        db_session.commit()
        _migrate(db_session, template, v2, v1, restore_archived=True)
        db_session.refresh(parked_v1)
        assert parked_v1.archived is True


# ---------------------------------------------------------------------------
# Per-page workflow status
# ---------------------------------------------------------------------------

def _page(db_session, template, version, name, order):
    page = FormPage(template_id=template.id, version_id=version.id, name=name, order=order)
    db_session.add(page)
    db_session.commit()
    return page


def _put_in_page(db_session, section, page):
    section.page_id = page.id
    db_session.commit()


class TestPageStatusCarryForward:
    def test_page_workflow_status_follows_the_page(self, db_session, admin_user):
        template, published, draft = _versions(db_session, admin_user)
        pub_section, drf_section, pub_item, _drf_item = _pair(db_session, template, published, draft)
        pub_page = _page(db_session, template, published, 'Page 1', 1)
        drf_page = _page(db_session, template, draft, 'Page 1 (renamed)', 1)
        _put_in_page(db_session, pub_section, pub_page)
        _put_in_page(db_session, drf_section, drf_page)

        aes = create_test_assignment_entity_status(db_session, template=template)
        status_row = AssignmentPageStatus(
            assignment_entity_status_id=aes.id, form_page_id=pub_page.id, status='Approved'
        )
        db_session.add(status_row)
        db_session.commit()

        summary = _migrate(db_session, template, published, draft)
        db_session.refresh(status_row)
        assert status_row.form_page_id == drf_page.id
        assert status_row.status == 'Approved'
        assert summary['per_table']['assignment_page_status'] == 1
        assert summary['remapped_rows'] == 0, 'page status is reported separately from submission values'

    def test_estimate_reports_page_status_without_inflating_remappable_rows(self, db_session, admin_user):
        template, published, draft = _versions(db_session, admin_user)
        pub_section, drf_section, _pi, _di = _pair(db_session, template, published, draft)
        pub_page = _page(db_session, template, published, 'P', 1)
        drf_page = _page(db_session, template, draft, 'P', 1)
        _put_in_page(db_session, pub_section, pub_page)
        _put_in_page(db_session, drf_section, drf_page)
        aes = create_test_assignment_entity_status(db_session, template=template)
        db_session.add(AssignmentPageStatus(
            assignment_entity_status_id=aes.id, form_page_id=pub_page.id, status='Submitted'
        ))
        db_session.commit()
        estimate = Service.estimate_migration_counts(published.id, draft.id, template.id)
        assert estimate['per_table']['assignment_page_status'] == 1
        assert estimate['remappable_rows'] == 0

    def test_existing_status_on_new_page_is_never_overwritten(self, db_session, admin_user):
        template, published, draft = _versions(db_session, admin_user)
        pub_section, drf_section, _pi, _di = _pair(db_session, template, published, draft)
        pub_page = _page(db_session, template, published, 'P', 1)
        drf_page = _page(db_session, template, draft, 'P', 1)
        _put_in_page(db_session, pub_section, pub_page)
        _put_in_page(db_session, drf_section, drf_page)
        aes = create_test_assignment_entity_status(db_session, template=template)
        old_row = AssignmentPageStatus(
            assignment_entity_status_id=aes.id, form_page_id=pub_page.id, status='Approved'
        )
        existing = AssignmentPageStatus(
            assignment_entity_status_id=aes.id, form_page_id=drf_page.id, status='In progress'
        )
        db_session.add_all([old_row, existing])
        db_session.commit()

        summary = _migrate(db_session, template, published, draft)
        db_session.refresh(old_row)
        db_session.refresh(existing)
        assert old_row.form_page_id == pub_page.id
        assert existing.status == 'In progress'
        assert summary['page_status_conflicts'] == 1

    def test_split_page_maps_to_the_page_holding_most_sections(self, db_session, admin_user):
        template, published, draft = _versions(db_session, admin_user)
        pub_page = _page(db_session, template, published, 'Big', 1)
        new_page_a = _page(db_session, template, draft, 'A', 1)
        new_page_b = _page(db_session, template, draft, 'B', 2)
        sections = []
        for idx in range(3):
            pub_s, drf_s, _pi, _di = _pair(
                db_session, template, published, draft, order=idx + 1, section_name=f'S{idx}'
            )
            _put_in_page(db_session, pub_s, pub_page)
            _put_in_page(db_session, drf_s, new_page_a if idx < 2 else new_page_b)
            sections.append(drf_s)

        page_map = Service._build_page_map(
            Service._build_key_maps(published.id, draft.id, template.id)[1]
        )
        assert page_map == {pub_page.id: new_page_a.id}

    def test_two_old_pages_merged_into_one_do_not_both_claim_it(self, db_session, admin_user):
        template, published, draft = _versions(db_session, admin_user)
        old_a = _page(db_session, template, published, 'A', 1)
        old_b = _page(db_session, template, published, 'B', 2)
        merged = _page(db_session, template, draft, 'Merged', 1)
        for idx, old_page in enumerate((old_a, old_b)):
            pub_s, drf_s, _pi, _di = _pair(
                db_session, template, published, draft, order=idx + 1, section_name=f'S{idx}'
            )
            _put_in_page(db_session, pub_s, old_page)
            _put_in_page(db_session, drf_s, merged)
        page_map = Service._build_page_map(
            Service._build_key_maps(published.id, draft.id, template.id)[1]
        )
        assert list(page_map.values()) == [merged.id]
        assert len(page_map) == 1


# ---------------------------------------------------------------------------
# Template variables that read a field by id
# ---------------------------------------------------------------------------

class TestVariableReferencesFollowTheField:
    def test_other_template_variable_is_repointed(self, db_session, admin_user):
        source, published, draft = _versions(db_session, admin_user)
        _ps, _ds, pub_item, drf_item = _pair(db_session, source, published, draft)

        consumer = create_test_template(db_session, owner_id=admin_user.id)
        consumer_version = consumer.published_version
        consumer_version.variables = {
            'staff': {
                'variable_type': 'lookup',
                'source_template_id': source.id,
                'source_form_item_id': pub_item.id,
                'entity_scope': 'same',
            },
            'unrelated': {'source_form_item_id': 999999},
            'metadata_var': {'variable_type': 'metadata'},
        }
        db_session.commit()

        summary = _migrate(db_session, source, published, draft)
        db_session.refresh(consumer_version)
        assert consumer_version.variables['staff']['source_form_item_id'] == drf_item.id
        assert consumer_version.variables['unrelated']['source_form_item_id'] == 999999
        assert consumer_version.variables['metadata_var'] == {'variable_type': 'metadata'}
        assert summary['variable_references_remapped'] == 1

    def test_same_template_new_version_variable_is_repointed(self, db_session, admin_user):
        template, published, draft = _versions(db_session, admin_user)
        _ps, _ds, pub_item, drf_item = _pair(db_session, template, published, draft)
        draft.variables = {'self_ref': {'source_template_id': template.id, 'source_form_item_id': pub_item.id}}
        db_session.commit()
        _migrate(db_session, template, published, draft)
        db_session.refresh(draft)
        assert draft.variables['self_ref']['source_form_item_id'] == drf_item.id

    def test_string_ids_are_handled_and_orphans_left_alone(self, db_session, admin_user):
        source, published, draft = _versions(db_session, admin_user)
        pub_section, _ds, pub_item, drf_item = _pair(db_session, source, published, draft)
        orphan = create_test_item(
            db_session, pub_section, source, version=published, item_type='question', label='gone', order=5
        )
        consumer = create_test_template(db_session, owner_id=admin_user.id)
        consumer_version = consumer.published_version
        consumer_version.variables = {
            'as_text': {'source_form_item_id': str(pub_item.id)},
            'orphan': {'source_form_item_id': orphan.id},
        }
        db_session.commit()
        _migrate(db_session, source, published, draft)
        db_session.refresh(consumer_version)
        assert consumer_version.variables['as_text']['source_form_item_id'] == drf_item.id
        assert consumer_version.variables['orphan']['source_form_item_id'] == orphan.id


# ---------------------------------------------------------------------------
# Mapping review (read-only comparison)
# ---------------------------------------------------------------------------

class TestFieldComparison:
    def test_orphaned_published_item_reports_its_data(self, db_session, admin_user):
        template, published, draft = _versions(db_session, admin_user)
        pub_section, _ds, _pi, _di = _pair(db_session, template, published, draft)
        removed = create_test_item(
            db_session, pub_section, template, version=published, item_type='question', label='removed', order=9
        )
        aes = create_test_assignment_entity_status(db_session, template=template)
        _form_data(db_session, aes, removed)

        rows = Service.build_field_comparison(published.id, draft.id, template.id)
        orphaned = [r for r in rows if r['entity_type'] == 'item' and r['confidence'] == 'orphaned']
        assert len(orphaned) == 1
        assert orphaned[0]['data_rows'] == 1
        summary = Service.count_field_mapping_summary(published.id, draft.id, template.id)
        assert summary['orphaned_items_with_data'] == 1

    def test_new_draft_item_is_reported_as_new(self, db_session, admin_user):
        template, published, draft = _versions(db_session, admin_user)
        _ps, drf_section, _pi, _di = _pair(db_session, template, published, draft)
        create_test_item(
            db_session, drf_section, template, version=draft, item_type='question', label='new', order=8
        )
        summary = Service.count_field_mapping_summary(published.id, draft.id, template.id)
        assert summary['unlinked_items'] == 1

    def test_suggestion_is_not_offered_for_an_already_linked_published_item(self, db_session, admin_user):
        template, published, draft = _versions(db_session, admin_user)
        pub_section, drf_section, pub_item, drf_item = _pair(db_session, template, published, draft)
        # A second draft item sits at a different position, so only the exact match claims pub_item.
        rival = create_test_item(
            db_session, drf_section, template, version=draft, item_type='question', label='rival', order=1
        )
        db_session.commit()
        rows = Service.build_field_comparison(published.id, draft.id, template.id)
        by_draft_id = {r['draft_item']['id']: r for r in rows if r['entity_type'] == 'item' and r['draft_item']}
        assert by_draft_id[drf_item.id]['confidence'] == 'exact'
        assert by_draft_id[rival.id]['confidence'] == 'new'
        assert by_draft_id[rival.id]['published_item'] is None

    def test_comparison_of_a_version_with_itself_is_empty(self, db_session, admin_user):
        template, published, _draft = _versions(db_session, admin_user)
        assert Service.build_field_comparison(published.id, published.id, template.id) == []

    def test_section_rows_are_compared_too(self, db_session, admin_user):
        template, published, draft = _versions(db_session, admin_user)
        _pair(db_session, template, published, draft)
        removed = create_test_section(db_session, template, version=published, name='gone', order=6)
        added = create_test_section(db_session, template, version=draft, name='added', order=7)
        rows = Service.build_field_comparison(published.id, draft.id, template.id)
        section_rows = {
            (r['confidence']): r for r in rows if r['entity_type'] == 'section'
        }
        assert section_rows['exact']['draft_item']['name'] == 'S'
        assert section_rows['orphaned']['published_item']['id'] == removed.id
        assert section_rows['new']['draft_item']['id'] == added.id


class TestStableKeyHelpers:
    def test_choose_shared_key_prefers_published_identity(self):
        class Row:
            def __init__(self, key):
                self.stable_key = key

        assert Service._choose_shared_stable_key(Row('old'), Row('new')) == 'old'
        assert Service._choose_shared_stable_key(Row(None), Row('new')) == 'new'
        generated = Service._choose_shared_stable_key(Row(None), Row(None))
        assert generated and generated not in ('old', 'new')

    def test_orphan_counts_ignore_matched_rows(self, db_session, admin_user):
        template, published, draft = _versions(db_session, admin_user)
        pub_section, _ds, _pi, _di = _pair(db_session, template, published, draft)
        create_test_item(
            db_session, pub_section, template, version=published, item_type='question', label='gone', order=3
        )
        create_test_section(db_session, template, version=published, name='gone', order=4)
        db_session.commit()
        assert Service._count_orphan_items(published.id, draft.id, template.id) == 1
        assert Service._count_orphan_sections(published.id, draft.id, template.id) == 1
