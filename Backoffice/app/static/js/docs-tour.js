/**
 * Documentation tour button handler
 * Handles starting interactive tours from documentation pages
 */

(function() {
    'use strict';

    // Delegate clicks so it keeps working after AJAX navigation updates the header.
    document.addEventListener('click', async function(e) {
        const tourButton = e.target.closest('#start-tour-btn');
        if (!tourButton) return;

        e.preventDefault();
        e.stopPropagation();

        const workflowId = tourButton.getAttribute('data-workflow');
        if (!workflowId) return;

        // Disable button during loading
        tourButton.disabled = true;
        tourButton.style.opacity = '0.6';
        const labelEl = tourButton.querySelector('span');
        const originalText = labelEl ? labelEl.textContent : '';
        if (labelEl) labelEl.textContent = 'Loading...';

        try {
            // Fetch workflow details to get the first page
            let targetPage = '/dashboard';
            let data;
            const apiFn = (window.getApiFetch && window.getApiFetch());
            if (apiFn) {
                data = await apiFn(`/api/ai/documents/workflows/${workflowId}`);
            } else {
                const fn = (window.getFetch && window.getFetch()) || fetch;
                const r = await fn(`/api/ai/documents/workflows/${workflowId}`, { credentials: 'same-origin' });
                if (!r.ok) throw (window.httpErrorSync && window.httpErrorSync(r, `Workflow lookup failed (HTTP ${r.status})`)) || new Error(`Workflow lookup failed (HTTP ${r.status})`);
                data = await r.json();
            }
            if (!data || !data.success || !data.workflow) {
                throw new Error('Workflow lookup failed (bad response)');
            }
            if (data.workflow.pages && data.workflow.pages.length > 0) {
                targetPage = data.workflow.pages[0];
            }

            // Use WorkflowTourParser if available
            if (window.WorkflowTourParser && typeof window.WorkflowTourParser.handleTourTrigger === 'function') {
                window.WorkflowTourParser.handleTourTrigger(workflowId, targetPage);
            } else {
                // Fallback: navigate with tour hash
                window.location.href = `${targetPage}#chatbot-tour=${workflowId}&step=1`;
            }
        } catch (err) {
            console.warn('Tour start failed:', err);
            if (window.showAlert) window.showAlert('This guide does not have an interactive tour available yet.', 'info');
        } finally {
            // Re-enable button (in case we stayed on page)
            tourButton.disabled = false;
            tourButton.style.opacity = '1';
            if (labelEl) labelEl.textContent = originalText;
        }
    });
})();
