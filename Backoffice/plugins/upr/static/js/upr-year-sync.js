/* Shared filters for the three international support visuals.
 *
 * The map, funding rankings, and coverage chart each run in their own iframe.
 * They are the same host, so they share this tab's sessionStorage. A change
 * writes the value there and tells the other frames on a BroadcastChannel.
 * A frame that loads later reads the stored value when it builds its control.
 */
(function (global) {
    'use strict';

    function channelFor(name) {
        try {
            return new BroadcastChannel(name);
        } catch (e) {
            return null;
        }
    }

    function storageGet(key) {
        try {
            return sessionStorage.getItem(key) || '';
        } catch (e) {
            return '';
        }
    }

    function storageSet(key, value) {
        try {
            sessionStorage.setItem(key, value);
        } catch (e) { /* private mode */ }
    }

    var YEAR_KEY = 'upr-support-year';
    var yearChannel = channelFor(YEAR_KEY);
    var lastYear = storageGet(YEAR_KEY);

    function readYear() {
        return storageGet(YEAR_KEY) || lastYear || '';
    }

    function publishYear(year) {
        var value = String(year || '');
        if (!/^\d{4}$/.test(value) || value === lastYear) return;
        lastYear = value;
        storageSet(YEAR_KEY, value);
        if (yearChannel) yearChannel.postMessage({ year: value });
    }

    function subscribeYear(apply) {
        if (!yearChannel || typeof apply !== 'function') return;
        yearChannel.addEventListener('message', function (event) {
            var year = event.data && String(event.data.year || '');
            if (/^\d{4}$/.test(year)) apply(year);
        });
    }

    var PARTY_KEY = 'upr-support-party';
    var partyChannel = channelFor(PARTY_KEY);
    var lastParty = { from: '', to: '' };
    try {
        var raw = storageGet(PARTY_KEY);
        if (raw) lastParty = Object.assign({ from: '', to: '' }, JSON.parse(raw));
    } catch (e) { /* keep empty */ }

    function readParty() {
        try {
            var stored = storageGet(PARTY_KEY);
            if (stored) return Object.assign({ from: '', to: '' }, JSON.parse(stored));
        } catch (e) { /* ignore */ }
        return { from: lastParty.from || '', to: lastParty.to || '' };
    }

    function publishParty(party) {
        var next = {
            from: String((party && party.from) || '').toUpperCase(),
            to: String((party && party.to) || '').toUpperCase(),
            fromName: String((party && party.fromName) || ''),
            toName: String((party && party.toName) || '')
        };
        if (
            next.from === lastParty.from
            && next.to === lastParty.to
            && next.fromName === (lastParty.fromName || '')
            && next.toName === (lastParty.toName || '')
        ) {
            return;
        }
        lastParty = next;
        storageSet(PARTY_KEY, JSON.stringify(next));
        if (partyChannel) partyChannel.postMessage({ party: next });
    }

    function subscribeParty(apply) {
        if (!partyChannel || typeof apply !== 'function') return;
        partyChannel.addEventListener('message', function (event) {
            if (event.data && event.data.party) apply(event.data.party);
        });
    }

    global.UprYearSync = { read: readYear, publish: publishYear, subscribe: subscribeYear };
    global.UprPartySync = { read: readParty, publish: publishParty, subscribe: subscribeParty };
})(window);
