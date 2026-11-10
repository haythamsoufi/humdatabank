/**
 * Client-side duplicate grouping. Keeper order matches
 * app/services/ai/documents/duplicates.py choose_keeper.
 */

import { cfg } from './shared.js';

export function normalizeDedupeSourceUrl(url) {
    const raw = String(url || '').trim();
    if (!raw) return '';
    try {
        const u = new URL(raw);
        const scheme = (u.protocol || '').replace(':', '').toLowerCase();
        let hostname = (u.hostname || '').toLowerCase();
        let netloc = hostname;
        const port = u.port ? Number(u.port) : null;
        if (port && !((scheme === 'https' && port === 443) || (scheme === 'http' && port === 80))) {
            netloc = hostname + ':' + port;
        }
        let path = u.pathname || '/';
        path = path.replace(/\/{2,}/g, '/');
        return scheme + '://' + netloc + path + (u.search || '');
    } catch (e) {
        return raw;
    }
}

export function annotateDuplicateRows(rows) {
    const list = Array.isArray(rows) ? rows : [];
    const hashBuckets = {};
    const urlBuckets = {};

    list.forEach(function (row) {
        if (!row || row.id == null) return;
        row.is_duplicate = false;
        row.duplicate_group_id = null;
        row.duplicate_match = null;
        row.duplicate_keeper_id = null;
        row.is_duplicate_keeper = false;

        const hash = String(row.content_hash || '').trim().toLowerCase();
        if (hash) {
            if (!hashBuckets[hash]) hashBuckets[hash] = [];
            hashBuckets[hash].push(row);
            return;
        }
        const url = normalizeDedupeSourceUrl(row.source_url);
        if (url) {
            if (!urlBuckets[url]) urlBuckets[url] = [];
            urlBuckets[url].push(row);
        }
    });

    const chooseKeeper = function (members) {
        return members.slice().sort(function (a, b) {
            const linkedA = (a.submitted_document_id || a.guidance_document_id) ? 0 : 1;
            const linkedB = (b.submitted_document_id || b.guidance_document_id) ? 0 : 1;
            if (linkedA !== linkedB) return linkedA - linkedB;
            const statusRank = { completed: 3, processing: 2, pending: 1, failed: 0 };
            const sa = statusRank[String(a.processing_status || '').toLowerCase()] || 0;
            const sb = statusRank[String(b.processing_status || '').toLowerCase()] || 0;
            if (sa !== sb) return sb - sa;
            const ca = Number(a.total_chunks || 0);
            const cb = Number(b.total_chunks || 0);
            if (ca !== cb) return cb - ca;
            return Number(a.id) - Number(b.id);
        })[0];
    };

    const applyGroup = function (matchType, matchValue, members) {
        if (!members || members.length < 2) return;
        const keeper = chooseKeeper(members);
        const groupId = matchType + ':' + matchValue;
        members.forEach(function (row) {
            row.is_duplicate = true;
            row.duplicate_group_id = groupId;
            row.duplicate_match = matchType;
            row.duplicate_keeper_id = keeper.id;
            row.is_duplicate_keeper = Number(row.id) === Number(keeper.id);
        });
    };

    Object.keys(hashBuckets).forEach(function (hash) {
        applyGroup('hash', hash, hashBuckets[hash]);
    });
    Object.keys(urlBuckets).forEach(function (url) {
        applyGroup('url', url, urlBuckets[url]);
    });

    return list;
}

export function summarizeDuplicateRows(rows) {
    const groups = {};
    (rows || []).forEach(function (row) {
        if (!row || !row.is_duplicate || !row.duplicate_group_id) return;
        if (!groups[row.duplicate_group_id]) groups[row.duplicate_group_id] = [];
        groups[row.duplicate_group_id].push(row);
    });
    const groupIds = Object.keys(groups);
    let extras = 0;
    groupIds.forEach(function (gid) {
        extras += Math.max(0, groups[gid].length - 1);
    });
    return { groups: groupIds.length, extras: extras, groupMap: groups };
}

export function updateDocumentsDuplicatesBanner(rows) {
    const banner = document.getElementById('documentsDuplicatesBanner');
    const textEl = document.getElementById('documentsDuplicatesBannerText');
    if (!banner || !textEl) return;
    const summary = summarizeDuplicateRows(rows);
    if (!summary.groups) {
        banner.classList.add('hidden');
        textEl.textContent = '';
        return;
    }
    const tpl = cfg.t.duplicates_banner_6d1f8a3c
        || 'Found {groups} duplicate group(s) ({extras} extra copies). Matching uses file content hash, then source URL.';
    textEl.textContent = tpl
        .replace('{groups}', String(summary.groups))
        .replace('{extras}', String(summary.extras));
    banner.classList.remove('hidden');
}
