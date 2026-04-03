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
    RepeatGroupInstance,
    RepeatGroupData,
    TemplateShare,
    FormTemplateVersion
)

from .form_items import FormItem

from .assignments import (
    AssignedForm,
    AssignmentEntityStatus,
    PublicSubmission
)

from .indicator_bank import (
    IndicatorBank,
    IndicatorBankHistory,
    IndicatorSuggestion,
    Sector,
    SubSector,
    CommonWord
)

from .documents import (
    SubmittedDocument,
    Resource,
    ResourceTranslation
)

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

from .embeddings import (
    AIDocument,
    AIDocumentChunk,
    AIEmbedding,
    IndicatorBankEmbedding,
    AIReasoningTrace,
    AIToolUsage,
    AITraceReview,
)

from .ai_jobs import (
    AIJob,
    AIJobItem,
)

from .ai_validation import (
    AIFormDataValidation,
)

from .ai_terminology import (
    AITermConcept,
    AITermGlossary,
    AITermConceptEmbedding,
)

from .enums import (
    PublicSubmissionStatus,
    QuestionType,
    SectionType,
    FormItemType,
    NotificationType,
    EntityType
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
    'RepeatGroupInstance',
    'RepeatGroupData',
    'TemplateShare',

    # Assignment models
    'AssignedForm',
    'AssignmentEntityStatus',
    'PublicSubmission',

    # Indicator Bank models
    'IndicatorBank',
    'IndicatorBankHistory',
    'IndicatorSuggestion',
    'Sector',
    'SubSector',
    'CommonWord',

    # Document models
    'SubmittedDocument',
    'Resource',
    'ResourceTranslation',

    # Lookup models
    'LookupList',
    'LookupListRow',

    # Organization models
    'NationalSociety',
    'NSBranch',
    'NSSubBranch',
    'NSLocalUnit',
    'SecretariatDivision',
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
    'PublicSubmissionStatus',
    'QuestionType',
    'SectionType',
    'FormItemType',
    'NotificationType',
    'EntityType',
]
