import { debugLog } from './debug.js';

let mobileNavToggleButton;
let mobileNavCloseButton;
let sectionNavigationSidebar;
let mobileNavOverlay;
let sectionLinks;

export function initMobileNav() {
    // Initialize DOM elements
    mobileNavToggleButton = document.getElementById('mobile-nav-toggle-button');
    mobileNavCloseButton = document.getElementById('mobile-nav-close-button');
    sectionNavigationSidebar = document.getElementById('section-navigation-sidebar');
    mobileNavOverlay = document.getElementById('mobile-nav-overlay');
    sectionLinks = sectionNavigationSidebar ? sectionNavigationSidebar.querySelectorAll('a.section-link') : [];

    // Set up event listeners
    if (mobileNavToggleButton) mobileNavToggleButton.addEventListener('click', openMobileNav);
    if (mobileNavCloseButton) mobileNavCloseButton.addEventListener('click', closeMobileNav);
    if (mobileNavOverlay) mobileNavOverlay.addEventListener('click', closeMobileNav);

    setupSectionLinkListeners();
}

function openMobileNav() {
    if (sectionNavigationSidebar && mobileNavOverlay) {
        sectionNavigationSidebar.classList.remove('-translate-x-full');
        sectionNavigationSidebar.classList.add('translate-x-0');
        mobileNavOverlay.classList.remove('hidden');
        document.body.classList.add('overflow-hidden');
        debugLog('Mobile nav opened');
    }
}

function closeMobileNav() {
    if (sectionNavigationSidebar && mobileNavOverlay) {
        sectionNavigationSidebar.classList.add('-translate-x-full');
        sectionNavigationSidebar.classList.remove('translate-x-0');
        mobileNavOverlay.classList.add('hidden');
        document.body.classList.remove('overflow-hidden');
        debugLog('Mobile nav closed');
    }
}

function setupSectionLinkListeners() {
    if (sectionLinks) {
        sectionLinks.forEach(link => {
            link.addEventListener('click', () => {
                if (mobileNavToggleButton &&
                    window.getComputedStyle(mobileNavToggleButton).display !== 'none' &&
                    sectionNavigationSidebar &&
                    sectionNavigationSidebar.classList.contains('translate-x-0')) {
                    setTimeout(closeMobileNav, 100);
                }
            });
        });
    }
}
