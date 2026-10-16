"""Apply a parsed NSD master workbook: project records, access, assignments and form data.

Projects live under their country: every report is one assignment (reference in the period name) given to the
country of the National Society. No core changes.

analyze() reads only. run() writes, one project per transaction, so one bad project
never blocks the others.
"""
import datetime as dt
import json
import unicodedata
from types import SimpleNamespace
from collections import defaultdict
from typing import Callable, Dict, List, Optional

from sqlalchemy import func

from app import db
from app.models import (AssignedForm, AssignmentEntityStatus, Country, FormData, FormItem, FormSection, FormTemplate,
                        FormTemplateVersion, RbacRole, RbacUserRole, RepeatGroupData, RepeatGroupInstance, User)
from app.models.enums import AssignmentEntityStatusValue
from app.models.organization import NationalSociety
from app.services.assignments.completion_service import AssignmentCompletionService
from app.services.assignments.workflow_service import apply_entity_status_change
from app.utils.datetime_helpers import utcnow

from ..access_on_create import ROLE_BY_CONTACT
from ..plugin import NSD_ROLE_FOCAL, NSD_ROLE_PM
from . import restrictions
from . import layout
from .workbook import Book, logframe_structure

ENTITY = 'country'

# items the importer prefills in each report; they do not count as report history
PREFILLED = {
    'CBF quarter': ('National Society', 'Title', 'Reference', 'Funding Modality', 'Categories/Thematics', 'Start Date', 'End Date',
                    'Amount Granted (in CHF)', 'NS Focal Person', 'IFRC Project Manager', 'Spending'),
    'CBF final report': ('National Society', 'Title', 'Reference', 'Funding Modality', 'Categories/Thematics', 'Start Date',
                         'End Date', 'Amount Granted (in CHF)', 'NS Focal Person', 'IFRC Project Manager',
                         'Overview of the initiative as planned', 'Outcomes and outputs'),
}


class TemplateProblem(Exception):
    pass


def _norm(s: str) -> str:
    return ' '.join(str(s or '').casefold().split())


def _norm_name(s: str) -> str:
    """National Society names compared loosely: no accents, no punctuation, no leading "The"."""
    s = unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().casefold()
    words = ''.join(c if c.isalnum() else ' ' for c in s).split()
    return ' '.join(words[1:] if words[:1] == ['the'] else words)


# --------------------------------------------------------------------- lookups
class Lookups:
    """Templates, National Societies and users, loaded once per run."""

    def __init__(self):
        self.templates: Dict[str, dict] = {}
        self.problems: List[str] = []
        for key, name in layout.TEMPLATE_NAMES.items():
            self._load_template(key, name)
        self.ns_index, self.ns_by_country = self._ns_index()
        self.ns_country = {i: c for i, c in db.session.query(NationalSociety.id, NationalSociety.country_id).all()}
        self.user_ids = {(e or '').strip().casefold(): uid for uid, e in db.session.query(User.id, User.email).all() if e}
        self.nsd_roles = restrictions.load_roles()
        for code in restrictions.missing_roles(self.nsd_roles):
            self.problems.append(f'Role "{code}" does not exist yet. Restart the application once so the plugin can set up its roles.')

    def _load_template(self, key: str, name: str):
        row = (db.session.query(FormTemplate, FormTemplateVersion)
               .join(FormTemplateVersion, FormTemplateVersion.id == FormTemplate.published_version_id)
               .filter(FormTemplateVersion.name == name).first())
        if not row:
            self.problems.append(f'Template "{name}" is not published. Create it with the form builder first.')
            return
        tpl, ver = row
        # plain objects, not ORM rows: ORM rows expire at every commit and would re-query on each access
        sections = {s.id: SimpleNamespace(id=s.id, name=s.name)
                    for s in FormSection.query.filter_by(version_id=ver.id, archived=False).all()}
        items = defaultdict(list)
        for it in FormItem.query.filter_by(version_id=ver.id, archived=False).all():
            items[_norm(it.label)].append(SimpleNamespace(id=it.id, section_id=it.section_id, label=it.label))
        self.templates[key] = {'tpl': SimpleNamespace(id=tpl.id), 'version_id': ver.id, 'sections': sections,
                               'items': items, 'sections_by_name': {_norm(s.name): s for s in sections.values()}}

    @staticmethod
    def _ns_index():
        """(normalised name -> NS ids, ISO3 -> NS ids) over the active National Societies."""
        by_name, by_country = defaultdict(set), defaultdict(set)
        rows = (db.session.query(NationalSociety, Country.iso3).join(Country, Country.id == NationalSociety.country_id)
                .filter(NationalSociety.is_active.is_(True)).all())
        for ns, iso3 in rows:
            for n in [ns.name] + [v for v in (ns.name_translations or {}).values() if isinstance(v, str)]:
                by_name[_norm_name(n)].add(ns.id)
            if iso3:
                by_country[iso3.upper()].add(ns.id)
        return by_name, by_country

    def match_ns(self, name: str, iso3: str = '') -> Optional[int]:
        """The National Society by name; failing that, the only one of the project's country (when its ISO3 is given)."""
        ids = self.ns_index.get(_norm_name(name), set())
        if len(ids) != 1 and iso3:
            ids = self.ns_by_country.get(iso3.strip().upper(), set())
        return next(iter(ids)) if len(ids) == 1 else None

    def item(self, key: str, label: str, section: Optional[str] = None):
        t = self.templates[key]
        cands = t['items'].get(_norm(label), [])
        if section:
            cands = [i for i in cands if _norm(t['sections'][i.section_id].name) == _norm(section)]
        if not cands:
            raise TemplateProblem(f'Template "{layout.TEMPLATE_NAMES[key]}" has no item "{label}"' + (f' in section "{section}"' if section else ''))
        return cands[0]

    def section(self, key: str, name: str):
        s = self.templates[key]['sections_by_name'].get(_norm(name))
        if not s:
            raise TemplateProblem(f'Template "{layout.TEMPLATE_NAMES[key]}" has no section "{name}"')
        return s


# -------------------------------------------------------------------- analysis
def analyze(book: Book) -> dict:
    """What an import would do, without writing anything."""
    lk = Lookups()
    projects = book.rows['Projects']
    refs = [p['reference'] for p in projects]
    profile_tpl = lk.templates.get('profile')
    existing = set()
    if refs and profile_tpl:
        names = {layout.period_name(r, layout.PROFILE_PERIOD): r for r in refs}
        existing = {names[n] for (n,) in db.session.query(AssignedForm.period_name).filter(
            AssignedForm.template_id == profile_tpl['tpl'].id, AssignedForm.period_name.in_(list(names))).all()}
    unmatched_ns = sorted({p['ns_name'] for p in projects if lk.match_ns(p['ns_name'], p['country_iso3']) is None})
    emails = {p[k].strip().casefold() for p in projects for k in ('ns_focal_email', 'ifrc_pm_email') if p.get(k)}
    unknown_emails = sorted(e for e in emails if e not in lk.user_ids)

    sched = book.rows['Schedule']
    types = defaultdict(int)
    for r in sched:
        types[r['report_type']] += 1
    return {
        'problems': lk.problems,
        'projects': {'total': len(projects), 'new': len(projects) - len(existing), 'existing': len(existing)},
        'ns': {'matched': len(projects) - sum(1 for p in projects if lk.match_ns(p['ns_name'], p['country_iso3']) is None),
               'unmatched_names': unmatched_ns[:30], 'unmatched_count': len(unmatched_ns)},
        'access': {'emails': len(emails), 'matched': len(emails) - len(unknown_emails), 'unknown': len(unknown_emails),
                   'unknown_sample': unknown_emails[:10]},
        'logframe_projects': len({r['reference'] for r in book.rows['Logframe']}),
        'logframe_rows': len(book.rows['Logframe']),
        'schedule': dict(types),
        'quarterly': len(book.rows['Quarterly']),
        'final': len(book.rows['FinalCBF']),
    }


# ----------------------------------------------------------------------- write
class Run:
    def __init__(self, book: Book, user_id: int, overwrite_reports: bool, progress: Callable[[int, int, str], None],
                 cancelled: Callable[[], bool]):
        self.book, self.uid, self.overwrite = book, user_id, overwrite_reports
        self.progress, self.cancelled = progress, cancelled
        self.lk = Lookups()
        self.stats = defaultdict(int)
        self.roles = {}
        self.messages: List[str] = []
        self.logframes = defaultdict(list)
        for r in book.rows['Logframe']:
            self.logframes[r['reference']].append(r)
        self.sched = defaultdict(list)
        for r in book.rows['Schedule']:
            self.sched[r['reference']].append(r)
        self.quarterly = defaultdict(dict)
        for r in book.rows['Quarterly']:
            self.quarterly[r['reference']][r['period']] = r
        self.final = {r['reference']: r for r in book.rows['FinalCBF']}

    def note(self, msg: str):
        if len(self.messages) < 200:
            self.messages.append(msg)

    # -- low level writers
    def put(self, aes, item, value=None, disagg=None, dtype=None, when=None):
        fd = FormData.query.filter_by(assignment_entity_status_id=aes.id, form_item_id=item.id).first()
        if fd is None:
            fd = FormData(assignment_entity_status_id=aes.id, form_item_id=item.id, created_by_user_id=self.uid)
            db.session.add(fd)
        if disagg is not None:
            fd.value = None
            fd.numeric_value = None
            fd.disagg_data = disagg
            fd.disagg_type = dtype
            fd.data_not_available = False
            fd.not_applicable = False
        else:
            fd.set_simple_value(value)
        fd.submitted_at = when or utcnow()
        self.stats['values'] += 1

    def get_assignment(self, key: str, suffix: str, due: Optional[dt.datetime], proj: SimpleNamespace):
        """One assignment per project and report (the reference is part of the period name), given to the country."""
        tpl = self.lk.templates[key]['tpl']
        period = layout.period_name(proj.reference, suffix)
        # The project record (profile) is never a task: it stays inactive, like the reports of closed projects.
        active = proj.active and key != 'profile'
        af = AssignedForm.query.filter_by(template_id=tpl.id, period_name=period).first()
        if not af:
            af = AssignedForm(template_id=tpl.id, period_name=period, is_active=active)
            db.session.add(af)
            db.session.flush()
            self.stats['assignments_created'] += 1
        elif af.is_active != active:
            af.is_active = active
        if restrictions.restrict(af, key, self.lk.nsd_roles):
            self.stats['assignment_roles_set'] += 1
        aes = AssignmentEntityStatus.query.filter_by(assigned_form_id=af.id, entity_type=ENTITY, entity_id=proj.country_id).first()
        if not aes:
            aes = AssignmentEntityStatus(assigned_form_id=af.id, entity_type=ENTITY, entity_id=proj.country_id,
                                         status=AssignmentEntityStatusValue.pending, due_date=due)
            db.session.add(aes)
            db.session.flush()
            self.stats['entities_created'] += 1
        elif due is not None:
            aes.due_date = due
        return aes

    def has_history(self, aes, key: str) -> bool:
        """Answers beyond what the importer prefills (project information, planned budget and structure)."""
        prefilled = {self.lk.item(key, label).id for label in PREFILLED.get(key, ())}
        q = db.session.query(FormData.id).filter(FormData.assignment_entity_status_id == aes.id)
        if prefilled:
            q = q.filter(FormData.form_item_id.notin_(prefilled))
        if q.first() is not None or \
                db.session.query(RepeatGroupInstance.id).filter_by(assignment_entity_status_id=aes.id).first() is not None:
            return True
        if key == 'CBF quarter':  # the Spending table is prefilled with the expected amount; an actual amount is history
            fd = FormData.query.filter_by(assignment_entity_status_id=aes.id, form_item_id=self.lk.item(key, 'Spending').id).first()
            return bool(fd and (fd.disagg_data or {}).get('Amount (CHF)_Actual amount spent to date (CHF)'))
        return False

    def finish_aes(self, aes, status: str, when: Optional[dt.datetime]):
        db.session.flush()
        AssignmentCompletionService.refresh_and_persist(aes.id)
        new = AssignmentEntityStatusValue.submitted if status == 'Submitted' else AssignmentEntityStatusValue.in_progress
        apply_entity_status_change(aes, new, self.uid, now=when or utcnow())

    def repeat_rows(self, aes, key: str, section_name: str, rows: List[dict], fields: Dict[str, str]):
        """Replace the instances of one repeat section; fields maps item label -> key in the row dict."""
        sec = self.lk.section(key, section_name)
        for inst in RepeatGroupInstance.query.filter_by(assignment_entity_status_id=aes.id, section_id=sec.id).all():
            RepeatGroupData.query.filter_by(repeat_instance_id=inst.id).delete()
            db.session.delete(inst)
        db.session.flush()
        n = 0
        for row in rows:
            if not isinstance(row, dict) or not any(str(row.get(k) or '').strip() for k in fields.values()):
                continue
            n += 1
            inst = RepeatGroupInstance(assignment_entity_status_id=aes.id, section_id=sec.id, instance_number=n,
                                       created_by_user_id=self.uid, is_hidden=False)
            db.session.add(inst)
            db.session.flush()
            for label, k in fields.items():
                v = str(row.get(k) or '').strip()
                if not v:
                    continue
                item = self.lk.item(key, label, section_name)
                d = RepeatGroupData(repeat_instance_id=inst.id, form_item_id=item.id, created_by_user_id=self.uid,
                                    created_at=utcnow())
                d.set_simple_value(v)
                db.session.add(d)

    def ensure_role(self, uid: int, code: str):
        """Give the role that goes with a contact type; never removes roles and skips System Managers."""
        role = self.roles.get(code)
        if role is None:
            role = self.roles[code] = RbacRole.query.filter_by(code=code).first() or False
        if not role:
            return
        held = {c for (c,) in db.session.query(RbacRole.code).join(RbacUserRole, RbacUserRole.role_id == RbacRole.id)
                .filter(RbacUserRole.user_id == uid).all()}
        if code in held or 'system_manager' in held:
            return
        if code == NSD_ROLE_FOCAL and NSD_ROLE_PM in held:  # the PM role supersedes the focal point role
            return
        if code == NSD_ROLE_PM and NSD_ROLE_FOCAL in held:
            focal = RbacRole.query.filter_by(code=NSD_ROLE_FOCAL).first()
            if focal:
                RbacUserRole.query.filter_by(user_id=uid, role_id=focal.id).delete()
        db.session.add(RbacUserRole(user_id=uid, role_id=role.id))
        self.stats['roles_granted'] += 1

    # -- one project
    def import_project(self, p: dict):
        ref = p['reference']
        ns_id = self.lk.match_ns(p['ns_name'], p['country_iso3'])
        country_id = self.lk.ns_country.get(ns_id) if ns_id else None
        if country_id is None:
            self.stats['skipped_no_national_society'] += 1
            self.note(f'{ref}: National Society "{p["ns_name"]}" not found, project skipped')
            return
        proj = SimpleNamespace(reference=ref, country_id=country_id, active=(p['status'] or 'Open') in ('Open', 'Active'), p=p)
        existed = AssignedForm.query.filter_by(template_id=self.lk.templates['profile']['tpl'].id,
                                               period_name=layout.period_name(ref, layout.PROFILE_PERIOD)).first()
        self.stats['projects_updated' if existed else 'projects_created'] += 1

        for em, field in ((p['ns_focal_email'], 'NS focal person email'), (p['ifrc_pm_email'], 'IFRC project manager email')):
            uid = self.lk.user_ids.get((em or '').strip().casefold())
            if uid:
                db.session.get(User, uid).add_entity_permission(ENTITY, country_id)
                self.stats['access_grants'] += 1
                self.ensure_role(uid, ROLE_BY_CONTACT[field])

        self.write_profile(proj)
        for s in self.sched.get(ref, []):
            self.write_schedule_row(proj, s)
        if ref in self.final and not any(s['report_type'] == 'CBF final report' for s in self.sched.get(ref, [])):
            self.write_schedule_row(proj, {'report_type': 'CBF final report', 'period': layout.FINAL_PERIOD, 'deadline': ''})

    @staticmethod
    def _date(v: str) -> str:
        return dt.date.fromisoformat(v).strftime('%d/%m/%Y') if v else ''

    @staticmethod
    def _money(v) -> str:
        try:
            f = float(v)
        except (TypeError, ValueError):
            return ''
        return f'{f:,.0f}' if f.is_integer() else f'{f:,.2f}'

    @staticmethod
    def _person(name: str, email: str) -> str:
        return f'{name} ({email})' if name and email else (name or email or '')

    def _expected(self, p: dict) -> str:
        return p['expected_spending_chf'] or p['amount_granted_chf'] or ''

    def write_profile(self, proj: SimpleNamespace):
        """The project record: one hidden form per project, read by the overview pages."""
        p, key = proj.p, 'profile'
        aes = self.get_assignment(key, layout.PROFILE_PERIOD, None, proj)
        L = self.lk.item
        for label, v in (('National Society', p['ns_name']), ('Title', p['title']), ('Reference', p['reference']),
                         ('Status', p['status'] or 'Open'), ('Funding modality', p['funding_modality']),
                         ('Categories / thematics', p['categories']), ('Start date', p['start_date']), ('End date', p['end_date']),
                         ('Amount granted (CHF)', p['amount_granted_chf']), ('Overview of the initiative as planned', p['planned_overview']),
                         ('NS focal person', p['ns_focal_name']), ('NS focal person email', p['ns_focal_email']),
                         ('IFRC project manager', p['ifrc_pm_name']), ('IFRC project manager email', p['ifrc_pm_email'])):
            if v not in (None, ''):
                self.put(aes, L(key, label), value=v)
        expected = self._expected(p)
        if expected:
            self.put(aes, L(key, 'Expected spending'), disagg={'Amount (CHF)_Expected spending (CHF)': expected}, dtype='matrix')
        frame = logframe_structure(self.logframes.get(p['reference'], []))
        if frame:
            self.put(aes, L(key, 'Outcomes and outputs'), disagg=frame, dtype='plugin')
            self.stats['logframes'] += 1
        self.finish_aes(aes, 'Submitted', None)
        self.stats['profiles'] += 1

    def prefill(self, aes, key: str, p: dict):
        """Project information in a report is a locked copy of the project record, refreshed on every import."""
        L = self.lk.item
        values = (('National Society', p['ns_name']), ('Title', p['title']), ('Reference', p['reference']),
                  ('Funding Modality', p['funding_modality']), ('Categories/Thematics', p['categories']),
                  ('Start Date', self._date(p['start_date'])), ('End Date', self._date(p['end_date'])),
                  ('Amount Granted (in CHF)', self._money(p['amount_granted_chf'])),
                  ('NS Focal Person', self._person(p['ns_focal_name'], p['ns_focal_email'])),
                  ('IFRC Project Manager', self._person(p['ifrc_pm_name'], p['ifrc_pm_email'])))
        for label, v in values:
            if v:
                self.put(aes, L(key, label), value=v)
        if key == 'CBF final report':
            if p['planned_overview']:
                self.put(aes, L(key, 'Overview of the initiative as planned'), value=p['planned_overview'])
            frame_item = L(key, 'Outcomes and outputs')
            frame = logframe_structure(self.logframes.get(p['reference'], []))
            if frame and not FormData.query.filter_by(assignment_entity_status_id=aes.id, form_item_id=frame_item.id).first():
                self.put(aes, frame_item, disagg=frame, dtype='plugin')
        else:
            self._expected_cell(aes, key, p, None)

    def _expected_cell(self, aes, key: str, p: dict, actual: Optional[str], when=None):
        """Spending table: set the expected cell (and the actual one when given) without touching other cells."""
        item = self.lk.item(key, 'Spending')
        fd = FormData.query.filter_by(assignment_entity_status_id=aes.id, form_item_id=item.id).first()
        cells = dict((fd.disagg_data or {}) if fd else {})
        if self._expected(p):
            cells['Amount (CHF)_Expected spending (CHF)'] = self._expected(p)
        if actual:
            cells['Amount (CHF)_Actual amount spent to date (CHF)'] = actual
        if cells:
            self.put(aes, item, disagg=cells, dtype='matrix', when=when)

    def write_schedule_row(self, proj: SimpleNamespace, s: dict):
        rtype, period = s['report_type'], s['period']
        key = rtype
        if key not in self.lk.templates:
            return
        due = dt.datetime.fromisoformat(s['deadline']) if s.get('deadline') else None
        suffix = layout.FINAL_PERIOD if rtype == 'CBF final report' else period
        aes = self.get_assignment(key, suffix, due, proj)
        self.stats['schedule_rows'] += 1
        self.prefill(aes, key, proj.p)
        if rtype == 'CBF quarter':
            row = self.quarterly.get(proj.reference, {}).get(period)
            if row:
                self.write_quarterly(aes, proj, row)
            else:
                self.finish_prefilled(aes)
        elif proj.reference in self.final:
            self.write_final(aes, proj, self.final[proj.reference])
        else:
            self.finish_prefilled(aes)

    def finish_prefilled(self, aes):
        """A report with only the prefilled information keeps its pending status."""
        db.session.flush()
        AssignmentCompletionService.refresh_and_persist(aes.id)

    def _guard(self, aes, key: str) -> bool:
        if self.has_history(aes, key) and not self.overwrite:
            self.stats['reports_skipped_existing'] += 1
            return False
        return True

    def write_quarterly(self, aes, proj: SimpleNamespace, r: dict):
        key = 'CBF quarter'
        if not self._guard(aes, key):
            return
        L = self.lk.item
        when = dt.datetime.fromisoformat(r['review_date']) if r['review_date'] else None
        for label, v in (('Review author(s)', r['review_author']), ('Review date', r['review_date']),
                         ('Overall implementation assessment', r['overall_assessment']),
                         ("Activities' implementation according to the plan", r['activities_status']),
                         ('OPTIONAL extra KPI (if helpful)', r['extra_kpi']), ('OPTIONAL Comments', r['implementation_comments'])):
            if v:
                self.put(aes, L(key, label), value=v, when=when)
        self._expected_cell(aes, key, proj.p, r['actual_spending_chf'] or None, when)
        self.repeat_rows(aes, key, 'Last quarter action points (optional)', r['last_action_points'] or [],
                         {'Action point': 'action', 'Follow up / comments': 'follow_up'})
        self.repeat_rows(aes, key, 'Next quarter action points (optional)', r['next_action_points'] or [],
                         {'Action point': 'action', 'By whom (names)': 'by_whom', 'By when': 'by_when'})
        self.finish_aes(aes, r['status'], when)
        self.stats['quarterly_reports'] += 1

    def write_final(self, aes, proj: SimpleNamespace, r: dict):
        key = 'CBF final report'
        if not self._guard(aes, key):
            return
        L = self.lk.item
        when = dt.datetime.fromisoformat(r['review_date']) if r['review_date'] else None
        simple = (('Review author(s)', r['review_author']), ('Review date', r['review_date']),
                  ('Overview of achieved results', r['achieved_results']),
                  ('Major changes from the original plan', r['major_changes']),
                  ('Overall implementation assessment', r['overall_assessment']),
                  ("Activities' implementation", r['activities_assessment']),
                  ('To the National Society development', r['ns_development']),
                  ('To the National Society humanitarian impacts and resilience of communities', r['humanitarian_impacts']),
                  ('Unexpected outcomes or impacts', r['unexpected_outcomes']),
                  ('Actual beneficiaries reached', r['actual_beneficiaries']),
                  ('Share key lessons learned from the implementation and results of the initiative', r['lessons_learned']),
                  ('What would you do differently next time?', r['advice']),
                  ('Any tips or tools you would like to share with other National Societies?', r['tips_tools']),
                  ('Additional information', r['additional_information']))
        for label, v in simple:
            if v:
                self.put(aes, L(key, label), value=v, when=when)
        if r['collab_gov']:
            self.put(aes, L(key, 'Home government'), value=r['collab_gov'].lower(), when=when)
        if isinstance(r['collab_rcrc'], list) and r['collab_rcrc']:
            self.put(aes, L(key, 'RCRC partners'), value=json.dumps([str(x) for x in r['collab_rcrc']]), when=when)
        if isinstance(r['collab_other'], list) and r['collab_other']:
            self.put(aes, L(key, 'Other partners'), disagg=[{'name': str(x)} for x in r['collab_other']], dtype='plugin', when=when)
        if isinstance(r['new_partnerships'], list) and r['new_partnerships']:
            self.put(aes, L(key, 'New partnerships'), disagg=[x for x in r['new_partnerships'] if isinstance(x, dict)],
                     dtype='plugin', when=when)
        if isinstance(r['logframe_json'], list) and r['logframe_json']:
            self.put(aes, L(key, 'Outcomes and outputs'), disagg=r['logframe_json'], dtype='plugin', when=when)
        self.finish_aes(aes, r['status'], when)
        self.stats['final_reports'] += 1


def run(book: Book, user_id: int, overwrite_reports: bool, progress, cancelled) -> dict:
    """Write everything. Returns {'stats', 'messages', 'failed'}."""
    r = Run(book, user_id, overwrite_reports, progress, cancelled)
    if r.lk.problems:
        return {'stats': {}, 'messages': r.lk.problems, 'failed': len(book.rows['Projects']), 'cancelled': False}
    projects = book.rows['Projects']
    failed = 0
    for i, p in enumerate(projects, 1):
        if cancelled():
            return {'stats': dict(r.stats), 'messages': r.messages, 'failed': failed, 'cancelled': True}
        try:
            r.import_project(p)
            db.session.commit()
        except TemplateProblem as exc:
            db.session.rollback()
            return {'stats': dict(r.stats), 'messages': [str(exc)], 'failed': len(projects), 'cancelled': False}
        except Exception as exc:  # one project must not stop the others
            db.session.rollback()
            failed += 1
            r.note(f'{p["reference"]}: {type(exc).__name__}: {str(exc)[:200]}')
        progress(i, len(projects), p['reference'])
    return {'stats': dict(r.stats), 'messages': r.messages, 'failed': failed, 'cancelled': False}
