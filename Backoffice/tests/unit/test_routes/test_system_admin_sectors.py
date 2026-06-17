"""
Tests for app/routes/admin/system_admin/sectors.py
Targeting 100% code coverage of sector, subsector and NS hierarchy routes.
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from app.models import Sector, SubSector
from tests.factories import create_test_country

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_render(return_value="<html>ok</html>"):
    return patch(
        "app.routes.admin.system_admin.sectors.render_template",
        return_value=return_value,
    )


def _create_sector(db_session, name="Test Sector"):
    existing = Sector.query.filter_by(name=name).first()
    if existing:
        return existing
    sector = Sector(name=name, is_active=True)
    db_session.add(sector)
    db_session.commit()
    db_session.refresh(sector)
    return sector


def _create_subsector(db_session, sector_id, name="Test SubSector"):
    existing = SubSector.query.filter_by(name=name, sector_id=sector_id).first()
    if existing:
        return existing
    subsector = SubSector(name=name, sector_id=sector_id, is_active=True)
    db_session.add(subsector)
    db_session.commit()
    db_session.refresh(subsector)
    return subsector


# ---------------------------------------------------------------------------
# GET /admin/sectors_subsectors  – manage sectors & subsectors
# ---------------------------------------------------------------------------

class TestManageSectorsSubsectors:
    def test_get_renders_page(self, logged_in_client, db_session):
        with _mock_render() as mock_rt:
            resp = logged_in_client.get("/admin/sectors_subsectors")
        assert resp.status_code == 200
        mock_rt.assert_called_once()

    def test_unauthenticated_redirects(self, client, db_session):
        resp = client.get("/admin/sectors_subsectors", follow_redirects=False)
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# POST /admin/sectors/new  – create sector
# ---------------------------------------------------------------------------

class TestNewSector:
    def test_post_creates_sector(self, logged_in_client, db_session, app):
        resp = logged_in_client.post(
            "/admin/sectors/new",
            data={"name": "New Test Sector"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        with app.app_context():
            sector = Sector.query.filter_by(name="New Test Sector").first()
            assert sector is not None

    def test_post_invalid_name_flashes_errors(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/sectors/new",
            data={"name": ""},  # Empty name fails DataRequired
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_post_exception_flashes_error(self, logged_in_client, db_session):
        with patch(
            "app.routes.admin.system_admin.sectors.Sector",
            side_effect=Exception("db error"),
        ):
            resp = logged_in_client.post(
                "/admin/sectors/new",
                data={"name": "Exception Sector"},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_post_with_logo_file(self, logged_in_client, db_session, app):
        import io
        with patch(
            "app.routes.admin.system_admin.sectors._save_logo_file",
            return_value="saved_logo.png",
        ):
            logo_data = io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
            resp = logged_in_client.post(
                "/admin/sectors/new",
                data={
                    "name": "Logo Sector",
                    "logo_file": (logo_data, "logo.png"),
                },
                content_type="multipart/form-data",
                follow_redirects=False,
            )
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# POST /admin/sectors/edit/<id>  – edit sector (form or JSON)
# ---------------------------------------------------------------------------

class TestEditSector:
    def test_post_form_updates_sector(self, logged_in_client, db_session, app):
        with app.app_context():
            sector = _create_sector(db_session, "Edit Form Sector")
        resp = logged_in_client.post(
            f"/admin/sectors/edit/{sector.id}",
            data={"name": "Updated Sector Name"},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_post_json_updates_translations(self, logged_in_client, db_session, app):
        with app.app_context():
            sector = _create_sector(db_session, "JSON Trans Sector")
        resp = logged_in_client.post(
            f"/admin/sectors/edit/{sector.id}",
            data=json.dumps({"name_fr": "Secteur en français"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True

    def test_post_json_no_valid_fields_returns_400(self, logged_in_client, db_session, app):
        with app.app_context():
            sector = _create_sector(db_session, "JSON No Fields Sector")
        resp = logged_in_client.post(
            f"/admin/sectors/edit/{sector.id}",
            data=json.dumps({"other_field": "value"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_post_json_empty_body_returns_error(self, logged_in_client, db_session, app):
        with app.app_context():
            sector = _create_sector(db_session, "JSON Empty Body Sector")
        resp = logged_in_client.post(
            f"/admin/sectors/edit/{sector.id}",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_post_json_exception_returns_server_error(self, logged_in_client, db_session, app):
        with app.app_context():
            sector = _create_sector(db_session, "JSON Exception Sector")
        with patch(
            "app.routes.admin.system_admin.sectors.db"
        ) as mock_db:
            mock_db.session.flush.side_effect = Exception("db error")
            mock_db.session.add = MagicMock()
            resp = logged_in_client.post(
                f"/admin/sectors/edit/{sector.id}",
                data=json.dumps({"name_fr": "Test"}),
                content_type="application/json",
            )
        assert resp.status_code == 500

    def test_post_form_invalid_flashes_errors(self, logged_in_client, db_session, app):
        with app.app_context():
            sector = _create_sector(db_session, "Form Invalid Sector")
        resp = logged_in_client.post(
            f"/admin/sectors/edit/{sector.id}",
            data={"name": ""},  # Empty name fails
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_post_form_exception_flashes_error(self, logged_in_client, db_session, app):
        with app.app_context():
            sector = _create_sector(db_session, "Form Exception Sector")
        with patch(
            "app.routes.admin.system_admin.sectors.db"
        ) as mock_db:
            mock_db.session.flush.side_effect = Exception("db error")
            resp = logged_in_client.post(
                f"/admin/sectors/edit/{sector.id}",
                data={"name": "Valid Name"},
                follow_redirects=False,
            )
        assert resp.status_code == 302

    def test_404_for_missing_sector(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/sectors/edit/9999999",
            data={"name": "X"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /admin/sectors/<id>  – get sector data (JSON)
# ---------------------------------------------------------------------------

class TestGetSector:
    def test_returns_sector_json(self, logged_in_client, db_session, app):
        with app.app_context():
            sector = _create_sector(db_session, "Get JSON Sector")
        resp = logged_in_client.get(f"/admin/sectors/{sector.id}")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True
        assert data.get("id") == sector.id

    def test_404_for_missing(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/sectors/9999999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /admin/sectors/delete/<id>  – delete sector
# ---------------------------------------------------------------------------

class TestDeleteSector:
    def test_delete_sector_without_subsectors(self, logged_in_client, db_session, app):
        with app.app_context():
            sector = _create_sector(db_session, "Delete Me Sector")
        resp = logged_in_client.post(
            f"/admin/sectors/delete/{sector.id}",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        with app.app_context():
            assert Sector.query.get(sector.id) is None

    def test_delete_sector_with_subsectors_shows_error(self, logged_in_client, db_session, app):
        with app.app_context():
            sector = _create_sector(db_session, "Has SubSectors Sector")
            _create_subsector(db_session, sector.id, "Child SubSector")

        resp = logged_in_client.post(
            f"/admin/sectors/delete/{sector.id}",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        with app.app_context():
            # Should still exist
            assert Sector.query.get(sector.id) is not None

    def test_delete_exception_flashes_error(self, logged_in_client, db_session, app):
        with app.app_context():
            sector = _create_sector(db_session, "Delete Exception Sector")

        with patch("app.routes.admin.system_admin.sectors.Sector") as mock_class:
            mock_sector = MagicMock()
            mock_sector.id = sector.id
            mock_sector.name = sector.name
            mock_sector.sub_sectors = []
            mock_sector.logo_filename = None
            mock_class.query.get_or_404.return_value = mock_sector
            with patch("app.routes.admin.system_admin.sectors.db") as mock_db:
                mock_db.session.delete.side_effect = Exception("db error")
                resp = logged_in_client.post(
                    f"/admin/sectors/delete/{sector.id}",
                    follow_redirects=False,
                )
        assert resp.status_code == 302

    def test_delete_sector_with_logo(self, logged_in_client, db_session, app):
        with app.app_context():
            sector = _create_sector(db_session, "Logo Delete Sector")
            sector.logo_filename = "logo.png"
            db_session.commit()

        with patch(
            "app.routes.admin.system_admin.sectors._delete_logo_file"
        ) as mock_delete:
            resp = logged_in_client.post(
                f"/admin/sectors/delete/{sector.id}",
                follow_redirects=False,
            )
        assert resp.status_code == 302
        mock_delete.assert_called_once()

    def test_404_for_missing(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/sectors/delete/9999999",
            follow_redirects=False,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /admin/subsectors/new  – create subsector
# ---------------------------------------------------------------------------

class TestNewSubSector:
    def test_post_creates_subsector(self, logged_in_client, db_session, app):
        with app.app_context():
            sector = _create_sector(db_session, "Parent Sector New Sub")
        resp = logged_in_client.post(
            "/admin/subsectors/new",
            data={
                "name": "New SubSector",
                "sector_id": str(sector.id),
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        with app.app_context():
            sub = SubSector.query.filter_by(name="New SubSector").first()
            assert sub is not None

    def test_post_invalid_flashes_errors(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/subsectors/new",
            data={"name": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_post_exception_flashes_error(self, logged_in_client, db_session, app):
        with app.app_context():
            sector = _create_sector(db_session, "Parent Sector Exc Sub")
        with patch(
            "app.routes.admin.system_admin.sectors.SubSector",
            side_effect=Exception("db error"),
        ):
            resp = logged_in_client.post(
                "/admin/subsectors/new",
                data={"name": "Exception SubSector", "sector_id": str(sector.id)},
                follow_redirects=False,
            )
        assert resp.status_code == 302


# ---------------------------------------------------------------------------
# POST /admin/subsectors/edit/<id>  – edit subsector
# ---------------------------------------------------------------------------

class TestEditSubSector:
    def test_post_form_updates_subsector(self, logged_in_client, db_session, app):
        with app.app_context():
            sector = _create_sector(db_session, "Parent Sector Edit")
            subsector = _create_subsector(db_session, sector.id, "Edit SubSector")
        resp = logged_in_client.post(
            f"/admin/subsectors/edit/{subsector.id}",
            data={"name": "Updated SubSector", "sector_id": str(sector.id)},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_post_json_updates_translations(self, logged_in_client, db_session, app):
        with app.app_context():
            sector = _create_sector(db_session, "Parent Sector JSON Edit")
            subsector = _create_subsector(db_session, sector.id, "JSON Edit SubSector")
        resp = logged_in_client.post(
            f"/admin/subsectors/edit/{subsector.id}",
            data=json.dumps({"name_fr": "Sous-secteur en français"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True

    def test_post_json_no_valid_fields_returns_400(self, logged_in_client, db_session, app):
        with app.app_context():
            sector = _create_sector(db_session, "Parent Sector No Fields")
            subsector = _create_subsector(db_session, sector.id, "No Fields SubSector")
        resp = logged_in_client.post(
            f"/admin/subsectors/edit/{subsector.id}",
            data=json.dumps({"other": "x"}),
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_post_json_exception_returns_500(self, logged_in_client, db_session, app):
        with app.app_context():
            sector = _create_sector(db_session, "Parent Sector JSON Exc")
            subsector = _create_subsector(db_session, sector.id, "JSON Exc SubSector")
        with patch("app.routes.admin.system_admin.sectors.db") as mock_db:
            mock_db.session.flush.side_effect = Exception("db error")
            mock_db.session.add = MagicMock()
            resp = logged_in_client.post(
                f"/admin/subsectors/edit/{subsector.id}",
                data=json.dumps({"name_fr": "Test"}),
                content_type="application/json",
            )
        assert resp.status_code == 500

    def test_post_form_invalid_flashes_errors(self, logged_in_client, db_session, app):
        with app.app_context():
            sector = _create_sector(db_session, "Parent Sector Form Invalid")
            subsector = _create_subsector(db_session, sector.id, "Form Invalid SubSector")
        resp = logged_in_client.post(
            f"/admin/subsectors/edit/{subsector.id}",
            data={"name": ""},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_404_for_missing_subsector(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/subsectors/edit/9999999",
            data={"name": "X"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /admin/subsectors/<id>  – get subsector data (JSON)
# ---------------------------------------------------------------------------

class TestGetSubSector:
    def test_returns_subsector_json(self, logged_in_client, db_session, app):
        with app.app_context():
            sector = _create_sector(db_session, "Get SubSector Parent")
            subsector = _create_subsector(db_session, sector.id, "Get JSON SubSector")
        resp = logged_in_client.get(f"/admin/subsectors/{subsector.id}")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data.get("success") is True
        assert data.get("id") == subsector.id

    def test_404_for_missing(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/subsectors/9999999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /admin/subsectors/delete/<id>  – delete subsector
# ---------------------------------------------------------------------------

class TestDeleteSubSector:
    def test_delete_subsector_success(self, logged_in_client, db_session, app):
        with app.app_context():
            sector = _create_sector(db_session, "Delete SubSector Parent")
            subsector = _create_subsector(db_session, sector.id, "Delete Me SubSector")
        resp = logged_in_client.post(
            f"/admin/subsectors/delete/{subsector.id}",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        with app.app_context():
            assert SubSector.query.get(subsector.id) is None

    def test_delete_subsector_with_logo(self, logged_in_client, db_session, app):
        with app.app_context():
            sector = _create_sector(db_session, "Delete SubSector Logo Parent")
            subsector = _create_subsector(db_session, sector.id, "Logo Delete SubSector")
            subsector.logo_filename = "sublogo.png"
            db_session.commit()

        with patch(
            "app.routes.admin.system_admin.sectors._delete_logo_file"
        ) as mock_delete:
            resp = logged_in_client.post(
                f"/admin/subsectors/delete/{subsector.id}",
                follow_redirects=False,
            )
        assert resp.status_code == 302
        mock_delete.assert_called_once()

    def test_delete_exception_flashes_error(self, logged_in_client, db_session, app):
        with app.app_context():
            sector = _create_sector(db_session, "Exception Delete Sub Parent")
            subsector = _create_subsector(db_session, sector.id, "Exception Delete SubSector")

        with patch("app.routes.admin.system_admin.sectors.SubSector") as mock_class:
            mock_sub = MagicMock()
            mock_sub.id = subsector.id
            mock_sub.name = subsector.name
            mock_sub.logo_filename = None
            mock_class.query.get_or_404.return_value = mock_sub
            with patch("app.routes.admin.system_admin.sectors.db") as mock_db:
                mock_db.session.delete.side_effect = Exception("db error")
                resp = logged_in_client.post(
                    f"/admin/subsectors/delete/{subsector.id}",
                    follow_redirects=False,
                )
        assert resp.status_code == 302

    def test_404_for_missing(self, logged_in_client, db_session):
        resp = logged_in_client.post(
            "/admin/subsectors/delete/9999999",
            follow_redirects=False,
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /admin/sectors/<id>/logo  – serve sector logo (public)
# ---------------------------------------------------------------------------

class TestSectorLogo:
    def test_sector_no_logo_returns_404(self, logged_in_client, db_session, app):
        with app.app_context():
            sector = _create_sector(db_session, "No Logo Sector")
            sector.logo_filename = None
            db_session.commit()

        resp = logged_in_client.get(f"/admin/sectors/{sector.id}/logo")
        assert resp.status_code == 404

    def test_sector_with_logo_streams(self, logged_in_client, db_session, app):
        with app.app_context():
            sector = _create_sector(db_session, "Has Logo Sector")
            sector.logo_filename = "logo.png"
            db_session.commit()

        with patch(
            "app.routes.admin.system_admin.sectors.storage"
        ) as mock_storage:
            mock_storage.stream_response.return_value = MagicMock(status_code=200)
            mock_storage.SYSTEM = "system"
            resp = logged_in_client.get(f"/admin/sectors/{sector.id}/logo")
        mock_storage.stream_response.assert_called_once()


# ---------------------------------------------------------------------------
# GET /admin/subsectors/<id>/logo  – serve subsector logo (public)
# ---------------------------------------------------------------------------

class TestSubSectorLogo:
    def test_subsector_no_logo_returns_404(self, logged_in_client, db_session, app):
        with app.app_context():
            sector = _create_sector(db_session, "No Logo Parent")
            subsector = _create_subsector(db_session, sector.id, "No Logo SubSector")
            subsector.logo_filename = None
            db_session.commit()

        resp = logged_in_client.get(f"/admin/subsectors/{subsector.id}/logo")
        assert resp.status_code == 404

    def test_subsector_with_logo_streams(self, logged_in_client, db_session, app):
        with app.app_context():
            sector = _create_sector(db_session, "Has Logo Parent")
            subsector = _create_subsector(db_session, sector.id, "Has Logo SubSector")
            subsector.logo_filename = "sublogo.png"
            db_session.commit()

        with patch(
            "app.routes.admin.system_admin.sectors.storage"
        ) as mock_storage:
            mock_storage.stream_response.return_value = MagicMock(status_code=200)
            mock_storage.SYSTEM = "system"
            resp = logged_in_client.get(f"/admin/subsectors/{subsector.id}/logo")
        mock_storage.stream_response.assert_called_once()


# ---------------------------------------------------------------------------
# NS Hierarchy Routes  – branches, subbranches, local units
# ---------------------------------------------------------------------------

class TestNSBranchRoutes:
    def test_get_new_branch_renders_form(self, logged_in_client, db_session):
        with _mock_render() as mock_rt:
            resp = logged_in_client.get("/admin/ns_hierarchy/branch/new")
        assert resp.status_code == 200
        mock_rt.assert_called()

    def test_post_new_branch_with_valid_data(self, logged_in_client, db_session, app):
        from app.models import NSBranch
        with app.app_context():
            country = create_test_country(db_session, name="NS Branch Country", iso3="NBC")

        resp = logged_in_client.post(
            "/admin/ns_hierarchy/branch/new",
            data={
                "name": "Test Branch",
                "country_id": str(country.id),
                "is_active": "y",
                "display_order": "0",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_post_new_branch_exception_flashes_error(self, logged_in_client, db_session, app):
        with app.app_context():
            country = create_test_country(db_session, name="NS Branch Exc Country", iso3="NEC")
        with patch(
            "app.routes.admin.system_admin.sectors.db"
        ) as mock_db:
            mock_db.session.flush.side_effect = Exception("db error")
            mock_db.session.add = MagicMock()
            resp = logged_in_client.post(
                "/admin/ns_hierarchy/branch/new",
                data={
                    "name": "Error Branch",
                    "country_id": str(country.id),
                    "is_active": "y",
                },
                follow_redirects=False,
            )
        assert resp.status_code in (200, 302)

    def test_get_edit_branch_renders_form(self, logged_in_client, db_session, app):
        from app.models import NSBranch
        with app.app_context():
            country = create_test_country(db_session, name="Edit Branch Country", iso3="EBC")
            branch = NSBranch(
                name="Edit Test Branch",
                country_id=country.id,
                is_active=True,
            )
            db_session.add(branch)
            db_session.commit()
            db_session.refresh(branch)

        with _mock_render() as mock_rt:
            resp = logged_in_client.get(f"/admin/ns_hierarchy/branch/edit/{branch.id}")
        assert resp.status_code == 200
        mock_rt.assert_called()

    def test_post_edit_branch_updates(self, logged_in_client, db_session, app):
        from app.models import NSBranch
        with app.app_context():
            country = create_test_country(db_session, name="Post Edit Branch Country", iso3="PEB")
            branch = NSBranch(
                name="Post Edit Branch",
                country_id=country.id,
                is_active=True,
            )
            db_session.add(branch)
            db_session.commit()
            db_session.refresh(branch)

        resp = logged_in_client.post(
            f"/admin/ns_hierarchy/branch/edit/{branch.id}",
            data={
                "name": "Updated Branch",
                "country_id": str(country.id),
                "is_active": "y",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_delete_branch_without_children(self, logged_in_client, db_session, app):
        from app.models import NSBranch
        with app.app_context():
            country = create_test_country(db_session, name="Delete Branch Country", iso3="DBR")
            branch = NSBranch(
                name="Delete Test Branch",
                country_id=country.id,
                is_active=True,
            )
            db_session.add(branch)
            db_session.commit()
            db_session.refresh(branch)

        resp = logged_in_client.post(
            f"/admin/ns_hierarchy/branch/delete/{branch.id}",
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_delete_branch_with_subbranches_shows_error(self, logged_in_client, db_session, app):
        from app.models import NSBranch, NSSubBranch
        with app.app_context():
            country = create_test_country(db_session, name="Branch With Sub Country", iso3="BWS")
            branch = NSBranch(
                name="Branch With SubBranches",
                country_id=country.id,
                is_active=True,
            )
            db_session.add(branch)
            db_session.commit()
            db_session.refresh(branch)
            subbranch = NSSubBranch(
                name="Child SubBranch",
                branch_id=branch.id,
                is_active=True,
            )
            db_session.add(subbranch)
            db_session.commit()

        resp = logged_in_client.post(
            f"/admin/ns_hierarchy/branch/delete/{branch.id}",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        with app.app_context():
            assert NSBranch.query.get(branch.id) is not None  # Not deleted

    def test_delete_branch_exception(self, logged_in_client, db_session, app):
        from app.models import NSBranch
        with app.app_context():
            country = create_test_country(db_session, name="Delete Exc Branch Country", iso3="DEB")
            branch = NSBranch(
                name="Delete Exception Branch",
                country_id=country.id,
                is_active=True,
            )
            db_session.add(branch)
            db_session.commit()
            db_session.refresh(branch)

        with patch("app.routes.admin.system_admin.sectors.NSBranch") as mock_class:
            mock_branch = MagicMock()
            mock_branch.id = branch.id
            mock_branch.name = branch.name
            mock_branch.country_id = country.id
            mock_branch.subbranches.first.return_value = None
            mock_branch.local_units.first.return_value = None
            mock_class.query.get_or_404.return_value = mock_branch
            with patch("app.routes.admin.system_admin.sectors.db") as mock_db:
                mock_db.session.delete.side_effect = Exception("db error")
                resp = logged_in_client.post(
                    f"/admin/ns_hierarchy/branch/delete/{branch.id}",
                    follow_redirects=False,
                )
        assert resp.status_code == 302

    def test_branch_404_for_missing(self, logged_in_client, db_session):
        resp = logged_in_client.get("/admin/ns_hierarchy/branch/edit/9999999")
        assert resp.status_code == 404


class TestNSSubBranchRoutes:
    def test_get_new_subbranch_renders_form(self, logged_in_client, db_session):
        with _mock_render() as mock_rt:
            resp = logged_in_client.get("/admin/ns_hierarchy/subbranch/new")
        assert resp.status_code == 200
        mock_rt.assert_called()

    def test_post_new_subbranch_valid(self, logged_in_client, db_session, app):
        from app.models import NSBranch, NSSubBranch
        with app.app_context():
            country = create_test_country(db_session, name="SubBranch Country", iso3="SBC")
            branch = NSBranch(
                name="Parent Branch For Sub",
                country_id=country.id,
                is_active=True,
            )
            db_session.add(branch)
            db_session.commit()
            db_session.refresh(branch)

        resp = logged_in_client.post(
            "/admin/ns_hierarchy/subbranch/new",
            data={
                "name": "New SubBranch",
                "branch_id": str(branch.id),
                "is_active": "y",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_get_edit_subbranch_renders_form(self, logged_in_client, db_session, app):
        from app.models import NSBranch, NSSubBranch
        with app.app_context():
            country = create_test_country(db_session, name="Edit SubBranch Country", iso3="ESB")
            branch = NSBranch(name="Branch For SubEdit", country_id=country.id, is_active=True)
            db_session.add(branch)
            db_session.flush()
            subbranch = NSSubBranch(name="Edit SubBranch", branch_id=branch.id, is_active=True)
            db_session.add(subbranch)
            db_session.commit()
            db_session.refresh(subbranch)

        with _mock_render() as mock_rt:
            resp = logged_in_client.get(f"/admin/ns_hierarchy/subbranch/edit/{subbranch.id}")
        assert resp.status_code == 200
        mock_rt.assert_called()

    def test_post_edit_subbranch_updates(self, logged_in_client, db_session, app):
        from app.models import NSBranch, NSSubBranch
        with app.app_context():
            country = create_test_country(db_session, name="Post Edit SubBranch Country", iso3="PSB")
            branch = NSBranch(name="Branch For SubEdit2", country_id=country.id, is_active=True)
            db_session.add(branch)
            db_session.flush()
            subbranch = NSSubBranch(name="Post Edit SubBranch", branch_id=branch.id, is_active=True)
            db_session.add(subbranch)
            db_session.commit()
            db_session.refresh(subbranch)

        resp = logged_in_client.post(
            f"/admin/ns_hierarchy/subbranch/edit/{subbranch.id}",
            data={"name": "Updated SubBranch", "branch_id": str(branch.id), "is_active": "y"},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_delete_subbranch_without_local_units(self, logged_in_client, db_session, app):
        from app.models import NSBranch, NSSubBranch
        with app.app_context():
            country = create_test_country(db_session, name="Delete SubBranch Country", iso3="DSB")
            branch = NSBranch(name="Branch For Delete Sub", country_id=country.id, is_active=True)
            db_session.add(branch)
            db_session.flush()
            subbranch = NSSubBranch(name="Delete SubBranch", branch_id=branch.id, is_active=True)
            db_session.add(subbranch)
            db_session.commit()
            db_session.refresh(subbranch)

        resp = logged_in_client.post(
            f"/admin/ns_hierarchy/subbranch/delete/{subbranch.id}",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        with app.app_context():
            assert NSSubBranch.query.get(subbranch.id) is None

    def test_delete_subbranch_with_local_units_shows_error(self, logged_in_client, db_session, app):
        from app.models import NSBranch, NSSubBranch, NSLocalUnit
        with app.app_context():
            country = create_test_country(db_session, name="SubBranch Local Unit Country", iso3="SLU")
            branch = NSBranch(name="Branch With Local Units", country_id=country.id, is_active=True)
            db_session.add(branch)
            db_session.flush()
            subbranch = NSSubBranch(name="SubBranch With Local Units", branch_id=branch.id, is_active=True)
            db_session.add(subbranch)
            db_session.flush()
            local_unit = NSLocalUnit(name="Local Unit", branch_id=branch.id, subbranch_id=subbranch.id, is_active=True)
            db_session.add(local_unit)
            db_session.commit()

        resp = logged_in_client.post(
            f"/admin/ns_hierarchy/subbranch/delete/{subbranch.id}",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        with app.app_context():
            assert NSSubBranch.query.get(subbranch.id) is not None


class TestNSLocalUnitRoutes:
    def test_get_new_localunit_renders_form(self, logged_in_client, db_session):
        with _mock_render() as mock_rt:
            resp = logged_in_client.get("/admin/ns_hierarchy/localunit/new")
        assert resp.status_code == 200
        mock_rt.assert_called()

    def test_post_new_localunit_valid(self, logged_in_client, db_session, app):
        from app.models import NSBranch, NSLocalUnit
        with app.app_context():
            country = create_test_country(db_session, name="LocalUnit Country", iso3="LUC")
            branch = NSBranch(name="Branch For LocalUnit", country_id=country.id, is_active=True)
            db_session.add(branch)
            db_session.commit()
            db_session.refresh(branch)

        resp = logged_in_client.post(
            "/admin/ns_hierarchy/localunit/new",
            data={
                "name": "New Local Unit",
                "branch_id": str(branch.id),
                "is_active": "y",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_get_edit_localunit_renders_form(self, logged_in_client, db_session, app):
        from app.models import NSBranch, NSLocalUnit
        with app.app_context():
            country = create_test_country(db_session, name="Edit LocalUnit Country", iso3="ELU")
            branch = NSBranch(name="Branch For LocalEdit", country_id=country.id, is_active=True)
            db_session.add(branch)
            db_session.flush()
            localunit = NSLocalUnit(name="Edit Local Unit", branch_id=branch.id, is_active=True)
            db_session.add(localunit)
            db_session.commit()
            db_session.refresh(localunit)

        with _mock_render() as mock_rt:
            resp = logged_in_client.get(f"/admin/ns_hierarchy/localunit/edit/{localunit.id}")
        assert resp.status_code == 200
        mock_rt.assert_called()

    def test_post_edit_localunit_updates(self, logged_in_client, db_session, app):
        from app.models import NSBranch, NSLocalUnit
        with app.app_context():
            country = create_test_country(db_session, name="Post Edit LocalUnit Country", iso3="PEL")
            branch = NSBranch(name="Branch For LocalEdit2", country_id=country.id, is_active=True)
            db_session.add(branch)
            db_session.flush()
            localunit = NSLocalUnit(name="Post Edit Local Unit", branch_id=branch.id, is_active=True)
            db_session.add(localunit)
            db_session.commit()
            db_session.refresh(localunit)

        resp = logged_in_client.post(
            f"/admin/ns_hierarchy/localunit/edit/{localunit.id}",
            data={
                "name": "Updated Local Unit",
                "branch_id": str(branch.id),
                "is_active": "y",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_delete_localunit_success(self, logged_in_client, db_session, app):
        from app.models import NSBranch, NSLocalUnit
        with app.app_context():
            country = create_test_country(db_session, name="Delete LocalUnit Country", iso3="DLU")
            branch = NSBranch(name="Branch For DeleteLocal", country_id=country.id, is_active=True)
            db_session.add(branch)
            db_session.flush()
            localunit = NSLocalUnit(name="Delete Local Unit", branch_id=branch.id, is_active=True)
            db_session.add(localunit)
            db_session.commit()
            db_session.refresh(localunit)

        resp = logged_in_client.post(
            f"/admin/ns_hierarchy/localunit/delete/{localunit.id}",
            follow_redirects=False,
        )
        assert resp.status_code == 302
        with app.app_context():
            assert NSLocalUnit.query.get(localunit.id) is None

    def test_delete_localunit_exception(self, logged_in_client, db_session, app):
        from app.models import NSBranch, NSLocalUnit
        with app.app_context():
            country = create_test_country(db_session, name="Delete Exc LocalUnit Country", iso3="DEL")
            branch = NSBranch(name="Branch Exc Delete Local", country_id=country.id, is_active=True)
            db_session.add(branch)
            db_session.flush()
            localunit = NSLocalUnit(name="Exc Delete Local Unit", branch_id=branch.id, is_active=True)
            db_session.add(localunit)
            db_session.commit()
            db_session.refresh(localunit)

        with patch("app.routes.admin.system_admin.sectors.NSLocalUnit") as mock_class:
            mock_lu = MagicMock()
            mock_lu.id = localunit.id
            mock_lu.name = localunit.name
            mock_class.query.get_or_404.return_value = mock_lu
            with patch("app.routes.admin.system_admin.sectors.db") as mock_db:
                mock_db.session.delete.side_effect = Exception("db error")
                resp = logged_in_client.post(
                    f"/admin/ns_hierarchy/localunit/delete/{localunit.id}",
                    follow_redirects=False,
                )
        assert resp.status_code == 302
