/**
 * Date/Time Utility
 * Centralized date/time formatting and timezone conversion for the application.
 *
 * All dates are stored in UTC in the database. This utility:
 * 1. Converts UTC dates to the user's local timezone for display
 * 2. Provides consistent formatting across the application
 * 3. Supports localized date/time formats
 *
 * Usage:
 *   // Auto-convert all elements with data-datetime attribute
 *   DateTimeUtils.convertAll();
 *
 *   // Convert a specific element
 *   DateTimeUtils.convertElement(element, 'datetime');
 *
 *   // Format a date string
 *   DateTimeUtils.format('2024-01-15T10:30:00Z', 'datetime');
 *
 *   // For AG Grid cell renderer
 *   DateTimeUtils.agGridRenderer(params, 'datetime');
 */

(function() {
    'use strict';

    /**
     * Get the user's locale from the page or browser
     * @returns {string} Locale string (e.g., 'en-US', 'ar-SA')
     */
    function getUserLocale() {
        // Try to get from HTML lang attribute
        const htmlLang = document.documentElement.lang;
        if (htmlLang) {
            return htmlLang;
        }
        // Fallback to browser locale
        return navigator.language || navigator.userLanguage || 'en-US';
    }

    /**
     * Format options for different display types
     */
    const FORMAT_OPTIONS = {
        // Full date and time: "Jan 15, 2024, 10:30 AM"
        datetime: {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        },
        // Full date and time with seconds: "Jan 15, 2024, 10:30:45 AM"
        datetimeFull: {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        },
        // Short datetime: "1/15/24, 10:30 AM"
        datetimeShort: {
            year: '2-digit',
            month: 'numeric',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        },
        // Date only: "Jan 15, 2024"
        date: {
            year: 'numeric',
            month: 'short',
            day: 'numeric'
        },
        // Short date: "1/15/24"
        dateShort: {
            year: '2-digit',
            month: 'numeric',
            day: 'numeric'
        },
        // ISO-style date: "2024-01-15"
        dateISO: {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit'
        },
        // Time only: "10:30 AM"
        time: {
            hour: '2-digit',
            minute: '2-digit'
        },
        // Time with seconds: "10:30:45 AM"
        timeFull: {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        },
        // Relative time display (handled specially)
        relative: null
    };

    /**
     * Parse a datetime string to a Date object
     * Handles various formats including ISO strings and naive datetimes
     * @param {string|Date} dateInput - Date string or Date object
     * @returns {Date|null} Parsed Date object or null if invalid
     */
    function parseDate(dateInput) {
        if (!dateInput) {
            return null;
        }

        if (dateInput instanceof Date) {
            return isNaN(dateInput.getTime()) ? null : dateInput;
        }

        let dateStr = String(dateInput).trim();

        // Handle empty strings
        if (!dateStr) {
            return null;
        }

        // If no timezone indicator, assume UTC (naive datetime from Python)
        // Check for Z, +, or - timezone indicators
        if (!dateStr.endsWith('Z') && !dateStr.match(/[+-]\d{2}:?\d{2}$/)) {
            // If it has a T separator, add Z for UTC
            if (dateStr.includes('T')) {
                dateStr += 'Z';
            } else if (dateStr.match(/^\d{4}-\d{2}-\d{2}$/)) {
                // Date only - add time and timezone
                dateStr += 'T00:00:00Z';
            } else if (dateStr.match(/^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}/)) {
                // Space-separated datetime - convert to ISO format
                dateStr = dateStr.replace(' ', 'T') + 'Z';
            }
        }

        const date = new Date(dateStr);
        return isNaN(date.getTime()) ? null : date;
    }

    /**
     * Format a date according to the specified format type
     * @param {string|Date} dateInput - Date string or Date object
     * @param {string} formatType - Format type (datetime, date, time, etc.)
     * @param {Object} options - Additional options
     * @param {string} options.locale - Override locale
     * @param {boolean} options.showTimezone - Show timezone abbreviation
     * @returns {string} Formatted date string
     */
    function format(dateInput, formatType, options) {
        formatType = formatType || 'datetime';
        options = options || {};

        const date = parseDate(dateInput);
        if (!date) {
            return options.fallback || '';
        }

        const locale = options.locale || getUserLocale();

        // Handle relative time
        if (formatType === 'relative') {
            return formatRelative(date, locale);
        }

        // Get format options
        const formatOpts = FORMAT_OPTIONS[formatType] || FORMAT_OPTIONS.datetime;

        try {
            let formatted = new Intl.DateTimeFormat(locale, formatOpts).format(date);

            // Optionally append timezone
            if (options.showTimezone) {
                const tzAbbr = getTimezoneAbbreviation(date);
                if (tzAbbr) {
                    formatted += ' ' + tzAbbr;
                }
            }

            return formatted;
        } catch (e) {
            console.warn('DateTimeUtils: Error formatting date:', e);
            // Fallback to manual formatting
            return formatManual(date, formatType);
        }
    }

    /**
     * Format relative time (e.g., "2 hours ago", "in 3 days")
     * @param {Date} date - Date object
     * @param {string} locale - Locale string
     * @returns {string} Relative time string
     */
    function formatRelative(date, locale) {
        const now = new Date();
        const diffMs = now - date;
        const diffSec = Math.floor(diffMs / 1000);
        const diffMin = Math.floor(diffSec / 60);
        const diffHour = Math.floor(diffMin / 60);
        const diffDay = Math.floor(diffHour / 24);

        // Try to use Intl.RelativeTimeFormat if available
        if (typeof Intl.RelativeTimeFormat === 'function') {
            try {
                const rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });

                if (Math.abs(diffDay) >= 30) {
                    return rtf.format(-Math.floor(diffDay / 30), 'month');
                } else if (Math.abs(diffDay) >= 1) {
                    return rtf.format(-diffDay, 'day');
                } else if (Math.abs(diffHour) >= 1) {
                    return rtf.format(-diffHour, 'hour');
                } else if (Math.abs(diffMin) >= 1) {
                    return rtf.format(-diffMin, 'minute');
                } else {
                    return rtf.format(-diffSec, 'second');
                }
            } catch (e) {
                // Fall through to manual formatting
            }
        }

        // Manual fallback
        if (diffDay > 30) {
            return Math.floor(diffDay / 30) + ' months ago';
        } else if (diffDay > 1) {
            return diffDay + ' days ago';
        } else if (diffDay === 1) {
            return 'yesterday';
        } else if (diffHour > 1) {
            return diffHour + ' hours ago';
        } else if (diffHour === 1) {
            return '1 hour ago';
        } else if (diffMin > 1) {
            return diffMin + ' minutes ago';
        } else if (diffMin === 1) {
            return '1 minute ago';
        } else {
            return 'just now';
        }
    }

    /**
     * Get timezone abbreviation for a date
     * @param {Date} date - Date object
     * @returns {string} Timezone abbreviation (e.g., "PST", "UTC")
     */
    function getTimezoneAbbreviation(date) {
        try {
            const options = { timeZoneName: 'short' };
            const formatter = new Intl.DateTimeFormat('en-US', options);
            const parts = formatter.formatToParts(date);
            const tzPart = parts.find(function(p) { return p.type === 'timeZoneName'; });
            return tzPart ? tzPart.value : '';
        } catch (e) {
            return '';
        }
    }

    /**
     * Manual fallback formatting when Intl is not available
     * @param {Date} date - Date object
     * @param {string} formatType - Format type
     * @returns {string} Formatted date string
     */
    function formatManual(date, formatType) {
        const year = date.getFullYear();
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const day = String(date.getDate()).padStart(2, '0');
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        const seconds = String(date.getSeconds()).padStart(2, '0');

        switch (formatType) {
            case 'date':
            case 'dateShort':
            case 'dateISO':
                return year + '-' + month + '-' + day;
            case 'time':
                return hours + ':' + minutes;
            case 'timeFull':
                return hours + ':' + minutes + ':' + seconds;
            case 'datetimeFull':
                return year + '-' + month + '-' + day + ' ' + hours + ':' + minutes + ':' + seconds;
            case 'datetime':
            case 'datetimeShort':
            default:
                return year + '-' + month + '-' + day + ' ' + hours + ':' + minutes;
        }
    }

    /**
     * Convert a single element's datetime to local timezone
     * @param {HTMLElement} element - Element with data-datetime attribute
     * @param {string} formatType - Format type to use
     * @param {Object} options - Additional options
     */
    function convertElement(element, formatType, options) {
        if (!element) {
            return;
        }

        formatType = formatType || element.dataset.datetimeFormat || 'datetime';
        options = options || {};

        const utcDateStr = element.dataset.datetime || element.getAttribute('data-datetime');
        if (!utcDateStr || utcDateStr.trim() === '') {
            return;
        }

        const formatted = format(utcDateStr, formatType, options);
        if (formatted) {
            element.textContent = formatted;
            // Mark as converted to avoid re-processing
            element.dataset.datetimeConverted = 'true';
        }
    }

    /**
     * Convert all elements with data-datetime attribute on the page
     * @param {HTMLElement} container - Optional container to search within (defaults to document)
     * @param {Object} options - Options to pass to convertElement
     */
    function convertAll(container, options) {
        container = container || document;
        options = options || {};

        // Find all elements with data-datetime that haven't been converted
        var selector = '[data-datetime]:not([data-datetime-converted="true"])';
        var elements = container.querySelectorAll(selector);

        elements.forEach(function(element) {
            var formatType = element.dataset.datetimeFormat || 'datetime';
            convertElement(element, formatType, options);
        });
    }

    /**
     * Create an AG Grid cell renderer for datetime columns
     * @param {Object} params - AG Grid cell renderer params
     * @param {string} formatType - Format type to use
     * @param {Object} options - Additional options
     * @param {string} options.field - Field name to get date from (defaults to params.value)
     * @param {string} options.emptyValue - Value to show for empty dates (defaults to '-')
     * @param {boolean} options.showTimezone - Show timezone abbreviation
     * @returns {string} HTML string for the cell
     */
    function agGridRenderer(params, formatType, options) {
        formatType = formatType || 'datetime';
        options = options || {};

        var value = options.field ? params.data[options.field] : params.value;
        var emptyValue = options.emptyValue !== undefined ? options.emptyValue : '-';

        if (!value) {
            return '<span class="text-gray-400">' + emptyValue + '</span>';
        }

        var formatted = format(value, formatType, options);
        if (!formatted) {
            return '<span class="text-gray-400">' + emptyValue + '</span>';
        }

        // Build the HTML with proper styling
        var html = '<div class="datetime-cell">';
        html += '<span class="text-sm text-gray-900">' + escapeHtml(formatted) + '</span>';

        // Optionally show timezone separately
        if (options.showTimezone) {
            var date = parseDate(value);
            if (date) {
                var tz = getTimezoneAbbreviation(date);
                if (tz) {
                    html += '<div class="text-xs text-gray-500">' + escapeHtml(tz) + '</div>';
                }
            }
        }

        html += '</div>';
        return html;
    }

    /**
     * Create a dual-line AG Grid cell renderer (date on top, time below)
     * @param {Object} params - AG Grid cell renderer params
     * @param {Object} options - Additional options
     * @returns {string} HTML string for the cell
     */
    function agGridDualLineRenderer(params, options) {
        options = options || {};

        var value = options.field ? params.data[options.field] : params.value;
        var emptyValue = options.emptyValue !== undefined ? options.emptyValue : '-';

        if (!value) {
            return '<span class="text-gray-400">' + emptyValue + '</span>';
        }

        var date = parseDate(value);
        if (!date) {
            return '<span class="text-gray-400">' + emptyValue + '</span>';
        }

        var dateFormatted = format(date, 'date', options);
        var timeFormatted = format(date, 'time', options);

        var html = '<div class="datetime-cell-dual">';
        html += '<div class="text-sm text-gray-900">' + escapeHtml(dateFormatted) + '</div>';
        html += '<div class="text-xs text-gray-500">' + escapeHtml(timeFormatted) + '</div>';

        if (options.showTimezone) {
            var tz = getTimezoneAbbreviation(date);
            if (tz) {
                html += '<div class="text-xs text-gray-400">' + escapeHtml(tz) + '</div>';
            }
        }

        html += '</div>';
        return html;
    }

    /**
     * Helper function to escape HTML
     * @param {string} str - String to escape
     * @returns {string} Escaped string
     */
    function escapeHtml(str) {
        if (!str) return '';
        var div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    /**
     * Set up a MutationObserver to automatically convert new datetime elements
     * @param {HTMLElement} container - Container to observe (defaults to document.body)
     */
    function observeNewElements(container) {
        container = container || document.body;

        if (typeof MutationObserver === 'undefined') {
            return;
        }

        var observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                mutation.addedNodes.forEach(function(node) {
                    if (node.nodeType === 1) {
                        // Check if node itself has data-datetime
                        if (node.hasAttribute && node.hasAttribute('data-datetime')) {
                            convertElement(node);
                        }
                        // Check descendants
                        if (node.querySelectorAll) {
                            convertAll(node);
                        }
                    }
                });
            });
        });

        observer.observe(container, { childList: true, subtree: true });
    }

    /**
     * Get an ISO string for a Date in UTC
     * Useful for sending dates back to the server
     * @param {Date} date - Date object
     * @returns {string} ISO string in UTC
     */
    function toUTCISO(date) {
        if (!date || !(date instanceof Date) || isNaN(date.getTime())) {
            return '';
        }
        return date.toISOString();
    }

    /**
     * Convert local datetime input value to UTC for server
     * @param {string} localDatetimeStr - Local datetime string from input (e.g., "2024-01-15T10:30")
     * @returns {string} UTC ISO string
     */
    function localInputToUTC(localDatetimeStr) {
        if (!localDatetimeStr) {
            return '';
        }
        // Parse as local time
        var date = new Date(localDatetimeStr);
        if (isNaN(date.getTime())) {
            return '';
        }
        return date.toISOString();
    }

    /**
     * Convert UTC datetime to local datetime input value
     * @param {string} utcDatetimeStr - UTC datetime string
     * @returns {string} Local datetime string for input (e.g., "2024-01-15T10:30")
     */
    function utcToLocalInput(utcDatetimeStr) {
        var date = parseDate(utcDatetimeStr);
        if (!date) {
            return '';
        }
        // Format for datetime-local input (YYYY-MM-DDTHH:MM)
        var year = date.getFullYear();
        var month = String(date.getMonth() + 1).padStart(2, '0');
        var day = String(date.getDate()).padStart(2, '0');
        var hours = String(date.getHours()).padStart(2, '0');
        var minutes = String(date.getMinutes()).padStart(2, '0');

        return year + '-' + month + '-' + day + 'T' + hours + ':' + minutes;
    }

    // Export public API
    window.DateTimeUtils = {
        // Core functions
        format: format,
        parseDate: parseDate,

        // Element conversion
        convertElement: convertElement,
        convertAll: convertAll,
        observeNewElements: observeNewElements,

        // AG Grid renderers
        agGridRenderer: agGridRenderer,
        agGridDualLineRenderer: agGridDualLineRenderer,

        // Input helpers
        toUTCISO: toUTCISO,
        localInputToUTC: localInputToUTC,
        utcToLocalInput: utcToLocalInput,

        // Utility
        getUserLocale: getUserLocale,
        getTimezoneAbbreviation: getTimezoneAbbreviation,

        // Format options reference (for customization)
        FORMAT_OPTIONS: FORMAT_OPTIONS
    };

    // Auto-initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            convertAll();
            observeNewElements();
        });
    } else {
        // DOM already ready
        convertAll();
        observeNewElements();
    }

})();
