"""Build an Excel workbook (.xlsx) with embedded Power Query definitions."""

from __future__ import annotations

import base64
import io
import re
import struct
import uuid
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

_DATA_MASHUP_NS = 'http://schemas.microsoft.com/DataMashup'
_QUERY_NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
_TEMPLATE_PATH = Path(__file__).resolve().parents[1] / 'static' / 'templates' / 'power_query_workbook_template.xlsx'
_EMPTY_METADATA_CONTENT_ZIP = b'PK\x05\x06' + (b'\x00' * 18)
_PERMISSIONS_XML = (
    '\ufeff<?xml version="1.0" encoding="utf-8"?>'
    '<PermissionList xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
    '<CanEvaluateFuturePackages>false</CanEvaluateFuturePackages>'
    '<FirewallEnabled>true</FirewallEnabled>'
    '<WorkbookGroupType xsi:nil="true" />'
    '</PermissionList>'
).encode('utf-8')
_INNER_PACKAGE_XML = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<Package xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
    'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
    '<Version>2.153.226.0</Version>'
    '<MinVersion>2.21.0.0</MinVersion>'
    '<Culture>en-GB</Culture>'
    '</Package>'
)
_INNER_CONTENT_TYPES_XML = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="xml" ContentType="text/xml" />'
    '<Default Extension="m" ContentType="application/x-ms-m" />'
    '</Types>'
)


def _normalize_formula_text(formula: str) -> str:
    return formula.replace('\r\n', '\n').replace('\r', '\n').strip()


def _build_section1_m(queries: list[tuple[str, str]]) -> str:
    members = []
    for name, formula in queries:
        body = _normalize_formula_text(formula)
        if not body.lower().startswith('let'):
            body = f'let\n{body}'
        if '\nin\n' not in f'\n{body}\n':
            raise ValueError(f'Power Query formula for {name} must contain an in clause')
        members.append(f'shared {name} = {body}')
    return 'section Section1;\r\n\r\n' + ';\r\n\r\n'.join(members) + ';'


def _build_inner_package_zip(section1_m: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as inner:
        inner.writestr('Config/Package.xml', _INNER_PACKAGE_XML.encode('utf-8'))
        inner.writestr('[Content_Types].xml', _INNER_CONTENT_TYPES_XML.encode('utf-8'))
        inner.writestr('Formulas/Section1.m', section1_m.encode('utf-8'))
    return buffer.getvalue()


def _build_metadata_xml(query_names: list[str]) -> bytes:
    items = [
        '<Item>'
        '<ItemLocation><ItemType>AllFormulas</ItemType><ItemPath /></ItemLocation>'
        '<StableEntries />'
        '</Item>',
    ]
    for name in query_names:
        query_id = str(uuid.uuid4())
        safe_name = escape(name)
        items.extend([
            '<Item>'
            '<ItemLocation>'
            '<ItemType>Formula</ItemType>'
            f'<ItemPath>Section1/{safe_name}</ItemPath>'
            '</ItemLocation>'
            '<StableEntries>'
            '<Entry Type="IsPrivate" Value="l0" />'
            '<Entry Type="FillEnabled" Value="l0" />'
            '<Entry Type="FillObjectType" Value="sConnectionOnly" />'
            '<Entry Type="FillToDataModelEnabled" Value="l0" />'
            f'<Entry Type="QueryID" Value="s{query_id}" />'
            '</StableEntries>'
            '</Item>',
            '<Item>'
            '<ItemLocation>'
            '<ItemType>Formula</ItemType>'
            f'<ItemPath>Section1/{safe_name}/Source</ItemPath>'
            '</ItemLocation>'
            '<StableEntries />'
            '</Item>',
        ])
    xml = (
        '\ufeff<?xml version="1.0" encoding="utf-8"?>'
        '<LocalPackageMetadataFile xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        f'<Items>{"".join(items)}</Items>'
        '</LocalPackageMetadataFile>'
    )
    return xml.encode('utf-8')


def _wrap_metadata(metadata_xml: bytes) -> bytes:
    return b''.join([
        struct.pack('<I', 0),
        struct.pack('<I', len(metadata_xml)),
        metadata_xml,
        struct.pack('<I', len(_EMPTY_METADATA_CONTENT_ZIP)),
        _EMPTY_METADATA_CONTENT_ZIP,
    ])


def _build_datamashup_binary(section1_m: str, query_names: list[str]) -> bytes:
    package_zip = _build_inner_package_zip(section1_m)
    permissions = _PERMISSIONS_XML
    metadata = _wrap_metadata(_build_metadata_xml(query_names))
    permission_bindings = b'\x00'
    return b''.join([
        struct.pack('<I', 0),
        struct.pack('<I', len(package_zip)),
        package_zip,
        struct.pack('<I', len(permissions)),
        permissions,
        struct.pack('<I', len(metadata)),
        metadata,
        struct.pack('<I', len(permission_bindings)),
        permission_bindings,
    ])


def _build_datamashup_xml(section1_m: str, query_names: list[str]) -> bytes:
    encoded = base64.b64encode(_build_datamashup_binary(section1_m, query_names)).decode('ascii')
    sqmid = str(uuid.uuid4())
    return (
        f'<?xml version="1.0" encoding="utf-8"?>'
        f'<DataMashup xmlns="{_DATA_MASHUP_NS}" sqmid="{sqmid}">{encoded}</DataMashup>'
    ).encode('utf-8')


def _load_template_bytes() -> bytes:
    if not _TEMPLATE_PATH.is_file():
        raise RuntimeError(
            f'Power Query workbook template is missing: {_TEMPLATE_PATH}. '
            'Regenerate it with scripts/generate_power_query_template.py.'
        )
    return _TEMPLATE_PATH.read_bytes()


def _encode_custom_xml_part(original_bytes: bytes, datamashup_xml: bytes) -> bytes:
    text = datamashup_xml.decode('utf-8')
    if original_bytes.startswith(b'\xff\xfe'):
        text = text.replace('encoding="utf-8"', 'encoding="utf-16"', 1)
        return b'\xff\xfe' + text.encode('utf-16-le')
    if original_bytes.startswith(b'\xfe\xff'):
        text = text.replace('encoding="utf-8"', 'encoding="utf-16"', 1)
        return b'\xfe\xff' + text.encode('utf-16-be')
    return datamashup_xml


def _decode_custom_xml_part(data: bytes) -> str:
    if data.startswith(b'\xff\xfe'):
        return data.decode('utf-16')
    if data.startswith(b'\xfe\xff'):
        return data.decode('utf-16-be')
    return data.decode('utf-8')


def _replace_datamashup_xml(template_bytes: bytes, datamashup_xml: bytes) -> bytes:
    input_buffer = io.BytesIO(template_bytes)
    output_buffer = io.BytesIO()
    replaced = False

    with zipfile.ZipFile(input_buffer, 'r') as src, zipfile.ZipFile(output_buffer, 'w') as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename.startswith('customXml/item') and item.filename.endswith('.xml') and '/_rels/' not in item.filename:
                root_text = _decode_custom_xml_part(data)
                if _DATA_MASHUP_NS in root_text and '<DataMashup' in root_text:
                    data = _encode_custom_xml_part(data, datamashup_xml)
                    replaced = True
            dst.writestr(item, data)

    if not replaced:
        raise RuntimeError('Template workbook does not contain a DataMashup customXml part')
    return output_buffer.getvalue()


def normalize_query_name(name: str) -> str:
    cleaned = re.sub(r'[^A-Za-z0-9_]', '_', (name or '').strip())
    if not cleaned or cleaned[0].isdigit():
        cleaned = f'Query_{cleaned or "Untitled"}'
    if not _QUERY_NAME_RE.match(cleaned):
        cleaned = f'Query_{uuid.uuid4().hex[:8]}'
    return cleaned


def build_power_query_workbook(queries: list[dict[str, str]]) -> bytes:
    """Return .xlsx bytes containing the given Power Query definitions.

    Each query dict must include ``name`` and ``formula`` keys.
    """
    if not queries:
        raise ValueError('At least one query is required')

    normalized: list[tuple[str, str]] = []
    seen_names: set[str] = set()
    for index, query in enumerate(queries):
        name = normalize_query_name(str(query.get('name') or f'Query_{index + 1}'))
        formula = str(query.get('formula') or '').strip()
        if not formula:
            raise ValueError(f'Query {name} is missing formula text')
        while name in seen_names:
            name = f'{name}_{len(seen_names)}'
        seen_names.add(name)
        normalized.append((name, formula))

    section1_m = _build_section1_m(normalized)
    query_names = [name for name, _ in normalized]
    datamashup_xml = _build_datamashup_xml(section1_m, query_names)
    return _replace_datamashup_xml(_load_template_bytes(), datamashup_xml)
