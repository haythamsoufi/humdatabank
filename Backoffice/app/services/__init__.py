# ========== Services Package ==========
"""
Business logic services for the platform.

This package contains service classes that encapsulate complex business logic
and data processing operations, extracted from route handlers for better
organization and testability.
"""

from .form_data_service import FormDataService
from .notification_service import NotificationService
from .push_notification_service import PushNotificationService
from .document_service import DocumentService
from .country_service import CountryService
from .template_service import TemplateService
from .user_service import UserService
from .assignment_service import AssignmentService
from .data_retrieval_service import (
    get_user_profile,
    get_country_info,
    get_indicator_details,
    get_template_structure,
    get_value_breakdown,
    get_assignments_for_country,
    get_platform_stats,
    get_user_data_context,
    check_country_access,
    get_formdata_map,
    get_aes_with_joins,
    ensure_aes_access,
    get_user_countries,
    get_user_country_ids,
    query_form_data,
    get_form_data_queries,
)

__all__ = [
    'FormDataService',
    'NotificationService',
    'PushNotificationService',
    'DocumentService',
    'CountryService',
    'TemplateService',
    'UserService',
    'AssignmentService',
    'get_user_profile',
    'get_country_info',
    'get_indicator_details',
    'get_template_structure',
    'get_value_breakdown',
    'get_assignments_for_country',
    'get_platform_stats',
    'get_user_data_context',
    'check_country_access',
    'get_formdata_map',
    'get_aes_with_joins',
    'ensure_aes_access',
    'get_user_countries',
    'get_user_country_ids',
    'query_form_data',
    'get_form_data_queries',
]
