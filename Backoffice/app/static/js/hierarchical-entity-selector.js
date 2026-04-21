/**
 * Hierarchical Entity Selector Component
 * Displays entities in a tree structure with checkboxes for permission assignment
 */
// Prevent duplicate declaration
if (typeof HierarchicalEntitySelector === 'undefined') {
window.HierarchicalEntitySelector = class HierarchicalEntitySelector {
    constructor(config) {
        this.containerId = config.containerId;
        // Allow empty string for apiBaseUrl (explicit check for undefined)
        this.apiBaseUrl = config.apiBaseUrl !== undefined ? config.apiBaseUrl : '/admin';
        this.targetUserId = config.targetUserId;
        this.entityTypes = config.entityTypes || []; // Array of entity types to show (e.g., ['ns_branch', 'ns_subbranch', 'ns_localunit'])
        this.onChange = config.onChange || (() => {});

        this.container = document.getElementById(this.containerId);
        this.hierarchy = [];
        this.assignedEntities = new Set(); // Set of assigned entity IDs with type: "type:id"
        this.expandedNodes = new Set(); // Set of expanded node keys

        this.init();
    }

    toString(value) {
        if (value === null || value === undefined) return '';
        return String(value);
    }

    // For safe interpolation into HTML text nodes (e.g. <div>TEXT</div>)
    escapeHtmlText(value) {
        return this.toString(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    // For safe interpolation into HTML attribute values (e.g. data-x="ATTR")
    escapeHtmlAttr(value) {
        return this.toString(value)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    // Helper method to construct URLs correctly
    buildUrl(path) {
        // If path starts with /, use it as absolute URL
        if (path.startsWith('/')) {
            return path;
        }
        // Otherwise, combine with apiBaseUrl
        return `${this.apiBaseUrl}${this.apiBaseUrl && !this.apiBaseUrl.endsWith('/') && !path.startsWith('/') ? '/' : ''}${path}`;
    }

    // Helper method to get CSRF token
    getCSRFToken() {
        // Try to get from meta tag first
        const metaTag = document.querySelector('meta[name="csrf-token"]');
        if (metaTag) {
            return metaTag.getAttribute('content');
        }
        // Fallback to form input
        const csrfInput = document.querySelector('input[name="csrf_token"]');
        if (csrfInput) {
            return csrfInput.value;
        }
        // Fallback to global variable if available
        if (typeof window !== 'undefined' && window.rawCsrfTokenValue) {
            return window.rawCsrfTokenValue;
        }
        return null;
    }

    async init() {
        if (!this.container) {
            console.error(`Container ${this.containerId} not found`);
            return;
        }

        // Load assigned entities for this user
        await this.loadAssignedEntities();

        // Render will be called after hierarchy is loaded
    }

    async loadAssignedEntities() {
        if (!this.targetUserId) return;

        try {
            const fn = (window.getFetch && window.getFetch()) || fetch;
            const response = await fn(this.buildUrl(`/admin/users/${this.targetUserId}/entities`));
            const data = await response.json();

            // Filter to only entity types we're displaying
            const entities = data.entities || [];
            for (const entity of entities) {
                if (this.entityTypes.includes(entity.entity_type)) {
                    this.assignedEntities.add(`${entity.entity_type}:${entity.entity_id}`);
                }
            }

            // Initialize hidden form fields with existing permissions
            this.updateHiddenFormFields();
        } catch (error) {
            console.error('Error loading assigned entities:', error);
        }
    }

    async loadHierarchy(hierarchyEndpoint) {
        try {
            const fn = (window.getFetch && window.getFetch()) || fetch;
            const response = await fn(this.buildUrl(hierarchyEndpoint));
            const data = await response.json();
            this.hierarchy = data.hierarchy || [];
            this.render();
        } catch (error) {
            console.error('Error loading hierarchy:', error);
            if (!this.container) return;
            this.container.replaceChildren();
            const wrap = document.createElement('div');
            wrap.className = 'text-center py-4';
            const icon = document.createElement('i');
            icon.className = 'fas fa-exclamation-circle text-red-500';
            const p = document.createElement('p');
            p.className = 'text-sm text-red-600 mt-2';
            p.textContent = 'Error loading hierarchy';
            wrap.append(icon, p);
            this.container.appendChild(wrap);
        }
    }

    render() {
        if (this.hierarchy.length === 0) {
            this.container.replaceChildren();
            const wrap = document.createElement('div');
            wrap.className = 'text-center py-4';
            const icon = document.createElement('i');
            icon.className = 'fas fa-inbox text-gray-400 text-2xl';
            const p = document.createElement('p');
            p.className = 'text-sm text-gray-500 mt-2';
            p.textContent = 'No structure defined yet';
            wrap.append(icon, p);
            this.container.appendChild(wrap);
            return;
        }

        this.container.replaceChildren();
        const treeRoot = this.renderTree(this.hierarchy, 0);
        if (treeRoot) {
            this.container.appendChild(treeRoot);
        }
        this.attachEventListeners();
    }

    renderTree(nodes, level) {
        const ul = document.createElement('ul');
        ul.className = 'space-y-1';

        for (const node of nodes) {
            const hasChildren = node.children && node.children.length > 0;
            const nodeKey = `${this.toString(node.type)}:${this.toString(node.id)}`;
            const isExpanded = this.expandedNodes.has(nodeKey);
            const isAssigned = this.assignedEntities.has(nodeKey);
            const icon = this.getEntityIcon(node.type);

            // If this node type is not in our entity types list, but it has children, render children only
            if (!this.entityTypes.includes(node.type)) {
                if (hasChildren) {
                    // Flatten country grouping by rendering children directly without a header
                    if (node.type === 'country') {
                        const childrenTree = this.renderTree(node.children, 0);
                        if (childrenTree) {
                            // Append children directly to current ul
                            Array.from(childrenTree.children).forEach(child => ul.appendChild(child));
                        }
                    } else {
                        // For other non-selectable nodes, just render children
                        const childrenTree = this.renderTree(node.children, level);
                        if (childrenTree) {
                            Array.from(childrenTree.children).forEach(child => ul.appendChild(child));
                        }
                    }
                }
                continue;
            }

            // Calculate indentation based on level (adjust if we're skipping country level)
            const indentClass = level === 0 ? '' : level === 1 ? 'ml-6' : level === 2 ? 'ml-12' : 'ml-16';

            const li = document.createElement('li');
            li.className = indentClass;

            const itemDiv = document.createElement('div');
            itemDiv.className = 'flex items-center py-1 px-2 hover:bg-gray-50 rounded';

            if (hasChildren) {
                const expandBtn = document.createElement('button');
                expandBtn.type = 'button';
                expandBtn.className = 'expand-btn mr-2 text-gray-500 hover:text-gray-700 focus:outline-none';
                expandBtn.setAttribute('data-node-key', nodeKey);
                expandBtn.setAttribute('data-expanded', isExpanded.toString());
                const chevronIcon = document.createElement('i');
                chevronIcon.className = `fas fa-chevron-${isExpanded ? 'down' : 'right'} text-xs`;
                expandBtn.appendChild(chevronIcon);
                itemDiv.appendChild(expandBtn);
            } else {
                const spacer = document.createElement('span');
                spacer.className = 'mr-4';
                itemDiv.appendChild(spacer);
            }

            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.className = 'entity-checkbox h-4 w-4 text-blue-600 border-gray-300 rounded focus:ring-blue-500';
            checkbox.setAttribute('data-entity-type', node.type);
            checkbox.setAttribute('data-entity-id', node.id.toString());
            checkbox.setAttribute('data-entity-name', node.name);
            checkbox.checked = isAssigned;
            itemDiv.appendChild(checkbox);

            const iconEl = document.createElement('i');
            iconEl.className = `${icon} ml-2 mr-2 text-gray-600`;
            itemDiv.appendChild(iconEl);

            const label = document.createElement('label');
            label.className = 'text-sm text-gray-900 cursor-pointer flex-1';
            label.appendChild(document.createTextNode(node.name));
            if (node.code) {
                const codeSpan = document.createElement('span');
                codeSpan.className = 'text-xs text-gray-500 ml-2';
                codeSpan.textContent = `(${node.code})`;
                label.appendChild(codeSpan);
            }
            itemDiv.appendChild(label);

            li.appendChild(itemDiv);

            if (hasChildren) {
                const childrenContainer = document.createElement('div');
                childrenContainer.className = `children-container ${isExpanded ? '' : 'hidden'}`;
                childrenContainer.setAttribute('data-parent-key', nodeKey);
                const childrenTree = this.renderTree(node.children, level + 1);
                if (childrenTree) {
                    childrenContainer.appendChild(childrenTree);
                }
                li.appendChild(childrenContainer);
            }

            ul.appendChild(li);
        }

        return ul;
    }

    attachEventListeners() {
        // Expand/collapse buttons
        this.container.querySelectorAll('.expand-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const nodeKey = btn.dataset.nodeKey;
                const isExpanded = btn.dataset.expanded === 'true';
                const escapedKey = (window.CSS && typeof window.CSS.escape === 'function')
                    ? window.CSS.escape(nodeKey)
                    : nodeKey.replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/'/g, "\\'").replace(/[\[\]]/g, '\\$&');
                const childrenContainer = this.container.querySelector(`[data-parent-key="${escapedKey}"]`);
                const icon = btn.querySelector('i');

                if (isExpanded) {
                    childrenContainer.classList.add('hidden');
                    icon.classList.remove('fa-chevron-down');
                    icon.classList.add('fa-chevron-right');
                    btn.dataset.expanded = 'false';
                    this.expandedNodes.delete(nodeKey);
                } else {
                    childrenContainer.classList.remove('hidden');
                    icon.classList.remove('fa-chevron-right');
                    icon.classList.add('fa-chevron-down');
                    btn.dataset.expanded = 'true';
                    this.expandedNodes.add(nodeKey);
                }
            });
        });

        // Checkboxes
        this.container.querySelectorAll('.entity-checkbox').forEach(checkbox => {
            checkbox.addEventListener('change', (e) => {
                const entityType = checkbox.dataset.entityType;
                const entityId = parseInt(checkbox.dataset.entityId);
                const entityName = checkbox.dataset.entityName;
                const isChecked = checkbox.checked;

                this.toggleEntityPermission(entityType, entityId, entityName, isChecked, checkbox);
            });

            // Make label clickable - prevent double toggling
            const label = checkbox.closest('li').querySelector('label');
            if (label) {
                label.addEventListener('click', (e) => {
                    // Prevent default label behavior (which would toggle the checkbox)
                    e.preventDefault();
                    if (e.target.tagName !== 'INPUT') {
                        // Manually toggle the checkbox without triggering double events
                        checkbox.checked = !checkbox.checked;
                        // Trigger change event to ensure toggleEntityPermission is called
                        checkbox.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                });
            }
        });
    }

    // Update hidden form fields instead of making API calls
    updateHiddenFormFields() {
        // Find or create hidden form fields container
        let hiddenContainer = document.getElementById('entity-permissions-hidden-fields');
        if (!hiddenContainer) {
            hiddenContainer = document.createElement('div');
            hiddenContainer.id = 'entity-permissions-hidden-fields';
            hiddenContainer.style.display = 'none';
            // Insert before the form's submit button or at the end of the form
            const form = document.querySelector('form');
            if (form) {
                form.appendChild(hiddenContainer);
            } else {
                this.container.parentElement.appendChild(hiddenContainer);
            }
        }

        // Clear existing hidden fields for this selector's entity types
        this.entityTypes.forEach(entityType => {
            hiddenContainer.querySelectorAll(`input[data-entity-type="${entityType}"]`).forEach(input => {
                input.remove();
            });
        });

        // Create hidden inputs for each selected entity
        this.assignedEntities.forEach(entityKey => {
            const [entityType, entityId] = entityKey.split(':');
            if (this.entityTypes.includes(entityType)) {
                const hiddenInput = document.createElement('input');
                hiddenInput.type = 'hidden';
                hiddenInput.name = 'entity_permissions';
                hiddenInput.value = `${entityType}:${entityId}`;
                hiddenInput.setAttribute('data-entity-type', entityType);
                hiddenContainer.appendChild(hiddenInput);
            }
        });
    }

    toggleEntityPermission(entityType, entityId, entityName, isChecked, checkboxElement) {
        const entityKey = `${entityType}:${entityId}`;

        // Ensure checkbox state matches what the user clicked
        if (checkboxElement) {
            checkboxElement.checked = isChecked;
        }

        // Update local state based on checkbox state
        if (isChecked) {
            this.assignedEntities.add(entityKey);
        } else {
            this.assignedEntities.delete(entityKey);
        }

        // Update hidden form fields
        this.updateHiddenFormFields();

        // Call onChange callback if provided (for UI updates, not API calls)
        if (this.onChange) {
            this.onChange({
                entity_type: entityType,
                entity_id: entityId,
                action: isChecked ? 'added' : 'removed'
            });
        }
    }

    filterHierarchy(searchQuery) {
        if (!searchQuery || searchQuery.trim() === '') {
            this.render();
            return;
        }

        const query = searchQuery.toLowerCase().trim();

        const filterNode = (node) => {
            const matches = node.name.toLowerCase().includes(query) ||
                           (node.code && node.code.toLowerCase().includes(query));

            if (node.children) {
                const filteredChildren = node.children
                    .map(child => filterNode(child))
                    .filter(child => child !== null);

                if (matches || filteredChildren.length > 0) {
                    return {
                        ...node,
                        children: filteredChildren
                    };
                }
            } else if (matches) {
                return node;
            }

            return null;
        };

        const filteredHierarchy = this.hierarchy
            .map(node => filterNode(node))
            .filter(node => node !== null);

        // Temporarily store original hierarchy
        const originalHierarchy = this.hierarchy;
        this.hierarchy = filteredHierarchy;

        // Expand all nodes when filtering
        this.expandAllForSearch();

        this.render();

        // Restore original hierarchy after render (for future searches)
        this.hierarchy = originalHierarchy;
    }

    expandAllForSearch() {
        const expandNode = (node) => {
            if (node.children && node.children.length > 0) {
                const nodeKey = `${node.type}:${node.id}`;
                this.expandedNodes.add(nodeKey);
                node.children.forEach(child => expandNode(child));
            }
        };

        this.hierarchy.forEach(node => expandNode(node));
    }

    getEntityIcon(entityType) {
        const icons = {
            'country': 'fas fa-flag',
            'ns_branch': 'fas fa-sitemap',
            'ns_subbranch': 'fas fa-code-branch',
            'ns_localunit': 'fas fa-map-marker-alt',
            'division': 'fas fa-building',
            'department': 'fas fa-briefcase',
            'regional_office': 'fas fa-globe-europe',
            'cluster_office': 'fas fa-project-diagram'
        };
        return icons[entityType] || 'fas fa-folder';
    }

    showMessage(message, type) {
        const category = type === 'success' ? 'success' : 'danger';
        const text = typeof message === 'string' ? message : (this.toString ? this.toString(message) : String(message || ''));
        if (typeof window.showFlashMessage === 'function') {
            window.showFlashMessage(text, category);
        }
    }
};
} // End of if statement preventing duplicate declaration
