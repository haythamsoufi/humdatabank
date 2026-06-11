# ========== Services Package ==========
"""
Business logic services for the platform.

This package contains service classes that encapsulate complex business logic
and data processing operations, extracted from route handlers for better
organization and testability.

Exports are loaded lazily so importing a submodule (e.g. ``security``) does not
pull in heavy dependencies such as pgvector/numpy via ``data_retrieval_service``.
"""

_LAZY_EXPORT_MODULES = {
    'FormDataService': 'form_data_service',
    'NotificationService': 'notification_service',
    'PushNotificationService': 'push_notification_service',
    'DocumentService': 'document_service',
    'CountryService': 'country_service',
    'TemplateService': 'template_service',
    'UserService': 'user_service',
    'AssignmentService': 'assignment_service',
    'get_user_profile': 'data_retrieval_service',
    'get_country_info': 'data_retrieval_service',
    'get_indicator_details': 'data_retrieval_service',
    'get_template_structure': 'data_retrieval_service',
    'get_value_breakdown': 'data_retrieval_service',
    'get_assignments_for_country': 'data_retrieval_service',
    'get_platform_stats': 'data_retrieval_service',
    'get_user_data_context': 'data_retrieval_service',
    'check_country_access': 'data_retrieval_service',
    'get_formdata_map': 'data_retrieval_service',
    'get_aes_with_joins': 'data_retrieval_service',
    'ensure_aes_access': 'data_retrieval_service',
    'get_user_countries': 'data_retrieval_service',
    'get_user_country_ids': 'data_retrieval_service',
    'query_form_data': 'data_retrieval_service',
    'get_form_data_queries': 'data_retrieval_service',
}

__all__ = list(_LAZY_EXPORT_MODULES.keys())


def __getattr__(name: str):
    module_name = _LAZY_EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from importlib import import_module

    module = import_module(f'.{module_name}', __name__)
    value = getattr(module, name)
    globals()[name] = value
    return value
