"""Build human-readable + structured diagnostics for platform 5xx security events."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from app.services.monitoring.request_pressure import snapshot_inflight

_PLATFORM_5XX_CODES = {502, 503, 504}

_CAUSE_LABELS = {
    'stale_workers': 'Gunicorn worker(s) blocked on requests exceeding the timeout window',
    'db_pool_pressure': 'Database connection pool near or at capacity on this worker',
    'high_in_flight': 'Many concurrent requests in flight on this worker',
    'traffic_spike': 'Elevated request rate on this worker in the last minute',
    'upstream_gateway_timeout': 'Gateway timeout (likely queue/wait; no stale workers visible on this process)',
}


def is_platform_5xx(error_code: int) -> bool:
    return int(error_code) in _PLATFORM_5XX_CODES


def _infer_likely_causes(metrics: Dict[str, Any]) -> List[str]:
    causes: List[str] = []
    stale = int(metrics.get('stale_in_flight_count') or 0)
    in_flight = int(metrics.get('in_flight_count') or 0)
    traffic_60s = int(metrics.get('traffic_last_60s') or 0)
    pool = metrics.get('db_pool') or {}

    if stale > 0:
        causes.append('stale_workers')
    checked_out = pool.get('checked_out')
    pool_size = pool.get('size')
    overflow = pool.get('overflow') or 0
    if (
        isinstance(checked_out, int)
        and isinstance(pool_size, int)
        and pool_size > 0
        and checked_out >= pool_size
        and overflow > 0
    ):
        causes.append('db_pool_pressure')
    threads = metrics.get('gunicorn_threads')
    if in_flight >= 8 or (isinstance(threads, int) and in_flight >= max(threads - 1, 1)):
        causes.append('high_in_flight')
    if traffic_60s >= 40:
        causes.append('traffic_spike')
    if not causes:
        causes.append('upstream_gateway_timeout')
    return causes


def _format_stale_lines(in_flight: List[Dict[str, Any]], limit: int = 3) -> str:
    stale_rows = [row for row in in_flight if row.get('stale')]
    if not stale_rows:
        return ''
    parts = []
    for row in stale_rows[:limit]:
        parts.append(
            f"{row.get('method')} {row.get('path')} ({row.get('elapsed_s')}s)"
        )
    return '; '.join(parts)


def build_platform_5xx_diagnostics(
    *,
    error_code: int,
    failed_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Return diagnostics payload for security-event context_data."""
    metrics = snapshot_inflight()
    causes = _infer_likely_causes(metrics)
    cause_text = '; '.join(_CAUSE_LABELS.get(key, key) for key in causes)

    stale_summary = _format_stale_lines(metrics.get('in_flight_requests') or [])
    pool = metrics.get('db_pool') or {}
    pool_text = ''
    if pool.get('checked_out') is not None and pool.get('size') is not None:
        pool_text = (
            f"DB pool {pool.get('checked_out')}/{pool.get('size')} checked out"
            f" (overflow {pool.get('overflow', 0)})"
        )

    summary_parts = [
        f"HTTP {error_code} platform error",
        f"likely: {cause_text}",
        f"worker pid {metrics.get('worker_pid')}: "
        f"{metrics.get('in_flight_count')} in-flight"
        f" ({metrics.get('stale_in_flight_count')} stale ≥{metrics.get('gunicorn_timeout_s')}s)",
        f"traffic {metrics.get('traffic_last_60s')}/min, {metrics.get('traffic_last_5m')}/5m on this worker",
    ]
    if pool_text:
        summary_parts.append(pool_text)
    if stale_summary:
        summary_parts.append(f"stale/holding: {stale_summary}")
    if failed_url:
        summary_parts.append(f"failed URL: {failed_url}")

    return {
        'diagnostics_summary': '. '.join(summary_parts),
        'likely_causes': causes,
        'failed_url': failed_url,
        'worker_metrics': metrics,
    }


def attach_platform_5xx_diagnostics(
    context_data: Dict[str, Any],
    *,
    error_code: int,
    failed_url: Optional[str] = None,
    max_json_bytes: int = 12000,
) -> Dict[str, Any]:
    """Merge diagnostics into context_data, trimming if the JSON payload is too large."""
    if not is_platform_5xx(error_code):
        return context_data

    try:
        diagnostics = build_platform_5xx_diagnostics(
            error_code=error_code,
            failed_url=failed_url,
        )
    except Exception:
        diagnostics = {
            'diagnostics_summary': 'Diagnostics collection failed on this worker.',
            'likely_causes': ['unknown'],
        }

    merged = {**context_data, **diagnostics}
    merged['source'] = context_data.get('source') or 'client_reporter'

    payload = json.dumps(merged, default=str)
    if len(payload) <= max_json_bytes:
        return merged

    # Drop detailed in-flight rows first; keep summary text.
    trimmed = dict(merged)
    worker_metrics = dict(trimmed.get('worker_metrics') or {})
    worker_metrics['in_flight_requests'] = (worker_metrics.get('in_flight_requests') or [])[:5]
    worker_metrics['recent_slow_completions'] = (
        worker_metrics.get('recent_slow_completions') or []
    )[:3]
    trimmed['worker_metrics'] = worker_metrics
    trimmed['diagnostics_truncated'] = True

    if len(json.dumps(trimmed, default=str)) > max_json_bytes:
        trimmed.pop('worker_metrics', None)

    return trimmed
