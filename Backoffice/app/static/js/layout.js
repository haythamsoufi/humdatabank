// Layout Management JavaScript - SECURITY ENHANCED
//
// SECURITY WARNING: localStorage Security
// =====================================
// All localStorage operations must be validated and sanitized to prevent:
// - XSS attacks through stored data
// - Data corruption through malformed JSON
// - Local storage poisoning attacks
// - Privacy leaks through uncontrolled data storage

// SECURITY: Safe localStorage operations
function safeLocalStorageSet(key, value) {
    if (!key || typeof key !== 'string') {
        console.error('Invalid localStorage key');
        return false;
    }

    // Sanitize key to prevent injection
    const sanitizedKey = key.replace(/[<>"'&]/g, '');
    if (sanitizedKey !== key) {
        console.error('Potentially malicious localStorage key blocked');
        return false;
    }

    try {
        // Validate and sanitize value
        let sanitizedValue = value;
        if (typeof value === 'object') {
            sanitizedValue = JSON.stringify(value);
        } else if (typeof value === 'string') {
            // Basic XSS prevention for string values
            sanitizedValue = value.replace(/[<>"'&]/g, '');
        }

        localStorage.setItem(sanitizedKey, sanitizedValue);
        return true;
    } catch (error) {
        console.error('localStorage set failed:', error);
        return false;
    }
}

function safeLocalStorageGet(key, fallback = null) {
    if (!key || typeof key !== 'string') {
        return fallback;
    }

    // Sanitize key
    const sanitizedKey = key.replace(/[<>"'&]/g, '');
    if (sanitizedKey !== key) {
        console.error('Potentially malicious localStorage key blocked');
        return fallback;
    }

    try {
        const value = localStorage.getItem(sanitizedKey);
        if (value === null) return fallback;

        // Try to parse JSON, but handle both JSON and string values
        try {
            return JSON.parse(value);
        } catch {
            // If not JSON, return as sanitized string
            return value.toString().replace(/[<>"'&]/g, '');
        }
    } catch (error) {
        console.error('localStorage get failed:', error);
        return fallback;
    }
}

// Immediate mobile app detection - runs before DOMContentLoaded
(function() {
    function hideMobileMenuIfApp() {
        const isMobileApp = window.isMobileApp === true ||
                           window.IFRCMobileApp === true ||
                           document.documentElement.getAttribute('data-mobile-app') === 'true' ||
                           (navigator.userAgent && navigator.userAgent.includes('wv'));

        if (isMobileApp) {
            const mobileMenuFAB = document.getElementById('mobileMenuFAB');
            const mobileMenuScrim = document.getElementById('mobileMenuScrim');
            const mobileFloatingMenu = document.getElementById('mobileFloatingMenu');

            if (mobileMenuFAB) {
                mobileMenuFAB.style.display = 'none';
                mobileMenuFAB.style.visibility = 'hidden';
            }
            if (mobileMenuScrim) {
                mobileMenuScrim.style.display = 'none';
                mobileMenuScrim.style.visibility = 'hidden';
            }
            if (mobileFloatingMenu) {
                mobileFloatingMenu.style.display = 'none';
                mobileFloatingMenu.style.visibility = 'hidden';
            }
        }
    }

    // Try immediately
    hideMobileMenuIfApp();

    // Also try when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', hideMobileMenuIfApp);
    } else {
        // DOM already ready
        hideMobileMenuIfApp();
    }

    // Also try after a short delay to catch late-loading elements
    setTimeout(hideMobileMenuIfApp, 100);
    setTimeout(hideMobileMenuIfApp, 500);
})();

document.addEventListener('DOMContentLoaded', function() {
    const adminSidebar = document.getElementById('adminSidebar');
    const mainContent = document.getElementById('mainContent');
    const desktopSidebarToggle = document.getElementById('sidebarToggle');
    const localStorageKey = 'sidebarCollapseState';
    const categoryLocalStorageKey = 'sidebarCategoryState';
    const sidebarScrollPositionKey = 'sidebarScrollPosition';

    // Set RTL direction for Arabic
    const currentLanguage = (document.documentElement.getAttribute('data-language') || document.body.getAttribute('data-language') || 'en');
    if (currentLanguage === 'ar') {
        document.documentElement.setAttribute('dir', 'rtl');
    } else {
        document.documentElement.setAttribute('dir', 'ltr');
    }

    // --- Refined Category Expansion/Collapse Functions ---
    window.expandCategory = (categoryContainer) => {
        const content = categoryContainer.querySelector('.collapsable-content');
        const icon = categoryContainer.querySelector('.collapsable-icon');
        if (!content || !icon) return;

        if (content.classList.contains('hidden-collapse')) {
            content.classList.remove('hidden-collapse');
            icon.classList.add('rotated');
            content.style.maxHeight = content.scrollHeight + 'px';
            setTimeout(() => {
                if (!content.classList.contains('hidden-collapse')) {
                    content.style.maxHeight = '';
                }
            }, 300);
        } else {
            if (!icon.classList.contains('rotated')) {
                icon.classList.add('rotated');
            }
            if (!content.style.maxHeight && content.scrollHeight > 0) {
                content.style.maxHeight = content.scrollHeight + 'px';
                setTimeout(() => {
                    if (!content.classList.contains('hidden-collapse')) {
                        content.style.maxHeight = '';
                    }
                }, 300);
            }
        }
    };

    window.collapseCategory = (categoryContainer) => {
        const content = categoryContainer.querySelector('.collapsable-content');
        const icon = categoryContainer.querySelector('.collapsable-icon');
        if (!content || !icon) return;

        if (!content.classList.contains('hidden-collapse')) {
            content.style.maxHeight = content.scrollHeight + 'px';
            content.offsetHeight;

            content.classList.add('hidden-collapse');
            icon.classList.remove('rotated');
            content.style.maxHeight = '0';
        }
    };

    window.saveCategoryState = (categoryId, isExpanded, storageKeyPrefix) => {
        // SECURITY: Use safe localStorage operations
        const state = safeLocalStorageGet(storageKeyPrefix, {});
        if (typeof state === 'object') {
            // Sanitize categoryId to prevent injection
            const sanitizedCategoryId = categoryId.toString().replace(/[<>"'&]/g, '');
            state[sanitizedCategoryId] = Boolean(isExpanded); // Ensure boolean value
            safeLocalStorageSet(storageKeyPrefix, state);
        } else {
            console.error("Invalid state format from localStorage");
        }
    };

    window.restoreCategoryStates = (navContainer, storageKeyPrefix) => {
        if (!navContainer) return;

        // SECURITY: Use safe localStorage operations
        const state = safeLocalStorageGet(storageKeyPrefix, {});

        navContainer.querySelectorAll('[data-category]').forEach(categoryContainer => {
            const categoryId = categoryContainer.dataset.category;
            const hasSavedState = Object.prototype.hasOwnProperty.call(state, categoryId);
            const isSavedAsExpanded = state[categoryId] === true;
            const hasActiveLinkInside = categoryContainer.querySelector('.sidebar-item-container.active');

            // Default behavior: expand categories unless a saved preference says collapsed.
            if (!hasSavedState || isSavedAsExpanded || hasActiveLinkInside) {
                expandCategory(categoryContainer);
                if (hasActiveLinkInside && !isSavedAsExpanded) {
                    saveCategoryState(categoryId, true, storageKeyPrefix);
                }
            } else {
                collapseCategory(categoryContainer);
            }
        });
    };

    // --- Desktop Sidebar Logic ---
    if (adminSidebar && desktopSidebarToggle) {
        const applyDesktopSidebarState = (isCollapsed) => {
            adminSidebar.classList.toggle('collapsed', isCollapsed);
            mainContent.classList.toggle('content-with-collapsed-sidebar', isCollapsed);
            mainContent.classList.toggle('content-with-sidebar', !isCollapsed);
            desktopSidebarToggle.replaceChildren();
            const icon = document.createElement('i');
            icon.className = isCollapsed ? 'fas fa-bars fa-fw h-6 w-6' : 'fas fa-times fa-fw h-6 w-6';
            desktopSidebarToggle.appendChild(icon);
            desktopSidebarToggle.setAttribute('aria-expanded', !isCollapsed);

            // Always restore category states - the CSS will handle visibility in collapsed mode
            restoreCategoryStates(document.getElementById('adminSidebarNav'), categoryLocalStorageKey + '_desktop');
        };

        desktopSidebarToggle.addEventListener('click', () => {
            const newState = !adminSidebar.classList.contains('collapsed');
            // SECURITY: Use safe localStorage operations (store as boolean)
            safeLocalStorageSet(localStorageKey, newState);
            applyDesktopSidebarState(newState);
        });

        // SECURITY: Use safe localStorage operations
        const savedSidebarStateRaw = safeLocalStorageGet(localStorageKey, false);
        if (window.innerWidth > 768) {
            // Remove the initial class and apply proper state
            document.documentElement.classList.remove('sidebar-initially-collapsed');
            const isCollapsed = savedSidebarStateRaw === true || savedSidebarStateRaw === 'true';
            applyDesktopSidebarState(isCollapsed);
        }
    }

    // --- Active Link Highlighting ---
    const setActiveLink = (navContainer) => {
        if (!navContainer) return;
        const currentPath = (window.location.pathname.replace(/\/$/, "") || "/");
        const navLinks = navContainer.querySelectorAll('a.sidebar-item-container');
        let bestMatchLink = null;
        let longestMatchLength = -1;

        navLinks.forEach(link => {
            link.classList.remove('active');
            link.removeAttribute('aria-current');
            const linkUrl = new URL(link.href, window.location.origin);
            const linkPath = (linkUrl.pathname.replace(/\/$/, "") || "/");
            let isMatch = currentPath === linkPath || (linkPath !== "/" && currentPath.startsWith(linkPath) && (currentPath.length === linkPath.length || currentPath.charAt(linkPath.length) === '/'));
            if (isMatch && linkPath.length > longestMatchLength) {
                longestMatchLength = linkPath.length;
                bestMatchLink = link;
            }
        });

        if (bestMatchLink) {
            bestMatchLink.classList.add('active');
            bestMatchLink.setAttribute('aria-current', 'page');
            let parentCollapsableContent = bestMatchLink.closest('.collapsable-content');
            if (parentCollapsableContent) {
                const categoryContainer = parentCollapsableContent.parentElement;
                if (categoryContainer && categoryContainer.dataset.category) {
                    expandCategory(categoryContainer);
                    saveCategoryState(categoryContainer.dataset.category, true, navContainer.id === 'adminSidebarNav' ? categoryLocalStorageKey + '_desktop' : categoryLocalStorageKey + '_mobile');
                }
            }
        }
    };

    // --- Initialize Collapsable Categories ---
    const initCollapsableCategories = (navContainer, storageKeyPrefix) => {
        if (!navContainer) return;
        const collapsableTitles = navContainer.querySelectorAll('.collapsable-category-title');

        collapsableTitles.forEach(title => {
            title.addEventListener('click', function() {
                if (navContainer.id === 'adminSidebarNav' && adminSidebar && adminSidebar.classList.contains('collapsed') && window.innerWidth > 768) {
                    return;
                }
                const categoryContainer = this.parentElement;
                const content = this.nextElementSibling;
                if (categoryContainer && categoryContainer.dataset.category && content) {
                    const categoryId = categoryContainer.dataset.category;
                    const isCurrentlyExpanded = !content.classList.contains('hidden-collapse');
                    if (isCurrentlyExpanded) {
                        collapseCategory(categoryContainer);
                        saveCategoryState(categoryId, false, storageKeyPrefix);
                    } else {
                        expandCategory(categoryContainer);
                        saveCategoryState(categoryId, true, storageKeyPrefix);
                    }
                }
            });
        });
        restoreCategoryStates(navContainer, storageKeyPrefix);
    };

    setActiveLink(document.getElementById('adminSidebarNav'));
    setActiveLink(document.getElementById('mobileFloatingMenuNav'));

    initCollapsableCategories(document.getElementById('adminSidebarNav'), categoryLocalStorageKey + '_desktop');
    initCollapsableCategories(document.getElementById('mobileFloatingMenuNav'), categoryLocalStorageKey + '_mobile');

    // --- Tooltip Logic for Collapsed Sidebar ---
    if (adminSidebar) {
        let tooltipElem;

        const createTooltip = () => {
            // Check if tooltip element already exists
            if (!document.getElementById('sidebar-tooltip')) {
                const tooltip = document.createElement('div');
                tooltip.id = 'sidebar-tooltip';
                document.body.appendChild(tooltip);
                tooltipElem = tooltip;
            } else {
                tooltipElem = document.getElementById('sidebar-tooltip');
            }
        };
        createTooltip(); // Create the tooltip element on DOM load

        // Migrate native title attributes to custom attributes to prevent browser tooltips
        const migrateSidebarTitles = () => {
            adminSidebar.querySelectorAll('a.sidebar-item-container[title]').forEach(link => {
                const nativeTitle = link.getAttribute('title');
                if (nativeTitle) {
                    // Preserve for accessibility and our custom tooltip
                    link.setAttribute('data-tooltip', nativeTitle);
                    if (!link.getAttribute('aria-label')) {
                        link.setAttribute('aria-label', nativeTitle);
                    }
                    // Remove native tooltip
                    link.removeAttribute('title');
                }
            });
        };
        migrateSidebarTitles();

        const showTooltip = (e) => {
            // Only show tooltips if the sidebar is collapsed
            if (!adminSidebar.classList.contains('collapsed') && !document.documentElement.classList.contains('sidebar-initially-collapsed')) return;

            const targetLink = e.currentTarget;
            const tooltipText = targetLink.getAttribute('data-tooltip') || targetLink.getAttribute('aria-label');

            if (tooltipText && tooltipElem) {
                tooltipElem.textContent = tooltipText;
                const rect = targetLink.getBoundingClientRect();

                // Position tooltip to be vertically centered with the hovered icon
                tooltipElem.style.top = `${rect.top + rect.height / 2}px`;

                // Adjust positioning for RTL
                if (document.documentElement.getAttribute('dir') === 'rtl') {
                    tooltipElem.style.right = '85px';
                    tooltipElem.style.left = 'auto';
                } else {
                    tooltipElem.style.left = '85px';
                    tooltipElem.style.right = 'auto';
                }

                tooltipElem.classList.add('visible');
            }
        };

        const hideTooltip = () => {
            if (tooltipElem) {
                tooltipElem.classList.remove('visible');
            }
        };

        // Add event listeners to all sidebar links
        adminSidebar.querySelectorAll('a.sidebar-item-container').forEach(link => {
            link.addEventListener('mouseenter', showTooltip);
            link.addEventListener('mouseleave', hideTooltip);
        });
    }

    // --- Mobile FAB and Floating Menu Logic ---
    const mobileMenuFAB = document.getElementById('mobileMenuFAB');
    const mobileMenuFABIcon = document.getElementById('mobileMenuFABIcon');
    const mobileFloatingMenu = document.getElementById('mobileFloatingMenu');
    const mobileMenuScrim = document.getElementById('mobileMenuScrim');
    const mobileMenuCloseButton = document.getElementById('mobileMenuCloseButton');

    // Detect if we're in the Flutter mobile app
    const isMobileApp = window.isMobileApp === true ||
                       window.IFRCMobileApp === true ||
                       document.documentElement.getAttribute('data-mobile-app') === 'true' ||
                       (navigator.userAgent && navigator.userAgent.includes('wv')); // Android WebView indicator

    // Hide mobile menu button if in mobile app
    if (isMobileApp && mobileMenuFAB) {
        mobileMenuFAB.style.display = 'none';
        // Also hide the scrim and menu if they exist
        if (mobileMenuScrim) mobileMenuScrim.style.display = 'none';
        if (mobileFloatingMenu) mobileFloatingMenu.style.display = 'none';
    }

    if (mobileMenuFAB && mobileFloatingMenu && mobileMenuScrim && mobileMenuCloseButton && !isMobileApp) {
        const toggleMobileMenu = (forceOpen) => {
            const isOpen = typeof forceOpen === 'boolean' ? forceOpen : !mobileFloatingMenu.classList.contains('menu-open');
            mobileFloatingMenu.classList.toggle('menu-open', isOpen);
            mobileMenuScrim.classList.toggle('scrim-visible', isOpen);
            mobileMenuFAB.classList.toggle('fab-active', isOpen);
            if(mobileMenuFAB) mobileMenuFAB.setAttribute('aria-expanded', isOpen.toString());

            if (isOpen) {
                if(mobileMenuFABIcon) {
                    mobileMenuFABIcon.classList.remove('fa-bars');
                    mobileMenuFABIcon.classList.add('fa-times');
                }
                setActiveLink(document.getElementById('mobileFloatingMenuNav'));
                restoreCategoryStates(document.getElementById('mobileFloatingMenuNav'), categoryLocalStorageKey + '_mobile');
            } else {
                if(mobileMenuFABIcon) {
                    mobileMenuFABIcon.classList.remove('fa-times');
                    mobileMenuFABIcon.classList.add('fa-bars');
                }
            }
        };
        mobileMenuFAB.addEventListener('click', () => toggleMobileMenu());
        mobileMenuScrim.addEventListener('click', () => toggleMobileMenu(false));
        mobileMenuCloseButton.addEventListener('click', () => toggleMobileMenu(false));
        mobileFloatingMenu.querySelectorAll('a.sidebar-item-container').forEach(link => {
            link.addEventListener('click', () => {
                saveSidebarScrollPosition();
                setTimeout(() => toggleMobileMenu(false), 100);
            });
        });
    }

    // --- Sidebar Scroll Position Management ---
    const saveSidebarScrollPosition = () => {
        if (adminSidebar && window.innerWidth > 768) {
            // SECURITY: Use safe localStorage operations with validation
            const scrollTop = Math.max(0, Math.min(adminSidebar.scrollTop, 10000)); // Limit scroll values
            safeLocalStorageSet(sidebarScrollPositionKey + '_desktop', scrollTop.toString());
        }
        const mobileMenuNav = document.getElementById('mobileFloatingMenuNav');
        if (mobileMenuNav && window.innerWidth <= 768) {
            // SECURITY: Use safe localStorage operations with validation
            const scrollTop = Math.max(0, Math.min(mobileMenuNav.scrollTop, 10000)); // Limit scroll values
            safeLocalStorageSet(sidebarScrollPositionKey + '_mobile', scrollTop.toString());
        }
    };

    const restoreSidebarScrollPosition = () => {
        if (adminSidebar && window.innerWidth > 768) {
            // SECURITY: Use safe localStorage operations with validation
            const savedScrollPosition = safeLocalStorageGet(sidebarScrollPositionKey + '_desktop', '0');
            const scrollValue = parseInt(savedScrollPosition, 10);
            if (!isNaN(scrollValue) && scrollValue >= 0 && scrollValue <= 10000) {
                adminSidebar.scrollTop = scrollValue;
            }
        }
        const mobileMenuNav = document.getElementById('mobileFloatingMenuNav');
        if (mobileMenuNav && window.innerWidth <= 768) {
            // SECURITY: Use safe localStorage operations with validation
            const savedScrollPosition = safeLocalStorageGet(sidebarScrollPositionKey + '_mobile', '0');
            const scrollValue = parseInt(savedScrollPosition, 10);
            if (!isNaN(scrollValue) && scrollValue >= 0 && scrollValue <= 10000) {
                mobileMenuNav.scrollTop = scrollValue;
            }
        }
    };

    // Add scroll event listeners to save position
    if (adminSidebar) {
        let scrollTimeout;
        adminSidebar.addEventListener('scroll', () => {
            clearTimeout(scrollTimeout);
            scrollTimeout = setTimeout(saveSidebarScrollPosition, 150);
        });
    }

    const mobileMenuNav = document.getElementById('mobileFloatingMenuNav');
    if (mobileMenuNav) {
        let mobileScrollTimeout;
        mobileMenuNav.addEventListener('scroll', () => {
            clearTimeout(mobileScrollTimeout);
            mobileScrollTimeout = setTimeout(saveSidebarScrollPosition, 150);
        });
    }

    // Save scroll position when sidebar links are clicked (desktop)
    if (adminSidebar) {
        adminSidebar.querySelectorAll('a.sidebar-item-container').forEach(link => {
            link.addEventListener('click', saveSidebarScrollPosition);
        });
    }

    // Save scroll position before page unload
    window.addEventListener('beforeunload', saveSidebarScrollPosition);

    // Restore scroll position after a short delay to ensure DOM is ready
    setTimeout(restoreSidebarScrollPosition, 100);

    // --- Global Select2 Initialization ---
    if (typeof $ !== 'undefined' && $.fn.select2) {
        $('.select2-enable').select2({ width: '100%', theme: "default" });
    }

    // --- Handle Resize ---
    window.addEventListener('resize', () => {
        // Check again for mobile app in case it wasn't detected initially
        const isMobileAppCheck = window.isMobileApp === true ||
                                 window.IFRCMobileApp === true ||
                                 document.documentElement.getAttribute('data-mobile-app') === 'true' ||
                                 (navigator.userAgent && navigator.userAgent.includes('wv'));

        if (window.innerWidth > 768 && !isMobileAppCheck) {
            if (mobileFloatingMenu && mobileFloatingMenu.classList.contains('menu-open')) {
                mobileFloatingMenu.classList.remove('menu-open');
                if (mobileMenuScrim) mobileMenuScrim.classList.remove('scrim-visible');
                if(mobileMenuFAB) mobileMenuFAB.classList.remove('fab-active');
                if(mobileMenuFABIcon) { mobileMenuFABIcon.classList.remove('fa-times'); mobileMenuFABIcon.classList.add('fa-bars');}
                if(mobileMenuFAB) mobileMenuFAB.setAttribute('aria-expanded', 'false');
            }
            if (adminSidebar && desktopSidebarToggle) {
                adminSidebar.style.transform = '';
                adminSidebar.style.visibility = '';
                // SECURITY: Use safe localStorage operations
                const savedStateRaw = safeLocalStorageGet(localStorageKey, false);
                const savedState = savedStateRaw === true || savedStateRaw === 'true';
                if (adminSidebar.classList.contains('collapsed') !== savedState) {
                     adminSidebar.classList.toggle('collapsed', savedState);
                     mainContent.classList.toggle('content-with-collapsed-sidebar', savedState);
                     mainContent.classList.toggle('content-with-sidebar', !savedState);
                     desktopSidebarToggle.replaceChildren();
                     const icon = document.createElement('i');
                     icon.className = savedState ? 'fas fa-bars fa-fw h-6 w-6' : 'fas fa-times fa-fw h-6 w-6';
                     desktopSidebarToggle.appendChild(icon);
                     desktopSidebarToggle.setAttribute('aria-expanded', !savedState);
                }
                // Always restore category states - CSS handles visibility in collapsed mode
                restoreCategoryStates(document.getElementById('adminSidebarNav'), categoryLocalStorageKey + '_desktop');
            }
        }

        // Adjust FAB position on resize to handle mobile/desktop transitions
        const aiChatbotFAB = document.getElementById('aiChatbotFAB');
        if (aiChatbotFAB && typeof adjustFABPosition === 'function') {
            adjustFABPosition();
        }
    });
});
