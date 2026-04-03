import io

import pytest
from flask import Flask
from werkzeug.datastructures import FileStorage

from app.utils.file_scanning import FileScanError, scan_file_for_viruses


@pytest.fixture()
def app_context():
    app = Flask(__name__)
    app.config['TESTING'] = True
    with app.app_context():
        yield app


def _build_file(name: str = 'test.txt') -> FileStorage:
    return FileStorage(stream=io.BytesIO(b'data'), filename=name, content_type='text/plain')


def test_scan_file_fail_closed_raises(app_context):
    app_context.config['FILE_SCANNER_TYPE'] = 'none'
    app_context.config['FILE_SCANNER_FAIL_OPEN'] = False

    with pytest.raises(FileScanError):
        scan_file_for_viruses(_build_file())


def test_scan_file_fail_open_allows(app_context):
    app_context.config['FILE_SCANNER_TYPE'] = 'none'
    app_context.config['FILE_SCANNER_FAIL_OPEN'] = True

    result = scan_file_for_viruses(_build_file())

    assert result['clean'] is False
    assert result['fail_open'] is True
    assert result['scanner'] == 'none'
    assert 'error' in result and result['error']
