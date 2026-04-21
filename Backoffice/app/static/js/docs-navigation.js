/**
 * Documentation navigation functionality
 * Handles AJAX navigation, category toggling, and sidebar interactions
 */

(function() {
    'use strict';

    function normalizeUrl(url) {
        try {
            const u = new URL(url, window.location.origin);
            return u.pathname + u.search;
        } catch (e) {
            return url;
        }
    }

    /**
     * Return the docs base path (e.g. "/help/docs" or "/admin/docs") from the current page URL.
     * Used to detect in-content links that should be loaded via AJAX instead of full reload.
     */
    function getDocsBasePath() {
        const path = window.location.pathname || '';
        if (path.indexOf('/help/docs') === 0) return '/help/docs';
        if (path.indexOf('/admin/docs') === 0) return '/admin/docs';
        return '';
    }

    /**
     * Return true if the given URL is a same-origin docs link that should use client-side navigation.
     */
    function isInternalDocsLink(href) {
        if (!href || typeof href !== 'string') return false;
        const base = getDocsBasePath();
        if (!base) return false;
        try {
            const u = new URL(href, window.location.origin);
            if (u.origin !== window.location.origin) return false;
            const path = u.pathname || '';
            if (path === base || path === base + '/') return true;
            if (path.indexOf(base + '/') === 0) return true;
            return false;
        } catch (e) {
            return false;
        }
    }

    function toggleCategory(categoryName) {
        const items = document.getElementById('category-' + categoryName);
        const icon = document.getElementById('icon-' + categoryName);

        if (!items || !icon) {
            console.warn('Category elements not found:', categoryName);
            return;
        }

        const isExpanded = items.classList.contains('expanded');

        if (isExpanded) {
            items.classList.remove('expanded');
            icon.classList.remove('expanded');
        } else {
            items.classList.add('expanded');
            icon.classList.add('expanded');
        }
    }

    function expandAllCategories() {
        const categories = document.querySelectorAll('.nav-category-items');
        const icons = document.querySelectorAll('.nav-category-icon');

        categories.forEach(function(items) {
            items.classList.add('expanded');
        });

        icons.forEach(function(icon) {
            icon.classList.add('expanded');
        });
    }

    function collapseAllCategories() {
        const categories = document.querySelectorAll('.nav-category-items');
        const icons = document.querySelectorAll('.nav-category-icon');

        categories.forEach(function(items) {
            items.classList.remove('expanded');
        });

        icons.forEach(function(icon) {
            icon.classList.remove('expanded');
        });
    }

    function setLoading(isLoading) {
        const contentRoot = document.querySelector('.docs-content-inner');
        if (!contentRoot) return;
        contentRoot.setAttribute('aria-busy', isLoading ? 'true' : 'false');
        contentRoot.style.opacity = isLoading ? '0.6' : '';
        contentRoot.style.pointerEvents = isLoading ? 'none' : '';
    }

    function setActiveNavByUrl(url) {
        const target = normalizeUrl(url);
        const navItems = document.querySelectorAll('.nav-item');
        let activeItem = null;

        navItems.forEach(function(item) {
            const href = item.getAttribute('href') || '';
            const isActive = normalizeUrl(href) === target;

            item.classList.toggle('nav-item-active', isActive);
            item.classList.toggle('nav-item-inactive', !isActive);

            if (isActive) activeItem = item;
        });

        return activeItem;
    }

    function ensureCategoryExpandedForItem(item) {
        if (!item) return;

        const itemsContainer = item.closest('.nav-category-items');
        if (itemsContainer) itemsContainer.classList.add('expanded');

        const category = item.closest('.nav-category');
        if (!category) return;

        const icon = category.querySelector('.nav-category-icon');
        if (icon) icon.classList.add('expanded');
    }

    let currentRequestId = 0;
    async function navigateTo(url, options) {
        options = options || {};
        const requestId = ++currentRequestId;

        const titleEl = document.querySelector('.docs-content-title');
        const proseEl = document.querySelector('.docs-prose');
        const contentRoot = document.querySelector('.docs-content-inner');

        if (!titleEl || !proseEl || !contentRoot) {
            window.location.href = url;
            return;
        }

        setLoading(true);

        try {
            const fn = (window.getFetch && window.getFetch()) || fetch;
            const response = await fn(url, {
                method: 'GET',
                credentials: 'same-origin',
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            });

            if (!response.ok) {
                throw (window.httpErrorSync && window.httpErrorSync(response)) || new Error('HTTP ' + response.status);
            }

            const html = await response.text();
            if (requestId !== currentRequestId) return;

            const parsed = new DOMParser().parseFromString(html, 'text/html');
            const newTitleEl = parsed.querySelector('.docs-content-title');
            const newProseEl = parsed.querySelector('.docs-prose');
            const newHeaderActions = parsed.querySelector('#docs-header-actions');

            if (!newTitleEl || !newProseEl) {
                throw new Error('Unexpected response shape');
            }

            titleEl.textContent = newTitleEl.textContent || '';
            // Adopt nodes from the same-origin server response via document.adoptNode so
            // scripts are not re-executed and the content stays within the trusted origin.
            proseEl.textContent = '';
            Array.from(newProseEl.childNodes).forEach(n => proseEl.appendChild(document.adoptNode(n)));
            if (parsed.title) document.title = parsed.title;

            // Render Mermaid diagrams after content update
            if (window.renderMermaidDiagrams) {
                window.renderMermaidDiagrams(proseEl);
            }

            // Update header actions (tour button) to match the new page
            const headerActions = document.getElementById('docs-header-actions');
            if (headerActions) {
                headerActions.textContent = '';
                if (newHeaderActions) {
                    Array.from(newHeaderActions.childNodes).forEach(n => headerActions.appendChild(document.adoptNode(n)));
                }
            }

            const activeItem = setActiveNavByUrl(url);
            ensureCategoryExpandedForItem(activeItem);

            if (options.pushState) {
                history.pushState({ docsUrl: url }, '', url);
            }

            if (activeItem) {
                setTimeout(function() {
                    activeItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }, 50);
            }

            if (options.scrollTop !== false) {
                contentRoot.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }

            // Scroll to hash in the new content if present
            try {
                const parsedUrl = new URL(url, window.location.origin);
                if (parsedUrl.hash) {
                    const id = parsedUrl.hash.slice(1);
                    const anchor = id ? document.getElementById(id) : null;
                    if (anchor) {
                        setTimeout(function() {
                            anchor.scrollIntoView({ behavior: 'smooth', block: 'start' });
                        }, 100);
                    }
                }
            } catch (err) {
                // ignore
            }
        } catch (err) {
            console.warn('Docs navigation failed, falling back to full load:', err);
            window.location.href = url;
        } finally {
            if (requestId === currentRequestId) setLoading(false);
        }
    }

    // Initialize when DOM is ready
    function init() {
        // Use event delegation for category headers - attach to sidebar container
        const sidebar = document.querySelector('.docs-sidebar-inner');
        if (!sidebar) {
            console.warn('Sidebar not found');
            return;
        }

        // Click handler
        sidebar.addEventListener('click', function(e) {
            const header = e.target.closest('.nav-category-header');
            if (header) {
                e.preventDefault();
                e.stopPropagation();
                const categoryName = header.getAttribute('data-category');
                if (categoryName) {
                    toggleCategory(categoryName);
                }
            }
        });

        // Keyboard handler
        sidebar.addEventListener('keydown', function(e) {
            const header = e.target.closest('.nav-category-header');
            if (header && (e.key === 'Enter' || e.key === ' ')) {
                e.preventDefault();
                e.stopPropagation();
                const categoryName = header.getAttribute('data-category');
                if (categoryName) {
                    toggleCategory(categoryName);
                }
            }
        });

        // Intercept navigation item clicks to avoid full page reload
        const nav = document.getElementById('docs-nav');
        if (nav) {
            nav.addEventListener('click', function(e) {
                const link = e.target.closest('a.nav-item');
                if (!link) return;

                // Allow new-tab / modified clicks
                if (e.defaultPrevented) return;
                if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
                if (typeof e.button === 'number' && e.button !== 0) return;
                if (link.target && link.target !== '_self') return;

                const href = link.getAttribute('href');
                if (!href) return;

                e.preventDefault();
                e.stopPropagation();
                navigateTo(href, { pushState: true });
            });
        }

        // Intercept in-content doc links (links inside .docs-prose) so navigation never reloads the page
        const contentSection = document.querySelector('.docs-content');
        if (contentSection) {
            contentSection.addEventListener('click', function(e) {
                const link = e.target.closest('a[href]');
                if (!link) return;

                if (e.defaultPrevented) return;
                if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
                if (typeof e.button === 'number' && e.button !== 0) return;
                if (link.target && link.target !== '_self') return;

                const href = link.getAttribute('href');
                if (!href) return;

                // Only intercept same-origin docs links (not anchors, not external)
                if (href.startsWith('#')) return;
                if (!isInternalDocsLink(href)) return;

                e.preventDefault();
                e.stopPropagation();
                navigateTo(href, { pushState: true });
            });
        }

        // Ensure history state exists for back/forward navigation
        try {
            history.replaceState({ docsUrl: window.location.href }, '', window.location.href);
        } catch (e) {
            // no-op
        }

        window.addEventListener('popstate', function(e) {
            const url = (e.state && e.state.docsUrl) ? e.state.docsUrl : window.location.href;
            navigateTo(url, { pushState: false, scrollTop: false });
        });

        // Expand all categories by default
        const allCategories = document.querySelectorAll('.nav-category-items');
        const allIcons = document.querySelectorAll('.nav-category-icon');
        allCategories.forEach(function(items) {
            items.classList.add('expanded');
        });
        allIcons.forEach(function(icon) {
            icon.classList.add('expanded');
        });

        // Expand category containing current page
        // Note: This requires server-side data, so it's handled in the template
        // The template will call this function with the active category name

        // Scroll active item into view
        const activeItem = document.querySelector('.nav-item-active');
        if (activeItem) {
            setTimeout(function() {
                activeItem.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }, 100);
        }

        // Expand/Collapse all buttons
        const expandAllBtn = document.getElementById('expand-all-btn');
        const collapseAllBtn = document.getElementById('collapse-all-btn');

        if (expandAllBtn) {
            expandAllBtn.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                expandAllCategories();
            });
        }

        if (collapseAllBtn) {
            collapseAllBtn.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                collapseAllCategories();
            });
        }
    }

    // Run when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        // DOM already loaded, run immediately
        setTimeout(init, 0);
    }

    // Export functions for template use
    window.DocsNavigation = {
        toggleCategory: toggleCategory,
        expandAllCategories: expandAllCategories,
        collapseAllCategories: collapseAllCategories
    };
})();
