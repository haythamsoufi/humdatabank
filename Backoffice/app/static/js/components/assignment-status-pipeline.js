/**
 * Workflow progress tooltip: step descriptions on hover/focus, default to current step.
 */
(function () {
    'use strict';

    function initPipelineContainer(container) {
        const tooltip = container.querySelector('.assignment-status-pipeline-tooltip');
        if (!tooltip) return;

        const descLabel = tooltip.querySelector('.assignment-status-pipeline-description-label');
        const descText = tooltip.querySelector('.assignment-status-pipeline-description-text');
        const steps = Array.from(tooltip.querySelectorAll('.assignment-status-pipeline-step'));
        const pipeline = tooltip.querySelector('.assignment-status-pipeline');

        if (!descLabel || !descText || !steps.length) return;

        const parsedDefault = parseInt(tooltip.getAttribute('data-default-step-index') || '0', 10);
        const defaultIdx = Number.isFinite(parsedDefault) && parsedDefault >= 0 && parsedDefault < steps.length
            ? parsedDefault
            : 0;

        function setActiveStep(idx) {
            const step = steps[idx];
            if (!step) return;

            steps.forEach((candidate, candidateIdx) => {
                const isActive = candidateIdx === idx;
                candidate.classList.toggle('is-desc-active', isActive);
                candidate.setAttribute('aria-current', isActive ? 'step' : 'false');
            });

            descLabel.textContent = step.getAttribute('data-step-label') || '';
            descText.textContent = step.getAttribute('data-step-description') || '';
        }

        function resetToDefault() {
            setActiveStep(defaultIdx);
        }

        steps.forEach((step, idx) => {
            step.addEventListener('mouseenter', () => setActiveStep(idx));
            step.addEventListener('focus', () => setActiveStep(idx));
        });

        if (pipeline) {
            pipeline.addEventListener('mouseleave', resetToDefault);
        }

        tooltip.addEventListener('focusout', (event) => {
            if (tooltip.contains(event.relatedTarget)) return;
            resetToDefault();
        });

        resetToDefault();
    }

    function initAll() {
        document.querySelectorAll('.assignment-status-pipeline-container').forEach(initPipelineContainer);
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initAll);
    } else {
        initAll();
    }
})();
