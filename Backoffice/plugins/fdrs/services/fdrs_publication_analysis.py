"""Flag large variations and outliers in an FDRS publication preview.

Used by ``get_assignment_publication_summary`` so the Manage Publication UI can
show a "review before publish" list. Thresholds are publication-specific (not
the per-country validation-matrix fractions): they answer "what would look
surprising on the public site?", not "did this NS breach its KPI check?".
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# Relative change vs last published snapshot or previous period.
VARIATION_PCT_MEDIUM = 0.50  # 50%
VARIATION_PCT_HIGH = 1.00    # 100%

# Tukey fences on peer % changes for the same indicator (same assignment).
OUTLIER_IQR_K = 1.5
OUTLIER_MIN_PEERS = 8

# Share of the assignment-wide (all-country) total for the same indicator.
# India at 4M of 18M volunteers is ~22% → high.
GLOBAL_SHARE_MEDIUM = 0.10
GLOBAL_SHARE_HIGH = 0.20
GLOBAL_IMPACT_MEDIUM = 0.05
GLOBAL_IMPACT_HIGH = 0.10
GLOBAL_SHARE_MIN_COUNTRIES = 5

REASON_CLEARED = "cleared"
REASON_FROM_ZERO = "from_zero"
REASON_LARGE_VARIATION = "large_variation"
REASON_OUTLIER = "outlier"
REASON_GLOBAL_SHARE = "global_share"
REASON_GLOBAL_IMPACT = "global_impact"

VS_PUBLISHED = "published"
VS_PRIOR = "prior"

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
_SEVERITY_RANK = {SEVERITY_HIGH: 2, SEVERITY_MEDIUM: 1}


def coerce_numeric(value: Any) -> Optional[float]:
    """Parse a stored numeric / string value. Blank, non-numeric → None."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if value != value:  # NaN
            return None
        return float(value)
    text = str(value).strip().replace(",", "")
    if text == "":
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def relative_change(current: float, baseline: float) -> Optional[float]:
    """(current - baseline) / baseline. None when baseline is 0 (undefined %)."""
    if baseline == 0:
        return None
    return (current - baseline) / baseline


def variation_severity(pct: Optional[float]) -> Optional[str]:
    if pct is None:
        return None
    magnitude = abs(pct)
    if magnitude >= VARIATION_PCT_HIGH:
        return SEVERITY_HIGH
    if magnitude >= VARIATION_PCT_MEDIUM:
        return SEVERITY_MEDIUM
    return None


def _quantile(sorted_vals: Sequence[float], p: float) -> float:
    """Linear-interpolation quantile for a non-empty sorted sequence."""
    n = len(sorted_vals)
    if n == 1:
        return float(sorted_vals[0])
    idx = (n - 1) * p
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return float(sorted_vals[lo]) * (1.0 - frac) + float(sorted_vals[hi]) * frac


def iqr_outlier_mask(
    values: Sequence[float],
    *,
    k: float = OUTLIER_IQR_K,
    min_n: int = OUTLIER_MIN_PEERS,
) -> List[bool]:
    """Tukey fences. All-False when there are too few peers or IQR is 0."""
    n = len(values)
    if n < min_n:
        return [False] * n
    ordered = sorted(float(v) for v in values)
    q1 = _quantile(ordered, 0.25)
    q3 = _quantile(ordered, 0.75)
    iqr = q3 - q1
    if iqr == 0:
        return [False] * n
    low, high = q1 - k * iqr, q3 + k * iqr
    return [v < low or v > high for v in values]


def _worse_severity(a: Optional[str], b: Optional[str]) -> Optional[str]:
    if _SEVERITY_RANK.get(a or "", 0) >= _SEVERITY_RANK.get(b or "", 0):
        return a
    return b


def _flag_sort_key(flag: Dict[str, Any]) -> Tuple:
    pcts = [abs(r["pct"]) for r in flag["reasons"] if r.get("pct") is not None]
    shares = [
        float(r["share"])
        for r in flag["reasons"]
        if r.get("code") == REASON_GLOBAL_SHARE and r.get("share") is not None
    ]
    return (
        -_SEVERITY_RANK.get(flag.get("severity") or "", 0),
        -(max(shares) if shares else 0.0),
        -(max(pcts) if pcts else 0.0),
        flag.get("country_name") or "",
        flag.get("label") or "",
    )


def global_share_severity(share: Optional[float]) -> Optional[str]:
    if share is None:
        return None
    if share >= GLOBAL_SHARE_HIGH:
        return SEVERITY_HIGH
    if share >= GLOBAL_SHARE_MEDIUM:
        return SEVERITY_MEDIUM
    return None


def global_impact_severity(impact: Optional[float]) -> Optional[str]:
    if impact is None:
        return None
    if impact >= GLOBAL_IMPACT_HIGH:
        return SEVERITY_HIGH
    if impact >= GLOBAL_IMPACT_MEDIUM:
        return SEVERITY_MEDIUM
    return None


def analyze_publication_rows(
    rows: Iterable[Dict[str, Any]],
    *,
    prior_numeric_by_key: Optional[Dict[Tuple[int, int], float]] = None,
    prior_period_name: Optional[str] = None,
    global_totals_by_item: Optional[Dict[int, float]] = None,
    global_reporters_by_item: Optional[Dict[int, int]] = None,
) -> Dict[str, Any]:
    """
    Build the analysis payload for one assignment preview.

    Each ``row`` is a public item — pending (new / changed / removed / source)
    or already published (unchanged). Already-published rows are still checked
    against the previous period and assignment-wide share, so a fully published
    assignment can still surface values that would be questioned.

        assignment_entity_status_id, country_id, country_name, country_iso3,
        form_item_id, label, kind, current_value, published_value,
        current_numeric, published_numeric
    """
    prior_numeric_by_key = prior_numeric_by_key or {}
    global_totals_by_item = global_totals_by_item or {}
    global_reporters_by_item = global_reporters_by_item or {}
    prepared: List[Dict[str, Any]] = []

    for raw in rows:
        kind = raw.get("kind")
        if kind not in ("new", "changed", "removed", "unchanged", "source"):
            continue
        country_id = raw.get("country_id")
        form_item_id = raw.get("form_item_id")
        current_num = coerce_numeric(raw.get("current_numeric"))
        if current_num is None:
            current_num = coerce_numeric(raw.get("current_value"))
        published_num = coerce_numeric(raw.get("published_numeric"))
        if published_num is None:
            published_num = coerce_numeric(raw.get("published_value"))
        prior_num = None
        if country_id is not None and form_item_id is not None:
            prior_num = prior_numeric_by_key.get((int(country_id), int(form_item_id)))

        reasons: List[Dict[str, Any]] = []
        severity: Optional[str] = None
        pct_vs_published = None
        pct_vs_prior = None

        if kind == "removed":
            reasons.append({"code": REASON_CLEARED, "vs": VS_PUBLISHED, "pct": None})
            severity = SEVERITY_HIGH if published_num not in (None, 0) else SEVERITY_MEDIUM

        if kind == "changed" and current_num is not None and published_num is not None:
            if published_num == 0 and current_num != 0:
                reasons.append({"code": REASON_FROM_ZERO, "vs": VS_PUBLISHED, "pct": None})
                severity = _worse_severity(severity, SEVERITY_HIGH)
            else:
                pct_vs_published = relative_change(current_num, published_num)
                sev = variation_severity(pct_vs_published)
                if sev:
                    reasons.append({
                        "code": REASON_LARGE_VARIATION,
                        "vs": VS_PUBLISHED,
                        "pct": pct_vs_published,
                    })
                    severity = _worse_severity(severity, sev)

        if kind in ("new", "changed", "unchanged", "source") and current_num is not None and prior_num is not None:
            if prior_num == 0 and current_num != 0:
                reasons.append({"code": REASON_FROM_ZERO, "vs": VS_PRIOR, "pct": None})
                severity = _worse_severity(severity, SEVERITY_HIGH)
            else:
                pct_vs_prior = relative_change(current_num, prior_num)
                sev = variation_severity(pct_vs_prior)
                if sev:
                    reasons.append({
                        "code": REASON_LARGE_VARIATION,
                        "vs": VS_PRIOR,
                        "pct": pct_vs_prior,
                    })
                    severity = _worse_severity(severity, sev)

        if form_item_id is not None:
            total = global_totals_by_item.get(int(form_item_id))
            reporters = global_reporters_by_item.get(int(form_item_id), 0)
        else:
            total = None
            reporters = 0
        if total and total > 0 and reporters >= GLOBAL_SHARE_MIN_COUNTRIES:
            share = None
            if kind == "removed" and published_num not in (None, 0):
                share = abs(published_num) / (total + abs(published_num))
            elif current_num not in (None, 0):
                share = abs(current_num) / total
            sev = global_share_severity(share)
            if sev and share is not None:
                reasons.append({
                    "code": REASON_GLOBAL_SHARE,
                    "vs": "global",
                    "pct": share,
                    "share": share,
                    "global_total": total,
                })
                severity = _worse_severity(severity, sev)

            baseline = published_num if published_num is not None else prior_num
            impact = None
            if kind == "removed" and published_num not in (None, 0):
                impact = abs(published_num) / (total + abs(published_num))
            elif kind == "changed" and current_num is not None and baseline is not None:
                impact = abs(current_num - baseline) / total
            isev = global_impact_severity(impact)
            if isev and impact is not None and (share is None or abs(impact - share) > 0.01):
                reasons.append({
                    "code": REASON_GLOBAL_IMPACT,
                    "vs": "global",
                    "pct": impact,
                    "global_total": total,
                })
                severity = _worse_severity(severity, isev)

        comparable_pct = pct_vs_published if pct_vs_published is not None else pct_vs_prior
        comparable_vs = (
            VS_PUBLISHED if pct_vs_published is not None
            else (VS_PRIOR if pct_vs_prior is not None else None)
        )

        prepared.append({
            "assignment_entity_status_id": raw.get("assignment_entity_status_id"),
            "country_id": country_id,
            "country_name": raw.get("country_name"),
            "country_iso3": raw.get("country_iso3"),
            "form_item_id": form_item_id,
            "label": raw.get("label"),
            "kind": kind,
            "current_value": raw.get("current_value"),
            "published_value": raw.get("published_value"),
            "prior_value": prior_num,
            "current_numeric": current_num,
            "published_numeric": published_num,
            "prior_numeric": prior_num,
            "pct_vs_published": pct_vs_published,
            "pct_vs_prior": pct_vs_prior,
            "comparable_pct": comparable_pct,
            "comparable_vs": comparable_vs,
            "reasons": reasons,
            "severity": severity,
        })

    by_item: Dict[int, List[int]] = {}
    for idx, item in enumerate(prepared):
        fid = item.get("form_item_id")
        if fid is None or item.get("comparable_pct") is None:
            continue
        by_item.setdefault(int(fid), []).append(idx)

    for indexes in by_item.values():
        pcts = [prepared[i]["comparable_pct"] for i in indexes]
        mask = iqr_outlier_mask(pcts)
        for i, is_out in zip(indexes, mask):
            if not is_out:
                continue
            prepared[i]["reasons"].append({
                "code": REASON_OUTLIER,
                "vs": prepared[i]["comparable_vs"],
                "pct": prepared[i]["comparable_pct"],
            })
            prepared[i]["severity"] = _worse_severity(prepared[i]["severity"], SEVERITY_MEDIUM)

    flags = [item for item in prepared if item["reasons"]]
    for flag in flags:
        flag.pop("comparable_pct", None)
        flag.pop("comparable_vs", None)
    flags.sort(key=_flag_sort_key)

    country_ids = {f["assignment_entity_status_id"] for f in flags}
    counts = {
        REASON_CLEARED: 0,
        REASON_FROM_ZERO: 0,
        REASON_LARGE_VARIATION: 0,
        REASON_OUTLIER: 0,
        REASON_GLOBAL_SHARE: 0,
        REASON_GLOBAL_IMPACT: 0,
    }
    for flag in flags:
        seen = set()
        for reason in flag["reasons"]:
            code = reason.get("code")
            if code in counts and code not in seen:
                counts[code] += 1
                seen.add(code)

    review_count_by_aes: Dict[int, int] = {}
    for flag in flags:
        aes_id = flag.get("assignment_entity_status_id")
        if aes_id is None:
            continue
        review_count_by_aes[int(aes_id)] = review_count_by_aes.get(int(aes_id), 0) + 1

    return {
        "flag_count": len(flags),
        "country_count": len(country_ids),
        "prior_period_name": prior_period_name,
        "thresholds": {
            "medium_pct": VARIATION_PCT_MEDIUM,
            "high_pct": VARIATION_PCT_HIGH,
            "global_share_medium": GLOBAL_SHARE_MEDIUM,
            "global_share_high": GLOBAL_SHARE_HIGH,
        },
        "counts": counts,
        "review_count_by_aes": review_count_by_aes,
        "flags": flags,
    }
