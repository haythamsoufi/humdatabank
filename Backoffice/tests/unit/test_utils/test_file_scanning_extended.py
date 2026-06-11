"""Extended tests for app/utils/file_scanning.py – targets 100 % coverage.

Complements the basic tests in test_file_scanning.py by exercising every branch
of FileScanner: ClamAV, VirusTotal, cloud scanner, helper methods, and the
is_file_clean convenience wrapper.
"""
import io
import os
import subprocess

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from flask import Flask
from werkzeug.datastructures import FileStorage

from app.utils.file_scanning import (
    FileScanError,
    FileScanner,
    scan_file_for_viruses,
    is_file_clean,
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


def _build_file(name: str = "test.txt", data: bytes = b"data") -> FileStorage:
    return FileStorage(stream=io.BytesIO(data), filename=name, content_type="text/plain")


# ---------------------------------------------------------------------------
# _should_fail_open
# ---------------------------------------------------------------------------

class TestShouldFailOpen:
    def test_explicit_true_lower(self, app_ctx):
        app_ctx.config["FILE_SCANNER_FAIL_OPEN"] = "true"
        assert FileScanner._should_fail_open() is True

    def test_explicit_one(self, app_ctx):
        app_ctx.config["FILE_SCANNER_FAIL_OPEN"] = "1"
        assert FileScanner._should_fail_open() is True

    def test_explicit_yes(self, app_ctx):
        app_ctx.config["FILE_SCANNER_FAIL_OPEN"] = "yes"
        assert FileScanner._should_fail_open() is True

    def test_explicit_false(self, app_ctx):
        app_ctx.config["FILE_SCANNER_FAIL_OPEN"] = "false"
        assert FileScanner._should_fail_open() is False

    def test_explicit_zero(self, app_ctx):
        app_ctx.config["FILE_SCANNER_FAIL_OPEN"] = "0"
        assert FileScanner._should_fail_open() is False

    def test_explicit_no(self, app_ctx):
        app_ctx.config["FILE_SCANNER_FAIL_OPEN"] = "no"
        assert FileScanner._should_fail_open() is False

    def test_explicit_boolean_true(self, app_ctx):
        app_ctx.config["FILE_SCANNER_FAIL_OPEN"] = True
        assert FileScanner._should_fail_open() is True

    def test_no_explicit_debug_true(self, app_ctx):
        app_ctx.config.pop("FILE_SCANNER_FAIL_OPEN", None)
        app_ctx.config["DEBUG"] = True
        assert FileScanner._should_fail_open() is True

    def test_no_explicit_debug_false(self, app_ctx):
        app_ctx.config.pop("FILE_SCANNER_FAIL_OPEN", None)
        app_ctx.config["DEBUG"] = False
        assert FileScanner._should_fail_open() is False

    def test_no_explicit_no_debug_key(self, app_ctx):
        app_ctx.config.pop("FILE_SCANNER_FAIL_OPEN", None)
        app_ctx.config.pop("DEBUG", None)
        assert FileScanner._should_fail_open() is False


# ---------------------------------------------------------------------------
# _handle_failure
# ---------------------------------------------------------------------------

class TestHandleFailure:
    def test_fail_open_returns_dict(self):
        result = FileScanner._handle_failure("clamav", "some error", fail_open=True)
        assert result["clean"] is False
        assert result["fail_open"] is True
        assert result["scanner"] == "clamav"
        assert result["error"] == "some error"

    def test_fail_closed_raises(self):
        with pytest.raises(FileScanError):
            FileScanner._handle_failure("clamav", "some error", fail_open=False)

    def test_fail_open_infected_is_none(self):
        result = FileScanner._handle_failure("cloud", "msg", fail_open=True)
        assert result["infected"] is None
        assert result["threats"] == []


# ---------------------------------------------------------------------------
# _get_file_length
# ---------------------------------------------------------------------------

class TestGetFileLength:
    def test_content_length_attr(self):
        f = MagicMock()
        f.content_length = 1024
        assert FileScanner._get_file_length(f) == 1024

    def test_stream_seek_tell(self):
        # FileStorage.content_length defaults to 0 (not None), so we use a plain
        # mock without that attribute to hit the stream.tell() fallback path.
        f = MagicMock(spec=[])  # no content_length attribute → getattr returns None
        f.stream = io.BytesIO(b"x" * 50)
        assert FileScanner._get_file_length(f) == 50

    def test_stream_tell_raises_returns_none(self):
        f = MagicMock()
        f.content_length = None
        f.stream = MagicMock()
        f.stream.tell.side_effect = OSError("broken stream")
        result = FileScanner._get_file_length(f)
        assert result is None

    def test_no_stream_returns_none(self):
        f = MagicMock(spec=[])
        result = FileScanner._get_file_length(f)
        assert result is None


# ---------------------------------------------------------------------------
# scan_file – basic dispatch
# ---------------------------------------------------------------------------

class TestScanFileDispatch:
    def test_unknown_scanner_fail_open(self, app_ctx):
        app_ctx.config["FILE_SCANNER_TYPE"] = "unknown_scanner"
        app_ctx.config["FILE_SCANNER_FAIL_OPEN"] = True
        result = FileScanner.scan_file(_build_file())
        assert result["fail_open"] is True
        assert "unknown_scanner" in result["error"].lower() or "Unknown" in result["error"]

    def test_unknown_scanner_fail_closed(self, app_ctx):
        app_ctx.config["FILE_SCANNER_TYPE"] = "unknown_scanner"
        app_ctx.config["FILE_SCANNER_FAIL_OPEN"] = False
        with pytest.raises(FileScanError):
            FileScanner.scan_file(_build_file())

    def test_stream_rewound_after_scan(self, app_ctx):
        app_ctx.config["FILE_SCANNER_TYPE"] = "none"
        app_ctx.config["FILE_SCANNER_FAIL_OPEN"] = True
        f = _build_file()
        f.stream.read()  # advance
        try:
            FileScanner.scan_file(f)
        except FileScanError:
            pass
        assert f.stream.tell() == 0

    def test_stream_rewind_exception_suppressed(self, app_ctx):
        """Failing to rewind the stream should not bubble up."""
        app_ctx.config["FILE_SCANNER_TYPE"] = "none"
        app_ctx.config["FILE_SCANNER_FAIL_OPEN"] = True
        f = _build_file()
        f.stream = MagicMock()
        f.stream.seek.side_effect = OSError("broken")
        result = FileScanner.scan_file(f)
        assert result["fail_open"] is True


# ---------------------------------------------------------------------------
# _scan_with_clamav
# ---------------------------------------------------------------------------

class TestScanWithClamav:
    @pytest.fixture()
    def clamav_ctx(self, app_ctx):
        app_ctx.config["FILE_SCANNER_TYPE"] = "clamav"
        app_ctx.config["FILE_SCANNER_FAIL_OPEN"] = True
        app_ctx.config["TEMP_UPLOAD_DIR"] = "/tmp"
        return app_ctx

    def _run(self, returncode: int, stdout: str = "", stderr: str = ""):
        mock_result = MagicMock()
        mock_result.returncode = returncode
        mock_result.stdout = stdout
        mock_result.stderr = stderr
        return mock_result

    def test_clean_file(self, clamav_ctx, tmp_path):
        clamav_ctx.config["TEMP_UPLOAD_DIR"] = str(tmp_path)
        with patch("subprocess.run", return_value=self._run(0)):
            result = FileScanner._scan_with_clamav(_build_file(), fail_open=True)
        assert result["clean"] is True
        assert result["infected"] is False
        assert result["scanner"] == "clamav"

    def test_infected_file_with_colon_in_stdout(self, clamav_ctx, tmp_path):
        clamav_ctx.config["TEMP_UPLOAD_DIR"] = str(tmp_path)
        with patch("subprocess.run", return_value=self._run(1, stdout="/tmp/file.txt: Eicar.Test.Virus FOUND")):
            result = FileScanner._scan_with_clamav(_build_file(), fail_open=True)
        assert result["clean"] is False
        assert result["infected"] is True
        assert "Eicar.Test.Virus FOUND" in result["threats"]

    def test_infected_file_no_colon_in_stdout(self, clamav_ctx, tmp_path):
        clamav_ctx.config["TEMP_UPLOAD_DIR"] = str(tmp_path)
        with patch("subprocess.run", return_value=self._run(1, stdout="FOUND")):
            result = FileScanner._scan_with_clamav(_build_file(), fail_open=True)
        assert result["infected"] is True
        assert result["threats"] == ["Unknown threat"]

    def test_error_returncode_fail_open(self, clamav_ctx, tmp_path):
        clamav_ctx.config["TEMP_UPLOAD_DIR"] = str(tmp_path)
        with patch("subprocess.run", return_value=self._run(2, stderr="some error")):
            result = FileScanner._scan_with_clamav(_build_file(), fail_open=True)
        assert result["fail_open"] is True

    def test_error_returncode_fail_closed(self, clamav_ctx, tmp_path):
        clamav_ctx.config["TEMP_UPLOAD_DIR"] = str(tmp_path)
        with patch("subprocess.run", return_value=self._run(2)):
            with pytest.raises(FileScanError):
                FileScanner._scan_with_clamav(_build_file(), fail_open=False)

    def test_clamav_not_found_fail_open(self, clamav_ctx, tmp_path):
        clamav_ctx.config["TEMP_UPLOAD_DIR"] = str(tmp_path)
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            result = FileScanner._scan_with_clamav(_build_file(), fail_open=True)
        assert result["fail_open"] is True
        assert "not installed" in result["error"]

    def test_clamav_not_found_fail_closed(self, clamav_ctx, tmp_path):
        clamav_ctx.config["TEMP_UPLOAD_DIR"] = str(tmp_path)
        with patch("subprocess.run", side_effect=FileNotFoundError()):
            with pytest.raises(FileScanError):
                FileScanner._scan_with_clamav(_build_file(), fail_open=False)

    def test_clamav_timeout_fail_open(self, clamav_ctx, tmp_path):
        clamav_ctx.config["TEMP_UPLOAD_DIR"] = str(tmp_path)
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("clam", 30)):
            result = FileScanner._scan_with_clamav(_build_file(), fail_open=True)
        assert result["fail_open"] is True
        assert "timed out" in result["error"]

    def test_clamav_generic_exception_fail_open(self, clamav_ctx, tmp_path):
        clamav_ctx.config["TEMP_UPLOAD_DIR"] = str(tmp_path)
        with patch("subprocess.run", side_effect=RuntimeError("unexpected")):
            result = FileScanner._scan_with_clamav(_build_file(), fail_open=True)
        assert result["fail_open"] is True

    def test_temp_file_cleaned_up(self, clamav_ctx, tmp_path):
        clamav_ctx.config["TEMP_UPLOAD_DIR"] = str(tmp_path)
        files_after = []
        original_run = subprocess.run

        def run_and_capture(*args, **kwargs):
            files_after.extend(list(tmp_path.iterdir()))
            return self._run(0)

        with patch("subprocess.run", side_effect=run_and_capture):
            FileScanner._scan_with_clamav(_build_file(), fail_open=True)

        # Temp file should have been cleaned up
        remaining = list(tmp_path.iterdir())
        assert len(remaining) == 0

    def test_scan_dispatches_to_clamav(self, clamav_ctx, tmp_path):
        clamav_ctx.config["TEMP_UPLOAD_DIR"] = str(tmp_path)
        with patch("subprocess.run", return_value=self._run(0)):
            result = FileScanner.scan_file(_build_file())
        assert result["scanner"] == "clamav"


# ---------------------------------------------------------------------------
# _scan_with_virustotal
# ---------------------------------------------------------------------------

class TestScanWithVirusTotal:
    @pytest.fixture()
    def vt_ctx(self, app_ctx):
        app_ctx.config["FILE_SCANNER_TYPE"] = "virustotal"
        app_ctx.config["FILE_SCANNER_FAIL_OPEN"] = True
        return app_ctx

    def test_no_api_key_fail_open(self, vt_ctx):
        vt_ctx.config.pop("VIRUSTOTAL_API_KEY", None)
        result = FileScanner._scan_with_virustotal(_build_file(), fail_open=True)
        assert result["fail_open"] is True
        assert "API key" in result["error"]

    def test_no_api_key_fail_closed(self, vt_ctx):
        vt_ctx.config.pop("VIRUSTOTAL_API_KEY", None)
        with pytest.raises(FileScanError):
            FileScanner._scan_with_virustotal(_build_file(), fail_open=False)

    def test_clean_scan(self, vt_ctx):
        vt_ctx.config["VIRUSTOTAL_API_KEY"] = "test-key"
        scan_resp = MagicMock()
        scan_resp.json.return_value = {"response_code": 1, "resource": "abc123"}
        scan_resp.raise_for_status = MagicMock()

        report_resp = MagicMock()
        report_resp.status_code = 200
        report_resp.json.return_value = {"positives": 0, "scans": {}}

        with patch("requests.post", return_value=scan_resp):
            with patch("requests.get", return_value=report_resp):
                result = FileScanner._scan_with_virustotal(_build_file(), fail_open=True)
        assert result["clean"] is True
        assert result["infected"] is False

    def test_infected_scan(self, vt_ctx):
        vt_ctx.config["VIRUSTOTAL_API_KEY"] = "test-key"
        scan_resp = MagicMock()
        scan_resp.json.return_value = {"response_code": 1, "resource": "abc123"}
        scan_resp.raise_for_status = MagicMock()

        report_resp = MagicMock()
        report_resp.status_code = 200
        report_resp.json.return_value = {
            "positives": 2,
            "scans": {
                "AntivirusA": {"detected": True, "result": "Trojan.X"},
                "AntivirusB": {"detected": False, "result": None},
            },
        }

        with patch("requests.post", return_value=scan_resp):
            with patch("requests.get", return_value=report_resp):
                result = FileScanner._scan_with_virustotal(_build_file(), fail_open=True)
        assert result["clean"] is False
        assert result["infected"] is True
        assert "AntivirusA" in result["threats"]

    def test_report_non_200_triggers_failure(self, vt_ctx):
        vt_ctx.config["VIRUSTOTAL_API_KEY"] = "test-key"
        scan_resp = MagicMock()
        scan_resp.json.return_value = {"response_code": 1, "resource": "abc123"}
        scan_resp.raise_for_status = MagicMock()

        report_resp = MagicMock()
        report_resp.status_code = 503

        with patch("requests.post", return_value=scan_resp):
            with patch("requests.get", return_value=report_resp):
                result = FileScanner._scan_with_virustotal(_build_file(), fail_open=True)
        assert result["fail_open"] is True

    def test_bad_response_code_triggers_failure(self, vt_ctx):
        vt_ctx.config["VIRUSTOTAL_API_KEY"] = "test-key"
        scan_resp = MagicMock()
        scan_resp.json.return_value = {"response_code": 0}
        scan_resp.raise_for_status = MagicMock()

        with patch("requests.post", return_value=scan_resp):
            result = FileScanner._scan_with_virustotal(_build_file(), fail_open=True)
        assert result["fail_open"] is True

    def test_exception_fail_open(self, vt_ctx):
        vt_ctx.config["VIRUSTOTAL_API_KEY"] = "test-key"
        with patch("requests.post", side_effect=Exception("network err")):
            result = FileScanner._scan_with_virustotal(_build_file(), fail_open=True)
        assert result["fail_open"] is True

    def test_dispatches_via_scan_file(self, vt_ctx):
        vt_ctx.config["VIRUSTOTAL_API_KEY"] = "test-key"
        scan_resp = MagicMock()
        scan_resp.json.return_value = {"response_code": 1, "resource": "r"}
        scan_resp.raise_for_status = MagicMock()
        report_resp = MagicMock()
        report_resp.status_code = 200
        report_resp.json.return_value = {"positives": 0}
        with patch("requests.post", return_value=scan_resp):
            with patch("requests.get", return_value=report_resp):
                result = FileScanner.scan_file(_build_file())
        assert result["scanner"] == "virustotal"


# ---------------------------------------------------------------------------
# _scan_with_cloud_service
# ---------------------------------------------------------------------------

class TestScanWithCloudService:
    @pytest.fixture()
    def cloud_ctx(self, app_ctx):
        app_ctx.config["FILE_SCANNER_TYPE"] = "cloud"
        app_ctx.config["FILE_SCANNER_FAIL_OPEN"] = True
        app_ctx.config["CLOUD_SCANNER_URL"] = "https://scanner.example.com/scan"
        app_ctx.config["CLOUD_SCANNER_API_KEY"] = "cloud-key"
        return app_ctx

    def _make_response(self, json_data=None, raise_status=False):
        import requests as _req
        resp = MagicMock()
        if json_data is not None:
            resp.json.return_value = json_data
        else:
            resp.json.side_effect = ValueError("invalid JSON")
        if raise_status:
            # Must raise requests.HTTPError (subclass of RequestException) so
            # the except clause in _scan_with_cloud_service catches it.
            resp.raise_for_status.side_effect = _req.exceptions.HTTPError("HTTP 500")
        else:
            resp.raise_for_status = MagicMock()
        return resp

    def test_not_configured_no_url_fail_open(self, app_ctx):
        app_ctx.config.pop("CLOUD_SCANNER_URL", None)
        app_ctx.config.pop("CLOUD_SCANNER_API_KEY", None)
        result = FileScanner._scan_with_cloud_service(_build_file(), fail_open=True)
        assert result["fail_open"] is True
        assert "not configured" in result["error"]

    def test_not_configured_no_key_fail_open(self, app_ctx):
        app_ctx.config["CLOUD_SCANNER_URL"] = "https://scanner.example.com/scan"
        app_ctx.config.pop("CLOUD_SCANNER_API_KEY", None)
        result = FileScanner._scan_with_cloud_service(_build_file(), fail_open=True)
        assert result["fail_open"] is True

    def test_file_too_large(self, cloud_ctx):
        cloud_ctx.config["CLOUD_SCANNER_MAX_BYTES"] = 100
        # FileStorage.content_length defaults to 0; mock _get_file_length
        # to return a size that exceeds the limit.
        f = _build_file(data=b"x" * 200)
        with patch.object(FileScanner, "_get_file_length", return_value=200):
            result = FileScanner._scan_with_cloud_service(f, fail_open=True)
        assert result["fail_open"] is True
        assert "size limit" in result["error"]

    def test_clean_response_with_flags(self, cloud_ctx):
        resp = self._make_response({"clean": True, "infected": False, "threats": []})
        with patch("requests.post", return_value=resp):
            result = FileScanner._scan_with_cloud_service(_build_file(), fail_open=True)
        assert result["clean"] is True
        assert result["infected"] is False

    def test_infected_response_with_flags(self, cloud_ctx):
        resp = self._make_response({"clean": False, "infected": True, "threats": ["Trojan.X"]})
        with patch("requests.post", return_value=resp):
            result = FileScanner._scan_with_cloud_service(_build_file(), fail_open=True)
        assert result["clean"] is False
        assert result["infected"] is True
        assert "Trojan.X" in result["threats"]

    def test_status_clean(self, cloud_ctx):
        resp = self._make_response({"status": "clean"})
        with patch("requests.post", return_value=resp):
            result = FileScanner._scan_with_cloud_service(_build_file(), fail_open=True)
        assert result["clean"] is True

    def test_status_ok(self, cloud_ctx):
        resp = self._make_response({"status": "ok"})
        with patch("requests.post", return_value=resp):
            result = FileScanner._scan_with_cloud_service(_build_file(), fail_open=True)
        assert result["clean"] is True

    def test_status_infected(self, cloud_ctx):
        resp = self._make_response({"status": "infected"})
        with patch("requests.post", return_value=resp):
            result = FileScanner._scan_with_cloud_service(_build_file(), fail_open=True)
        assert result["infected"] is True

    def test_status_dirty(self, cloud_ctx):
        resp = self._make_response({"status": "dirty"})
        with patch("requests.post", return_value=resp):
            result = FileScanner._scan_with_cloud_service(_build_file(), fail_open=True)
        assert result["infected"] is True

    def test_status_malicious(self, cloud_ctx):
        resp = self._make_response({"status": "malicious"})
        with patch("requests.post", return_value=resp):
            result = FileScanner._scan_with_cloud_service(_build_file(), fail_open=True)
        assert result["infected"] is True

    def test_status_unknown_fail_open(self, cloud_ctx):
        resp = self._make_response({"status": "pending"})
        with patch("requests.post", return_value=resp):
            result = FileScanner._scan_with_cloud_service(_build_file(), fail_open=True)
        assert result["fail_open"] is True

    def test_threats_non_list_wrapped(self, cloud_ctx):
        resp = self._make_response({"clean": False, "infected": True, "threats": "Trojan.X"})
        with patch("requests.post", return_value=resp):
            result = FileScanner._scan_with_cloud_service(_build_file(), fail_open=True)
        assert isinstance(result["threats"], list)
        assert "Trojan.X" in result["threats"]

    def test_invalid_json_response_fail_open(self, cloud_ctx):
        resp = self._make_response(json_data=None)  # json() raises ValueError
        with patch("requests.post", return_value=resp):
            result = FileScanner._scan_with_cloud_service(_build_file(), fail_open=True)
        assert result["fail_open"] is True
        assert "invalid JSON" in result["error"]

    def test_timeout_fail_open(self, cloud_ctx):
        import requests as req
        with patch("requests.post", side_effect=req.exceptions.Timeout()):
            result = FileScanner._scan_with_cloud_service(_build_file(), fail_open=True)
        assert result["fail_open"] is True
        assert "timed out" in result["error"]

    def test_request_exception_fail_open(self, cloud_ctx):
        import requests as req
        with patch("requests.post", side_effect=req.exceptions.ConnectionError("refused")):
            result = FileScanner._scan_with_cloud_service(_build_file(), fail_open=True)
        assert result["fail_open"] is True

    def test_http_error_fail_open(self, cloud_ctx):
        resp = self._make_response({"clean": True}, raise_status=True)
        with patch("requests.post", return_value=resp):
            result = FileScanner._scan_with_cloud_service(_build_file(), fail_open=True)
        assert result["fail_open"] is True

    def test_custom_auth_header(self, cloud_ctx):
        cloud_ctx.config["CLOUD_SCANNER_AUTH_HEADER"] = "X-Api-Key"
        cloud_ctx.config["CLOUD_SCANNER_AUTH_SCHEME"] = ""
        resp = self._make_response({"clean": True, "infected": False})
        captured = {}
        def capture_call(**kwargs):
            captured["headers"] = kwargs.get("headers", {})
            return resp
        with patch("requests.post", side_effect=lambda *a, **kw: capture_call(**kw)):
            FileScanner._scan_with_cloud_service(_build_file(), fail_open=True)
        assert "X-Api-Key" in captured["headers"]
        assert captured["headers"]["X-Api-Key"] == "cloud-key"

    def test_no_auth_header_skips_auth(self, cloud_ctx):
        cloud_ctx.config["CLOUD_SCANNER_AUTH_HEADER"] = ""
        resp = self._make_response({"clean": True, "infected": False})
        with patch("requests.post", return_value=resp):
            result = FileScanner._scan_with_cloud_service(_build_file(), fail_open=True)
        assert result["clean"] is True

    def test_extra_headers_merged(self, cloud_ctx):
        cloud_ctx.config["CLOUD_SCANNER_EXTRA_HEADERS"] = {"X-Custom": "val"}
        resp = self._make_response({"clean": True, "infected": False})
        captured = {}
        def capture_call(**kwargs):
            captured["headers"] = kwargs.get("headers", {})
            return resp
        with patch("requests.post", side_effect=lambda *a, **kw: capture_call(**kw)):
            FileScanner._scan_with_cloud_service(_build_file(), fail_open=True)
        assert "X-Custom" in captured["headers"]

    def test_dispatches_via_scan_file(self, cloud_ctx):
        resp = self._make_response({"clean": True, "infected": False})
        with patch("requests.post", return_value=resp):
            result = FileScanner.scan_file(_build_file())
        assert result["scanner"] == "cloud"

    def test_size_check_skipped_when_no_max(self, cloud_ctx):
        cloud_ctx.config.pop("CLOUD_SCANNER_MAX_BYTES", None)
        cloud_ctx.config.pop("MAX_CONTENT_LENGTH", None)
        resp = self._make_response({"clean": True, "infected": False})
        with patch("requests.post", return_value=resp):
            result = FileScanner._scan_with_cloud_service(_build_file(), fail_open=True)
        assert result["clean"] is True

    def test_size_check_skipped_when_file_size_unknown(self, cloud_ctx):
        cloud_ctx.config["CLOUD_SCANNER_MAX_BYTES"] = 10
        f = MagicMock(spec=FileStorage)
        f.content_length = None
        f.stream = MagicMock()
        f.stream.tell.side_effect = OSError("no tell")
        f.filename = "file.txt"
        f.content_type = "text/plain"
        resp = self._make_response({"clean": True, "infected": False})
        with patch("requests.post", return_value=resp):
            result = FileScanner._scan_with_cloud_service(f, fail_open=True)
        assert result["clean"] is True


# ---------------------------------------------------------------------------
# is_file_clean
# ---------------------------------------------------------------------------

class TestIsFileClean:
    def test_clean_file(self, app_ctx):
        app_ctx.config["FILE_SCANNER_TYPE"] = "none"
        app_ctx.config["FILE_SCANNER_FAIL_OPEN"] = True
        f = _build_file()
        result = is_file_clean(f)
        # With none scanner + fail_open: clean is False
        assert result is False

    def test_raises_on_fail_closed(self, app_ctx):
        app_ctx.config["FILE_SCANNER_TYPE"] = "none"
        app_ctx.config["FILE_SCANNER_FAIL_OPEN"] = False
        with pytest.raises(FileScanError):
            is_file_clean(_build_file())

    def test_returns_true_when_clean(self, app_ctx):
        app_ctx.config["FILE_SCANNER_TYPE"] = "clamav"
        app_ctx.config["FILE_SCANNER_FAIL_OPEN"] = True
        app_ctx.config["TEMP_UPLOAD_DIR"] = "/tmp"
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_result.stderr = ""
        with patch("subprocess.run", return_value=mock_result):
            result = is_file_clean(_build_file())
        assert result is True


# ---------------------------------------------------------------------------
# scan_file_for_viruses (convenience wrapper)
# ---------------------------------------------------------------------------

class TestScanFileForViruses:
    def test_delegates_to_file_scanner(self, app_ctx):
        app_ctx.config["FILE_SCANNER_TYPE"] = "none"
        app_ctx.config["FILE_SCANNER_FAIL_OPEN"] = True
        result = scan_file_for_viruses(_build_file())
        assert "scanner" in result
        assert result["scanner"] == "none"
