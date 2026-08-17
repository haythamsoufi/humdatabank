/**
 * jsdom implements window.scrollTo / Element.scrollTo as "not implemented"
 * stubs that print to stderr. Entry-form validation and pagination call them
 * after submit / page change; replace with no-ops for the whole suite.
 */
import { beforeEach } from 'vitest';

function stubUnimplementedScroll() {
    if (typeof window !== 'undefined') {
        window.scrollTo = () => {};
        window.scroll = () => {};
    }
    if (typeof Element !== 'undefined' && Element.prototype) {
        Element.prototype.scrollTo = function scrollTo() {};
        Element.prototype.scroll = function scroll() {};
    }
}

stubUnimplementedScroll();
beforeEach(stubUnimplementedScroll);
