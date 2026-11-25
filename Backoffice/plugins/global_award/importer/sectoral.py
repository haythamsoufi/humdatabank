"""Read the Sectoral Interventions workbook. No database access.

Three sheets are used:

* ``Sectoral interventions``: the sectors each country works in, with its pillar.
* ``PMER Focal Points``: PMER focal points per country, region office or HQ.
* ``Project Managers``: project managers per country, region office or HQ.

The other sheets of the file (slide draft, country info, reporting schedule) are ignored.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from plugins.global_award.importer.workbook import clean_text, open_workbook

SHEET_SECTORS = "Sectoral interventions"
SHEET_PMER = "PMER Focal Points"
SHEET_MANAGERS = "Project Managers"

KIND_COUNTRY = "country"
KIND_REGIONAL = "regional"
KIND_GLOBAL = "global"

ROLE_PMER = "PMER focal point"
ROLE_MANAGER = "Project manager"

_EMAIL = re.compile(r"[A-Za-z0-9._%+'\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")
_NAME_SPLIT = re.compile(r"\s*[,;\n]\s*")
# The workbook states a country that has no data yet with this note.
_MISSING_NOTE = "missing data"


@dataclass(frozen=True)
class Person:
    name: str
    email: str


@dataclass
class SectoralCountry:
    """One country row of the sectoral matrix."""

    name: str
    region: str
    group: str
    sectors: List[str]
    pillar: str
    source: str
    missing: bool = False


@dataclass
class ContactRow:
    """One row of a contact sheet: who, and for which country, region office or HQ."""

    kind: str
    label: str
    region: str
    people: List[Person]
    role: str
    row: int = 0


@dataclass
class ParsedSectoral:
    sectors: List[str]
    countries: List[SectoralCountry]
    contacts: List[ContactRow]
    updated_on: str = ""
    skipped_rows: List[str] = field(default_factory=list)


def region_key(text: Any) -> str:
    """Stable key for a region written differently across sheets (``AsiaPac``, ``Asia Pacific``)."""
    token = re.sub(r"[^a-z0-9]+", " ", clean_text(text).casefold()).strip()
    token = re.sub(r"\b(regional|region|office|regional office)\b", " ", token)
    token = " ".join(token.split())
    if token.startswith("asia"):
        return "asia_pacific"
    if token.startswith("europe"):
        return "europe"
    if token.startswith("africa"):
        return "africa"
    if token in ("mena", "middle east") or "middle east" in token:
        return "mena"
    if token.startswith("america"):
        return "americas"
    return token.replace(" ", "_")


def split_people(names: Any, emails: Any) -> List[Person]:
    """People in one name cell and one email cell. Both cells may list several people.

    When the number of names differs from the number of emails (``Rommanee K. Kwanta N.``
    next to two addresses) the names are read from the addresses instead of guessed.
    """
    found: List[str] = []
    for address in _EMAIL.findall(clean_text_keep_breaks(emails)):
        address = address.strip().lower()
        if address not in found:
            found.append(address)
    if not found:
        return []
    listed = [clean_text(part) for part in _NAME_SPLIT.split(clean_text_keep_breaks(names))]
    listed = [part for part in listed if part]
    if len(listed) != len(found):
        listed = [_name_from_email(address) for address in found]
    return [Person(name=name, email=address) for name, address in zip(listed, found)]


def clean_text_keep_breaks(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("_x000D_", "\n").replace("\r", "\n").replace("\xa0", " ")


def _name_from_email(address: str) -> str:
    local = address.split("@", 1)[0]
    return " ".join(part.capitalize() for part in re.split(r"[._\-]+", local) if part)


def _find_sheet(workbook, wanted: str):
    key = wanted.casefold()
    for name in workbook.sheetnames:
        if name.strip().casefold() == key:
            return workbook[name]
    raise ValueError(f"The workbook has no sheet named {wanted}.")


def _rows(sheet) -> List[tuple]:
    return [tuple(row) for row in sheet.iter_rows(values_only=True)]


def _find_header(rows: List[tuple], required: set, sheet_name: str) -> tuple[int, Dict[str, int]]:
    for index, row in enumerate(rows[:30]):
        labels = {clean_text(cell).casefold(): position for position, cell in enumerate(row) if clean_text(cell)}
        if required <= set(labels):
            return index, labels
    raise ValueError(f"{sheet_name} has no header row with: {', '.join(sorted(required))}.")


def _at(row: tuple, index: Optional[int]) -> Any:
    if index is None or index >= len(row):
        return None
    return row[index]


def _parse_sectors(workbook) -> tuple[List[str], List[SectoralCountry], str]:
    rows = _rows(_find_sheet(workbook, SHEET_SECTORS))
    header_at, labels = _find_header(rows, {"region", "country", "pillar"}, SHEET_SECTORS)
    header = rows[header_at]
    country_col = labels["country"]
    pillar_col = labels["pillar"]
    # Sector columns sit between the country columns and Pillar. The cell after Country is
    # blank in the header: it holds the Pacific country when C names a group.
    first_sector = country_col + 2
    sectors = [
        (position, clean_text(_at(header, position)))
        for position in range(first_sector, pillar_col)
        if clean_text(_at(header, position))
    ]
    if not sectors:
        raise ValueError(f"{SHEET_SECTORS} has no sector columns before Pillar.")

    updated_on = ""
    for row in rows[:header_at]:
        cells = [clean_text(cell).casefold() for cell in row]
        if "updated on" in cells:
            value = _at(row, cells.index("updated on") + 1)
            if isinstance(value, dt.datetime):
                value = value.date()
            updated_on = value.isoformat() if isinstance(value, dt.date) else clean_text(value)
            break

    countries: List[SectoralCountry] = []
    region = ""
    current_group = ""
    for row in rows[header_at + 1 :]:
        region_cell = clean_text(_at(row, labels["region"]))
        if region_cell:
            region = region_cell
            current_group = ""
        group = clean_text(_at(row, country_col))
        member = clean_text(_at(row, country_col + 1))
        name = member or group
        if not name:
            continue
        # "Pacific Islands" is written once in C; the countries under it fill D below it.
        if member:
            current_group = group or current_group
        else:
            current_group = ""
        marks = [
            sector
            for position, sector in sectors
            if clean_text(_at(row, position)).upper() == "X"
        ]
        source = ""
        for position, cell in enumerate(row):
            if clean_text(cell).casefold().rstrip(":") == "source":
                source = clean_text(_at(row, position + 1))
                break
        missing = source.casefold() == _MISSING_NOTE
        countries.append(
            SectoralCountry(
                name=name,
                region=region,
                group=current_group,
                sectors=[] if missing else marks,
                pillar=clean_text(_at(row, pillar_col)),
                source=source,
                missing=missing,
            )
        )
    if not countries:
        raise ValueError(f"{SHEET_SECTORS} has no country rows.")
    return [sector for _position, sector in sectors], countries, updated_on


def _parse_pmer(workbook) -> List[ContactRow]:
    rows = _rows(_find_sheet(workbook, SHEET_PMER))
    header_at, labels = _find_header(rows, {"region / country", "name", "email"}, SHEET_PMER)
    out: List[ContactRow] = []
    for offset, row in enumerate(rows[header_at + 1 :], start=header_at + 2):
        label = clean_text(_at(row, labels["region / country"]))
        if not label:
            continue
        people = split_people(_at(row, labels["name"]), _at(row, labels["email"]))
        normal = label.casefold()
        if "regional" in normal:
            kind, region = KIND_REGIONAL, region_key(label)
        elif normal in ("geneva", "hq", "global"):
            kind, region = KIND_GLOBAL, ""
        else:
            kind, region = KIND_COUNTRY, ""
        out.append(ContactRow(kind=kind, label=label, region=region, people=people, role=ROLE_PMER, row=offset))
    return out


def _parse_managers(workbook) -> List[ContactRow]:
    rows = _rows(_find_sheet(workbook, SHEET_MANAGERS))
    header_at, labels = _find_header(rows, {"region", "country", "project manager", "email"}, SHEET_MANAGERS)
    sub_col = labels.get("subregion")
    out: List[ContactRow] = []
    for offset, row in enumerate(rows[header_at + 1 :], start=header_at + 2):
        label = clean_text(_at(row, labels["country"]))
        if not label:
            continue
        region = clean_text(_at(row, labels["region"]))
        sub = clean_text(_at(row, sub_col)).casefold()
        people = split_people(_at(row, labels["project manager"]), _at(row, labels["email"]))
        if region.casefold() == "global":
            kind, key = KIND_GLOBAL, ""
        elif sub == "regional" or label.casefold().startswith(("region office", "regional office")):
            kind, key = KIND_REGIONAL, region_key(region)
        else:
            kind, key = KIND_COUNTRY, ""
        out.append(ContactRow(kind=kind, label=label, region=key, people=people, role=ROLE_MANAGER, row=offset))
    return out


def parse_workbook(workbook) -> ParsedSectoral:
    sectors, countries, updated_on = _parse_sectors(workbook)
    contacts = [*_parse_pmer(workbook), *_parse_managers(workbook)]
    return ParsedSectoral(sectors=sectors, countries=countries, contacts=contacts, updated_on=updated_on)


def load_sectoral(source) -> ParsedSectoral:
    """Open a path or uploaded bytes and parse the sectoral interventions workbook."""
    workbook = open_workbook(source)
    try:
        return parse_workbook(workbook)
    finally:
        workbook.close()
