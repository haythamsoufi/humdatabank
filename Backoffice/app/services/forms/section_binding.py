"""Registry for plugin-owned dynamic section bindings.

Core form entry, export, variable resolution, and save call this module.
A plugin registers a provider that decides which sections it owns, which
template variables it supplies, and how a binding is stored.
"""

import logging

logger = logging.getLogger(__name__)

_providers = []


def register_section_binding_provider(provider) -> None:
    """Replace any previous provider with the same ``provider_id``."""
    provider_id = getattr(provider, 'provider_id', None)
    if not provider_id:
        raise ValueError('section binding provider requires provider_id')
    unregister_section_binding_provider(provider_id)
    _providers.append(provider)


def unregister_section_binding_provider(provider_id: str) -> None:
    _providers[:] = [p for p in _providers if getattr(p, 'provider_id', None) != provider_id]


def resolve_section_variables(aes) -> dict:
    """Merge template variables from every registered provider."""
    resolved = {}
    for provider in list(_providers):
        resolve = getattr(provider, 'resolve_variables', None)
        if not callable(resolve):
            continue
        try:
            values = resolve(aes) or {}
        except Exception as exc:
            logger.debug(
                'Section binding provider %s failed to resolve variables: %s',
                getattr(provider, 'provider_id', provider),
                exc,
            )
            continue
        if isinstance(values, dict):
            resolved.update(values)
    return resolved


def persist_section_bindings(section, aes, user_id=None):
    """Ask each provider that owns ``section`` to store its binding."""
    result = None
    for provider in list(_providers):
        owns = getattr(provider, 'owns_section', None)
        if callable(owns):
            try:
                if not owns(section):
                    continue
            except Exception as exc:
                logger.debug(
                    'Section binding provider %s failed ownership check: %s',
                    getattr(provider, 'provider_id', provider),
                    exc,
                )
                continue
        persist = getattr(provider, 'persist', None)
        if not callable(persist):
            continue
        try:
            result = persist(section, aes, user_id)
        except Exception:
            logger.exception(
                'Section binding provider %s failed to persist',
                getattr(provider, 'provider_id', provider),
            )
    return result
