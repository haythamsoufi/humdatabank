# ========== File: app/forms/content/__init__.py ==========
"""
Content management forms for resources, translations, and content-related entities.
"""

from .resource_forms import ResourceForm
from .translation_forms import TranslationForm

__all__ = [
    'ResourceForm',
    'TranslationForm'
]
