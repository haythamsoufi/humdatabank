"""
Unit tests for organization.py models to achieve 100% code coverage.

Covers: NationalSociety, NSBranch, NSSubBranch, NSLocalUnit,
        SecretariatDivision, SecretariatRegionalOffice,
        SecretariatClusterOffice, SecretariatDepartment
"""
import pytest
from tests.factories import create_test_country


@pytest.mark.unit
class TestNationalSociety:
    """Tests for NationalSociety model."""

    def _create_ns(self, db_session, country, **kwargs):
        from app.models.organization import NationalSociety
        import uuid
        defaults = {
            'name': f'National Society {uuid.uuid4().hex[:6]}',
            'country_id': country.id,
        }
        defaults.update(kwargs)
        ns = NationalSociety(**defaults)
        db_session.add(ns)
        db_session.commit()
        db_session.refresh(ns)
        return ns

    def test_create_ns(self, db_session, app):
        """Test creating a national society."""
        with app.app_context():
            country = create_test_country(db_session)
            ns = self._create_ns(db_session, country, name='Kenya Red Cross')
            assert ns.id is not None
            assert ns.name == 'Kenya Red Cross'
            assert ns.country_id == country.id

    def test_repr_with_country(self, db_session, app):
        """Test __repr__ includes country name."""
        with app.app_context():
            country = create_test_country(db_session)
            ns = self._create_ns(db_session, country, name='Test NS')
            result = repr(ns)
            assert 'Test NS' in result

    def test_normalize_code_strips_whitespace(self, db_session, app):
        """Test _normalize_code removes surrounding whitespace."""
        with app.app_context():
            country = create_test_country(db_session)
            ns = self._create_ns(db_session, country, code='  KRC  ')
            assert ns.code == 'KRC'

    def test_normalize_code_none(self, db_session, app):
        """Test _normalize_code returns None for None input."""
        with app.app_context():
            country = create_test_country(db_session)
            ns = self._create_ns(db_session, country, code=None)
            assert ns.code is None

    def test_normalize_code_whitespace_only(self, db_session, app):
        """Test _normalize_code returns None for whitespace-only code."""
        with app.app_context():
            country = create_test_country(db_session)
            ns = self._create_ns(db_session, country, code='   ')
            assert ns.code is None

    def test_get_name_translation(self, db_session, app):
        """Test get_name_translation."""
        with app.app_context():
            country = create_test_country(db_session)
            ns = self._create_ns(db_session, country, name='Test NS', name_translations={'fr': 'Société Test'})
            assert ns.get_name_translation('fr') == 'Société Test'
            assert ns.get_name_translation('de') == 'Test NS'

    def test_get_name_translation_no_translations(self, db_session, app):
        """Test get_name_translation fallback."""
        with app.app_context():
            country = create_test_country(db_session)
            ns = self._create_ns(db_session, country, name='Test NS', name_translations=None)
            assert ns.get_name_translation('fr') == 'Test NS'

    def test_set_name_translation(self, db_session, app):
        """Test set_name_translation."""
        with app.app_context():
            country = create_test_country(db_session)
            ns = self._create_ns(db_session, country)
            ns.set_name_translation('fr', 'Société Test')
            assert ns.name_translations['fr'] == 'Société Test'

    def test_set_name_translation_init(self, db_session, app):
        """Test initializes dict when None."""
        with app.app_context():
            country = create_test_country(db_session)
            ns = self._create_ns(db_session, country, name_translations=None)
            ns.set_name_translation('fr', 'Société Test')
            assert isinstance(ns.name_translations, dict)

    def test_set_name_translation_empty_removes(self, db_session, app):
        """Test empty text removes key."""
        with app.app_context():
            country = create_test_country(db_session)
            ns = self._create_ns(db_session, country, name_translations={'fr': 'Société Test'})
            ns.set_name_translation('fr', '')
            assert 'fr' not in ns.name_translations

    def test_has_logo(self, db_session, app):
        with app.app_context():
            country = create_test_country(db_session)
            ns = self._create_ns(db_session, country)
            assert ns.has_logo is False
            ns.logo_filename = "BGD.png"
            assert ns.has_logo is True


@pytest.mark.unit
class TestNSBranch:
    """Tests for NSBranch model."""

    def _create_branch(self, db_session, country, **kwargs):
        from app.models.organization import NSBranch
        import uuid
        defaults = {
            'name': f'NS Branch {uuid.uuid4().hex[:6]}',
            'country_id': country.id,
        }
        defaults.update(kwargs)
        b = NSBranch(**defaults)
        db_session.add(b)
        db_session.commit()
        db_session.refresh(b)
        return b

    def test_create_branch(self, db_session, app):
        """Test creating an NS branch."""
        with app.app_context():
            country = create_test_country(db_session)
            branch = self._create_branch(db_session, country, name='Nairobi Branch')
            assert branch.id is not None
            assert branch.name == 'Nairobi Branch'

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            country = create_test_country(db_session)
            branch = self._create_branch(db_session, country, name='Nairobi Branch')
            result = repr(branch)
            assert 'Nairobi Branch' in result

    def test_normalize_code(self, db_session, app):
        """Test _normalize_code strips whitespace."""
        with app.app_context():
            country = create_test_country(db_session)
            branch = self._create_branch(db_session, country, code='  NRB  ')
            assert branch.code == 'NRB'

    def test_normalize_code_none(self, db_session, app):
        """Test _normalize_code returns None for None."""
        with app.app_context():
            country = create_test_country(db_session)
            branch = self._create_branch(db_session, country, code=None)
            assert branch.code is None

    def test_normalize_code_whitespace_only(self, db_session, app):
        """Test _normalize_code returns None for whitespace only."""
        with app.app_context():
            country = create_test_country(db_session)
            branch = self._create_branch(db_session, country, code='  ')
            assert branch.code is None

    def test_timestamps_set(self, db_session, app):
        """Test created_at/updated_at set on init."""
        with app.app_context():
            country = create_test_country(db_session)
            branch = self._create_branch(db_session, country)
            assert branch.created_at is not None
            assert branch.updated_at is not None

    def test_optional_fields(self, db_session, app):
        """Test optional contact/geo fields."""
        with app.app_context():
            country = create_test_country(db_session)
            branch = self._create_branch(
                db_session, country,
                address='123 Main St',
                city='Nairobi',
                postal_code='00100',
                phone='+254700000000',
                email='branch@example.com',
                website='https://example.com',
            )
            assert branch.city == 'Nairobi'
            assert branch.email == 'branch@example.com'


@pytest.mark.unit
class TestNSSubBranch:
    """Tests for NSSubBranch model."""

    def _create_subbranch(self, db_session, branch, **kwargs):
        from app.models.organization import NSSubBranch
        import uuid
        defaults = {
            'name': f'SubBranch {uuid.uuid4().hex[:6]}',
            'branch_id': branch.id,
        }
        defaults.update(kwargs)
        sb = NSSubBranch(**defaults)
        db_session.add(sb)
        db_session.commit()
        db_session.refresh(sb)
        return sb

    def _create_branch(self, db_session, country):
        from app.models.organization import NSBranch
        import uuid
        b = NSBranch(name=f'Branch {uuid.uuid4().hex[:6]}', country_id=country.id)
        db_session.add(b)
        db_session.commit()
        return b

    def test_create_subbranch(self, db_session, app):
        """Test creating an NS sub-branch."""
        with app.app_context():
            country = create_test_country(db_session)
            branch = self._create_branch(db_session, country)
            sb = self._create_subbranch(db_session, branch, name='West Nairobi')
            assert sb.id is not None
            assert sb.name == 'West Nairobi'

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            country = create_test_country(db_session)
            branch = self._create_branch(db_session, country)
            sb = self._create_subbranch(db_session, branch, name='West SubBranch')
            result = repr(sb)
            assert 'West SubBranch' in result

    def test_timestamps_set(self, db_session, app):
        """Test timestamps set on init."""
        with app.app_context():
            country = create_test_country(db_session)
            branch = self._create_branch(db_session, country)
            sb = self._create_subbranch(db_session, branch)
            assert sb.created_at is not None


@pytest.mark.unit
class TestNSLocalUnit:
    """Tests for NSLocalUnit model."""

    def _create_branch(self, db_session, country):
        from app.models.organization import NSBranch
        import uuid
        b = NSBranch(name=f'Branch {uuid.uuid4().hex[:6]}', country_id=country.id)
        db_session.add(b)
        db_session.commit()
        return b

    def _create_subbranch(self, db_session, branch):
        from app.models.organization import NSSubBranch
        import uuid
        sb = NSSubBranch(name=f'SubBranch {uuid.uuid4().hex[:6]}', branch_id=branch.id)
        db_session.add(sb)
        db_session.commit()
        return sb

    def _create_local_unit(self, db_session, branch, **kwargs):
        from app.models.organization import NSLocalUnit
        import uuid
        defaults = {
            'name': f'Local Unit {uuid.uuid4().hex[:6]}',
            'branch_id': branch.id,
        }
        defaults.update(kwargs)
        lu = NSLocalUnit(**defaults)
        db_session.add(lu)
        db_session.commit()
        db_session.refresh(lu)
        return lu

    def test_create_local_unit(self, db_session, app):
        """Test creating an NS local unit."""
        with app.app_context():
            country = create_test_country(db_session)
            branch = self._create_branch(db_session, country)
            lu = self._create_local_unit(db_session, branch)
            assert lu.id is not None

    def test_repr_with_subbranch(self, db_session, app):
        """Test __repr__ with subbranch."""
        with app.app_context():
            country = create_test_country(db_session)
            branch = self._create_branch(db_session, country)
            sb = self._create_subbranch(db_session, branch)
            lu = self._create_local_unit(db_session, branch, name='My Local Unit', subbranch_id=sb.id)
            db_session.refresh(lu)
            result = repr(lu)
            assert 'My Local Unit' in result

    def test_repr_without_subbranch(self, db_session, app):
        """Test __repr__ without subbranch."""
        with app.app_context():
            country = create_test_country(db_session)
            branch = self._create_branch(db_session, country)
            lu = self._create_local_unit(db_session, branch, name='Direct Unit')
            db_session.refresh(lu)
            result = repr(lu)
            assert 'Direct Unit' in result

    def test_parent_entity_via_subbranch(self, db_session, app):
        """Test parent_entity returns subbranch when subbranch_id set."""
        with app.app_context():
            country = create_test_country(db_session)
            branch = self._create_branch(db_session, country)
            sb = self._create_subbranch(db_session, branch)
            lu = self._create_local_unit(db_session, branch, subbranch_id=sb.id)
            db_session.refresh(lu)
            parent = lu.parent_entity
            assert parent is not None
            assert parent.id == sb.id

    def test_parent_entity_via_branch(self, db_session, app):
        """Test parent_entity returns branch when no subbranch_id."""
        with app.app_context():
            country = create_test_country(db_session)
            branch = self._create_branch(db_session, country)
            lu = self._create_local_unit(db_session, branch)
            db_session.refresh(lu)
            parent = lu.parent_entity
            assert parent.id == branch.id

    def test_hierarchy_path_with_subbranch(self, db_session, app):
        """Test hierarchy_path with full chain."""
        with app.app_context():
            country = create_test_country(db_session)
            branch = self._create_branch(db_session, country)
            sb = self._create_subbranch(db_session, branch)
            lu = self._create_local_unit(db_session, branch, name='Community Unit', subbranch_id=sb.id)
            db_session.refresh(lu)
            path = lu.hierarchy_path
            assert ' > ' in path
            assert 'Community Unit' in path

    def test_hierarchy_path_without_subbranch(self, db_session, app):
        """Test hierarchy_path without subbranch."""
        with app.app_context():
            country = create_test_country(db_session)
            branch = self._create_branch(db_session, country)
            lu = self._create_local_unit(db_session, branch, name='Direct Community Unit')
            db_session.refresh(lu)
            path = lu.hierarchy_path
            assert 'Direct Community Unit' in path

    def test_country_property(self, db_session, app):
        """Test country property returns country via branch."""
        with app.app_context():
            country = create_test_country(db_session)
            branch = self._create_branch(db_session, country)
            lu = self._create_local_unit(db_session, branch)
            db_session.refresh(lu)
            assert lu.country.id == country.id

    def test_timestamps_set(self, db_session, app):
        """Test timestamps set on init."""
        with app.app_context():
            country = create_test_country(db_session)
            branch = self._create_branch(db_session, country)
            lu = self._create_local_unit(db_session, branch)
            assert lu.created_at is not None


@pytest.mark.unit
class TestSecretariatDivision:
    """Tests for SecretariatDivision model."""

    def _create_division(self, db_session, **kwargs):
        from app.models.organization import SecretariatDivision
        import uuid
        defaults = {'name': f'Division {uuid.uuid4().hex[:6]}'}
        defaults.update(kwargs)
        d = SecretariatDivision(**defaults)
        db_session.add(d)
        db_session.commit()
        db_session.refresh(d)
        return d

    def test_create_division(self, db_session, app):
        """Test creating a secretariat division."""
        with app.app_context():
            d = self._create_division(db_session, name='Operations Division')
            assert d.id is not None
            assert d.name == 'Operations Division'

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            d = self._create_division(db_session, name='My Division')
            assert 'My Division' in repr(d)

    def test_normalize_code(self, db_session, app):
        """Test _normalize_code strips whitespace."""
        with app.app_context():
            d = self._create_division(db_session, code='  OPS  ')
            assert d.code == 'OPS'

    def test_normalize_code_none(self, db_session, app):
        """Test _normalize_code returns None for None."""
        with app.app_context():
            d = self._create_division(db_session, code=None)
            assert d.code is None

    def test_normalize_code_whitespace_only(self, db_session, app):
        """Test _normalize_code returns None for whitespace only."""
        with app.app_context():
            d = self._create_division(db_session, code='   ')
            assert d.code is None

    def test_timestamps_set(self, db_session, app):
        """Test timestamps set on init."""
        with app.app_context():
            d = self._create_division(db_session)
            assert d.created_at is not None
            assert d.updated_at is not None


@pytest.mark.unit
class TestSecretariatRegionalOffice:
    """Tests for SecretariatRegionalOffice model."""

    def _create_ro(self, db_session, **kwargs):
        from app.models.organization import SecretariatRegionalOffice
        import uuid
        defaults = {'name': f'Regional Office {uuid.uuid4().hex[:6]}'}
        defaults.update(kwargs)
        ro = SecretariatRegionalOffice(**defaults)
        db_session.add(ro)
        db_session.commit()
        db_session.refresh(ro)
        return ro

    def test_create_regional_office(self, db_session, app):
        """Test creating a regional office."""
        with app.app_context():
            ro = self._create_ro(db_session, name='Africa Regional Office')
            assert ro.id is not None
            assert ro.name == 'Africa Regional Office'

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            ro = self._create_ro(db_session, name='Africa RO')
            assert 'Africa RO' in repr(ro)

    def test_normalize_code(self, db_session, app):
        """Test _normalize_code strips whitespace."""
        with app.app_context():
            ro = self._create_ro(db_session, code='  ARO  ')
            assert ro.code == 'ARO'

    def test_normalize_code_none(self, db_session, app):
        """Test _normalize_code returns None for None."""
        with app.app_context():
            ro = self._create_ro(db_session, code=None)
            assert ro.code is None

    def test_normalize_code_whitespace_only(self, db_session, app):
        """Test _normalize_code returns None for whitespace only."""
        with app.app_context():
            ro = self._create_ro(db_session, code='  ')
            assert ro.code is None

    def test_short_name_and_translations(self, db_session, app):
        """Test short_name fields and translation helpers."""
        with app.app_context():
            ro = self._create_ro(
                db_session,
                name='Europe and Central Asia',
                short_name='Europe & CA',
                short_name_translations={'en': 'Europe & CA', 'fr': 'Europe & CA'},
            )
            assert ro.short_name == 'Europe & CA'
            assert ro.get_short_name_translation('en') == 'Europe & CA'
            assert ro.get_short_name_translation('fr') == 'Europe & CA'
            assert ro.get_short_name_translation('de') == 'Europe & CA'


@pytest.mark.unit
class TestSecretariatClusterOffice:
    """Tests for SecretariatClusterOffice model."""

    def _create_ro(self, db_session):
        from app.models.organization import SecretariatRegionalOffice
        import uuid
        ro = SecretariatRegionalOffice(name=f'RO {uuid.uuid4().hex[:6]}')
        db_session.add(ro)
        db_session.commit()
        return ro

    def _create_cluster_office(self, db_session, ro, **kwargs):
        from app.models.organization import SecretariatClusterOffice
        import uuid
        defaults = {
            'name': f'Cluster Office {uuid.uuid4().hex[:6]}',
            'regional_office_id': ro.id,
        }
        defaults.update(kwargs)
        co = SecretariatClusterOffice(**defaults)
        db_session.add(co)
        db_session.commit()
        db_session.refresh(co)
        return co

    def test_create_cluster_office(self, db_session, app):
        """Test creating a cluster office."""
        with app.app_context():
            ro = self._create_ro(db_session)
            co = self._create_cluster_office(db_session, ro, name='East Africa Cluster')
            assert co.id is not None
            assert co.name == 'East Africa Cluster'

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            ro = self._create_ro(db_session)
            co = self._create_cluster_office(db_session, ro, name='Test Cluster')
            result = repr(co)
            assert 'Test Cluster' in result
            assert str(ro.id) in result

    def test_normalize_code(self, db_session, app):
        """Test _normalize_code strips whitespace."""
        with app.app_context():
            ro = self._create_ro(db_session)
            co = self._create_cluster_office(db_session, ro, code='  EAC  ')
            assert co.code == 'EAC'

    def test_normalize_code_none(self, db_session, app):
        """Test _normalize_code returns None for None."""
        with app.app_context():
            ro = self._create_ro(db_session)
            co = self._create_cluster_office(db_session, ro, code=None)
            assert co.code is None

    def test_normalize_code_whitespace_only(self, db_session, app):
        """Test _normalize_code returns None for whitespace only."""
        with app.app_context():
            ro = self._create_ro(db_session)
            co = self._create_cluster_office(db_session, ro, code='  ')
            assert co.code is None


@pytest.mark.unit
class TestSecretariatDepartment:
    """Tests for SecretariatDepartment model."""

    def _create_division(self, db_session):
        from app.models.organization import SecretariatDivision
        import uuid
        d = SecretariatDivision(name=f'Div {uuid.uuid4().hex[:6]}')
        db_session.add(d)
        db_session.commit()
        return d

    def _create_department(self, db_session, division, **kwargs):
        from app.models.organization import SecretariatDepartment
        import uuid
        defaults = {
            'name': f'Department {uuid.uuid4().hex[:6]}',
            'division_id': division.id,
        }
        defaults.update(kwargs)
        dept = SecretariatDepartment(**defaults)
        db_session.add(dept)
        db_session.commit()
        db_session.refresh(dept)
        return dept

    def test_create_department(self, db_session, app):
        """Test creating a secretariat department."""
        with app.app_context():
            division = self._create_division(db_session)
            dept = self._create_department(db_session, division, name='Finance Dept')
            assert dept.id is not None
            assert dept.name == 'Finance Dept'

    def test_repr(self, db_session, app):
        """Test __repr__."""
        with app.app_context():
            division = self._create_division(db_session)
            dept = self._create_department(db_session, division, name='Test Dept')
            result = repr(dept)
            assert 'Test Dept' in result

    def test_timestamps_set(self, db_session, app):
        """Test timestamps set on init."""
        with app.app_context():
            division = self._create_division(db_session)
            dept = self._create_department(db_session, division)
            assert dept.created_at is not None
            assert dept.updated_at is not None
