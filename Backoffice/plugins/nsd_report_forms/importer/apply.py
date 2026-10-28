"""Apply a parsed NSD master workbook onto core Project + shared CBF report slots.

Projects are stored in core ``project``. Each report is an AES on a *shared* slot
assignment (period ``Y1Q2`` / ``Final``) with ``entity_type=project``.

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
                        FormTemplateVersion, RepeatGroupData, RepeatGroupInstance, User)
from app.models.enums import AssignmentEntityStatusValue
from app.models.organization import NationalSociety
from app.models.projects import Project
from app.services.assignments.completion_service import AssignmentCompletionService
from app.services.assignments.workflow_service import apply_entity_status_change
from app.utils.datetime_helpers import utcnow

from plugins.nsd_report_forms.constants import ENTITY_TYPE, FINAL_SLOT
from plugins.nsd_report_forms import schedule as nsd_schedule

from . import restrictions
from . import layout
from .workbook import Book, logframe_structure

ENTITY = 'country'  # geography grants still use country

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
        # Auto-create/publish CBF quarter + final if missing (idempotent).
        try:
            from plugins.nsd_report_forms.ensure_templates import ensure_cbf_report_templates

            ensure_cbf_report_templates(commit=True)
        except Exception as exc:
            self.problems.append(f'Could not prepare NSD report templates: {exc}')
        # Profile template is optional (identity lives in core project); quarter + final are required.
        for key, name in layout.TEMPLATE_NAMES.items():
            required = key != 'profile'
            self._load_template(key, name, required=required)
        self.ns_index, self.ns_by_country = self._ns_index()
        self.ns_country = {i: c for i, c in db.session.query(NationalSociety.id, NationalSociety.country_id).all()}
        self.user_ids = {(e or '').strip().casefold(): uid for uid, e in db.session.query(User.id, User.email).all() if e}
        self.nsd_roles = restrictions.load_roles()
        for code in restrictions.missing_roles(self.nsd_roles):
            self.problems.append(f'Role "{code}" does not exist yet. Run the RBAC seed so the NSD admin permission role is created.')
        try:
            self.access_groups = restrictions.ensure_nsd_access_groups()
            self.editor_role = restrictions.ensure_editor_role()
            self.pm_overview_role = restrictions.ensure_pm_overview_role()
            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            self.access_groups = {}
            self.editor_role = None
            self.pm_overview_role = None
            self.problems.append(f'Could not prepare NSD Access Groups: {exc}')

    def _load_template(self, key: str, name: str, required: bool = True):
        row = (db.session.query(FormTemplate, FormTemplateVersion)
               .join(FormTemplateVersion, FormTemplateVersion.id == FormTemplate.published_version_id)
               .filter(FormTemplateVersion.name == name).first())
        if not row:
            if required:
                self.problems.append(
                    f'Template "{name}" is not published and could not be auto-created.'
                )
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
        """(normalised name -> NS ids, ISO3 -> NS ids) over all National Societies (incl. inactive)."""
        by_name, by_country = defaultdict(set), defaultdict(set)
        rows = (
            db.session.query(NationalSociety, Country.iso3)
            .join(Country, Country.id == NationalSociety.country_id)
            .all()
        )
        for ns, iso3 in rows:
            for n in [ns.name] + [v for v in (ns.name_translations or {}).values() if isinstance(v, str)]:
                by_name[_norm_name(n)].add(ns.id)
            if iso3:
                by_country[iso3.upper()].add(ns.id)
        return by_name, by_country

    def match_ns(self, name: str, iso3: str = '') -> Optional[int]:
        """Match an NS by name (active or inactive); ISO3 fallback when the country has exactly one NS.

        Also accepts a workbook name that is a prefix of the stored name (e.g. ``Nicaraguan Red Cross``
        vs ``Nicaraguan Red Cross* dissolved …``).
        """
        key = _norm_name(name)
        ids = set(self.ns_index.get(key, set()))
        if len(ids) != 1 and key:
            cands = set()
            for nkey, nids in self.ns_index.items():
                if nkey == key:
                    cands |= nids
                elif nkey.startswith(key + " ") or key.startswith(nkey + " "):
                    cands |= nids
            if len(cands) == 1:
                ids = cands
            elif not ids and cands:
                ids = cands
        if len(ids) != 1 and iso3:
            ids = set(self.ns_by_country.get(iso3.strip().upper(), set()))
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
    existing = set()
    if refs:
        existing = {
            r for (r,) in db.session.query(Project.reference).filter(Project.reference.in_(refs)).all()
        }
        # Also count legacy profile assignments as "existing" during dual-read migration
        profile_tpl = lk.templates.get('profile')
        if profile_tpl:
            names = {layout.period_name(r, layout.PROFILE_PERIOD): r for r in refs}
            existing |= {names[n] for (n,) in db.session.query(AssignedForm.period_name).filter(
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
        'access': {
            'emails': len(emails),
            'matched': len(emails) - len(unknown_emails),
            'unknown': len(unknown_emails),
            'unknown_sample': unknown_emails[:10],
            'will_create': len(unknown_emails),
            'will_create_sample': unknown_emails[:10],
            'focal_group': restrictions.FOCAL_GROUP_NAME,
            'pm_group': restrictions.PM_GROUP_NAME,
        },
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
        self._slots: Optional[Dict[str, AssignedForm]] = None
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
        """AES on a shared slot assignment (period = Y1Q2 / Final), entity = the NSD project.

        Profile key is no longer written as an assignment; project identity lives in core ``project``.
        """
        if key == 'profile':
            raise TemplateProblem('NSD project profiles are stored in the core project registry, not as assignments')
        slot = FINAL_SLOT if key == 'CBF final report' or suffix == layout.FINAL_PERIOD else suffix
        if self._slots is None:
            self._slots = nsd_schedule.ensure_shared_slots()
        af = self._slots.get(slot)
        if af is None:
            existed_af = AssignedForm.query.filter_by(
                template_id=self.lk.templates[key]['tpl'].id, period_name=slot
            ).first()
            af = nsd_schedule._get_or_create_slot(
                self.lk.templates[key]['tpl'].id, slot, is_active=True
            )
            self._slots[slot] = af
            if existed_af is None:
                self.stats['assignments_created'] += 1
        existed_aes = AssignmentEntityStatus.query.filter_by(
            assigned_form_id=af.id, entity_type=ENTITY_TYPE, entity_id=proj.project.id
        ).first()
        aes = nsd_schedule.ensure_project_aes(proj.project, af, due=due, active=proj.active)
        if existed_aes is None:
            self.stats['entities_created'] += 1
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

    # -- one project
    def import_project(self, p: dict):
        ref = p['reference']
        ns_id = self.lk.match_ns(p['ns_name'], p['country_iso3'])
        country_id = self.lk.ns_country.get(ns_id) if ns_id else None
        if country_id is None:
            self.stats['skipped_no_national_society'] += 1
            self.note(f'{ref}: National Society "{p["ns_name"]}" not found, project skipped')
            return
        frame = logframe_structure(self.logframes.get(ref, []))
        existed = Project.query.filter_by(reference=ref).first() is not None
        project = nsd_schedule.upsert_project_from_import(p, country_id, logframe=frame or None)
        self.stats['projects_updated' if existed else 'projects_created'] += 1
        self.stats['profiles'] += 1

        proj = SimpleNamespace(
            reference=ref,
            country_id=country_id,
            active=(p['status'] or 'Open') in ('Open', 'Active'),
            p=p,
            project=project,
        )

        self._ensure_contacts(p, country_id)

        for s in self.sched.get(ref, []):
            self.write_schedule_row(proj, s)
        if ref in self.final and not any(s['report_type'] == 'CBF final report' for s in self.sched.get(ref, [])):
            self.write_schedule_row(proj, {'report_type': 'CBF final report', 'period': layout.FINAL_PERIOD, 'deadline': ''})

    def _ensure_contacts(self, p: dict, country_id: int) -> None:
        """Create missing contact users, put them in NSD Access Groups, grant country access."""
        groups = getattr(self.lk, 'access_groups', None) or {}
        editor = getattr(self.lk, 'editor_role', None)
        pm_role = getattr(self.lk, 'pm_overview_role', None)

        contacts = (
            ('ns_focal_email', 'ns_focal_name', 'focal', False),
            ('ifrc_pm_email', 'ifrc_pm_name', 'pm', True),
        )
        for email_key, name_key, group_key, is_pm in contacts:
            email = (p.get(email_key) or '').strip()
            if not email or '@' not in email:
                continue
            group = groups.get(group_key)
            if group is None:
                # Fall back to country grant only when groups could not be prepared
                uid = self.lk.user_ids.get(email.casefold())
                if uid:
                    db.session.get(User, uid).add_entity_permission(ENTITY, country_id)
                    self.stats['access_grants'] += 1
                continue
            also = [r for r in (editor, pm_role if is_pm else None) if r is not None]
            try:
                user, created = restrictions.ensure_contact_user(
                    email=email,
                    name=(p.get(name_key) or '').strip(),
                    group=group,
                    also_roles=also,
                )
            except ValueError:
                continue
            user.add_entity_permission(ENTITY, country_id)
            self.lk.user_ids[email.casefold()] = user.id
            self.stats['access_grants'] += 1
            if created:
                self.stats['users_created'] += 1
            self.stats['group_memberships'] += 1

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
    r.note('NSD reports use shared slots (Y1Q1…Final) with entity_type=project. '
           'Country access for contact emails still opens those project reports.')
    try:
        r._slots = nsd_schedule.ensure_shared_slots()
        db.session.flush()
    except RuntimeError as exc:
        return {'stats': {}, 'messages': [str(exc)], 'failed': len(book.rows['Projects']), 'cancelled': False}
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
