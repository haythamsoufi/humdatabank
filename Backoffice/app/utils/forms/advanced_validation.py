# Advanced input validation and sanitization utilities
import logging
import re

logger = logging.getLogger(__name__)
import html
import bleach
from typing import Any, Dict, List, Optional, Union
from werkzeug.datastructures import FileStorage
from flask import current_app
import os

class AdvancedValidator:
    """Advanced input validation and sanitization."""

    # Allowed HTML tags for rich text content
    ALLOWED_HTML_TAGS = [
        'p', 'br', 'strong', 'em', 'u', 'ul', 'ol', 'li',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote',
        'a', 'span', 'div'
    ]

    # Allowed HTML attributes
    ALLOWED_HTML_ATTRIBUTES = {
        'a': ['href', 'title'],
        'span': ['class'],
        'div': ['class'],
        'p': ['class']
    }

    # Dangerous file extensions
    DANGEROUS_EXTENSIONS = {
        '.exe', '.bat', '.cmd', '.com', '.pif', '.scr', '.vbs', '.js', '.jar',
        '.php', '.asp', '.aspx', '.jsp', '.py', '.rb', '.pl', '.sh', '.ps1'
    }

    # Maximum file sizes by type (in bytes)
    MAX_FILE_SIZES = {
        'image': 5 * 1024 * 1024,  # 5MB
        'document': 25 * 1024 * 1024,  # 25MB
        'spreadsheet': 25 * 1024 * 1024,  # 25MB
        'presentation': 25 * 1024 * 1024,  # 25MB
        'default': 5 * 1024 * 1024  # 5MB
    }

    @staticmethod
    def sanitize_html(content: str, allow_html: bool = False) -> str:
        """
        Sanitize HTML content based on allowed tags and attributes.

        Args:
            content: HTML content to sanitize
            allow_html: Whether to allow HTML tags (default: False)

        Returns:
            Sanitized content
        """
        if not content:
            return ""

        if not allow_html:
            # Strip all HTML tags
            return html.escape(content)

        # Use bleach for HTML sanitization
        try:
            cleaned = bleach.clean(
                content,
                tags=AdvancedValidator.ALLOWED_HTML_TAGS,
                attributes=AdvancedValidator.ALLOWED_HTML_ATTRIBUTES,
                strip=True
            )
            return cleaned
        except Exception as e:
            current_app.logger.warning(f"HTML sanitization failed: {e}")
            return html.escape(content)

    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email address format."""
        if not email:
            return False

        # RFC 5322 compliant regex (simplified)
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(pattern, email))

    @staticmethod
    def validate_phone_number(phone: str) -> bool:
        """Validate phone number format."""
        if not phone:
            return True  # Optional field

        # Remove all non-digit characters
        digits_only = re.sub(r'\D', '', phone)

        # Check if it's a valid length (7-15 digits)
        return 7 <= len(digits_only) <= 15

    @staticmethod
    def validate_url(url: str) -> bool:
        """Validate URL format."""
        if not url:
            return True  # Optional field

        pattern = r'^https?://[^\s/$.?#].[^\s]*$'
        return bool(re.match(pattern, url))

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """
        Sanitize filename to prevent path traversal and other issues.

        Args:
            filename: Original filename

        Returns:
            Sanitized filename
        """
        if not filename:
            return "untitled"

        # SECURITY: Remove path components to prevent path traversal attacks
        # Normalize path separators and get only the basename
        filename = os.path.basename(filename)
        # Additional check for path traversal attempts
        if '..' in filename or filename.startswith('/') or filename.startswith('\\'):
            # If path traversal detected, use only the final component
            filename = filename.replace('..', '').lstrip('/\\')
            filename = os.path.basename(filename)

        # Remove null bytes and control characters
        filename = filename.replace('\x00', '')
        filename = ''.join(char for char in filename if ord(char) >= 32)

        # Remove dangerous characters
        filename = re.sub(r'[<>:"/\\|?*]', '_', filename)

        # Limit length
        if len(filename) > 255:
            name, ext = filename.rsplit('.', 1) if '.' in filename else (filename, '')
            filename = name[:250] + ('.' + ext if ext else '')

        return filename or "untitled"

    @staticmethod
    def validate_mime_type(file: FileStorage, expected_extensions: List[str] = None) -> tuple[bool, Optional[str]]:
        """
        Validate file MIME type using magic bytes (file signature).
        This prevents MIME type spoofing attacks while being permissive for unknown types.

        Args:
            file: Uploaded file
            expected_extensions: List of expected file extensions (e.g., ['.pdf', '.docx'])

        Returns:
            Tuple of (is_valid: bool, detected_mime_type: str or None)
            - Returns (True, mime) when file is valid or type is unknown (permissive)
            - Returns (False, mime) only when clear mismatch detected (e.g., claims PDF but is ZIP)
        """
        if not file or not hasattr(file, 'read'):
            return True, None  # Permissive: allow if we can't validate

        # Save current position
        current_pos = file.tell()
        file.seek(0)

        try:
            # Read first 32 bytes for magic number detection
            header = file.read(32)
            if not header or len(header) < 4:
                return True, None  # Permissive: allow small/empty files

            # Magic number signatures for common file types
            # Format: (signature_bytes, mime_type, extensions)
            magic_signatures = [
                # PDF
                (b'%PDF', 'application/pdf', ['.pdf']),
                # Windows executables (PE/COFF typically start with "MZ")
                (b'MZ', 'application/x-dosexec', ['.exe', '.dll', '.com']),
                # Images
                (b'\xff\xd8\xff', 'image/jpeg', ['.jpg', '.jpeg']),
                (b'\x89PNG\r\n\x1a\n', 'image/png', ['.png']),
                (b'GIF87a', 'image/gif', ['.gif']),
                (b'GIF89a', 'image/gif', ['.gif']),
                (b'RIFF', 'image/webp', ['.webp']),  # WebP starts with RIFF
                # Microsoft Office (ZIP-based formats)
                (b'PK\x03\x04', 'application/zip', ['.docx', '.xlsx', '.pptx', '.zip']),
                (b'PK\x05\x06', 'application/zip', ['.docx', '.xlsx', '.pptx', '.zip']),  # Empty ZIP
                # Microsoft Office (legacy)
                (b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1', 'application/msword', ['.doc', '.xls', '.ppt']),
            ]

            detected_mime = None
            detected_exts = []

            # Check magic signatures first
            for signature, mime_type, exts in magic_signatures:
                if header.startswith(signature):
                    detected_mime = mime_type
                    detected_exts = exts
                    break

            # If no binary signature found, check if it's text-based
            if not detected_mime:
                try:
                    # Try to decode as text (for .txt, .csv, .md, .html files)
                    header.decode('utf-8', errors='strict')
                    detected_mime = 'text/plain'
                    detected_exts = ['.txt', '.csv', '.md', '.html', '.json', '.xml']
                except (UnicodeDecodeError, AttributeError):
                    pass

            # If we couldn't detect the type, be permissive and allow the file
            if not detected_mime:
                return True, None  # Unknown type - allow it through

            # If we have expected extensions, verify the detected type matches
            if expected_extensions:
                # Normalize extensions (ensure they start with .)
                expected_exts = [ext if ext.startswith('.') else f'.{ext}' for ext in expected_extensions]
                expected_exts_lower = [ext.lower() for ext in expected_exts]
                detected_exts_lower = [ext.lower() for ext in detected_exts]

                # Check if any expected extension matches detected type
                if any(ext in detected_exts_lower for ext in expected_exts_lower):
                    return True, detected_mime

                # Special case: text-based files are flexible
                if detected_mime == 'text/plain':
                    # Text files can have many extensions - be permissive
                    text_extensions = ['.txt', '.csv', '.md', '.html', '.json', '.xml', '.log']
                    if any(ext in text_extensions for ext in expected_exts_lower):
                        return True, detected_mime

                # Special case: ZIP-based Office files
                if detected_mime == 'application/zip':
                    office_extensions = ['.docx', '.xlsx', '.pptx', '.odt', '.ods', '.odp']
                    if any(ext in office_extensions for ext in expected_exts_lower):
                        return True, detected_mime

                # Clear mismatch detected - this is suspicious
                return False, detected_mime

            return True, detected_mime

        except Exception as e:
            current_app.logger.warning(f"MIME type validation error: {e}", exc_info=True)
            # SECURITY: Fail-closed on validation errors - reject suspicious files
            # Returning False prevents bypassing MIME validation via exceptions
            return False, None
        finally:
            # Restore file position
            file.seek(current_pos)

    @staticmethod
    def validate_file_upload(file: FileStorage, allowed_extensions: List[str] = None) -> Dict[str, Any]:
        """
        Validate file upload for security and format.

        Args:
            file: Uploaded file
            allowed_extensions: List of allowed file extensions

        Returns:
            Dict with validation results
        """
        result = {
            'valid': False,
            'errors': [],
            'sanitized_filename': None,
            'file_type': None
        }

        if not file or not file.filename:
            result['errors'].append('No file provided')
            return result

        # Sanitize filename
        sanitized_filename = AdvancedValidator.sanitize_filename(file.filename)
        result['sanitized_filename'] = sanitized_filename

        # Check file extension
        file_ext = '.' + sanitized_filename.split('.')[-1].lower() if '.' in sanitized_filename else ''

        # Check for dangerous extensions
        if file_ext in AdvancedValidator.DANGEROUS_EXTENSIONS:
            result['errors'].append(f'File type {file_ext} is not allowed for security reasons')
            return result

        # Check allowed extensions if provided
        if allowed_extensions and file_ext not in allowed_extensions:
            result['errors'].append(f'File type {file_ext} is not allowed. Allowed types: {", ".join(allowed_extensions)}')
            return result

        # SECURITY: Validate MIME type using magic bytes to prevent MIME spoofing
        if file_ext:  # Only validate if we have an extension
            mime_valid, detected_mime = AdvancedValidator.validate_mime_type(file, allowed_extensions)
            if not mime_valid:
                result['errors'].append(
                    f'File MIME type validation failed. '
                    f'Expected type for {file_ext} but detected: {detected_mime or "unknown"}. '
                    f'This may indicate a file type mismatch or spoofing attempt.'
                )
                return result

        # Determine file type for size validation
        file_type = 'default'
        if file_ext in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg']:
            file_type = 'image'
        elif file_ext in ['.pdf', '.doc', '.docx', '.txt']:
            file_type = 'document'
        elif file_ext in ['.xls', '.xlsx']:
            file_type = 'spreadsheet'
        elif file_ext in ['.ppt', '.pptx']:
            file_type = 'presentation'

        result['file_type'] = file_type

        # Check file size
        max_size = AdvancedValidator.MAX_FILE_SIZES.get(file_type, AdvancedValidator.MAX_FILE_SIZES['default'])

        # Reset file pointer to beginning
        file.seek(0, 2)  # Seek to end
        file_size = file.tell()
        file.seek(0)  # Reset to beginning

        if file_size > max_size:
            result['errors'].append(f'File size {file_size} bytes exceeds maximum allowed size of {max_size} bytes')
            return result

        # Basic magic number validation for images (permissive for SVG and unknown formats)
        if file_type == 'image':
            file.seek(0)
            header = file.read(64)  # Read more for SVG detection
            file.seek(0)

            # Check for common image magic numbers
            image_signatures = [
                b'\xff\xd8\xff',  # JPEG
                b'\x89PNG\r\n\x1a\n',  # PNG
                b'GIF87a',  # GIF87a
                b'GIF89a',  # GIF89a
                b'RIFF',  # WebP (starts with RIFF)
            ]

            # Check for SVG (XML-based, text format)
            is_svg = False
            try:
                header_str = header.decode('utf-8', errors='ignore').lower()
                if '<svg' in header_str or '<?xml' in header_str:
                    is_svg = True
            except Exception as e:
                logger.debug("AdvancedValidator: SVG/XML header check failed: %s", e)

            # Only block if we detect a clearly wrong format (e.g., PDF claiming to be image)
            if not any(header.startswith(sig) for sig in image_signatures) and not is_svg:
                # Check if it's a known non-image format
                non_image_signatures = [
                    b'%PDF',  # PDF
                    b'PK\x03\x04',  # ZIP/Office
                    b'\xd0\xcf\x11\xe0',  # MS Office legacy
                ]
                if any(header.startswith(sig) for sig in non_image_signatures):
                    result['errors'].append('File appears to be a document, not an image')
                    return result
                # Unknown format - allow it through (permissive)

        result['valid'] = True
        return result

    @staticmethod
    def validate_json_input(data: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
        """
        Validate JSON input against schema.

        Args:
            data: Input data to validate
            schema: Validation schema

        Returns:
            Dict with validation results
        """
        result = {
            'valid': True,
            'errors': [],
            'sanitized_data': {}
        }

        try:
            # Basic type validation
            for field, field_schema in schema.items():
                value = data.get(field)
                expected_type = field_schema.get('type')

                if field_schema.get('required', False) and value is None:
                    result['errors'].append(f'Field {field} is required')
                    result['valid'] = False
                    continue

                if value is not None:
                    # Type validation
                    if expected_type == 'string' and not isinstance(value, str):
                        result['errors'].append(f'Field {field} must be a string')
                        result['valid'] = False
                    elif expected_type == 'integer' and not isinstance(value, int):
                        result['errors'].append(f'Field {field} must be an integer')
                        result['valid'] = False
                    elif expected_type == 'boolean' and not isinstance(value, bool):
                        result['errors'].append(f'Field {field} must be a boolean')
                        result['valid'] = False

                    # Sanitize string values
                    if isinstance(value, str):
                        sanitized_value = AdvancedValidator.sanitize_html(
                            value,
                            allow_html=field_schema.get('allow_html', False)
                        )
                        result['sanitized_data'][field] = sanitized_value
                    else:
                        result['sanitized_data'][field] = value

            return result

        except Exception as e:
            current_app.logger.error(f"JSON validation error: {e}", exc_info=True)
            result['valid'] = False
            result['errors'].append('Validation error occurred')
            return result

# Global validator instance
validator = AdvancedValidator()

def validate_upload_extension_and_mime(
    file: FileStorage,
    allowed_extensions: Union[List[str], set],
) -> tuple[bool, Optional[str], Optional[str]]:
    """
    Validate uploaded file extension and MIME type. Shared helper to reduce duplication.

    Args:
        file: Uploaded file (FileStorage)
        allowed_extensions: Allowed extensions, e.g. {'.csv', '.xlsx', '.xls'} or ['.xlsx', '.xls']

    Returns:
        Tuple of (valid: bool, error_message: Optional[str], ext: Optional[str]).
        When valid is True, error_message is None and ext is the file extension.
        When valid is False, error_message describes the failure.
    """
    if not file or not file.filename:
        return False, "No file provided", None

    filename = file.filename
    _, ext = os.path.splitext(filename.lower())
    ext = ext if ext else None

    allowed = {e if e.startswith(".") else f".{e}" for e in allowed_extensions}
    allowed_lower = {e.lower() for e in allowed}

    if ext not in allowed_lower:
        return False, f"Unsupported file type. Allowed: {', '.join(sorted(allowed))}", ext

    mime_valid, detected_mime = AdvancedValidator.validate_mime_type(file, list(allowed))
    if not mime_valid:
        return (
            False,
            f"File type validation failed: extension ({ext}) does not match actual file content.",
            ext,
        )

    file.seek(0)
    return True, None, ext


# Convenience functions
def sanitize_input(value: str, allow_html: bool = False) -> str:
    """Sanitize user input."""
    return validator.sanitize_html(value, allow_html)

def validate_file(file: FileStorage, allowed_extensions: List[str] = None) -> Dict[str, Any]:
    """Validate uploaded file."""
    return validator.validate_file_upload(file, allowed_extensions)

def sanitize_filename(filename: str) -> str:
    """Sanitize filename."""
    return validator.sanitize_filename(filename)
