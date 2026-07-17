(function() {
  'use strict';
  var cfg = window.pluginManagementConfig || {};
  /* block 1 */
// Plugin Management JavaScript
    let pluginsData = [];
    let currentPluginForUninstall = null;
    const i18n = JSON.parse(document.getElementById('plugin-mgmt-i18n').textContent);

    function getPluginId(plugin) {
        // Canonical backend identity is plugin_id; fall back to legacy keys
        return (
            plugin?.plugin_id ||
            plugin?.pluginId ||
            plugin?.id ||
            plugin?.name ||
            plugin?.slug ||
            ''
        );
    }

    function getPluginDisplayName(plugin) {
        // UI display name; fall back to id
        return (
            plugin?.display_name ||
            plugin?.displayName ||
            plugin?.display ||
            plugin?.name ||
            getPluginId(plugin) ||
            'Unknown plugin'
        );
    }

    function findPluginById(pluginId) {
        return (Array.isArray(pluginsData) ? pluginsData : []).find(p => String(getPluginId(p)) === String(pluginId)) || null;
    }

    document.addEventListener('DOMContentLoaded', function() {
        loadPlugins();
        updateOverviewCounts();
        setupEventListeners();
    });

    function setupEventListeners() {
        // Header action buttons
        document.querySelectorAll('[data-action="reload-all"]').forEach(btn => {
            btn.addEventListener('click', reloadAllPlugins);
        });
        document.querySelectorAll('[data-action="scan-new"]').forEach(btn => {
            btn.addEventListener('click', scanForNewPlugins);
        });
        document.querySelectorAll('[data-action="download-starter"]').forEach(btn => {
            btn.addEventListener('click', downloadStarterPlugin);
        });

        // Install plugin button - trigger file picker
        const installBtn = document.getElementById('install-plugin-btn');
        const fileInput = document.getElementById('plugin-package-input');
        if (installBtn && fileInput) {
            installBtn.addEventListener('click', function() {
                fileInput.click();
            });

            // When file is selected, automatically install
            fileInput.addEventListener('change', function() {
                if (this.files.length > 0) {
                    installPlugin();
                }
            });
        }

        // Modal close buttons
        document.getElementById('close-plugin-modal-btn')?.addEventListener('click', closePluginModal);
        document.getElementById('close-plugin-modal-btn-2')?.addEventListener('click', closePluginModal);
        document.getElementById('close-cleanup-modal-btn')?.addEventListener('click', closeCleanupModal);
        document.getElementById('close-cleanup-modal-btn-2')?.addEventListener('click', closeCleanupModal);

        // Event delegation for dynamically generated plugin action buttons
        const pluginsTableBody = document.getElementById('plugins-table-body');
        if (pluginsTableBody) {
            pluginsTableBody.addEventListener('click', function(e) {
                const button = e.target.closest('button[data-action]');
                if (!button) return;

                const actionContainer = button.closest('.plugin-actions');
                if (!actionContainer) return;

                const pluginId = actionContainer.getAttribute('data-plugin-name');
                if (!pluginId) return;

                const action = button.getAttribute('data-action');

                switch(action) {
                    case 'view-details':
                        viewPluginDetails(pluginId);
                        break;
                    case 'settings':
                        openPluginSettings(pluginId);
                        break;
                    case 'activate':
                        activatePlugin(pluginId);
                        break;
                    case 'deactivate':
                        deactivatePlugin(pluginId);
                        break;
                    case 'reload':
                        reloadPlugin(pluginId);
                        break;
                    case 'uninstall':
                        showUninstallConfirmation(pluginId);
                        break;
                }
            });
        }

        // Confirm uninstall button
        const confirmUninstallBtn = document.getElementById('confirm-uninstall-btn');
        if (confirmUninstallBtn) {
            confirmUninstallBtn.addEventListener('click', function() {
                if (currentPluginForUninstall) {
                    uninstallPlugin(currentPluginForUninstall);
                }
            });
        }
    }

    async function loadPlugins() {
        try {
            const response = await ((window.getFetch && window.getFetch()) || fetch)('/admin/api/plugins/', {
                headers: {
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                }
            });

            if (response.ok) {
                const data = await response.json();
                window.__clientLog && window.__clientLog('API Response:', data); // Debug log

                if (data.success) {
                    // Handle different possible response structures
                    if (Array.isArray(data.plugins)) {
                        pluginsData = data.plugins;
                    } else if (data.plugins && typeof data.plugins === 'object') {
                        // Convert object to array format
                        pluginsData = Object.entries(data.plugins).map(([pluginId, plugin]) => ({
                            plugin_id: pluginId,
                            ...plugin
                        }));
                    } else if (Array.isArray(data.data)) {
                        pluginsData = data.data;
                    } else if (Array.isArray(data)) {
                        pluginsData = data;
                    } else {
                        window.__clientWarn && window.__clientWarn('Unexpected API response structure:', data);
                        pluginsData = [];
                    }

                    window.__clientLog && window.__clientLog('Processed plugins data:', pluginsData); // Debug log
                    renderPluginsTable();
                    updateOverviewCounts();
                } else {
                    window.__clientWarn && window.__clientWarn('API returned success: false');
                    pluginsData = [];
                    renderPluginsTable();
                    updateOverviewCounts();
                }
            } else {
                console.error('API request failed:', response.status, response.statusText);
                showError(i18n.error_failed_load_plugins_prefix + ' ' + response.status);
                pluginsData = [];
                renderPluginsTable();
                updateOverviewCounts();
            }
        } catch (error) {
            console.error('Error loading plugins:', error);
            showError(i18n.error_failed_load_plugins_prefix);
            pluginsData = [];
            renderPluginsTable();
            updateOverviewCounts();
        }
    }

    function renderPluginsTable() {
        const tbody = document.getElementById('plugins-table-body');
        tbody.innerHTML = '';

        // Ensure pluginsData is always an array
        if (!Array.isArray(pluginsData)) {
            window.__clientWarn && window.__clientWarn('pluginsData is not an array:', pluginsData);
            pluginsData = [];
        }

        if (pluginsData.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" class="px-6 py-4 text-center text-gray-500">
                        <div class="flex flex-col items-center">
                            <i class="fas fa-info-circle text-4xl text-gray-300 mb-2"></i>
                            <p>${i18n.no_plugins_found}</p>
                            <p class="text-sm">${i18n.plugins_will_appear}</p>
                        </div>
                    </td>
                </tr>
            `;
            return;
        }

        pluginsData.forEach(plugin => {
            const pluginId = getPluginId(plugin);
            const displayName = getPluginDisplayName(plugin);
            const row = document.createElement('tr');
            row.innerHTML = `
                <td class="px-6 py-4 align-top w-1/4">
                    <div class="flex items-center">
                        <div class="flex-shrink-0 h-10 w-10">
                            <div class="h-10 w-10 rounded-full bg-blue-100 flex items-center justify-center">
                                <i class="fas fa-puzzle-piece text-blue-600 text-xl leading-none"></i>
                            </div>
                        </div>
                        <div class="ml-4 min-w-0 whitespace-normal break-words">
                            <div class="text-sm font-medium text-gray-900">${escapeHtml(displayName)}</div>
                            <div class="text-xs text-gray-500">${escapeHtml(pluginId)}</div>
                            <div class="text-sm text-gray-500">${escapeHtml(plugin.description || '')}</div>
                        </div>
                    </div>
                </td>
                <td class="px-6 py-4 whitespace-nowrap">
                    ${plugin.is_active ?
                        (window.StatusLabels
                            ? window.StatusLabels.render(i18n.status_active, 'success')
                            : `<span class="status-label status-label--success">${escapeHtml(i18n.status_active)}</span>`) :
                        (window.StatusLabels
                            ? window.StatusLabels.render(i18n.status_inactive, 'neutral')
                            : `<span class="status-label status-label--neutral">${escapeHtml(i18n.status_inactive)}</span>`)
                    }
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    ${escapeHtml(plugin.version || '')}
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">
                    ${plugin.field_types ? plugin.field_types.length : 0}
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    ${escapeHtml(plugin.author || '')}
                </td>
                <td class="px-6 py-4 whitespace-nowrap text-sm font-medium">
                    <div class="flex space-x-2 plugin-actions" data-plugin-name="${escapeHtmlAttr(pluginId)}">
                        <button data-action="view-details"
                                class="text-blue-600 hover:text-blue-900 inline-flex items-center justify-center" title="${i18n.title_view_details}">
                            <i class="fas fa-eye text-base align-middle leading-none"></i>
                        </button>
                        <button data-action="settings"
                                class="text-green-600 hover:text-green-900 inline-flex items-center justify-center" title="${i18n.title_settings}">
                            <i class="fas fa-cog text-base align-middle leading-none"></i>
                        </button>
                        ${plugin.is_active ?
                            `<button data-action="deactivate"
                                     class="text-orange-600 hover:text-orange-900 inline-flex items-center justify-center" title="${i18n.title_deactivate}">
                                <i class="fas fa-pause text-base align-middle leading-none"></i>
                            </button>` :
                            `<button data-action="activate"
                                     class="text-green-600 hover:text-green-900 inline-flex items-center justify-center" title="${i18n.title_activate}">
                                <i class="fas fa-play text-base align-middle leading-none"></i>
                            </button>`
                        }
                        <button data-action="reload"
                                class="text-yellow-600 hover:text-yellow-900 inline-flex items-center justify-center" title="${i18n.title_reload}">
                            <i class="fas fa-sync-alt text-base align-middle leading-none"></i>
                        </button>
                        <button data-action="uninstall"
                                class="text-red-600 hover:text-red-900 inline-flex items-center justify-center" title="${i18n.title_uninstall}">
                            <i class="fas fa-trash text-base align-middle leading-none"></i>
                        </button>
                    </div>
                </td>
            `;
            tbody.appendChild(row);
        });
    }

    function updateOverviewCounts() {
        // Ensure pluginsData is always an array
        if (!Array.isArray(pluginsData)) {
            pluginsData = [];
        }

        document.getElementById('total-plugins-count').textContent = pluginsData.length;
        document.getElementById('active-plugins-count').textContent = pluginsData.filter(p => p.is_active).length;

        const totalFieldTypes = pluginsData.reduce((sum, plugin) => {
            return sum + (plugin.field_types ? plugin.field_types.length : 0);
        }, 0);
        document.getElementById('field-types-count').textContent = totalFieldTypes;

        // This would need to be calculated from actual form usage
        document.getElementById('custom-fields-count').textContent = '--';
    }

    async function _reloadAllPlugins() {
        try {
            showLoading(true);
            const response = await ((window.getFetch && window.getFetch()) || fetch)('/admin/api/plugins/reload', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                }
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    showSuccess(i18n.success_all_reloaded);
                    await loadPlugins();
                }
            }
        } catch (error) {
            console.error('Error reloading plugins:', error);
            showError(i18n.error_failed_reload_plugins);
        } finally {
            showLoading(false);
        }
    }

    function reloadAllPlugins() {
        if (window.showConfirmation) {
            window.showConfirmation(i18n.confirm_reload_all, () => { void _reloadAllPlugins(); }, null, 'Reload', 'Cancel', 'Reload All Plugins?');
        } else {
            void _reloadAllPlugins();
        }
    }

    async function scanForNewPlugins() {
        try {
            showLoading(true);
            // This would trigger a scan of plugin directories
            showSuccess(i18n.success_scan_completed);
            await loadPlugins();
        } catch (error) {
            console.error('Error scanning for plugins:', error);
            showError(i18n.error_failed_scan_plugins);
        } finally {
            showLoading(false);
        }
    }

    async function downloadStarterPlugin() {
        try {
            showLoading(true);
            // Directly navigate to the download endpoint to prompt browser download
            window.location.href = '/admin/api/plugins/sample-package/download';
        } catch (error) {
            console.error('Error starting download:', error);
            showError(i18n.error_failed_start_download);
        } finally {
            // Keep spinner minimal to avoid blocking the download UX
            showLoading(false);
        }
    }

    async function installPlugin() {
        const fileInput = document.getElementById('plugin-package-input');
        const file = fileInput.files[0];

        if (!file) {
            showError(i18n.error_select_package);
            return;
        }

        try {
            showLoading(true);
            const formData = new FormData();
            formData.append('plugin_package', file);

            const response = await ((window.getFetch && window.getFetch()) || fetch)('/admin/api/plugins/install', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                },
                body: formData
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    showSuccess(i18n.success_installed);
                    fileInput.value = '';
                    await loadPlugins();
                }
            }
        } catch (error) {
            console.error('Error installing plugin:', error);
            showError(i18n.error_failed_install);
        } finally {
            showLoading(false);
        }
    }

    function viewPluginDetails(pluginId) {
        const plugin = findPluginById(pluginId);
        if (!plugin) return;

        var pluginTitleEl = document.getElementById('plugin-details-modal-title');
        if (pluginTitleEl) pluginTitleEl.textContent = getPluginDisplayName(plugin);

        let content = `
            <div class="space-y-4">
                <div>
                    <h4 class="font-medium text-gray-700">${i18n.details_description}</h4>
                    <p class="text-gray-600">${escapeHtml(plugin.description || '')}</p>
                </div>
                <div>
                    <h4 class="font-medium text-gray-700">${i18n.details_version}</h4>
                    <p class="text-gray-600">${escapeHtml(plugin.version || '')}</p>
                </div>
                <div>
                    <h4 class="font-medium text-gray-700">${i18n.details_author}</h4>
                    <p class="text-gray-600">${escapeHtml(plugin.author || '')}</p>
                </div>
                <div>
                    <h4 class="font-medium text-gray-700">${i18n.details_license}</h4>
                    <p class="text-gray-600">${escapeHtml(plugin.license || i18n.details_not_specified)}</p>
                </div>
                <div>
                    <h4 class="font-medium text-gray-700">${i18n.details_field_types}</h4>
                    <div class="space-y-2">
                        ${plugin.field_types ? plugin.field_types.map(ft => `
                            <div class="bg-gray-50 p-2 rounded">
                                <span class="font-medium">${escapeHtml(ft.display_name)}</span>
                                <span class="text-sm text-gray-500 ml-2">(${escapeHtml(ft.type)})</span>
                            </div>
                        `).join('') : `<p class="text-gray-500">${i18n.details_no_field_types}</p>`}
                    </div>
                </div>
        `;

        // Add resource usage if available
        if (plugin.resource_usage) {
            content += `
                <div>
                    <h4 class="font-medium text-gray-700">${i18n.usage_resource_usage}</h4>
                    <div class="bg-gray-50 p-3 rounded space-y-1">
                        <p class="text-sm"><span class="font-medium">${i18n.usage_disk_space}</span> ${escapeHtml(plugin.resource_usage.disk_space)}</p>
                        <p class="text-sm"><span class="font-medium">${i18n.usage_database_tables}</span> ${escapeHtml(plugin.resource_usage.database_tables)}</p>
                        <p class="text-sm"><span class="font-medium">${i18n.usage_uploaded_files}</span> ${escapeHtml(plugin.resource_usage.uploaded_files)}</p>
                        <p class="text-sm"><span class="font-medium">${i18n.usage_configuration_keys}</span> ${escapeHtml(plugin.resource_usage.configuration_keys)}</p>
                    </div>
                </div>
            `;
        }

        content += '</div>';
        document.getElementById('modal-plugin-content').innerHTML = content;

        document.getElementById('plugin-details-modal').classList.remove('hidden');
    }

    function openPluginSettings(pluginId) {
        // pluginId is canonical and already URL-safe (snake_case)
        window.location.href = `/admin/plugins/${encodeURIComponent(pluginId)}/settings`;
    }

    async function _reloadPlugin(pluginId) {
        const plugin = findPluginById(pluginId);
        const displayName = plugin ? getPluginDisplayName(plugin) : pluginId;
        try {
            showLoading(true);
            const response = await ((window.getFetch && window.getFetch()) || fetch)(`/admin/api/plugins/${encodeURIComponent(pluginId)}/reload`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                }
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    showSuccess(i18n.success_plugin_reloaded.replace('%(plugin)s', displayName));
                    await loadPlugins();
                } else {
                    showError(data.message || i18n.error_failed_reload_plugins);
                }
            } else {
                showError(i18n.error_failed_reload_plugins);
            }
        } catch (error) {
            console.error('Error reloading plugin:', error);
            showError(i18n.error_failed_reload_plugins);
        } finally {
            showLoading(false);
        }
    }

    function reloadPlugin(pluginId) {
        const plugin = findPluginById(pluginId);
        const displayName = plugin ? getPluginDisplayName(plugin) : pluginId;
        const msg = i18n.confirm_reload_plugin.replace('%(plugin)s', displayName);
        if (window.showConfirmation) {
            window.showConfirmation(msg, () => { void _reloadPlugin(pluginId); }, null, 'Reload', 'Cancel', 'Reload Plugin?');
        } else {
            void _reloadPlugin(pluginId);
        }
    }

    async function _activatePlugin(pluginId) {
        const plugin = findPluginById(pluginId);
        const displayName = plugin ? getPluginDisplayName(plugin) : pluginId;
        try {
            showLoading(true);
            const response = await ((window.getFetch && window.getFetch()) || fetch)(`/admin/api/plugins/${encodeURIComponent(pluginId)}/activate`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                }
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    showSuccess(i18n.success_plugin_activated.replace('%(plugin)s', displayName));
                    await loadPlugins();
                } else {
                    showError(data.message || i18n.error_failed_install);
                }
            } else {
                showError(i18n.error_failed_install);
            }
        } catch (error) {
            console.error('Error activating plugin:', error);
            showError(i18n.error_failed_install);
        } finally {
            showLoading(false);
        }
    }

    function activatePlugin(pluginId) {
        const plugin = findPluginById(pluginId);
        const displayName = plugin ? getPluginDisplayName(plugin) : pluginId;
        const msg = i18n.confirm_activate_plugin.replace('%(plugin)s', displayName);
        if (window.showConfirmation) {
            window.showConfirmation(msg, () => { void _activatePlugin(pluginId); }, null, 'Activate', 'Cancel', 'Activate Plugin?');
        } else {
            void _activatePlugin(pluginId);
        }
    }

    async function _deactivatePlugin(pluginId) {
        const plugin = findPluginById(pluginId);
        const displayName = plugin ? getPluginDisplayName(plugin) : pluginId;
        try {
            showLoading(true);
            const response = await ((window.getFetch && window.getFetch()) || fetch)(`/admin/api/plugins/${encodeURIComponent(pluginId)}/deactivate`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                }
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    showSuccess(i18n.success_plugin_deactivated.replace('%(plugin)s', displayName));
                    await loadPlugins();
                } else {
                    showError(data.message || i18n.error_failed_install);
                }
            } else {
                showError(i18n.error_failed_install);
            }
        } catch (error) {
            console.error('Error deactivating plugin:', error);
            showError(i18n.error_failed_install);
        } finally {
            showLoading(false);
        }
    }

    async function showUninstallConfirmation(pluginId) {
        const plugin = findPluginById(pluginId);
        const displayName = plugin ? getPluginDisplayName(plugin) : pluginId;
        try {
            // Get cleanup information for the plugin
            const response = await ((window.getFetch && window.getFetch()) || fetch)(`/admin/api/plugins/${encodeURIComponent(pluginId)}/cleanup-info`, {
                headers: {
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                }
            });

            if (response.ok) {
                const data = await response.json();
                if (data.success) {
                    currentPluginForUninstall = pluginId;
                    displayUninstallConfirmation(displayName, data.cleanup_info);
                } else {
                    const msg = i18n.confirm_uninstall_plugin.replace('%(plugin)s', displayName);
                    if (window.showDangerConfirmation) {
                        window.showDangerConfirmation(msg, () => { void uninstallPlugin(pluginId); }, null, 'Uninstall', 'Cancel', 'Uninstall Plugin?');
                    } else {
                        void uninstallPlugin(pluginId);
                    }
                }
            } else {
                const msg = i18n.confirm_uninstall_plugin.replace('%(plugin)s', displayName);
                if (window.showDangerConfirmation) {
                    window.showDangerConfirmation(msg, () => { void uninstallPlugin(pluginId); }, null, 'Uninstall', 'Cancel', 'Uninstall Plugin?');
                } else {
                    void uninstallPlugin(pluginId);
                }
            }
        } catch (error) {
            console.error('Error getting cleanup info:', error);
            const msg = i18n.confirm_uninstall_plugin.replace('%(plugin)s', displayName);
            if (window.showDangerConfirmation) {
                window.showDangerConfirmation(msg, () => { void uninstallPlugin(pluginId); }, null, 'Uninstall', 'Cancel', 'Uninstall Plugin?');
            } else {
                void uninstallPlugin(pluginId);
            }
        }
    }

    function displayUninstallConfirmation(pluginName, cleanupInfo) {
        document.getElementById('cleanup-modal-title').textContent = i18n.uninstall_heading.replace('%(plugin)s', pluginName);

        let content = `
            <div class="space-y-4">
                <div class="bg-red-50 border border-red-200 rounded-md p-4">
                    <div class="flex">
                        <div class="flex-shrink-0">
                            <i class="fas fa-exclamation-triangle text-red-400 text-base align-middle"></i>
                        </div>
                        <div class="ml-3">
                            <h3 class="text-sm font-medium text-red-800">${i18n.uninstall_warning_title}</h3>
                            <div class="mt-2 text-sm text-red-700">
                                <p>${i18n.uninstall_will_remove}</p>
                            </div>
                        </div>
                    </div>
                </div>

                <div>
                    <h4 class="font-medium text-gray-700 mb-2">${i18n.uninstall_what_removed}</h4>
                    <div class="space-y-3">
        `;

        if (cleanupInfo.database_tables && cleanupInfo.database_tables.length > 0) {
            content += `
                <div class="bg-gray-50 p-3 rounded">
                    <h5 class="font-medium text-gray-700 mb-1">${i18n.usage_database_tables}</h5>
                    <ul class="text-sm text-gray-600 space-y-1">
                        ${cleanupInfo.database_tables.map(table => `<li>• ${escapeHtml(table)}</li>`).join('')}
                    </ul>
                </div>
            `;
        }

        if (cleanupInfo.uploaded_files && cleanupInfo.uploaded_files.length > 0) {
            content += `
                <div class="bg-gray-50 p-3 rounded">
                    <h5 class="font-medium text-gray-700 mb-1">${i18n.usage_uploaded_files}</h5>
                    <ul class="text-sm text-gray-600 space-y-1">
                        ${cleanupInfo.uploaded_files.map(file => `<li>• ${escapeHtml(file)}</li>`).join('')}
                    </ul>
                </div>
            `;
        }

        if (cleanupInfo.configuration_keys && cleanupInfo.configuration_keys.length > 0) {
            content += `
                <div class="bg-gray-50 p-3 rounded">
                    <h5 class="font-medium text-gray-700 mb-1">${i18n.usage_configuration_keys}</h5>
                    <ul class="text-sm text-gray-600 space-y-1">
                        ${cleanupInfo.configuration_keys.map(key => `<li>• ${escapeHtml(key)}</li>`).join('')}
                    </ul>
                </div>
            `;
        }

        if (cleanupInfo.estimated_space_freed) {
            content += `
                <div class="bg-blue-50 p-3 rounded">
                    <h5 class="font-medium text-blue-700 mb-1">${i18n.usage_space_freed}</h5>
                    <p class="text-sm text-blue-600">${escapeHtml(cleanupInfo.estimated_space_freed)}</p>
                </div>
            `;
        }

        if (cleanupInfo.warnings && cleanupInfo.warnings.length > 0) {
            content += `
                <div class="bg-yellow-50 p-3 rounded">
                    <h5 class="font-medium text-yellow-700 mb-1">${i18n.warnings_additional}</h5>
                    <ul class="text-sm text-yellow-600 space-y-1">
                        ${cleanupInfo.warnings.map(warning => `<li>• ${escapeHtml(warning)}</li>`).join('')}
                    </ul>
                </div>
            `;
        }

        if (cleanupInfo.backup_recommendation) {
            content += `
                <div class="bg-green-50 p-3 rounded">
                    <div class="flex">
                        <div class="flex-shrink-0">
                            <i class="fas fa-info-circle text-green-400 text-base align-middle"></i>
                        </div>
                        <div class="ml-3">
                            <p class="text-sm text-green-700">
                                <strong>${i18n.recommendation_label}</strong> ${i18n.recommendation_text}
                            </p>
                        </div>
                    </div>
                </div>
            `;
        }

        content += `
                    </div>
                </div>
            </div>
        `;

        document.getElementById('cleanup-modal-content').innerHTML = content;

        // Show the modal
        document.getElementById('plugin-cleanup-modal').classList.remove('hidden');
    }

    async function uninstallPlugin(pluginName) {
        // Use the passed pluginName parameter, fallback to currentPluginForUninstall if needed
        const pluginToUninstall = pluginName || currentPluginForUninstall;

        if (!pluginToUninstall) {
            showError(i18n.error_no_plugin_for_uninstall);
            return;
        }

        try {
            showLoading(true);
            closeCleanupModal();

            const response = await ((window.getFetch && window.getFetch()) || fetch)(`/admin/api/plugins/${encodeURIComponent(pluginToUninstall)}/uninstall`, {
                method: 'POST',
                headers: {
                    'X-CSRFToken': document.querySelector('meta[name="csrf-token"]').getAttribute('content')
                }
            });

            if (!response.ok) {
                const err = window.parseHttpError ? await window.parseHttpError(response) : new Error('HTTP ' + response.status);
                showError(err.message || i18n.error_failed_uninstall);
            } else {
                const data = await response.json();
                if (data.success) {
                    showSuccess(i18n.success_plugin_uninstalled.replace('%(plugin)s', pluginToUninstall));
                    await loadPlugins();
                } else {
                    showError(data.error || i18n.error_failed_uninstall);
                }
            }
        } catch (error) {
            console.error('Error uninstalling plugin:', error);
            showError(i18n.error_failed_uninstall);
        } finally {
            showLoading(false);
            currentPluginForUninstall = null;
        }
    }

    function closePluginModal() {
        document.getElementById('plugin-details-modal').classList.add('hidden');
    }

    function closeCleanupModal() {
        document.getElementById('plugin-cleanup-modal').classList.add('hidden');
        currentPluginForUninstall = null;
    }

    function showLoading(show) {
        document.getElementById('loading-spinner').classList.toggle('hidden', !show);
    }

    function showSuccess(message) {
        const text = i18n.success_prefix + message;
        if (window.showAlert) {
            window.showAlert(text, 'success');
        } else {
            window.__clientLog && window.__clientLog('Success:', text);
        }
    }

    function showError(message) {
        const text = i18n.error_prefix + message;
        if (window.showAlert) {
            window.showAlert(text, 'error');
        } else {
            console.error('Error:', text);
        }
    }

})();
