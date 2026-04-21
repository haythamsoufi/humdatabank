# Backoffice/app/plugins/__init__.py

from .manager import PluginManager
from .base import BaseFieldType, BasePlugin

__all__ = ['PluginManager', 'BaseFieldType', 'BasePlugin']
