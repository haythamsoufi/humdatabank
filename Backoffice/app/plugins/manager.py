# Backoffice/app/plugins/manager.py
from app.utils.datetime_helpers import utcnow

import os
import sys
import importlib.util
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from flask import Flask, current_app
from .base import BasePlugin, BaseFieldType
import shutil
import json
from datetime import datetime
import hashlib
import time
from functools import lru_cache
import threading

from jinja2 import ChoiceLoader

from .jinja_plugin_loader import PluginTemplateLoader

class PluginManager:
    """Manages plugin discovery, loading, and lifecycle."""

    def __init__(self, app: Flask):
        self.app = app
        self.logger = logging.getLogger(__name__)
        # Disable verbose plugin logs by setting level to WARNING
        self.logger.setLevel(logging.WARNING)
        # Canonical identity is plugin_id
        self.plugins: Dict[str, BasePlugin] = {}
        self.active_plugins: Set[str] = set()  # set of plugin_id
        self.field_types: Dict[str, BaseFieldType] = {}
        self.field_type_to_plugin_id: Dict[str, str] = {}
        self.plugin_installations: Dict[str, Dict[str, Any]] = {}
        self.plugin_dirs: Dict[str, Path] = {}
        self.template_dirs: Dict[str, Path] = {}
        self.static_dirs: Dict[str, Path] = {}

        # Plugin directories to scan
        self.plugin_directories = [
            Path(app.root_path) / 'plugins',  # Core plugins
            Path(app.root_path).parent / 'plugins'  # External plugins
        ]

        # Plugin state file path
        self.state_file_path = Path(app.instance_path) / 'plugin_states.json'

        # Caching and optimization
        self._discovery_cache = {}
        self._discovery_cache_file = Path(app.instance_path) / 'plugin_discovery_cache.json'
        self._state_update_lock = threading.Lock()
        self._pending_state_updates = []
        self._loaded_plugin_modules = {}  # Cache for loaded modules

        # Load plugin states on initialization
        self._load_plugin_states()
        self._load_discovery_cache()

    def _load_plugin_states(self):
        """Load plugin activation states from persistent storage."""
        try:
            if self.state_file_path.exists():
                with open(self.state_file_path, 'r') as f:
                    state_data = json.load(f)
                    # Support new and legacy keys.
                    # - New: active_plugin_ids
                    # - Legacy: active_plugins (could be plugin_id or display_name)
                    self._raw_active_tokens = list(state_data.get('active_plugin_ids') or state_data.get('active_plugins') or [])
                    self.active_plugins = set()  # resolved after plugins are loaded
                    self.logger.info(f"Loaded plugin states: {len(self._raw_active_tokens)} tokens")
            else:
                self.logger.info("No plugin state file found, all plugins will be active by default")
                self._raw_active_tokens = None
        except Exception as e:
            self.logger.error(f"Error loading plugin states: {e}")
            # Fallback: all plugins active by default
            self.active_plugins = set()
            self._raw_active_tokens = None

    def _load_discovery_cache(self):
        """Load plugin discovery cache from persistent storage."""
        try:
            if self._discovery_cache_file.exists():
                with open(self._discovery_cache_file, 'r') as f:
                    cache_data = json.load(f)
                    self._discovery_cache = cache_data.get('cache', {})
                    self.logger.info(f"Loaded discovery cache with {len(self._discovery_cache)} entries")
            else:
                self._discovery_cache = {}
        except Exception as e:
            self.logger.warning(f"Error loading discovery cache: {e}")
            self._discovery_cache = {}

    def _save_discovery_cache(self):
        """Save plugin discovery cache to persistent storage."""
        try:
            self._discovery_cache_file.parent.mkdir(parents=True, exist_ok=True)
            cache_data = {
                'cache': self._discovery_cache,
                'last_updated': utcnow().isoformat()
            }
            with open(self._discovery_cache_file, 'w') as f:
                json.dump(cache_data, f, indent=2)
        except Exception as e:
            self.logger.warning(f"Error saving discovery cache: {e}")

    def _get_directory_hash(self, directory: Path) -> str:
        """Generate a hash based on directory contents and modification times."""
        try:
            if not directory.exists():
                return ""

            hash_data = []
            for item in sorted(directory.iterdir()):
                if item.is_dir() and not item.name.startswith('.'):
                    stat = item.stat()
                    hash_data.append(f"{item.name}:{stat.st_mtime}:{stat.st_size}")

                    # Also include main plugin file modification time
                    plugin_py = item / "plugin.py"
                    plugin_json = item / "plugin.json"
                    if plugin_py.exists():
                        plugin_stat = plugin_py.stat()
                        hash_data.append(f"plugin.py:{plugin_stat.st_mtime}")
                    elif plugin_json.exists():
                        plugin_stat = plugin_json.stat()
                        hash_data.append(f"plugin.json:{plugin_stat.st_mtime}")

            return hashlib.md5('|'.join(hash_data).encode()).hexdigest()
        except Exception as e:
            self.logger.warning(f"Error generating directory hash for {directory}: {e}")
            return str(time.time())  # Fallback to timestamp

    def _save_plugin_states(self):
        """Save plugin activation states to persistent storage with batching."""
        with self._state_update_lock:
            try:
                # Process any pending updates
                if self._pending_state_updates:
                    for update in self._pending_state_updates:
                        plugin_name, action = update
                        # Process update logic here if needed
                    self._pending_state_updates.clear()

                # Ensure the instance directory exists
                self.state_file_path.parent.mkdir(parents=True, exist_ok=True)

                state_data = {
                    # Canonical
                    'active_plugin_ids': sorted(list(self.active_plugins)),
                    'last_updated': utcnow().isoformat()
                }

                with open(self.state_file_path, 'w') as f:
                    json.dump(state_data, f, indent=2)

                self.logger.info(f"Saved plugin states: {len(self.active_plugins)} active plugins")
            except Exception as e:
                self.logger.error(f"Error saving plugin states: {e}")

    def register_template_loader(self) -> None:
        """
        Register deterministic plugin template loader so templates can be referenced as:
            plugins/<plugin_id>/<template>.html
        """
        try:
            existing_loader = self.app.jinja_loader
            plugin_loader = PluginTemplateLoader(lambda pid: self.template_dirs.get(pid))

            if existing_loader:
                self.app.jinja_loader = ChoiceLoader([existing_loader, plugin_loader])
            else:
                self.app.jinja_loader = plugin_loader

            # Ensure env uses the updated loader
            if hasattr(self.app, "jinja_env") and self.app.jinja_env is not None:
                self.app.jinja_env.loader = self.app.jinja_loader
        except Exception as e:
            self.logger.error(f"Failed to register plugin template loader: {e}", exc_info=True)

    def _queue_state_update(self, plugin_name: str, action: str):
        """Queue a state update for batching."""
        with self._state_update_lock:
            self._pending_state_updates.append((plugin_name, action))

    def discover_plugins(self) -> List[str]:
        """Discover available plugins in configured directories with caching."""
        discovered_plugins = []
        cache_updated = False

        for directory in self.plugin_directories:
            if not directory.exists():
                continue

            # Check cache first
            dir_hash = self._get_directory_hash(directory)
            cache_key = str(directory)

            if cache_key in self._discovery_cache and self._discovery_cache[cache_key]['hash'] == dir_hash:
                # Use cached results
                cached_plugins = self._discovery_cache[cache_key]['plugins']
                discovered_plugins.extend(cached_plugins)
                self.logger.info(f"Used cached discovery for {directory}: {len(cached_plugins)} plugins")
            else:
                # Scan directory and update cache
                directory_plugins = self._scan_plugin_directory(directory)
                discovered_plugins.extend(directory_plugins)

                # Update cache
                self._discovery_cache[cache_key] = {
                    'hash': dir_hash,
                    'plugins': directory_plugins,
                    'last_scan': utcnow().isoformat()
                }
                cache_updated = True
                self.logger.info(f"Scanned and cached {directory}: {len(directory_plugins)} plugins")

        if cache_updated:
            self._save_discovery_cache()

        self.logger.info(f"Discovered {len(discovered_plugins)} plugin directories")
        return discovered_plugins

    def _scan_plugin_directory(self, directory: Path) -> List[str]:
        """Scan a directory for plugins."""
        plugins = []

        for item in directory.iterdir():
            if item.is_dir() and not item.name.startswith('.'):
                # Check if it's a plugin directory
                if self._is_plugin_directory(item):
                    plugins.append(str(item))
                # Check if it contains plugins
                elif self._contains_plugins(item):
                    for subdir in item.iterdir():
                        if subdir.is_dir() and self._is_plugin_directory(subdir):
                            plugins.append(str(subdir))

        return plugins

    def _is_plugin_directory(self, directory: Path) -> bool:
        """Check if a directory contains a valid plugin."""
        # Must have __init__.py
        if not (directory / "__init__.py").exists():
            return False

        # Must have plugin.py or plugin.json
        has_plugin_file = (directory / "plugin.py").exists() or (directory / "plugin.json").exists()

        return has_plugin_file

    def _contains_plugins(self, directory: Path) -> bool:
        """Check if a directory contains plugin subdirectories."""
        return any(
            subdir.is_dir() and self._is_plugin_directory(subdir)
            for subdir in directory.iterdir()
        )

    def load_plugins(self) -> Dict[str, BasePlugin]:
        """Load all discovered plugins."""
        discovered_plugins = self.discover_plugins()
        loaded_plugins: List[str] = []

        for plugin_path in discovered_plugins:
            try:
                plugin = self._load_plugin(plugin_path)
                if plugin:
                    plugin_id = plugin.plugin_id

                    # Skip if plugin is already loaded
                    if plugin_id in self.plugins:
                        continue

                    plugin_dir = Path(plugin_path)
                    # Attach directory metadata for deterministic template/static resolution
                    self.plugin_dirs[plugin_id] = plugin_dir
                    self.template_dirs[plugin_id] = plugin_dir / 'templates'
                    self.static_dirs[plugin_id] = plugin_dir / 'static'

                    # Sanity check: plugin folder name must match plugin_id
                    if plugin_dir.name != plugin_id:
                        self.logger.error(
                            f"Plugin folder mismatch: folder='{plugin_dir.name}' plugin_id='{plugin_id}'. "
                            f"Please rename folder to match plugin_id."
                        )

                    self.plugins[plugin_id] = plugin
                    loaded_plugins.append(plugin_id)

                    # Track plugin installation
                    self._track_plugin_installation(plugin, 'installed')

            except Exception as e:
                self.logger.error(f"Failed to load plugin from {plugin_path}: {e}")

        # Resolve which plugins are active using stored tokens (plugin_id or legacy display_name)
        self._resolve_active_plugins()

        # Extract field types from all plugins
        self._extract_field_types()

        # Save the current state after loading
        self._save_plugin_states()

        if loaded_plugins:
            self.logger.info(f"Plugin system: Loaded {len(loaded_plugins)} plugins [{', '.join(loaded_plugins)}]")

        return self.plugins

    def _resolve_active_plugins(self):
        """
        Resolve active plugins from persisted state tokens.
        Tokens may be plugin_id (new) or display_name/name (legacy).
        """
        if getattr(self, "_raw_active_tokens", None) is None:
            # No persisted state => default: all loaded plugins active
            self.active_plugins = set(self.plugins.keys())
            return

        tokens = set(str(t) for t in (self._raw_active_tokens or []) if str(t).strip())
        resolved: Set[str] = set()
        for plugin_id, plugin in self.plugins.items():
            if plugin_id in tokens:
                resolved.add(plugin_id)
                continue
            # legacy: display_name/name
            if getattr(plugin, "display_name", "") in tokens:
                resolved.add(plugin_id)
                continue
            if getattr(plugin, "name", "") in tokens:
                resolved.add(plugin_id)
                continue

        # If nothing matched but there were tokens, keep resolved empty (all inactive).
        self.active_plugins = resolved

    def _is_existing_plugin(self, plugin_name: str) -> bool:
        """Check if a plugin was previously known to the system."""
        try:
            if self.state_file_path.exists():
                with open(self.state_file_path, 'r') as f:
                    state_data = json.load(f)
                    # Check if this plugin was mentioned in any previous state
                    # We can track this by looking at installation history or previous states
                    return True  # For now, assume all plugins are existing
            return False
        except Exception as e:
            self.logger.debug("_is_existing_plugin state read failed: %s", e)
            return False

    def _load_plugin(self, plugin_path: str) -> Optional[BasePlugin]:
        """Load a single plugin from a directory."""
        plugin_dir = Path(plugin_path)

        # Try to load from plugin.py first
        plugin_file = plugin_dir / "plugin.py"
        if plugin_file.exists():
            return self._load_python_plugin(plugin_file)

        # Try to load from plugin.json
        plugin_json = plugin_dir / "plugin.json"
        if plugin_json.exists():
            return self._load_json_plugin(plugin_json)

        return None

    def _load_python_plugin(self, plugin_file: Path) -> Optional[BasePlugin]:
        """Load a plugin from a Python file with proper import isolation."""
        try:
            plugin_dir = plugin_file.parent
            plugin_name = plugin_dir.name

            # Check if we've already loaded this module
            module_key = f"{plugin_name}_{plugin_file.stat().st_mtime}"
            if module_key in self._loaded_plugin_modules:
                cached_module = self._loaded_plugin_modules[module_key]
                return self._extract_plugin_class(cached_module)

            # Create unique module name to avoid conflicts
            module_name = f"plugin_{plugin_name}_{id(self)}"

            # Load module with isolated namespace
            spec = importlib.util.spec_from_file_location(module_name, plugin_file)
            if not spec or not spec.loader:
                self.logger.error(f"Could not create module spec for {plugin_file}")
                return None

            plugin_module = importlib.util.module_from_spec(spec)

            # Add plugin directory to module's sys.path temporarily for local imports
            original_path = sys.path[:]
            try:
                sys.path.insert(0, str(plugin_dir))
                spec.loader.exec_module(plugin_module)

                # Cache the loaded module
                self._loaded_plugin_modules[module_key] = plugin_module

                return self._extract_plugin_class(plugin_module)

            finally:
                # Restore original sys.path to prevent pollution
                sys.path[:] = original_path

        except Exception as e:
            self.logger.error(f"Error loading Python plugin {plugin_file}: {e}")
            return None

    def _extract_plugin_class(self, plugin_module) -> Optional[BasePlugin]:
        """Extract plugin class from loaded module."""
        try:
            for attr_name in dir(plugin_module):
                attr = getattr(plugin_module, attr_name)
                if (isinstance(attr, type) and
                    issubclass(attr, BasePlugin) and
                    attr != BasePlugin):
                    return attr()

            self.logger.warning(f"No plugin class found in module {plugin_module}")
            return None
        except Exception as e:
            self.logger.error(f"Error extracting plugin class: {e}")
            return None

    def _load_json_plugin(self, plugin_json: Path) -> Optional[BasePlugin]:
        """Load a plugin from a JSON file."""
        try:
            with open(plugin_json, 'r') as f:
                config = json.load(f)

            # Create a dynamic plugin class from JSON config
            plugin_class = self._create_plugin_class_from_json(config)
            return plugin_class()

        except Exception as e:
            self.logger.error(f"Error loading JSON plugin {plugin_json}: {e}")
            return None

    def _create_plugin_class_from_json(self, config: Dict[str, Any]) -> type:
        """Create a plugin class dynamically from JSON configuration."""
        # This is a simplified implementation
        # In a real system, you'd want more sophisticated JSON plugin support

        class DynamicPlugin(BasePlugin):
            @property
            def plugin_id(self) -> str:
                # Canonical identity
                return config.get('plugin_id') or config.get('id') or config.get('slug') or 'unknown_plugin'

            @property
            def display_name(self) -> str:
                return config.get('display_name') or config.get('name', 'Unknown Plugin')

            @property
            def version(self) -> str:
                return config.get('version', '1.0.0')

            @property
            def description(self) -> str:
                return config.get('description', '')

            @property
            def author(self) -> str:
                return config.get('author', 'Unknown')

            def get_field_types(self) -> List[BaseFieldType]:
                # Create dynamic field types from JSON config
                field_types = []
                for field_config in config.get('field_types', []):
                    field_type = self._create_field_type_from_json(field_config)
                    if field_type:
                        field_types.append(field_type)
                return field_types

            def _create_field_type_from_json(self, field_config: Dict[str, Any]) -> Optional[BaseFieldType]:
                # Create a dynamic field type class
                # This is a simplified implementation
                return None

        return DynamicPlugin

    def _track_plugin_installation(self, plugin: BasePlugin, action: str):
        """Track plugin installation and status changes."""
        try:
            # Only track if we have an app context or can create one
            installation_info = {
                'plugin_id': plugin.plugin_id,
                'display_name': plugin.display_name,
                'version': plugin.version,
                'action': action,
                'timestamp': utcnow().isoformat(),
                'status': 'active' if action == 'installed' else action
            }

            # Try to get plugin info within a valid Flask application context
            # Some plugin methods may rely on current_app
            try:
                with self.app.app_context():
                    if hasattr(plugin, 'get_cleanup_info'):
                        installation_info['cleanup_info'] = plugin.get_cleanup_info()
                    else:
                        installation_info['cleanup_info'] = {}

                    if hasattr(plugin, 'get_resource_usage'):
                        installation_info['resource_usage'] = plugin.get_resource_usage()
                    else:
                        installation_info['resource_usage'] = {}
            except Exception as inner_e:
                self.logger.info(f"Could not get additional plugin info for {plugin.name}: {inner_e}")
                installation_info['cleanup_info'] = {}
                installation_info['resource_usage'] = {}

            self.plugin_installations[plugin.plugin_id] = installation_info

        except Exception as e:
            self.logger.warning(f"Could not track plugin installation for {getattr(plugin, 'plugin_id', 'unknown')}: {e}")

    def _extract_field_types(self):
        """Extract field types from all active plugins."""
        self.field_types.clear()
        self.field_type_to_plugin_id.clear()

        for plugin_id in self.active_plugins:
            if plugin_id in self.plugins:
                plugin = self.plugins[plugin_id]
                for field_type in plugin.get_field_types():
                    self.field_types[field_type.type_name] = field_type
                    self.field_type_to_plugin_id[field_type.type_name] = plugin_id

    def register_blueprints(self):
        """Register blueprints from all active plugins."""
        registered_blueprints = []
        skipped_blueprints = []

        for plugin_id in self.active_plugins:
            if plugin_id in self.plugins:
                plugin = self.plugins[plugin_id]
                blueprint = plugin.get_blueprint()
                if blueprint:
                    # Check if blueprint is already registered
                    blueprint_name = blueprint.name
                    if blueprint_name in self.app.blueprints:
                        skipped_blueprints.append(plugin_id)
                        continue

                    try:
                        self.app.register_blueprint(blueprint)
                        registered_blueprints.append(plugin_id)
                    except Exception as e:
                        if "has already been registered" in str(e):
                            skipped_blueprints.append(plugin_id)
                        else:
                            self.logger.error(f"Failed to register blueprint for plugin {plugin_id}: {e}")

        # Summary logging
        if registered_blueprints:
            self.logger.info(f"Plugin routes: Registered {len(registered_blueprints)} blueprints [{', '.join(registered_blueprints)}]")
        if skipped_blueprints:
            self.logger.info(f"Skipped {len(skipped_blueprints)} already registered blueprints")

    def get_plugin(self, plugin_name: str) -> Optional[BasePlugin]:
        """Get plugin instance by plugin_id."""
        return self.plugins.get(plugin_name)

    def get_active_plugins(self) -> Dict[str, BasePlugin]:
        """Get all active plugin instances."""
        active_plugin_instances = {}
        for plugin_id in self.active_plugins:
            if plugin_id in self.plugins:
                active_plugin_instances[plugin_id] = self.plugins[plugin_id]
        return active_plugin_instances

    def get_plugin_info(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific plugin."""
        if plugin_name not in self.plugins:
            return None

        plugin = self.plugins[plugin_name]

        # Get basic plugin info
        info = plugin.get_installation_info()

        # Add status information
        info['is_active'] = plugin_name in self.active_plugins
        info['status'] = self.get_plugin_status(plugin_name)

        # Add field type information
        field_types = []
        for field_type in plugin.get_field_types():
            field_types.append({
                'type': field_type.type_name,
                'display_name': field_type.display_name,
                'category': field_type.category,
                'description': field_type.description,
                'icon': field_type.icon,
                'version': field_type.version
            })
        info['field_types'] = field_types

        # Add resource usage information
        if hasattr(plugin, 'get_resource_usage'):
            info['resource_usage'] = plugin.get_resource_usage()

        # Add cleanup information
        if hasattr(plugin, 'get_cleanup_info'):
            info['cleanup_info'] = plugin.get_cleanup_info()

        # Add installation tracking
        if plugin_name in self.plugin_installations:
            info['installation_info'] = self.plugin_installations[plugin_name]

        return info

    def get_all_plugin_info(self) -> List[Dict[str, Any]]:
        """Get information about all plugins."""
        return [
            self.get_plugin_info(plugin_name)
            for plugin_name in self.plugins.keys()
        ]

    def list_field_types(self) -> List[str]:
        """Backward-compatible alias for get_field_types()."""
        return self.get_field_types()

    def install_plugin(self, plugin_name: str) -> bool:
        """Install a specific plugin."""
        if plugin_name not in self.plugins:
            self.logger.error(f"Plugin {plugin_name} not found")
            return False

        try:
            plugin = self.plugins[plugin_name]
            success = plugin.install()
            if success:
                self.logger.info(f"Plugin {plugin_name} installed successfully")
                self._track_plugin_installation(plugin, 'installed')
            else:
                self.logger.error(f"Plugin {plugin_name} installation failed")
            return success
        except Exception as e:
            self.logger.error(f"Error installing plugin {plugin_name}: {e}")
            return False

    def deactivate_plugin(self, plugin_name: str) -> bool:
        """Deactivate a specific plugin (safe, reversible)."""
        if plugin_name not in self.plugins:
            self.logger.error(f"Plugin {plugin_name} not found")
            return False

        try:
            plugin = self.plugins[plugin_name]

            # Call plugin's deactivate method if it exists
            if hasattr(plugin, 'deactivate') and callable(getattr(plugin, 'deactivate')):
                success = plugin.deactivate()
                if not success:
                    self.logger.error(f"Plugin {plugin_name} deactivation failed")
                    return False

            # Mark plugin as inactive
            self.active_plugins.discard(plugin_name)

            # Re-extract field types to exclude this plugin's field types
            self._extract_field_types()

            # Track the deactivation
            self._track_plugin_installation(plugin, 'deactivated')

            # Save the updated state
            self._save_plugin_states()

            self.logger.info(f"Plugin {plugin_name} deactivated successfully")
            return True

        except Exception as e:
            self.logger.error(f"Error deactivating plugin {plugin_name}: {e}")
            return False

    def activate_plugin(self, plugin_name: str) -> bool:
        """Activate a specific plugin."""
        if plugin_name not in self.plugins:
            self.logger.error(f"Plugin {plugin_name} not found")
            return False

        try:
            plugin = self.plugins[plugin_name]

            # Call plugin's activate method if it exists
            if hasattr(plugin, 'activate') and callable(getattr(plugin, 'activate')):
                success = plugin.activate()
                if not success:
                    self.logger.error(f"Plugin {plugin_name} activation failed")
                    return False

            # Mark plugin as active
            self.active_plugins.add(plugin_name)

            # Re-extract field types to include this plugin's field types
            self._extract_field_types()

            # Track the activation
            self._track_plugin_installation(plugin, 'activated')

            # Save the updated state
            self._save_plugin_states()

            self.logger.info(f"Plugin {plugin_name} activated successfully")
            return True

        except Exception as e:
            self.logger.error(f"Error activating plugin {plugin_name}: {e}")
            return False

    def uninstall_plugin(self, plugin_name: str) -> bool:
        """Uninstall a specific plugin (complete removal)."""
        if plugin_name not in self.plugins:
            self.logger.error(f"Plugin {plugin_name} not found")
            return False

        try:
            plugin = self.plugins[plugin_name]

            # Get cleanup information before uninstalling
            cleanup_info = {}
            if hasattr(plugin, 'get_cleanup_info'):
                cleanup_info = plugin.get_cleanup_info()

            # Call plugin's cleanup method
            if hasattr(plugin, 'cleanup') and callable(getattr(plugin, 'cleanup')):
                success = plugin.cleanup()
                if not success:
                    self.logger.error(f"Plugin {plugin_name} cleanup failed")
                    return False

            # Remove plugin files from disk
            self._remove_plugin_files(plugin_name)

            # Remove from active plugins
            self.active_plugins.discard(plugin_name)

            # Remove from plugins dictionary
            del self.plugins[plugin_name]

            # Re-extract field types
            self._extract_field_types()

            # Track the uninstallation
            self._track_plugin_installation(plugin, 'uninstalled')

            # Save the updated state
            self._save_plugin_states()

            self.logger.info(f"Plugin {plugin_name} uninstalled successfully")
            return True

        except Exception as e:
            self.logger.error(f"Error uninstalling plugin {plugin_name}: {e}")
            return False

    def _remove_plugin_files(self, plugin_name: str):
        """Remove plugin files from disk."""
        try:
            # Find the plugin directory
            plugin_dir = None
            for base_dir in self.plugin_directories:
                potential_dir = base_dir / plugin_name
                if potential_dir.exists():
                    plugin_dir = potential_dir
                    break

            if plugin_dir and plugin_dir.exists():
                # Remove the entire plugin directory
                shutil.rmtree(plugin_dir)
                self.logger.info(f"Removed plugin directory: {plugin_dir}")
            else:
                self.logger.warning(f"Could not find plugin directory for {plugin_name}")

        except Exception as e:
            self.logger.error(f"Error removing plugin files for {plugin_name}: {e}")

    def reload_plugin(self, plugin_name: str) -> bool:
        """Reload a specific plugin."""
        if plugin_name not in self.plugins:
            self.logger.error(f"Plugin {plugin_name} not found")
            return False

        try:
            # Store current activation state
            was_active = plugin_name in self.active_plugins

            # Deactivate first
            self.deactivate_plugin(plugin_name)

            # Remove from plugins dictionary
            plugin = self.plugins.pop(plugin_name)

            # Reload the plugin
            plugin_path = self._find_plugin_path(plugin_name)
            if plugin_path:
                new_plugin = self._load_plugin(plugin_path)
                if new_plugin:
                    # Ensure the reloaded plugin id is consistent
                    if new_plugin.plugin_id != plugin_name:
                        self.logger.error(
                            f"Reloaded plugin_id mismatch: expected '{plugin_name}', got '{new_plugin.plugin_id}'. "
                            "Refusing to overwrite plugin registry entry."
                        )
                        return False

                    self.plugins[plugin_name] = new_plugin

                    # Restore activation state
                    if was_active:
                        self.active_plugins.add(plugin_name)

                    self._extract_field_types()
                    self.logger.info(f"Plugin {plugin_name} reloaded successfully")
                    return True

            self.logger.error(f"Failed to reload plugin {plugin_name}")
            return False

        except Exception as e:
            self.logger.error(f"Error reloading plugin {plugin_name}: {e}")
            return False

    def _find_plugin_path(self, plugin_name: str) -> Optional[str]:
        """Find the path to a plugin directory."""
        for base_dir in self.plugin_directories:
            potential_dir = base_dir / plugin_name
            if potential_dir.exists():
                return str(potential_dir)
        return None

    def reload_plugins(self):
        """Reload all plugins (useful for development)."""
        try:
            # Store current plugin state
            current_plugins = self.plugins.copy()
            current_active = self.active_plugins.copy()

            # Clear current state
            self.plugins.clear()
            self.active_plugins.clear()
            self.field_types.clear()

            # Reload all plugins
            self.load_plugins()

            # Restore active state for existing plugins
            for plugin_name in current_active:
                if plugin_name in self.plugins:
                    self.active_plugins.add(plugin_name)

            # Re-extract field types
            self._extract_field_types()

            # Save the updated state
            self._save_plugin_states()

            self.logger.info("All plugins reloaded successfully")

        except Exception as e:
            self.logger.error(f"Error reloading plugins: {e}")

    def is_plugin_active(self, plugin_name: str) -> bool:
        """Check if a plugin is currently active."""
        return plugin_name in self.active_plugins

    def get_plugin_status(self, plugin_name: str) -> str:
        """Get the current status of a plugin."""
        if plugin_name not in self.plugins:
            return "not_installed"
        elif plugin_name in self.active_plugins:
            return "active"
        else:
            return "inactive"

    def get_field_types(self) -> List[str]:
        """Get list of all available field type names."""
        return list(self.field_types.keys())

    def list_active_field_types(self) -> List[str]:
        """Get list of field types from active plugins."""
        return list(self.field_types.keys())

    def get_field_type(self, field_type_name: str) -> Optional[BaseFieldType]:
        """Get a specific field type by name."""
        return self.field_types.get(field_type_name)

    def get_field_type_config(self, field_type_name: str) -> Optional[Dict[str, Any]]:
        """Get configuration for a specific field type."""
        field_type = self.get_field_type(field_type_name)
        if not field_type:
            return None

        return {
            'type_name': field_type.type_name,
            'display_name': field_type.display_name,
            'category': field_type.category,
            'description': field_type.description,
            'icon': field_type.icon,
            'version': field_type.version,
            'form_builder_config': field_type.get_form_builder_config(),
            'entry_form_config': field_type.get_entry_form_config(),
            'validation_rules': field_type.get_validation_rules(),
            'condition_types': field_type.get_condition_types(),
            'data_storage_config': field_type.get_data_storage_config(),
            'translation_config': field_type.get_translation_config(),
            'js_dependencies': field_type.get_js_dependencies(),
            'css_dependencies': field_type.get_css_dependencies(),
            'external_dependencies': field_type.get_external_dependencies()
        }

    def get_all_field_type_configs(self) -> List[Dict[str, Any]]:
        """Get configurations for all field types."""
        configs = []
        for field_type_name in self.field_types:
            config = self.get_field_type_config(field_type_name)
            if config:
                configs.append(config)
        return configs

    def get_plugin_cleanup_info(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """Get cleanup information for a specific plugin."""
        if plugin_name not in self.plugins:
            return None

        plugin = self.plugins[plugin_name]
        if hasattr(plugin, 'get_cleanup_info'):
            return plugin.get_cleanup_info()
        return None

    def get_plugin_resource_usage(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """Get resource usage information for a specific plugin."""
        if plugin_name not in self.plugins:
            return None

        plugin = self.plugins[plugin_name]
        if hasattr(plugin, 'get_resource_usage'):
            return plugin.get_resource_usage()
        return None

    def get_plugin_installation_history(self, plugin_name: str) -> Optional[Dict[str, Any]]:
        """Get installation history for a specific plugin."""
        return self.plugin_installations.get(plugin_name)

    def get_all_plugin_installations(self) -> Dict[str, Dict[str, Any]]:
        """Get installation history for all plugins."""
        return self.plugin_installations.copy()
