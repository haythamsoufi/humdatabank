"""Access control for unauthenticated document, download and upload-serving routes.

Covers the authorization matrix for ``/forms/public-document/*``, the legacy integer
URLs, the API's URL generation, template-image access, and the response hardening applied
to every route that serves user-supplied files.
"""
from __future__ import annotations

import io
from pathlib import Path
from uuid import uuid4

import pytest

from app import db
from app.extensions import limiter
from app.models.documents import SubmittedDocument
from app.models.enums import DocumentStatus
from app.services.platform import storage_service as storage

pytestmark = [pytest.mark.unit]

PDF_BYTES = b"%PDF-1.4\n%test\n"


def _png_bytes() -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGBA", (2, 2), (255, 0, 0, 255)).save(buf, format="PNG")
    return buf.getvalue()


PNG_BYTES = _png_bytes()


@pytest.fixture
def upload_root(app, tmp_path):
    previous = (app.config.get("UPLOAD_FOLDER"), app.config.get("UPLOAD_STORAGE_PROVIDER"))
    app.config["UPLOAD_FOLDER"] = str(tmp_path)
    app.config["UPLOAD_STORAGE_PROVIDER"] = "filesystem"
    yield tmp_path
    app.config["UPLOAD_FOLDER"], app.config["UPLOAD_STORAGE_PROVIDER"] = previous


@pytest.fixture(autouse=True)
def _reset_limiter():
    limiter.reset()
    yield
    limiter.reset()


def _write_upload(root: Path, storage_path: str, data: bytes) -> None:
    category = storage.submitted_document_rel_storage_category(storage_path)
    target = root / category / storage_path if category else root / storage_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)


def _make_document(db_session, root: Path | None = None, *, public_submission=True, **overrides):
    from tests.factories import create_test_public_submission, create_test_user

    user = create_test_user(db_session)
    fields = dict(
        filename="report.pdf",
        storage_path=f"public/{uuid4().hex}.pdf",
        is_public=True,
        status=DocumentStatus.APPROVED,
        uploaded_by_user_id=user.id,
    )
    if public_submission:
        submission, _form, _token = create_test_public_submission(db_session)
        fields["public_submission_id"] = submission.id
    fields.update(overrides)
    doc = SubmittedDocument(**fields)
    db_session.add(doc)
    db_session.flush()
    if root is not None and doc.storage_path:
        _write_upload(root, doc.storage_path, PDF_BYTES)
    return doc


def _download_url(doc) -> str:
    return f"/forms/public-document/{doc.public_id}/download"


class TestPublicIdColumn:
    def test_public_id_generated_unique_and_not_the_integer_id(self, db_session):
        first = _make_document(db_session, public_submission=False)
        second = _make_document(db_session, public_submission=False)
        assert first.public_id is not None
        assert first.public_id != second.public_id
        assert first.public_id.version == 4

    def test_public_id_is_unique_indexed(self, db_session):
        from sqlalchemy import inspect

        indexes = {i["name"]: i for i in inspect(db.engine).get_indexes("submitted_document")}
        assert indexes["uq_submitted_doc_public_id"]["unique"]
        assert indexes["uq_submitted_doc_public_id"]["column_names"] == ["public_id"]


class TestPublicDocumentDownload:
    def test_public_approved_document_is_served(self, client, db_session, upload_root):
        doc = _make_document(db_session, upload_root)
        resp = client.get(_download_url(doc))
        assert resp.status_code == 200
        assert resp.data == PDF_BYTES
        assert "attachment" in resp.headers["Content-Disposition"]
        assert resp.headers["X-Content-Type-Options"] == "nosniff"

    @pytest.mark.parametrize(
        "overrides",
        [
            {"is_public": False},
            {"status": DocumentStatus.PENDING},
            {"status": DocumentStatus.REJECTED},
            {"is_public": False, "status": DocumentStatus.PENDING},
        ],
    )
    def test_unpublished_documents_are_denied(self, client, db_session, upload_root, overrides):
        doc = _make_document(db_session, upload_root, **overrides)
        assert client.get(_download_url(doc)).status_code == 404
        assert client.get(f"/forms/public-document/{doc.id}/download").status_code == 404
        assert client.get(f"/public_documents/download/{doc.id}").status_code == 404

    def test_document_outside_public_submission_is_denied(self, client, db_session, upload_root):
        doc = _make_document(db_session, upload_root, public_submission=False)
        assert doc.is_public and doc.status == DocumentStatus.APPROVED
        assert client.get(_download_url(doc)).status_code == 404
        assert client.get(f"/forms/public-document/{doc.id}/download").status_code == 404

    def test_unknown_public_id_is_denied(self, client, db_session, upload_root):
        assert client.get(f"/forms/public-document/{uuid4()}/download").status_code == 404

    def test_denied_and_missing_are_indistinguishable(self, client, db_session, upload_root):
        denied = _make_document(db_session, upload_root, is_public=False)
        a = client.get(_download_url(denied))
        b = client.get(f"/forms/public-document/{uuid4()}/download")
        assert a.status_code == b.status_code == 404
        assert a.data == b.data

    def test_missing_file_is_404(self, client, db_session, upload_root):
        doc = _make_document(db_session)
        assert client.get(_download_url(doc)).status_code == 404

    def test_legacy_integer_url_redirects_to_opaque_url(self, client, db_session, upload_root):
        doc = _make_document(db_session, upload_root)
        resp = client.get(f"/forms/public-document/{doc.id}/download")
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith(f"/forms/public-document/{doc.public_id}/download")
        assert resp.headers["Deprecation"] == "true"
        assert 'rel="successor-version"' in resp.headers["Link"]

    def test_legacy_public_documents_url_redirects_straight_to_opaque_url(
        self, client, db_session, upload_root
    ):
        doc = _make_document(db_session, upload_root)
        resp = client.get(f"/public_documents/download/{doc.id}")
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith(f"/forms/public-document/{doc.public_id}/download")

    def test_legacy_integer_url_unknown_id_404(self, client, db_session):
        assert client.get("/forms/public-document/987654/download").status_code == 404

    def test_file_pending_redirects_only_to_allowlisted_source(self, client, db_session, upload_root):
        ok = _make_document(
            db_session, storage_path=None, file_pending=True, source_url="https://go.ifrc.org/a.pdf"
        )
        bad = _make_document(
            db_session, storage_path=None, file_pending=True, source_url="https://evil.example.com/a.pdf"
        )
        resp = client.get(_download_url(ok))
        assert resp.status_code == 302
        assert resp.headers["Location"] == "https://go.ifrc.org/a.pdf"
        assert client.get(_download_url(bad)).status_code == 404

    def test_download_is_rate_limited(self, app, client, db_session, upload_root):
        doc = _make_document(db_session, upload_root)
        app.config["PUBLIC_DOWNLOAD_RATE_LIMIT"] = "2 per minute"
        try:
            codes = [client.get(_download_url(doc)).status_code for _ in range(4)]
        finally:
            app.config.pop("PUBLIC_DOWNLOAD_RATE_LIMIT", None)
        assert codes[:2] == [200, 200]
        assert codes[2:] == [429, 429]

    def test_legacy_integer_url_is_rate_limited(self, app, client, db_session, upload_root):
        doc = _make_document(db_session, upload_root)
        app.config["PUBLIC_DOWNLOAD_RATE_LIMIT"] = "2 per minute"
        try:
            codes = [client.get(f"/forms/public-document/{doc.id}/download").status_code for _ in range(3)]
        finally:
            app.config.pop("PUBLIC_DOWNLOAD_RATE_LIMIT", None)
        assert codes == [302, 302, 429]


class TestApiDocumentListing:
    @pytest.fixture
    def documents(self, db_session, upload_root):
        from tests.factories import create_test_user

        user = create_test_user(db_session)
        rows = {}
        for key, is_public, status in (
            ("cover", True, DocumentStatus.APPROVED),
            ("private", False, DocumentStatus.APPROVED),
            ("pending", True, DocumentStatus.PENDING),
        ):
            doc = SubmittedDocument(
                filename=f"{key}.png", storage_path=f"public/{key}.png",
                thumbnail_relative_path=f"public/{key}_thumb.png",
                document_type="Cover Image", is_public=is_public, status=status,
                uploaded_by_user_id=user.id,
            )
            db_session.add(doc)
            rows[key] = doc
            for rel in (doc.storage_path, doc.thumbnail_relative_path):
                _write_upload(upload_root, rel, PNG_BYTES)
        db_session.flush()
        return rows

    @staticmethod
    def _grant(api_key, db_session, *capabilities):
        from app.services.security.api_key_permissions import build_permissions_document

        api_key_obj, _full = api_key
        api_key_obj.permissions = build_permissions_document(capabilities)
        db_session.commit()

    @pytest.fixture
    def auth_headers(self, api_key, auth_headers, db_session):
        from app.services.security.api_key_permissions import CONTENT_READ

        self._grant(api_key, db_session, CONTENT_READ)
        return auth_headers

    @pytest.fixture
    def privileged_headers(self, api_key, auth_headers, db_session):
        from app.services.security.api_key_permissions import CONTENT_READ, DOCUMENTS_READ

        self._grant(api_key, db_session, CONTENT_READ, DOCUMENTS_READ)
        return auth_headers

    def test_key_without_content_capability_is_refused(self, client, api_key, auth_headers, db_session, documents):
        from app.services.security.api_key_permissions import REFERENCE_READ

        self._grant(api_key, db_session, REFERENCE_READ)
        assert client.get("/api/v1/submitted-documents", headers=auth_headers).status_code == 403

    @staticmethod
    def _ids(resp):
        return {d["id"]: d for d in resp.get_json()["documents"]}

    def test_content_key_lists_public_approved_only_by_default(self, client, auth_headers, documents):
        resp = client.get("/api/v1/submitted-documents", headers=auth_headers)
        assert resp.status_code == 200
        listed = self._ids(resp)
        assert set(listed) == {documents["cover"].id}

    def test_urls_are_opaque(self, client, auth_headers, documents):
        cover = documents["cover"]
        entry = self._ids(client.get("/api/v1/submitted-documents", headers=auth_headers))[cover.id]
        assert entry["public_id"] == str(cover.public_id)
        assert entry["display_url"].endswith(f"/documents/display/{cover.public_id}")
        assert entry["thumbnail_url"].endswith(f"/documents/thumbnail/{cover.public_id}")
        assert f"/{cover.id}" not in entry["display_url"]
        assert f"/{cover.id}" not in entry["thumbnail_url"]

    @pytest.mark.parametrize("query", ["is_public=false", "status=pending", "status=rejected"])
    def test_content_key_cannot_request_unpublished(self, client, auth_headers, documents, query):
        assert client.get(f"/api/v1/submitted-documents?{query}", headers=auth_headers).status_code == 403

    def test_content_key_can_explicitly_request_published(self, client, auth_headers, documents):
        resp = client.get("/api/v1/submitted-documents?is_public=true&status=approved", headers=auth_headers)
        assert resp.status_code == 200
        assert set(self._ids(resp)) == {documents["cover"].id}

    def test_documents_key_sees_unpublished_but_gets_no_public_urls_for_them(
        self, client, privileged_headers, documents
    ):
        resp = client.get("/api/v1/submitted-documents?is_public=false", headers=privileged_headers)
        assert resp.status_code == 200
        private = self._ids(resp)[documents["private"].id]
        assert private["display_url"] is None and private["thumbnail_url"] is None

        resp = client.get("/api/v1/submitted-documents?status=pending", headers=privileged_headers)
        pending = self._ids(resp)[documents["pending"].id]
        assert pending["display_url"] is None and pending["thumbnail_url"] is None

    def test_requires_api_key(self, client, documents):
        assert client.get("/api/v1/submitted-documents").status_code == 401


class TestPublicImageResponseHeaders:
    def test_public_image_is_served_hardened(self, client, db_session, upload_root):
        doc = _make_document(db_session, upload_root, filename="cover.png", storage_path="public/cover.png")
        _write_upload(upload_root, "public/cover.png", PNG_BYTES)
        resp = client.get(f"/documents/display/{doc.public_id}")
        assert resp.status_code == 200
        assert resp.headers["Content-Type"].startswith("image/png")
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["Content-Security-Policy"] == "default-src 'none'; sandbox"


def _template_with_image(db_session, *, storage_path="1/v1/items/1/en/a.png"):
    from tests.factories import create_test_item, create_test_section, create_test_template

    template = create_test_template(db_session)
    section = create_test_section(db_session, template)
    item = create_test_item(
        db_session, section, template, item_type="image",
        config={"image": {"sources": {"en": {"source_type": "upload", "storage_path": storage_path}}}},
    )
    return template, item


class TestTemplateImageAccess:
    def _url(self, item, rel="1/v1/items/1/en/a.png", query=""):
        return f"/forms/template-image/{item.id}/{rel}{query}"

    @pytest.fixture
    def image_file(self, upload_root):
        path = upload_root / storage.TEMPLATE_ASSETS / "1/v1/items/1/en/a.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PNG_BYTES)
        return path

    @pytest.mark.parametrize("value", ["1", "true", "anything", "0"])
    def test_preview_flag_no_longer_bypasses_login(self, client, db_session, image_file, value):
        _template, item = _template_with_image(db_session)
        assert client.get(self._url(item, query=f"?preview={value}")).status_code == 403

    def test_anonymous_without_token_is_forbidden(self, client, db_session, image_file):
        _template, item = _template_with_image(db_session)
        assert client.get(self._url(item)).status_code == 403

    def test_anonymous_with_malformed_token_is_forbidden(self, client, db_session, image_file):
        _template, item = _template_with_image(db_session)
        assert client.get(self._url(item, query="?public_token=nope")).status_code == 403

    def test_anonymous_with_live_public_form_token_is_served(self, client, db_session, image_file):
        from tests.factories import create_test_public_submission

        template, item = _template_with_image(db_session)
        _sub, _form, token = create_test_public_submission(db_session, template=template)
        resp = client.get(self._url(item, query=f"?public_token={token}"))
        assert resp.status_code == 200
        assert resp.headers["X-Content-Type-Options"] == "nosniff"

    def test_unknown_token_is_denied(self, client, db_session, image_file):
        _template, item = _template_with_image(db_session)
        assert client.get(self._url(item, query=f"?public_token={uuid4()}")).status_code == 404

    def test_token_of_another_templates_form_is_denied(self, client, db_session, image_file):
        from tests.factories import create_test_public_submission

        _template, item = _template_with_image(db_session)
        _sub, _form, token = create_test_public_submission(db_session)
        assert client.get(self._url(item, query=f"?public_token={token}")).status_code == 404

    def test_inactive_public_form_is_denied(self, client, db_session, image_file):
        from tests.factories import create_test_public_submission

        template, item = _template_with_image(db_session)
        _sub, form, token = create_test_public_submission(db_session, template=template)
        form.is_public_active = False
        db_session.flush()
        assert client.get(self._url(item, query=f"?public_token={token}")).status_code == 404

    def test_unpublished_version_is_denied(self, client, db_session, image_file):
        from tests.factories import create_test_draft_version, create_test_item, create_test_public_submission, create_test_section

        template, _published_item = _template_with_image(db_session)
        draft = create_test_draft_version(db_session, template)
        section = create_test_section(db_session, template, version=draft)
        draft_item = create_test_item(
            db_session, section, template, version=draft, item_type="image",
            config={"image": {"sources": {"en": {"source_type": "upload", "storage_path": "1/v1/items/1/en/a.png"}}}},
        )
        _sub, _form, token = create_test_public_submission(db_session, template=template)
        assert client.get(self._url(draft_item, query=f"?public_token={token}")).status_code == 404

    def test_path_not_configured_on_item_is_denied(self, client, db_session, image_file):
        from tests.factories import create_test_public_submission

        template, item = _template_with_image(db_session)
        _sub, _form, token = create_test_public_submission(db_session, template=template)
        url = self._url(item, rel="9/v9/other.png", query=f"?public_token={token}")
        assert client.get(url).status_code == 404

    def test_authenticated_user_is_served(self, client, db_session, image_file, test_user):
        _template, item = _template_with_image(db_session)
        with client.session_transaction() as sess:
            sess["_user_id"] = str(test_user.id)
            sess["_fresh"] = True
        assert client.get(self._url(item)).status_code == 200

    def test_entry_url_builder_carries_public_token_only_on_public_form(self, app):
        from app.utils.template_image_assets import build_entry_serve_url

        token = str(uuid4())
        with app.test_request_context(f"/forms/public/{token}"):
            assert f"public_token={token}" in build_entry_serve_url(3, "a/b.png", "en")
        with app.test_request_context("/forms/anything"):
            assert "public_token" not in build_entry_serve_url(3, "a/b.png", "en")


class TestUploadServingHeaders:
    def _put(self, root: Path, rel: str, data: bytes):
        target = root / storage.SYSTEM / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'

    @pytest.mark.parametrize(
        "url,rel",
        [
            ("/api/v1/uploads/branding/evil.svg", "branding/evil.svg"),
            ("/api/v1/uploads/sectors/evil.svg", "sectors/evil.svg"),
            ("/api/v1/uploads/spef/evil.svg", "spef/evil.svg"),
            ("/api/v1/uploads/ns/evil.svg", "ns/evil.svg"),
        ],
    )
    def test_svg_is_never_rendered_inline(self, client, upload_root, url, rel):
        self._put(upload_root, rel, self.SVG)
        resp = client.get(url)
        assert resp.status_code == 200
        assert resp.headers["Content-Disposition"].startswith("attachment")
        assert resp.headers["Content-Security-Policy"] == "default-src 'none'; sandbox"
        assert resp.headers["X-Content-Type-Options"] == "nosniff"

    def test_raster_logo_is_inline_and_hardened(self, client, upload_root):
        self._put(upload_root, "branding/logo.png", PNG_BYTES)
        resp = client.get("/api/v1/uploads/branding/logo.png")
        assert resp.status_code == 200
        assert resp.headers["Content-Disposition"].startswith("inline")
        assert resp.headers["Content-Type"].startswith("image/png")
        assert resp.headers["Content-Security-Policy"] == "default-src 'none'; sandbox"
        assert resp.headers["X-Content-Type-Options"] == "nosniff"

    @pytest.mark.parametrize("name", ["..", ".", "%2e%2e", "..%5csecret", "a/../../secret"])
    def test_traversal_names_do_not_escape(self, client, upload_root, name):
        (upload_root / "secret").write_text("nope")
        assert client.get(f"/api/v1/uploads/branding/{name}").status_code == 404

    def test_missing_file_is_404(self, client, upload_root):
        assert client.get("/api/v1/uploads/branding/none.png").status_code == 404


class TestStorageStreamResponse:
    def test_inline_pdf_keeps_viewer_compatible_headers(self, app, upload_root):
        target = upload_root / storage.RESOURCES / "doc.pdf"
        target.parent.mkdir(parents=True)
        target.write_bytes(PDF_BYTES)
        with app.test_request_context():
            resp = storage.stream_response(storage.RESOURCES, "doc.pdf", filename="doc.pdf", as_attachment=False)
        assert resp.headers["Content-Disposition"].startswith("inline")
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert "Content-Security-Policy" not in resp.headers

    @pytest.mark.parametrize(
        "filename,mimetype",
        [
            ("page.html", None),
            ("page.htm", None),
            ("img.svg", None),
            ("data.xml", None),
            ("x.js", None),
            ("disguised.bin", "text/html"),
            ("disguised.svg", "image/png"),
        ],
    )
    def test_active_content_forced_to_attachment(self, app, upload_root, filename, mimetype):
        target = upload_root / storage.SYSTEM / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"<x/>")
        with app.test_request_context():
            resp = storage.stream_response(
                storage.SYSTEM, filename, filename=filename, mimetype=mimetype, as_attachment=False
            )
        assert resp.headers["Content-Disposition"].startswith("attachment")
        assert resp.headers["Content-Security-Policy"] == "default-src 'none'; sandbox"

    def test_traversal_rel_path_rejected(self, app, upload_root):
        with app.test_request_context():
            assert storage.exists(storage.SYSTEM, "../secret") is False

    def test_blob_names_reject_relative_segments(self):
        for bad in ("a/../b", "../b", "a/./b"):
            with pytest.raises(PermissionError):
                storage._blob_name(storage.SYSTEM, bad)
        assert storage._blob_name(storage.SYSTEM, "sectors/a.png") == "system/sectors/a.png"

    def test_security_middleware_keeps_upload_csp(self, client, upload_root):
        target = upload_root / storage.SYSTEM / "branding" / "logo.png"
        target.parent.mkdir(parents=True)
        target.write_bytes(PNG_BYTES)
        resp = client.get("/api/v1/uploads/branding/logo.png")
        assert resp.headers["Content-Security-Policy"] == "default-src 'none'; sandbox"
        assert resp.headers["X-Frame-Options"] == "DENY"

    def test_security_middleware_still_sets_csp_elsewhere(self, client):
        resp = client.get("/health")
        assert "default-src 'self'" in resp.headers["Content-Security-Policy"]


class TestBrandingUploadValidation:
    def _file(self, name: str, data: bytes):
        from werkzeug.datastructures import FileStorage

        return FileStorage(stream=io.BytesIO(data), filename=name)

    @pytest.fixture(autouse=True)
    def _capture_uploads(self, monkeypatch):
        self.uploaded = []
        monkeypatch.setattr(
            "app.utils.branding_visual_assets.storage.upload",
            lambda category, rel, data: self.uploaded.append(rel) or rel,
        )

    def test_svg_logo_rejected(self, app):
        from app.utils.branding_visual_assets import upload_organization_logo

        with pytest.raises(ValueError, match="not allowed"):
            upload_organization_logo(self._file("logo.svg", b"<svg xmlns='http://www.w3.org/2000/svg'/>"))
        assert self.uploaded == []

    def test_svg_favicon_rejected(self, app):
        from app.utils.branding_visual_assets import upload_organization_favicon

        with pytest.raises(ValueError, match="not allowed"):
            upload_organization_favicon(self._file("favicon.svg", b"<svg/>"))

    def test_valid_png_accepted(self, app):
        from app.utils.branding_visual_assets import upload_organization_logo

        rel = upload_organization_logo(self._file("Logo.PNG", PNG_BYTES))
        assert rel.startswith("branding/") and rel.endswith("_logo.png")
        assert self.uploaded == [rel]

    def test_html_disguised_as_png_rejected(self, app):
        from app.utils.branding_visual_assets import upload_organization_logo

        with pytest.raises(ValueError, match="valid image"):
            upload_organization_logo(self._file("logo.png", b"<html><script>alert(1)</script></html>"))
        assert self.uploaded == []

    def test_png_with_wrong_extension_rejected(self, app):
        from app.utils.branding_visual_assets import upload_organization_logo

        with pytest.raises(ValueError, match="does not match"):
            upload_organization_logo(self._file("logo.jpg", PNG_BYTES))

    def test_ico_favicon_accepted(self, app):
        from PIL import Image

        from app.utils.branding_visual_assets import upload_organization_favicon

        buf = io.BytesIO()
        Image.new("RGBA", (16, 16), (255, 0, 0, 255)).save(buf, format="ICO")
        rel = upload_organization_favicon(self._file("favicon.ico", buf.getvalue()))
        assert rel.endswith("_favicon.ico")

    def test_ico_not_allowed_for_logo(self, app):
        from app.utils.branding_visual_assets import upload_organization_logo

        with pytest.raises(ValueError, match="not allowed"):
            upload_organization_logo(self._file("logo.ico", b"\x00\x00\x01\x00"))


class TestExternalUrlValidation:
    GOOD = [
        "https://go.ifrc.org/doc.pdf",
        "https://GO.IFRC.ORG/doc.pdf",
        "https://sub.ifrc.org/a/b.pdf?x=1",
        "https://go.ifrc.org:443/doc.pdf",
        "https://prddsgolocstor01.blob.core.windows.net/c/x.pdf",
    ]
    BAD = [
        "",
        "   ",
        None,
        "http://go.ifrc.org/doc.pdf",
        "https://evil.example.com/doc.pdf",
        "https://go.ifrc.org.evil.example.com/doc.pdf",
        "https://evilifrc.org/doc.pdf",
        "https://go.ifrc.org@evil.example.com/",
        "https://user:pw@go.ifrc.org/",
        "https://go.ifrc.org:8443/doc.pdf",
        "https://go.ifrc.org:notaport/doc.pdf",
        "https://127.0.0.1/doc.pdf",
        "https://[::1]/doc.pdf",
        "//go.ifrc.org/doc.pdf",
        "/relative/path",
        "javascript:alert(1)",
        "data:text/html,hi",
        "https://go.ifrc.org/doc.pdf\r\nSet-Cookie: a=b",
        "https://go.ifrc.org/a b.pdf",
        "https://go.ifrc.org\\@evil.example.com/",
    ]

    @pytest.mark.parametrize("url", GOOD)
    def test_allowlisted_urls_pass(self, app, url):
        from app.utils.external_url_validation import safe_external_redirect_target, validate_allowlisted_https_url

        with app.app_context():
            assert validate_allowlisted_https_url(url) == (True, "")
            assert safe_external_redirect_target(url) == url.strip()

    @pytest.mark.parametrize("url", BAD)
    def test_untrusted_urls_fail(self, app, url):
        from app.utils.external_url_validation import safe_external_redirect_target, validate_allowlisted_https_url

        with app.app_context():
            ok, reason = validate_allowlisted_https_url(url)
            assert ok is False and reason
            assert safe_external_redirect_target(url) is None

    def test_fails_closed_without_configured_hosts(self, app):
        from app.utils.external_url_validation import validate_allowlisted_https_url

        with app.app_context():
            previous = app.config.get("IFRC_DOCUMENT_ALLOWED_HOSTS")
            app.config["IFRC_DOCUMENT_ALLOWED_HOSTS"] = []
            try:
                ok, reason = validate_allowlisted_https_url("https://go.ifrc.org/a.pdf")
            finally:
                app.config["IFRC_DOCUMENT_ALLOWED_HOSTS"] = previous
        assert ok is False and "not configured" in reason

    @pytest.mark.parametrize("url", GOOD + BAD)
    def test_matches_ai_documents_validator(self, app, url):
        """The AI-documents SSRF validator and the shared one must agree on every input."""
        from app.routes.ai_documents.helpers import _validate_ifrc_fetch_url
        from app.utils.external_url_validation import validate_allowlisted_https_url

        with app.app_context():
            try:
                legacy = _validate_ifrc_fetch_url(url)[0]
            except ValueError:
                legacy = False
            shared = validate_allowlisted_https_url(url)[0]
            has_control_chars = any(ch.isspace() or ord(ch) < 32 for ch in (url or "").strip())
            if has_control_chars:
                assert shared is False
            else:
                assert shared == legacy
