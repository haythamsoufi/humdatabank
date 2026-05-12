/**
 * Template Deletion Confirmation Modal
 * Handles the confirmation modal for deleting templates with detailed information
 * Uses apiFetch/fetchJson from core layout (load api-fetch.js)
 */

const fetchJson = (url, options) => (window.fetchJson || window.apiFetch)(url, options);

/**
 * Show template deletion confirmation modal
 * @param {number} templateId - Template ID
 * @param {string} templateName - Template name
 * @param {string} deleteUrl - URL to submit deletion
 * @param {string} deleteInfoUrl - URL to fetch deletion info
 * @param {object} translations - Translation strings
 * @param {string} csrfToken - CSRF token for form submission
 */
function showTemplateDeleteConfirmation(templateId, templateName, deleteUrl, deleteInfoUrl, translations, csrfToken) {
    fetchJson(deleteInfoUrl, {
        method: 'GET',
        headers: { 'X-Requested-With': 'XMLHttpRequest' }
    }).then(data => {
        if (data.error) {
            window.showAlert(data.error, 'error');
            return;
        }

        // Build assignments list using DOM construction
        function buildAssignmentsList() {
            if (data.assignments && data.assignments.length > 0) {
                const ul = document.createElement('ul');
                ul.className = 'list-disc list-inside space-y-1 text-sm text-gray-700';
                data.assignments.forEach(assignment => {
                    const li = document.createElement('li');
                    li.appendChild(document.createTextNode(`${assignment.period_name || 'Unnamed Assignment'} (ID: ${assignment.id})`));
                    if (assignment.public_submissions_count > 0) {
                        li.appendChild(document.createTextNode(' - '));
                        const span = document.createElement('span');
                        span.className = 'text-red-600 font-semibold';
                        span.textContent = `${assignment.public_submissions_count} public submission(s)`;
                        li.appendChild(span);
                    }
                    ul.appendChild(li);
                });
                return ul;
            } else {
                const p = document.createElement('p');
                p.className = 'text-sm text-gray-600';
                p.textContent = 'No assignments';
                return p;
            }
        }

        // Build versions list using DOM construction
        function buildVersionsList() {
            if (data.versions && data.versions.length > 0) {
                const ul = document.createElement('ul');
                ul.className = 'list-disc list-inside space-y-1 text-sm text-gray-700';
                data.versions.forEach(version => {
                    const li = document.createElement('li');
                    li.appendChild(document.createTextNode(`Version ${version.version_number || version.id}`));
                    const statusBadge = document.createElement('span');
                    statusBadge.className = 'inline-block text-xs px-2 py-1 rounded ml-2';
                    if (version.status === 'published') {
                        statusBadge.className += ' bg-green-100 text-green-800';
                        statusBadge.textContent = 'Published';
                    } else if (version.status === 'draft') {
                        statusBadge.className += ' bg-yellow-100 text-yellow-800';
                        statusBadge.textContent = 'Draft';
                    } else {
                        statusBadge.className += ' bg-gray-100 text-gray-800';
                        statusBadge.textContent = 'Archived';
                    }
                    li.appendChild(statusBadge);
                    ul.appendChild(li);
                });
                return ul;
            } else {
                const p = document.createElement('p');
                p.className = 'text-sm text-gray-600';
                p.textContent = 'No versions';
                return p;
            }
        }

        const modalTitle = `${translations.deleteTemplate || 'Delete Template'}?`;
        const { modal, modalContent, innerDiv, contentDiv, closeModal } = window.createModalShell(modalTitle, { iconType: 'danger', maxWidth: '2xl' });
        modalContent.classList.add('max-h-[90vh]', 'overflow-y-auto');
        contentDiv.className = 'mb-6 space-y-4';
        const nameP = document.createElement('p');
        nameP.className = 'text-sm text-gray-600 -mt-2 mb-2';
        nameP.textContent = templateName;
        contentDiv.insertBefore(nameP, contentDiv.firstChild);

        const warningDiv = document.createElement('div');
        warningDiv.className = 'bg-red-50 border-l-4 border-red-400 p-4';
        const warningFlex = document.createElement('div');
        warningFlex.className = 'flex';
        const warningIconContainer = document.createElement('div');
        warningIconContainer.className = 'flex-shrink-0';
        const warningSvg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        warningSvg.setAttribute('class', 'h-5 w-5 text-red-400');
        warningSvg.setAttribute('viewBox', '0 0 20 20');
        warningSvg.setAttribute('fill', 'currentColor');
        const warningPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        warningPath.setAttribute('fill-rule', 'evenodd');
        warningPath.setAttribute('d', 'M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z');
        warningPath.setAttribute('clip-rule', 'evenodd');
        warningSvg.appendChild(warningPath);
        warningIconContainer.appendChild(warningSvg);
        const warningTextDiv = document.createElement('div');
        warningTextDiv.className = 'ml-3';
        const warningTitleP = document.createElement('p');
        warningTitleP.className = 'text-sm font-medium text-red-800';
        warningTitleP.textContent = translations.warning || 'Warning: This action cannot be undone!';
        const warningDescP = document.createElement('p');
        warningDescP.className = 'text-sm text-red-700 mt-1';
        warningDescP.textContent = translations.allWillBeDeleted || 'All of the following will be permanently deleted:';
        warningTextDiv.appendChild(warningTitleP);
        warningTextDiv.appendChild(warningDescP);
        warningFlex.appendChild(warningIconContainer);
        warningFlex.appendChild(warningTextDiv);
        warningDiv.appendChild(warningFlex);
        contentDiv.appendChild(warningDiv);

        const detailsDiv = document.createElement('div');
        detailsDiv.className = 'space-y-4';

        if (data.assignments_count > 0) {
            const assignmentsSection = document.createElement('div');
            const assignmentsH4 = document.createElement('h4');
            assignmentsH4.className = 'text-sm font-semibold text-gray-900 mb-2';
            assignmentsH4.textContent = `${translations.assignments || 'Assignments'} (${data.assignments_count})`;
            assignmentsSection.appendChild(assignmentsH4);
            assignmentsSection.appendChild(buildAssignmentsList());
            detailsDiv.appendChild(assignmentsSection);
        }

        if (data.data_counts.total > 0) {
            const dataSection = document.createElement('div');
            const dataH4 = document.createElement('h4');
            dataH4.className = 'text-sm font-semibold text-gray-900 mb-2';
            dataH4.textContent = `${translations.dataEntries || 'Data Entries'} (${data.data_counts.total})`;
            const dataUl = document.createElement('ul');
            dataUl.className = 'list-disc list-inside space-y-1 text-sm text-gray-700';
            if (data.data_counts.form_data > 0) {
                const li = document.createElement('li');
                li.textContent = `${data.data_counts.form_data} ${translations.formDataEntries || 'form data entries'}`;
                dataUl.appendChild(li);
            }
            if (data.data_counts.repeat_data > 0) {
                const li = document.createElement('li');
                li.textContent = `${data.data_counts.repeat_data} ${translations.repeatDataEntries || 'repeat group data entries'}`;
                dataUl.appendChild(li);
            }
            if (data.data_counts.dynamic_data > 0) {
                const li = document.createElement('li');
                li.textContent = `${data.data_counts.dynamic_data} ${translations.dynamicDataEntries || 'dynamic indicator data entries'}`;
                dataUl.appendChild(li);
            }
            dataSection.appendChild(dataH4);
            dataSection.appendChild(dataUl);
            detailsDiv.appendChild(dataSection);
        }

        const structureSection = document.createElement('div');
        const structureH4 = document.createElement('h4');
        structureH4.className = 'text-sm font-semibold text-gray-900 mb-2';
        structureH4.textContent = translations.templateStructure || 'Template Structure';
        const structureUl = document.createElement('ul');
        structureUl.className = 'list-disc list-inside space-y-1 text-sm text-gray-700';
        if (data.structure_counts.versions > 0) {
            const li = document.createElement('li');
            li.textContent = `${data.structure_counts.versions} ${translations.versions || 'version(s)'}`;
            structureUl.appendChild(li);
        }
        if (data.structure_counts.pages > 0) {
            const li = document.createElement('li');
            li.textContent = `${data.structure_counts.pages} ${translations.pages || 'page(s)'}`;
            structureUl.appendChild(li);
        }
        if (data.structure_counts.sections > 0) {
            const li = document.createElement('li');
            li.textContent = `${data.structure_counts.sections} ${translations.sections || 'section(s)'}`;
            structureUl.appendChild(li);
        }
        if (data.structure_counts.items > 0) {
            const li = document.createElement('li');
            li.textContent = `${data.structure_counts.items} ${translations.items || 'item(s)'}`;
            structureUl.appendChild(li);
        }
        structureSection.appendChild(structureH4);
        structureSection.appendChild(structureUl);
        detailsDiv.appendChild(structureSection);

        if (data.versions && data.versions.length > 0) {
            const versionsSection = document.createElement('div');
            const versionsH4 = document.createElement('h4');
            versionsH4.className = 'text-sm font-semibold text-gray-900 mb-2';
            versionsH4.textContent = translations.versions || 'Versions';
            versionsSection.appendChild(versionsH4);
            versionsSection.appendChild(buildVersionsList());
            detailsDiv.appendChild(versionsSection);
        }

        contentDiv.appendChild(detailsDiv);

        const buttonsDiv = document.createElement('div');
        buttonsDiv.className = 'flex justify-end space-x-3';

        const cancelBtn = document.createElement('button');
        cancelBtn.type = 'button';
        cancelBtn.id = 'template-delete-cancel';
        cancelBtn.className = 'px-4 py-2 text-sm font-medium text-gray-700 bg-gray-100 border border-gray-300 rounded-md hover:bg-gray-200 focus:outline-none focus:ring-2 focus:ring-gray-500';
        cancelBtn.textContent = translations.cancel || 'Cancel';

        const confirmBtn = document.createElement('button');
        confirmBtn.type = 'button';
        confirmBtn.id = 'template-delete-confirm';
        confirmBtn.className = 'px-4 py-2 text-sm font-medium text-white bg-red-600 border border-transparent rounded-md hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500';
        confirmBtn.textContent = translations.deleteTemplate || 'Delete Template';

        buttonsDiv.appendChild(cancelBtn);
        buttonsDiv.appendChild(confirmBtn);

        innerDiv.appendChild(buttonsDiv);

        cancelBtn.addEventListener('click', closeModal);

        confirmBtn.addEventListener('click', () => {
            // Prevent double-clicks
            if (confirmBtn.disabled) return;
            confirmBtn.disabled = true;
            confirmBtn.classList.add('opacity-50', 'cursor-not-allowed');
            const originalText = confirmBtn.textContent;
            confirmBtn.textContent = 'Deleting...';

            // Create a form and submit it with confirmed=true
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = deleteUrl;
            form.classList.add('no-submit-guard'); // Avoid double-protection

            // Add CSRF token
            const csrfInput = document.createElement('input');
            csrfInput.type = 'hidden';
            csrfInput.name = 'csrf_token';
            csrfInput.value = csrfToken;
            form.appendChild(csrfInput);

            // Add confirmed flag
            const confirmedInput = document.createElement('input');
            confirmedInput.type = 'hidden';
            confirmedInput.name = 'confirmed';
            confirmedInput.value = 'true';
            form.appendChild(confirmedInput);

            document.body.appendChild(form);
            form.submit();
        });

        // Backdrop click and Escape handled by createModalShell

        // Focus the cancel button for safety
        setTimeout(() => {
            cancelBtn.focus();
        }, 100);
    })
    .catch(error => {
        console.error('Error fetching template delete info:', error);
        window.showAlert(translations.errorLoading || 'Error loading deletion information. Please try again.', 'error');
    });
}

/**
 * Initialize template deletion handlers
 * Sets up event delegation for delete buttons
 */
function initTemplateDeleteHandlers() {
    // Get CSRF token from meta tag
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';

    // Get translations from data attributes on the document or use defaults
    const translations = {
        deleteTemplate: document.body.dataset.transDeleteTemplate || 'Delete Template',
        warning: document.body.dataset.transWarning || 'Warning: This action cannot be undone!',
        allWillBeDeleted: document.body.dataset.transAllWillBeDeleted || 'All of the following will be permanently deleted:',
        assignments: document.body.dataset.transAssignments || 'Assignments',
        dataEntries: document.body.dataset.transDataEntries || 'Data Entries',
        formDataEntries: document.body.dataset.transFormDataEntries || 'form data entries',
        repeatDataEntries: document.body.dataset.transRepeatDataEntries || 'repeat group data entries',
        dynamicDataEntries: document.body.dataset.transDynamicDataEntries || 'dynamic indicator data entries',
        templateStructure: document.body.dataset.transTemplateStructure || 'Template Structure',
        versions: document.body.dataset.transVersions || 'Versions',
        pages: document.body.dataset.transPages || 'page(s)',
        sections: document.body.dataset.transSections || 'section(s)',
        items: document.body.dataset.transItems || 'item(s)',
        cancel: document.body.dataset.transCancel || 'Cancel',
        errorLoading: document.body.dataset.transErrorLoading || 'Error loading deletion information. Please try again.'
    };

    // Handle delete button clicks (delegated event listener for dynamically created buttons)
    document.addEventListener('click', function(e) {
        if (e.target.closest('.delete-template-btn')) {
            e.preventDefault();
            const btn = e.target.closest('.delete-template-btn');
            const templateId = btn.getAttribute('data-template-id');
            const templateName = btn.getAttribute('data-template-name');
            const deleteUrl = btn.getAttribute('data-delete-url');
            const deleteInfoUrl = btn.getAttribute('data-delete-info-url');
            showTemplateDeleteConfirmation(templateId, templateName, deleteUrl, deleteInfoUrl, translations, csrfToken);
        }
    });
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initTemplateDeleteHandlers);
} else {
    initTemplateDeleteHandlers();
}

// Export for use in other modules if needed
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { showTemplateDeleteConfirmation, initTemplateDeleteHandlers };
}
