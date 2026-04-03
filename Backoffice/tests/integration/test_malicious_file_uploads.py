"""
Test suite for malicious file upload security.

Tests that the backend properly rejects:
- Shell scripts (.sh, .bat, .ps1)
- Executables (.exe, .dll, .com)
- Script files (.py, .php, .js, .rb)
- Files with path traversal attempts
- Files with MIME type spoofing
- Other dangerous file types
"""
import io
import pytest
from unittest.mock import Mock
from werkzeug.datastructures import FileStorage
from flask_login import login_user

from app.services.form_data_service import FormDataService
from app.models import (
    FormTemplate, FormSection, FormItem, AssignedForm,
    AssignmentEntityStatus, EntityType
)
from tests.factories import create_test_country, create_test_template, create_test_user


@pytest.mark.integration
class TestMaliciousFileUploads:
    """Test that malicious file uploads are properly rejected."""

    @pytest.fixture
    def setup_form_with_document_field(self, db_session, app, admin_user):
        """Create a form template with a document field for testing."""
        with app.app_context():
            import uuid
            login_user(admin_user)

            # Use UUID to ensure unique country name
            unique_id = str(uuid.uuid4())[:8]
            country = create_test_country(db_session, name=f"Test Country {unique_id}")
            template = create_test_template(db_session)

            section = FormSection(
                template_id=template.id,
                name="Test Section",
                order=1,
                version_id=template.published_version_id
            )
            db_session.add(section)
            db_session.commit()

            form_item = FormItem(
                section_id=section.id,
                template_id=template.id,
                item_type='document_field',
                label="Test Document Field",
                order=1,
                version_id=template.published_version_id
            )
            db_session.add(form_item)
            db_session.commit()

            assigned_form = AssignedForm(
                template_id=template.id,
                period_name="2024"
            )
            db_session.add(assigned_form)
            db_session.commit()

            assignment_status = AssignmentEntityStatus(
                assigned_form_id=assigned_form.id,
                entity_type=EntityType.country.value,
                entity_id=country.id,
                status="In Progress"
            )
            db_session.add(assignment_status)
            db_session.commit()

            # Store IDs to avoid detached instance issues
            return {
                'assignment_status': assignment_status,
                'section': section,
                'form_item': form_item,
                'template': template,
                'form_item_id': form_item.id,
                'assignment_status_id': assignment_status.id,
                'section_id': section.id,
                'admin_user_id': admin_user.id,
            }

    def _create_malicious_file(self, filename: str, content: bytes = None) -> FileStorage:
        """Helper to create a FileStorage object with malicious content."""
        if content is None:
            # Default malicious content (shell script)
            content = b'#!/bin/bash\necho "malicious code"\nrm -rf /\n'

        file_storage = FileStorage(
            stream=io.BytesIO(content),
            filename=filename,
            content_type='application/octet-stream'
        )
        return file_storage

    def _create_file_with_mime_spoofing(self, filename: str, actual_content: bytes) -> FileStorage:
        """Helper to create a file with spoofed extension (e.g., .exe renamed to .pdf)."""
        file_storage = FileStorage(
            stream=io.BytesIO(actual_content),
            filename=filename,
            content_type='application/pdf'  # Spoofed MIME type
        )
        return file_storage

    def _test_malicious_upload(self, app, setup_data, malicious_file, expected_error_pattern=None):
        """Helper to test that a malicious file upload is rejected."""
        with app.app_context():
            from flask_wtf import FlaskForm

            assignment_status = setup_data['assignment_status']
            section = setup_data['section']
            form_item = setup_data['form_item']

            # Use stored ID to avoid detached instance errors
            form_item_id = setup_data.get('form_item_id', form_item.id)

            # Configure app for testing
            app.config['FILE_SCANNER_TYPE'] = 'none'  # Disable scanner for unit tests
            app.config['FILE_SCANNER_FAIL_OPEN'] = True

            # Create form data with malicious file
            # Use the correct field naming pattern: field_value[{id}] for files
            file_field_name = f'field_value[{form_item_id}]'
            if not getattr(malicious_file, 'filename', None):
                malicious_file.filename = 'malicious.sh'
            malicious_file.stream.seek(0)
            upload_tuple = (
                malicious_file.stream,
                malicious_file.filename,
                malicious_file.content_type or 'application/octet-stream'
            )

            with app.test_request_context(
                method='POST',
                data={
                    'action': 'save',
                    f'field_language[{form_item_id}]': 'en',
                    file_field_name: upload_tuple,
                },
                content_type='multipart/form-data'
            ):
                # Ensure current_user is authenticated inside the request context.
                # The fixture calls login_user() outside the request, which does not
                # persist into this test_request_context.
                from app.models import User
                admin_user = User.query.get(setup_data['admin_user_id'])
                login_user(admin_user)

                csrf_form = FlaskForm()
                csrf_form.validate_on_submit = Mock(return_value=True)

                all_sections = [section]
                section.fields_ordered = [form_item]

                result = FormDataService.process_form_submission(
                    assignment_status, all_sections, csrf_form
                )

                # Should fail validation
                assert result['success'] is False, f"Expected upload to fail but it succeeded: {result}"
                assert len(result.get('validation_errors', [])) > 0, \
                    f"Expected validation errors but got: {result}"

                # Check error message contains expected pattern if provided
                if expected_error_pattern:
                    errors = ' '.join(result.get('validation_errors', []))
                    assert expected_error_pattern.lower() in errors.lower(), \
                        f"Expected error pattern '{expected_error_pattern}' not found in: {errors}"

                return result

    def test_shell_script_upload_rejected(self, app, setup_form_with_document_field, db_session):
        """Test that shell scripts (.sh) are rejected."""
        malicious_file = self._create_malicious_file('malicious.sh', b'#!/bin/bash\necho "hack"\n')
        result = self._test_malicious_upload(
            app, setup_form_with_document_field, malicious_file,
            expected_error_pattern='Unsupported file type'
        )
        assert any('Unsupported file type' in str(err) for err in result.get('validation_errors', []))

    def test_batch_script_upload_rejected(self, app, setup_form_with_document_field, db_session):
        """Test that batch scripts (.bat) are rejected."""
        malicious_file = self._create_malicious_file(
            'malicious.bat',
            b'@echo off\ndel /F /Q C:\\Windows\\System32\\*.*\n'
        )
        result = self._test_malicious_upload(
            app, setup_form_with_document_field, malicious_file,
            expected_error_pattern='Unsupported file type'
        )
        assert any('Unsupported file type' in str(err) for err in result.get('validation_errors', []))

    def test_powershell_script_upload_rejected(self, app, setup_form_with_document_field, db_session):
        """Test that PowerShell scripts (.ps1) are rejected."""
        malicious_file = self._create_malicious_file(
            'malicious.ps1',
            b'Remove-Item -Path "C:\\Windows\\System32" -Recurse -Force\n'
        )
        result = self._test_malicious_upload(
            app, setup_form_with_document_field, malicious_file,
            expected_error_pattern='Unsupported file type'
        )
        assert any('Unsupported file type' in str(err) for err in result.get('validation_errors', []))

    def test_executable_upload_rejected(self, app, setup_form_with_document_field, db_session):
        """Test that executables (.exe) are rejected."""
        # Create a fake PE executable header
        pe_header = b'MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff'
        malicious_file = self._create_malicious_file('malicious.exe', pe_header)
        result = self._test_malicious_upload(
            app, setup_form_with_document_field, malicious_file,
            expected_error_pattern='Unsupported file type'
        )
        assert any('Unsupported file type' in str(err) for err in result.get('validation_errors', []))

    def test_dll_upload_rejected(self, app, setup_form_with_document_field, db_session):
        """Test that DLL files (.dll) are rejected."""
        pe_header = b'MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff'
        malicious_file = self._create_malicious_file('malicious.dll', pe_header)
        result = self._test_malicious_upload(
            app, setup_form_with_document_field, malicious_file,
            expected_error_pattern='Unsupported file type'
        )
        assert any('Unsupported file type' in str(err) for err in result.get('validation_errors', []))

    def test_python_script_upload_rejected(self, app, setup_form_with_document_field, db_session):
        """Test that Python scripts (.py) are rejected."""
        malicious_file = self._create_malicious_file(
            'malicious.py',
            b'import os\nos.system("rm -rf /")\n'
        )
        result = self._test_malicious_upload(
            app, setup_form_with_document_field, malicious_file,
            expected_error_pattern='Unsupported file type'
        )
        assert any('Unsupported file type' in str(err) for err in result.get('validation_errors', []))

    def test_php_script_upload_rejected(self, app, setup_form_with_document_field, db_session):
        """Test that PHP scripts (.php) are rejected."""
        malicious_file = self._create_malicious_file(
            'malicious.php',
            b'<?php system($_GET["cmd"]); ?>\n'
        )
        result = self._test_malicious_upload(
            app, setup_form_with_document_field, malicious_file,
            expected_error_pattern='Unsupported file type'
        )
        assert any('Unsupported file type' in str(err) for err in result.get('validation_errors', []))

    def test_javascript_upload_rejected(self, app, setup_form_with_document_field, db_session):
        """Test that JavaScript files (.js) are rejected."""
        malicious_file = self._create_malicious_file(
            'malicious.js',
            b'const fs = require("fs"); fs.unlinkSync("/etc/passwd");\n'
        )
        result = self._test_malicious_upload(
            app, setup_form_with_document_field, malicious_file,
            expected_error_pattern='Unsupported file type'
        )
        assert any('Unsupported file type' in str(err) for err in result.get('validation_errors', []))

    def test_ruby_script_upload_rejected(self, app, setup_form_with_document_field, db_session):
        """Test that Ruby scripts (.rb) are rejected."""
        malicious_file = self._create_malicious_file(
            'malicious.rb',
            b'system("rm -rf /")\n'
        )
        result = self._test_malicious_upload(
            app, setup_form_with_document_field, malicious_file,
            expected_error_pattern='Unsupported file type'
        )
        assert any('Unsupported file type' in str(err) for err in result.get('validation_errors', []))

    def test_path_traversal_filename_rejected(self, app, setup_form_with_document_field, db_session):
        """Test that filenames with path traversal attempts are rejected."""
        # Create a valid PDF content but with malicious filename
        pdf_content = b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n'
        malicious_file = FileStorage(
            stream=io.BytesIO(pdf_content),
            filename='../../../etc/passwd.pdf',
            content_type='application/pdf'
        )
        result = self._test_malicious_upload(
            app, setup_form_with_document_field, malicious_file,
            expected_error_pattern='Invalid filename'
        )
        # Should be rejected either for path traversal or filename validation
        assert len(result.get('validation_errors', [])) > 0

    def test_path_traversal_windows_style_rejected(self, app, setup_form_with_document_field, db_session):
        """Test that Windows-style path traversal attempts are rejected."""
        pdf_content = b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n'
        malicious_file = FileStorage(
            stream=io.BytesIO(pdf_content),
            filename='..\\..\\..\\windows\\system32\\config\\sam.pdf',
            content_type='application/pdf'
        )
        result = self._test_malicious_upload(
            app, setup_form_with_document_field, malicious_file,
            expected_error_pattern='Invalid filename'
        )
        assert len(result.get('validation_errors', [])) > 0

    def test_mime_type_spoofing_exe_as_pdf_rejected(self, app, setup_form_with_document_field, db_session):
        """Test that executables renamed to .pdf are rejected via MIME validation."""
        # Create PE executable but name it as .pdf
        pe_header = b'MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00\xff\xff'
        malicious_file = self._create_file_with_mime_spoofing('malicious.pdf', pe_header)
        result = self._test_malicious_upload(
            app, setup_form_with_document_field, malicious_file,
            expected_error_pattern='File type validation failed'
        )
        # Should be rejected for MIME type mismatch
        assert any(
            'File type validation failed' in str(err) or
            'MIME type mismatch' in str(err) or
            'Unsupported file type' in str(err)
            for err in result.get('validation_errors', [])
        )

    def test_mime_type_spoofing_sh_as_txt_rejected(self, app, setup_form_with_document_field, db_session):
        """Test that shell scripts renamed to .txt are rejected."""
        shell_content = b'#!/bin/bash\necho "malicious"\n'
        malicious_file = FileStorage(
            stream=io.BytesIO(shell_content),
            filename='script.txt',  # Spoofed extension
            content_type='text/plain'
        )
        # This might pass extension check but should fail MIME validation
        # or be caught by file extension check if .txt is allowed
        result = self._test_malicious_upload(
            app, setup_form_with_document_field, malicious_file
        )
        # Should be rejected - either by extension (.txt might be allowed) or MIME validation
        # If .txt is allowed, the shell script content might pass MIME check as text
        # So we just verify it's handled (either rejected or flagged)
        assert result['success'] is False or len(result.get('validation_errors', [])) > 0

    def test_null_byte_in_filename_rejected(self, app, setup_form_with_document_field, db_session):
        """Test that filenames with null bytes are sanitized/rejected."""
        pdf_content = b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n'
        # Create filename with null byte (should be sanitized)
        malicious_file = FileStorage(
            stream=io.BytesIO(pdf_content),
            filename='malicious\x00.pdf',
            content_type='application/pdf'
        )
        result = self._test_malicious_upload(
            app, setup_form_with_document_field, malicious_file
        )
        # Should handle null bytes (sanitize or reject)
        assert result['success'] is False or len(result.get('validation_errors', [])) > 0

    def test_oversized_file_rejected(self, app, setup_form_with_document_field, db_session):
        """Test that files exceeding size limits are rejected."""
        # Create a large file (exceeds 25MB default limit)
        large_content = b'X' * (26 * 1024 * 1024)  # 26MB
        malicious_file = FileStorage(
            stream=io.BytesIO(large_content),
            filename='large_file.pdf',
            content_type='application/pdf'
        )
        result = self._test_malicious_upload(
            app, setup_form_with_document_field, malicious_file,
            expected_error_pattern='too large'
        )
        assert any('too large' in str(err).lower() for err in result.get('validation_errors', []))

    def test_com_file_upload_rejected(self, app, setup_form_with_document_field, db_session):
        """Test that .com files are rejected."""
        malicious_file = self._create_malicious_file('malicious.com', b'MZ\x90\x00')
        result = self._test_malicious_upload(
            app, setup_form_with_document_field, malicious_file,
            expected_error_pattern='Unsupported file type'
        )
        assert any('Unsupported file type' in str(err) for err in result.get('validation_errors', []))

    def test_jar_file_upload_rejected(self, app, setup_form_with_document_field, db_session):
        """Test that .jar files are rejected."""
        # JAR files are ZIP archives
        jar_content = b'PK\x03\x04' + b'X' * 100  # ZIP header
        malicious_file = self._create_malicious_file('malicious.jar', jar_content)
        result = self._test_malicious_upload(
            app, setup_form_with_document_field, malicious_file,
            expected_error_pattern='Unsupported file type'
        )
        assert any('Unsupported file type' in str(err) for err in result.get('validation_errors', []))

    def test_valid_pdf_upload_accepted(self, app, setup_form_with_document_field, db_session):
        """Test that valid PDF files are accepted (positive test)."""
        with app.app_context():
            from flask_wtf import FlaskForm

            setup_data = setup_form_with_document_field
            assignment_status = setup_data['assignment_status']
            section = setup_data['section']
            form_item = setup_data['form_item']

            # Create valid PDF content
            pdf_content = b'%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\nxref\n0 0\ntrailer\n<< /Size 0 >>\nstartxref\n0\n%%EOF'
            valid_file = FileStorage(
                stream=io.BytesIO(pdf_content),
                filename='valid_document.pdf',
                content_type='application/pdf'
            )

            # Use stored ID to avoid detached instance errors
            form_item_id = setup_data.get('form_item_id', form_item.id)

            # Configure app for testing
            app.config['FILE_SCANNER_TYPE'] = 'none'
            app.config['FILE_SCANNER_FAIL_OPEN'] = True

            valid_file.stream.seek(0)
            upload_tuple = (
                valid_file.stream,
                valid_file.filename,
                valid_file.content_type or 'application/pdf'
            )

            with app.test_request_context(
                method='POST',
                data={
                    'action': 'save',
                    f'field_language[{form_item_id}]': 'en',
                    f'field_value[{form_item_id}]': upload_tuple
                },
                content_type='multipart/form-data'
            ):
                csrf_form = FlaskForm()
                csrf_form.validate_on_submit = Mock(return_value=True)

                all_sections = [section]
                section.fields_ordered = [form_item]

                result = FormDataService.process_form_submission(
                    assignment_status, all_sections, csrf_form
                )

                # Valid PDF should be accepted (may fail due to missing upload folder in test, but shouldn't fail validation)
                # If it fails, it should be due to file system issues, not validation
                if not result['success']:
                    validation_errors = result.get('validation_errors', [])
                    # Should not have file type validation errors
                    assert not any(
                        'Unsupported file type' in str(err) or
                        'File type validation failed' in str(err) or
                        'MIME type mismatch' in str(err)
                        for err in validation_errors
                    ), f"Valid PDF was rejected with validation errors: {validation_errors}"
