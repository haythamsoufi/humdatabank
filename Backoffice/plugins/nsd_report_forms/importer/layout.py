"""Layout of the NSD master import workbook (shared by the importer and the sample generator).

Row 1 of every sheet holds the column names, row 2 a short explanation (skipped on import),
data starts on row 3. Required columns must be present with a value in every row.
"""
from dataclasses import dataclass
from typing import Dict, List, Tuple

FUNDS = ('CBF',)  # NSIA follows later
STATUSES = ('Open', 'Active', 'Closed', 'Archived')
REPORT_TYPES = ('CBF quarter', 'CBF final report')
ROW_TYPES = ('Outcome', 'Output', 'Activity', 'Indicator')
REPORT_STATUSES = ('Draft', 'Saved', 'Submitted')

OVERALL_ASSESSMENT = ('All on track', 'Partially on track', 'Not on track')
ACTIVITIES_STATUS = ('On track', 'Partially on track', 'Not on track')
FINAL_OVERALL = ('Results achieved beyond expectations', 'Results achieved as expected',
                 'Expected results partially achieved', 'Results not achieved')
FINAL_ACTIVITIES = ('All achieved', 'Partially achieved', 'Not achieved')
PARTNER_TYPES = ('Home government', 'Private Sector', 'Local organisations', 'Donors',
                 'International Organisations', 'RCRC partners')


@dataclass(frozen=True)
class Col:
    name: str
    help: str
    required: bool = False
    kind: str = 'text'          # text | date | number | json | choice
    choices: Tuple[str, ...] = ()
    aliases: Tuple[Tuple[str, str], ...] = ()   # (older MOMO wording, canonical value)


PROJECTS: List[Col] = [
    Col('reference', 'Unique project id, e.g. CBF-XX-2401-001', True),
    Col('fund', 'CBF (NSIA follows later)', True, 'choice', FUNDS),
    Col('title', 'Project title', True),
    Col('ns_name', 'National Society name (matched against the National Society list)', True),
    Col('country_iso3', 'Optional: ISO3 of the country. Used when the NS name does not match and that country has exactly one National Society'),
    Col('status', 'Open / Active / Closed / Archived. Closed and Archived projects get no new work', False, 'choice', STATUSES),
    Col('funding_modality', 'e.g. Standard'),
    Col('categories', 'Categories / thematics'),
    Col('start_date', 'yyyy-mm-dd', False, 'date'),
    Col('end_date', 'yyyy-mm-dd, final implementation end date', False, 'date'),
    Col('amount_granted_chf', 'Total granted amount in CHF', False, 'number'),
    Col('expected_spending_chf', 'Optional. Prefills the Spending table; defaults to the amount granted', False, 'number'),
    Col('planned_overview', 'Overview of the initiative as planned (shown in the final report)'),
    Col('ns_focal_name', 'NS focal person'),
    Col('ns_focal_email', 'Also gives that user access to the project when the user exists'),
    Col('ifrc_pm_name', 'IFRC project manager'),
    Col('ifrc_pm_email', 'Also gives that user access to the project when the user exists'),
]

LOGFRAME: List[Col] = [
    Col('reference', 'Project reference', True),
    Col('row_type', 'Outcome / Output / Activity / Indicator', True, 'choice', ROW_TYPES),
    Col('outcome_no', '1, 2, 3 ... on every row', True, 'number'),
    Col('output_no', 'Blank on Outcome rows and outcome-level Indicators', False, 'number'),
    Col('text', 'Outcome, output, activity or indicator wording (may be empty if MOMO has no wording)'),
    Col('planned_budget_chf', 'Outcome, Output and Activity rows', False, 'number'),
    Col('baseline', 'Indicator rows'),
    Col('target', 'Indicator rows'),
    Col('category', 'Outcome rows: outcome category (optional)'),
]

SCHEDULE: List[Col] = [
    Col('reference', 'Project reference', True),
    Col('report_type', 'CBF quarter / CBF final report', True, 'choice', REPORT_TYPES),
    Col('period', 'Y1Q1, Y1Q2 ... (project year and quarter, as in MOMO). Final reports: any label, usually Y2Q4', True),
    Col('period_start', 'yyyy-mm-dd', False, 'date'),
    Col('period_end', 'yyyy-mm-dd', False, 'date'),
    Col('deadline', 'yyyy-mm-dd. Becomes the due date of this project in the assignment', False, 'date'),
]

QUARTERLY: List[Col] = [
    Col('reference', 'Project reference', True),
    Col('period', 'Must exist in Schedule for this project as a CBF quarter', True),
    Col('status', 'Draft / Saved / Submitted', True, 'choice', REPORT_STATUSES),
    Col('review_author', ''),
    Col('review_date', 'yyyy-mm-dd', False, 'date'),
    Col('overall_assessment', ' / '.join(OVERALL_ASSESSMENT), False, 'choice', OVERALL_ASSESSMENT),
    Col('actual_spending_chf', 'Actual amount spent to date', False, 'number'),
    Col('activities_status', ' / '.join(ACTIVITIES_STATUS), False, 'choice', ACTIVITIES_STATUS),
    Col('extra_kpi', ''),
    Col('implementation_comments', ''),
    Col('last_action_points', 'JSON list: [{"action":"...","follow_up":"..."}]', False, 'json'),
    Col('next_action_points', 'JSON list: [{"action":"...","by_whom":"...","by_when":"yyyy-mm-dd"}]', False, 'json'),
]

FINAL_CBF: List[Col] = [
    Col('reference', 'Project reference', True),
    Col('status', 'Draft / Saved / Submitted', True, 'choice', REPORT_STATUSES),
    Col('review_author', ''),
    Col('review_date', 'yyyy-mm-dd', False, 'date'),
    Col('achieved_results', 'Overview of achieved results'),
    Col('major_changes', 'Major changes from the original plan'),
    Col('overall_assessment', ' / '.join(FINAL_OVERALL), False, 'choice', FINAL_OVERALL,
        (('Results partially achieved', 'Expected results partially achieved'),
         ('Results achieved beyond expectation', 'Results achieved beyond expectations'))),
    Col('activities_assessment', ' / '.join(FINAL_ACTIVITIES), False, 'choice', FINAL_ACTIVITIES),
    Col('logframe_json', 'Outcomes and outputs WITH assessments and actuals (JSON, same shape as the app stores)', False, 'json'),
    Col('ns_development', ''),
    Col('humanitarian_impacts', ''),
    Col('unexpected_outcomes', ''),
    Col('actual_beneficiaries', ''),
    Col('collab_gov', 'Yes / No', False, 'choice', ('Yes', 'No')),
    Col('collab_rcrc', 'JSON list of National Society names', False, 'json'),
    Col('collab_other', 'JSON list of partner names', False, 'json'),
    Col('new_partnerships', 'JSON list: [{"type":"Donors","who":"...","purpose":"..."}]', False, 'json'),
    Col('lessons_learned', ''),
    Col('advice', 'What would you do differently next time?'),
    Col('tips_tools', ''),
    Col('additional_information', ''),
]

SHEETS: Dict[str, List[Col]] = {
    'Projects': PROJECTS,
    'Logframe': LOGFRAME,
    'Schedule': SCHEDULE,
    'Quarterly': QUARTERLY,
    'FinalCBF': FINAL_CBF,
}
REQUIRED_SHEETS = ('Projects',)
OPTIONAL_SHEETS = ('Logframe', 'Schedule', 'Quarterly', 'FinalCBF')

# Template names the importer writes into (created beforehand with the form builder)
TEMPLATE_NAMES = {
    'profile': 'NSD Project profile - CBF',
    'CBF quarter': 'NSD Quarterly report - CBF',
    'CBF final report': 'NSD Final report - CBF',
}
PROFILE_PERIOD = 'Project'
FINAL_PERIOD = 'Final'


def period_name(reference: str, suffix: str) -> str:
    """Assignment period of one project report, e.g. 'CBF-XX-2401-001 Y1Q2'."""
    return f'{reference} {suffix}'
