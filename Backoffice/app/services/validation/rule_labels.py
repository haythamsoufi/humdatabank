"""Human-readable labels for validation rule codes."""

from __future__ import annotations

RULE_LABELS: dict[str, str] = {
    "indicator_not_reported": "Not reported",
    "not_reported": "Not reported",
    "non_zero": "Not reported",  # legacy code before rename migration
}


def _pack_rule_label(rule_code: str) -> str | None:
    """Label declared by whichever product pack owns this rule."""
    from app.services.validation.pack_registry import list_packs

    for pack in list_packs():
        for rule in pack.rules:
            if getattr(rule, "code", None) != rule_code:
                continue
            label = getattr(rule, "label", None)
            if isinstance(label, str) and label.strip():
                return label.strip()
    return None


def format_rule_label(rule_code: str | None) -> str:
    if not rule_code:
        return ""
    if rule_code in RULE_LABELS:
        return RULE_LABELS[rule_code]
    contributed = _pack_rule_label(rule_code)
    if contributed:
        return contributed
    return rule_code.replace("_", " ").title()


def format_rule_labels(rule_codes: list[str]) -> list[str]:
    labels: list[str] = []
    seen: set[str] = set()
    for code in rule_codes:
        label = format_rule_label(code)
        key = label.casefold()
        if not label or key in seen:
            continue
        seen.add(key)
        labels.append(label)
    return labels
