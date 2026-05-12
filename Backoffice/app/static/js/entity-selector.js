/**
 * Entity Selector Component
 * Reusable JavaScript component for selecting and managing organizational entities
 * Can be used for user permissions and assignment management
 */

class EntitySelector {
    constructor(config) {
        this.containerId = config.containerId;
        this.apiBaseUrl = config.apiBaseUrl || '/admin';
        this.entityType = config.entityType || 'user'; // 'user' or 'assignment'
        this.targetId = config.targetId; // user_id or assignment_id
        this.filteredEntityType = config.filteredEntityType || null; // Pre-filter by entity type
        this.onAdd = config.onAdd || (() => {});
        this.onRemove = config.onRemove || (() => {});

        this.container = document.getElementById(this.containerId);
        this.entities = [];

        this.init();
    }

    init() {
        if (!this.container) {
            console.error(`Container ${this.containerId} not found`);
            return;
        }

        this.render();
        this.loadEntities();
        this.attachEventListeners();
    }

    render() {
        // Render using DOM APIs to avoid HTML injection
        this.container.replaceChildren();

        const root = document.createElement('div');
        root.className = 'entity-selector';

        // Current Entities
        const currentWrap = document.createElement('div');
        currentWrap.className = 'mb-4';

        const heading = document.createElement('h4');
        heading.className = 'text-md font-semibold text-gray-900 mb-2';
        heading.textContent = this.filteredEntityType
            ? `Assigned ${this.formatEntityTypePlural(this.filteredEntityType)}`
            : 'Assigned Entities';

        const list = document.createElement('div');
        list.id = `${this.containerId}-list`;
        list.className = 'space-y-2';

        const loading = document.createElement('div');
        loading.className = 'text-center py-4';
        const spin = document.createElement('i');
        spin.className = 'fas fa-spinner fa-spin text-gray-400';
        const loadingText = document.createElement('p');
        loadingText.className = 'text-sm text-gray-500 mt-2';
        loadingText.textContent = 'Loading entities...';
        loading.append(spin, loadingText);

        list.appendChild(loading);
        currentWrap.append(heading, list);

        // Add New Entity
        const addWrap = document.createElement('div');
        addWrap.className = 'border-t pt-4';

        const addHeading = document.createElement('h4');
        addHeading.className = 'text-md font-semibold text-gray-900 mb-2';
        addHeading.textContent = 'Add Entity';
        addWrap.appendChild(addHeading);

        // Entity Type Selector (hidden if filtered)
        if (!this.filteredEntityType) {
            const typeRow = document.createElement('div');
            typeRow.className = 'mb-2';

            const typeLabel = document.createElement('label');
            typeLabel.className = 'block text-sm font-medium text-gray-700 mb-1';
            typeLabel.textContent = 'Entity Type';

            const typeSelect = document.createElement('select');
            typeSelect.id = `${this.containerId}-type`;
            typeSelect.className = 'form-select w-full rounded-md border-gray-300';

            const optBlank = document.createElement('option');
            optBlank.value = '';
            optBlank.textContent = 'Select entity type...';
            typeSelect.appendChild(optBlank);

            const options = [
                ['country', 'Country'],
                ['ns_branch', 'NS Branch'],
                ['ns_subbranch', 'NS Sub-branch'],
                ['ns_localunit', 'NS Local Unit'],
                ['division', 'Secretariat Division'],
                ['department', 'Secretariat Department'],
            ];
            options.forEach(([value, label]) => {
                const opt = document.createElement('option');
                opt.value = value;
                opt.textContent = label;
                typeSelect.appendChild(opt);
            });

            typeRow.append(typeLabel, typeSelect);
            addWrap.appendChild(typeRow);
        }

        // Search Input
        const searchRow = document.createElement('div');
        searchRow.className = 'mb-2';
        const searchLabel = document.createElement('label');
        searchLabel.className = 'block text-sm font-medium text-gray-700 mb-1';
        searchLabel.textContent = 'Search';
        const searchInput = document.createElement('input');
        searchInput.type = 'text';
        searchInput.id = `${this.containerId}-search`;
        searchInput.className = 'form-input w-full rounded-md border-gray-300';
        searchInput.placeholder = 'Type to search...';
        if (!this.filteredEntityType) searchInput.disabled = true;
        searchRow.append(searchLabel, searchInput);
        addWrap.appendChild(searchRow);

        // Search Results
        const results = document.createElement('div');
        results.id = `${this.containerId}-results`;
        results.className = 'hidden border rounded-md p-2 max-h-48 overflow-y-auto bg-white';
        addWrap.appendChild(results);

        // Due Date (for assignments only)
        if (this.entityType === 'assignment') {
            const dueRow = document.createElement('div');
            dueRow.className = 'mb-2';
            const dueLabel = document.createElement('label');
            dueLabel.className = 'block text-sm font-medium text-gray-700 mb-1';
            dueLabel.textContent = 'Due Date (Optional)';
            const dueInput = document.createElement('input');
            dueInput.type = 'date';
            dueInput.id = `${this.containerId}-duedate`;
            dueInput.className = 'form-input w-full rounded-md border-gray-300';
            dueRow.append(dueLabel, dueInput);
            addWrap.appendChild(dueRow);
        }

        // Add Button
        const addBtn = document.createElement('button');
        addBtn.id = `${this.containerId}-add-btn`;
        addBtn.className =
            'w-full inline-flex justify-center items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed';
        addBtn.disabled = true;
        const plus = document.createElement('i');
        plus.className = 'fas fa-plus mr-2';
        addBtn.append(plus, document.createTextNode('Add Selected Entity'));
        addWrap.appendChild(addBtn);

        root.append(currentWrap, addWrap);
        this.container.appendChild(root);
    }

    attachEventListeners() {
        const typeSelect = document.getElementById(`${this.containerId}-type`);
        const searchInput = document.getElementById(`${this.containerId}-search`);
        const addBtn = document.getElementById(`${this.containerId}-add-btn`);

        // If filtered entity type is set, search is always enabled
        const entityType = this.filteredEntityType || (typeSelect ? typeSelect.value : '');

        // Enable search when type is selected (if type selector exists)
        if (typeSelect) {
            typeSelect.addEventListener('change', () => {
                const selected = typeSelect.value;
                if (selected) {
                    searchInput.disabled = false;
                    searchInput.value = '';
                    searchInput.focus();
                    this.clearResults();
                } else {
                    searchInput.disabled = true;
                    searchInput.value = '';
                    this.clearResults();
                }
                addBtn.disabled = true;
            });
        }

        // Search as user types
        let searchTimeout;
        searchInput.addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                const currentType = this.filteredEntityType || (typeSelect ? typeSelect.value : '');
                if (currentType) {
                    this.searchEntities(currentType, e.target.value);
                }
            }, 300);
        });

        // Add button click
        addBtn.addEventListener('click', () => {
            this.addSelectedEntity();
        });
    }

    async loadEntities() {
        const listContainer = document.getElementById(`${this.containerId}-list`);

        try {
            const endpoint = this.entityType === 'user'
                ? `${this.apiBaseUrl}/users/${this.targetId}/entities`
                : `${this.apiBaseUrl}/assignments/${this.targetId}/entities`;

            const apiFn = (window.getApiFetch && window.getApiFetch());
            const data = apiFn ? await apiFn(endpoint) : await ((window.getFetch && window.getFetch()) || fetch)(endpoint).then(r => r.ok ? r.json() : Promise.reject((window.httpErrorSync && window.httpErrorSync(r)) || new Error(`HTTP ${r.status}`)));

            // Filter entities by filteredEntityType if set
            let entities = data.entities || [];
            if (this.filteredEntityType) {
                entities = entities.filter(e => e.entity_type === this.filteredEntityType);
            }

            this.entities = entities;
            this.renderEntitiesList();
        } catch (error) {
            console.error('Error loading entities:', error);
            if (!listContainer) return;
            listContainer.replaceChildren();
            const wrap = document.createElement('div');
            wrap.className = 'text-center py-4';
            const icon = document.createElement('i');
            icon.className = 'fas fa-exclamation-circle text-red-500';
            const p = document.createElement('p');
            p.className = 'text-sm text-red-600 mt-2';
            p.textContent = 'Error loading entities';
            wrap.append(icon, p);
            listContainer.appendChild(wrap);
        }
    }

    renderEntitiesList() {
        const listContainer = document.getElementById(`${this.containerId}-list`);
        if (!listContainer) return;

        if (this.entities.length === 0) {
            listContainer.replaceChildren();
            const wrap = document.createElement('div');
            wrap.className = 'text-center py-4';
            const icon = document.createElement('i');
            icon.className = 'fas fa-inbox text-gray-400 text-2xl';
            const p = document.createElement('p');
            p.className = 'text-sm text-gray-500 mt-2';
            p.textContent = 'No entities assigned yet';
            wrap.append(icon, p);
            listContainer.appendChild(wrap);
            return;
        }

        listContainer.replaceChildren();
        const frag = document.createDocumentFragment();

        this.entities.forEach((entity) => {
            const root = document.createElement('div');
            root.className =
                'flex items-center justify-between p-3 bg-gray-50 rounded-md border border-gray-200 hover:bg-gray-100 transition-colors';

            const left = document.createElement('div');
            left.className = 'flex items-center space-x-3 flex-1';

            const icon = document.createElement('i');
            icon.className = `${this.getEntityIcon(entity.entity_type)} text-gray-600`;

            const meta = document.createElement('div');
            meta.className = 'flex-1';

            const nameEl = document.createElement('p');
            nameEl.className = 'text-sm font-medium text-gray-900';
            nameEl.textContent = String(entity.entity_name || entity.name || '');

            const typeEl = document.createElement('p');
            typeEl.className = 'text-xs text-gray-500';
            typeEl.textContent = this.formatEntityType(entity.entity_type);

            meta.appendChild(nameEl);
            meta.appendChild(typeEl);

            if (this.entityType === 'assignment' && entity.due_date) {
                const due = document.createElement('p');
                due.className = 'text-xs text-gray-500';
                const dueIcon = document.createElement('i');
                dueIcon.className = 'far fa-calendar mr-1';
                due.appendChild(dueIcon);
                due.appendChild(document.createTextNode(`Due: ${entity.due_date}`));
                meta.appendChild(due);
            }

            left.appendChild(icon);
            left.appendChild(meta);

            if (this.entityType === 'assignment' && entity.status) {
                const badge = this.createStatusBadge(entity.status);
                if (badge) left.appendChild(badge);
            }

            const removeBtn = document.createElement('button');
            removeBtn.className = 'ml-2 text-red-600 hover:text-red-800 entity-remove-btn';
            removeBtn.type = 'button';
            removeBtn.dataset.entityId = String(entity.permission_id || entity.status_id || '');
            removeBtn.dataset.entityName = String(entity.entity_name || entity.name || 'this entity');
            const removeIcon = document.createElement('i');
            removeIcon.className = 'fas fa-times';
            removeBtn.appendChild(removeIcon);

            root.appendChild(left);
            root.appendChild(removeBtn);
            frag.appendChild(root);
        });

        listContainer.appendChild(frag);

        // Add event listeners to remove buttons
        const removeButtons = listContainer.querySelectorAll('.entity-remove-btn');
        removeButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                const id = parseInt(btn.dataset.entityId);
                const name = btn.dataset.entityName;
                this.removeEntity(id, name);
            });
        });
    }

    async searchEntities(entityType, query) {
        const resultsContainer = document.getElementById(`${this.containerId}-results`);
        if (!resultsContainer) return;

        if (!entityType) {
            this.clearResults();
            return;
        }

        if (query.length < 2) {
            resultsContainer.replaceChildren();
            const p = document.createElement('p');
            p.className = 'text-sm text-gray-500 p-2';
            p.textContent = 'Type at least 2 characters...';
            resultsContainer.appendChild(p);
            resultsContainer.classList.remove('hidden');
            return;
        }

        resultsContainer.replaceChildren();
        const loading = document.createElement('p');
        loading.className = 'text-sm text-gray-500 p-2';
        const spin = document.createElement('i');
        spin.className = 'fas fa-spinner fa-spin mr-2';
        loading.append(spin, document.createTextNode('Searching...'));
        resultsContainer.appendChild(loading);
        resultsContainer.classList.remove('hidden');

        try {
            const url = `${this.apiBaseUrl}/entities/search?type=${entityType}&q=${encodeURIComponent(query)}`;
            const apiFn = (window.getApiFetch && window.getApiFetch());
            const data = apiFn ? await apiFn(url) : await ((window.getFetch && window.getFetch()) || fetch)(url).then(r => r.ok ? r.json() : Promise.reject((window.httpErrorSync && window.httpErrorSync(r)) || new Error(`HTTP ${r.status}`)));

            if (data.results && data.results.length > 0) {
                resultsContainer.replaceChildren();
                const frag = document.createDocumentFragment();
                data.results.forEach((result) => {
                    const el = document.createElement('div');
                    el.className =
                        'p-2 hover:bg-blue-50 cursor-pointer rounded border-b border-gray-200 last:border-b-0 entity-search-result';
                    el.dataset.id = String(result.id);
                    el.dataset.name = String(result.display_name || result.name || '');

                    const p = document.createElement('p');
                    p.className = 'text-sm font-medium text-gray-900';
                    p.textContent = String(result.display_name || result.name || '');
                    el.appendChild(p);

                    el.addEventListener('click', () => {
                        this.selectEntity(el.dataset.id, el.dataset.name);
                    });

                    frag.appendChild(el);
                });
                resultsContainer.appendChild(frag);
            } else {
                resultsContainer.replaceChildren();
                const p = document.createElement('p');
                p.className = 'text-sm text-gray-500 p-2';
                p.textContent = 'No results found';
                resultsContainer.appendChild(p);
            }
        } catch (error) {
            console.error('Error searching entities:', error);
            resultsContainer.replaceChildren();
            const p = document.createElement('p');
            p.className = 'text-sm text-red-600 p-2';
            p.textContent = 'Error searching entities';
            resultsContainer.appendChild(p);
        }
    }

    selectEntity(id, name) {
        const typeSelect = document.getElementById(`${this.containerId}-type`);
        const searchInput = document.getElementById(`${this.containerId}-search`);
        const addBtn = document.getElementById(`${this.containerId}-add-btn`);

        const entityType = this.filteredEntityType || (typeSelect ? typeSelect.value : '');

        this.selectedEntity = {
            id: parseInt(id),
            name: name,
            type: entityType
        };

        searchInput.value = name;
        addBtn.disabled = false;
        this.clearResults();
    }

    async addSelectedEntity() {
        if (!this.selectedEntity) return;

        const addBtn = document.getElementById(`${this.containerId}-add-btn`);
        addBtn.disabled = true;
        addBtn.replaceChildren();
        const spin = document.createElement('i');
        spin.className = 'fas fa-spinner fa-spin mr-2';
        addBtn.append(spin, document.createTextNode('Adding...'));

        try {
            const endpoint = this.entityType === 'user'
                ? `${this.apiBaseUrl}/users/${this.targetId}/entities/add`
                : `${this.apiBaseUrl}/assignments/${this.targetId}/entities/add`;

            const body = {
                entity_type: this.selectedEntity.type,
                entity_id: this.selectedEntity.id
            };

            // Add due date for assignments
            if (this.entityType === 'assignment') {
                const dueDateInput = document.getElementById(`${this.containerId}-duedate`);
                if (dueDateInput.value) {
                    body.due_date = dueDateInput.value;
                }
            }

            const apiFn = (window.getApiFetch && window.getApiFetch());
            const data = apiFn
                ? await apiFn(endpoint, { method: 'POST', body: JSON.stringify(body) })
                : await ((window.getFetch && window.getFetch()) || fetch)(endpoint, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }).then(r => r.ok ? r.json() : Promise.reject((window.httpErrorSync && window.httpErrorSync(r)) || new Error(`HTTP ${r.status}`)));

            if (data && data.success) {
                this.showMessage('Entity added successfully!', 'success');
                this.loadEntities();
                this.resetForm();
                this.onAdd(data);
            } else {
                this.showMessage(data.error || 'Error adding entity', 'error');
            }
        } catch (error) {
            console.error('Error adding entity:', error);
            this.showMessage('Error adding entity', 'error');
        } finally {
            addBtn.disabled = false;
            addBtn.replaceChildren();
            const plus = document.createElement('i');
            plus.className = 'fas fa-plus mr-2';
            addBtn.append(plus, document.createTextNode('Add Selected Entity'));
        }
    }

    async removeEntity(id, name) {
        const msg = `Remove ${name}?`;
        const doRemove = async () => {
        try {
            const endpoint = this.entityType === 'user'
                ? `${this.apiBaseUrl}/users/${this.targetId}/entities/remove/${id}`
                : `${this.apiBaseUrl}/assignments/${this.targetId}/entities/remove/${id}`;

            const apiFn = (window.getApiFetch && window.getApiFetch());
            const data = apiFn
                ? await apiFn(endpoint, { method: 'DELETE' })
                : await ((window.getFetch && window.getFetch()) || fetch)(endpoint, { method: 'DELETE' }).then(r => r.ok ? r.json() : Promise.reject((window.httpErrorSync && window.httpErrorSync(r)) || new Error(`HTTP ${r.status}`)));

            if (data && data.success) {
                this.showMessage('Entity removed successfully!', 'success');
                this.loadEntities();
                this.onRemove(data);
            } else {
                this.showMessage('Error removing entity', 'error');
            }
        } catch (error) {
            console.error('Error removing entity:', error);
            this.showMessage('Error removing entity', 'error');
        }
        };
        if (window.showDangerConfirmation) {
            window.showDangerConfirmation(msg, () => { void doRemove(); }, null, 'Remove', 'Cancel', 'Remove Entity?');
        } else if (window.showConfirmation) {
            window.showConfirmation(msg, () => { void doRemove(); }, null, 'Remove', 'Cancel', 'Remove Entity?');
        } else {
            console.warn('Confirmation dialog not available:', msg);
        }
    }

    resetForm() {
        const typeSelect = document.getElementById(`${this.containerId}-type`);
        const searchInput = document.getElementById(`${this.containerId}-search`);
        const addBtn = document.getElementById(`${this.containerId}-add-btn`);

        if (typeSelect) {
            typeSelect.value = '';
        }

        if (searchInput) {
            searchInput.value = '';
            // Only disable search if we don't have a filtered entity type
            if (!this.filteredEntityType) {
                searchInput.disabled = true;
            }
        }

        if (addBtn) {
            addBtn.disabled = true;
        }

        if (this.entityType === 'assignment') {
            const dueDateInput = document.getElementById(`${this.containerId}-duedate`);
            if (dueDateInput) {
                dueDateInput.value = '';
            }
        }

        this.selectedEntity = null;
        this.clearResults();
    }

    clearResults() {
        const resultsContainer = document.getElementById(`${this.containerId}-results`);
        if (!resultsContainer) return;
        resultsContainer.replaceChildren();
        resultsContainer.classList.add('hidden');
    }

    getEntityIcon(entityType) {
        const icons = {
            'country': 'fas fa-flag',
            'ns_branch': 'fas fa-sitemap',
            'ns_subbranch': 'fas fa-code-branch',
            'ns_localunit': 'fas fa-map-marker-alt',
            'division': 'fas fa-building',
            'department': 'fas fa-briefcase'
        };
        return icons[entityType] || 'fas fa-folder';
    }

    formatEntityType(entityType) {
        const names = {
            'country': 'Country',
            'ns_branch': 'NS Branch',
            'ns_subbranch': 'NS Sub-branch',
            'ns_localunit': 'NS Local Unit',
            'division': 'Secretariat Division',
            'department': 'Secretariat Department'
        };
        return names[entityType] || entityType;
    }

    formatEntityTypePlural(entityType) {
        const plurals = {
            'country': 'Countries',
            'ns_branch': 'NS Branches',
            'ns_subbranch': 'NS Sub-branches',
            'ns_localunit': 'NS Local Units',
            'division': 'Secretariat Divisions',
            'department': 'Secretariat Departments'
        };
        return plurals[entityType] || `${this.formatEntityType(entityType)}s`;
    }

    createStatusBadge(status) {
        const statusColors = {
            'Pending': 'bg-yellow-100 text-yellow-800',
            'In Progress': 'bg-blue-100 text-blue-800',
            'Submitted': 'bg-green-100 text-green-800',
            'Approved': 'bg-green-100 text-green-800',
            'Rejected': 'bg-red-100 text-red-800'
        };
        const colorClass = statusColors[status] || 'bg-gray-100 text-gray-800';
        const span = document.createElement('span');
        span.className = `px-2 py-1 text-xs font-semibold rounded-full ${colorClass}`;
        span.textContent = String(status || '');
        return span;
    }

    showMessage(message, type) {
        const category = type === 'success' ? 'success' : 'danger';
        if (typeof window.showFlashMessage === 'function') {
            window.showFlashMessage(String(message || ''), category);
        }
    }
}

// Export for global use
window.EntitySelector = EntitySelector;
