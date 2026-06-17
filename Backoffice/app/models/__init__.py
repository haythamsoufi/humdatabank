"""
Models package for the application.

This package contains all database models organized by functionality:
- core: User, Country, and activity tracking models
- forms: Form templates, sections, items, and data models
- form_items: The unified FormItem model
- assignments: Form assignments and public submissions
- indicator_bank: Indicator definitions, sectors, and common words
- documents: Document uploads and resource management
- lookups: Dynamic lookup tables
- organization: National Society hierarchy models
- system: Logging, notifications, and security models
- enums: Enum definitions used across models
"""

# Import the database instance
from app.extensions import db

# Import Config for utility functions
from config import Config

# Import all models to make them available
from .core import (
    User,
    Country,
    UserLoginLog,
    UserActivityLog,
    UserSessionLog,
    UserEntityPermission
)

from .forms import (
    FormTemplate,
    FormPage,
    FormSection,
    FormData,
    DynamicIndicatorData,
    DynamicSectionContext,
    RepeatGroupInstance,
    RepeatGroupData,
    TemplateShare,
    FormTemplateVersion
)

from .form_items import FormItem

from .assignments import (
    AssignedForm,
    AssignmentEntityStatus,
    PublicSubmission,
    ReportingPeriod
)

from .indicator_bank import (
    IndicatorBank,
    IndicatorBankHistory,
    IndicatorBankSpef,
    IndicatorBankType,
    IndicatorBankUnit,
    IndicatorSuggestion,
    Sector,
    SubSector,
    CommonWord
)

from .documents import (
    SubmittedDocument,
    Resource,
    ResourceSubcategory,
    ResourceTranslation
)

from .embed_content import EmbedContent

from .lookups import (
    LookupList,
    LookupListRow
)

from .organization import (
    NationalSociety,
    NSBranch,
    NSSubBranch,
    NSLocalUnit,
    SecretariatDivision,
    SecretariatRegionalOffice,
    SecretariatClusterOffice,
    SecretariatDepartment
)

from .system import (
    AdminActionLog,
    SecurityEvent,
    Notification,
    NotificationPreferences,
    NotificationCampaign,
    EntityActivityLog,
    CountryAccessRequest,
    SystemSettings,
    UserDevice,
    EmailDeliveryLog
)

from .api_key_management import (
    APIKey,
    APIKeyUsage
)

from .api_usage import APIUsage

from .password_reset_token import (
    PasswordResetToken
)

from .ai_chat import (
    AIConversation,
    AIMessage,
)

from .rbac import (
    RbacPermission,
    RbacRole,
    RbacRolePermission,
    RbacUserRole,
    RbacAccessGrant,
)

from .ai_jobs import (
    AIJob,
    AIJobItem,
)

from .ai_validation import (
    AIFormDataValidation,
)

from .validation import (
    ValidationQuestion,
    ValidationDispatchBatch,
    ValidationThreshold,
    ValidationKpiCheckType,
    ValidationQuestionTemplate,
    CountryYearReference,
    CountryAttribute,
)

# pgvector (and numpy 2.4+) are loaded lazily — see ``__getattr__`` below.
# Eager imports here break pytest-cov narrow ``--cov=app.module`` runs because
# coverage re-imports modules and numpy rejects double extension init.
_LAZY_MODEL_MODULES = {
    'AIDocument': 'embeddings',
    'AIDocumentChunk': 'embeddings',
    'AIEmbedding': 'embeddings',
    'IndicatorBankEmbedding': 'embeddings',
    'AIReasoningTrace': 'embeddings',
    'AIToolUsage': 'embeddings',
    'AITraceReview': 'embeddings',
    'AITermConcept': 'ai_terminology',
    'AITermGlossary': 'ai_terminology',
    'AITermConceptEmbedding': 'ai_terminology',
}


def __getattr__(name: str):
    module_name = _LAZY_MODEL_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    module = import_module(f'.{module_name}', __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value

from .enums import (
    AssignmentEntityStatusValue,
    DocumentStatus,
    DocumentStatusValue,
    CountryAccessRequestStatus,
    CountryAccessRequestStatusValue,
    FormTemplateVersionStatusValue,
    IndicatorSuggestionStatusValue,
    IndicatorSuggestionTypeValue,
    NotificationCampaignStatusValue,
    EmailDeliveryStatusValue,
    AIJobStatusValue,
    AIJobItemStatusValue,
    AIDocumentProcessingStatusValue,
    AIReasoningTraceStatusValue,
    AITraceReviewStatusValue,
    AITraceReviewVerdictValue,
    AIFormDataValidationStatusValue,
    AIFormDataValidationVerdictValue,
    PublicSubmissionStatus,
    status_display_label,
    STATUS_DISPLAY_LABELS,
    QuestionType,
    SectionType,
    FormItemType,
    NotificationType,
    EntityType,
)

# Export all models for easy importing
__all__ = [
    # Database instance
    'db',

    # Config
    'Config',

    # Core models
    'User',
    'Country',
    'UserLoginLog',
    'UserActivityLog',
    'UserSessionLog',
    'UserEntityPermission',

    # Form models
    'FormTemplate',
    'FormPage',
    'FormSection',
    'FormItem',
    'FormData',
    'DynamicIndicatorData',
    'DynamicSectionContext',
    'RepeatGroupInstance',
    'RepeatGroupData',
    'TemplateShare',

    # Assignment models
    'AssignedForm',
    'AssignmentEntityStatus',
    'PublicSubmission',
    'ReportingPeriod',

    # Indicator Bank models
    'IndicatorBank',
    'IndicatorBankHistory',
    'IndicatorBankSpef',
    'IndicatorBankType',
    'IndicatorBankUnit',
    'IndicatorSuggestion',
    'Sector',
    'SubSector',
    'CommonWord',

    # Document models
    'SubmittedDocument',
    'Resource',
    'ResourceSubcategory',
    'ResourceTranslation',

    # Embed content
    'EmbedContent',

    # Lookup models
    'LookupList',
    'LookupListRow',

    # Organization models
    'NationalSociety',
    'NSBranch',
    'NSSubBranch',
    'NSLocalUnit',
    'SecretariatDivision',
    'SecretariatRegionalOffice',
    'SecretariatClusterOffice',
    'SecretariatDepartment',

    # System models
    'AdminActionLog',
    'SecurityEvent',
    'Notification',
    'NotificationPreferences',
    'NotificationCampaign',
    'EntityActivityLog',
    'CountryAccessRequest',
    'SystemSettings',
    'UserDevice',
    'EmailDeliveryLog',

    # API Key Management models
    'APIKey',
    'APIKeyUsage',

    # API Usage tracking
    'APIUsage',

    # Password Reset Token models
    'PasswordResetToken',

    # AI Chat models
    'AIConversation',
    'AIMessage',

    # AI Embeddings models
    'AIDocument',
    'AIDocumentChunk',
    'AIEmbedding',
    'IndicatorBankEmbedding',
    'AIReasoningTrace',
    'AIToolUsage',
    'AITraceReview',

    # Generic AI queued jobs
    'AIJob',
    'AIJobItem',

    # AI validation models
    'AIFormDataValidation',

    # Validation / data quality models
    'ValidationQuestion',
    'ValidationDispatchBatch',
    'ValidationThreshold',
    'ValidationKpiCheckType',
    'ValidationQuestionTemplate',
    'CountryYearReference',
    'CountryAttribute',

    # AI terminology models
    'AITermConcept',
    'AITermGlossary',
    'AITermConceptEmbedding',

    # RBAC models
    'RbacPermission',
    'RbacRole',
    'RbacRolePermission',
    'RbacUserRole',
    'RbacAccessGrant',

    # Enums
    'AssignmentEntityStatusValue',
    'PublicSubmissionStatus',
    'QuestionType',
    'SectionType',
    'FormItemType',
    'NotificationType',
    'EntityType',
]
