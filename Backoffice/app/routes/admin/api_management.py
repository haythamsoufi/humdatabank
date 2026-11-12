from flask import Blueprint, render_template, request
from sqlalchemy import func
from datetime import timedelta
from app.models.api_usage import APIUsage
from app.models import (
    AssignedForm,
    IndicatorBank,
    Sector,
    SubSector,
    FormTemplate,
    Country,
    User,
)
from app import db
from app.routes.admin.shared import admin_permission_required
from flask import current_app
from app.utils.common.datetime_helpers import utcnow
from app.utils.api.api_helpers import GENERIC_ERROR_MESSAGE
from app.utils.api.api_responses import json_ok, json_server_error
from app.services.platform.api_usage_stats import (
    bulk_endpoint_usage_stats,
    chart_stats_for_period,
    usage_tracked_clause,
)
from app.services.forms.reporting_period_service import period_chronology_sort_key
from app.routes.admin.api_registry import ENDPOINT_REGISTRY
from sqlalchemy.orm import joinedload


_URL_BUILDER_METHOD_RANK = {
    'GET': 0,
    'POST': 1,
    'PUT': 2,
    'PATCH': 3,
    'DELETE': 4,
}


def _url_builder_endpoint_sort_key(endpoint: dict):
    """Path, then HTTP method, so list routes sit above their detail routes."""
    method = str(endpoint.get('method') or '')
    primary = method.split('/')[0].strip().upper()
    return (
        str(endpoint.get('path') or '').casefold(),
        _URL_BUILDER_METHOD_RANK.get(primary, 50),
        method.casefold(),
    )


def _url_builder_param_contracts(endpoints: list[dict]) -> dict:
    """Query-parameter contracts declared by endpoints, keyed by path.

    Only endpoints that set ``query_params`` are included. The URL builder uses
    this instead of a path-specific list in the core template.
    """
    contracts: dict = {}
    for ep in endpoints or []:
        params = ep.get('query_params')
        path = str(ep.get('path') or '').strip()
        if not path or not params:
            continue
        contracts[path] = list(params)
    return contracts


def _url_builder_endpoint_groups(endpoints: list[dict]) -> list[dict]:
    """Keep registry group order; sort paths alphabetically inside each group."""
    order = []
    grouped: dict[str, list] = {}
    for ep in endpoints or []:
        name = (ep.get('group') or 'Other').strip() or 'Other'
        if name not in grouped:
            order.append(name)
            grouped[name] = []
        grouped[name].append(ep)
    return [
        {
            'name': name,
            'endpoints': sorted(grouped[name], key=_url_builder_endpoint_sort_key),
        }
        for name in order
    ]


def _assignment_label_for_url_builder(assignment: AssignedForm) -> str:
    """Label for URL-builder assignment dropdown (custom name, else template – period)."""
    template_name = (
        assignment.template.name
        if assignment.template and assignment.template.name
        else 'Template Missing'
    )
    period = (assignment.period_name or '').strip()
    default_label = f"{template_name} \u2013 {period}" if period else template_name
    custom = (assignment.custom_name or '').strip()
    if custom:
        if period and period not in custom:
            return f"{custom} ({template_name} \u2013 {period})"
        return custom
    return default_label


def _assignment_options_for_url_builder():
    """AssignedForm options for the API URL builder (id + label + API filter fields)."""
    assignments = (
        AssignedForm.query
        .options(joinedload(AssignedForm.template))
        .order_by(AssignedForm.assigned_at.desc(), AssignedForm.id.desc())
        .all()
    )
    assignments.sort(
        key=lambda af: (
            period_chronology_sort_key(
                af.period_name,
                period_start=af.period_start,
                period_end=af.period_end,
            ),
            (af.template.name if af.template and af.template.name else '').casefold(),
            -(af.id or 0),
        ),
        reverse=True,
    )
    return [
        {
            'id': af.id,
            'template_id': af.template_id,
            'period_name': af.period_name,
            'label': _assignment_label_for_url_builder(af),
        }
        for af in assignments
        if af and af.id is not None
    ]

bp = Blueprint('api_management', __name__, url_prefix='/admin')


def _count_unique_overlap_pairs(endpoints: list[dict]) -> int:
    """Undirected pairs from registry `overlaps` (same logical v1 ↔ mobile analogue counted once)."""
    pairs: set[tuple[str, str]] = set()
    for ep in endpoints:
        p = (ep.get('path') or '').strip()
        for o in ep.get('overlaps') or []:
            o = str(o).strip()
            if p and o:
                pairs.add(tuple(sorted((p, o))))
    return len(pairs)


# ---------------------------------------------------------------------------
# Live route scanner
# ---------------------------------------------------------------------------
import re as _re

# Methods Flask adds to every route that we never want to surface
_SKIP_METHODS = frozenset({'HEAD', 'OPTIONS'})

# Decision Maker JSON API (IFRC plugin). Paths sit under /api/ but not /api/v1.
_DECISION_API_PREFIXES = (
    '/api/decisions',
    '/api/decision-',
    '/api/metric-definitions',
)

# Indicator Bank app routes live at the site root, not under /api.
_INDICATOR_BANK_APP_ENDPOINT_PREFIX = 'indicator_bank_compat.'
# FDRS public-frontend adapter (legacy data-api paths such as /api/data and /csv/export).
# Plugin-owned; its view functions are all named ``fdrs_public_compat_*``.
_FDRS_PUBLIC_COMPAT_ENDPOINT_PREFIX = 'fdrs.fdrs_public_compat_'

# Mounted by flask-sock only when WEBSOCKET_ENABLED is on. Absent from url_map
# while sockets are off, which is expected rather than a removed route.
_WEBSOCKET_ROUTES = frozenset({
    '/api/ai/v2/ws',
    '/api/ai/documents/ws',
})

# AI-surface path heuristic: auth via resolve_ai_identity() inline (no decorator)
_AI_AUTH_HEURISTIC = 'ai_session'

# Flask uses <type:name> — strip the type annotation for comparison
def _normalize_path(path: str) -> str:
    return _re.sub(r'<[^:>]+:([^>]+)>', r'<\1>', path)


def _is_scanned_api_rule(path: str, endpoint: str | None = None) -> bool:
    """Routes the registry compares against the live url_map.

    Every ``/api/…`` route is included, not only ``/api/v1``, mobile, and AI.
    Indicator Bank app routes and the FDRS CSV export live outside that prefix
    and are picked up by view-function name.
    """
    if path.startswith('/api/'):
        return True
    return bool(
        endpoint
        and endpoint.startswith(
            (_INDICATOR_BANK_APP_ENDPOINT_PREFIX, _FDRS_PUBLIC_COMPAT_ENDPOINT_PREFIX)
        )
    )


def _surface_for_path(path: str, endpoint: str | None = None) -> str:
    if endpoint and endpoint.startswith(_FDRS_PUBLIC_COMPAT_ENDPOINT_PREFIX):
        return 'fdrs_public'
    if endpoint and endpoint.startswith(_INDICATOR_BANK_APP_ENDPOINT_PREFIX):
        return 'indicator_bank'
    if path.startswith('/api/mobile/v1/'):
        return 'mobile'
    if path.startswith('/api/ai/'):
        return 'ai'
    if path.startswith('/api/v1/'):
        return 'v1'
    if any(path.startswith(prefix) for prefix in _DECISION_API_PREFIXES):
        return 'decisions'
    return 'other'


def _auth_for_view(view_fn) -> tuple[str, str | None]:
    """Return (auth_type, permission) by reading _ep_auth/_ep_permission tags."""
    auth = getattr(view_fn, '_ep_auth', None)
    perm = getattr(view_fn, '_ep_permission', None)
    return auth, perm


def _capability_for_view(view_fn) -> str | None:
    """API-key capability declared on a view (see app.utils.auth.auth), following ``__wrapped__``."""
    seen = 0
    while view_fn is not None and seen < 20:
        capability = getattr(view_fn, '_ep_capability', None)
        if capability is not None:
            return capability
        view_fn = getattr(view_fn, '__wrapped__', None)
        seen += 1
    return None


def _collect_plugin_api_endpoints() -> list[dict]:
    """Registry rows contributed by loaded plugins via ``get_api_endpoints()``."""
    try:
        pm = getattr(current_app, 'plugin_manager', None)
    except RuntimeError:
        return []
    if pm is None:
        return []
    getter = getattr(pm, 'get_api_endpoints', None)
    if getter is None:
        return []
    try:
        return list(getter() or [])
    except Exception:
        current_app.logger.warning('plugin get_api_endpoints failed', exc_info=True)
        return []


def get_endpoint_registry() -> list[dict]:
    """Core ``ENDPOINT_REGISTRY`` plus plugin-owned ``/api/*`` routes."""
    combined = [dict(ep) for ep in ENDPOINT_REGISTRY]
    seen = {_normalize_path(ep['path']) for ep in combined if ep.get('path')}
    for ep in _collect_plugin_api_endpoints():
        path = _normalize_path(ep.get('path') or '')
        if not path or path in seen:
            continue
        seen.add(path)
        row = dict(ep)
        row.setdefault('surface', _surface_for_path(path))
        combined.append(row)
    return combined


def scan_flask_routes(app) -> dict:
    """
    Scan the live Flask url_map and compare against the unified registry
    (core ``ENDPOINT_REGISTRY`` plus plugin ``get_api_endpoints()``).

    Returns a dict with:
      live          – list of dicts for every tracked route found in url_map
                      (every /api/ route, plus Indicator Bank and FDRS CSV routes)
      undocumented  – routes in url_map but NOT in the registry
      stale         – registry entries whose path is NOT in url_map
      coverage_pct  – float (0–100)
    """
    registry = get_endpoint_registry()
    # ── Build a normalised set of registry paths ──────────────────────────
    registry_paths: set[str] = {
        _normalize_path(ep['path'])
        for ep in registry
    }

    # ── Walk the live url_map ─────────────────────────────────────────────
    live: list[dict] = []
    live_paths: set[str] = set()

    for rule in app.url_map.iter_rules():
        path = rule.rule
        if not _is_scanned_api_rule(path, rule.endpoint):
            continue

        methods = sorted(rule.methods - _SKIP_METHODS)
        norm   = _normalize_path(path)
        surface = _surface_for_path(path, rule.endpoint)

        view_fn  = app.view_functions.get(rule.endpoint)
        ep_auth, ep_perm = _auth_for_view(view_fn) if view_fn else (None, None)
        ep_capability = _capability_for_view(view_fn)

        # For AI routes without a decorator tag, fall back to heuristic
        if ep_auth is None and surface == 'ai':
            ep_auth = _AI_AUTH_HEURISTIC

        live.append({
            'path':       norm,
            'raw_path':   path,
            'methods':    methods,
            'surface':    surface,
            'ep_auth':    ep_auth,    # None means "not tagged"
            'ep_perm':    ep_perm,
            'ep_capability': ep_capability,
            'endpoint':   rule.endpoint,
            'in_registry': norm in registry_paths,
        })
        live_paths.add(norm)

    # ── Undocumented: in url_map but not in registry ──────────────────────
    undocumented = [r for r in live if not r['in_registry']]

    # ── Stale: in registry but path not found in url_map ─────────────────
    stale_paths = registry_paths - live_paths
    if not app.config.get('WEBSOCKET_ENABLED', False):
        stale_paths -= _WEBSOCKET_ROUTES
    stale = [ep for ep in registry if _normalize_path(ep['path']) in stale_paths]

    total_live = len(live_paths)
    documented = total_live - len(undocumented)
    coverage   = (documented / total_live * 100) if total_live else 100.0

    return {
        'live':          live,
        'undocumented':  undocumented,
        'stale':         stale,
        'coverage_pct':  round(coverage, 1),
        'total_live':    total_live,
        'documented':    documented,
    }


def _ep_surface_filter_disabled(grid_rows: list[dict]) -> dict[str, bool]:
    """Per chip: True if that filter matches zero rows (same rules as registry grid JS)."""

    def row_matches(row: dict, surface: str) -> bool:
        if surface == 'flagged':
            return bool(row.get('has_flags'))
        if surface == 'overlap':
            return bool(row.get('has_overlap'))
        if surface == 'has_stats':
            return bool(row.get('has_stats'))
        if surface == 'undocumented':
            return bool(row.get('undocumented'))
        if surface == 'stale':
            return bool(row.get('stale'))
        if surface == 'gaps':
            return bool(row.get('gaps'))
        return (row.get('surface') or '') == surface

    keys = (
        'v1',
        'mobile',
        'ai',
        'indicator_bank',
        'fdrs_public',
        'decisions',
        'other',
        'flagged',
        'overlap',
        'has_stats',
        'undocumented',
        'stale',
        'gaps',
    )
    return {k: not any(row_matches(r, k) for r in grid_rows) for k in keys}


def _endpoint_registry_grid_rows(all_endpoints: list[dict]) -> list[dict]:
    """JSON-serializable rows for AG Grid (Endpoint Registry)."""
    rows: list[dict] = []
    for ep in all_endpoints:
        surf = ep.get('surface') or ''
        grp = ep.get('group') or ''
        path = ep.get('path') or ''
        if surf == 'v1':
            group_label = f'External /v1 — {grp}'
        elif surf == 'mobile':
            group_label = f'Mobile — {grp}'
        elif surf == 'ai':
            if path.startswith('/api/ai/documents'):
                group_label = f'AI Documents — {grp}'
            else:
                group_label = f'AI /v2 — {grp}'
        elif surf == 'indicator_bank':
            group_label = grp or 'Indicator Bank app'
        elif surf == 'fdrs_public':
            group_label = grp or 'FDRS public frontend'
        elif surf == 'decisions':
            group_label = grp or 'Decision Maker'
        elif surf == 'other':
            group_label = grp or 'Other API'
        else:
            group_label = grp or '—'
        desc = ep.get('description') or ''
        flags = ep.get('flags') or []
        overlaps = ep.get('overlaps') or []
        methods = list(ep.get('methods') or [])
        consumers = ep.get('flutter') or ep.get('consumers') or ''
        tr = int(ep.get('total_requests') or 0)
        rows.append({
            'registryGroup': group_label,
            'surface': surf,
            'path': path,
            'pathLower': path.lower(),
            'pathSearch': ' '.join((
                path.lower(),
                desc.lower(),
                grp.lower(),
                group_label.lower(),
                consumers.lower(),
                ', '.join(methods).lower(),
                (ep.get('auth') or '').lower(),
                (ep.get('permission') or '').lower(),
                surf,
            )),
            'description': desc,
            'methods': methods,
            'methodsStr': ', '.join(methods),
            'auth': ep.get('auth') or '',
            'permission': ep.get('permission') or '',
            'consumers': consumers,
            'total_requests': tr,
            'success_rate': float(ep.get('success_rate') or 0),
            'featured': bool(ep.get('featured')),
            'has_flags': bool(flags),
            'has_overlap': bool(overlaps),
            'has_stats': tr > 0,
            'undocumented': bool(ep.get('undocumented')),
            'stale': bool(ep.get('stale')),
            'gaps': bool(ep.get('undocumented') or ep.get('stale')),
            'rate_limited': bool(ep.get('rate_limited')),
            'overlapPaths': list(overlaps),
            'flags': [{'type': f.get('type'), 'note': f.get('note') or ''} for f in flags],
        })
    return rows


@bp.route('/api-management')
@admin_permission_required('admin.api.manage')
def api_management():
    # ── Live route scan ───────────────────────────────────────────────────────
    # Compare url_map to the registry so undocumented / stale routes surface immediately.
    scan = scan_flask_routes(current_app._get_current_object())

    # Mark stale registry entries (path not found in live url_map)
    stale_paths = {_normalize_path(ep['path']) for ep in scan['stale']}

    # ── Unified endpoint registry ─────────────────────────────────────────────
    # Core registry plus plugin get_api_endpoints(); copies so usage stats stay request-local
    all_endpoints = get_endpoint_registry()

    # Stamp stale flag on registry entries whose path is no longer live
    for ep in all_endpoints:
        if _normalize_path(ep['path']) in stale_paths:
            ep['stale'] = True

    # Show the API-key capability each key-protected route enforces (declared in code, not hand-maintained)
    capability_by_path = {
        r['path']: r['ep_capability'] for r in scan['live'] if r.get('ep_capability')
    }
    for ep in all_endpoints:
        capability = capability_by_path.get(_normalize_path(ep['path']))
        if capability and ep.get('auth') in ('api_key', 'api_key_or_session') and not ep.get('permission'):
            ep['permission'] = capability

    # Append undocumented live routes at the end (shown with warning badge)
    for live_ep in scan['undocumented']:
        # Best-guess auth from decorator tag; fall back to '?' for truly unknown
        auth = live_ep['ep_auth'] or '?'
        all_endpoints.append({
            'surface':      live_ep['surface'],
            'group':        'Undocumented',
            'path':         live_ep['path'],
            'methods':      live_ep['methods'],
            'auth':         auth,
            'permission':   live_ep['ep_perm'] or live_ep.get('ep_capability') or '',
            'description':  '⚠ Route exists in Flask url_map but is not in the registry.',
            'consumers':    '',
            'rate_limited': False,
            'total_requests': 0,
            'success_rate': 100,
            'undocumented': True,
        })

    # Attach usage stats. Each logged path counts toward one registry route.
    usage_by_path = bulk_endpoint_usage_stats([ep['path'] for ep in all_endpoints])
    for ep in all_endpoints:
        stats = usage_by_path.get(ep['path'], {})
        ep['total_requests'] = stats.get('total_requests', 0)
        ep['success_rate'] = stats.get('success_rate', 100)

    # ── Per-surface summary ───────────────────────────────────────────────────
    def _surface_summary(surface_key):
        eps = [e for e in all_endpoints if e['surface'] == surface_key]
        return {
            'total':        len(eps),
            'public':       sum(1 for e in eps if e['auth'] == 'public'),
            'flagged':      sum(1 for e in eps if e.get('flags')),
            'overlapping':  sum(1 for e in eps if e.get('overlaps')),
            'rate_limited': sum(1 for e in eps if e.get('rate_limited')),
            'with_stats':   sum(1 for e in eps if e['total_requests'] > 0),
        }

    surface_summary = {
        'v1':              _surface_summary('v1'),
        'ai':              _surface_summary('ai'),
        'mobile':          _surface_summary('mobile'),
        'indicator_bank':  _surface_summary('indicator_bank'),
        'fdrs_public':     _surface_summary('fdrs_public'),
        'decisions':       _surface_summary('decisions'),
        'other':           _surface_summary('other'),
    }
    surface_summary['all'] = {
        'total':          len(all_endpoints),
        'flagged':        sum(1 for e in all_endpoints if e.get('flags')),
        # Unique v1↔mobile analogue pairs (registry may list both endpoints; grid filter still matches each row)
        'overlapping':    _count_unique_overlap_pairs(all_endpoints),
        'with_stats':     sum(1 for e in all_endpoints if e['total_requests'] > 0),
        'undocumented':   len(scan['undocumented']),
        'stale':          len(scan['stale']),
        'coverage_pct':   scan['coverage_pct'],
        'documented_live_paths': scan['documented'],
        'total_live_paths': scan['total_live'],
    }

    # ── v1, Indicator Bank app, and the FDRS public frontend for the URL builder ─
    v1_endpoints = [
        {**ep, 'method': '/'.join(ep['methods'])}
        for ep in all_endpoints
        if ep['surface'] in ('v1', 'indicator_bank', 'fdrs_public') and not ep.get('undocumented')
    ]
    url_builder_endpoint_groups = _url_builder_endpoint_groups(v1_endpoints)
    url_builder_contracts = _url_builder_param_contracts(v1_endpoints)

    # ── Legacy `api_endpoints` list kept for the chart / URL-builder selectors ─
    # Featured (endorsed) endpoints stay pinned at the top; then busiest first.
    api_endpoints = sorted(
        v1_endpoints,
        key=lambda x: (0 if x.get('featured') else 1, -int(x.get('total_requests') or 0)),
    )

    # ── Data for URL-builder dropdowns ────────────────────────────────────────
    templates = FormTemplate.query.all()
    templates.sort(key=lambda t: t.name if t.name else '')
    countries = Country.query.order_by(Country.name.asc()).all()
    users = User.query.order_by(User.name.asc()).all()
    assignment_options = _assignment_options_for_url_builder()

    sector_options     = [s.name for s in Sector.query.order_by(Sector.name.asc()).all()]
    sub_sector_options = [ss.name for ss in SubSector.query.order_by(SubSector.name.asc()).all()]
    type_options       = [
        t[0] for t in
        db.session.query(IndicatorBank.type).distinct().order_by(IndicatorBank.type.asc()).all()
    ]

    # ── Overall stats (APIUsage — covers v1 traffic only) ────────────────────
    total_requests    = APIUsage.query.count()
    avg_response_time = db.session.query(func.avg(APIUsage.response_time)).scalar() or 0
    success_rate      = (
        APIUsage.query.filter(APIUsage.status_code < 400).count() / total_requests * 100
        if total_requests > 0 else 100
    )
    unique_ips = APIUsage.query.with_entities(APIUsage.ip_address).distinct().count()

    # Chart data — last 24 h hourly breakdown (v1 traffic)
    last_24h  = utcnow() - timedelta(days=1)
    stats     = APIUsage.query.filter(
        usage_tracked_clause(),
        APIUsage.timestamp >= last_24h,
    ).all()
    hour_counts = {}
    for record in stats:
        hour = record.timestamp.strftime('%H:00')
        hour_counts[hour] = hour_counts.get(hour, 0) + 1
    all_hours = {}
    current   = utcnow()
    for i in range(24):
        hour = (current - timedelta(hours=i)).strftime('%H:00')
        all_hours[hour] = hour_counts.get(hour, 0)
    chart_data = [{'label': h, 'count': c} for h, c in reversed(all_hours.items())]

    endpoint_registry_grid_rows = _endpoint_registry_grid_rows(all_endpoints)
    ep_surface_filter_disabled = _ep_surface_filter_disabled(endpoint_registry_grid_rows)

    return render_template(
        'admin/api_management.html',
        # Unified registry
        all_endpoints=all_endpoints,
        endpoint_registry_grid_rows=endpoint_registry_grid_rows,
        ep_surface_filter_disabled=ep_surface_filter_disabled,
        surface_summary=surface_summary,
        # Backward-compat for URL builder + chart selector
        endpoints=api_endpoints,
        url_builder_endpoint_groups=url_builder_endpoint_groups,
        url_builder_contracts=url_builder_contracts,
        # Overview stats (v1 / APIUsage)
        total_requests=total_requests,
        avg_response_time=avg_response_time,
        success_rate=success_rate,
        unique_ips=unique_ips,
        chart_data=chart_data,
        # URL builder dropdowns
        sector_options=sector_options,
        sub_sector_options=sub_sector_options,
        type_options=type_options,
        templates=templates,
        countries=countries,
        assignment_options=assignment_options,
        users=users,
        # Legacy — keep mobile_summary accessible if needed elsewhere
        mobile_summary=surface_summary['mobile'],
    )



@bp.route('/api-management/stats')
@admin_permission_required('admin.api.manage')
def api_stats():
    try:
        period = request.args.get('period', 'daily')
        endpoint = request.args.get('endpoint', 'all')

        base_query = APIUsage.query.filter(usage_tracked_clause())
        if endpoint != 'all':
            logged = [
                row[0]
                for row in base_query.with_entities(APIUsage.api_endpoint).distinct().all()
            ]
            from app.services.platform.api_usage_stats import assign_logged_paths

            registry_paths = [ep['path'] for ep in get_endpoint_registry()]
            assigned = assign_logged_paths(registry_paths, logged)
            matched = [logged_path for logged_path, route in assigned.items() if route == endpoint]
            base_query = base_query.filter(
                APIUsage.api_endpoint.in_(matched or ['\x00'])
            )

        if period not in ('daily', 'weekly', 'monthly', 'quarterly', 'yearly'):
            period = 'daily'

        formatted_stats = chart_stats_for_period(base_query, period)
        return json_ok(stats=formatted_stats)

    except Exception as e:
        current_app.logger.error(f"Error in api_stats: {str(e)}", exc_info=True)
        return json_server_error(GENERIC_ERROR_MESSAGE)
