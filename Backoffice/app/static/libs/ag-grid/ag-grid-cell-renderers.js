/**
 * AG Grid Common Cell Renderers
 * Centralized cell renderers used across all AG Grid templates
 *
 * Usage:
 *   In column definitions:
 *   { field: 'status', cellRenderer: AgGridRenderers.statusBadge }
 *   { field: 'active', cellRenderer: AgGridRenderers.booleanIcon }
 *   { field: 'owner', cellRenderer: AgGridRenderers.profileIcon }
 */

(function() {
    'use strict';

    /**
     * Get translation from window.agGridTranslations or i18n-json
     * @param {string} key - Translation key
     * @param {string} defaultValue - Default English value
     * @returns {string} Translated string
     */
    function getTranslation(key, defaultValue) {
        if (typeof AgGridUtils !== 'undefined' && typeof AgGridUtils.getTranslation === 'function') {
            return AgGridUtils.getTranslation(key, defaultValue);
        }
        return defaultValue;
    }

    function escapeHtml(text) {
        if (typeof AgGridUtils !== 'undefined' && typeof AgGridUtils.escapeHtml === 'function') {
            return AgGridUtils.escapeHtml(text);
        }
        if (text === null || text === undefined) return '';
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    /**
     * Escape value for HTML attributes
     * @param {*} value - Value to escape
     * @returns {string} Escaped attribute value
     */
    function escapeHtmlAttr(value) {
        return escapeHtml(value);
    }

    function renderStatusLabel(text, variant) {
        if (window.StatusLabels) {
            return window.StatusLabels.render(text, variant || 'neutral');
        }
        return '<span class="status-label status-label--' + (variant || 'neutral') + '">' + escapeHtml(text) + '</span>';
    }

    /**
     * Common Cell Renderers
     */
    var AgGridRenderers = {
        /**
         * Active/Inactive status badge
         * Expects params.value to be boolean
         */
        statusBadge: function(params) {
            var isActive = params.value;
            var activeText = getTranslation('active', 'Active');
            var inactiveText = getTranslation('inactive', 'Inactive');
            return renderStatusLabel(isActive ? activeText : inactiveText, isActive ? 'success' : 'neutral');
        },

        /**
         * Approval status badge (Approved/Rejected/Pending)
         * Expects params.value to be 'approved', 'rejected', or other (pending)
         */
        approvalStatus: function(params) {
            var status = (params.value || '').toLowerCase();
            var approvedText = getTranslation('approved', 'Approved');
            var rejectedText = getTranslation('rejected', 'Rejected');
            var pendingText = getTranslation('pending', 'Pending');
            var pendingReviewText = getTranslation('pendingReview', 'Pending Review');

            switch(status) {
                case 'approved':
                    return renderStatusLabel(approvedText, 'success');
                case 'rejected':
                    return renderStatusLabel(rejectedText, 'danger');
                default:
                    return renderStatusLabel(pendingReviewText || pendingText, 'pending');
            }
        },

        /**
         * Deployed/Draft status badge
         * Expects params.data.is_deployed to be boolean
         */
        deployedStatus: function(params) {
            var isDeployed = params.data && params.data.is_deployed;
            var deployedText = getTranslation('deployed', 'Deployed');
            var draftText = getTranslation('draft', 'Draft');
            var displayText = params.value || (isDeployed ? deployedText : draftText);
            return renderStatusLabel(displayText, isDeployed ? 'success' : 'neutral');
        },

        /**
         * Boolean check/cross icon
         * Expects params.value to be boolean
         */
        booleanIcon: function(params) {
            if (params.value) {
                return '<i class="fas fa-check-circle text-green-500" title="' + getTranslation('yes', 'Yes') + '"></i>';
            }
            return '<i class="fas fa-times-circle text-red-500" title="' + getTranslation('no', 'No') + '"></i>';
        },

        /**
         * Boolean with allowed/not allowed titles
         * Expects params.value to be boolean
         */
        booleanAllowed: function(params) {
            var allowedText = getTranslation('allowed', 'Allowed');
            var notAllowedText = getTranslation('notAllowed', 'Not Allowed');

            if (params.value) {
                return '<i class="fas fa-check-circle text-green-500" title="' + allowedText + '"></i>';
            }
            return '<i class="fas fa-times-circle text-red-500" title="' + notAllowedText + '"></i>';
        },

        /**
         * Date/Time formatter - converts UTC to user's local timezone
         * Expects params.value to be a UTC date string or Date object
         * Requires DateTimeUtils to be loaded (via ag_grid_includes.html)
         */
        dateTime: function(params) {
            if (!params.value) return '<span class="text-gray-400">-</span>';
            return DateTimeUtils.agGridRenderer(params, 'datetime');
        },

        /**
         * Date/Time formatter with dual lines (date on top, time below)
         * Expects params.value to be a UTC date string or Date object
         */
        dateTimeDual: function(params) {
            if (!params.value) return '<span class="text-gray-400">-</span>';
            return DateTimeUtils.agGridDualLineRenderer(params);
        },

        /**
         * Date only formatter (no time) - converts UTC to user's local timezone
         * Expects params.value to be a UTC date string or Date object
         */
        dateOnly: function(params) {
            if (!params.value) return '<span class="text-gray-400">-</span>';
            return DateTimeUtils.agGridRenderer(params, 'date');
        },

        /**
         * Time only formatter - converts UTC to user's local timezone
         * Expects params.value to be a UTC date string or Date object
         */
        timeOnly: function(params) {
            if (!params.value) return '<span class="text-gray-400">-</span>';
            return DateTimeUtils.agGridRenderer(params, 'time');
        },

        /**
         * Relative time formatter (e.g., "2 hours ago")
         * Expects params.value to be a UTC date string or Date object
         */
        relativeTime: function(params) {
            if (!params.value) return '<span class="text-gray-400">-</span>';
            return DateTimeUtils.agGridRenderer(params, 'relative');
        },

        /**
         * Privacy badge (Public/Private)
         * Expects params.value to be boolean (true = public)
         */
        privacyBadge: function(params) {
            var publicText = getTranslation('public', 'Public');
            var privateText = getTranslation('private', 'Private');
            return renderStatusLabel(params.value ? publicText : privateText, params.value ? 'success' : 'neutral');
        },

        /**
         * Archived/Active status badge
         * Expects params.value to be boolean (true = archived)
         */
        archivedStatus: function(params) {
            var archivedText = getTranslation('archived', 'Archived');
            var activeText = getTranslation('active', 'Active');
            return renderStatusLabel(
                params.value ? archivedText : activeText,
                params.value ? 'warning' : 'success'
            );
        },

        /** Filter labels for archived column (matches archivedStatus display). */
        archivedFilterValue: function(params) {
            var archivedText = getTranslation('archived', 'Archived');
            var activeText = getTranslation('active', 'Active');
            if (!params.data) {
                return '';
            }
            return params.data.archived ? archivedText : activeText;
        },

        /** Filter labels for emergency column (matches emergencyBadge display). */
        emergencyFilterValue: function(params) {
            var emergencyText = getTranslation('emergency', 'Emergency');
            var notEmergencyText = getTranslation('not_emergency', 'Not emergency');
            if (!params.data) {
                return '';
            }
            return params.data.emergency ? emergencyText : notEmergencyText;
        },

        /**
         * Emergency indicator
         * Expects params.value to be boolean
         */
        emergencyBadge: function(params) {
            var emergencyText = getTranslation('emergency', 'Emergency');
            var notEmergencyText = getTranslation('not_emergency', 'Not emergency');
            return renderStatusLabel(
                params.value ? emergencyText : notEmergencyText,
                params.value ? 'danger' : 'neutral'
            );
        },

        /**
         * Usage count badge
         * Expects params.value to be a number
         */
        usageCount: function(params) {
            var count = params.value || 0;
            var bgClass = count > 0 ? 'bg-blue-100 text-blue-800' : 'bg-gray-100 text-gray-800';
            return '<span class="inline-flex items-center gap-x-1.5 py-1 px-2.5 rounded-full text-xs font-medium ' + bgClass + '">' +
                '<i class="fas fa-chart-line"></i>' + count + '</span>';
        },

        /**
         * Profile icon with initials
         * Expects params.value or params.data.user/owner to contain user object with:
         *   - name: string
         *   - email: string
         *   - profile_color: string (hex color)
         */
        profileIcon: function(params) {
            var user = params.value;
            if (!user && params.data) {
                user = params.data.user || params.data.owner;
            }
            if (!user) return '-';

            var name = user.name || '';
            var email = user.email || '';
            var displayName = name || email;

            if (!displayName) return '-';

            var initials = profileDisplayInitials(name, email);

            var profileColor = user.profile_color || '#3B82F6';
            var html = '<div class="flex items-center profile-icon">';
            html += '<div class="w-8 h-8 rounded-full text-white text-xs font-semibold flex items-center justify-center mr-2 flex-shrink-0 profile-icon-circle" style="background-color: ' +
                escapeHtmlAttr(profileColor) + ';">' + escapeHtml(initials) + '</div>';

            html += '<div class="flex flex-col min-w-0">';
            html += '<span class="text-sm font-medium text-gray-900 truncate">' + escapeHtml(displayName) + '</span>';
            html += '</div></div>';

            return html;
        },

        /**
         * Profile icon with wrapping text (for narrow columns)
         */
        profileIconWrap: function(params) {
            var user = params.value;
            if (!user && params.data) {
                user = params.data.user || params.data.owner;
            }
            if (!user) return '-';

            var name = user.name || '';
            var email = user.email || '';
            var displayName = name || email;

            if (!displayName) return '-';

            var initials = profileDisplayInitials(name, email);

            var profileColor = user.profile_color || '#3B82F6';
            var html = '<div class="flex items-start profile-icon" style="min-width: 0; width: 100%;">';
            html += '<div class="w-8 h-8 rounded-full text-white text-xs font-semibold flex items-center justify-center mr-2 flex-shrink-0 profile-icon-circle" style="background-color: ' +
                escapeHtmlAttr(profileColor) + ';">' + escapeHtml(initials) + '</div>';

            html += '<div class="flex flex-col min-w-0 flex-1" style="overflow-wrap: break-word; word-wrap: break-word; word-break: break-word;">';
            html += '<span class="text-sm font-medium text-gray-900 break-words">' + escapeHtml(displayName) + '</span>';
            html += '</div></div>';

            return html;
        },

        /**
         * User cell with hover profile popup support
         * Usage:
         *   AgGridRenderers.userHoverCell(params, {
         *     sourceField: 'owner', // optional object field
         *     idField: 'owner_id',  // optional scalar field
         *     nameField: 'owner_name',
         *     emailField: 'owner_email'
         *   })
         */
        userHoverCell: function(params, options) {
            options = options || {};
            var data = params && params.data ? params.data : {};

            var user = null;
            if (options.sourceField && data && data[options.sourceField]) {
                user = data[options.sourceField];
            } else if (params && params.value && typeof params.value === 'object') {
                user = params.value;
            } else if (params && params.value && !options.nameField && !options.emailField) {
                user = { name: params.value };
            }

            if (!user) {
                user = {};
            }

            var userId = options.idField ? data[options.idField] : user.id;
            var userName = options.nameField ? data[options.nameField] : user.name;
            var userEmail = options.emailField ? data[options.emailField] : user.email;
            var userTitle = options.titleField ? data[options.titleField] : user.title;
            var userActive = options.activeField ? data[options.activeField] : user.active;
            var profileColor = options.profileColorField ? data[options.profileColorField] : user.profile_color;
            var roleList = options.rolesField ? data[options.rolesField] : user.rbac_roles;
            var roleBadgeKey = options.roleBadgeKeyField ? data[options.roleBadgeKeyField] : user.role_badge_key;
            var externalId = options.externalIdField ? data[options.externalIdField] : user.external_id;
            var countriesCount = options.countriesCountField ? data[options.countriesCountField] : user.countries_count;
            var entitySummary = options.entitySummaryField ? data[options.entitySummaryField] : user.entity_summary;
            var scopeDisplayLines = user.scope_display_lines;
            var lastPresence = options.lastPresenceField ? data[options.lastPresenceField] : user.last_presence;
            var fallbackLabel = options.fallbackLabel || getTranslation('unknownUser', 'Unknown User');
            var showEmail = options.showEmail !== false;

            var displayName = userName || userEmail || '';
            if (!displayName) {
                return '<span class="text-sm text-gray-500">' + escapeHtml(fallbackLabel) + '</span>';
            }

            var inlineProfile = {
                id: userId,
                name: userName || '',
                email: userEmail || '',
                title: userTitle || '',
                active: userActive,
                profile_color: profileColor || '#3B82F6',
                role_badge_key: roleBadgeKey || '',
                external_id: externalId ? String(externalId) : '',
                rbac_roles: Array.isArray(roleList) ? roleList : [],
                countries_count: countriesCount,
                entity_summary: entitySummary || '',
                last_presence: lastPresence || null
            };
            if (Array.isArray(scopeDisplayLines) && scopeDisplayLines.length) {
                inlineProfile.scope_display_lines = scopeDisplayLines;
            }

            var encodedProfile = '';
            try {
                encodedProfile = encodeURIComponent(JSON.stringify(inlineProfile));
            } catch (e) {
                encodedProfile = '';
            }

            var html = '<div class="ag-user-hover-cell" style="display:flex;width:100%;max-width:100%;min-width:0;overflow:hidden;box-sizing:border-box;">';
            html += '<span class="ag-user-hover-trigger" style="display:flex;flex:1 1 0%;flex-direction:column;min-width:0;max-width:100%;overflow:hidden;"';
            if (userId !== null && userId !== undefined && userId !== '') {
                html += ' data-user-id="' + escapeHtmlAttr(userId) + '"';
            }
            if (externalId) {
                html += ' data-user-external-id="' + escapeHtmlAttr(String(externalId)) + '"';
            }
            if (userEmail) {
                html += ' data-user-email="' + escapeHtmlAttr(userEmail) + '"';
            }
            if (encodedProfile) {
                html += ' data-user-inline="' + escapeHtmlAttr(encodedProfile) + '"';
            }
            html += '>';
            html += '<span class="ag-user-hover-name" style="display:block;font-size:0.875rem;font-weight:500;color:#111827;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0;">' + escapeHtml(displayName) + '</span>';
            if (showEmail && userName && userEmail) {
                html += '<span class="ag-user-hover-subline" style="display:block;font-size:0.75rem;color:#6b7280;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0;">' + escapeHtml(userEmail) + '</span>';
            }
            html += '</span>';
            html += '</div>';
            return html;
        },

        /**
         * Same data/hover behavior as userHoverCell, but first row is [device icon][name]
         * and email is on the second row with small gap and padding-left aligned under the name.
         * @param {string} deviceIconHtml - Trusted HTML for leading <i class="..."> (include title if needed)
         */
        userHoverCellWithDeviceIcon: function(params, options, deviceIconHtml) {
            options = options || {};
            deviceIconHtml = deviceIconHtml || '';
            var data = params && params.data ? params.data : {};

            var user = null;
            if (options.sourceField && data && data[options.sourceField]) {
                user = data[options.sourceField];
            } else if (params && params.value && typeof params.value === 'object') {
                user = params.value;
            } else if (params && params.value && !options.nameField && !options.emailField) {
                user = { name: params.value };
            }

            if (!user) {
                user = {};
            }

            var userId = options.idField ? data[options.idField] : user.id;
            var userName = options.nameField ? data[options.nameField] : user.name;
            var userEmail = options.emailField ? data[options.emailField] : user.email;
            var userTitle = options.titleField ? data[options.titleField] : user.title;
            var userActive = options.activeField ? data[options.activeField] : user.active;
            var profileColor = options.profileColorField ? data[options.profileColorField] : user.profile_color;
            var roleList = options.rolesField ? data[options.rolesField] : user.rbac_roles;
            var roleBadgeKey = options.roleBadgeKeyField ? data[options.roleBadgeKeyField] : user.role_badge_key;
            var externalId = options.externalIdField ? data[options.externalIdField] : user.external_id;
            var countriesCount = options.countriesCountField ? data[options.countriesCountField] : user.countries_count;
            var entitySummary = options.entitySummaryField ? data[options.entitySummaryField] : user.entity_summary;
            var scopeDisplayLines = user.scope_display_lines;
            var lastPresence = options.lastPresenceField ? data[options.lastPresenceField] : user.last_presence;
            var fallbackLabel = options.fallbackLabel || getTranslation('unknownUser', 'Unknown User');
            var showEmail = options.showEmail !== false;

            var displayName = userName || userEmail || '';
            if (!displayName) {
                return '<div class="ag-user-hover-cell" style="display:flex;width:100%;max-width:100%;min-width:0;align-items:center;gap:0.5rem;">' +
                    deviceIconHtml +
                    '<span class="text-sm text-gray-500">' + escapeHtml(fallbackLabel) + '</span></div>';
            }

            var inlineProfile = {
                id: userId,
                name: userName || '',
                email: userEmail || '',
                title: userTitle || '',
                active: userActive,
                profile_color: profileColor || '#3B82F6',
                role_badge_key: roleBadgeKey || '',
                external_id: externalId ? String(externalId) : '',
                rbac_roles: Array.isArray(roleList) ? roleList : [],
                countries_count: countriesCount,
                entity_summary: entitySummary || '',
                last_presence: lastPresence || null
            };
            if (Array.isArray(scopeDisplayLines) && scopeDisplayLines.length) {
                inlineProfile.scope_display_lines = scopeDisplayLines;
            }

            var encodedProfile = '';
            try {
                encodedProfile = encodeURIComponent(JSON.stringify(inlineProfile));
            } catch (e) {
                encodedProfile = '';
            }

            var emailPad = '1.75rem';

            var html = '<div class="ag-user-hover-cell" style="display:flex;width:100%;max-width:100%;min-width:0;overflow:hidden;box-sizing:border-box;">';
            html += '<span class="ag-user-hover-trigger" style="display:flex;flex:1 1 0%;flex-direction:column;gap:4px;min-width:0;max-width:100%;overflow:hidden;"';
            if (userId !== null && userId !== undefined && userId !== '') {
                html += ' data-user-id="' + escapeHtmlAttr(userId) + '"';
            }
            if (externalId) {
                html += ' data-user-external-id="' + escapeHtmlAttr(String(externalId)) + '"';
            }
            if (userEmail) {
                html += ' data-user-email="' + escapeHtmlAttr(userEmail) + '"';
            }
            if (encodedProfile) {
                html += ' data-user-inline="' + escapeHtmlAttr(encodedProfile) + '"';
            }
            html += '>';
            html += '<span style="display:flex;flex-direction:row;align-items:center;gap:0.5rem;min-width:0;width:100%;">';
            html += deviceIconHtml;
            html += '<span class="ag-user-hover-name" style="flex:1;min-width:0;font-size:0.875rem;line-height:1.4;font-weight:500;color:#111827;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + escapeHtml(displayName) + '</span>';
            html += '</span>';
            if (showEmail && userName && userEmail) {
                html += '<span class="ag-user-hover-subline" style="display:block;padding-left:' + emailPad + ';font-size:0.75rem;line-height:1.4;color:#6b7280;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-width:0;">' + escapeHtml(userEmail) + '</span>';
            }
            html += '</span>';
            html += '</div>';
            return html;
        },

        /**
         * Numeric value with formatting
         * Expects params.value to be a number
         */
        numericValue: function(params) {
            var value = params.value;
            if (value === null || value === undefined) {
                return '<span class="text-gray-400">-</span>';
            }
            var numValue = typeof value === 'number' ? value : parseFloat(value);
            if (isNaN(numValue) || !isFinite(numValue)) {
                return escapeHtml(String(value));
            }
            return '<span class="font-semibold text-blue-700">' + numValue.toLocaleString() + '</span>';
        },

        /**
         * Empty value placeholder
         */
        emptyPlaceholder: function(params) {
            if (!params.value && params.value !== 0) {
                return '<span class="text-gray-400">-</span>';
            }
            return escapeHtml(String(params.value));
        },

        /**
         * Link renderer
         * Expects params.data to contain a URL field (configurable)
         * Usage: { cellRenderer: AgGridRenderers.link('url_field') }
         */
        link: function(urlField) {
            return function(params) {
                var value = params.value;
                if (!value) return '-';
                var url = params.data && params.data[urlField];
                if (!url) return escapeHtml(value);
                return '<a href="' + escapeHtmlAttr(url) + '" class="text-blue-600 hover:text-blue-800 hover:underline">' +
                    escapeHtml(value) + '</a>';
            };
        },

        /**
         * External link (opens in new tab)
         */
        externalLink: function(urlField) {
            return function(params) {
                var value = params.value;
                if (!value) return '-';
                var url = params.data && params.data[urlField];
                if (!url) return escapeHtml(value);
                return '<a href="' + escapeHtmlAttr(url) + '" target="_blank" rel="noopener noreferrer" class="text-blue-600 hover:text-blue-800 hover:underline">' +
                    escapeHtml(value) + ' <i class="fas fa-external-link-alt text-xs ml-1"></i></a>';
            };
        },

        /**
         * Chip/Tag list renderer
         * Expects params.value to be an array of strings
         * @param {number} maxShow - Maximum number of items to show before "+N more"
         */
        chipList: function(maxShow) {
            maxShow = maxShow || 3;
            var moreText = getTranslation('more', 'more');

            return function(params) {
                var items = params.value;
                if (!items || !Array.isArray(items) || items.length === 0) {
                    return '<span class="text-gray-400">-</span>';
                }

                var html = '<div class="flex flex-wrap gap-1">';
                var displayItems = items.slice(0, maxShow);

                displayItems.forEach(function(item) {
                    html += '<span class="bg-gray-200 text-gray-700 text-xs font-medium px-2 py-0.5 rounded">' +
                        escapeHtml(item) + '</span>';
                });

                if (items.length > maxShow) {
                    html += '<span class="text-gray-400 text-xs">+' + (items.length - maxShow) + ' ' + moreText + '</span>';
                }

                html += '</div>';
                return html;
            };
        },

        /**
         * Sector/Category hierarchy display
         * Expects params.data to contain sector_primary, sector_secondary, sector_tertiary
         */
        sectorHierarchy: function(fieldPrefix) {
            fieldPrefix = fieldPrefix || 'sector';

            return function(params) {
                var data = params.data;
                if (!data) return '<span class="text-gray-400">-</span>';

                var parts = [];
                if (data[fieldPrefix + '_primary']) parts.push(data[fieldPrefix + '_primary']);
                if (data[fieldPrefix + '_secondary']) parts.push(data[fieldPrefix + '_secondary']);
                if (data[fieldPrefix + '_tertiary']) parts.push(data[fieldPrefix + '_tertiary']);

                if (parts.length === 0) {
                    return '<span class="text-gray-400">-</span>';
                }

                var html = '<div class="sector-items">';
                parts.forEach(function(part) {
                    html += '<div>' + escapeHtml(part) + '</div>';
                });
                html += '</div>';

                return html;
            };
        }
    };

    /**
     * Common Column Definition Presets
     */
    var AgGridColumnPresets = {
        /**
         * Standard ID column
         */
        id: function(options) {
            options = options || {};
            return {
                field: options.field || 'id',
                headerName: options.headerName || getTranslation('id', 'ID'),
                width: options.width || 80,
                minWidth: options.minWidth || 80,
                maxWidth: options.maxWidth || 120,
                hide: options.hide !== false,
                filter: 'agNumberColumnFilter',
                sortable: true
            };
        },

        /**
         * Actions column (pinned right)
         */
        actions: function(cellRenderer, options) {
            options = options || {};
            var mobileLayout = typeof AgGridRenderers !== 'undefined'
                && typeof AgGridRenderers.isMobileActionsLayout === 'function'
                && AgGridRenderers.isMobileActionsLayout();
            return {
                field: 'actions',
                headerName: options.headerName || getTranslation('actions', 'Actions'),
                width: mobileLayout ? 40 : (options.width || 180),
                minWidth: mobileLayout ? 40 : (options.minWidth || 150),
                maxWidth: mobileLayout ? 44 : (options.maxWidth || 250),
                pinned: 'right',
                lockVisible: true,
                lockPinned: true,
                suppressMovable: true,
                sortable: false,
                filter: false,
                cellRenderer: typeof AgGridRenderers !== 'undefined'
                    && typeof AgGridRenderers.wrapActionsCellRenderer === 'function'
                    ? AgGridRenderers.wrapActionsCellRenderer(cellRenderer)
                    : cellRenderer
            };
        },

        /**
         * Status column with badge renderer
         */
        status: function(options) {
            options = options || {};
            return {
                field: options.field || 'status',
                headerName: options.headerName || getTranslation('status', 'Status'),
                width: options.width || 150,
                minWidth: options.minWidth || 120,
                maxWidth: options.maxWidth || 200,
                filter: 'customSetFilter',
                sortable: true,
                cellRenderer: options.renderer || AgGridRenderers.approvalStatus,
                cellStyle: options.centerAlign !== false ? { 'text-align': 'center' } : undefined
            };
        },

        /**
         * Active/Inactive status column
         */
        activeStatus: function(options) {
            options = options || {};
            return {
                field: options.field || 'active',
                headerName: options.headerName || getTranslation('status', 'Status'),
                width: options.width || 120,
                minWidth: options.minWidth || 100,
                maxWidth: options.maxWidth || 150,
                filter: 'customSetFilter',
                sortable: true,
                cellRenderer: AgGridRenderers.statusBadge
            };
        },

        /**
         * Owner/User column with profile icon
         */
        owner: function(options) {
            options = options || {};
            return {
                field: options.field || 'owner',
                headerName: options.headerName || getTranslation('owner', 'Owner'),
                width: options.width || 250,
                minWidth: options.minWidth || 200,
                maxWidth: options.maxWidth || 350,
                filter: 'agTextColumnFilter',
                sortable: true,
                valueGetter: function(params) {
                    var user = params.data && params.data[options.field || 'owner'];
                    return user ? (user.name || user.email || '') : '';
                },
                cellRenderer: options.wrap ? AgGridRenderers.profileIconWrap : AgGridRenderers.profileIcon,
                cellStyle: { 'white-space': 'normal', 'line-height': '1.4' }
            };
        },

        /**
         * Date column
         */
        date: function(options) {
            options = options || {};
            return {
                field: options.field,
                headerName: options.headerName || getTranslation('date', 'Date'),
                width: options.width || 180,
                minWidth: options.minWidth || 150,
                maxWidth: options.maxWidth || 250,
                filter: 'agTextColumnFilter',
                sortable: true,
                cellRenderer: options.showTime !== false ? AgGridRenderers.dateTime : AgGridRenderers.dateOnly
            };
        },

        /**
         * Text column with word wrap
         */
        textWrap: function(options) {
            options = options || {};
            return {
                field: options.field,
                headerName: options.headerName || '',
                width: options.width || 250,
                minWidth: options.minWidth || 200,
                maxWidth: options.maxWidth || 400,
                filter: 'agTextColumnFilter',
                sortable: true,
                cellRenderer: options.renderer || AgGridRenderers.emptyPlaceholder,
                cellStyle: {
                    'white-space': 'normal',
                    'word-wrap': 'break-word',
                    'line-height': '1.4'
                }
            };
        },

        /**
         * Boolean column with icon
         */
        boolean: function(options) {
            options = options || {};
            return {
                field: options.field,
                headerName: options.headerName || '',
                width: options.width || 120,
                minWidth: options.minWidth || 100,
                maxWidth: options.maxWidth || 150,
                filter: 'customSetFilter',
                sortable: true,
                cellRenderer: options.renderer || AgGridRenderers.booleanIcon,
                cellStyle: { 'text-align': 'center' }
            };
        },

        /**
         * Numeric column
         */
        numeric: function(options) {
            options = options || {};
            return {
                field: options.field,
                headerName: options.headerName || '',
                width: options.width || 120,
                minWidth: options.minWidth || 100,
                maxWidth: options.maxWidth || 180,
                filter: 'agNumberColumnFilter',
                sortable: true,
                cellRenderer: options.formatted ? AgGridRenderers.numericValue : undefined,
                cellStyle: { 'text-align': options.alignRight !== false ? 'right' : 'left' }
            };
        }
    };

    /**
     * Shared comparator for agDateColumnFilter.
     * Normalises cell values (ISO strings, timestamps) to midnight for comparison.
     */
    function dateFilterComparator(filterLocalDateAtMidnight, cellValue) {
        if (!cellValue) return -1;
        var cellDate = new Date(cellValue);
        if (isNaN(cellDate.getTime())) return -1;
        cellDate = new Date(cellDate.getFullYear(), cellDate.getMonth(), cellDate.getDate());
        if (cellDate < filterLocalDateAtMidnight) return -1;
        if (cellDate > filterLocalDateAtMidnight) return 1;
        return 0;
    }

    /**
     * Pre-built filterParams object for agDateColumnFilter columns.
     * Usage: { filter: 'agDateColumnFilter', filterParams: AgGridRenderers.dateFilterParams }
     */
    var dateFilterParams = { comparator: dateFilterComparator };

    /**
     * Null-safe string comparator for AG Grid sorting.
     * Usage: { comparator: AgGridRenderers.safeStringComparator }
     */
    function safeStringComparator(a, b) {
        return (a || '').localeCompare(b || '');
    }

    /**
     * Value formatter that returns an em-dash for null/empty values.
     * Usage: { valueFormatter: AgGridRenderers.dashIfEmpty }
     */
    function dashIfEmpty(params) {
        return (params.value != null && params.value !== '') ? params.value : '\u2014';
    }

    var ICON_ACTION_LABELS = {
        'fa-pen': 'Edit',
        'fa-edit': 'Edit',
        'fa-pencil-alt': 'Edit',
        'fa-eye': 'View',
        'fa-trash': 'Delete',
        'fa-pause-circle': 'Deactivate',
        'fa-play-circle': 'Activate',
        'fa-undo': 'Reopen',
        'fa-lock': 'Close',
        'fa-unlock': 'Unlock',
        'fa-copy': 'Copy',
        'fa-download': 'Download',
        'fa-external-link-alt': 'Open',
        'fa-check': 'Approve',
        'fa-times': 'Reject',
        'fa-ban': 'Revoke'
    };

    function isMobileActionsLayout() {
        if (typeof AgGridUtils !== 'undefined' && typeof AgGridUtils.isCoarsePointerDevice === 'function') {
            return AgGridUtils.isCoarsePointerDevice();
        }
        if (typeof AgGridHelper !== 'undefined' && typeof AgGridHelper.isCoarsePointerDevice === 'function') {
            return AgGridHelper.isCoarsePointerDevice();
        }
        return (window.innerWidth || 0) <= 768;
    }

    function labelFromIconClasses(className) {
        if (!className) {
            return '';
        }
        var classes = String(className).split(/\s+/);
        for (var i = 0; i < classes.length; i++) {
            var cls = classes[i];
            if (ICON_ACTION_LABELS[cls]) {
                return ICON_ACTION_LABELS[cls];
            }
        }
        return '';
    }

    function getActionElementLabel(el) {
        if (!el) {
            return getTranslation('actions', 'Actions');
        }

        var target = el;
        if (el.tagName === 'FORM') {
            target = el.querySelector('button[type="submit"], button, a[href]') || el;
        }

        var title = target.getAttribute && (target.getAttribute('title') || target.getAttribute('aria-label'));
        if (title && String(title).trim()) {
            return String(title).trim();
        }

        var text = target.textContent && String(target.textContent).replace(/\s+/g, ' ').trim();
        if (text) {
            return text;
        }

        var icon = target.querySelector && target.querySelector('i[class*="fa-"]');
        if (icon) {
            var fromIcon = labelFromIconClasses(icon.className);
            if (fromIcon) {
                return fromIcon;
            }
        }

        return getTranslation('action', 'Action');
    }

    function collectActionElements(root) {
        var actions = [];
        if (!root) {
            return actions;
        }

        var direct = root.querySelectorAll(':scope > form, :scope > a[href], :scope > button');
        if (direct.length) {
            direct.forEach(function(node) {
                actions.push(node);
            });
            return actions;
        }

        root.querySelectorAll('form, a[href], button').forEach(function(node) {
            if (node.closest('form') && node.tagName !== 'FORM') {
                return;
            }
            if (actions.indexOf(node) === -1) {
                actions.push(node);
            }
        });
        return actions;
    }

    function closeAgActionsOverflowMenus(exceptMenu) {
        document.querySelectorAll('.ag-actions-overflow-menu').forEach(function(menu) {
            if (menu === exceptMenu) {
                return;
            }

            menu.classList.add('hidden');
            menu.classList.remove('ag-actions-overflow-menu--portal');
            menu.style.position = '';
            menu.style.top = '';
            menu.style.left = '';
            menu.style.right = '';
            menu.style.bottom = '';
            menu.style.zIndex = '';

            var wrap = menu._agActionsWrap;
            if (wrap && menu.parentElement === document.body) {
                wrap.appendChild(menu);
            }

            var toggle = wrap
                ? wrap.querySelector('.ag-actions-overflow-btn')
                : (menu.parentElement
                    ? menu.parentElement.querySelector('.ag-actions-overflow-btn')
                    : null);
            if (toggle) {
                toggle.setAttribute('aria-expanded', 'false');
            }

            menu._agActionsWrap = null;
            menu._agActionsToggle = null;
        });
    }

    function positionAgActionsOverflowMenu(toggle, menu) {
        var rect = toggle.getBoundingClientRect();
        var menuWidth = menu.offsetWidth || 160;
        var menuHeight = menu.offsetHeight || 120;
        var viewportW = window.innerWidth || document.documentElement.clientWidth || 0;
        var viewportH = window.innerHeight || document.documentElement.clientHeight || 0;
        var margin = 8;
        var isRtl = document.documentElement.getAttribute('dir') === 'rtl'
            || menu.closest('.ag-rtl');

        var left = isRtl ? rect.left : (rect.right - menuWidth);
        if (left < margin) {
            left = margin;
        }
        if (left + menuWidth > viewportW - margin) {
            left = Math.max(margin, viewportW - menuWidth - margin);
        }

        var top = rect.bottom + 4;
        if (top + menuHeight > viewportH - margin) {
            top = rect.top - menuHeight - 4;
        }
        if (top < margin) {
            top = margin;
        }

        menu.style.position = 'fixed';
        menu.style.left = Math.round(left) + 'px';
        menu.style.top = Math.round(top) + 'px';
        menu.style.right = 'auto';
        menu.style.bottom = 'auto';
        menu.style.zIndex = '10050';
    }

    function openAgActionsOverflowMenu(toggle, menu, wrap) {
        menu._agActionsWrap = wrap;
        menu._agActionsToggle = toggle;
        wrap._agActionsMenu = menu;

        if (menu.parentElement !== document.body) {
            document.body.appendChild(menu);
        }

        menu.classList.remove('hidden');
        menu.classList.add('ag-actions-overflow-menu--portal');
        toggle.setAttribute('aria-expanded', 'true');
        positionAgActionsOverflowMenu(toggle, menu);
    }

    function getAgActionsOverflowWrapFromMenu(menu) {
        if (!menu) {
            return null;
        }
        if (menu._agActionsWrap && document.body.contains(menu._agActionsWrap)) {
            return menu._agActionsWrap;
        }
        return menu.closest('.ag-actions-overflow');
    }

    function triggerAgActionElement(el) {
        if (!el) {
            return;
        }
        if (el.tagName === 'FORM') {
            var submitBtn = el.querySelector('button[type="submit"], button');
            if (submitBtn) {
                submitBtn.click();
            } else if (typeof el.requestSubmit === 'function') {
                el.requestSubmit();
            } else {
                el.submit();
            }
            return;
        }
        el.click();
    }

    /**
     * Render desktop action icons or a compact vertical-dots menu on mobile.
     * @param {string} desktopHtml - HTML from the page's actions cellRenderer
     * @param {Object} [params] - AG Grid cell renderer params (optional)
     * @returns {string}
     */
    function renderActionsCell(desktopHtml, params) {
        if (!desktopHtml || !isMobileActionsLayout()) {
            return desktopHtml || '';
        }

        var wrapper = document.createElement('div');
        wrapper.innerHTML = desktopHtml;
        var root = wrapper.firstElementChild || wrapper;
        var actionElements = collectActionElements(root);
        if (!actionElements.length) {
            return desktopHtml;
        }

        var rowKey = (params && params.node && params.node.id != null)
            ? String(params.node.id)
            : String((params && params.rowIndex != null) ? params.rowIndex : Math.random().toString(36).slice(2));

        var menuItemsHtml = actionElements.map(function(actionEl, index) {
            var label = escapeHtml(getActionElementLabel(actionEl));
            return '<button type="button" role="menuitem" class="ag-actions-overflow-item" data-action-index="' + index + '">' + label + '</button>';
        }).join('');

        return ''
            + '<div class="ag-actions-overflow" data-ag-actions-row="' + escapeHtmlAttr(rowKey) + '">'
            + '<button type="button" class="ag-actions-overflow-btn" aria-haspopup="menu" aria-expanded="false" title="'
            + escapeHtmlAttr(getTranslation('actions', 'Actions')) + '" aria-label="'
            + escapeHtmlAttr(getTranslation('actions', 'Actions')) + '">'
            + '<i class="fas fa-ellipsis-v" aria-hidden="true"></i>'
            + '</button>'
            + '<div class="ag-actions-overflow-menu hidden" role="menu">' + menuItemsHtml + '</div>'
            + '<div class="ag-actions-overflow-source" hidden aria-hidden="true">' + desktopHtml + '</div>'
            + '</div>';
    }

    /**
     * Wrap an actions column cellRenderer to use the mobile overflow menu automatically.
     * @param {Function|string} originalRenderer
     * @returns {Function}
     */
    function wrapActionsCellRenderer(originalRenderer) {
        return function(params) {
            var html = '';
            if (typeof originalRenderer === 'function') {
                html = originalRenderer(params);
            } else if (typeof originalRenderer === 'string') {
                html = originalRenderer;
            }
            return renderActionsCell(html, params);
        };
    }

    var agActionsOverflowListenersBound = false;
    function setupAgActionsOverflowListeners() {
        if (agActionsOverflowListenersBound) {
            return;
        }
        agActionsOverflowListenersBound = true;

        document.addEventListener('click', function(event) {
            var toggle = event.target.closest('.ag-actions-overflow-btn');
            if (toggle) {
                event.preventDefault();
                event.stopPropagation();
                var wrap = toggle.closest('.ag-actions-overflow');
                if (!wrap) {
                    return;
                }
                var menu = wrap._agActionsMenu || wrap.querySelector('.ag-actions-overflow-menu');
                if (!menu) {
                    return;
                }
                var isOpen = menu.classList.contains('ag-actions-overflow-menu--portal') &&
                    !menu.classList.contains('hidden');
                if (isOpen) {
                    closeAgActionsOverflowMenus();
                } else {
                    closeAgActionsOverflowMenus();
                    openAgActionsOverflowMenu(toggle, menu, wrap);
                }
                return;
            }

            var menuItem = event.target.closest('.ag-actions-overflow-item');
            if (menuItem) {
                event.preventDefault();
                event.stopPropagation();
                var menuEl = menuItem.closest('.ag-actions-overflow-menu');
                var cellWrap = getAgActionsOverflowWrapFromMenu(menuEl);
                var source = cellWrap ? cellWrap.querySelector('.ag-actions-overflow-source') : null;
                var index = parseInt(menuItem.getAttribute('data-action-index'), 10);
                if (source && !isNaN(index)) {
                    var actionElements = collectActionElements(source.firstElementChild || source);
                    triggerAgActionElement(actionElements[index]);
                }
                closeAgActionsOverflowMenus();
                return;
            }

            if (!event.target.closest('.ag-actions-overflow') &&
                !event.target.closest('.ag-actions-overflow-menu')) {
                closeAgActionsOverflowMenus();
            }
        }, true);

        window.addEventListener('scroll', function() {
            closeAgActionsOverflowMenus();
        }, true);

        window.addEventListener('resize', function() {
            closeAgActionsOverflowMenus();
        });
    }

    setupAgActionsOverflowListeners();

    // Attach shared utilities to AgGridRenderers
    AgGridRenderers.dateFilterComparator = dateFilterComparator;
    AgGridRenderers.dateFilterParams = dateFilterParams;
    AgGridRenderers.safeStringComparator = safeStringComparator;
    AgGridRenderers.dashIfEmpty = dashIfEmpty;
    AgGridRenderers.isMobileActionsLayout = isMobileActionsLayout;
    AgGridRenderers.renderActionsCell = renderActionsCell;
    AgGridRenderers.wrapActionsCellRenderer = wrapActionsCellRenderer;

    // Export to global scope
    window.AgGridRenderers = AgGridRenderers;
    window.AgGridColumnPresets = AgGridColumnPresets;

    // Also export utility functions
    window.AgGridRenderers.escapeHtml = escapeHtml;
    window.AgGridRenderers.escapeHtmlAttr = escapeHtmlAttr;
    window.AgGridRenderers.getTranslation = getTranslation;

})();
