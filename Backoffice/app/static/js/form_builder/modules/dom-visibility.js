/**
 * Shared visibility helpers for the form builder modal and AJAX submit layer.
 */

/**
 * Return true when *el* is not visible/interactive (hidden container, display:none, etc.).
 *
 * @param {Element|null|undefined} el
 * @returns {boolean}
 */
export function isActuallyHidden(el) {
    if (!el) return true;
    try {
        if (el.closest && el.closest('.hidden')) return true;
        const inlineDisplay = el.style && el.style.display;
        const inlineVisibility = el.style && el.style.visibility;
        if (inlineDisplay === 'none' || inlineVisibility === 'hidden') return true;
        if (el.offsetParent === null) return true;
        const style = window.getComputedStyle(el);
        return style.display === 'none' || style.visibility === 'hidden';
    } catch (_e) {
        return false;
    }
}
