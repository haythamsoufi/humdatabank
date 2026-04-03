# File upload virus scanning utilities
"""
File scanning utilities for virus/malware detection on uploaded files.

Supports multiple scanning backends:
- ClamAV (local installation)
- Cloud-based services (AWS, VirusTotal API)
- External service integration
"""

import os
import subprocess
import requests
from typing import Dict, Optional
from flask import current_app
from werkzeug.datastructures import FileStorage
import logging
from contextlib import suppress

logger = logging.getLogger(__name__)


class FileScanError(RuntimeError):
    """Raised when a file cannot be scanned and fail-open is disabled."""


class FileScanner:
    """File scanner interface for virus/malware detection."""

    @staticmethod
    def _should_fail_open() -> bool:
        """
        Determine whether scanning failures should fail-open.

        Defaults to True in DEBUG mode unless explicitly overridden via
        FILE_SCANNER_FAIL_OPEN.
        """
        cfg = current_app.config
        default_fail_open = bool(cfg.get('DEBUG', False))
        return bool(cfg.get('FILE_SCANNER_FAIL_OPEN', default_fail_open))

    @staticmethod
    def _handle_failure(scanner: str, message: str, fail_open: bool) -> Dict[str, any]:
        """Centralized handler for scanner failures respecting fail-open policy."""
        if fail_open:
            logger.warning("File scanner fail-open (%s): %s", scanner, message)
            return {
                'clean': False,
                'infected': None,
                'threats': [],
                'scanner': scanner,
                'error': message,
                'fail_open': True
            }
        raise FileScanError(message)

    @staticmethod
    def _get_file_length(file_storage: FileStorage) -> Optional[int]:
        """Return the size of the uploaded file in bytes, if determinable."""
        length = getattr(file_storage, 'content_length', None)
        if length is not None:
            return length
        stream = getattr(file_storage, 'stream', None)
        if stream and hasattr(stream, 'tell'):
            try:
                current_pos = stream.tell()
                stream.seek(0, os.SEEK_END)
                length = stream.tell()
                stream.seek(current_pos)
                return length
            except Exception as e:
                logger.debug("Could not determine uploaded file length: %s", e, exc_info=True)
                return None
        return None

    @staticmethod
    def scan_file(file_storage: FileStorage) -> Dict[str, any]:
        """
        Scan a file for viruses/malware.

        Args:
            file_storage: FileStorage object to scan

        Returns:
            Dict with scan results:
            {
                'clean': bool,
                'infected': bool,
                'threats': list,
                'scanner': str,
                'error': str or None
            }
        """
        scanner_type = current_app.config.get('FILE_SCANNER_TYPE', 'none').lower()
        fail_open = FileScanner._should_fail_open()

        try:
            if scanner_type == 'none' or not scanner_type:
                # When scanner is explicitly disabled, always fail-open (allow uploads)
                # There's no security benefit to blocking uploads when scanning is disabled
                return FileScanner._handle_failure('none', 'File scanner disabled', True)
            if scanner_type == 'clamav':
                return FileScanner._scan_with_clamav(file_storage, fail_open)
            if scanner_type == 'virustotal':
                return FileScanner._scan_with_virustotal(file_storage, fail_open)
            if scanner_type == 'cloud':
                return FileScanner._scan_with_cloud_service(file_storage, fail_open)

            logger.warning(f"Unknown file scanner type: {scanner_type}")
            return FileScanner._handle_failure('unknown', f'Unknown scanner type: {scanner_type}', fail_open)
        finally:
            try:
                file_storage.stream.seek(0)
            except Exception as e:
                logger.debug("Failed to rewind upload stream after scanning: %s", e, exc_info=True)

    @staticmethod
    def _scan_with_clamav(file_storage: FileStorage, fail_open: bool) -> Dict[str, any]:
        """Scan file using ClamAV (local installation)."""
        try:
            # Save file temporarily for scanning
            import tempfile

            # Create temporary file
            temp_dir = current_app.config.get('TEMP_UPLOAD_DIR', '/tmp')
            os.makedirs(temp_dir, exist_ok=True)

            with tempfile.NamedTemporaryFile(delete=False, dir=temp_dir) as temp_file:
                file_storage.save(temp_file.name)
                temp_path = temp_file.name

            try:
                # Run ClamAV scan
                # Note: Requires 'clamdscan' or 'clamscan' to be installed
                clamdscan_path = current_app.config.get('CLAMAV_SCAN_PATH', 'clamdscan')

                result = subprocess.run(
                    [clamdscan_path, '--no-summary', temp_path],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                # ClamAV returns 0 if clean, 1 if infected, 2 if error
                if result.returncode == 0:
                    return {
                        'clean': True,
                        'infected': False,
                        'threats': [],
                        'scanner': 'clamav',
                        'error': None,
                        'fail_open': False
                    }
                elif result.returncode == 1:
                    # Extract threat name from output
                    threat = result.stdout.strip().split(':')[1].strip() if ':' in result.stdout else 'Unknown threat'
                    return {
                        'clean': False,
                        'infected': True,
                        'threats': [threat],
                        'scanner': 'clamav',
                        'error': None,
                        'fail_open': False
                    }
                else:
                    return FileScanner._handle_failure('clamav', f'ClamAV scan error: {result.stderr}', fail_open)

            finally:
                # Clean up temporary file
                if os.path.exists(temp_path):
                    os.unlink(temp_path)

        except FileNotFoundError:
            return FileScanner._handle_failure('clamav', 'ClamAV not installed or not found in PATH', fail_open)
        except subprocess.TimeoutExpired:
            return FileScanner._handle_failure('clamav', 'ClamAV scan timed out', fail_open)
        except Exception as e:
            logger.error(f"ClamAV scan error: {e}")
            return FileScanner._handle_failure('clamav', 'Scan failed.', fail_open)

    @staticmethod
    def _scan_with_virustotal(file_storage: FileStorage, fail_open: bool) -> Dict[str, any]:
        """Scan file using VirusTotal API."""
        try:
            api_key = current_app.config.get('VIRUSTOTAL_API_KEY')
            if not api_key:
                return FileScanner._handle_failure('virustotal', 'VirusTotal API key not configured', fail_open)

            # Upload file to VirusTotal
            url = 'https://www.virustotal.com/vtapi/v2/file/scan'
            files = {'file': (file_storage.filename, file_storage.stream, file_storage.content_type)}
            params = {'apikey': api_key}

            file_storage.stream.seek(0)  # Reset stream position

            response = requests.post(url, files=files, params=params, timeout=30)
            response.raise_for_status()

            scan_data = response.json()

            if scan_data.get('response_code') == 1:
                # Scan submitted successfully, get report
                resource = scan_data.get('resource')

                # Poll for results (in production, use async task)
                report_url = 'https://www.virustotal.com/vtapi/v2/file/report'
                report_response = requests.get(
                    report_url,
                    params={'apikey': api_key, 'resource': resource},
                    timeout=30
                )

                if report_response.status_code == 200:
                    report = report_response.json()
                    positives = report.get('positives', 0)

                    if positives > 0:
                        scans = report.get('scans', {})
                        threats = [name for name, result in scans.items() if result.get('detected')]

                        return {
                            'clean': False,
                            'infected': True,
                            'threats': threats,
                            'scanner': 'virustotal',
                            'error': None,
                            'fail_open': False
                        }
                    else:
                        return {
                            'clean': True,
                            'infected': False,
                            'threats': [],
                            'scanner': 'virustotal',
                            'error': None,
                            'fail_open': False
                        }

            return FileScanner._handle_failure('virustotal', 'VirusTotal API error', fail_open)

        except Exception as e:
            logger.error(f"VirusTotal scan error: {e}")
            return FileScanner._handle_failure('virustotal', 'Scan failed.', fail_open)

    @staticmethod
    def _scan_with_cloud_service(file_storage: FileStorage, fail_open: bool) -> Dict[str, any]:
        """Scan file using cloud-based scanning service."""
        cloud_service_url = current_app.config.get('CLOUD_SCANNER_URL')
        api_key = current_app.config.get('CLOUD_SCANNER_API_KEY')

        if not cloud_service_url or not api_key:
            return FileScanner._handle_failure('cloud', 'Cloud scanner not configured', fail_open)

        max_bytes = current_app.config.get('CLOUD_SCANNER_MAX_BYTES') or current_app.config.get('MAX_CONTENT_LENGTH')
        file_size = FileScanner._get_file_length(file_storage)
        if max_bytes and file_size and file_size > max_bytes:
            return FileScanner._handle_failure(
                'cloud',
                f'File exceeds cloud scanner size limit ({file_size} bytes > {max_bytes} bytes)',
                fail_open
            )

        timeout = current_app.config.get('CLOUD_SCANNER_TIMEOUT', 30)
        auth_header = current_app.config.get('CLOUD_SCANNER_AUTH_HEADER', 'Authorization')
        auth_scheme = current_app.config.get('CLOUD_SCANNER_AUTH_SCHEME', 'Bearer')
        extra_headers = current_app.config.get('CLOUD_SCANNER_EXTRA_HEADERS') or {}

        headers = dict(extra_headers)
        if auth_header:
            headers[auth_header] = f"{auth_scheme} {api_key}".strip() if auth_scheme else api_key

        payload = {
            'filename': file_storage.filename or 'upload.bin',
            'content_type': file_storage.content_type or 'application/octet-stream'
        }

        file_storage.stream.seek(0)
        files = {
            'file': (
                file_storage.filename or 'upload.bin',
                file_storage.stream,
                file_storage.content_type or 'application/octet-stream'
            )
        }

        try:
            response = requests.post(
                cloud_service_url,
                data=payload,
                files=files,
                headers=headers,
                timeout=timeout
            )
            response.raise_for_status()
        except requests.exceptions.Timeout:
            return FileScanner._handle_failure('cloud', 'Cloud scanner request timed out', fail_open)
        except requests.exceptions.RequestException as exc:
            logger.error(f"Cloud scanner request error: {exc}", exc_info=True)
            return FileScanner._handle_failure('cloud', f'Cloud scanner request failed: {exc}', fail_open)

        try:
            result = response.json()
        except ValueError:
            return FileScanner._handle_failure('cloud', 'Cloud scanner returned invalid JSON', fail_open)

        clean_flag = result.get('clean')
        infected_flag = result.get('infected')

        if clean_flag is None and infected_flag is None:
            status = (result.get('status') or '').lower()
            if status in ('clean', 'ok'):
                clean_flag = True
                infected_flag = False
            elif status in ('infected', 'dirty', 'malicious'):
                clean_flag = False
                infected_flag = True
            else:
                return FileScanner._handle_failure('cloud', f'Cloud scanner returned unknown status: {status}', fail_open)

        threats = result.get('threats') or []
        if threats and not isinstance(threats, list):
            threats = [str(threats)]

        return {
            'clean': bool(clean_flag) and not bool(infected_flag),
            'infected': bool(infected_flag),
            'threats': threats,
            'scanner': 'cloud',
            'error': None,
            'fail_open': False
        }


def scan_file_for_viruses(file_storage: FileStorage) -> Dict[str, any]:
    """
    Convenience function to scan a file for viruses.

    Args:
        file_storage: FileStorage object to scan

    Returns:
        Dict with scan results

    Raises:
        FileScanError: When scanning fails and fail-open mode is disabled.
    """
    return FileScanner.scan_file(file_storage)


def is_file_clean(file_storage: FileStorage) -> bool:
    """
    Quick check if file is clean (no viruses detected).

    Args:
        file_storage: FileStorage object to check

    Returns:
        True if file is clean, False if infected (raises FileScanError on failure)
    """
    result = FileScanner.scan_file(file_storage)
    return result.get('clean', True)
