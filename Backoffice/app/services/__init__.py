# ========== Services Package ==========
"""
Business logic services for the platform.

This package contains service classes that encapsulate complex business logic
and data processing operations, extracted from route handlers for better
organization and testability.

Exports are loaded lazily so importing a submodule (e.g. ``security``) does not
pull in heavy dependencies such as pgvector/numpy via ``data_retrieval.service``.
"""

_LAZY_EXPORT_MODULES = {
    'FormDataService': 'forms.data_service',
    'NotificationService': 'notification.service',
    'PushNotificationService': 'notification.push',
    'DocumentService': 'documents.service',
    'CountryService': 'organization.country_service',
    'TemplateService': 'templates.service',
    'UserService': 'platform.user_service',
    'AssignmentService': 'assignments.service',
    'get_user_profile': 'data_retrieval.service',
    'get_country_info': 'data_retrieval.service',
    'get_indicator_details': 'data_retrieval.service',
    'get_template_structure': 'data_retrieval.service',
    'get_value_breakdown': 'data_retrieval.service',
    'get_assignments_for_country': 'data_retrieval.service',
    'get_platform_stats': 'data_retrieval.service',
    'get_user_data_context': 'data_retrieval.service',
    'check_country_access': 'data_retrieval.service',
    'get_formdata_map': 'data_retrieval.service',
    'get_aes_with_joins': 'data_retrieval.service',
    'check_aes_access_light': 'data_retrieval.service',
    'ensure_aes_access': 'data_retrieval.service',
    'get_user_countries': 'data_retrieval.service',
    'get_user_country_ids': 'data_retrieval.service',
    'query_form_data': 'data_retrieval.service',
    'get_form_data_queries': 'data_retrieval.service',
    'query_dynamic_indicator_data': 'data_retrieval.service',
    'query_repeat_group_data': 'data_retrieval.service',
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
