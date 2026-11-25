"""Decide who the PMER focal points and project managers of each country are. No database access.

A country uses the people listed for it. A country with nobody listed uses the region office
of its region instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from plugins.global_award.importer.countries import CountryIndex, CountryRef, normalize_country
from plugins.global_award.importer.sectoral import (
    KIND_COUNTRY,
    KIND_REGIONAL,
    ROLE_MANAGER,
    ROLE_PMER,
    ContactRow,
    ParsedSectoral,
    Person,
    SectoralCountry,
    region_key,
)

SOURCE_COUNTRY = "country"
SOURCE_REGIONAL = "regional"
SOURCE_NONE = "none"


@dataclass
class CountryContacts:
    country: SectoralCountry
    ref: CountryRef
    pmer: List[Person]
    pmer_source: str
    managers: List[Person]
    managers_source: str


@dataclass
class PersonRecord:
    """Everyone named in the workbook becomes one user, whatever their role."""

    email: str
    name: str
    roles: List[str] = field(default_factory=list)
    country_ids: List[int] = field(default_factory=list)


@dataclass
class ResolvedContacts:
    countries: List[CountryContacts]
    people: Dict[str, PersonRecord]
    unmatched_countries: List[str]
    unmatched_contacts: List[str]


def _targets(label: str, countries: CountryIndex, groups: Dict[str, List[int]]) -> Optional[List[int]]:
    """Country ids a contact row covers: a country, or a group such as ``Pacific Islands``."""
    group = groups.get(normalize_country(label))
    if group:
        return list(group)
    ref = countries.match(label)
    if ref is None and "/" in label:
        # "Pakistan/RESERVES" is the country's reserves line.
        ref = countries.match(label.split("/", 1)[0])
    return [ref.id] if ref is not None else None


def _merge(into: List[Person], people: List[Person]) -> None:
    known = {person.email for person in into}
    for person in people:
        if person.email not in known:
            into.append(person)
            known.add(person.email)


def _index(
    rows: List[ContactRow],
    role: str,
    countries: CountryIndex,
    groups: Dict[str, List[int]],
    unmatched: List[str],
) -> tuple[Dict[int, List[Person]], Dict[str, List[Person]]]:
    by_country: Dict[int, List[Person]] = {}
    by_region: Dict[str, List[Person]] = {}
    for row in rows:
        if row.role != role or not row.people:
            continue
        if row.kind == KIND_REGIONAL:
            _merge(by_region.setdefault(row.region, []), row.people)
        elif row.kind == KIND_COUNTRY:
            ids = _targets(row.label, countries, groups)
            if ids is None:
                unmatched.append(f"{row.label} ({role})")
                continue
            for country_id in ids:
                _merge(by_country.setdefault(country_id, []), row.people)
    return by_country, by_region


def _pick(
    ref: CountryRef,
    region: str,
    by_country: Dict[int, List[Person]],
    by_region: Dict[str, List[Person]],
) -> tuple[List[Person], str]:
    own = by_country.get(ref.id)
    if own:
        return list(own), SOURCE_COUNTRY
    regional = by_region.get(region)
    if regional:
        return list(regional), SOURCE_REGIONAL
    return [], SOURCE_NONE


def resolve_contacts(parsed: ParsedSectoral, countries: CountryIndex) -> ResolvedContacts:
    matched: List[tuple[SectoralCountry, CountryRef]] = []
    unmatched_countries: List[str] = []
    groups: Dict[str, List[int]] = {}
    for country in parsed.countries:
        ref = countries.match(country.name)
        if ref is None:
            unmatched_countries.append(country.name)
            continue
        matched.append((country, ref))
        if country.group:
            groups.setdefault(normalize_country(country.group), []).append(ref.id)

    unmatched_contacts: List[str] = []
    pmer_country, pmer_region = _index(parsed.contacts, ROLE_PMER, countries, groups, unmatched_contacts)
    mgr_country, mgr_region = _index(parsed.contacts, ROLE_MANAGER, countries, groups, unmatched_contacts)

    resolved: List[CountryContacts] = []
    people: Dict[str, PersonRecord] = {}

    def remember(person: Person, role: str, country_id: Optional[int] = None) -> None:
        record = people.setdefault(person.email, PersonRecord(email=person.email, name=person.name))
        if role not in record.roles:
            record.roles.append(role)
        if country_id is not None and country_id not in record.country_ids:
            record.country_ids.append(country_id)

    for country, ref in matched:
        region = region_key(country.region)
        pmer, pmer_source = _pick(ref, region, pmer_country, pmer_region)
        managers, managers_source = _pick(ref, region, mgr_country, mgr_region)
        resolved.append(
            CountryContacts(
                country=country,
                ref=ref,
                pmer=pmer,
                pmer_source=pmer_source,
                managers=managers,
                managers_source=managers_source,
            )
        )
        for person in pmer:
            remember(person, ROLE_PMER, ref.id)
        for person in managers:
            remember(person, ROLE_MANAGER, ref.id)

    # People who cover no country here (HQ, region office staff) are still imported as users.
    for row in parsed.contacts:
        for person in row.people:
            remember(person, row.role)

    return ResolvedContacts(
        countries=resolved,
        people=people,
        unmatched_countries=unmatched_countries,
        unmatched_contacts=sorted(set(unmatched_contacts)),
    )
