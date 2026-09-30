"""Path conftest for tests/.

Shared fixtures/hooks are loaded from the Backoffice root ``conftest.py``
via ``pytest_plugins = ["tests.shared_fixtures"]`` so ``plugins/*/tests``
see the same fixtures when collected together.
"""
