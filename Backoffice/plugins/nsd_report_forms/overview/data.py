"""Read-only data layer for the NSD admin project overview.

Every project is an Initiative (core entity type). Its hidden "project record" is its row in the assignment of the
NSD Project profile template (period ``Project``); its reports are its rows in the quarterly assignments (``Y1Q2``)
and the final report assignment (``Final``). Answers are FormData rows keyed by form item label. The list needs a handful of set-based queries (templates/items, project
answers, report assignments, report answers, countries) and aggregates in Python, so there is no N+1.
Nothing here writes.
"""
import calendar
import datetime as dt
import json
import re
from collections import defaultdict
from typing import Dict, Iterable, List, Optional

from sqlalchemy import and_, func

from app import db
from app.models import (AssignedForm, AssignmentEntityStatus, Country, FormData, FormItem, FormTemplate,
                        FormTemplateVersion)
from app.models.enums import EntityType
from app.models.initiatives import Initiative
from app.models.organization import NationalSociety
from app.utils.datetime_helpers import utcnow

from plugins.nsd_report_forms.importer import layout

PROFILE, QUARTER, FINAL = 'profile', 'CBF quarter', 'CBF final report'

DONE_STATUSES = ('submitted', 'approved')
IDLE_STATUSES = DONE_STATUSES + ('cancelled',)
PROJECT_STATUSES = layout.STATUSES  # Open, Active, Closed, Archived

PROFILE_LABELS = {
    'ns': 'National Society', 'title': 'Title', 'reference': 'Reference', 'status': 'Status',
    'modality': 'Funding modality', 'categories': 'Categories / thematics', 'start': 'Start date', 'end': 'End date',
    'granted': 'Amount granted (CHF)', 'overview': 'Overview of the initiative as planned',
    'ns_focal': 'NS focal person', 'ns_focal_email': 'NS focal person email',
    'pm': 'IFRC project manager', 'pm_email': 'IFRC project manager email',
}
QUARTER_LABELS = {'overall': 'Overall implementation assessment',
                  'activities': "Activities' implementation according to the plan",
                  'spending': 'Spending', 'author': 'Review author(s)'}
FINAL_LABELS = {'overall': 'Overall implementation assessment', 'activities': "Activities' implementation",
                'author': 'Review author(s)', 'frame': 'Outcomes and outputs'}
ACTUAL_CELL = 'Amount (CHF)_Actual amount spent to date (CHF)'
EXPECTED_CELL = 'Amount (CHF)_Expected spending (CHF)'


# ------------------------------------------------------------------ helpers
def status_value(s) -> str:
    return str(getattr(s, 'value', s) or '')


def parse_date(v) -> Optional[dt.date]:
    v = str(v or '').strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            return dt.datetime.strptime(v[:10], fmt).date()
        except ValueError:
            continue
    return None


def parse_amount(v) -> Optional[float]:
    if v in (None, ''):
        return None
    try:
        return float(str(v).replace(',', '').replace(' ', ''))
    except ValueError:
        return None


def assessment_light(value: Optional[str]) -> str:
    """green / amber / red / grey for the assessment wordings of the quarterly and final report."""
    v = (value or '').casefold()
    if not v:
        return 'grey'
    if 'partial' in v:
        return 'amber'
    if 'not on track' in v or 'not achieved' in v:
        return 'red'
    if 'on track' in v or 'achieved' in v:
        return 'green'
    return 'grey'


def period_sort_key(period: str):
    m = re.match(r'^Y(\d+)Q(\d+)$', period or '')
    return (0, int(m.group(1)), int(m.group(2)), '') if m else (1, 0, 0, period or '')


def _template_items(key: str):
    """(template id, {label: item id}) of the published version of one NSD template, or (None, {})."""
    row = (db.session.query(FormTemplate.id, FormTemplateVersion.id)
           .join(FormTemplateVersion, FormTemplateVersion.id == FormTemplate.published_version_id)
           .filter(FormTemplateVersion.name == layout.TEMPLATE_NAMES[key]).first())
    if not row:
        return None, {}
    items = {label: iid for iid, label in db.session.query(FormItem.id, FormItem.label)
             .filter(FormItem.version_id == row[1], FormItem.archived.is_(False)).all()}
    return row[0], items


class Ctx:
    """Template and item ids, loaded once per request."""

    def __init__(self):
        self.tpl: Dict[str, Optional[int]] = {}
        self.items: Dict[str, Dict[str, int]] = {}
        for key in (PROFILE, QUARTER, FINAL):
            self.tpl[key], self.items[key] = _template_items(key)
        self.problems = [f'Template "{layout.TEMPLATE_NAMES[k]}" is not published.' for k in (PROFILE, QUARTER, FINAL)
                         if self.tpl[k] is None]

    def ids(self, key: str, labels: Dict[str, str]) -> Dict[int, str]:
        """item id -> short key, for the labels that exist in the template."""
        return {self.items[key][label]: short for short, label in labels.items() if label in self.items[key]}


# ------------------------------------------------------------------ queries
def norm_email(v) -> str:
    return str(v or '').strip().lower()


def _initiative_rows(query):
    """Join the initiative (and its country, through the National Society) to an AssignmentEntityStatus query."""
    return (query
            .join(Initiative, and_(AssignmentEntityStatus.entity_type == EntityType.initiative.value,
                                   Initiative.id == AssignmentEntityStatus.entity_id))
            .outerjoin(NationalSociety, NationalSociety.id == Initiative.national_society_id))


def _profiles(ctx: Ctx, reference: Optional[str] = None, with_logframe: bool = False,
              pm_email: Optional[str] = None) -> Dict[str, dict]:
    """reference -> project dict (simple answers, the expected-spending cell, optionally the planned logframe).

    ``pm_email`` keeps only the projects whose "IFRC project manager email" equals it (trimmed, case-insensitive).
    """
    if ctx.tpl[PROFILE] is None:
        return {}
    by_item = ctx.ids(PROFILE, PROFILE_LABELS)
    spend_id = ctx.items[PROFILE].get('Expected spending')
    frame_id = ctx.items[PROFILE].get('Outcomes and outputs')
    wanted = list(by_item) + ([spend_id] if spend_id else []) + ([frame_id] if with_logframe and frame_id else [])
    q = _initiative_rows(
        db.session.query(AssignmentEntityStatus.id, Initiative.reference, Initiative.id, NationalSociety.country_id,
                         FormData.form_item_id, FormData.value, FormData.numeric_value, FormData.disagg_data)
        .select_from(AssignmentEntityStatus)
        .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
        .join(FormData, FormData.assignment_entity_status_id == AssignmentEntityStatus.id)
        .filter(AssignedForm.template_id == ctx.tpl[PROFILE], FormData.form_item_id.in_(wanted)))
    if reference:
        q = q.filter(Initiative.reference == reference)
    if pm_email is not None:
        pm_item = ctx.items[PROFILE].get(PROFILE_LABELS['pm_email'])
        pm_email = norm_email(pm_email)
        if not pm_item or not pm_email:
            return {}
        mine = (db.session.query(FormData.assignment_entity_status_id)
                .filter(FormData.form_item_id == pm_item, func.lower(func.trim(FormData.value)) == pm_email))
        q = q.filter(AssignmentEntityStatus.id.in_(mine))
    projects: Dict[int, dict] = {}
    for aes_id, ref, initiative_id, country_id, item_id, value, numeric, disagg in q.all():
        p = projects.setdefault(aes_id, {'aes_id': aes_id, 'reference': ref, 'initiative_id': initiative_id,
                                         'country_id': country_id,
                                         'expected': None, 'logframe': None})
        if item_id == spend_id:
            p['expected'] = parse_amount((disagg or {}).get(EXPECTED_CELL))
        elif item_id == frame_id:
            p['logframe'] = disagg if isinstance(disagg, list) else None
        else:
            short = by_item[item_id]
            if short != 'reference':   # the initiative's own reference is the one that counts
                p[short] = value if value not in (None, '') else (numeric if numeric is not None else '')
    out: Dict[str, dict] = {}
    for p in projects.values():
        p['status'] = p.get('status') or 'Open'
        p['granted'] = parse_amount(p.get('granted'))
        p['start'], p['end'] = parse_date(p.get('start')), parse_date(p.get('end'))
        out[p['reference']] = p
    return out


def _report_rows(ctx: Ctx, reference: Optional[str] = None, with_answers: bool = True,
                 references: Optional[Iterable[str]] = None) -> Dict[str, List[dict]]:
    """reference -> report dicts (assignment, status, due date and the answers the overview needs)."""
    tpl_ids = {ctx.tpl[QUARTER]: QUARTER, ctx.tpl[FINAL]: FINAL}
    tpl_ids.pop(None, None)
    if not tpl_ids:
        return {}
    q = _initiative_rows(
        db.session.query(AssignedForm.template_id, AssignedForm.period_name, AssignedForm.is_active, Initiative.reference,
                         Initiative.is_active, NationalSociety.country_id,
                         AssignmentEntityStatus.id, AssignmentEntityStatus.status,
                         AssignmentEntityStatus.due_date, AssignmentEntityStatus.completion_rate,
                         AssignmentEntityStatus.submitted_at, AssignmentEntityStatus.status_timestamp)
        .select_from(AssignmentEntityStatus)
        .join(AssignedForm, AssignedForm.id == AssignmentEntityStatus.assigned_form_id)
        .filter(AssignedForm.template_id.in_(list(tpl_ids))))
    if reference:
        q = q.filter(Initiative.reference == reference)
    if references is not None:
        wanted_refs = list(references)
        if not wanted_refs:
            return {}
        q = q.filter(Initiative.reference.in_(wanted_refs))
    reports: Dict[int, dict] = {}
    for (tpl_id, period, af_active, ref, init_active, country_id, aes_id, status, due, comp, submitted_at,
         status_ts) in q.all():
        reports[aes_id] = {'aes_id': aes_id, 'reference': ref, 'period': period, 'kind': tpl_ids[tpl_id],
                           'active': bool(af_active and init_active), 'status': status_value(status), 'due': due,
                           'completion': float(comp) if comp is not None else None,
                           'submitted_at': submitted_at or status_ts, 'country_id': country_id,
                           'overall': None, 'activities': None, 'actual': None, 'author': None, 'frame': None}
    if reports and with_answers:
        _attach_answers(ctx, reports)
    by_ref: Dict[str, List[dict]] = defaultdict(list)
    for r in reports.values():
        by_ref[r['reference']].append(r)
    return by_ref


def _attach_answers(ctx: Ctx, reports: Dict[int, dict]):
    ids = {}
    for key, labels in ((QUARTER, QUARTER_LABELS), (FINAL, FINAL_LABELS)):
        for item_id, short in ctx.ids(key, labels).items():
            ids[item_id] = (key, short)
    ids_list = list(ids)
    aes_ids = list(reports)
    for i in range(0, len(aes_ids), 5000):
        chunk = aes_ids[i:i + 5000]
        rows = (db.session.query(FormData.assignment_entity_status_id, FormData.form_item_id, FormData.value,
                                 FormData.disagg_data)
                .filter(FormData.assignment_entity_status_id.in_(chunk), FormData.form_item_id.in_(ids_list)).all())
        for aes_id, item_id, value, disagg in rows:
            kind, short = ids[item_id]
            r = reports[aes_id]
            if r['kind'] != kind:
                continue
            if short == 'spending':
                r['actual'] = parse_amount((disagg or {}).get(ACTUAL_CELL))
            elif short == 'frame':
                r['frame'] = disagg if isinstance(disagg, list) else None
            elif value:
                r[short] = str(value)


def _countries() -> Dict[int, dict]:
    return {cid: {'name': name, 'region': region or '', 'iso3': iso3}
            for cid, name, region, iso3 in db.session.query(Country.id, Country.name, Country.region, Country.iso3).all()}


# ------------------------------------------------------------------ MOMO wording and groups
OPEN_GROUP = ('Open', 'Active')        # MOMO: "Open" also covers Ongoing / On hold
CLOSED_GROUP = ('Closed', 'Archived')  # MOMO: "Closed" also covers Archived, Withdrawn ...


def matches_status(status: str, wanted: str) -> bool:
    if wanted == 'Open':
        return status in OPEN_GROUP
    if wanted == 'Closed':
        return status in CLOSED_GROUP
    return status == wanted


def add_months(d: dt.date, n: int) -> dt.date:
    y, m = divmod(d.year * 12 + d.month - 1 + n, 12)
    return dt.date(y, m + 1, min(d.day, calendar.monthrange(y, m + 1)[1]))


def _quarter_index(period: str) -> Optional[int]:
    m = re.match(r'^Y(\d+)Q(\d+)$', period or '')
    return (int(m.group(1)) - 1) * 4 + int(m.group(2)) - 1 if m else None


def _quarter_label(idx: int) -> str:
    return f'Y{idx // 4 + 1}Q{idx % 4 + 1}'


def _project_row(p: dict, countries: Dict[int, dict]) -> dict:
    c = countries.get(p['country_id'], {})
    return {**p, 'country': c.get('name') or p.get('ns') or '', 'region': c.get('region', '')}


# ------------------------------------------------------------------ list page (MOMO "welcome")
def project_list(fund: str = '', region: str = '', country: str = '', status: str = '') -> dict:
    """MOMO's welcome page for CBF: filter choices, totals and the project list, all from the project records."""
    ctx = Ctx()
    if ctx.tpl[PROFILE] is None:
        return {'problems': ctx.problems}
    countries = _countries()
    rows = [_project_row(p, countries) for p in _profiles(ctx).values()]
    rows.sort(key=lambda r: ((r['country'] or '').casefold(), r['reference']))
    fund_types = ['CBF'] if rows else []
    if fund not in ('', 'CBF'):
        rows = []  # NSIA / ESF are not part of the Databank data yet

    # a country that is not in the selected region is dropped (MOMO)
    if region and country and not any(r['country'] == country and r['region'] == region for r in rows):
        country = ''

    def in_region(r):
        return not region or r['region'] == region

    statuses = {r['status'] for r in rows if in_region(r) and (not country or r['country'] == country) and r['status']}
    if 'Active' in statuses:
        statuses = (statuses - {'Active'}) | {'Open'}   # MOMO leaves "Ongoing" out, "Open" covers it
    regions = {r['region'] for r in rows if r['region'] and (not status or matches_status(r['status'], status))}
    countries_ok = {r['country'] for r in rows if r['country'] and in_region(r)
                    and (not status or matches_status(r['status'], status))}

    base = [r for r in rows if in_region(r) and (not country or r['country'] == country)]  # statistics ignore status
    shown = [r for r in base if not status or matches_status(r['status'], status)]
    stats = {
        'total': len(base),
        'open': sum(1 for r in base if r['status'] in OPEN_GROUP),
        'closed': sum(1 for r in base if r['status'] in CLOSED_GROUP),
        'funds': sum(r['granted'] or 0 for r in base),
        'with_amount': sum(1 for r in base if (r['granted'] or 0) > 0),
    }
    return {'problems': [], 'projects': shown, 'stats': stats,
            'fund_filter': fund if fund == 'CBF' else '', 'region_filter': region, 'country_filter': country,
            'status_filter': status, 'all_fund_types': fund_types, 'all_regions': sorted(regions),
            'all_countries': sorted(countries_ok), 'all_statuses': sorted(statuses)}


# ------------------------------------------------------------------ project page (MOMO "reference_detail")
def _recalculate_outcome_budgets(outcomes):
    """MOMO: an outcome's actual budget is the sum of its outputs' actual budgets."""
    for o in outcomes:
        outs = o.get('outputs')
        if isinstance(outs, list) and outs:
            total = sum(parse_amount(x.get('actual_budget')) or 0 for x in outs if isinstance(x, dict))
            o['actual_budget'] = total if total > 0 else ''
    return outcomes


def _outcomes(frame) -> List[dict]:
    if isinstance(frame, str):
        try:
            frame = json.loads(frame)
        except ValueError:
            frame = None
    outcomes = [o for o in (frame if isinstance(frame, list) else []) if isinstance(o, dict)]
    return _recalculate_outcome_budgets(outcomes)


def project_detail(reference: str, pm_email: Optional[str] = None) -> Optional[dict]:
    """The project page data. With ``pm_email`` only a project that names that IFRC project manager is returned."""
    today = utcnow().date()
    ctx = Ctx()
    if ctx.problems:
        return None
    p = _profiles(ctx, reference=reference, pm_email=pm_email).get(reference)
    if not p or (pm_email is not None and norm_email(p.get('pm_email')) != norm_email(pm_email)):
        return None
    row = _project_row(p, _countries())
    reports = _report_rows(ctx, reference=reference).get(reference, [])
    quarters = [r for r in reports if r['kind'] == QUARTER]
    final = next((r for r in reports if r['kind'] == FINAL), None)
    base = row.get('expected') or row.get('granted')

    last_idx = max((i for i in (_quarter_index(q['period']) for q in quarters) if i is not None), default=None)
    # a final report that was only prefilled by the import (still "pending") has no results to show
    outcomes = _outcomes(final['frame']) if final and final['status'] != 'pending' else []
    for r in reports:
        r['done'] = r['status'] in DONE_STATUSES
        r['submitted'] = r['submitted_at'] if r['done'] else None
        due = r['due'].date() if r['due'] else None
        r['deadline_status'] = None
        if due:
            r['deadline_status'] = 'red' if today > due else ('yellow' if today >= due - dt.timedelta(days=14) else None)
        r['rate'] = None
        if r['kind'] == QUARTER:
            idx = _quarter_index(r['period'])
            r['label'] = r['period']
            # MOMO stores the reporting period; here it follows from the project start (3-month quarters)
            r['start'] = add_months(p['start'], 3 * idx) if idx is not None and p['start'] else None
            r['end'] = add_months(p['start'], 3 * idx + 3) if idx is not None and p['start'] else None
            if r['actual'] is not None and base:
                r['rate'] = round(100.0 * r['actual'] / base, 2)
        else:
            r['label'] = _quarter_label(last_idx + 1) if last_idx is not None else 'Final'
            r['start'], r['end'] = p['start'], p['end']
            planned = sum(parse_amount(o.get('planned_budget')) or 0 for o in outcomes)
            actual = sum(parse_amount(o.get('actual_budget')) or 0 for o in outcomes)
            if planned and actual:
                r['rate'] = round(100.0 * actual / planned, 2)
    reports.sort(key=lambda r: (r['due'] is None, r['due'] or dt.datetime.max, r['kind'] == FINAL))

    outcomes_actual = sum(parse_amount(o.get('actual_budget')) or 0 for o in outcomes)
    actuals = [q['actual'] for q in quarters if q['actual'] is not None]
    if outcomes_actual > 0:
        expenditure = outcomes_actual
    else:
        expenditure = max(actuals) if actuals else None  # quarterly actuals are "to date"
    row.update({'reports': reports, 'expenditure': expenditure, 'outcomes': outcomes,
                'categories_list': [c.strip() for c in re.split(r'[,;]', row.get('categories') or '') if c.strip()]})
    return row


# ------------------------------------------------------------------ personal PM page (MOMO "pm_personal")
SPEND_AMBER, SPEND_GREEN = 45.0, 75.0   # MOMO: spending rate < 45 red, < 75 amber
LIGHT_LABELS = {'green': 'On track', 'amber': 'Partially on track', 'red': 'Not on track', 'grey': 'No data'}


def _naive(d: Optional[dt.datetime]) -> dt.datetime:
    return d.replace(tzinfo=None) if d else dt.datetime.min


def spend_light(rate: Optional[float]) -> str:
    if rate is None:
        return 'grey'
    return 'green' if rate >= SPEND_GREEN else ('amber' if rate >= SPEND_AMBER else 'red')


def _pm_project(p: dict, reports: List[dict], countries: Dict[int, dict], today: dt.date) -> dict:
    """One card of the PM page: the latest report's traffic lights (MOMO takes the latest submission with an
    overall assessment), spending rate (quarterly reports only, as in MOMO) and the next report deadline."""
    base = p.get('expected') or p.get('granted')
    done = [r for r in reports if r['overall'] and r['status'] not in ('pending', 'cancelled')]
    latest = max(done, key=lambda r: _naive(r['submitted_at'] or r['due']), default=None)
    overall = activities = rate = None
    if latest:
        overall = assessment_light(latest['overall'])
        if latest['kind'] == QUARTER:
            activities = assessment_light(latest['activities']) if latest['activities'] else None
            if latest['actual'] is not None and base:
                rate = round(100.0 * latest['actual'] / base, 1)
    lights = [x for x in (overall, activities) if x]
    sr = spend_light(rate)
    if 'red' in lights or sr == 'red':
        severity = 'red'
    elif 'amber' in lights or sr == 'amber':
        severity = 'amber'
    elif lights or rate is not None:
        severity = 'green'
    else:
        severity = 'grey'
    is_open = p['status'] in OPEN_GROUP
    nxt = None
    if is_open:
        # periods before the latest submitted one that were never reported (import history) are not "next"
        cut = max((_naive(r['due']) for r in reports if r['status'] in DONE_STATUSES and r['due']), default=None)
        pending = [r for r in reports if r['status'] not in IDLE_STATUSES and r['due']
                   and (cut is None or _naive(r['due']) >= cut)]
        if pending:
            r = min(pending, key=lambda x: (_naive(x['due']), x['kind'] == FINAL))
            due = r['due'].date()
            nxt = {'label': r['period'] if r['kind'] == QUARTER else 'Final report', 'due': due,
                   'status': 'red' if today > due else ('yellow' if today >= due - dt.timedelta(days=14) else None)}
    c = countries.get(p['country_id'], {})
    return {'reference': p['reference'], 'title': p.get('title') or p['reference'],
            'country': c.get('name') or p.get('ns') or '', 'status': p['status'], 'is_open': is_open,
            'amount': p.get('granted') or 0, 'overall': overall, 'activities': activities, 'spending': rate,
            'spending_light': sr, 'severity': severity, 'next_deadline': nxt}


def pm_projects(email: str) -> dict:
    """The projects whose "IFRC project manager email" equals ``email`` (trimmed, case-insensitive), as cards.

    Three set-based queries (profiles of that PM, their reports and report answers, countries); no per-project query.
    """
    email = norm_email(email)
    empty = {'problems': [], 'projects': [], 'pm_name': '', 'email': email}
    ctx = Ctx()
    if ctx.problems:
        return {**empty, 'problems': ctx.problems}
    profiles = {ref: p for ref, p in _profiles(ctx, pm_email=email).items() if norm_email(p.get('pm_email')) == email}
    if not profiles:
        return empty
    today = utcnow().date()
    reports = _report_rows(ctx, references=list(profiles))
    countries = _countries()
    cards = [_pm_project(p, reports.get(ref, []), countries, today) for ref, p in profiles.items()]
    sev_order = {'red': 0, 'amber': 1, 'green': 2, 'grey': 3}
    cards.sort(key=lambda c: (sev_order[c['severity']], c['status'], c['country'].casefold(), c['reference']))
    names = [str(p.get('pm') or '').strip() for p in profiles.values() if str(p.get('pm') or '').strip()]
    return {'problems': [], 'projects': cards, 'pm_name': min(names, key=len) if names else '', 'email': email}
