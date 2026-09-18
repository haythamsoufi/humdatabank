"""Register IFRC GO-API import routes from ``plugins.upr.ai.ifrc_routes``.

Kept as a same-package import so ``ai_documents.__init__`` does not load
``plugins.upr.routes`` (that package import pulls the Data Explorer blueprint
and can deadlock if ``ai_documents`` is still initializing).
"""

from plugins.upr.ai import ifrc_routes as _ifrc_routes  # noqa: F401
