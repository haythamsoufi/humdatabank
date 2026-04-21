# ========== File: app/forms/__init__.py ==========
"""
Forms package for the platform.
Organized by domain for better maintainability and separation of concerns.
"""

# Import base utilities
from .base import (
    BaseForm, MultilingualForm, FileUploadForm, CommonFields, CommonValidators,
    MultilingualFieldsMixin, LayoutFieldsMixin, DataAvailabilityMixin, SkipLogicMixin,
    int_or_none, lookup_list_id_coerce
)

# Import forms from each domain explicitly to avoid namespace pollution
from .system import (
    CountryForm,
    UserForm,
    IndicatorBankForm,
    SectorForm,
    SubSectorForm,
    CommonWordForm,
)
from .content import (
    ResourceForm,
    TranslationForm,
)
from .form_builder import (
    FormTemplateForm,
    FormSectionForm,
    IndicatorForm,
    QuestionForm,
    DocumentFieldForm,
    MatrixForm,
    PluginItemForm,
)
from .assignments import (
    AssignedFormForm,
    AssignmentEntityStatusForm,
    ReopenAssignmentForm,
    ApproveAssignmentForm,
)
from .shared import (
    DeleteForm,
    PublicSubmissionDetailsForm,
)

__all__ = [
    # Base classes and utilities
    'BaseForm', 'MultilingualForm', 'FileUploadForm', 'CommonFields', 'CommonValidators',
    'MultilingualFieldsMixin', 'LayoutFieldsMixin', 'DataAvailabilityMixin', 'SkipLogicMixin',
    'int_or_none', 'lookup_list_id_coerce',

    # System forms
    'CountryForm', 'UserForm', 'IndicatorBankForm', 'SectorForm', 'SubSectorForm', 'CommonWordForm',

    # Content forms
    'ResourceForm', 'TranslationForm',

    # Form builder forms
    'FormTemplateForm', 'FormSectionForm', 'IndicatorForm', 'QuestionForm',
    'DocumentFieldForm', 'MatrixForm', 'PluginItemForm',

    # Assignment forms
    'AssignedFormForm', 'AssignmentEntityStatusForm', 'ReopenAssignmentForm', 'ApproveAssignmentForm',

    # Shared forms
    'DeleteForm', 'PublicSubmissionDetailsForm'
]
