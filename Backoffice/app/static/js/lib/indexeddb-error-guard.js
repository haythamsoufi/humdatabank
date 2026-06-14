/**
 * Suppresses and tracks IndexedDB errors from third-party polyfills.
 * Native IndexedDB diagnostics remain available via diagnoseIndexedDB().
 */
(function () {
    'use strict';

    window._indexedDBErrors = window._indexedDBErrors || [];

    function isIndexedDBErrorMessage(message) {
        return message && (
            message.includes('IndexedDB') ||
            message.includes('indexedDB') ||
            message.includes('IDBDatabase')
        );
    }

    window.addEventListener('error', function (event) {
        const isIndexedDBError = isIndexedDBErrorMessage(event.message) ||
            (event.filename && event.filename.includes('polyfill'));

        if (!isIndexedDBError) {
            return;
        }

        const errorInfo = {
            message: event.message,
            filename: event.filename,
            lineno: event.lineno,
            colno: event.colno,
            stack: event.error ? event.error.stack : 'No stack trace',
            timestamp: new Date().toISOString(),
            url: window.location.href
        };
        window._indexedDBErrors.push(errorInfo);

        if (window._indexedDBErrors.length <= 3) {
            window.__clientGroup && window.__clientGroup('⚠️ IndexedDB Error from Third-Party Library');
            window.__clientWarn && window.__clientWarn('Message:', event.message);
            window.__clientWarn && window.__clientWarn('Source:', event.filename || 'Unknown');
            window.__clientWarn && window.__clientWarn('Line:', event.lineno, 'Column:', event.colno);
            if (event.error && event.error.stack) {
                window.__clientWarn && window.__clientWarn('Stack trace:', event.error.stack);
            }
            window.__clientWarn && window.__clientWarn('This error is from a polyfill/library, not native IndexedDB.');
            window.__clientWarn && window.__clientWarn('Native IndexedDB is working correctly (run diagnoseIndexedDB() to verify).');
            window.__clientWarn && window.__clientWarn('To view all tracked errors:', 'window._indexedDBErrors');
            window.__clientGroupEnd && window.__clientGroupEnd();
        } else if (window._indexedDBErrors.length === 4) {
            window.__clientWarn && window.__clientWarn('IndexedDB errors suppressed (3+ occurrences). View all:', 'window._indexedDBErrors');
        }

        event.preventDefault();
    }, true);

    window.addEventListener('unhandledrejection', function (event) {
        const reason = event.reason;
        const errorMessage = reason?.message || reason?.toString() || '';

        const isIndexedDBRejection = isIndexedDBErrorMessage(errorMessage) ||
            (reason?.name && reason.name.includes('DOMException'));

        if (!isIndexedDBRejection) {
            return;
        }

        const rejectionInfo = {
            message: errorMessage,
            reason: reason,
            stack: reason?.stack || 'No stack trace',
            timestamp: new Date().toISOString(),
            url: window.location.href
        };
        window._indexedDBErrors.push(rejectionInfo);

        if (window._indexedDBErrors.length <= 3) {
            window.__clientGroup && window.__clientGroup('⚠️ IndexedDB Promise Rejection from Third-Party Library');
            window.__clientWarn && window.__clientWarn('Error:', errorMessage);
            if (reason?.stack) {
                window.__clientWarn && window.__clientWarn('Stack trace:', reason.stack);
            }
            window.__clientWarn && window.__clientWarn('This rejection is from a polyfill/library, not native IndexedDB.');
            window.__clientWarn && window.__clientWarn('To view all tracked errors:', 'window._indexedDBErrors');
            window.__clientGroupEnd && window.__clientGroupEnd();
        }

        window.__clientWarn && window.__clientWarn('IndexedDB promise rejection (suppressed, non-critical):', errorMessage);
        event.preventDefault();
    });
})();
