/**
 * Discussion panel: sidebar preview/expand + optional inline form items.
 */

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatCommentTimestamp(isoString) {
    if (!isoString) return '';
    if (window.DateTimeUtils && typeof window.DateTimeUtils.format === 'function') {
        return window.DateTimeUtils.format(isoString, 'datetimeShort');
    }
    try {
        return new Date(isoString).toLocaleString();
    } catch (_) {
        return isoString;
    }
}

function buildCommentElement(comment, { compact = false } = {}) {
    const isImported = Boolean(comment.is_imported || comment.source === 'upr_excel_import');
    const authorName = comment.author_label
        || (comment.author && comment.author.name)
        || '';
    const item = document.createElement('div');
    item.className = 'discussion-comment flex gap-2.5'
        + (isImported ? ' discussion-comment--imported' : '')
        + (compact ? ' discussion-comment--compact' : '');
    item.dataset.commentId = String(comment.id);
    if (comment.source) {
        item.dataset.commentSource = comment.source;
    }

    const avatarSize = compact ? 'w-7 h-7' : 'w-9 h-9';
    const iconSize = compact ? 'text-xs' : 'text-sm';
    const textSize = compact ? 'text-xs line-clamp-3' : 'text-sm';
    const nameSize = compact ? 'text-xs' : 'text-sm';

    let avatarHtml;
    if (isImported) {
        avatarHtml = `<div class="flex-shrink-0"><span class="inline-flex items-center justify-center ${avatarSize} rounded-full bg-amber-100 text-amber-700" aria-hidden="true"><i class="fas fa-file-import ${iconSize}"></i></span></div>`;
    } else if (comment.author) {
        const initial = escapeHtml((authorName || '?').charAt(0).toUpperCase());
        avatarHtml = `<div class="flex-shrink-0"><span class="inline-flex items-center justify-center ${avatarSize} rounded-full bg-blue-100 text-blue-700 ${compact ? 'text-xs' : 'text-sm'} font-semibold">${initial}</span></div>`;
    } else {
        avatarHtml = `<div class="flex-shrink-0"><span class="inline-flex items-center justify-center ${avatarSize} rounded-full bg-gray-200 text-gray-600" aria-hidden="true"><i class="fas fa-user ${iconSize}"></i></span></div>`;
    }

    const importedBadge = isImported && !compact
        ? '<span class="inline-flex items-center rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-800 ring-1 ring-inset ring-amber-200">Historical import</span>'
        : '';

    item.innerHTML = `
        ${avatarHtml}
        <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-x-2 gap-y-0.5 mb-0.5">
                <span class="${nameSize} font-semibold text-gray-900 truncate max-w-full">${escapeHtml(authorName)}</span>
                ${importedBadge}
                <span class="text-xs text-gray-500 whitespace-nowrap">${escapeHtml(formatCommentTimestamp(comment.created_at))}</span>
            </div>
            <p class="${textSize} text-gray-800 whitespace-pre-wrap break-words">${escapeHtml(comment.body || '')}</p>
        </div>
    `;
    return item;
}

function formatShowMoreLabel(template, count) {
    if (!template) return `Show ${count} more`;
    return template.replace('%(count)s', String(count));
}

function updateExpandButton(panel, expandBtn) {
    if (!panel || !expandBtn) return;
    const count = parseInt(panel.dataset.commentCount || '0', 10);
    const canEdit = panel.dataset.canEdit === 'true';
    const hiddenCount = Math.max(0, count - 1);

    if (count === 0 && !canEdit) {
        expandBtn.classList.add('hidden');
        return;
    }

    expandBtn.classList.remove('hidden');
    if (hiddenCount > 0) {
        expandBtn.textContent = formatShowMoreLabel(panel.dataset.i18nShowMore, hiddenCount);
    } else if (count > 0) {
        expandBtn.textContent = panel.dataset.i18nViewDiscussion || 'View discussion';
    } else {
        expandBtn.textContent = panel.dataset.i18nAddComment || 'Add a comment';
    }
}

function updatePreviewContent(previewContent, comment) {
    if (!previewContent) return;
    previewContent.innerHTML = '';
    if (comment) {
        previewContent.appendChild(buildCommentElement(comment, { compact: true }));
    } else {
        const empty = document.createElement('p');
        empty.id = 'discussion-empty-state';
        empty.className = 'text-xs text-gray-500 italic px-0.5';
        empty.textContent = 'No comments yet.';
        previewContent.appendChild(empty);
    }
}

function incrementCommentCounts(delta = 1) {
    document.querySelectorAll('[data-comment-count]').forEach((el) => {
        const current = parseInt(el.dataset.commentCount || '0', 10);
        el.dataset.commentCount = String(current + delta);
    });
}

function appendCommentToAllViews(comment) {
    document.querySelectorAll('.discussion-inline-comments, #discussion-comments-list').forEach((list) => {
        list.querySelectorAll('[id^="discussion-empty-state"]').forEach((node) => node.remove());
        list.querySelectorAll('p.text-gray-500.italic').forEach((node) => {
            if (node.id && node.id.includes('empty-state')) {
                node.remove();
            }
        });
        const emptyExpanded = document.getElementById('discussion-expanded-empty-state');
        if (emptyExpanded) emptyExpanded.remove();
        list.appendChild(buildCommentElement(comment, { compact: false }));
        list.scrollTop = list.scrollHeight;
    });

    const panel = document.getElementById('discussion-panel');
    const previewContent = document.getElementById('discussion-preview-content');
    const expandBtn = document.getElementById('discussion-expand-btn');
    if (panel) {
        updatePreviewContent(previewContent, comment);
        updateExpandButton(panel, expandBtn);
    }
    incrementCommentCounts(1);
}

async function postDiscussionComment({ aesId, body, maxLength, errorEl, onSuccess }) {
    if (!body) {
        if (errorEl) {
            errorEl.textContent = 'Comment body is required';
            errorEl.classList.remove('hidden');
        }
        return false;
    }
    if (body.length > maxLength) {
        if (errorEl) {
            errorEl.textContent = `Comment exceeds maximum length of ${maxLength} characters`;
            errorEl.classList.remove('hidden');
        }
        return false;
    }

    const fetchFn = (window.getCsrfAwareFetch && window.getCsrfAwareFetch()) || fetch;
    const response = await fetchFn('/api/forms/discussion/comments', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
        },
        credentials: 'same-origin',
        body: JSON.stringify({
            assignment_entity_status_id: parseInt(aesId, 10),
            body,
        }),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        if (errorEl) {
            errorEl.textContent = data.error || data.message || 'Failed to post comment';
            errorEl.classList.remove('hidden');
        }
        return false;
    }

    const comment = data.comment || data.data?.comment;
    if (comment) {
        appendCommentToAllViews(comment);
        if (typeof onSuccess === 'function') onSuccess();
    }
    return true;
}

let discussionExpanded = false;

function setDiscussionExpanded(expanded) {
    const sidebar = document.getElementById('section-navigation-sidebar');
    const expandedPane = document.getElementById('discussion-sidebar-expanded');
    const expandBtn = document.getElementById('discussion-expand-btn');
    const discussionTitle = document.getElementById('sidebar-discussion-title');
    const panel = document.getElementById('discussion-panel');
    const headerDiscussion = document.getElementById('sidebar-header-discussion');

    if (!sidebar || !expandedPane) return;

    discussionExpanded = expanded;
    sidebar.setAttribute('data-discussion-expanded', expanded ? 'true' : 'false');
    expandedPane.setAttribute('aria-hidden', expanded ? 'false' : 'true');

    if (expandBtn) {
        expandBtn.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    }
    if (headerDiscussion) {
        headerDiscussion.setAttribute('aria-hidden', expanded ? 'false' : 'true');
    }
    if (discussionTitle && panel?.dataset.panelTitle) {
        discussionTitle.textContent = panel.dataset.panelTitle;
    }
    if (expanded) {
        const input = document.getElementById('discussion-comment-input');
        if (input && panel?.dataset.canEdit === 'true') {
            window.requestAnimationFrame(() => input.focus());
        }
    }
}

export function collapseDiscussionSidebar() {
    if (discussionExpanded) {
        setDiscussionExpanded(false);
    }
}

function initDiscussionSidebar() {
    const panel = document.getElementById('discussion-panel');
    const sidebar = document.getElementById('section-navigation-sidebar');
    const expandedPane = document.getElementById('discussion-sidebar-expanded');
    if (!panel || !sidebar || !expandedPane) return;

    const expandBtn = document.getElementById('discussion-expand-btn');
    const collapseBtn = document.getElementById('discussion-collapse-btn');
    const postBtn = document.getElementById('discussion-post-btn');
    const input = document.getElementById('discussion-comment-input');
    const errorEl = document.getElementById('discussion-comment-error');
    const discussionTitle = document.getElementById('sidebar-discussion-title');

    updateExpandButton(panel, expandBtn);
    if (discussionTitle && panel.dataset.panelTitle) {
        discussionTitle.textContent = panel.dataset.panelTitle;
    }

    expandBtn?.addEventListener('click', () => setDiscussionExpanded(true));
    collapseBtn?.addEventListener('click', () => setDiscussionExpanded(false));

    if (!postBtn || !input || panel.dataset.canEdit !== 'true') return;

    const aesId = panel.dataset.aesId;
    const maxLength = parseInt(panel.dataset.maxLength || '2000', 10);
    let posting = false;

    postBtn.addEventListener('click', async () => {
        if (posting) return;
        posting = true;
        postBtn.disabled = true;
        if (errorEl) {
            errorEl.textContent = '';
            errorEl.classList.add('hidden');
        }
        try {
            const ok = await postDiscussionComment({
                aesId,
                maxLength,
                body: (input.value || '').trim(),
                errorEl,
                onSuccess: () => { input.value = ''; },
            });
            if (!ok && errorEl && !errorEl.textContent) {
                errorEl.textContent = 'Failed to post comment';
                errorEl.classList.remove('hidden');
            }
        } catch (_) {
            if (errorEl) {
                errorEl.textContent = 'Failed to post comment';
                errorEl.classList.remove('hidden');
            }
        } finally {
            posting = false;
            postBtn.disabled = false;
        }
    });
}

function initDiscussionFormItems() {
    document.querySelectorAll('.discussion-form-item[data-can-edit="true"]').forEach((block) => {
        const postBtn = block.querySelector('.discussion-post-btn');
        const input = block.querySelector('.discussion-comment-input');
        const errorEl = block.querySelector('.discussion-comment-error');
        if (!postBtn || !input) return;

        const aesId = block.dataset.aesId;
        const maxLength = parseInt(block.dataset.maxLength || '2000', 10);
        let posting = false;

        postBtn.addEventListener('click', async () => {
            if (posting) return;
            posting = true;
            postBtn.disabled = true;
            if (errorEl) {
                errorEl.textContent = '';
                errorEl.classList.add('hidden');
            }
            try {
                const ok = await postDiscussionComment({
                    aesId,
                    maxLength,
                    body: (input.value || '').trim(),
                    errorEl,
                    onSuccess: () => { input.value = ''; },
                });
                if (!ok && errorEl && !errorEl.textContent) {
                    errorEl.textContent = 'Failed to post comment';
                    errorEl.classList.remove('hidden');
                }
            } catch (_) {
                if (errorEl) {
                    errorEl.textContent = 'Failed to post comment';
                    errorEl.classList.remove('hidden');
                }
            } finally {
                posting = false;
                postBtn.disabled = false;
            }
        });
    });
}

export function initDiscussion() {
    document.addEventListener('discussion:collapse', () => collapseDiscussionSidebar());
    initDiscussionSidebar();
    initDiscussionFormItems();
}
