import { debugLog } from './debug.js';

const MODULE_NAME = 'disability-questions';

function syncWashingtonGroupVisibility(container) {
    if (!container) return;
    const yesSelected = container.querySelector('input.disability-disaggregated-radio[value="yes"]:checked');
    const wgBlock = container.querySelector('.disability-washington-group-block');
    if (!wgBlock) return;
    if (yesSelected) {
        wgBlock.classList.remove('hidden');
    } else {
        wgBlock.classList.add('hidden');
        container.querySelectorAll('input.disability-washington-group-radio').forEach((input) => {
            input.checked = false;
        });
    }
}

export function initDisabilityQuestions() {
    debugLog(MODULE_NAME, 'Initializing disability questions');
    const formRoot = document.querySelector('#entry-form-ui') || document;
    formRoot.querySelectorAll('.disability-questions').forEach((container) => {
        syncWashingtonGroupVisibility(container);
    });

    formRoot.addEventListener('change', (event) => {
        const target = event.target;
        if (!(target instanceof HTMLInputElement)) return;
        if (!target.classList.contains('disability-disaggregated-radio')) return;
        const container = target.closest('.disability-questions');
        syncWashingtonGroupVisibility(container);
    });
}

document.addEventListener('repeatEntryAdded', (event) => {
    const container = event.detail?.container;
    if (!container) return;
    container.querySelectorAll('.disability-questions').forEach((block) => {
        syncWashingtonGroupVisibility(block);
    });
});
