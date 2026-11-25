#!/usr/bin/env python3
"""Tag indicator-bank rows that match the Emergency Appeal tracking form.

The bank marks a wide set with the Emergency flag (and the "Emergency" tag).
Emergency Appeal plans need the shorter list in the XLSForm (the Ukraine and
Impacted Countries Emergency Appeal indicator tracking tool). This reads that
form, finds the best bank row for each indicator, and adds the tag
"Emergency Appeal".

The Emergency flag is left as it is. A row can carry both.

Dry run (default) prints every form indicator, the bank row it would tag, and
the rows it will not touch because the match is weak or tied. Nothing is written.

    python scripts/ops/tag_emergency_appeal_indicators.py --form PATH/form.xlsx

Write, after the dry run looks right. Add --user-email to store an indicator
history row for that user.

    python scripts/ops/tag_emergency_appeal_indicators.py --form PATH/form.xlsx --apply

On production, upload the workbook and dry-run before --apply. From the repo root:

    ./azure-webapp/azure_webapp_run_script.ps1 -Environment PROD -Script ops/tag_emergency_appeal_indicators.py -Upload "PATH/form.xlsx=/tmp/appeal-indicators.xlsx" -RemoteArgs "--form /tmp/appeal-indicators.xlsx"

The script reads whichever database DATABASE_URL / FLASK_CONFIG point at.
See docs/runbooks/operations/routine-maintenance.md.

Matching uses the English question, its hint, and the choice label. Age, sex,
and item-group breakdowns are data-entry fields, not separate indicators.
"None of the above" is skipped. A tie or a low score is reported and not tagged.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

for candidate in (Path("/app"), Path(__file__).resolve().parent.parent.parent):
    if (candidate / "app").is_dir() and (candidate / "run.py").is_file():
        root = str(candidate)
        if root not in sys.path:
            sys.path.insert(0, root)
        scripts = str(candidate / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        break
else:
    from _bootstrap import setup_cli_paths

    setup_cli_paths(__file__)

from app import create_app  # noqa: E402

TAG = "Emergency Appeal"
MIN_SCORE = 0.72
MIN_RECALL = 0.5
MIN_MARGIN = 0.045

# Words that show up on almost every "number of people reached" indicator.
_GENERIC = {
    "number", "percentage", "percent", "people", "person", "persons", "individuals",
    "individual", "reached", "reach", "provided", "provide", "received", "receive",
    "receiving", "have", "has", "been", "were", "was", "are", "is", "with", "through",
    "including", "during", "from", "into", "over", "national", "society", "your",
    "this", "that", "their", "its", "who", "which", "how", "many", "other", "also",
    "emergency", "emergencies", "response", "situation", "operation", "operations",
    "programme", "programmes", "program", "programs", "the", "and", "for", "per",
    "all", "any", "not", "only", "where", "when", "what", "can", "may", "such",
    "than", "between", "total", "data", "please", "reported", "activities", "activity",
    "services", "service", "including", "based", "related", "using", "within",
    "across", "about", "after", "before", "under", "above", "each", "both",
    "these", "those", "them", "they", "you", "our", "being", "done", "made",
}

_TAG_RE = re.compile(r"<[^>]+>")
_MARKUP_RE = re.compile(r"[#*]+")
_LEADING_NUM_RE = re.compile(r"^\d+[a-z]?\.\s*")
_SPACE_RE = re.compile(r"\s+")
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_HOW_MANY_RE = re.compile(
    r"^how many\s+(.+?)\s+(?:have|has|were|was|are|is|did|can)\b\s*(.*)$",
    re.IGNORECASE,
)
_NONE_RE = re.compile(r"none of the above", re.IGNORECASE)

_SECTIONS = {
    "choose_indicators": "Health and Care, including WASH",
    "choose_indicators_ia": "Integrated Assistance",
    "choose_indicators_ps": "Protection, Prevention and National Society Strengthening",
    "choose_indicators_ss": "Support services",
    "choose_indicators_winter": "Winter response",
}

# Joined before tokenization so both sides share one token.
_PHRASES = (
    (re.compile(r"psycho[\s-]*social"), "psychosocial"),
    (re.compile(r"health\s*care"), "health"),
    (re.compile(r"first\s+aid"), "firstaid"),
    (re.compile(r"child[\s-]*friendly"), "childfriendly"),
    (re.compile(r"humanitarian\s+service\s+points?"), "humanitarianservicepoint"),
    (re.compile(r"\bhsps?\b"), "humanitarianservicepoint"),
    (re.compile(r"\bmhpss\b"), "mental health psychosocial"),
    (re.compile(r"\bpgi\b"), "protection gender inclusion"),
    (re.compile(r"\bcea\b"), "community engagement accountability"),
    (re.compile(r"\bcva\b"), "cash voucher"),
    (re.compile(r"\bpsea\b"), "sexual exploitation abuse"),
    (re.compile(r"\bnss?\b"), "national society"),
    (re.compile(r"\bfa\b"), "firstaid"),
    (re.compile(r"cash\s+and\s*/?\s*or\s+voucher"), "cash voucher"),
    (re.compile(r"cash\s+and\s+voucher"), "cash voucher"),
)


@dataclass(frozen=True)
class FormIndicator:
    code: str
    section: str
    label: str
    question: str
    hint: str

    @property
    def phrases(self) -> list[str]:
        found = []
        for raw in (self._as_bank_name(self.question), self.hint, self.label, self.question):
            text = (raw or "").strip()
            if text and text not in found and not text.lower().startswith("if number is unknown"):
                found.append(text)
        return found

    @staticmethod
    def _as_bank_name(question: str) -> str:
        """Turn "How many people have been reached with X" into bank-style wording."""
        text = (question or "").strip()
        if not text:
            return ""
        if text.startswith("%"):
            return "Percentage of " + text[1:].lstrip()
        match = _HOW_MANY_RE.match(text)
        if not match:
            return text
        subject = _SPACE_RE.sub(" ", match.group(1)).strip()
        rest = _SPACE_RE.sub(" ", match.group(2)).strip(" ?.")
        rest = re.sub(r"^(been|being)\s+", "", rest, flags=re.IGNORECASE)
        if rest:
            return f"Number of {subject} {rest}"
        return f"Number of {subject}"

    @property
    def name_aliases(self) -> list[str]:
        """Bank wordings for this form line, where the form does not use the bank's phrase.

        Matched against indicator names only. Ids are not stored: production and
        local banks share the IFRC names, not a guaranteed id.
        """
        text = f"{self.question} {self.label}".casefold()
        extras: list[str] = []
        if "primary health" in text:
            extras.append("Number of people reached through primary health care")
        if "rental" in text:
            extras.append("Number of households who received rental assistance")
        if "child-friendly" in text or "child friendly" in text:
            extras.append("Number of people with access to temporary safe spaces")
        if "sexual exploitation" in text or "child safeguarding" in text:
            extras.append(
                "staff and volunteers trained on prevention and protection of sexual exploitation "
                "and abuse and child safeguarding"
            )
        if "feedback mechanism" in text:
            extras.append("National Society has a functioning community feedback mechanism")
        if "education support" in text:
            extras.append("Number of people receiving any form of education support")
        if "insurance" in text and "volunteer" in text:
            extras.append("Number of volunteers covered by accident insurance")
        if "winter" not in text and "humanitarian service point" in text and "how many people" in text:
            extras.append("Number of people reached through humanitarian service points")
        if "winter" not in text and "how many humanitarian service point" in text:
            extras.append("Number of Humanitarian Service Points")
        if "conditional" in text and "unconditional" in text:
            extras.append("Number of people provided with unconditional cash assistance")
            extras.append("Number of people provided with conditional cash assistance")
        if "community engagement" in text and "trained" in text:
            extras.append("staff, volunteers and leadership trained on community engagement and accountability")
        if "protection, gender" in text or "protection gender" in text:
            extras.append("Number of people reached by protection, gender and inclusion")
        if "advocacy" in text or "humanitarian diplomacy" in text:
            extras.append("National Society has a domestic advocacy strategy")
            extras.append("National Society implements humanitarian diplomacy initiatives")
        if "social cohesion" in text:
            extras.append("Number of people reached by social cohesion activities")
        if "relief assistance" in text and "basic needs" in text:
            extras.append("Number of people reached with relief assistance for basic needs")
        return extras


@dataclass(frozen=True)
class BankRow:
    id: int
    name: str
    definition: str
    type: str
    emergency: bool
    archived: bool
    tags: list[str]


@dataclass(frozen=True)
class Candidate:
    row: BankRow
    score: float
    recall: float
    via: str


def clean_text(value) -> str:
    text = _TAG_RE.sub(" ", str(value or ""))
    text = text.replace("\xa0", " ")
    text = _MARKUP_RE.sub(" ", text)
    text = text.replace("•", " ")
    text = _SPACE_RE.sub(" ", text).strip()
    text = _LEADING_NUM_RE.sub("", text)
    return text.strip(" ?")


def _prepare(text: str) -> str:
    lowered = clean_text(text).casefold()
    lowered = lowered.replace("’", "'").replace("`", "'")
    for pattern, replacement in _PHRASES:
        lowered = pattern.sub(replacement, lowered)
    return lowered


def content_tokens(text: str) -> list[str]:
    prepared = _prepare(text)
    seen = set()
    tokens = []
    for token in _TOKEN_RE.findall(prepared):
        if token in _GENERIC or len(token) < 3 or token.isdigit():
            continue
        if token not in seen:
            seen.add(token)
            tokens.append(token)
    return tokens


def _fold(text: str) -> str:
    return "".join(ch for ch in _prepare(text) if ch.isalnum())


def _f1(recall: float, precision: float) -> float:
    if recall + precision == 0:
        return 0.0
    return 2 * recall * precision / (recall + precision)


def _lcs(left: list[str], right: list[str]) -> int:
    if not left or not right:
        return 0
    previous = [0] * (len(right) + 1)
    for token in left:
        current = [0]
        for index, other in enumerate(right, start=1):
            if token == other:
                current.append(previous[index - 1] + 1)
            else:
                current.append(max(current[-1], previous[index]))
        previous = current
    return previous[-1]


def score_texts(phrase: str, bank_text: str) -> tuple[float, float]:
    """Return (score, recall) of a form phrase against one bank string."""
    form_fold = _fold(phrase)
    bank_fold = _fold(bank_text)
    # The whole phrase sitting inside the bank name (or the bank name inside the
    # phrase) is the same indicator, even when extra clauses surround it.
    if len(form_fold) >= 20 and form_fold and bank_fold and form_fold in bank_fold:
        return 0.93, 1.0
    if len(bank_fold) >= 28 and form_fold and bank_fold and bank_fold in form_fold:
        return 0.86, 0.9
    form_tokens = content_tokens(phrase)
    bank_tokens = content_tokens(bank_text)
    if len(form_tokens) < 2 or not bank_tokens:
        return 0.0, 0.0
    form_set = set(form_tokens)
    bank_set = set(bank_tokens)
    overlap = form_set & bank_set
    recall = len(overlap) / len(form_set)
    precision = len(overlap) / len(bank_set)
    lexical = _f1(recall, precision)
    order = _lcs(form_tokens, bank_tokens) / len(form_tokens)
    sequence = SequenceMatcher(None, form_fold, bank_fold).ratio() if form_fold and bank_fold else 0.0
    score = 0.62 * lexical + 0.23 * order + 0.15 * sequence
    return score, recall


def score_row(indicator: FormIndicator, row: BankRow) -> Candidate | None:
    best_score = 0.0
    best_recall = 0.0
    via = ""
    for phrase in indicator.phrases:
        name_score, name_recall = score_texts(phrase, row.name)
        if name_score > best_score:
            best_score, best_recall, via = name_score, name_recall, "name"
        if row.definition:
            # Definitions are long and repeat common words. They can explain a
            # near-miss in the report, but they must not win the tag on their own.
            def_score, def_recall = score_texts(phrase, row.definition)
            capped = min(def_score * 0.75, 0.68)
            if capped > best_score:
                best_score, best_recall, via = capped, def_recall, "definition"
    for alias in indicator.name_aliases:
        name_score, name_recall = score_texts(alias, row.name)
        if name_score > best_score:
            best_score, best_recall, via = name_score, name_recall, "alias"
    if best_score <= 0:
        return None
    factor = _head_factor(indicator, row)
    if best_score >= 0.9:
        factor = max(factor, 0.88)
    factor *= _action_factor(indicator, row)
    return Candidate(row=row, score=best_score * factor, recall=best_recall, via=via)


def _action(text: str) -> str | None:
    """Reached and trained are different indicators that share the same topic words."""
    lowered = _prepare(text)
    trained = bool(re.search(r"\btrain(?:ed|ing)?\b", lowered))
    reached = bool(re.search(r"\b(?:reached|provided|received|receives|receive|assisted)\b", lowered))
    if trained and not reached:
        return "trained"
    if reached and not trained:
        return "reached"
    return None


def _action_factor(indicator: FormIndicator, row: BankRow) -> float:
    form_action = _action(indicator.question) or _action(indicator.label)
    bank_action = _action(row.name)
    if form_action and bank_action and form_action != bank_action:
        return 0.62
    return 1.0


def _head(text: str) -> str | None:
    lowered = _prepare(text)
    if lowered.startswith("%") or lowered.startswith("percentage of"):
        return "percentage"
    if re.match(r"^(did|does|are all|is your|has your|do you)\b", lowered):
        return "yesno"
    match = re.search(r"how many\s+(.+?)\s+(?:have|has|were|was|are|is|did|can)\b", lowered)
    if not match:
        return None
    noun = match.group(1)
    if "humanitarianservicepoint" in noun:
        return "hsp"
    if "host" in noun and "famil" in noun:
        return "household"
    if "child" in noun:
        return "child"
    if "volunteer" in noun:
        return "volunteer"
    if "branch" in noun:
        return "branch"
    if "household" in noun or "famil" in noun:
        return "household"
    if "good" in noun:
        return "goods"
    if "staff" in noun and "people" not in noun and "volunteer" not in noun:
        return "staff"
    if "people" in noun or "person" in noun:
        return "people"
    return None


def _bank_head(row: BankRow) -> str | None:
    kind = (row.type or "").casefold()
    name = _prepare(row.name)
    if kind in {"percentage", "percent"} or name.startswith("percentage"):
        return "percentage"
    if kind in {"yesno", "yes/no", "boolean"}:
        return "yesno"
    if "humanitarianservicepoint" in name:
        return "hsp"
    if re.search(r"\bhouseholds?\b", name):
        return "household"
    if re.search(r"\bchildren\b|\bchild\b", name):
        return "child"
    if re.search(r"\bvolunteers?\b", name) and "people" not in name:
        return "volunteer"
    if re.search(r"\bbranches\b", name):
        return "branch"
    if re.search(r"\bgoods\b", name):
        return "goods"
    if re.search(r"\bstaff\b", name) and "people" not in name:
        return "staff"
    if re.search(r"\bpeople\b|\bpersons?\b", name):
        return "people"
    return None


def _head_factor(indicator: FormIndicator, row: BankRow) -> float:
    """Down-rank a bank row whose measure (people, households, percentage) disagrees."""
    form_head = _head(indicator.question) or _head(indicator.label)
    bank_head = _bank_head(row)
    if form_head is None or bank_head is None or form_head == bank_head:
        return 1.0
    close = {
        frozenset({"people", "child"}),
        frozenset({"staff", "volunteer"}),
        frozenset({"people", "staff"}),
        frozenset({"people", "volunteer"}),
        frozenset({"people", "household"}),
    }
    if frozenset({form_head, bank_head}) in close:
        return 0.9
    return 0.62


def load_form(path: Path) -> list[FormIndicator]:
    import openpyxl

    workbook = openpyxl.load_workbook(path, data_only=True, read_only=True)
    try:
        survey = {}
        for row in workbook["survey"].iter_rows(min_row=2, values_only=True):
            name = row[1]
            if name and name not in survey:
                survey[name] = row
        indicators = []
        for row in workbook["choices"].iter_rows(min_row=2, values_only=True):
            list_name = str(row[0] or "")
            code = str(row[1] or "").strip()
            if not list_name.startswith("choose_indicators") or not code or code.lower() == "na":
                continue
            label = clean_text(row[2] if len(row) > 2 else "")
            if not label or _NONE_RE.search(label):
                continue
            question_row = survey.get(f"{code}_q")
            question = clean_text(question_row[2]) if question_row and len(question_row) > 2 else label
            hint = ""
            if question_row and len(question_row) > 7 and question_row[7]:
                hint = clean_text(question_row[7])
                hint = hint.split(". ")[0].strip()
                if len(hint) > 320:
                    hint = hint[:320].rsplit(" ", 1)[0]
            indicators.append(
                FormIndicator(
                    code=code,
                    section=_SECTIONS.get(list_name, list_name),
                    label=label,
                    question=question,
                    hint=hint,
                )
            )
        enabling = survey.get("ns_required_indicators")
        if enabling and enabling[2]:
            for line in str(enabling[2]).splitlines():
                label = clean_text(line).lstrip("* ").strip()
                if not label:
                    continue
                indicators.append(
                    FormIndicator(
                        code="enabling",
                        section="Enabling functions",
                        label=label,
                        question=label,
                        hint="",
                    )
                )
        return indicators
    finally:
        workbook.close()


def load_bank() -> tuple[list[BankRow], int]:
    from app.models import IndicatorBank

    rows = []
    emergency_count = 0
    for indicator in IndicatorBank.query.order_by(IndicatorBank.id.asc()).all():
        if indicator.emergency:
            emergency_count += 1
        if indicator.archived:
            continue
        rows.append(
            BankRow(
                id=int(indicator.id),
                name=indicator.name or "",
                definition=indicator.definition or "",
                type=indicator.type or "",
                emergency=bool(indicator.emergency),
                archived=False,
                tags=list(indicator.tags_list),
            )
        )
    return rows, emergency_count


def rank(indicator: FormIndicator, bank: list[BankRow], limit: int = 3) -> list[Candidate]:
    scored = []
    for row in bank:
        candidate = score_row(indicator, row)
        if candidate is not None:
            scored.append(candidate)
    scored.sort(key=lambda item: (item.score, item.recall, item.row.emergency), reverse=True)
    return scored[:limit]


def _near_duplicate(left: str, right: str) -> bool:
    """True when two bank names are the same indicator with a small wording change."""
    left_tokens = set(content_tokens(left))
    right_tokens = set(content_tokens(right))
    if not left_tokens or not right_tokens:
        return False
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens) >= 0.6


def _both_named(indicator: FormIndicator, left: Candidate, right: Candidate) -> bool:
    """True when the form itself names the word that separates the two bank rows."""
    text_tokens = set(content_tokens(f"{indicator.question} {indicator.label}"))
    left_tokens = set(content_tokens(left.row.name))
    right_tokens = set(content_tokens(right.row.name))
    left_only = left_tokens - right_tokens
    right_only = right_tokens - left_tokens
    if not left_only or not right_only:
        return False
    return bool(left_only & text_tokens) and bool(right_only & text_tokens)


def accept(
    indicator: FormIndicator,
    candidates: list[Candidate],
    min_score: float,
    min_margin: float,
) -> list[Candidate]:
    """Bank rows to tag for one form line.

    A near-duplicate of the winner is not a tie. Two different rows are both
    tagged only when the form names each of them (conditional and unconditional
    cash, humanitarian diplomacy or advocacy). Any other close pair is left
    unmatched.
    """
    qualified = [item for item in candidates if item.score >= min_score and item.recall >= MIN_RECALL]
    if not qualified:
        return []
    best = qualified[0]
    chosen = [best]
    for other in qualified[1:]:
        if any(other.row.id == item.row.id for item in chosen):
            continue
        if _near_duplicate(best.row.name, other.row.name):
            continue
        if best.score - other.score >= min_margin:
            break
        if other.score >= 0.85 and _both_named(indicator, best, other):
            chosen.append(other)
            if len(chosen) >= 3:
                break
            continue
        return []
    return chosen


def current_tags(indicator) -> list[str]:
    raw = indicator.tags
    if isinstance(raw, list) and all(isinstance(item, str) for item in raw):
        return list(raw)
    return list(indicator.tags_list)


def _snapshot(indicator) -> dict:
    programs = indicator.related_programs_list
    return {
        "name": indicator.name,
        "type": indicator.type,
        "unit": indicator.unit,
        "fdrs_kpi_code": indicator.fdrs_kpi_code,
        "definition": indicator.definition,
        "name_translations": indicator.name_translations,
        "definition_translations": indicator.definition_translations,
        "aggregated_label": indicator.aggregated_label,
        "aggregated_label_translations": indicator.aggregated_label_translations,
        "area": indicator.area,
        "area_label": indicator.area_label,
        "data_source": indicator.data_source,
        "disaggregation_guidance": indicator.disaggregation_guidance,
        "monitoring_questions": indicator.monitoring_questions,
        "tags": indicator.tags,
        "archived": indicator.archived,
        "comments": indicator.comments,
        "emergency": indicator.emergency,
        "related_programs": ", ".join(programs) if programs else None,
        "sector": indicator.sector,
        "sub_sector": indicator.sub_sector,
    }


def apply_tags(tag: str, bank_ids: list[int], user_email: str | None) -> list[dict]:
    from app.extensions import db
    from app.models import IndicatorBank, IndicatorBankHistory, User

    user = None
    if user_email:
        user = User.query.filter(User.email.ilike(user_email.strip())).first()
        if user is None:
            raise SystemExit(f"No user with email {user_email!r}. History was not written and nothing was tagged.")

    backup = []
    for bank_id in bank_ids:
        indicator = db.session.get(IndicatorBank, bank_id)
        if indicator is None or indicator.archived:
            continue
        tags = current_tags(indicator)
        if any(existing.casefold() == tag.casefold() for existing in tags):
            continue
        backup.append(
            {
                "id": indicator.id,
                "name": indicator.name,
                "emergency": bool(indicator.emergency),
                "tags": tags,
            }
        )
        indicator.tags = tags + [tag]
        if user is not None:
            db.session.add(
                IndicatorBankHistory(
                    indicator_bank_id=indicator.id,
                    user_id=user.id,
                    change_type="UPDATED",
                    change_description=f"Added tag {tag!r} from the Emergency Appeal indicator form.",
                    **_snapshot(indicator),
                )
            )
    return backup


def _clip(text: str, limit: int = 140) -> str:
    text = _SPACE_RE.sub(" ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--form", required=True, help="XLSForm workbook (.xlsx) of the Emergency Appeal indicator tool.")
    parser.add_argument("--apply", action="store_true", help="Write the tag. Default is a dry run.")
    parser.add_argument("--tag", default=TAG, help=f"Tag to add. Default: {TAG!r}.")
    parser.add_argument("--min-score", type=float, default=MIN_SCORE, help=f"Lowest score that can be tagged. Default: {MIN_SCORE}.")
    parser.add_argument("--min-margin", type=float, default=MIN_MARGIN, help=f"Required gap over the next candidate. Default: {MIN_MARGIN}.")
    parser.add_argument("--top", type=int, default=2, help="Candidates to show for each form indicator.")
    parser.add_argument(
        "--user-email",
        default=None,
        help="When set with --apply, record an indicator-bank history row for this user.",
    )
    args = parser.parse_args()
    form_path = Path(args.form)
    if not form_path.is_file():
        print(f"Form not found: {form_path}", file=sys.stderr)
        return 1

    indicators = load_form(form_path)
    if not indicators:
        print(f"No indicators found in {form_path}", file=sys.stderr)
        return 1

    app = create_app()
    with app.app_context():
        bank, emergency_count = load_bank()
        print(
            f"Bank rows searched: {len(bank)} (archived excluded). "
            f"Marked Emergency: {emergency_count}. Form indicators: {len(indicators)}."
        )
        print(f"Tag: {args.tag!r}. {'APPLY' if args.apply else 'DRY RUN'}.")
        print()

        accepted: list[tuple[FormIndicator, Candidate]] = []
        skipped = []
        for indicator in indicators:
            candidates = rank(indicator, bank, limit=max(args.top, 8))
            chosen = accept(indicator, candidates, args.min_score, args.min_margin)
            chosen_ids = {item.row.id for item in chosen}
            status = "TAG" if chosen else "SKIP"
            if chosen:
                accepted.extend((indicator, item) for item in chosen)
            else:
                skipped.append(indicator.code if indicator.code != "enabling" else indicator.label)
            question = _clip(indicator.question or indicator.label)
            print(f"{status}  [{indicator.section}] {indicator.code}")
            print(f"      {question}")
            shown = candidates[: max(args.top, 1)]
            if not shown:
                print("      (no candidate)")
            for candidate in shown:
                mark = "->" if candidate.row.id in chosen_ids else "  "
                emergency = "Emergency" if candidate.row.emergency else "not Emergency"
                already = "already tagged" if any(tag.casefold() == args.tag.casefold() for tag in candidate.row.tags) else ""
                print(
                    f"      {mark} {candidate.score:.2f} recall {candidate.recall:.2f} via {candidate.via}"
                    f"  id {candidate.row.id}  {emergency}  {_clip(candidate.row.name, 160)}"
                    + (f"  [{already}]" if already else "")
                )
            print()

        # One bank row can be the best match for more than one form line. Tag it once.
        by_id: dict[int, dict] = {}
        for indicator, candidate in accepted:
            slot = by_id.setdefault(
                candidate.row.id,
                {
                    "id": candidate.row.id,
                    "name": candidate.row.name,
                    "emergency": candidate.row.emergency,
                    "score": round(candidate.score, 3),
                    "already_tagged": any(tag.casefold() == args.tag.casefold() for tag in candidate.row.tags),
                    "form": [],
                },
            )
            slot["form"].append(
                {
                    "code": indicator.code,
                    "label": indicator.label,
                    "score": round(candidate.score, 3),
                }
            )
            slot["score"] = max(slot["score"], round(candidate.score, 3))

        to_write = [row for row in by_id.values() if not row["already_tagged"]]
        matched_lines = {(item.code, item.label) for item, _candidate in accepted}
        print(
            f"Form lines matched: {len(matched_lines)} of {len(indicators)}. "
            f"Bank rows to tag: {len(to_write)}. "
            f"Already tagged: {sum(1 for row in by_id.values() if row['already_tagged'])}. "
            f"Form lines skipped: {len(skipped)}."
        )

        backup = []
        if args.apply and to_write:
            backup = apply_tags(args.tag, [row["id"] for row in to_write], args.user_email)
            from app.extensions import db

            db.session.commit()
            print(f"Tagged {len(backup)} indicator(s).")
        elif args.apply:
            print("Nothing to write.")

        summary = {
            "tag": args.tag,
            "apply": bool(args.apply),
            "form": str(form_path),
            "emergency_in_bank": emergency_count,
            "form_indicators": len(indicators),
            "form_lines_matched": len(matched_lines),
            "bank_rows": list(by_id.values()),
            "skipped_form_codes": skipped,
            "backup": backup,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
