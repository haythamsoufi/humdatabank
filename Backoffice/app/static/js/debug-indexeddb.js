/**
 * IndexedDB Diagnostic Utility
 * Helps diagnose why IndexedDB might be failing in Azure Container environments
 *
 * Usage: Include this script and call diagnoseIndexedDB() in the browser console
 */

(function() {
    'use strict';

    /**
     * Comprehensive IndexedDB diagnostic
     * Returns detailed information about IndexedDB availability and potential issues
     */
    window.diagnoseIndexedDB = function() {
        const results = {
            timestamp: new Date().toISOString(),
            environment: {},
            indexedDB: {},
            storage: {},
            security: {},
            browser: {},
            errors: [],
            recommendations: []
        };

        // Environment detection
        results.environment = {
            userAgent: navigator.userAgent,
            platform: navigator.platform,
            cookieEnabled: navigator.cookieEnabled,
            onLine: navigator.onLine,
            language: navigator.language,
            url: window.location.href,
            origin: window.location.origin,
            protocol: window.location.protocol,
            hostname: window.location.hostname,
            isSecureContext: window.isSecureContext || false,
            // Azure-specific detection
            isAzure: window.location.hostname.includes('azurewebsites.net') ||
                    window.location.hostname.includes('azurecontainer.io') ||
                    document.cookie.includes('Azure') ||
                    navigator.userAgent.includes('Azure')
        };

        // IndexedDB availability check
        try {
            results.indexedDB = {
                available: typeof indexedDB !== 'undefined' && indexedDB !== null,
                type: typeof indexedDB,
                isNull: indexedDB === null,
                constructor: indexedDB ? indexedDB.constructor.name : 'N/A'
            };
        } catch (e) {
            results.indexedDB = {
                available: false,
                error: e.message,
                errorName: e.name
            };
            results.errors.push('IndexedDB check failed: ' + e.message);
        }

        // Try to open a test database
        if (results.indexedDB.available) {
            const testDBName = 'ifrc_test_db_' + Date.now();
            const testPromise = new Promise((resolve, reject) => {
                try {
                    const request = indexedDB.open(testDBName, 1);
                    let errorOccurred = false;

                    request.onerror = function(event) {
                        errorOccurred = true;
                        const error = event.target.error || request.error;
                        reject({
                            error: error ? error.message : 'Unknown error',
                            errorName: error ? error.name : 'UnknownError',
                            errorCode: error ? error.code : null,
                            stack: error ? error.stack : null
                        });
                    };

                    request.onsuccess = function(event) {
                        if (!errorOccurred) {
                            const db = event.target.result;
                            try {
                                // Try to create a transaction
                                const tx = db.transaction(['test'], 'readwrite');
                                tx.onerror = function() {
                                    resolve({
                                        canOpen: true,
                                        canCreateTransaction: false,
                                        transactionError: tx.error ? tx.error.message : 'Unknown transaction error'
                                    });
                                };
                                tx.oncomplete = function() {
                                    // Clean up test database
                                    db.close();
                                    indexedDB.deleteDatabase(testDBName).onsuccess = function() {
                                        resolve({
                                            canOpen: true,
                                            canCreateTransaction: true,
                                            canDelete: true
                                        });
                                    };
                                };
                            } catch (txError) {
                                db.close();
                                indexedDB.deleteDatabase(testDBName);
                                resolve({
                                    canOpen: true,
                                    canCreateTransaction: false,
                                    transactionError: txError.message
                                });
                            }
                        }
                    };

                    request.onupgradeneeded = function(event) {
                        try {
                            const db = event.target.result;
                            if (!db.objectStoreNames.contains('test')) {
                                db.createObjectStore('test', { keyPath: 'id' });
                            }
                        } catch (upgradeError) {
                            errorOccurred = true;
                            reject({
                                error: 'Upgrade failed: ' + upgradeError.message,
                                errorName: upgradeError.name
                            });
                        }
                    };

                    request.onblocked = function() {
                        results.warnings = results.warnings || [];
                        results.warnings.push('Database open was blocked (another tab may be using it)');
                    };

                    // Timeout after 5 seconds
                    setTimeout(() => {
                        if (!errorOccurred) {
                            reject({
                                error: 'Database open timeout',
                                errorName: 'TimeoutError'
                            });
                        }
                    }, 5000);

                } catch (openError) {
                    reject({
                        error: 'Failed to open database: ' + openError.message,
                        errorName: openError.name
                    });
                }
            });

            // Wait for test (will be handled below)
            results.indexedDB.test = 'pending';
        }

        // Storage quota check
        if (navigator.storage && navigator.storage.estimate) {
            navigator.storage.estimate().then(function(estimate) {
                results.storage.quota = estimate.quota;
                results.storage.usage = estimate.usage;
                results.storage.usageDetails = estimate.usageDetails;
                results.storage.available = estimate.quota - estimate.usage;
                results.storage.percentUsed = ((estimate.usage / estimate.quota) * 100).toFixed(2) + '%';
            }).catch(function(e) {
                results.storage.error = e.message;
                results.errors.push('Storage estimate failed: ' + e.message);
            });
        } else {
            results.storage.error = 'Storage API not available';
            results.recommendations.push('Browser does not support Storage API for quota checking');
        }

        // Check for private/incognito mode (IndexedDB may be limited)
        if (navigator.storage && navigator.storage.persist) {
            navigator.storage.persist().then(function(persistent) {
                results.storage.isPersistent = persistent;
                if (!persistent) {
                    results.recommendations.push('Storage is not persistent - may be in private/incognito mode or storage disabled');
                }
            }).catch(function(e) {
                results.storage.persistCheckError = e.message;
            });
        }

        // Security context check
        results.security = {
            isSecureContext: window.isSecureContext || false,
            protocol: window.location.protocol,
            isHttps: window.location.protocol === 'https:',
            isLocalhost: window.location.hostname === 'localhost' ||
                         window.location.hostname === '127.0.0.1',
            crossOriginIsolated: window.crossOriginIsolated || false
        };

        // Browser capabilities
        results.browser = {
            localStorage: (function() {
                try {
                    localStorage.setItem('test', 'test');
                    localStorage.removeItem('test');
                    return true;
                } catch (e) {
                    return false;
                }
            })(),
            sessionStorage: (function() {
                try {
                    sessionStorage.setItem('test', 'test');
                    sessionStorage.removeItem('test');
                    return true;
                } catch (e) {
                    return false;
                }
            })(),
            cookies: navigator.cookieEnabled,
            serviceWorkers: 'serviceWorker' in navigator,
            webWorkers: typeof Worker !== 'undefined'
        };

        // Check for CSP that might block IndexedDB
        const metaCSP = document.querySelector('meta[http-equiv="Content-Security-Policy"]');
        if (metaCSP) {
            results.security.csp = metaCSP.getAttribute('content');
            if (results.security.csp && !results.security.csp.includes('unsafe-eval')) {
                results.recommendations.push('CSP may be restricting IndexedDB - check Content Security Policy');
            }
        }

        // Service worker check
        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.getRegistrations().then(function(registrations) {
                results.browser.serviceWorkerRegistrations = registrations.length;
                results.browser.serviceWorkerActive = registrations.length > 0;
            }).catch(function(e) {
                results.browser.serviceWorkerError = e.message;
            });
        }

        // Generate recommendations based on findings
        if (!results.indexedDB.available) {
            results.recommendations.push('IndexedDB is not available in this browser/environment');
        }

        if (!results.security.isSecureContext && !results.security.isLocalhost) {
            results.recommendations.push('Not in a secure context - IndexedDB requires HTTPS or localhost');
        }

        if (!results.browser.localStorage && !results.browser.sessionStorage) {
            results.recommendations.push('All storage APIs are disabled - check browser settings or private mode');
        }

        if (results.environment.isAzure) {
            results.recommendations.push('Running in Azure - check if proxy/CDN is interfering with IndexedDB');
            results.recommendations.push('Verify Azure App Service allows persistent storage');
        }

        // If IndexedDB is available, test it
        if (results.indexedDB.available) {
            const testDBName = 'ifrc_test_db_' + Date.now();
            const testPromise = new Promise((resolve, reject) => {
                try {
                    const request = indexedDB.open(testDBName, 1);
                    let resolved = false;

                    request.onerror = function(event) {
                        if (!resolved) {
                            resolved = true;
                            const error = event.target.error || request.error;
                            reject({
                                error: error ? error.message : 'Unknown error',
                                errorName: error ? error.name : 'UnknownError',
                                errorCode: error ? error.code : null
                            });
                        }
                    };

                    request.onsuccess = function(event) {
                        if (!resolved) {
                            resolved = true;
                            const db = event.target.result;
                            try {
                                const tx = db.transaction(['test'], 'readwrite');
                                tx.onerror = function() {
                                    resolve({
                                        canOpen: true,
                                        canCreateTransaction: false,
                                        transactionError: tx.error ? tx.error.message : 'Unknown'
                                    });
                                };
                                tx.oncomplete = function() {
                                    db.close();
                                    indexedDB.deleteDatabase(testDBName).onsuccess = function() {
                                        resolve({
                                            canOpen: true,
                                            canCreateTransaction: true,
                                            canDelete: true
                                        });
                                    };
                                };
                                // Create test object
                                const store = tx.objectStore('test');
                                store.add({ id: 1, test: 'data' });
                            } catch (txError) {
                                db.close();
                                indexedDB.deleteDatabase(testDBName).catch(() => {});
                                resolve({
                                    canOpen: true,
                                    canCreateTransaction: false,
                                    transactionError: txError.message
                                });
                            }
                        }
                    };

                    request.onupgradeneeded = function(event) {
                        try {
                            const db = event.target.result;
                            if (!db.objectStoreNames.contains('test')) {
                                db.createObjectStore('test', { keyPath: 'id' });
                            }
                        } catch (upgradeError) {
                            if (!resolved) {
                                resolved = true;
                                reject({
                                    error: 'Upgrade failed: ' + upgradeError.message,
                                    errorName: upgradeError.name
                                });
                            }
                        }
                    };

                    request.onblocked = function() {
                        results.warnings = results.warnings || [];
                        results.warnings.push('Database open was blocked');
                    };

                    setTimeout(() => {
                        if (!resolved) {
                            resolved = true;
                            reject({
                                error: 'Database open timeout after 5 seconds',
                                errorName: 'TimeoutError'
                            });
                        }
                    }, 5000);

                } catch (openError) {
                    if (!resolved) {
                        resolved = true;
                        reject({
                            error: 'Failed to open database: ' + openError.message,
                            errorName: openError.name
                        });
                    }
                }
            });

            testPromise.then(function(testResult) {
                results.indexedDB.test = testResult;
                console.log('IndexedDB Diagnostic Results:', results);
                return results;
            }).catch(function(testError) {
                results.indexedDB.test = {
                    failed: true,
                    error: testError.error || testError.message,
                    errorName: testError.errorName || 'UnknownError',
                    errorCode: testError.errorCode
                };
                results.errors.push('IndexedDB test failed: ' + (testError.error || testError.message));
                console.error('IndexedDB Diagnostic - Test Failed:', testError);
                console.log('IndexedDB Diagnostic Results:', results);
                return results;
            });
        } else {
            console.log('IndexedDB Diagnostic Results:', results);
        }

        // Return results immediately (async parts will update)
        return results;
    };

    /**
     * Quick check - returns true/false if IndexedDB is available and working
     */
    window.quickIndexedDBCheck = function() {
        if (typeof indexedDB === 'undefined' || indexedDB === null) {
            return { available: false, reason: 'IndexedDB not defined' };
        }

        if (!window.isSecureContext && window.location.hostname !== 'localhost' &&
            window.location.hostname !== '127.0.0.1') {
            return { available: false, reason: 'Not in secure context (requires HTTPS or localhost)' };
        }

        return { available: true };
    };

    // Auto-run on load if requested via URL parameter
    if (window.location.search.includes('diagnoseIndexedDB=true')) {
        window.addEventListener('load', function() {
            setTimeout(function() {
                console.log('Auto-running IndexedDB diagnostic...');
                window.diagnoseIndexedDB();
            }, 1000);
        });
    }

})();
