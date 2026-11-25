"""Report buttons in the header of a cycle's entry form.

Someone filing a cycle can start an operational update from it. The final
report is only offered on the last reporting period of the operation.
"""

from __future__ import annotations

from plugins.emergency_operations_monitoring.access import current_actor
from plugins.emergency_operations_monitoring.services.entry_activities import resolve_cycle
from plugins.emergency_operations_monitoring.services.reporting import periods_for

OPERATIONAL_UPDATE = "operational_update"
FINAL_REPORT = "final_report"


def is_final_cycle(operation, period) -> bool:
    """True when this period is the last one on the operation."""
    if operation is None or period is None:
        return False
    periods = periods_for(operation.id)
    return bool(periods) and periods[-1].id == period.id


def report_kinds_for(operation, period) -> list[str]:
    kinds = [OPERATIONAL_UPDATE]
    if is_final_cycle(operation, period):
        kinds.append(FINAL_REPORT)
    return kinds


def report_actions_context(assignment_entity_status, actor=None) -> dict | None:
    """What the header buttons need, or None when this is not a DREF cycle the person can report on."""
    operation, period = resolve_cycle(assignment_entity_status)
    if operation is None or period is None:
        return None
    actor = actor or current_actor()
    if not actor.allows(operation, "enter"):
        return None
    from plugins.emergency_operations_monitoring.config_store import ai_enabled

    return {
        "operation": operation,
        "period": period,
        "kinds": report_kinds_for(operation, period),
        "ai_ready": bool(ai_enabled()),
        "aes_id": assignment_entity_status.id,
    }
