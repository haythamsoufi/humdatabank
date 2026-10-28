"""Deprecated: NSD uses the core ``Project`` model.

Kept so older imports ``from plugins.nsd_report_forms.models import NsdProject``
still resolve during transition.
"""

from app.models.projects import Project as NsdProject  # noqa: F401

__all__ = ["NsdProject"]
