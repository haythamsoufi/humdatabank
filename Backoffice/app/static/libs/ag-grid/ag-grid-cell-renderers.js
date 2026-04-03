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
        // Try window.agGridTranslations first
        if (window.agGridTranslations && window.agGridTranslations[key]) {
            return window.agGridTranslations[key];
        }

        // Try i18n-json element
        try {
            var i18nEl = document.getElementById('i18n-json');
            if (i18nEl && i18nEl.textContent) {
                var i18n = JSON.parse(i18nEl.textContent);
                if (i18n[key]) {
                    return i18n[key];
                }
            }
        } catch (e) {
            // Ignore
        }

        return defaultValue;
    }

    /**
     * Escape HTML to prevent XSS
     * @param {*} text - Value to escape
     * @returns {string} Escaped HTML string
     */
    function escapeHtml(text) {
        if (text === null || text === undefined) return '';
        var str = String(text);
        return str
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

            if (isActive) {
                return '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-green-100 text-green-800">' +
                    activeText + '</span>';
            }
            return '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-semibold bg-gray-200 text-gray-700">' +
                inactiveText + '</span>';
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
                    return '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">' +
                        '<i class="fas fa-check-circle mr-1"></i>' + approvedText + '</span>';
                case 'rejected':
                    return '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">' +
                        '<i class="fas fa-times-circle mr-1"></i>' + rejectedText + '</span>';
                default:
                    return '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">' +
                        '<i class="fas fa-clock mr-1"></i>' + (pendingReviewText || pendingText) + '</span>';
            }
        },

        /**
         * Deployed/Not Yet status badge
         * Expects params.data.is_deployed to be boolean
         */
        deployedStatus: function(params) {
            var isDeployed = params.data && params.data.is_deployed;
            var deployedText = getTranslation('deployed', 'Deployed');
            var notYetText = getTranslation('notYet', 'Not Yet');
            var displayText = params.value || (isDeployed ? deployedText : notYetText);

            if (isDeployed) {
                return '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">' +
                    '<i class="fas fa-check-circle mr-1"></i>' + displayText + '</span>';
            }
            return '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">' +
                '<i class="fas fa-clock mr-1"></i>' + displayText + '</span>';
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

            if (params.value) {
                return '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">' +
                    '<i class="fas fa-globe mr-1"></i>' + publicText + '</span>';
            }
            return '<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">' +
                '<i class="fas fa-lock mr-1"></i>' + privateText + '</span>';
        },

        /**
         * Archived/Active status badge
         * Expects params.value to be boolean (true = archived)
         */
        archivedStatus: function(params) {
            var archivedText = getTranslation('archived', 'Archived');
            var activeText = getTranslation('active', 'Active');

            if (params.value) {
                return '<span class="inline-flex items-center gap-x-1.5 py-1 px-2.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">' +
                    '<i class="fas fa-archive"></i>' + archivedText + '</span>';
            }
            return '<span class="inline-flex items-center gap-x-1.5 py-1 px-2.5 rounded-full text-xs font-medium bg-green-100 text-green-800">' +
                '<i class="fas fa-check-circle"></i>' + activeText + '</span>';
        },

        /**
         * Emergency indicator
         * Expects params.value to be boolean
         */
        emergencyBadge: function(params) {
            var emergencyText = getTranslation('emergency', 'Emergency');

            if (params.value) {
                return '<span class="inline-flex items-center gap-x-1.5 py-1 px-2.5 rounded-full text-xs font-bold bg-red-100 text-red-800">' +
                    '<i class="fas fa-exclamation-triangle"></i>' + emergencyText + '</span>';
            }
            return '<span class="text-gray-400">-</span>';
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

            var initials = name ?
                name.split(' ').map(function(n) { return n[0]; }).join('').toUpperCase().substring(0, 2) :
                email.split('@')[0].toUpperCase().substring(0, 2);

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

            var initials = name ?
                name.split(' ').map(function(n) { return n[0]; }).join('').toUpperCase().substring(0, 2) :
                email.split('@')[0].toUpperCase().substring(0, 2);

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
            var countriesCount = options.countriesCountField ? data[options.countriesCountField] : user.countries_count;
            var entitySummary = options.entitySummaryField ? data[options.entitySummaryField] : user.entity_summary;
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
                rbac_roles: Array.isArray(roleList) ? roleList : [],
                countries_count: countriesCount,
                entity_summary: entitySummary || '',
                last_presence: lastPresence || null
            };

            var encodedProfile = '';
            try {
                encodedProfile = encodeURIComponent(JSON.stringify(inlineProfile));
            } catch (e) {
                encodedProfile = '';
            }

            var html = '<div class="ag-user-hover-cell" style="display:flex;width:100%;min-width:0;">';
            html += '<span class="ag-user-hover-trigger" style="display:inline-flex;flex-direction:column;min-width:0;cursor:pointer;"';
            if (userId !== null && userId !== undefined && userId !== '') {
                html += ' data-user-id="' + escapeHtmlAttr(userId) + '"';
            }
            if (userEmail) {
                html += ' data-user-email="' + escapeHtmlAttr(userEmail) + '"';
            }
            if (encodedProfile) {
                html += ' data-user-inline="' + escapeHtmlAttr(encodedProfile) + '"';
            }
            html += '>';
            html += '<span class="ag-user-hover-name" style="font-size:0.875rem;font-weight:500;color:#111827;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + escapeHtml(displayName) + '</span>';
            if (showEmail && userName && userEmail) {
                html += '<span class="ag-user-hover-subline" style="font-size:0.75rem;color:#6b7280;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' + escapeHtml(userEmail) + '</span>';
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
                lockVisible: options.lockVisible !== false,
                filter: 'agNumberColumnFilter',
                sortable: true
            };
        },

        /**
         * Actions column (pinned right)
         */
        actions: function(cellRenderer, options) {
            options = options || {};
            return {
                field: 'actions',
                headerName: options.headerName || getTranslation('actions', 'Actions'),
                width: options.width || 180,
                minWidth: options.minWidth || 150,
                maxWidth: options.maxWidth || 250,
                pinned: 'right',
                lockVisible: true,
                lockPinned: true,
                suppressMovable: true,
                sortable: false,
                filter: false,
                cellRenderer: cellRenderer
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

    // Attach shared utilities to AgGridRenderers
    AgGridRenderers.dateFilterComparator = dateFilterComparator;
    AgGridRenderers.dateFilterParams = dateFilterParams;
    AgGridRenderers.safeStringComparator = safeStringComparator;
    AgGridRenderers.dashIfEmpty = dashIfEmpty;

    // Export to global scope
    window.AgGridRenderers = AgGridRenderers;
    window.AgGridColumnPresets = AgGridColumnPresets;

    // Also export utility functions
    window.AgGridRenderers.escapeHtml = escapeHtml;
    window.AgGridRenderers.escapeHtmlAttr = escapeHtmlAttr;
    window.AgGridRenderers.getTranslation = getTranslation;

})();
