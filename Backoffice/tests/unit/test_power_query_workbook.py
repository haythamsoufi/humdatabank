import base64
import re
import struct
import zipfile
from io import BytesIO

from app.utils.power_query_workbook import (
    _decode_custom_xml_part,
    build_power_query_workbook,
    normalize_query_name,
)


def _extract_section1_m(item_xml: str) -> str:
    encoded = re.search(r'<DataMashup[^>]*>([A-Za-z0-9+/=]+)</DataMashup>', item_xml)
    assert encoded is not None
    mashup = base64.b64decode(encoded.group(1))
    package_size = struct.unpack('<I', mashup[4:8])[0]
    package_zip = mashup[8:8 + package_size]
    with zipfile.ZipFile(BytesIO(package_zip)) as package:
        return package.read('Formulas/Section1.m').decode('utf-8')


def test_normalize_query_name_sanitizes_invalid_chars():
    assert normalize_query_name('Databank/Data') == 'Databank_Data'


def test_build_power_query_workbook_embeds_datamashup():
    formula = (
        'let\n'
        '    Source = 1\n'
        'in\n'
        '    Source'
    )
    data = build_power_query_workbook([
        {'name': 'Databank_Data', 'formula': formula},
        {'name': 'Databank_Countries', 'formula': formula},
    ])

    with zipfile.ZipFile(BytesIO(data)) as archive:
        names = archive.namelist()
        assert 'customXml/item1.xml' in names
        item_xml = _decode_custom_xml_part(archive.read('customXml/item1.xml'))
        section1_m = _extract_section1_m(item_xml)
        assert 'shared Databank_Data' in section1_m
        assert 'shared Databank_Countries' in section1_m
