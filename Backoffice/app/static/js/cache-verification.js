/**
 * Static File Cache Verification Script
 *
 * Copy this entire file content and paste into browser console to verify caching.
 * Or include this file in your page for debugging.
 */

(function() {
    'use strict';

    // Only run if explicitly called or in debug mode
    if (typeof window === 'undefined') return;

    window.verifyStaticFileCache = async function(options = {}) {
        const {
            files = [
                'css/output.css',
                'css/forms.css',
                'css/layout.css',
                'js/layout.js',
                'js/csrf.js',
                'js/chatbot.js',
                'js/components.js',
                'js/flash-messages.js'
            ],
            verbose = true,
            checkServiceWorker = true
        } = options;

        console.log('='.repeat(70));
        console.log('Static File Cache Verification');
        console.log('='.repeat(70));
        console.log('');

        const baseUrl = window.location.origin;
        const staticVersion = window.ASSET_VERSION || document.documentElement.dataset.staticVersion || 'v1';

        if (verbose) {
            console.log(`Base URL: ${baseUrl}`);
            console.log(`Static Version: ${staticVersion}`);
            console.log('');
        }

        const results = [];
        let successCount = 0;
        let versionedCount = 0;
        let longCacheCount = 0;
        let shortCacheCount = 0;

        // Check each file
        for (const file of files) {
            const versionedUrl = `${baseUrl}/static/${file}?v=${staticVersion}`;

            try {
                const fn = (window.getFetch && window.getFetch()) || fetch;
                const response = await fn(versionedUrl, {
                    method: 'HEAD',
                    cache: 'default'
                });

                const cacheControl = response.headers.get('Cache-Control') || 'Not set';
                const etag = response.headers.get('ETag') || 'Not set';
                const status = response.status;

                const isVersioned = versionedUrl.includes('?v=');
                const hasLongCache = cacheControl.includes('max-age=31536000') || cacheControl.includes('immutable');
                const hasShortCache = cacheControl.includes('max-age=3600') && !hasLongCache;

                const result = {
                    file,
                    url: versionedUrl,
                    status,
                    cacheControl,
                    etag: etag.length > 30 ? etag.substring(0, 30) + '...' : etag,
                    isVersioned,
                    hasLongCache,
                    hasShortCache,
                    cached: response.headers.get('X-Cache') || 'Unknown'
                };

                results.push(result);

                if (status === 200) successCount++;
                if (isVersioned) versionedCount++;
                if (hasLongCache) longCacheCount++;
                if (hasShortCache) shortCacheCount++;

                if (verbose) {
                    const statusIcon = status === 200 ? '✓' : '✗';
                    const cacheIcon = hasLongCache ? '✓' : hasShortCache ? '⚠' : '✗';

                    console.log(`${statusIcon} ${file} ${cacheIcon}`);
                    console.log(`   URL: ${versionedUrl}`);
                    console.log(`   Status: ${status}`);
                    console.log(`   Cache-Control: ${cacheControl}`);
                    if (verbose) {
                        console.log(`   ETag: ${etag.length > 50 ? etag.substring(0, 50) + '...' : etag}`);
                    }
                    console.log(`   Versioned: ${isVersioned ? 'Yes' : 'No'}`);
                    console.log(`   Cache: ${hasLongCache ? 'Long (1 year)' : hasShortCache ? 'Short (1 hour)' : 'Not set'}`);
                    console.log('');
                }

            } catch (error) {
                console.error(`✗ ${file}: Error - ${error.message}`);
                results.push({
                    file,
                    error: error.message
                });
                if (verbose) console.log('');
            }
        }

        // Check Service Worker cache if requested
        if (checkServiceWorker && 'serviceWorker' in navigator) {
            try {
                const registrations = await navigator.serviceWorker.getRegistrations();
                if (registrations.length > 0 && verbose) {
                    console.log('Service Worker Status:');
                    for (const registration of registrations) {
                        console.log(`  Active: ${registration.active ? 'Yes' : 'No'}`);
                        if (registration.active) {
                            const cacheNames = await caches.keys();
                            console.log(`  Caches: ${cacheNames.join(', ')}`);
                        }
                    }
                    console.log('');
                }
            } catch (error) {
                if (verbose) console.log(`Service Worker check failed: ${error.message}\n`);
            }
        }

        // Summary
        console.log('='.repeat(70));
        console.log('Summary');
        console.log('='.repeat(70));
        console.log(`Total files checked: ${files.length}`);
        console.log(`✓ Successful requests: ${successCount}/${files.length}`);
        console.log(`✓ Versioned URLs: ${versionedCount}/${files.length}`);
        console.log(`✓ Long cache (1 year): ${longCacheCount}/${files.length}`);
        console.log(`⚠ Short cache (1 hour): ${shortCacheCount}/${files.length}`);
        console.log('');

        if (longCacheCount === files.length) {
            console.log('🎉 All files are properly cached with long cache times!');
        } else if (versionedCount === files.length && longCacheCount > 0) {
            console.log('✅ Most files are properly cached. Check any files with short cache.');
        } else {
            console.log('⚠️ Some files may not be properly cached. Review the results above.');
        }

        return {
            total: files.length,
            successful: successCount,
            versioned: versionedCount,
            longCache: longCacheCount,
            shortCache: shortCacheCount,
            results: results
        };
    };

    // Auto-run in debug mode if URL has ?debug-cache parameter
    if (window.location.search.includes('debug-cache')) {
        window.verifyStaticFileCache().then(result => {
            console.log('Verification complete. Results:', result);
        });
    }

    // Export for manual use
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = window.verifyStaticFileCache;
    }
})();
