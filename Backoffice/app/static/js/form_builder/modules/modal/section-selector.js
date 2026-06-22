import { DataManager } from '../data-manager.js';

export const SectionSelectorMixin = {
    setupSectionSelector: function() {},

    // Keep "Section" proxy dropdowns inside plugin builders in sync with the main section selector.
    // Plugin builder templates can declare: <select data-section-proxy="true"> (no name attr).
    syncSectionProxyDropdowns: function() {
        if (!this.modalElement) return;

        const mainSelect = this.modalElement.querySelector('#item-section-select');
        if (!mainSelect) return;

        const proxies = Array.from(this.modalElement.querySelectorAll('select[data-section-proxy="true"]'));
        if (proxies.length === 0) return;

        const optionData = Array.from(mainSelect.options).map((opt) => ({
            value: opt.value,
            text: opt.textContent || ''
        }));

        for (const proxy of proxies) {
            // Rebuild options if empty or out of sync (cheap; options count is small)
            const needsRebuild =
                proxy.options.length !== optionData.length ||
                Array.from(proxy.options).some((o, i) => o.value !== optionData[i]?.value || (o.textContent || '') !== optionData[i]?.text);

            if (needsRebuild) {
                proxy.replaceChildren();
                optionData.forEach(({ value, text }) => {
                    const o = document.createElement('option');
                    o.value = value;
                    o.textContent = text;
                    proxy.appendChild(o);
                });
            }

            // Mirror selection
            if (proxy.value !== mainSelect.value) {
                proxy.value = mainSelect.value;
            }

            // Wire one-time change handler
            if (!proxy.dataset.sectionProxyWired) {
                proxy.dataset.sectionProxyWired = 'true';
                proxy.addEventListener('change', () => {
                    // Avoid loops: only write if changed
                    if (mainSelect.value !== proxy.value) {
                        mainSelect.value = proxy.value;
                        // Let existing listeners update hidden field + order
                        mainSelect.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                });
            }
        }
    },

    setupSectionProxyObserver: function() {
        if (!this.modalElement) return;
        // Tear down any existing observer
        if (this._sectionProxyObserver) {
            try { this._sectionProxyObserver.disconnect(); } catch (_) {}
            this._sectionProxyObserver = null;
        }

        // Observe plugin container (where builder HTML is injected) to sync proxies when they appear
        const pluginContainer =
            this.modalElement.querySelector('#plugin-configuration-container') ||
            this.modalElement.querySelector('#item-plugin-fields-container') ||
            this.modalElement;

        let rafQueued = false;
        const scheduleSync = () => {
            if (rafQueued) return;
            rafQueued = true;
            requestAnimationFrame(() => {
                rafQueued = false;
                this.syncSectionProxyDropdowns();
            });
        };

        this._sectionProxyObserver = new MutationObserver(() => scheduleSync());
        try {
            this._sectionProxyObserver.observe(pluginContainer, { childList: true, subtree: true });
        } catch (_) {
            // no-op
        }

        // Also keep proxies updated if the main selector changes (e.g., user changes section in Properties)
        const mainSelect = this.modalElement.querySelector('#item-section-select');
        if (mainSelect && !mainSelect.dataset.sectionProxyMainWired) {
            mainSelect.dataset.sectionProxyMainWired = 'true';
            mainSelect.addEventListener('change', () => this.syncSectionProxyDropdowns());
        }

        // Initial pass
        this.syncSectionProxyDropdowns();
    },

    populateSectionSelector: function() {
        if (!this.modalElement) return;

        const sectionSelect = this.modalElement.querySelector('#item-section-select');
        if (!sectionSelect) return;

        // Get sections from DataManager
        const sections = (DataManager && typeof DataManager.getData === 'function')
            ? (DataManager.getData('allTemplateSections') || [])
            : [];

        // Clear existing options except the first placeholder
        sectionSelect.replaceChildren();
        {
            const placeholder = document.createElement('option');
            placeholder.value = '';
            placeholder.textContent = 'Select a section...';
            sectionSelect.appendChild(placeholder);
        }

        // Add sections to dropdown
        sections.forEach(section => {
            // Handle both [id, name] array format and {id, name} object format
            const sectionId = Array.isArray(section) ? section[0] : (section.id || section.value);
            const sectionName = Array.isArray(section) ? section[1] : (section.name || section.label);

            if (sectionId && sectionName) {
                const option = document.createElement('option');
                option.value = String(sectionId);
                option.textContent = sectionName;
                sectionSelect.appendChild(option);
            }
        });

        // Remove existing change listener if any (avoid duplicates on repeated calls)
        if (sectionSelect._sectionChangeHandler) {
            sectionSelect.removeEventListener('change', sectionSelect._sectionChangeHandler);
        }

        // Sync with hidden field when dropdown changes
        sectionSelect._sectionChangeHandler = (e) => {
            const hiddenSectionId = this.modalElement.querySelector('#item-modal-section-id');
            if (hiddenSectionId) {
                hiddenSectionId.value = e.target.value;
            }

            // Update currentSectionId
            this.currentSectionId = e.target.value;

            const itemType = this.currentItemType || 'question';
            if (this.ensureUniqueOptionsInSectionField) {
                this.ensureUniqueOptionsInSectionField(itemType);
            }
            if (this.ensureLimitEntriesToOptionCountField) {
                this.ensureLimitEntriesToOptionCountField(itemType);
            }
            if (this.ensureUseAsRepeatEntryTitleField) {
                this.ensureUseAsRepeatEntryTitleField(itemType);
            }

            // Recalculate default order for the new section (only in add mode)
            if (this.currentMode === 'add' && e.target.value) {
                this.setDefaultOrderValue(e.target.value);
            }
        };
        sectionSelect.addEventListener('change', sectionSelect._sectionChangeHandler);

        return sectionSelect;
    },

    setDefaultOrderValue: function(sectionId) {
        // Find the order input field
        const orderInput = this.modalElement.querySelector('#item-order');
        if (!orderInput) return;

        // Get the current section's items to calculate the next order
        const sectionItems = (DataManager && typeof DataManager.getData === 'function')
            ? (DataManager.getData('sectionsWithItems') || [])
            : (window.sectionsWithItemsForJs || []);
        // Compare IDs robustly (string vs number)
        const currentSection = sectionItems.find(s => String(s.id) === String(sectionId));

        if (currentSection && currentSection.form_items && currentSection.form_items.length > 0) {
            // Find the highest order value in the current section
            const maxOrder = Math.max(...currentSection.form_items.map(item => parseFloat(item.order) || 0));
            const nextOrder = maxOrder + 1;
            orderInput.value = nextOrder;

        } else {
            // If no items in section, start with order 1
            orderInput.value = 1;

        }
    },

    getActiveSectionId: function() {
        if (!this.modalElement) return this.currentSectionId || null;
        const sectionSelect = this.modalElement.querySelector('#item-section-select');
        const hiddenSectionId = this.modalElement.querySelector('#item-modal-section-id');
        return (sectionSelect && sectionSelect.value)
            || (hiddenSectionId && hiddenSectionId.value)
            || this.currentSectionId
            || null;
    },

    isRepeatSection: function(sectionId) {
        if (!sectionId) return false;

        const sections = (DataManager && typeof DataManager.getData === 'function')
            ? (DataManager.getData('allTemplateSections') || [])
            : [];

        const section = sections.find(s => {
            const id = Array.isArray(s) ? s[0] : (s.id ?? s.value);
            return String(id) === String(sectionId);
        });

        if (section && !Array.isArray(section)) {
            const st = String(section.section_type || '').toLowerCase();
            if (st === 'repeat') return true;
        }

        // DOM fallback (form builder section cards)
        const editBtn = document.querySelector(`.edit-section-btn[data-section-id="${sectionId}"]`);
        if (editBtn) {
            const domType = String(editBtn.getAttribute('data-section-type') || '').toLowerCase();
            if (domType === 'repeat') return true;
        }

        return false;
    },
};
