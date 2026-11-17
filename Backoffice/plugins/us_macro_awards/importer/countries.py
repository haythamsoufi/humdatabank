"""Match logframe country headers to Country rows. No database access."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

# Alternate spellings of the same country. Each group is compared after
# ``normalize_country`` (accents stripped, punctuation removed).
_ALIAS_GROUPS = (
    {"viet nam", "vietnam"},
    {"turkiye", "turkey"},
    {"democratic republic of the congo", "congo democratic republic of the", "congo the democratic republic of the", "dr congo", "democratic republic of congo"},
    {"federated states of micronesia", "micronesia federated states of"},
    {"syrian arab republic", "syria"},
    {"kyrgyz republic", "kyrgyzstan"},
    {"eswatini", "swaziland"},
    {"cabo verde", "cape verde"},
    {"czech republic", "czechia"},
    {"united republic of tanzania", "tanzania"},
    {"lao peoples democratic republic", "laos", "lao pdr"},
    {"republic of moldova", "moldova"},
    {"russian federation", "russia"},
    {"iran islamic republic of", "iran"},
    {"bolivia plurinational state of", "bolivia"},
    {"republic of the congo", "congo republic of the"},
    {"korea republic of", "republic of korea"},
    {"cote divoire", "ivory coast"},
)


@dataclass(frozen=True)
class CountryRef:
    id: int
    name: str
    iso3: str


def normalize_country(name: str) -> str:
    text = unicodedata.normalize("NFKD", name or "")
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = text.casefold().replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


class CountryIndex:
    def __init__(self, countries: Sequence[CountryRef]):
        self._by_name: dict[str, list[CountryRef]] = {}
        for country in countries:
            self._by_name.setdefault(normalize_country(country.name), []).append(country)

    def match(self, logframe_name: str) -> Optional[CountryRef]:
        wanted = normalize_country(logframe_name)
        if not wanted:
            return None
        names = {wanted}
        for group in _ALIAS_GROUPS:
            if wanted in group:
                names.update(group)
        for candidate in sorted(names, key=len, reverse=True):
            hits = self._by_name.get(candidate) or []
            if len(hits) == 1:
                return hits[0]
        return None

    def match_all(self, names: Iterable[str]) -> dict[str, Optional[CountryRef]]:
        return {name: self.match(name) for name in names}
