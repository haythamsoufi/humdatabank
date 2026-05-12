// Confirmation Dialogs UI
// Centralized reusable alert and confirmation modals used across all Backoffice templates.
// Guard against duplicate script inclusion (e.g. layout + form_builder both loading this file).
(function() {
    if (typeof window.createModalShell !== 'undefined') return;

// These functions are exposed on window and loaded via core/layout.html.
//
// API:
//   createModalShell(title, options?) - Returns { modal, modalContent, innerDiv, headerDiv, contentDiv, closeModal }
//   showAlert(message, type?, title?)         - type: 'info'|'warning'|'error'|'success'
//   showConfirmation(msg, onConfirm, onCancel?, confirmText?, cancelText?, title?)
//   showSubmitConfirmation(msg, onConfirm, onCancel?, confirmText?, cancelText?, title?)
//   showDangerConfirmation(msg, onConfirm, onCancel?, confirmText?, cancelText?, title?)
//   showDeleteDataConfirmation(msg, dataCount, onDeleteData, onKeepData, onCancel?, itemType?, translations?)
//   getConfirmMessage(formOrElement) - returns first of data-confirm, data-confirm-message, data-confirm-msg, data-confirm-text
//   hasConfirm(formOrElement) - returns true if any confirm attribute is set

/**
 * Get confirmation message from form or element (data-confirm, data-confirm-message, data-confirm-msg, data-confirm-text).
 * @param {HTMLFormElement|HTMLElement} el - Form or element with confirm attributes
 * @returns {string|null} Message or null
 */
function getConfirmMessage(el) {
  if (!el || typeof el.getAttribute !== 'function') return null;
  return el.getAttribute('data-confirm') || el.getAttribute('data-confirm-message') || el.getAttribute('data-confirm-msg') || el.getAttribute('data-confirm-text') || null;
}

/**
 * Check if form or element has a confirmation message.
 * @param {HTMLFormElement|HTMLElement} el
 * @returns {boolean}
 */
function hasConfirm(el) {
  return !!getConfirmMessage(el);
}

const LOADING_HTML = '<i class="fas fa-spinner fa-spin mr-2"></i>';
const LOADING_TEXT = 'Loading...';

function setConfirmButtonLoading(btn, loading, originalText) {
    if (loading) {
        btn.disabled = true;
        btn.dataset.confirmOriginalText = originalText;
        btn.innerHTML = LOADING_HTML + LOADING_TEXT;
    } else {
        btn.disabled = false;
        btn.textContent = originalText || 'Confirm';
        delete btn.dataset.confirmOriginalText;
    }
}

/** SVG path data for modal icons */
const MODAL_ICONS = {
    warning: { class: 'h-6 w-6 text-amber-400', d: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z' },
    danger: { class: 'h-6 w-6 text-red-400', d: 'M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z' },
    info: { class: 'h-6 w-6 text-blue-400', d: 'M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z' },
    success: { class: 'h-6 w-6 text-green-400', d: 'M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z' },
    users: { class: 'h-6 w-6 text-blue-400', d: 'M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197m13.5-9a2.5 2.5 0 11-5 0 2.5 2.5 0 015 0z' }
};

/**
 * Create a reusable modal shell (backdrop, header with icon, content area).
 * Callers append to contentDiv and call closeModal when done.
 * @param {string} title - Modal title
 * @param {Object} [options] - Options: iconType ('warning'|'danger'|'info'|'success'|'users'), maxWidth ('md'|'lg'|'2xl'), zIndex
 * @returns {{ modal: HTMLElement, modalContent: HTMLElement, innerDiv: HTMLElement, headerDiv: HTMLElement, contentDiv: HTMLElement, closeModal: function }}
 */
function createModalShell(title, options = {}) {
    const { iconType = 'warning', maxWidth = 'md', zIndex = 1100 } = options;
    const icon = MODAL_ICONS[iconType] || MODAL_ICONS.warning;
    const maxW = { md: 'max-w-md', lg: 'max-w-lg', xl: 'max-w-xl', '2xl': 'max-w-2xl' }[maxWidth] || 'max-w-md';

    const modal = document.createElement('div');
    modal.className = 'fixed inset-0 flex items-center justify-center p-4';
    modal.style.zIndex = String(zIndex);
    modal.style.display = 'flex';

    const backdrop = document.createElement('div');
    backdrop.className = 'absolute inset-0 modal-backdrop transition-opacity';

    const modalContent = document.createElement('div');
    modalContent.className = `relative bg-white rounded-lg shadow-xl w-full ${maxW} transform transition-all`;

    const innerDiv = document.createElement('div');
    innerDiv.className = 'p-6';

    const headerDiv = document.createElement('div');
    headerDiv.className = 'flex items-center mb-4';

    const iconContainer = document.createElement('div');
    iconContainer.className = 'flex-shrink-0';
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', icon.class);
    svg.setAttribute('fill', 'none');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('stroke', 'currentColor');
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('stroke-linecap', 'round');
    path.setAttribute('stroke-linejoin', 'round');
    path.setAttribute('stroke-width', '2');
    path.setAttribute('d', icon.d);
    svg.appendChild(path);
    iconContainer.appendChild(svg);

    const titleContainer = document.createElement('div');
    titleContainer.className = 'ml-3';
    const heading = document.createElement('h3');
    heading.className = 'text-lg font-medium text-gray-900';
    heading.textContent = title;
    titleContainer.appendChild(heading);

    headerDiv.appendChild(iconContainer);
    headerDiv.appendChild(titleContainer);

    const contentDiv = document.createElement('div');
    contentDiv.className = 'space-y-4';

    innerDiv.appendChild(headerDiv);
    innerDiv.appendChild(contentDiv);
    modalContent.appendChild(innerDiv);
    modal.appendChild(backdrop);
    modal.appendChild(modalContent);
    document.body.appendChild(modal);

    modalContent.addEventListener('click', (e) => e.stopPropagation());

    const closeModal = () => {
        if (modal.parentNode) {
            document.body.removeChild(modal);
        }
        document.removeEventListener('keydown', handleEscape);
    };

    const handleEscape = (e) => {
        if (e.key === 'Escape') {
            closeModal();
            if (options.onCancel) options.onCancel();
        }
    };
    document.addEventListener('keydown', handleEscape);

    modal.addEventListener('click', (e) => {
        if (e.target === modal || e.target === backdrop) {
            closeModal();
            if (options.onCancel) options.onCancel();
        }
    });

    return { modal, modalContent, innerDiv, headerDiv, contentDiv, closeModal };
}

/**
 * Internal: show confirmation dialog using createModalShell
 * @param {string} message
 * @param {function} onConfirm
 * @param {function|null} onCancel
 * @param {string} confirmText
 * @param {string} cancelText
 * @param {string} title
 * @param {string} iconType - 'warning'|'danger'|'info'
 * @param {string} confirmBtnClass - Button class for confirm action
 * @param {boolean} focusCancel - If true, focus cancel button; else focus confirm
 */
function _showConfirmationWithButtons(message, onConfirm, onCancel, confirmText, cancelText, title, iconType, confirmBtnClass, focusCancel) {
    const { contentDiv, closeModal } = createModalShell(title, {
        iconType,
        maxWidth: 'md',
        // Stack above high-z app modals (e.g. AI Upload/Import modal at 11000; IFRC dropdown at 11050).
        zIndex: 12000,
        onCancel: () => {
            closeModal();
            if (onCancel) onCancel();
        }
    });

    const messageDiv = document.createElement('div');
    messageDiv.className = 'mb-6';
    const messageP = document.createElement('p');
    messageP.className = 'text-sm text-gray-600';
    messageP.textContent = message;
    messageDiv.appendChild(messageP);

    const buttonsDiv = document.createElement('div');
    buttonsDiv.className = 'flex justify-end space-x-3';

    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.id = 'confirm-cancel';
    cancelBtn.className = 'btn btn-secondary';
    cancelBtn.textContent = cancelText;

    const confirmBtn = document.createElement('button');
    confirmBtn.type = 'button';
    confirmBtn.id = 'confirm-ok';
    confirmBtn.className = confirmBtnClass;
    confirmBtn.textContent = confirmText;

    buttonsDiv.appendChild(cancelBtn);
    buttonsDiv.appendChild(confirmBtn);
    contentDiv.appendChild(messageDiv);
    contentDiv.appendChild(buttonsDiv);

    const doClose = () => {
        closeModal();
    };

    cancelBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        doClose();
        if (onCancel) onCancel();
    });

    confirmBtn.addEventListener('click', async (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!onConfirm) { doClose(); return; }
        const originalText = confirmText;
        setConfirmButtonLoading(confirmBtn, true, originalText);
        cancelBtn.disabled = true;
        try {
            const result = onConfirm();
            if (result && typeof result.then === 'function') {
                await result;
            }
            doClose();
        } catch (err) {
            setConfirmButtonLoading(confirmBtn, false, originalText);
            cancelBtn.disabled = false;
            if (typeof window.showAlert === 'function') {
                window.showAlert((err && err.message) ? err.message : String(err), 'error');
            } else {
                console.error('Confirm callback error:', err);
            }
        }
    });

    setTimeout(() => (focusCancel ? cancelBtn : confirmBtn).focus(), 100);
}

/**
 * Show a custom confirmation dialog
 * @param {string} message - The confirmation message to display
 * @param {function} onConfirm - Callback function to execute when user confirms
 * @param {function} onCancel - Optional callback function to execute when user cancels
 * @param {string} confirmText - Optional text for the confirm button (default: "Confirm")
 * @param {string} cancelText - Optional text for the cancel button (default: "Cancel")
 * @param {string} title - Optional title for the dialog (default: "Confirm Action")
 */
function showConfirmation(message, onConfirm, onCancel = null, confirmText = 'Confirm', cancelText = 'Cancel', title = 'Confirm Action') {
    _showConfirmationWithButtons(message, onConfirm, onCancel, confirmText, cancelText, title, 'warning',
        'btn btn-success', false);
}

/**
 * Show a confirmation dialog with success/submit styling for form submission
 * @param {string} message - The confirmation message to display
 * @param {function} onConfirm - Callback function to execute when user confirms
 * @param {function} onCancel - Optional callback function to execute when user cancels
 * @param {string} confirmText - Optional text for the confirm button (default: "Submit")
 * @param {string} cancelText - Optional text for the cancel button (default: "Cancel")
 * @param {string} title - Optional title for the dialog (default: "Submit Form?")
 */
function showSubmitConfirmation(message, onConfirm, onCancel = null, confirmText = 'Submit', cancelText = 'Cancel', title = 'Submit Form?') {
    _showConfirmationWithButtons(message, onConfirm, onCancel, confirmText, cancelText, title, 'warning',
        'btn btn-success', true);
}

/**
 * Show a confirmation dialog with danger styling for destructive actions
 * @param {string} message - The confirmation message to display
 * @param {function} onConfirm - Callback function to execute when user confirms
 * @param {function} onCancel - Optional callback function to execute when user cancels
 * @param {string} confirmText - Optional text for the confirm button (default: "Delete")
 * @param {string} cancelText - Optional text for the cancel button (default: "Cancel")
 * @param {string} title - Optional title for the dialog (default: "Confirm Delete")
 */
function showDangerConfirmation(message, onConfirm, onCancel = null, confirmText = 'Delete', cancelText = 'Cancel', title = 'Confirm Delete') {
    _showConfirmationWithButtons(message, onConfirm, onCancel, confirmText, cancelText, title, 'danger',
        'btn btn-danger', true);
}

/**
 * Show a confirmation dialog with two options for deletion (delete data vs keep data)
 * @param {string} message - The confirmation message to display
 * @param {number} dataCount - The number of data entries that would be deleted
 * @param {function} onDeleteData - Callback function when user chooses to delete data and item/section
 * @param {function} onKeepData - Callback function when user chooses to keep data (and cancel deletion)
 * @param {function} onCancel - Optional callback function when user cancels
 * @param {string} itemType - Type of item being deleted (e.g., "item", "section")
 * @param {object} translations - Optional object with translation strings
 */
function showDeleteDataConfirmation(message, dataCount, onDeleteData, onKeepData, onCancel = null, itemType = 'item', translations = {}) {
    // Default translations (English)
    const t = {
        delete: translations.delete || 'Delete',
        this: translations.this || 'This',
        has: translations.has || 'has',
        savedDataEntries: translations.savedDataEntries || 'saved data entries.',
        mayHaveAssociatedData: translations.mayHaveAssociatedData || 'may have associated data.',
        chooseOption: translations.chooseOption || 'Choose an option:',
        deleteDataAndRemove: translations.deleteDataAndRemove || 'Delete Data and Remove',
        permanentlyDelete: translations.permanentlyDelete || 'Permanently delete all associated data entries and remove the',
        fromTemplate: translations.fromTemplate || 'from the template.',
        keepDataAndRemoveItem: translations.keepDataAndRemoveItem || 'Keep Data and Archive Item',
        keepDataButRemove: translations.keepDataButRemove || 'Keep the data entries but archive the',
        itemWillBeArchived: translations.itemWillBeArchived || '(The item will be archived and hidden from the template)',
        sectionWillBeArchived: translations.sectionWillBeArchived || '(The section and its items will be archived and hidden from the template)',
        cancel: translations.cancel || 'Cancel',
        continue: translations.continue || 'Continue'
    };

    const itemTypeCapitalized = itemType.charAt(0).toUpperCase() + itemType.slice(1);
    const dataCountText = dataCount > 0 ? `${dataCount} ${t.savedDataEntries}` : t.mayHaveAssociatedData;
    const modalTitle = `${t.delete} ${itemTypeCapitalized}?`;

    const { modalContent, contentDiv, closeModal } = createModalShell(modalTitle, {
        iconType: 'danger',
        maxWidth: 'md',
        zIndex: 1100,
        onCancel: () => { closeModal(); if (onCancel) onCancel(); }
    });

    contentDiv.className = 'mb-6 space-y-4';

    const messageP = document.createElement('p');
    messageP.className = 'text-sm text-gray-600 mb-4';
    messageP.textContent = message;
    contentDiv.appendChild(messageP);

    const warningDiv = document.createElement('div');
    warningDiv.className = 'bg-yellow-50 border-l-4 border-yellow-400 p-4 mb-4';
    const warningFlex = document.createElement('div');
    warningFlex.className = 'flex';
    const warningIconContainer = document.createElement('div');
    warningIconContainer.className = 'flex-shrink-0';
    const warningSvg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    warningSvg.setAttribute('class', 'h-5 w-5 text-yellow-400');
    warningSvg.setAttribute('viewBox', '0 0 20 20');
    warningSvg.setAttribute('fill', 'currentColor');
    const warningPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    warningPath.setAttribute('fill-rule', 'evenodd');
    warningPath.setAttribute('d', 'M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z');
    warningPath.setAttribute('clip-rule', 'evenodd');
    warningSvg.appendChild(warningPath);
    warningIconContainer.appendChild(warningSvg);
    const warningTextDiv = document.createElement('div');
    warningTextDiv.className = 'ml-3';
    const warningTextP = document.createElement('p');
    warningTextP.className = 'text-sm text-yellow-700';
    const warningStrong = document.createElement('strong');
    warningStrong.textContent = `${t.this} ${itemType} ${dataCountText}`;
    warningTextP.appendChild(warningStrong);
    warningTextDiv.appendChild(warningTextP);
    warningFlex.appendChild(warningIconContainer);
    warningFlex.appendChild(warningTextDiv);
    warningDiv.appendChild(warningFlex);
    contentDiv.appendChild(warningDiv);

    const chooseOptionP = document.createElement('p');
    chooseOptionP.className = 'text-sm font-medium text-gray-900 mb-2';
    chooseOptionP.textContent = t.chooseOption;
    contentDiv.appendChild(chooseOptionP);

    const optionsDiv = document.createElement('div');
    optionsDiv.className = 'space-y-2';

    const deleteOptionLabel = document.createElement('label');
    deleteOptionLabel.className = 'flex items-start p-3 border-2 border-red-200 rounded-md hover:bg-red-50 cursor-pointer';
    const deleteRadio = document.createElement('input');
    deleteRadio.type = 'radio';
    deleteRadio.name = 'delete-option';
    deleteRadio.value = 'delete-data';
    deleteRadio.className = 'mt-1 mr-3 text-red-600 focus:ring-red-500';
    deleteRadio.checked = true;
    const deleteOptionDiv = document.createElement('div');
    const deleteOptionTitle = document.createElement('p');
    deleteOptionTitle.className = 'text-sm font-medium text-gray-900';
    deleteOptionTitle.textContent = `${t.deleteDataAndRemove} ${itemType}`;
    const deleteOptionDesc = document.createElement('p');
    deleteOptionDesc.className = 'text-xs text-gray-500';
    deleteOptionDesc.textContent = `${t.permanentlyDelete} ${itemType} ${t.fromTemplate}`;
    deleteOptionDiv.appendChild(deleteOptionTitle);
    deleteOptionDiv.appendChild(deleteOptionDesc);
    deleteOptionLabel.appendChild(deleteRadio);
    deleteOptionLabel.appendChild(deleteOptionDiv);
    optionsDiv.appendChild(deleteOptionLabel);

    const keepOptionLabel = document.createElement('label');
    keepOptionLabel.className = 'flex items-start p-3 border-2 border-blue-200 rounded-md hover:bg-blue-50 cursor-pointer';
    const keepRadio = document.createElement('input');
    keepRadio.type = 'radio';
    keepRadio.name = 'delete-option';
    keepRadio.value = 'keep-data-delete-item';
    keepRadio.className = 'mt-1 mr-3 text-blue-600 focus:ring-blue-500';
    const keepOptionDiv = document.createElement('div');
    const keepOptionTitle = document.createElement('p');
    keepOptionTitle.className = 'text-sm font-medium text-gray-900';
    keepOptionTitle.textContent = t.keepDataAndRemoveItem;
    const keepOptionDesc = document.createElement('p');
    keepOptionDesc.className = 'text-xs text-gray-500';
    const keepDescText = `${t.keepDataButRemove} ${itemType} ${t.fromTemplate} ${(itemType === 'section' || itemType === 'sub-section') ? (translations.sectionWillBeArchived || '(The section and its items will be archived and hidden from the template)') : t.itemWillBeArchived}`;
    keepOptionDesc.textContent = keepDescText;
    keepOptionDiv.appendChild(keepOptionTitle);
    keepOptionDiv.appendChild(keepOptionDesc);
    keepOptionLabel.appendChild(keepRadio);
    keepOptionLabel.appendChild(keepOptionDiv);
    optionsDiv.appendChild(keepOptionLabel);

    contentDiv.appendChild(optionsDiv);

    const buttonsDiv = document.createElement('div');
    buttonsDiv.className = 'flex justify-end space-x-3';

    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.id = 'confirm-cancel';
    cancelBtn.className = 'btn btn-secondary';
    cancelBtn.textContent = t.cancel;

    const confirmBtn = document.createElement('button');
    confirmBtn.type = 'button';
    confirmBtn.id = 'confirm-ok';
    confirmBtn.className = 'btn btn-danger';
    confirmBtn.textContent = t.continue;

    buttonsDiv.appendChild(cancelBtn);
    buttonsDiv.appendChild(confirmBtn);

    contentDiv.appendChild(buttonsDiv);

    cancelBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        closeModal();
        if (onCancel) onCancel();
    });

    confirmBtn.addEventListener('click', async (e) => {
        e.preventDefault();
        e.stopPropagation();
        const selectedOption = modalContent.querySelector('input[name="delete-option"]:checked').value;
        const cb = selectedOption === 'delete-data' ? onDeleteData : (onKeepData ? () => onKeepData('delete-item') : null);
        if (!cb) { closeModal(); return; }
        const originalText = t.continue;
        setConfirmButtonLoading(confirmBtn, true, originalText);
        cancelBtn.disabled = true;
        try {
            const result = cb();
            if (result && typeof result.then === 'function') {
                await result;
            }
            closeModal();
        } catch (err) {
            setConfirmButtonLoading(confirmBtn, false, originalText);
            cancelBtn.disabled = false;
            if (typeof window.showAlert === 'function') {
                window.showAlert((err && err.message) ? err.message : String(err), 'error');
            } else {
                console.error('Confirm callback error:', err);
            }
        }
    });

    // Focus the cancel button for safety
    setTimeout(() => {
        cancelBtn.focus();
    }, 100);
}

const ALERT_ICON_TYPES = { error: 'danger', warning: 'warning', success: 'success', info: 'info' };
const ALERT_TITLES = { error: 'Error', warning: 'Warning', success: 'Success', info: 'Information' };

/**
 * Show a blocking alert dialog (replaces native alert)
 * @param {string} message - The message to display
 * @param {string} type - Type of alert: 'info', 'warning', 'error', 'success' (default: 'info')
 * @param {string|null} title - Optional title for the dialog
 * @param {function|null} onClose - Optional callback when the user clicks OK (after the modal closes)
 */
function showAlert(message, type = 'info', title = null, onClose = null) {
    const iconType = ALERT_ICON_TYPES[type] || 'info';
    const alertTitle = title || ALERT_TITLES[type] || 'Information';

    const { contentDiv, closeModal } = createModalShell(alertTitle, {
        iconType,
        maxWidth: 'md',
        zIndex: 1100
    });

    const messageDiv = document.createElement('div');
    messageDiv.className = 'mb-6';
    const messageP = document.createElement('p');
    messageP.className = 'text-sm text-gray-600';
    messageP.textContent = message;
    messageDiv.appendChild(messageP);

    const buttonsDiv = document.createElement('div');
    buttonsDiv.className = 'flex justify-end';

    const okBtn = document.createElement('button');
    okBtn.type = 'button';
    okBtn.id = 'alert-ok';
    okBtn.className = 'btn btn-success';
    okBtn.textContent = 'OK';

    buttonsDiv.appendChild(okBtn);
    contentDiv.appendChild(messageDiv);
    contentDiv.appendChild(buttonsDiv);

    okBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        closeModal();
        if (typeof onClose === 'function') {
            try {
                onClose();
            } catch (err) {
                console.error('showAlert onClose error:', err);
            }
        }
    });

    setTimeout(() => okBtn.focus(), 100);
}

// Make functions globally available
window.createModalShell = createModalShell;
window.showConfirmation = showConfirmation;
window.showSubmitConfirmation = showSubmitConfirmation;
window.showDangerConfirmation = showDangerConfirmation;
window.showDeleteDataConfirmation = showDeleteDataConfirmation;
window.showAlert = showAlert;
window.getConfirmMessage = getConfirmMessage;
window.hasConfirm = hasConfirm;

})();
