/** Stable sessionStorage keys for paginated entry-form page/section restore. */

export function getStableFormStorageBaseUrl() {
    const form = document.getElementById('focalDataEntryForm');
    if (form && form.action) {
        return String(form.action).split('#')[0];
    }
    const url = new URL(window.location.href);
    url.hash = '';
    url.searchParams.delete('page');
    return `${url.origin}${url.pathname}${url.search}`;
}

export function buildFormPageStorageKey(baseUrl) {
    return `form_page_${btoa(baseUrl).replace(/[^a-zA-Z0-9]/g, '')}`;
}

export function getFormPageStorageKey() {
    return buildFormPageStorageKey(getStableFormStorageBaseUrl());
}

export function isPageReload() {
    try {
        const nav = performance.getEntriesByType('navigation')[0];
        return nav?.type === 'reload';
    } catch (e) {
        return false;
    }
}
