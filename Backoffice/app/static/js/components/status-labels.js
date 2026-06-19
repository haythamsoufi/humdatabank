/**
 * Centralized status label renderer (matches components/_status_label.html + components.css).
 * Usage: StatusLabels.render('Approved', 'success')
 *        StatusLabels.renderAssignmentStatus('in_progress', 'In Progress')
 */
(function (global) {
    'use strict';

    const ASSIGNMENT_VARIANTS = {
        submitted: 'success',
        approved: 'success',
        requires_revision: 'warning',
        sent_for_review: 'review',
        in_progress: 'active',
        completed: 'success',
        pending: 'pending',
    };

    const GENERIC_VARIANTS = {
        approved: 'success',
        active: 'success',
        enabled: 'success',
        success: 'success',
        completed: 'success',
        submitted: 'success',
        sent: 'success',
        deployed: 'success',
        published: 'success',
        available: 'success',
        rejected: 'danger',
        failed: 'danger',
        error: 'danger',
        revoked: 'danger',
        disabled: 'danger',
        inactive: 'neutral',
        unavailable: 'danger',
        deleted: 'danger',
        pending: 'pending',
        waiting: 'pending',
        draft: 'pending',
        in_review: 'pending',
        requires_revision: 'warning',
        warning: 'warning',
        caution: 'warning',
        sent_for_review: 'review',
        review: 'review',
        in_progress: 'active',
        processing: 'active',
        running: 'active',
    };

    function escapeHtml(text) {
        if (text == null) return '';
        return String(text)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function normalizeKey(value) {
        return String(value == null ? '' : value).toLowerCase().replace(/\s+/g, '_');
    }

    function assignmentStatusVariant(status) {
        return ASSIGNMENT_VARIANTS[normalizeKey(status)] || 'neutral';
    }

    function genericStatusVariant(status) {
        return GENERIC_VARIANTS[normalizeKey(status)] || 'neutral';
    }

    function accessRequestVariant(status, isRevoked) {
        if (isRevoked) return 'warning';
        const key = normalizeKey(status);
        if (key === 'pending') return 'pending';
        if (key === 'approved') return 'success';
        if (key === 'rejected') return 'danger';
        return 'neutral';
    }

    function changeTypeVariant(changeType) {
        const key = normalizeKey(changeType);
        if (key === 'added') return 'success';
        if (key === 'removed') return 'danger';
        if (key === 'modified') return 'warning';
        return 'neutral';
    }

    /**
     * @param {string} text - Visible label
     * @param {string} [variant='neutral'] - success|danger|warning|review|active|pending|info|neutral
     * @param {string} [extraClass=''] - Optional extra CSS classes
     * @returns {string} HTML string
     */
    function render(text, variant, extraClass) {
        const v = variant || 'neutral';
        const cls = 'status-label status-label--' + v + (extraClass ? ' ' + extraClass : '');
        return '<span class="' + cls + '">' + escapeHtml(text) + '</span>';
    }

    function renderAssignmentStatus(status, label, extraClass) {
        return render(label, assignmentStatusVariant(status), extraClass);
    }

    function renderGenericStatus(status, label, extraClass) {
        return render(label, genericStatusVariant(status), extraClass);
    }

    function renderAccessRequest(status, label, isRevoked, extraClass) {
        return render(label, accessRequestVariant(status, isRevoked), extraClass);
    }

    function renderChangeType(changeType, label, extraClass) {
        return render(label, changeTypeVariant(changeType), extraClass);
    }

    function renderActive(isActive, activeLabel, inactiveLabel, extraClass) {
        return render(isActive ? activeLabel : inactiveLabel, isActive ? 'success' : 'neutral', extraClass);
    }

    global.StatusLabels = {
        render: render,
        renderAssignmentStatus: renderAssignmentStatus,
        renderGenericStatus: renderGenericStatus,
        renderAccessRequest: renderAccessRequest,
        renderChangeType: renderChangeType,
        renderActive: renderActive,
        assignmentStatusVariant: assignmentStatusVariant,
        genericStatusVariant: genericStatusVariant,
        accessRequestVariant: accessRequestVariant,
        changeTypeVariant: changeTypeVariant,
        escapeHtml: escapeHtml,
    };
})(typeof window !== 'undefined' ? window : globalThis);
