/**
 * jsdom implements window.scrollTo / Element.scrollTo as "not implemented"
 * stubs that print to stderr. Entry-form validation and pagination call them
 * after submit / page change; replace with no-ops for the whole suite.
 *
 * jsdom also omits CompressionStream, which form-builder saves use to keep
 * large matrix bodies under the WAF combined-argument limit.
 */
import { beforeEach } from 'vitest';
import { CompressionStream, DecompressionStream } from 'node:stream/web';

if (typeof globalThis.CompressionStream !== 'function') {
    globalThis.CompressionStream = CompressionStream;
}
if (typeof globalThis.DecompressionStream !== 'function') {
    globalThis.DecompressionStream = DecompressionStream;
}

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
