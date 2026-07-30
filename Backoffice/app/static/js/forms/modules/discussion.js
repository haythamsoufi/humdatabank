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



function getDiscussionCurrentUserId() {
    const panel = document.getElementById('discussion-panel');
    if (panel?.dataset.currentUserId) {
        const id = parseInt(panel.dataset.currentUserId, 10);
        if (id) return id;
    }
    const block = document.querySelector('.discussion-form-item[data-current-user-id]');
    if (block?.dataset.currentUserId) {
        const id = parseInt(block.dataset.currentUserId, 10);
        if (id) return id;
    }
    return 0;
}

function isOwnDiscussionComment(comment, currentUserId) {
    if (!currentUserId || comment.is_imported || comment.source === 'upr_excel_import') {
        return false;
    }
    const authorId = comment.author?.id ?? comment.created_by_user_id;
    return authorId != null && Number(authorId) === Number(currentUserId);
}

function getDiscussionI18nString(datasetKey, fallback) {
    const panel = document.getElementById('discussion-panel');
    if (panel?.dataset[datasetKey]) return panel.dataset[datasetKey];
    const block = document.querySelector('.discussion-form-item');
    if (block?.dataset[datasetKey]) return block.dataset[datasetKey];
    return fallback;
}

function buildDiscussionAvatarHtml(comment, compact) {
    const isImported = Boolean(comment.is_imported || comment.source === 'upr_excel_import');
    if (isImported) {
        return `<div class="discussion-comment__avatar flex-shrink-0" aria-hidden="true">
            <span class="discussion-comment__avatar-icon discussion-comment__avatar-icon--imported">
                <i class="fas fa-file-import"></i>
            </span>
        </div>`;
    }

    const author = comment.author;
    if (author && author.initials) {
        const color = author.profile_color || '#3B82F6';
        const sizeClass = compact ? 'w-7 h-7 text-xs' : 'w-9 h-9 text-xs';
        return `<div class="discussion-comment__avatar flex-shrink-0" aria-hidden="true">
            <div class="profile-icon">
                <div class="${sizeClass} rounded-full text-white font-semibold flex items-center justify-center flex-shrink-0 profile-icon-circle avatar-circle"
                     style="background-color: ${escapeHtml(color)}">${escapeHtml(author.initials)}</div>
            </div>
        </div>`;
    }

    return `<div class="discussion-comment__avatar flex-shrink-0" aria-hidden="true">
        <span class="discussion-comment__avatar-icon discussion-comment__avatar-icon--unknown">
            <i class="fas fa-user"></i>
        </span>
    </div>`;
}

function getDiscussionCanEdit() {
    const panel = document.getElementById('discussion-panel');
    if (panel?.dataset.canEdit === 'true') return true;
    return Boolean(document.querySelector('.discussion-form-item[data-can-edit="true"]'));
}

function getDiscussionMaxLength() {
    const panel = document.getElementById('discussion-panel');
    if (panel?.dataset.maxLength) {
        return parseInt(panel.dataset.maxLength, 10);
    }
    const block = document.querySelector('.discussion-form-item[data-max-length]');
    if (block?.dataset.maxLength) {
        return parseInt(block.dataset.maxLength, 10);
    }
    return 2000;
}

function buildCommentActionsHtml(isOwn, compact, canEdit, isImported) {
    if (!isOwn || compact || !canEdit || isImported) return '';
    return `<div class="discussion-comment__actions">
                <button type="button"
                        class="discussion-comment__action-btn discussion-comment-edit-btn"
                        title="${escapeHtml(getDiscussionI18nString('i18nEdit', 'Edit comment'))}"
                        aria-label="${escapeHtml(getDiscussionI18nString('i18nEdit', 'Edit comment'))}">
                    <i class="fas fa-pen" aria-hidden="true"></i>
                </button>
                <button type="button"
                        class="discussion-comment__action-btn discussion-comment-delete-btn"
                        title="${escapeHtml(getDiscussionI18nString('i18nDelete', 'Delete comment'))}"
                        aria-label="${escapeHtml(getDiscussionI18nString('i18nDelete', 'Delete comment'))}">
                    <i class="fas fa-trash-alt" aria-hidden="true"></i>
                </button>
            </div>`;
}

function buildCommentElement(comment, { compact = false } = {}) {
    const isImported = Boolean(comment.is_imported || comment.source === 'upr_excel_import');
    const currentUserId = getDiscussionCurrentUserId();
    const isOwn = isOwnDiscussionComment(comment, currentUserId);
    const canEdit = getDiscussionCanEdit();
    const authorName = comment.author_label
        || (comment.author && comment.author.name)
        || '';

    const item = document.createElement('div');
    item.className = 'discussion-comment'
        + (isOwn ? ' discussion-comment--self' : ' discussion-comment--other')
        + (isImported ? ' discussion-comment--imported' : '')
        + (compact ? ' discussion-comment--compact' : '');
    item.dataset.commentId = String(comment.id);
    if (comment.created_by_user_id) {
        item.dataset.createdByUserId = String(comment.created_by_user_id);
    }
    if (comment.source) {
        item.dataset.commentSource = comment.source;
    }

    const importedBadge = isImported && !compact
        ? `<span class="discussion-comment__badge">${escapeHtml(getDiscussionI18nString('i18nHistoricalImport', 'Historical import'))}</span>`
        : '';

    const timeHtml = comment.created_at
        ? `<span class="discussion-comment__time">${escapeHtml(formatCommentTimestamp(comment.created_at))}</span>`
        : '';

    const actionsHtml = buildCommentActionsHtml(isOwn, compact, canEdit, isImported);

    item.innerHTML = `
        ${buildDiscussionAvatarHtml(comment, compact)}
        <div class="discussion-comment__main">
            <div class="discussion-comment__header">
                <span class="discussion-comment__author">${escapeHtml(authorName)}</span>
                ${importedBadge}
                ${timeHtml}
                ${actionsHtml}
            </div>
            <div class="discussion-comment__bubble">
                <p class="discussion-comment__body" dir="auto">${escapeHtml(comment.body || '')}</p>
            </div>
        </div>
    `;
    return item;
}

function commentFromElement(el) {
    if (!el) return null;
    const authorId = el.dataset.createdByUserId
        ? parseInt(el.dataset.createdByUserId, 10)
        : null;
    return {
        id: parseInt(el.dataset.commentId, 10),
        body: el.querySelector('.discussion-comment__body')?.textContent || '',
        source: el.dataset.commentSource || null,
        is_imported: el.classList.contains('discussion-comment--imported'),
        author_label: el.querySelector('.discussion-comment__author')?.textContent?.trim() || '',
        created_by_user_id: authorId,
        author: authorId ? { id: authorId } : null,
    };
}

function replaceCommentInAllViews(comment) {
    document.querySelectorAll(`.discussion-comment[data-comment-id="${comment.id}"]`).forEach((el) => {
        const compact = el.classList.contains('discussion-comment--compact');
        el.replaceWith(buildCommentElement(comment, { compact }));
    });
}

function refreshPreviewAfterDelete() {
    const panel = document.getElementById('discussion-panel');
    const previewContent = document.getElementById('discussion-preview-content');
    const expandBtn = document.getElementById('discussion-expand-btn');
    if (!panel || !previewContent) return;

    const list = document.getElementById('discussion-comments-list');
    const items = list ? list.querySelectorAll('.discussion-comment') : [];
    if (items.length === 0) {
        updatePreviewContent(previewContent, null);
    } else {
        updatePreviewContent(previewContent, commentFromElement(items[items.length - 1]));
    }
    updateExpandButton(panel, expandBtn);
}

function removeCommentFromAllViews(commentId) {
    document.querySelectorAll(`.discussion-comment[data-comment-id="${commentId}"]`).forEach((el) => el.remove());
    document.querySelectorAll('.discussion-inline-comments, #discussion-comments-list').forEach((list) => {
        if (list.querySelectorAll('.discussion-comment').length === 0) {
            const empty = document.createElement('p');
            empty.className = 'text-sm text-gray-500 italic';
            empty.id = list.id ? `${list.id}-empty` : 'discussion-empty-state';
            empty.textContent = 'No comments yet.';
            list.appendChild(empty);
        }
    });
    const emptyExpanded = document.getElementById('discussion-expanded-empty-state');
    if (emptyExpanded) emptyExpanded.remove();
    incrementCommentCounts(-1);
    refreshPreviewAfterDelete();
}

async function patchDiscussionComment(commentId, body, maxLength) {
    const trimmed = (body || '').trim();
    if (!trimmed) {
        return { ok: false, error: 'Comment body is required' };
    }
    if (trimmed.length > maxLength) {
        return { ok: false, error: `Comment exceeds maximum length of ${maxLength} characters` };
    }

    const fetchFn = (window.getCsrfAwareFetch && window.getCsrfAwareFetch()) || fetch;
    const response = await fetchFn(`/api/forms/discussion/comments/${commentId}`, {
        method: 'PATCH',
        headers: {
            'Content-Type': 'application/json',
            Accept: 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
        },
        credentials: 'same-origin',
        body: JSON.stringify({ body: trimmed }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        return { ok: false, error: data.error || data.message || 'Failed to update comment' };
    }
    return { ok: true, comment: data.comment || data.data?.comment };
}

async function deleteDiscussionComment(commentId) {
    const fetchFn = (window.getCsrfAwareFetch && window.getCsrfAwareFetch()) || fetch;
    const response = await fetchFn(`/api/forms/discussion/comments/${commentId}`, {
        method: 'DELETE',
        headers: {
            Accept: 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
        },
        credentials: 'same-origin',
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        return { ok: false, error: data.error || data.message || 'Failed to delete comment' };
    }
    return { ok: true };
}

function startCommentEdit(commentEl) {
    if (!commentEl || commentEl.classList.contains('discussion-comment--editing')) return;
    const bodyEl = commentEl.querySelector('.discussion-comment__body');
    const bubble = commentEl.querySelector('.discussion-comment__bubble');
    if (!bodyEl || !bubble) return;

    const originalBody = bodyEl.textContent || '';
    const maxLength = getDiscussionMaxLength();
    commentEl.classList.add('discussion-comment--editing');
    commentEl.dataset.originalBody = originalBody;

    bubble.innerHTML = `
        <div class="discussion-comment__edit-form">
            <textarea class="discussion-comment__edit-input" rows="3" maxlength="${maxLength}"></textarea>
            <div class="discussion-comment__edit-actions">
                <button type="button" class="discussion-comment-cancel-btn btn btn-secondary btn-sm">${escapeHtml(getDiscussionI18nString('i18nCancel', 'Cancel'))}</button>
                <button type="button" class="discussion-comment-save-btn btn btn-primary btn-sm">${escapeHtml(getDiscussionI18nString('i18nSave', 'Save'))}</button>
            </div>
        </div>
    `;
    const input = bubble.querySelector('.discussion-comment__edit-input');
    if (input) {
        input.value = originalBody;
        input.focus();
    }
}

function cancelCommentEdit(commentEl) {
    if (!commentEl || !commentEl.classList.contains('discussion-comment--editing')) return;
    const originalBody = commentEl.dataset.originalBody || '';
    const bubble = commentEl.querySelector('.discussion-comment__bubble');
    if (!bubble) return;

    commentEl.classList.remove('discussion-comment--editing');
    delete commentEl.dataset.originalBody;
    bubble.innerHTML = `<p class="discussion-comment__body" dir="auto">${escapeHtml(originalBody)}</p>`;
}

async function saveCommentEdit(commentEl) {
    if (!commentEl || !commentEl.classList.contains('discussion-comment--editing')) return;
    const input = commentEl.querySelector('.discussion-comment__edit-input');
    const saveBtn = commentEl.querySelector('.discussion-comment-save-btn');
    if (!input || !saveBtn) return;

    const commentId = parseInt(commentEl.dataset.commentId, 10);
    const maxLength = getDiscussionMaxLength();
    saveBtn.disabled = true;
    try {
        const result = await patchDiscussionComment(commentId, input.value, maxLength);
        if (!result.ok) {
            input.setCustomValidity(result.error || 'Failed to update comment');
            input.reportValidity();
            input.setCustomValidity('');
            return;
        }
        replaceCommentInAllViews(result.comment);
    } finally {
        saveBtn.disabled = false;
    }
}

function confirmDeleteComment(onConfirm) {
    const title = getDiscussionI18nString('i18nDeleteTitle', 'Delete comment?');
    const message = getDiscussionI18nString('i18nDeleteConfirm', 'Delete this comment? This cannot be undone.');
    const deleteLabel = getDiscussionI18nString('i18nDelete', 'Delete comment');
    const cancelLabel = getDiscussionI18nString('i18nCancel', 'Cancel');

    if (typeof window.showConfirmation === 'function') {
        window.showConfirmation(message, onConfirm, null, deleteLabel, cancelLabel, title);
        return;
    }
    onConfirm();
}

async function handleDeleteComment(commentEl) {
    const commentId = parseInt(commentEl.dataset.commentId, 10);
    confirmDeleteComment(async () => {
        const result = await deleteDiscussionComment(commentId);
        if (!result.ok) {
            return;
        }
        removeCommentFromAllViews(commentId);
    });
}

function initDiscussionCommentActions() {
    document.addEventListener('click', (event) => {
        const editBtn = event.target.closest('.discussion-comment-edit-btn');
        if (editBtn) {
            event.preventDefault();
            startCommentEdit(editBtn.closest('.discussion-comment'));
            return;
        }

        const cancelBtn = event.target.closest('.discussion-comment-cancel-btn');
        if (cancelBtn) {
            event.preventDefault();
            cancelCommentEdit(cancelBtn.closest('.discussion-comment'));
            return;
        }

        const saveBtn = event.target.closest('.discussion-comment-save-btn');
        if (saveBtn) {
            event.preventDefault();
            saveCommentEdit(saveBtn.closest('.discussion-comment'));
            return;
        }

        const deleteBtn = event.target.closest('.discussion-comment-delete-btn');
        if (deleteBtn) {
            event.preventDefault();
            handleDeleteComment(deleteBtn.closest('.discussion-comment'));
        }
    });
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



    if (panel.dataset.defaultCollapsed === 'false') {

        setDiscussionExpanded(true);

    }



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

    initDiscussionCommentActions();

    initDiscussionSidebar();

    initDiscussionFormItems();

}


