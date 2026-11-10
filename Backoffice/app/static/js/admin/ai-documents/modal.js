/**
 * Upload/import modal and its tab list.
 */

import { loadGuidanceDocuments } from './guidance.js';
import { ensureIfrcFilterDropdowns, syncUploadImportModalIfrcCompactLayout } from './import-ifrc.js';
import { loadSystemDocuments, resizeImportDocumentsGrid } from './import-system.js';
import { cfg, page } from './shared.js';

function setActiveTab(allTabs, allPanels, activeTab, activeContent) {
    allTabs.forEach(function (tab) {
        tab.classList.remove('active', 'border-blue-500', 'text-blue-600');
        tab.classList.add('border-transparent', 'text-gray-600');
        tab.setAttribute('aria-selected', 'false');
        tab.setAttribute('tabindex', '-1');
    });
    allPanels.forEach(function (content) {
        content.classList.add('hidden');
        content.setAttribute('aria-hidden', 'true');
    });
    activeTab.classList.add('active', 'border-blue-500', 'text-blue-600');
    activeTab.classList.remove('border-transparent', 'text-gray-600');
    activeTab.setAttribute('aria-selected', 'true');
    activeTab.setAttribute('tabindex', '0');
    activeContent.classList.remove('hidden');
    activeContent.setAttribute('aria-hidden', 'false');
    const track = activeTab.closest ? activeTab.closest('.scroll-tab-bar__track') : null;
    if (track) {
        const tabRect = activeTab.getBoundingClientRect();
        const trackRect = track.getBoundingClientRect();
        const pad = 12;
        if (tabRect.left < trackRect.left + pad) track.scrollLeft -= (trackRect.left + pad) - tabRect.left;
        else if (tabRect.right > trackRect.right - pad) track.scrollLeft += tabRect.right - (trackRect.right - pad);
    }
    syncUploadImportModalIfrcCompactLayout();
}

export function initUploadModal() {
    const modal = document.getElementById('uploadImportModal');
    const openBtn = document.getElementById('openUploadModalBtn');
    const closeBtn = document.getElementById('closeUploadModalBtn');
    const uploadTab = document.getElementById('uploadTab');
    const importTab = document.getElementById('importTab');
    const ifrcApiTab = document.getElementById('ifrcApiTab');
    const guidanceTab = document.getElementById('guidanceTab');
    const uploadContent = document.getElementById('uploadContent');
    const importContent = document.getElementById('importContent');
    const ifrcApiContent = document.getElementById('ifrcApiContent');
    const guidanceContent = document.getElementById('guidanceContent');

    function closeModal() {
        if (!modal) return;
        modal.classList.add('hidden');
        modal.classList.remove('upload-import-modal--ifrc-idle');
        if (ifrcApiContent) ifrcApiContent.classList.remove('ifrc-api-tab--expanded');
        document.body.style.overflow = '';
        const fileInput = document.getElementById('fileInput');
        const uploadBtn = document.getElementById('uploadBtn');
        const uploadProgress = document.getElementById('uploadProgress');
        const dropZone = document.getElementById('dropZone');
        const docTitle = document.getElementById('docTitle');
        const selectedFilesList = document.getElementById('selectedFilesList');
        if (fileInput) fileInput.value = '';
        if (uploadBtn) uploadBtn.disabled = true;
        if (uploadProgress) uploadProgress.classList.add('hidden');
        if (docTitle) {
            docTitle.value = '';
            docTitle.disabled = false;
            docTitle.removeAttribute('title');
        }
        if (selectedFilesList) {
            selectedFilesList.innerHTML = '';
            selectedFilesList.classList.add('hidden');
        }
        if (dropZone) {
            const textElements = dropZone.querySelectorAll('p');
            if (textElements.length > 0) textElements[0].textContent = cfg.t.drag_and_drop_files_here_or_click_to_sel_d56c91ec || '';
        }
    }

    page.closeUploadModal = closeModal;
    if (!modal || !openBtn) return;

    openBtn.addEventListener('click', function () {
        modal.classList.remove('hidden');
        document.body.style.overflow = 'hidden';
        syncUploadImportModalIfrcCompactLayout();
    });
    if (closeBtn) closeBtn.addEventListener('click', closeModal);
    const importTabCancelBtn = document.getElementById('importTabCancelBtn');
    const ifrcTabCancelBtn = document.getElementById('ifrcTabCancelBtn');
    if (importTabCancelBtn) importTabCancelBtn.addEventListener('click', closeModal);
    if (ifrcTabCancelBtn) ifrcTabCancelBtn.addEventListener('click', closeModal);
    modal.addEventListener('click', function (e) {
        if (e.target === modal) closeModal();
    });
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && !modal.classList.contains('hidden')) closeModal();
    });

    if (!uploadTab || !importTab || !ifrcApiTab || !uploadContent || !importContent || !ifrcApiContent) return;
    const allTabs = [uploadTab, importTab, ifrcApiTab].concat(guidanceTab ? [guidanceTab] : []);
    const allPanels = [uploadContent, importContent, ifrcApiContent].concat(guidanceContent ? [guidanceContent] : []);

    function activateTabByIndex(idx) {
        const nextIdx = Math.max(0, Math.min(allTabs.length - 1, idx));
        const tab = allTabs[nextIdx];
        const panel = allPanels[nextIdx];
        if (!tab || !panel) return;
        setActiveTab(allTabs, allPanels, tab, panel);
        try { tab.focus(); } catch (e) { /* ignore */ }
    }

    allTabs.forEach(function (tab, idx) {
        tab.addEventListener('keydown', function (e) {
            if (!e) return;
            const key = e.key;
            if (key === 'ArrowRight') { e.preventDefault(); activateTabByIndex(idx + 1); }
            else if (key === 'ArrowLeft') { e.preventDefault(); activateTabByIndex(idx - 1); }
            else if (key === 'Home') { e.preventDefault(); activateTabByIndex(0); }
            else if (key === 'End') { e.preventDefault(); activateTabByIndex(allTabs.length - 1); }
            else if (key === 'Enter' || key === ' ') { e.preventDefault(); activateTabByIndex(idx); }
        });
    });

    uploadTab.addEventListener('click', function () {
        setActiveTab(allTabs, allPanels, uploadTab, uploadContent);
    });
    importTab.addEventListener('click', function () {
        setActiveTab(allTabs, allPanels, importTab, importContent);
        if (!importTab.dataset.loaded) {
            loadSystemDocuments();
            importTab.dataset.loaded = 'true';
        } else {
            resizeImportDocumentsGrid();
        }
    });
    if (guidanceTab && guidanceContent) {
        guidanceTab.addEventListener('click', function () {
            setActiveTab(allTabs, allPanels, guidanceTab, guidanceContent);
            if (!guidanceTab.dataset.loaded) {
                loadGuidanceDocuments();
                guidanceTab.dataset.loaded = 'true';
            }
        });
    }
    ifrcApiTab.addEventListener('click', function () {
        setActiveTab(allTabs, allPanels, ifrcApiTab, ifrcApiContent);
        if (!ifrcApiTab.dataset.loaded) {
            ifrcApiTab.dataset.loaded = 'true';
            ensureIfrcFilterDropdowns().catch(function (err) { console.error('External API tab load:', err); });
        }
    });
}
