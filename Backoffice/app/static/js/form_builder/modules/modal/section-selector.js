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

            // Add mode picks the next top-level order. Edit mode keeps the
            // current position and only refreshes which parents exist.
            if (this.currentMode === 'add' && e.target.value) {
                this.setDefaultOrderValue(e.target.value);
            } else {
                const parentSelect = this.modalElement.querySelector('#item-parent-order');
                this.refreshItemParentOptions(parentSelect ? parentSelect.value : '');
                this.syncOrderInputMode();
            }
        };
        sectionSelect.addEventListener('change', sectionSelect._sectionChangeHandler);

        return sectionSelect;
    },

    setDefaultOrderValue: function(sectionId) {
        const orderInput = this.modalElement.querySelector('#item-order');
        if (!orderInput) return;

        this.refreshItemParentOptions('');
        const items = this.getSectionFormItems(sectionId);
        orderInput.value = String(this.nextMainItemOrder(items));
        this.syncOrderInputMode();
    },

    /**
     * Whole-number order is the position. A parent selection makes the field
     * a sub-item; the stored value stays a tenth (parent + position/10) so
     * existing sub-item rendering keeps working.
     */
    getSectionFormItems: function(sectionId) {
        const id = sectionId != null && sectionId !== '' ? sectionId : this.getActiveSectionId();
        if (id == null || id === '') return [];
        const sections = (DataManager && typeof DataManager.getData === 'function')
            ? (DataManager.getData('sectionsWithItems') || [])
            : (window.sectionsWithItemsForJs || []);
        const section = sections.find(s => String(s.id) === String(id));
        return (section && Array.isArray(section.form_items)) ? section.form_items : [];
    },

    splitStoredOrder: function(order) {
        const n = parseFloat(order);
        if (!Number.isFinite(n) || n < 0) return { parent: '', position: '' };
        const rounded = Math.round(n * 10) / 10;
        const parent = Math.floor(rounded + 1e-6);
        const tenth = Math.round((rounded - parent) * 10);
        if (tenth <= 0) return { parent: '', position: String(parent) };
        return { parent: String(parent), position: String(Math.min(9, tenth)) };
    },

    composeStoredOrder: function(positionRaw, parentRaw) {
        const positionText = String(positionRaw ?? '').trim();
        if (!positionText) return '';
        const position = parseInt(positionText, 10);
        if (!Number.isFinite(position) || position < 0) return '';
        const parentText = String(parentRaw ?? '').trim();
        if (!parentText) return String(position);
        const parent = parseInt(parentText, 10);
        if (!Number.isFinite(parent) || parent < 0) return String(position);
        const sub = Math.min(9, Math.max(1, position));
        return (parent + sub / 10).toFixed(1);
    },

    nextMainItemOrder: function(items) {
        const excludeId = this.currentItemId;
        let max = 0;
        (items || []).forEach((item) => {
            if (excludeId != null && String(item.item_id) === String(excludeId)) return;
            const split = this.splitStoredOrder(item.order);
            if (split.parent || !split.position) return;
            const n = parseInt(split.position, 10);
            if (Number.isFinite(n)) max = Math.max(max, n);
        });
        return max + 1;
    },

    nextSubItemPosition: function(items, parentOrder) {
        const excludeId = this.currentItemId;
        const used = new Set();
        (items || []).forEach((item) => {
            if (excludeId != null && String(item.item_id) === String(excludeId)) return;
            const split = this.splitStoredOrder(item.order);
            if (split.parent !== String(parentOrder)) return;
            const n = parseInt(split.position, 10);
            if (Number.isFinite(n)) used.add(n);
        });
        for (let i = 1; i <= 9; i += 1) {
            if (!used.has(i)) return i;
        }
        return 9;
    },

    refreshItemParentOptions: function(preferredParent) {
        if (!this.modalElement) return;
        const select = this.modalElement.querySelector('#item-parent-order');
        if (!select) return;
        this.wireItemOrderControls();

        const mainLabel = select.getAttribute('data-label-main') || 'Main item';
        const itemLabel = select.getAttribute('data-label-item') || 'Item';
        const archivedLabel = select.getAttribute('data-label-archived') || 'archived';
        const wanted = preferredParent != null ? String(preferredParent) : (select.value || '');
        const items = this.getSectionFormItems();
        const excludeId = this.currentItemId;

        const parents = items
            .filter((item) => {
                if (excludeId != null && String(item.item_id) === String(excludeId)) return false;
                const split = this.splitStoredOrder(item.order);
                if (!split.position || split.parent) return false;
                if (item.archived && split.position !== wanted) return false;
                return true;
            })
            .sort((a, b) => (parseFloat(a.order) || 0) - (parseFloat(b.order) || 0));

        select.replaceChildren();
        const mainOpt = document.createElement('option');
        mainOpt.value = '';
        mainOpt.textContent = mainLabel;
        select.appendChild(mainOpt);

        const seen = new Set();
        parents.forEach((item) => {
            const split = this.splitStoredOrder(item.order);
            if (seen.has(split.position)) return;
            seen.add(split.position);
            const opt = document.createElement('option');
            opt.value = split.position;
            const label = String(item.label || '').trim();
            const shortLabel = label.length > 80 ? `${label.slice(0, 77)}…` : label;
            let text = shortLabel ? `${split.position} — ${shortLabel}` : `${itemLabel} ${split.position}`;
            if (item.archived) text += ` (${archivedLabel})`;
            opt.textContent = text;
            select.appendChild(opt);
        });

        if (wanted && !seen.has(wanted)) {
            const missing = document.createElement('option');
            missing.value = wanted;
            missing.textContent = `${itemLabel} ${wanted}`;
            select.appendChild(missing);
        }
        const hasWanted = wanted && Array.from(select.options).some((opt) => opt.value === wanted);
        select.value = hasWanted ? wanted : '';
    },

    applyStoredItemOrder: function(order) {
        if (!this.modalElement) return;
        const orderInput = this.modalElement.querySelector('#item-order');
        const split = this.splitStoredOrder(order);
        this.refreshItemParentOptions(split.parent);
        if (orderInput) orderInput.value = split.position;
        this.syncOrderInputMode();
    },

    syncOrderInputMode: function() {
        if (!this.modalElement) return;
        const orderInput = this.modalElement.querySelector('#item-order');
        const parentSelect = this.modalElement.querySelector('#item-parent-order');
        if (!orderInput) return;
        const hasParent = !!(parentSelect && parentSelect.value);
        orderInput.step = '1';
        orderInput.min = hasParent ? '1' : '0';
        if (hasParent) orderInput.max = '9';
        else orderInput.removeAttribute('max');
    },

    wireItemOrderControls: function() {
        if (!this.modalElement) return;
        const orderInput = this.modalElement.querySelector('#item-order');
        const parentSelect = this.modalElement.querySelector('#item-parent-order');
        if (orderInput && !orderInput.dataset.orderWired) {
            orderInput.dataset.orderWired = 'true';
            orderInput.addEventListener('input', () => {
                const raw = String(orderInput.value ?? '');
                const digits = raw.split(/[.,]/, 1)[0].replace(/[^\d]/g, '');
                let next = digits;
                const parent = parentSelect && parentSelect.value;
                if (digits && parent) {
                    let n = parseInt(digits, 10);
                    if (n < 1) n = 1;
                    if (n > 9) n = 9;
                    next = String(n);
                }
                if (orderInput.value !== next) orderInput.value = next;
            });
        }
        if (parentSelect && !parentSelect.dataset.parentWired) {
            parentSelect.dataset.parentWired = 'true';
            parentSelect.addEventListener('change', () => {
                this.syncOrderInputMode();
                if (!orderInput) return;
                const parent = parentSelect.value;
                const pos = parseInt(orderInput.value, 10);
                const invalid = !Number.isFinite(pos);
                if (parent && (invalid || pos < 1 || pos > 9)) {
                    orderInput.value = String(this.nextSubItemPosition(this.getSectionFormItems(), parent));
                } else if (!parent && invalid) {
                    orderInput.value = String(this.nextMainItemOrder(this.getSectionFormItems()));
                }
            });
        }
    },

    composeItemOrderForSubmit: function() {
        if (!this.modalElement) return;
        const orderInput = this.modalElement.querySelector('#item-order');
        const parentSelect = this.modalElement.querySelector('#item-parent-order');
        const hidden = this.modalElement.querySelector('#item-order-value');
        if (!orderInput || !hidden) return;
        let position = orderInput.value;
        if (parentSelect && parentSelect.value && !String(position).trim()) {
            position = '1';
            orderInput.value = position;
        }
        hidden.value = this.composeStoredOrder(position, parentSelect ? parentSelect.value : '');
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
