"""Tests for app/utils/advanced_validation.py – targets 100 % coverage."""
import io
import pytest
from unittest.mock import patch, MagicMock
from flask import Flask
from werkzeug.datastructures import FileStorage

from app.utils.advanced_validation import (
    AdvancedValidator,
    validate_upload_extension_and_mime,
    sanitize_input,
    validate_file,
    sanitize_filename,
    validator,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def app_ctx():
    app = Flask(__name__)
    app.config["TESTING"] = True
    with app.app_context():
        yield app


def _file(data: bytes = b"hello", name: str = "test.txt", ctype: str = "text/plain") -> FileStorage:
    return FileStorage(stream=io.BytesIO(data), filename=name, content_type=ctype)


# ---------------------------------------------------------------------------
# sanitize_html
# ---------------------------------------------------------------------------

class TestSanitizeHtml:
    def test_empty_string(self):
        assert AdvancedValidator.sanitize_html("") == ""

    def test_none(self):
        assert AdvancedValidator.sanitize_html(None) == ""

    def test_no_html_escapes_tags(self):
        result = AdvancedValidator.sanitize_html("<script>alert(1)</script>", allow_html=False)
        assert "<script>" not in result
        assert "&lt;script&gt;" in result

    def test_allow_html_keeps_allowed_tags(self, app_ctx):
        result = AdvancedValidator.sanitize_html("<p>Hello <strong>world</strong></p>", allow_html=True)
        assert "<p>" in result
        assert "<strong>" in result

    def test_allow_html_strips_disallowed_tags(self, app_ctx):
        result = AdvancedValidator.sanitize_html("<p>ok</p><script>bad</script>", allow_html=True)
        assert "<script>" not in result
        assert "<p>" in result

    def test_allow_html_bleach_exception_falls_back_to_escape(self, app_ctx):
        with patch("bleach.clean", side_effect=Exception("bleach error")):
            result = AdvancedValidator.sanitize_html("<p>test</p>", allow_html=True)
        assert "&lt;p&gt;" in result


# ---------------------------------------------------------------------------
# validate_email
# ---------------------------------------------------------------------------

class TestValidateEmail:
    def test_empty(self):
        assert not AdvancedValidator.validate_email("")

    def test_none(self):
        assert not AdvancedValidator.validate_email(None)

    def test_valid(self):
        assert AdvancedValidator.validate_email("user@example.com")

    def test_valid_subdomain(self):
        assert AdvancedValidator.validate_email("a.b+c@mail.example.org")

    def test_invalid_no_at(self):
        assert not AdvancedValidator.validate_email("userexample.com")

    def test_invalid_no_domain(self):
        assert not AdvancedValidator.validate_email("user@")

    def test_invalid_short_tld(self):
        assert not AdvancedValidator.validate_email("user@example.c")

    def test_invalid_spaces(self):
        assert not AdvancedValidator.validate_email("user @example.com")


# ---------------------------------------------------------------------------
# validate_phone_number
# ---------------------------------------------------------------------------

class TestValidatePhoneNumber:
    def test_empty_is_valid(self):
        assert AdvancedValidator.validate_phone_number("")

    def test_none_is_valid(self):
        assert AdvancedValidator.validate_phone_number(None)

    def test_valid_international(self):
        assert AdvancedValidator.validate_phone_number("+1 (555) 123-4567")

    def test_exactly_7_digits(self):
        assert AdvancedValidator.validate_phone_number("1234567")

    def test_exactly_15_digits(self):
        assert AdvancedValidator.validate_phone_number("1" * 15)

    def test_too_short(self):
        assert not AdvancedValidator.validate_phone_number("12345")

    def test_too_long(self):
        assert not AdvancedValidator.validate_phone_number("1" * 16)


# ---------------------------------------------------------------------------
# validate_url
# ---------------------------------------------------------------------------

class TestValidateUrl:
    def test_empty_is_valid(self):
        assert AdvancedValidator.validate_url("")

    def test_none_is_valid(self):
        assert AdvancedValidator.validate_url(None)

    def test_valid_https(self):
        assert AdvancedValidator.validate_url("https://example.com")

    def test_valid_http_with_path(self):
        assert AdvancedValidator.validate_url("http://example.com/path?q=1")

    def test_invalid_no_scheme(self):
        assert not AdvancedValidator.validate_url("example.com")

    def test_invalid_ftp(self):
        assert not AdvancedValidator.validate_url("ftp://example.com")

    def test_invalid_plain_word(self):
        assert not AdvancedValidator.validate_url("notaurl")


# ---------------------------------------------------------------------------
# sanitize_filename
# ---------------------------------------------------------------------------

class TestSanitizeFilename:
    def test_empty(self):
        assert AdvancedValidator.sanitize_filename("") == "untitled"

    def test_none(self):
        assert AdvancedValidator.sanitize_filename(None) == "untitled"

    def test_normal_filename(self):
        assert AdvancedValidator.sanitize_filename("document.pdf") == "document.pdf"

    def test_path_traversal(self):
        result = AdvancedValidator.sanitize_filename("../../../etc/passwd")
        assert ".." not in result
        assert result

    def test_windows_path(self):
        result = AdvancedValidator.sanitize_filename("C:\\Users\\file.txt")
        assert result == "file.txt"

    def test_null_bytes_removed(self):
        result = AdvancedValidator.sanitize_filename("file\x00name.txt")
        assert "\x00" not in result

    def test_control_chars_removed(self):
        result = AdvancedValidator.sanitize_filename("file\x01\x1fname.txt")
        assert "\x01" not in result

    def test_dangerous_chars_replaced(self):
        result = AdvancedValidator.sanitize_filename("file<na>me.txt")
        assert "<" not in result
        assert ">" not in result

    def test_colon_replaced(self):
        result = AdvancedValidator.sanitize_filename("file:name.txt")
        assert ":" not in result

    def test_long_filename_with_extension(self):
        long_name = "a" * 300 + ".txt"
        result = AdvancedValidator.sanitize_filename(long_name)
        assert len(result) <= 255
        assert result.endswith(".txt")

    def test_long_filename_no_extension(self):
        long_name = "a" * 300
        result = AdvancedValidator.sanitize_filename(long_name)
        assert len(result) <= 255

    def test_forward_slash_in_name(self):
        result = AdvancedValidator.sanitize_filename("path/to/file.txt")
        assert "/" not in result
        assert result == "file.txt"

    def test_double_dot_in_basename(self):
        result = AdvancedValidator.sanitize_filename("..hidden")
        assert result  # should not be empty


# ---------------------------------------------------------------------------
# validate_mime_type
# ---------------------------------------------------------------------------

class TestValidateMimeType:
    def test_none_file(self):
        valid, mime = AdvancedValidator.validate_mime_type(None)
        assert valid is True
        assert mime is None

    def test_file_without_read_attr(self):
        valid, mime = AdvancedValidator.validate_mime_type(object())
        assert valid is True

    def test_file_too_small(self):
        f = _file(b"ab")
        valid, mime = AdvancedValidator.validate_mime_type(f)
        assert valid is True

    def test_pdf_matches_pdf_extension(self):
        f = _file(b"%PDF-1.4 " + b"\x00" * 28, "f.pdf")
        valid, mime = AdvancedValidator.validate_mime_type(f, [".pdf"])
        assert valid is True
        assert mime == "application/pdf"

    def test_pdf_mismatches_jpg_extension(self):
        f = _file(b"%PDF-1.4 " + b"\x00" * 28, "f.jpg")
        valid, mime = AdvancedValidator.validate_mime_type(f, [".jpg"])
        assert valid is False
        assert mime == "application/pdf"

    def test_exe_magic(self):
        f = _file(b"MZ" + b"\x00" * 30, "f.exe")
        valid, mime = AdvancedValidator.validate_mime_type(f, [".exe"])
        assert valid is True

    def test_jpeg_magic(self):
        f = _file(b"\xff\xd8\xff\xe0" + b"\x00" * 28, "img.jpg")
        valid, mime = AdvancedValidator.validate_mime_type(f, [".jpg", ".jpeg"])
        assert valid is True
        assert mime == "image/jpeg"

    def test_png_magic(self):
        f = _file(b"\x89PNG\r\n\x1a\n" + b"\x00" * 24, "img.png")
        valid, mime = AdvancedValidator.validate_mime_type(f, [".png"])
        assert valid is True
        assert mime == "image/png"

    def test_gif87a_magic(self):
        f = _file(b"GIF87a" + b"\x00" * 26, "img.gif")
        valid, mime = AdvancedValidator.validate_mime_type(f, [".gif"])
        assert valid is True

    def test_gif89a_magic(self):
        f = _file(b"GIF89a" + b"\x00" * 26, "img.gif")
        valid, mime = AdvancedValidator.validate_mime_type(f, [".gif"])
        assert valid is True

    def test_riff_webp(self):
        f = _file(b"RIFF" + b"\x00" * 28, "img.webp")
        valid, mime = AdvancedValidator.validate_mime_type(f, [".webp"])
        assert valid is True

    def test_zip_office_xlsx(self):
        f = _file(b"PK\x03\x04" + b"\x00" * 28, "doc.xlsx")
        valid, mime = AdvancedValidator.validate_mime_type(f, [".xlsx"])
        assert valid is True

    def test_zip_empty_xlsx(self):
        f = _file(b"PK\x05\x06" + b"\x00" * 28, "doc.xlsx")
        valid, mime = AdvancedValidator.validate_mime_type(f, [".xlsx"])
        assert valid is True

    def test_ms_legacy_office(self):
        f = _file(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 24, "doc.doc")
        valid, mime = AdvancedValidator.validate_mime_type(f, [".doc"])
        assert valid is True

    def test_text_file_matches_txt(self):
        f = _file(b"Hello world text content here!!!", "file.txt")
        valid, mime = AdvancedValidator.validate_mime_type(f, [".txt"])
        assert valid is True
        assert mime == "text/plain"

    def test_text_file_matches_csv(self):
        f = _file(b"name,age\nAlice,30\nBob,25", "file.csv")
        valid, mime = AdvancedValidator.validate_mime_type(f, [".csv"])
        assert valid is True

    def test_text_file_mismatch_non_text_ext(self):
        f = _file(b"Hello world text content here!!!", "file.pdf")
        valid, mime = AdvancedValidator.validate_mime_type(f, [".pdf"])
        # Text content claiming to be PDF – detected as text, expected .pdf → mismatch
        assert valid is False

    def test_zip_matches_odt(self):
        f = _file(b"PK\x03\x04" + b"\x00" * 28, "doc.odt")
        valid, mime = AdvancedValidator.validate_mime_type(f, [".odt"])
        assert valid is True

    def test_unknown_binary_no_expected_extensions(self):
        f = _file(b"\x80\x81\x82\x83" * 8, "file.bin")
        valid, mime = AdvancedValidator.validate_mime_type(f)
        assert valid is True
        assert mime is None

    def test_unknown_binary_with_extension(self):
        f = _file(b"\x80\x81\x82\x83" * 8, "file.bin")
        valid, _ = AdvancedValidator.validate_mime_type(f, [".bin"])
        # Unknown binary type – permissive, allow through
        assert valid is True

    def test_text_file_matches_log_extension(self):
        """Text-detected file with .log extension hits the text_extensions permissive path."""
        f = _file(b"some log content here!!", "app.log")
        valid, mime = AdvancedValidator.validate_mime_type(f, [".log"])
        assert valid is True
        assert mime == "text/plain"

    def test_extension_without_leading_dot(self):
        f = _file(b"%PDF-1.4 " + b"\x00" * 28, "f.pdf")
        valid, mime = AdvancedValidator.validate_mime_type(f, ["pdf"])
        assert valid is True

    def test_exception_returns_false(self, app_ctx):
        """If file.read() raises, should return (False, None) via exception handler."""
        f = MagicMock()
        f.tell.return_value = 0
        f.read.side_effect = RuntimeError("read error")
        valid, mime = AdvancedValidator.validate_mime_type(f)
        assert valid is False
        assert mime is None


# ---------------------------------------------------------------------------
# validate_file_upload
# ---------------------------------------------------------------------------

class TestValidateFileUpload:
    def test_no_file(self, app_ctx):
        result = AdvancedValidator.validate_file_upload(None)
        assert not result["valid"]
        assert "No file provided" in result["errors"][0]

    def test_empty_filename(self, app_ctx):
        f = FileStorage(stream=io.BytesIO(b""), filename="", content_type="text/plain")
        result = AdvancedValidator.validate_file_upload(f)
        assert not result["valid"]

    def test_dangerous_extension_exe(self, app_ctx):
        f = _file(b"MZ" + b"\x00" * 62, "virus.exe")
        result = AdvancedValidator.validate_file_upload(f)
        assert not result["valid"]
        assert "security reasons" in result["errors"][0]

    def test_dangerous_extension_sh(self, app_ctx):
        f = _file(b"#!/bin/bash", "run.sh")
        result = AdvancedValidator.validate_file_upload(f)
        assert not result["valid"]

    def test_not_in_allowed_extensions(self, app_ctx):
        f = _file(b"data", "file.xyz")
        result = AdvancedValidator.validate_file_upload(f, allowed_extensions=[".pdf"])
        assert not result["valid"]
        assert "not allowed" in result["errors"][0]

    def test_valid_pdf(self, app_ctx):
        pdf_data = b"%PDF-1.4 " + b"\x00" * 55
        f = _file(pdf_data, "doc.pdf")
        result = AdvancedValidator.validate_file_upload(f, allowed_extensions=[".pdf"])
        assert result["valid"]
        assert result["file_type"] == "document"

    def test_valid_docx(self, app_ctx):
        data = b"PK\x03\x04" + b"\x00" * 60
        f = _file(data, "doc.docx")
        result = AdvancedValidator.validate_file_upload(f, allowed_extensions=[".docx"])
        assert result["valid"]
        assert result["file_type"] == "document"

    def test_valid_txt(self, app_ctx):
        f = _file(b"plain text content here!", "note.txt")
        result = AdvancedValidator.validate_file_upload(f)
        assert result["valid"]
        assert result["file_type"] == "document"

    def test_valid_xlsx(self, app_ctx):
        data = b"PK\x03\x04" + b"\x00" * 60
        f = _file(data, "data.xlsx")
        result = AdvancedValidator.validate_file_upload(f)
        assert result["valid"]
        assert result["file_type"] == "spreadsheet"

    def test_valid_xls(self, app_ctx):
        data = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 56
        f = _file(data, "data.xls")
        result = AdvancedValidator.validate_file_upload(f)
        assert result["valid"]
        assert result["file_type"] == "spreadsheet"

    def test_valid_pptx(self, app_ctx):
        data = b"PK\x03\x04" + b"\x00" * 60
        f = _file(data, "slides.pptx")
        result = AdvancedValidator.validate_file_upload(f)
        assert result["valid"]
        assert result["file_type"] == "presentation"

    def test_valid_ppt(self, app_ctx):
        data = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 56
        f = _file(data, "slides.ppt")
        result = AdvancedValidator.validate_file_upload(f)
        assert result["valid"]
        assert result["file_type"] == "presentation"

    def test_valid_jpeg(self, app_ctx):
        jpeg_data = b"\xff\xd8\xff\xe0" + b"\x00" * 60
        f = _file(jpeg_data, "photo.jpg")
        result = AdvancedValidator.validate_file_upload(f)
        assert result["valid"]
        assert result["file_type"] == "image"

    def test_valid_png(self, app_ctx):
        png_data = b"\x89PNG\r\n\x1a\n" + b"\x00" * 56
        f = _file(png_data, "img.png")
        result = AdvancedValidator.validate_file_upload(f)
        assert result["valid"]
        assert result["file_type"] == "image"

    def test_valid_gif(self, app_ctx):
        gif_data = b"GIF89a" + b"\x00" * 58
        f = _file(gif_data, "anim.gif")
        result = AdvancedValidator.validate_file_upload(f)
        assert result["valid"]
        assert result["file_type"] == "image"

    def test_valid_webp(self, app_ctx):
        webp_data = b"RIFF" + b"\x00" * 60
        f = _file(webp_data, "img.webp")
        result = AdvancedValidator.validate_file_upload(f)
        assert result["valid"]
        assert result["file_type"] == "image"

    def test_valid_svg(self, app_ctx):
        svg_data = b'<svg xmlns="http://www.w3.org/2000/svg"><circle/></svg>'
        f = _file(svg_data, "icon.svg")
        result = AdvancedValidator.validate_file_upload(f)
        assert result["valid"]

    def test_valid_xml_svg(self, app_ctx):
        xml_data = b'<?xml version="1.0"?><svg></svg>'
        f = _file(xml_data, "icon.svg")
        result = AdvancedValidator.validate_file_upload(f)
        assert result["valid"]

    def test_image_file_too_large(self, app_ctx):
        large_data = b"\xff\xd8\xff" + b"x" * (6 * 1024 * 1024)
        f = _file(large_data, "big.jpg")
        result = AdvancedValidator.validate_file_upload(f)
        assert not result["valid"]
        assert "exceeds maximum" in result["errors"][0]

    def test_image_with_pdf_magic_rejected(self, app_ctx):
        pdf_data = b"%PDF-1.4 " + b"\x00" * 55
        f = _file(pdf_data, "fake.jpg")
        result = AdvancedValidator.validate_file_upload(f)
        assert not result["valid"]
        assert "document, not an image" in result["errors"][0]

    def test_image_with_zip_magic_rejected(self, app_ctx):
        zip_data = b"PK\x03\x04" + b"\x00" * 60
        f = _file(zip_data, "fake.png")
        result = AdvancedValidator.validate_file_upload(f)
        assert not result["valid"]

    def test_image_with_ms_legacy_magic_rejected(self, app_ctx):
        ms_data = b"\xd0\xcf\x11\xe0" + b"\x00" * 60
        f = _file(ms_data, "fake.gif")
        result = AdvancedValidator.validate_file_upload(f)
        assert not result["valid"]

    def test_unknown_image_binary_allowed(self, app_ctx):
        # Unknown binary (no recognized magic) – permissive, allowed through
        unknown_data = b"\xAB\xCD\xEF\x01" + b"\x00" * 60
        f = _file(unknown_data, "img.jpg")
        result = AdvancedValidator.validate_file_upload(f)
        assert result["valid"]

    def test_svg_header_decode_exception_hits_except_branch(self, app_ctx):
        """Force header.decode() to raise so the except block (lines 353-354) runs."""
        from werkzeug.datastructures import FileStorage as WerkzeugFS

        jpeg_data = b"\xff\xd8\xff\xe0" + b"\x00" * 60

        # A mock that looks like bytes but whose .decode() raises
        bad_header = MagicMock(spec=bytes)
        bad_header.__len__ = MagicMock(return_value=len(jpeg_data))
        bad_header.startswith = MagicMock(return_value=False)
        bad_header.decode = MagicMock(side_effect=RuntimeError("forced decode fail"))

        # Wrap in a real stream; patch FileStorage.read to return the bad header
        real_stream = io.BytesIO(jpeg_data)
        fs = WerkzeugFS(stream=real_stream, filename="photo.jpg",
                        content_type="image/jpeg")

        # Patch only on the instance so we don't touch the C type
        orig_read = fs.read

        read_calls = [0]

        def fake_read(n=-1):
            read_calls[0] += 1
            if n == 64 and read_calls[0] >= 2:   # second+ read(64) → bad header
                return bad_header
            return orig_read(n)

        fs.read = fake_read

        result = AdvancedValidator.validate_file_upload(fs)
        # After the decode error is caught and logged the code continues
        # (is_svg stays False) and the unknown binary is allowed through
        assert result["valid"]

    def test_mime_mismatch_from_validate_mime(self, app_ctx):
        pdf_data = b"%PDF-1.4 " + b"\x00" * 30
        f = _file(pdf_data, "fake.jpg")
        result = AdvancedValidator.validate_file_upload(f, allowed_extensions=[".jpg"])
        assert not result["valid"]
        assert "MIME type" in result["errors"][0]

    def test_no_extension_skips_mime_check(self, app_ctx):
        f = _file(b"some data", "noext")
        result = AdvancedValidator.validate_file_upload(f)
        assert result["valid"]
        assert result["file_type"] == "default"

    def test_sanitized_filename_stored(self, app_ctx):
        f = _file(b"data", "my<file>.txt")
        result = AdvancedValidator.validate_file_upload(f)
        assert result["sanitized_filename"] is not None
        assert "<" not in result["sanitized_filename"]


# ---------------------------------------------------------------------------
# validate_json_input
# ---------------------------------------------------------------------------

class TestValidateJsonInput:
    def test_required_field_missing(self, app_ctx):
        data = {}
        schema = {"name": {"type": "string", "required": True}}
        result = AdvancedValidator.validate_json_input(data, schema)
        assert not result["valid"]
        assert "required" in result["errors"][0]

    def test_wrong_type_string(self, app_ctx):
        data = {"name": 123}
        schema = {"name": {"type": "string"}}
        result = AdvancedValidator.validate_json_input(data, schema)
        assert not result["valid"]
        assert "must be a string" in result["errors"][0]

    def test_wrong_type_integer(self, app_ctx):
        data = {"count": "not_int"}
        schema = {"count": {"type": "integer"}}
        result = AdvancedValidator.validate_json_input(data, schema)
        assert not result["valid"]
        assert "must be an integer" in result["errors"][0]

    def test_wrong_type_boolean(self, app_ctx):
        data = {"active": "yes"}
        schema = {"active": {"type": "boolean"}}
        result = AdvancedValidator.validate_json_input(data, schema)
        assert not result["valid"]
        assert "must be a boolean" in result["errors"][0]

    def test_valid_string(self, app_ctx):
        data = {"name": "Alice"}
        schema = {"name": {"type": "string"}}
        result = AdvancedValidator.validate_json_input(data, schema)
        assert result["valid"]
        assert result["sanitized_data"]["name"] == "Alice"

    def test_valid_integer(self, app_ctx):
        data = {"count": 42}
        schema = {"count": {"type": "integer"}}
        result = AdvancedValidator.validate_json_input(data, schema)
        assert result["valid"]
        assert result["sanitized_data"]["count"] == 42

    def test_valid_boolean(self, app_ctx):
        data = {"active": True}
        schema = {"active": {"type": "boolean"}}
        result = AdvancedValidator.validate_json_input(data, schema)
        assert result["valid"]
        assert result["sanitized_data"]["active"] is True

    def test_html_sanitized_by_default(self, app_ctx):
        data = {"desc": "<script>bad</script>"}
        schema = {"desc": {"type": "string"}}
        result = AdvancedValidator.validate_json_input(data, schema)
        assert result["valid"]
        assert "<script>" not in result["sanitized_data"]["desc"]

    def test_allow_html_in_schema(self, app_ctx):
        data = {"content": "<p>Hello</p>"}
        schema = {"content": {"type": "string", "allow_html": True}}
        result = AdvancedValidator.validate_json_input(data, schema)
        assert result["valid"]
        assert "<p>Hello</p>" in result["sanitized_data"]["content"]

    def test_optional_field_absent(self, app_ctx):
        data = {}
        schema = {"optional": {"type": "string", "required": False}}
        result = AdvancedValidator.validate_json_input(data, schema)
        assert result["valid"]

    def test_non_string_value_stored_as_is(self, app_ctx):
        data = {"score": 99}
        schema = {"score": {"type": "integer"}}
        result = AdvancedValidator.validate_json_input(data, schema)
        assert result["sanitized_data"]["score"] == 99

    def test_exception_in_sanitize_handled(self, app_ctx):
        with patch.object(AdvancedValidator, "sanitize_html", side_effect=Exception("oops")):
            data = {"name": "test"}
            schema = {"name": {"type": "string"}}
            result = AdvancedValidator.validate_json_input(data, schema)
        assert not result["valid"]
        assert "Validation error occurred" in result["errors"]


# ---------------------------------------------------------------------------
# validate_upload_extension_and_mime
# ---------------------------------------------------------------------------

class TestValidateUploadExtensionAndMime:
    def test_no_file(self):
        valid, err, ext = validate_upload_extension_and_mime(None, [".csv"])
        assert not valid
        assert "No file provided" in err

    def test_empty_filename(self):
        f = FileStorage(stream=io.BytesIO(b""), filename="", content_type="text/plain")
        valid, err, ext = validate_upload_extension_and_mime(f, [".csv"])
        assert not valid

    def test_unsupported_extension(self):
        f = _file(b"data", "report.pdf")
        valid, err, ext = validate_upload_extension_and_mime(f, [".csv", ".xlsx"])
        assert not valid
        assert "Unsupported file type" in err
        assert ext == ".pdf"

    def test_valid_csv(self):
        f = _file(b"name,age\nAlice,30", "data.csv")
        valid, err, ext = validate_upload_extension_and_mime(f, [".csv"])
        assert valid
        assert err is None
        assert ext == ".csv"

    def test_extension_without_dot(self):
        f = _file(b"name,age\nAlice,30", "data.csv")
        valid, err, ext = validate_upload_extension_and_mime(f, ["csv"])
        assert valid

    def test_mime_mismatch(self):
        pdf_data = b"%PDF-1.4 " + b"\x00" * 30
        f = _file(pdf_data, "fake.csv")
        valid, err, ext = validate_upload_extension_and_mime(f, [".csv"])
        assert not valid
        assert "validation failed" in err.lower()

    def test_stream_rewound_on_success(self):
        f = _file(b"name,age\nAlice,30", "data.csv")
        f.stream.read()  # advance stream
        valid, _, _ = validate_upload_extension_and_mime(f, [".csv"])
        assert valid
        assert f.stream.tell() == 0

    def test_xlsx_valid(self):
        data = b"PK\x03\x04" + b"\x00" * 30
        f = _file(data, "data.xlsx")
        valid, err, ext = validate_upload_extension_and_mime(f, [".xlsx"])
        assert valid
        assert ext == ".xlsx"


# ---------------------------------------------------------------------------
# Convenience module-level functions
# ---------------------------------------------------------------------------

class TestConvenienceFunctions:
    def test_sanitize_input_escapes_html(self, app_ctx):
        result = sanitize_input("<script>xss</script>")
        assert "<script>" not in result

    def test_sanitize_input_allow_html(self, app_ctx):
        result = sanitize_input("<p>ok</p>", allow_html=True)
        assert "<p>" in result

    def test_validate_file_returns_dict(self, app_ctx):
        f = _file(b"data", "test.txt")
        result = validate_file(f)
        assert isinstance(result, dict)
        assert "valid" in result

    def test_sanitize_filename_convenience(self):
        result = sanitize_filename("document.pdf")
        assert result == "document.pdf"

    def test_sanitize_filename_traversal(self):
        result = sanitize_filename("../../etc/passwd")
        assert ".." not in result

    def test_validator_instance_exists(self):
        assert isinstance(validator, AdvancedValidator)
