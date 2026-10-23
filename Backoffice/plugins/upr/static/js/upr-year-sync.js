/* Shared year for the three international support visuals.
 *
 * The map, funding rankings, and coverage chart each run in their own iframe.
 * They are the same host, so they share this tab's sessionStorage. A change
 * writes the year there and tells the other frames on a BroadcastChannel.
 * A frame that loads later reads the stored year when it builds its control.
 */
(function (global) {
    'use strict';

    var KEY = 'upr-support-year';
    var channel = null;
    var last = '';
    try {
        channel = new BroadcastChannel(KEY);
    } catch (e) { /* an old browser still shares the stored year on load */ }
    try {
        last = sessionStorage.getItem(KEY) || '';
    } catch (e) { /* private mode */ }

    function read() {
        try {
            return sessionStorage.getItem(KEY) || last || '';
        } catch (e) {
            return last || '';
        }
    }

    function publish(year) {
        var value = String(year || '');
        if (!/^\d{4}$/.test(value) || value === last) return;
        last = value;
        try {
            sessionStorage.setItem(KEY, value);
        } catch (e) { /* private mode: the channel can still reach open frames */ }
        if (channel) channel.postMessage({ year: value });
    }

    function subscribe(apply) {
        if (!channel || typeof apply !== 'function') return;
        channel.addEventListener('message', function (event) {
            var year = event.data && String(event.data.year || '');
            if (/^\d{4}$/.test(year)) apply(year);
        });
    }

    global.UprYearSync = { read: read, publish: publish, subscribe: subscribe };
})(window);
