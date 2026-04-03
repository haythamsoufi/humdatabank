/**
 * Admin Notifications Center - Send notifications and view all notifications
 */

async function _anFetch(url, options = {}) {
    const fetchFn = (window.getApiFetch && window.getApiFetch()) || null;
    if (fetchFn) {
        const opts = { ...options };
        if (opts.body && !opts.headers) opts.headers = { 'Content-Type': 'application/json' };
        return fetchFn(url, opts);
    }
    const baseFetch = (window.getFetch && window.getFetch()) || fetch;
    const headers = {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRFToken': (document.querySelector('meta[name="csrf-token"]') || {}).getAttribute?.('content') || '',
        ...options.headers
    };
    const r = await baseFetch(url, { ...options, headers, credentials: 'same-origin' });
    if (!r.ok) throw (window.httpErrorSync && window.httpErrorSync(r)) || new Error(`HTTP ${r.status}`);
    const ct = r.headers.get('Content-Type') || '';
    if (ct.includes('application/json')) return r.json();
    return null;
}

class AdminNotifications {
    constructor() {
        this.selectedUsers = new Map();
        this.userSearchTimeout = null;
        this.csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
        this.editingCampaignId = null; // Track which campaign is being edited
        this.deviceStatusData = null; // Store device status data for modal
        // Removed filters - AG Grid handles filtering now

        // Bulk selection preview state
        this.previewUsers = [];
        this.selectedPreviewUsers = new Set();
        this.previewPage = 1;
        this.previewPerPage = 50;
        this.previewTotalPages = 1;
        this.previewTotal = 0;
        this.previewTimeout = null;
        this.allAssignments = []; // Store all assignments for filtering

        // Bulk selection options loading state
        this.bulkSelectionOptionsLoaded = false;
        this.bulkSelectionOptionsLoading = false;

        // Entity-based campaign state
        this.selectedEntities = new Map(); // Map of entity_key -> {entity_type, entity_id, display_name}
        this.campaignType = 'user'; // 'user' or 'entity'
        this.entitySelectorSelected = new Set(); // Temporary selection in modal

        this.init();
    }

    /**
     * Format RBAC role codes for display.
     * Input: array of role codes (strings)
     */
    formatRbacRoleCodes(codes) {
        const list = Array.isArray(codes) ? codes.filter(Boolean).map(String) : [];
        if (list.length === 0) return '—';
        const labelByCode = {
            system_manager: 'System Manager',
            admin_core: 'Admin',
            assignment_editor_submitter: 'Focal Point',
            assignment_viewer: 'Viewer',
        };
        return list.map(c => labelByCode[c] || c).join(', ');
    }

    init() {
        // Ensure campaign edit fields are not "required" when hidden (prevents HTML5 validation errors)
        this.hideCampaignEditFields();

        // Tab switching
        document.getElementById('tab-send')?.addEventListener('click', () => this.switchTab('send'));
        document.getElementById('tab-view-all')?.addEventListener('click', () => this.switchTab('view-all'));
        document.getElementById('tab-campaigns')?.addEventListener('click', () => this.switchTab('campaigns'));

        // View All tab now uses AG Grid with server-side rendering
        // Filtering is handled by AG Grid's built-in filters
        // No custom filter UI or API calls needed
        // Form submission
        document.getElementById('admin-notification-form')?.addEventListener('submit', (e) => {
            // If editing campaign, handle update instead of send
            if (this.editingCampaignId) {
                e.preventDefault();
                this.handleCampaignUpdate();
            } else {
                this.handleSubmit(e);
            }
        });

        // Update Campaign button
        document.getElementById('update-campaign-btn')?.addEventListener('click', (e) => {
            e.preventDefault();
            this.handleCampaignUpdate();
        });

        // Cancel button
        document.getElementById('cancel-admin-notification')?.addEventListener('click', () => this.resetForm());

        // Campaign type switching
        document.querySelectorAll('input[name="campaign-type"]').forEach(radio => {
            radio.addEventListener('change', (e) => this.handleCampaignTypeChange(e.target.value));
        });

        // Entity type checkboxes - load entities when changed
        document.querySelectorAll('.entity-type-checkbox').forEach(checkbox => {
            checkbox.addEventListener('change', () => {
                this.loadHierarchicalEntities();
            });
        });

        // Entity selection controls
        document.getElementById('select-all-entities')?.addEventListener('click', () => {
            this.selectAllVisibleEntities();
        });

        document.getElementById('deselect-all-entities')?.addEventListener('click', () => {
            this.deselectAllEntities();
        });

        document.getElementById('clear-all-entities')?.addEventListener('click', () => {
            const doClear = () => {
                this.selectedEntities.clear();
                this.updateEntityCount();
                this.updateSelectedEntitiesDisplay();
            };
            if (window.showConfirmation) {
                window.showConfirmation('Clear all selected entities?', doClear, null, 'Clear', 'Cancel', 'Clear Entities?');
            }
        });

        // Static attachments: show selected file names and clear button
        const staticAttachmentsInput = document.getElementById('notification-static-attachments');
        const staticAttachmentsList = document.getElementById('static-attachments-list');
        const clearStaticAttachmentsBtn = document.getElementById('clear-static-attachments');
        if (staticAttachmentsInput) {
            staticAttachmentsInput.addEventListener('change', () => {
                const files = staticAttachmentsInput.files;
                if (!staticAttachmentsList) return;
                staticAttachmentsList.replaceChildren();
                if (files && files.length) {
                    staticAttachmentsList.classList.remove('hidden');
                    for (let i = 0; i < files.length; i++) {
                        const span = document.createElement('span');
                        span.className = 'inline-flex items-center px-2 py-1 rounded bg-gray-200 text-gray-800 text-xs';
                        span.textContent = files[i].name;
                        staticAttachmentsList.appendChild(span);
                    }
                    clearStaticAttachmentsBtn?.classList.remove('hidden');
                } else {
                    staticAttachmentsList.classList.add('hidden');
                    clearStaticAttachmentsBtn?.classList.add('hidden');
                }
            });
        }
        if (clearStaticAttachmentsBtn) {
            clearStaticAttachmentsBtn.addEventListener('click', () => {
                if (staticAttachmentsInput) {
                    staticAttachmentsInput.value = '';
                    staticAttachmentsInput.dispatchEvent(new Event('change'));
                }
                staticAttachmentsList?.classList.add('hidden');
                staticAttachmentsList?.replaceChildren();
                clearStaticAttachmentsBtn.classList.add('hidden');
            });
        }

        // Drag and drop for email distribution rules
        this.initDragAndDrop();

        // Initialize entity selector state
        this.entitySelectorSelected = new Set();

        // User search
        const userSearchInput = document.getElementById('admin-notification-user-search');
        if (userSearchInput) {
            userSearchInput.addEventListener('input', (e) => this.handleUserSearch(e.target.value));
            userSearchInput.addEventListener('focus', () => {
                if (userSearchInput.value.trim().length >= 2) {
                    this.handleUserSearch(userSearchInput.value);
                }
            });

            // Close search results when clicking outside
            document.addEventListener('click', (e) => {
                const userSearch = document.getElementById('admin-notification-user-search');
                const userResults = document.getElementById('admin-notification-user-results');
                if (userSearch && userResults && !userSearch.contains(e.target) && !userResults.contains(e.target)) {
                    userResults.classList.add('hidden');
                }
            });
        }

        // Redirect type toggle
        document.getElementById('redirect-type-app')?.addEventListener('click', () => this.handleRedirectTypeChange('app'));
        document.getElementById('redirect-type-custom')?.addEventListener('click', () => this.handleRedirectTypeChange('custom'));

        // Get delivery method checkboxes (used for both redirect section and preview)
        const sendEmailCheckbox = document.getElementById('send-email');
        const sendPushCheckbox = document.getElementById('send-push');
        const redirectSection = document.getElementById('redirect-section');

        // Toggle redirect section visibility based on push notification checkbox
        if (sendPushCheckbox && redirectSection) {
            sendPushCheckbox.addEventListener('change', (e) => {
                if (e.target.checked) {
                    redirectSection.classList.remove('hidden');
                } else {
                    redirectSection.classList.add('hidden');
                    // Clear redirect values when push is unchecked
                    document.getElementById('admin-notification-redirect-screen').value = '';
                    document.getElementById('admin-notification-redirect-url').value = '';
                }
                // Also update preview when checkbox changes
                this.updatePreview();
            });
            // Initial state - hide if push is not checked
            if (!sendPushCheckbox.checked) {
                redirectSection.classList.add('hidden');
            }
        }

        // Preview updates
        const titleInput = document.getElementById('admin-notification-title');
        const messageInput = document.getElementById('admin-notification-message');

        if (titleInput) titleInput.addEventListener('input', () => this.updatePreview());
        if (messageInput) messageInput.addEventListener('input', () => this.updatePreview());
        if (sendEmailCheckbox) sendEmailCheckbox.addEventListener('change', () => this.updatePreview());
        if (sendPushCheckbox) sendPushCheckbox.addEventListener('change', () => this.updatePreview());

        // Toggle preview
        document.getElementById('toggle-preview')?.addEventListener('click', () => {
            const preview = document.getElementById('notification-preview');
            const content = document.getElementById('preview-content');
            const icon = document.querySelector('#toggle-preview i');
            if (preview && content) {
                if (content.classList.contains('hidden')) {
                    content.classList.remove('hidden');
                    icon?.classList.replace('fa-chevron-down', 'fa-chevron-up');
                } else {
                    content.classList.add('hidden');
                    icon?.classList.replace('fa-chevron-up', 'fa-chevron-down');
                }
            }
        });

        // Device status refresh button
        // Device status modal handlers
        document.getElementById('view-device-details')?.addEventListener('click', () => {
            this.openDeviceStatusModal();
        });

        document.getElementById('close-device-status-modal')?.addEventListener('click', () => {
            this.closeDeviceStatusModal();
        });

        document.getElementById('refresh-device-status')?.addEventListener('click', () => {
            this.checkDeviceStatus(true); // Force refresh
        });

        // Close device status modal when clicking outside
        const deviceStatusModal = document.getElementById('device-status-modal');
        deviceStatusModal?.addEventListener('click', (e) => {
            if (e.target.id === 'device-status-modal') {
                this.closeDeviceStatusModal();
            }
        });

        // Close modal on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && deviceStatusModal && !deviceStatusModal.classList.contains('hidden')) {
                this.closeDeviceStatusModal();
            }
        });

        // Campaign recipients modal handlers
        document.getElementById('close-campaign-recipients-modal')?.addEventListener('click', () => {
            this.closeCampaignRecipientsModal();
        });

        document.getElementById('close-campaign-recipients-modal-btn')?.addEventListener('click', () => {
            this.closeCampaignRecipientsModal();
        });

        // Recipients search
        const recipientsSearchInput = document.getElementById('recipients-search');
        if (recipientsSearchInput) {
            let searchTimeout = null;
            recipientsSearchInput.addEventListener('input', (e) => {
                clearTimeout(searchTimeout);
                searchTimeout = setTimeout(() => {
                    this.filterCampaignRecipients(e.target.value);
                }, 300);
            });
        }

        // Close recipients modal when clicking outside
        const recipientsModal = document.getElementById('campaign-recipients-modal');
        recipientsModal?.addEventListener('click', (e) => {
            if (e.target.id === 'campaign-recipients-modal') {
                this.closeCampaignRecipientsModal();
            }
        });

        // Close recipients modal on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && recipientsModal && !recipientsModal.classList.contains('hidden')) {
                this.closeCampaignRecipientsModal();
            }
        });

        // Bulk selection - single Add All button
        document.getElementById('add-all-filtered-users')?.addEventListener('click', () => {
            this.addUsersByFilters();
        });

        document.getElementById('clear-all-users')?.addEventListener('click', () => {
            if (window.showConfirmation) {
                window.showConfirmation(
                    'Clear all selected users?',
                    () => {
                        this.selectedUsers.clear();
                        this.updateSelectedUsersDisplay();
                    },
                    null,
                    'Clear',
                    'Cancel',
                    'Clear Users?'
                );
            } else {
                this.selectedUsers.clear();
                this.updateSelectedUsersDisplay();
            }
        });

        // Template dropdown
        const templateSelect = document.getElementById('notification-template-select');
        if (templateSelect) {
            templateSelect.addEventListener('change', (e) => {
                const templateType = e.target.value;
                console.log('Template dropdown changed:', templateType);
                if (templateType) {
                    this.loadTemplate(templateType);
                    // Reset dropdown after loading (with small delay to ensure template is applied)
                    setTimeout(() => {
                        e.target.value = '';
                    }, 100);
                }
            });
            console.log('Template dropdown event listener attached');
        } else {
            console.error('Template select element not found');
        }

        // Clear template button
        document.getElementById('clear-template')?.addEventListener('click', () => {
            this.resetForm();
        });

        // Campaign modal handlers
        const campaignModal = document.getElementById('campaign-modal');
        const saveAsCampaignBtn = document.getElementById('save-as-campaign-btn');
        const closeCampaignModal = document.getElementById('close-campaign-modal');
        const cancelCampaignModal = document.getElementById('cancel-campaign-modal');
        const campaignForm = document.getElementById('campaign-form');
        const campaignScheduledInput = document.getElementById('campaign-modal-scheduled-for');

        // Set minimum date for campaign scheduled input
        if (campaignScheduledInput) {
            const now = new Date();
            now.setMinutes(now.getMinutes() + 1);
            campaignScheduledInput.min = now.toISOString().slice(0, 16);
        }

        // Open campaign modal
        saveAsCampaignBtn?.addEventListener('click', () => {
            this.openCampaignModal();
        });

        // Close campaign modal
        closeCampaignModal?.addEventListener('click', () => {
            this.closeCampaignModal();
        });

        cancelCampaignModal?.addEventListener('click', () => {
            this.closeCampaignModal();
        });

        // Close modal when clicking outside
        campaignModal?.addEventListener('click', (e) => {
            if (e.target.id === 'campaign-modal') {
                this.closeCampaignModal();
            }
        });

        // Close modal on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape' && campaignModal && !campaignModal.classList.contains('hidden')) {
                this.closeCampaignModal();
            }
        });

        // Handle campaign form submission
        campaignForm?.addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleCampaignSubmit();
        });

        // Campaign management
        document.getElementById('create-campaign-btn')?.addEventListener('click', () => {
            this.switchTab('send');
            this.openCampaignModal();
        });

        // Campaign status filter removed - AG Grid handles filtering now

        // Campaigns grid initialization is handled in the template script
        // Grid is initialized when the campaigns tab becomes visible

        // Bulk selection modal
        document.getElementById('open-bulk-selection')?.addEventListener('click', () => {
            this.openBulkSelectionModal();
        });

        document.getElementById('close-bulk-selection')?.addEventListener('click', () => {
            this.closeBulkSelectionModal();
        });

        document.getElementById('close-bulk-selection-btn')?.addEventListener('click', () => {
            this.closeBulkSelectionModal();
        });

        // Close modal when clicking outside
        document.getElementById('bulk-selection-modal')?.addEventListener('click', (e) => {
            if (e.target.id === 'bulk-selection-modal') {
                this.closeBulkSelectionModal();
            }
        });

        // Close modal on Escape key
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                const modal = document.getElementById('bulk-selection-modal');
                if (modal && !modal.classList.contains('hidden')) {
                    this.closeBulkSelectionModal();
                }
            }
        });

        // Load countries, templates, and entities for bulk selection
        this.loadBulkSelectionOptions();

        // Initialize bulk selection features
        this.initBulkSelectionFeatures();

        // Preserve current tab on load using URL hash (e.g. #send, #campaigns, #view-all)
        // This avoids the "tab jump" UX when the page reloads after an action.
        const initialTab = (window.location.hash || '').replace('#', '');
        if (initialTab === 'send' || initialTab === 'view-all' || initialTab === 'campaigns') {
            this.switchTab(initialTab);
        }
    }

    renderBackendFlash(message, category = 'info') {
        if (!message) return;
        if (typeof window.showFlashMessage === 'function') {
            window.showFlashMessage(message, category);
        }
    }

    openBulkSelectionModal() {
        const modal = document.getElementById('bulk-selection-modal');
        if (modal) {
            modal.classList.remove('hidden');
            document.body.style.overflow = 'hidden'; // Prevent background scrolling

            // Reset bulk selection state
            this.resetBulkSelectionFilters();

            // Load options (countries, entity types, templates) if not already loaded
            this.loadBulkSelectionOptions();

            // Update counts on open
            setTimeout(() => {
                this.updateCountryCount();
                this.updateTemplateFilterCount();
                this.updateAssignmentFormCount();
            }, 100);
        }
    }

    resetBulkSelectionFilters() {
        // Clear search
        const searchInput = document.getElementById('bulk-search-users');
        if (searchInput) searchInput.value = '';

        // Clear role checkboxes
        document.querySelectorAll('.bulk-role-checkbox').forEach(cb => cb.checked = false);

        // Clear assignment status checkboxes
        document.querySelectorAll('.bulk-assignment-status-checkbox').forEach(cb => cb.checked = false);

        // Clear account status checkboxes
        document.querySelectorAll('.bulk-account-status-checkbox').forEach(cb => cb.checked = false);

        // Clear country select (Select2 or native)
        const countrySelect = document.getElementById('bulk-select-country');
        if (countrySelect) {
            if (window.jQuery && window.jQuery.fn.select2 && $(countrySelect).hasClass('select2-hidden-accessible')) {
                $(countrySelect).val(null).trigger('change');
            } else {
                countrySelect.value = '';
            }
        }

        // Clear entity type
        const entitySelect = document.getElementById('bulk-select-entity');
        if (entitySelect) entitySelect.value = '';

        // Clear template filter (standalone)
        const templateFilterSelect = document.getElementById('bulk-select-template-filter');
        if (templateFilterSelect) {
            if (window.jQuery && window.jQuery.fn.select2 && $(templateFilterSelect).hasClass('select2-hidden-accessible')) {
                $(templateFilterSelect).val(null).trigger('change');
            } else {
                templateFilterSelect.value = '';
            }
        }

        // Clear assignment form filter
        const assignmentFormSelect = document.getElementById('bulk-select-assignment-form');
        if (assignmentFormSelect) {
            if (window.jQuery && window.jQuery.fn.select2 && $(assignmentFormSelect).hasClass('select2-hidden-accessible')) {
                $(assignmentFormSelect).val(null).trigger('change');
            } else {
                assignmentFormSelect.value = '';
            }
        }

        // Clear template select (inside assignment filters)
        const templateSelect = document.getElementById('bulk-select-template');
        if (templateSelect) {
            if (window.jQuery && window.jQuery.fn.select2 && $(templateSelect).hasClass('select2-hidden-accessible')) {
                $(templateSelect).val(null).trigger('change');
            } else {
                templateSelect.value = '';
            }
        }

        // Reset preview
        this.previewPage = 1;
        this.selectedPreviewUsers.clear();
        this.loadPreviewUsers();
    }

    closeBulkSelectionModal() {
        const modal = document.getElementById('bulk-selection-modal');
        if (modal) {
            modal.classList.add('hidden');
            document.body.style.overflow = ''; // Restore scrolling
        }
    }

    async loadBulkSelectionOptions() {
        // Prevent concurrent calls and skip if already loaded
        if (this.bulkSelectionOptionsLoading) {
            console.log('Bulk selection options already loading, skipping...');
            return;
        }

        if (this.bulkSelectionOptionsLoaded) {
            console.log('Bulk selection options already loaded, skipping...');
            return;
        }

        this.bulkSelectionOptionsLoading = true;

        try {
            // Load countries
            try {
                const data = await _anFetch('/notifications/api/admin/countries');
                const countrySelect = document.getElementById('bulk-select-country');
                if (countrySelect && data.countries) {
                    data.countries.forEach(country => {
                        const option = document.createElement('option');
                        option.value = country.id;
                        option.textContent = country.name;
                        countrySelect.appendChild(option);
                    });

                    // Initialize Select2 for searchable multi-select
                    if (window.jQuery && window.jQuery.fn.select2) {
                        const $countrySelect = $(countrySelect);
                        const modal = document.getElementById('bulk-selection-modal');
                        if (!$countrySelect.hasClass('select2-hidden-accessible')) {
                            $countrySelect.select2({
                                placeholder: 'Search and select countries...',
                                allowClear: true,
                                width: '100%',
                                closeOnSelect: false,
                                theme: 'default',
                                dropdownParent: modal ? $(modal) : $('body')
                            });

                            // Update count when selection changes
                            $countrySelect.on('select2:select select2:unselect', () => {
                                this.updateCountryCount();
                                this.previewPage = 1;
                                this.loadPreviewUsers();
                            });
                        }
                    }
                }
            } catch (_) { /* no data */ }
        } catch (error) {
            console.error('Error loading countries:', error);
        }

        // Load entity types
        try {
            try {
                const data = await _anFetch('/notifications/api/admin/entity-types');
                const entitySelect = document.getElementById('bulk-select-entity');
                if (entitySelect && data.entity_types) {
                    // Clear existing options except the first "All Entity Types" option
                    const firstOption = entitySelect.querySelector('option[value=""]');
                    entitySelect.replaceChildren();
                    if (firstOption) {
                        entitySelect.appendChild(firstOption);
                    }

                    // Add entity type options
                    data.entity_types.forEach(entityType => {
                        const option = document.createElement('option');
                        option.value = entityType.value;
                        option.textContent = entityType.label;
                        entitySelect.appendChild(option);
                    });
                }
            } catch (_) { /* no data */ }
        } catch (error) {
            console.error('Error loading entity types:', error);
        }

        // Load templates once and populate both dropdowns (fixes 429 rate limit error)
        try {
            try {
                const data = await _anFetch('/notifications/api/admin/templates');
                const templates = data.templates || [];
                const modal = document.getElementById('bulk-selection-modal');

                // Populate template select for assignment status filter
                const templateSelect = document.getElementById('bulk-select-template');
                if (templateSelect && templates.length > 0) {
                    // Clear "All Templates" option and add actual templates
                    templateSelect.replaceChildren();
                    templates.forEach(template => {
                        const option = document.createElement('option');
                        option.value = template.id;
                        option.textContent = template.name;
                        templateSelect.appendChild(option);
                    });

                    // Initialize Select2 for searchable multi-select
                    if (window.jQuery && window.jQuery.fn.select2) {
                        const $templateSelect = $(templateSelect);
                        if (!$templateSelect.hasClass('select2-hidden-accessible')) {
                            $templateSelect.select2({
                                placeholder: 'Search and select templates...',
                                allowClear: true,
                                width: '100%',
                                closeOnSelect: false,
                                theme: 'default',
                                dropdownParent: modal ? $(modal) : $('body')
                            });

                            // Reload preview when template selection changes
                            $templateSelect.on('select2:select select2:unselect', () => {
                                this.previewPage = 1;
                                this.loadPreviewUsers();
                            });
                        }
                    }
                }

                // Populate standalone template filter
                const templateFilterSelect = document.getElementById('bulk-select-template-filter');
                if (templateFilterSelect && templates.length > 0) {
                    templates.forEach(template => {
                        const option = document.createElement('option');
                        option.value = template.id;
                        option.textContent = template.name;
                        templateFilterSelect.appendChild(option);
                    });

                    // Initialize Select2 for searchable multi-select
                    if (window.jQuery && window.jQuery.fn.select2) {
                        const $templateFilterSelect = $(templateFilterSelect);
                        if (!$templateFilterSelect.hasClass('select2-hidden-accessible')) {
                            $templateFilterSelect.select2({
                                placeholder: 'Search and select templates...',
                                allowClear: true,
                                width: '100%',
                                closeOnSelect: false,
                                theme: 'default',
                                dropdownParent: modal ? $(modal) : $('body')
                            });

                            // Update count, filter assignments, and reload preview when template selection changes
                            $templateFilterSelect.on('select2:select select2:unselect', () => {
                                this.updateTemplateFilterCount();
                                this.filterAssignmentsByTemplates();
                                this.previewPage = 1;
                                this.loadPreviewUsers();
                            });
                        }
                    }
                }
            } catch (e) {
                if (e?.status === 429) console.warn('Rate limit exceeded for templates API. Please wait a moment and try again.');
            }
        } catch (error) {
            console.error('Error loading templates:', error);
        }

        // Load assignments and store them for filtering
        try {
            const data = await _anFetch('/notifications/api/admin/assignments');
            if (data) {
                // Store all assignments for filtering
                this.allAssignments = data.assignments || [];
                this.loadAssignmentsDropdown();

                // Initialize Select2 for searchable multi-select
                const assignmentFormSelect = document.getElementById('bulk-select-assignment-form');
                if (assignmentFormSelect && window.jQuery && window.jQuery.fn.select2) {
                    const $assignmentFormSelect = $(assignmentFormSelect);
                    const modal = document.getElementById('bulk-selection-modal');
                    if (!$assignmentFormSelect.hasClass('select2-hidden-accessible')) {
                        $assignmentFormSelect.select2({
                            placeholder: 'Search and select assignments...',
                            allowClear: true,
                            width: '100%',
                            closeOnSelect: false,
                            theme: 'default',
                            dropdownParent: modal ? $(modal) : $('body')
                        });

                        // Update count and reload preview when assignment selection changes
                        $assignmentFormSelect.on('select2:select select2:unselect', () => {
                            this.updateAssignmentFormCount();
                            this.previewPage = 1;
                            this.loadPreviewUsers();
                        });
                    }
                }
            }
        } catch (error) {
            console.error('Error loading assignments:', error);
        } finally {
            // Mark loading as complete
            this.bulkSelectionOptionsLoading = false;
            this.bulkSelectionOptionsLoaded = true;
        }
    }

    async addUsersByFilters() {
        const role = document.getElementById('bulk-select-role')?.value || '';
        const countryId = document.getElementById('bulk-select-country')?.value || '';
        const entityType = document.getElementById('bulk-select-entity')?.value || '';
        const assignmentStatuses = Array.from(document.querySelectorAll('.bulk-assignment-status-checkbox:checked')).map(cb => cb.value);
        const templateSelect = document.getElementById('bulk-select-template');
        const selectedTemplateIds = templateSelect ? Array.from(templateSelect.selectedOptions).map(opt => opt.value).filter(v => v) : [];

        try {
            // Build query parameters (only include non-empty filters)
            const params = new URLSearchParams();
            if (role) params.append('role', role);
            if (countryId) params.append('country_id', countryId);
            if (entityType) params.append('entity_type', entityType);
            if (assignmentStatuses.length > 0) {
                assignmentStatuses.forEach(status => {
                    params.append('assignment_status', status);
                });
                // Add template IDs if any are selected
                selectedTemplateIds.forEach(templateId => {
                    params.append('template_id', templateId);
                });
            }

            const data = await _anFetch(`/notifications/api/admin/users/bulk?${params.toString()}`);
            if (data && data.success && data.users) {
                    let added = 0;
                    data.users.forEach(user => {
                        if (!this.selectedUsers.has(user.id)) {
                            this.selectedUsers.set(user.id, {
                                id: user.id,
                                name: user.name || user.email,
                                email: user.email,
                                rbac_role_codes: user.rbac_role_codes || []
                            });
                            added++;
                        }
                    });
                    this.updateSelectedUsersDisplay();

                    // Build filter description for message
                    const filterDesc = [];
                    if (role) {
                        const roleLabels = {
                            'assignment_editor_submitter': 'Focal Points',
                            'admin_core': 'Admins',
                            'system_manager': 'System Managers'
                        };
                        filterDesc.push(roleLabels[role] || role);
                    }
                    if (countryId) {
                        const countrySelect = document.getElementById('bulk-select-country');
                        const countryName = countrySelect?.options[countrySelect.selectedIndex]?.text || `country ${countryId}`;
                        filterDesc.push(countryName);
                    }
                    if (entityType) {
                        filterDesc.push(`entity: ${entityType}`);
                    }
                    if (assignmentStatuses.length > 0) {
                        let statusDesc = assignmentStatuses.length === 1
                            ? `${assignmentStatuses[0]} Assignments`
                            : `Assignments: ${assignmentStatuses.join(', ')}`;
                        if (selectedTemplateIds.length > 0) {
                            const templateNames = Array.from(templateSelect.selectedOptions).map(opt => opt.text);
                            statusDesc += ` (${templateNames.join(', ')})`;
                        }
                        filterDesc.push(statusDesc);
                    }
                    if (selectedTemplateFilterIds.length > 0 && assignmentStatuses.length === 0) {
                        const templateFilterSelectEl = document.getElementById('bulk-select-template-filter');
                        if (templateFilterSelectEl) {
                            const templateNames = [];
                            if (window.jQuery && window.jQuery.fn.select2 && $(templateFilterSelectEl).hasClass('select2-hidden-accessible')) {
                                const selectedData = $(templateFilterSelectEl).select2('data');
                                templateNames.push(...selectedData.map(item => item.text));
                            } else {
                                Array.from(templateFilterSelectEl.selectedOptions).forEach(opt => templateNames.push(opt.text));
                            }
                            filterDesc.push(`Templates: ${templateNames.join(', ')}`);
                        }
                    }
                    if (selectedAssignmentFormIds.length > 0) {
                        const assignmentFormSelectEl = document.getElementById('bulk-select-assignment-form');
                        if (assignmentFormSelectEl) {
                            const assignmentNames = [];
                            if (window.jQuery && window.jQuery.fn.select2 && $(assignmentFormSelectEl).hasClass('select2-hidden-accessible')) {
                                const selectedData = $(assignmentFormSelectEl).select2('data');
                                assignmentNames.push(...selectedData.map(item => item.text));
                            } else {
                                Array.from(assignmentFormSelectEl.selectedOptions).forEach(opt => assignmentNames.push(opt.text));
                            }
                            filterDesc.push(`Assignments: ${assignmentNames.join(', ')}`);
                        }
                    }

                    if (added > 0) {
                        setTimeout(() => this.closeBulkSelectionModal(), 1500);
                    }
            }
        } catch (error) {
            console.error('Error loading users by filters:', error);
        }
    }

    updatePreview() {
        const title = document.getElementById('admin-notification-title')?.value || '';
        const message = document.getElementById('admin-notification-message')?.value || '';
        const sendEmail = document.getElementById('send-email')?.checked;
        const sendPush = document.getElementById('send-push')?.checked;

        const preview = document.getElementById('notification-preview');
        if (!preview) return;

        // Only show preview if there's content AND at least one delivery method is selected
        if ((title || message) && (sendEmail || sendPush)) {
            preview.classList.remove('hidden');

            // Update email preview - only show if email is selected
            const emailPreview = document.getElementById('email-preview');
            if (emailPreview) {
                if (sendEmail) {
                    emailPreview.classList.remove('hidden');
                    document.getElementById('preview-email-title').textContent = title || 'No title';
                    document.getElementById('preview-email-message').textContent = message || 'No message';
                } else {
                    emailPreview.classList.add('hidden');
                }
            }

            // Update push preview - only show if push is selected
            const pushPreview = document.getElementById('push-preview');
            if (pushPreview) {
                if (sendPush) {
                    pushPreview.classList.remove('hidden');
                    document.getElementById('preview-push-title').textContent = title || 'No title';
                    document.getElementById('preview-push-message').textContent = message || 'No message';
                } else {
                    pushPreview.classList.add('hidden');
                }
            }
        } else {
            preview.classList.add('hidden');
        }
    }

    handleRedirectTypeChange(type) {
        const appGroup = document.getElementById('redirect-app-screen-group');
        const customGroup = document.getElementById('redirect-custom-url-group');
        const appBtn = document.getElementById('redirect-type-app');
        const customBtn = document.getElementById('redirect-type-custom');

        if (type === 'app') {
            appGroup?.classList.remove('hidden');
            customGroup?.classList.add('hidden');
            appBtn?.classList.add('active', 'border-blue-600', 'text-blue-600');
            appBtn?.classList.remove('border-transparent', 'text-gray-500');
            customBtn?.classList.remove('active', 'border-blue-600', 'text-blue-600');
            customBtn?.classList.add('border-transparent', 'text-gray-500');

            // Clear custom URL input
            const customUrlInput = document.getElementById('admin-notification-redirect-url');
            if (customUrlInput) customUrlInput.value = '';
        } else {
            appGroup?.classList.add('hidden');
            customGroup?.classList.remove('hidden');
            customBtn?.classList.add('active', 'border-blue-600', 'text-blue-600');
            customBtn?.classList.remove('border-transparent', 'text-gray-500');
            appBtn?.classList.remove('active', 'border-blue-600', 'text-blue-600');
            appBtn?.classList.add('border-transparent', 'text-gray-500');

            // Clear app screen select
            const appScreenSelect = document.getElementById('admin-notification-redirect-screen');
            if (appScreenSelect) appScreenSelect.value = '';
        }
    }

    async handleUserSearch(query) {
        if (!query || query.trim().length < 2) {
            document.getElementById('admin-notification-user-results')?.classList.add('hidden');
            return;
        }

        clearTimeout(this.userSearchTimeout);
        this.userSearchTimeout = setTimeout(async () => {
        try {
            const data = await _anFetch(`/notifications/api/admin/users/search?q=${encodeURIComponent(query.trim())}`);

                if (data && data.users) {
                    this.displayUserSearchResults(data.users);
                }
            } catch (error) {
                console.error('Error searching users:', error);
            }
        }, 300);
    }

    displayUserSearchResults(users) {
        const resultsContainer = document.getElementById('admin-notification-user-results');
        if (!resultsContainer) return;

        // Filter out already selected users
        const filteredUsers = users.filter(user => !this.selectedUsers.has(user.id));

        if (filteredUsers.length === 0) {
            resultsContainer.replaceChildren();
            const emptyEl = document.createElement('div');
            emptyEl.className = 'p-3 text-sm text-gray-500 text-center';
            emptyEl.textContent = 'No users found or all selected';
            resultsContainer.appendChild(emptyEl);
            resultsContainer.classList.remove('hidden');
            return;
        }

        resultsContainer.replaceChildren();
        const frag = document.createDocumentFragment();

        filteredUsers.forEach((user) => {
            const el = document.createElement('div');
            el.className = 'p-3 hover:bg-gray-100 cursor-pointer border-b border-gray-200 last:border-b-0 user-search-result';

            el.dataset.userId = String(user.id);
            el.dataset.userName = String(user.name || user.email || '');
            el.dataset.userEmail = String(user.email || '');
            el.dataset.userRoleCodes = JSON.stringify(user.rbac_role_codes || []);

            const row = document.createElement('div');
            row.className = 'flex items-center justify-between';

            const left = document.createElement('div');
            left.className = 'flex-1';

            const nameEl = document.createElement('div');
            nameEl.className = 'font-medium text-gray-900';
            nameEl.textContent = String(user.name || 'No name');

            const emailEl = document.createElement('div');
            emailEl.className = 'text-sm text-gray-500';
            emailEl.textContent = String(user.email || '');

            const roleEl = document.createElement('div');
            roleEl.className = 'text-xs text-gray-400 mt-1';
            roleEl.textContent = this.formatRbacRoleCodes(user.rbac_role_codes || []);

            left.appendChild(nameEl);
            left.appendChild(emailEl);
            left.appendChild(roleEl);

            row.appendChild(left);
            el.appendChild(row);
            frag.appendChild(el);
        });

        resultsContainer.appendChild(frag);

        // Add click handlers
        resultsContainer.querySelectorAll('.user-search-result').forEach(element => {
            element.addEventListener('click', () => {
                const userId = parseInt(element.dataset.userId);
                const userName = element.dataset.userName;
                const userEmail = element.dataset.userEmail;
                let userRoleCodes = [];
                try {
                    userRoleCodes = JSON.parse(element.dataset.userRoleCodes || '[]') || [];
                } catch (e) {
                    userRoleCodes = [];
                }

                this.selectedUsers.set(userId, {
                    id: userId,
                    name: userName,
                    email: userEmail,
                    rbac_role_codes: userRoleCodes
                });

                this.updateSelectedUsersDisplay();
                document.getElementById('admin-notification-user-search').value = '';
                resultsContainer.classList.add('hidden');
            });
        });

        resultsContainer.classList.remove('hidden');
    }

    updateSelectedUsersDisplay() {
        const container = document.getElementById('admin-notification-selected-users');
        if (!container) return;

        if (this.selectedUsers.size === 0) {
            container.replaceChildren();
            // Hide device status when no users selected
            const deviceStatus = document.getElementById('selected-users-device-status');
            if (deviceStatus) deviceStatus.classList.add('hidden');
            // Update selected count
            const countEl = document.getElementById('selected-count');
            if (countEl) countEl.textContent = '0';
            return;
        }

        container.replaceChildren();
        const frag = document.createDocumentFragment();
        Array.from(this.selectedUsers.values()).forEach((user) => {
            const pill = document.createElement('div');
            pill.className = 'inline-flex items-center gap-2 bg-blue-100 text-blue-800 px-3 py-1 rounded-full text-sm font-medium';

            const label = document.createElement('span');
            label.textContent = String(user.name || user.email || '');

            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'remove-selected-user text-blue-600 hover:text-blue-800 focus:outline-none';
            btn.dataset.userId = String(user.id);
            btn.textContent = '×';

            pill.appendChild(label);
            pill.appendChild(btn);
            frag.appendChild(pill);
        });
        container.appendChild(frag);

        // Attach event listeners to remove buttons
        container.querySelectorAll('.remove-selected-user').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const userId = parseInt(e.target.closest('button').dataset.userId);
                this.removeSelectedUser(userId);
            });
        });

        // Update selected count
        const countEl = document.getElementById('selected-count');
        if (countEl) {
            countEl.textContent = this.selectedUsers.size.toString();
        }

        // Check device status when users are selected
        this.checkDeviceStatus();
    }

    removeSelectedUser(userId) {
        this.selectedUsers.delete(userId);
        this.updateSelectedUsersDisplay();
    }

    async checkDeviceStatus(forceRefresh = false) {
        const userIds = Array.from(this.selectedUsers.keys());
        if (userIds.length === 0) {
            document.getElementById('selected-users-device-status')?.classList.add('hidden');
            return;
        }

        try {
            const data = await _anFetch('/notifications/api/admin/users/devices/check', {
                method: 'POST',
                body: JSON.stringify({ user_ids: userIds })
            });
            if (data && data.success) {
                this.displayDeviceStatusSummary(data);
                // If modal is open, update details
                const modal = document.getElementById('device-status-modal');
                if (modal && !modal.classList.contains('hidden')) {
                    this.displayDeviceStatusDetails(data);
                }
                // Store data for modal
                this.deviceStatusData = data;
            }
        } catch (error) {
            console.error('Error checking device status:', error);
        }
    }

    displayDeviceStatusSummary(data) {
        const summaryContainer = document.getElementById('device-status-summary');
        const statusContainer = document.getElementById('selected-users-device-status');
        if (!summaryContainer || !statusContainer) return;

        statusContainer.classList.remove('hidden');

        const { total_users, users_with_devices, users_without_devices } = data;

        // Show summary only
        let summaryText = `${total_users} user${total_users !== 1 ? 's' : ''} selected`;
        if (users_with_devices > 0 || users_without_devices > 0) {
            summaryText += ` • ${users_with_devices} with devices`;
            if (users_without_devices > 0) {
                summaryText += ` • ${users_without_devices} without devices`;
            }
        }

        summaryContainer.replaceChildren();
        const span = document.createElement('span');
        span.className = 'text-sm text-gray-700';
        span.textContent = summaryText;
        summaryContainer.appendChild(span);
    }

    displayDeviceStatusDetails(data) {
        const container = document.getElementById('device-status-details-content');
        if (!container) return;

        const { total_users, users_with_devices, users_without_devices, device_info } = data;

        let html = `
            <div class="mb-4 p-4 bg-gray-50 rounded-lg border border-gray-200">
                <div class="grid grid-cols-3 gap-4 text-center">
                    <div>
                        <div class="text-2xl font-bold text-gray-900">${total_users}</div>
                        <div class="text-xs text-gray-600 mt-1">Total Users</div>
                    </div>
                    <div>
                        <div class="text-2xl font-bold text-green-600">${users_with_devices}</div>
                        <div class="text-xs text-gray-600 mt-1">With Devices</div>
                    </div>
                    <div>
                        <div class="text-2xl font-bold text-orange-600">${users_without_devices}</div>
                        <div class="text-xs text-gray-600 mt-1">Without Devices</div>
                    </div>
                </div>
            </div>
        `;

        if (device_info && device_info.length > 0) {
            html += '<div class="space-y-3">';

            device_info.forEach(user => {
                const hasDevices = user.has_devices;
                const deviceCount = user.device_count || 0;
                const devices = user.devices || [];

                html += `
                    <div class="p-4 border border-gray-200 rounded-lg ${hasDevices ? 'bg-green-50' : 'bg-orange-50'}">
                        <div class="flex items-start justify-between mb-2">
                            <div class="flex-1">
                                <div class="font-medium text-gray-900">${this.escapeHtml(user.name || user.email)}</div>
                                <div class="text-sm text-gray-600">${this.escapeHtml(user.email)}</div>
                            </div>
                            <div class="ml-4 text-right">
                                ${hasDevices
                                    ? `<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                                        <i class="fas fa-check-circle mr-1"></i>${deviceCount} device${deviceCount !== 1 ? 's' : ''}
                                       </span>`
                                    : `<span class="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-800">
                                        <i class="fas fa-exclamation-circle mr-1"></i>No devices
                                       </span>`
                                }
                            </div>
                        </div>
                `;

                if (hasDevices && devices.length > 0) {
                    html += `
                        <div class="mt-3 pt-3 border-t border-gray-200">
                            <div class="text-xs font-medium text-gray-700 mb-2">Registered Devices:</div>
                            <div class="space-y-2">
                    `;

                    devices.forEach(device => {
                        const platform = device.platform || 'Unknown';
                        const lastActive = device.last_active
                            ? (typeof DateTimeUtils !== 'undefined' ? DateTimeUtils.format(device.last_active, 'datetime') : new Date(device.last_active).toLocaleString())
                            : 'Never';
                        html += `
                            <div class="p-2 bg-white rounded border border-gray-200">
                                <div class="flex items-center justify-between">
                                    <div>
                                        <div class="text-sm font-medium text-gray-900">${this.escapeHtml(platform)}</div>
                                        <div class="text-xs text-gray-500">Last active: ${lastActive}</div>
                                    </div>
                                    ${device.is_active
                                        ? '<span class="text-xs text-green-600"><i class="fas fa-circle mr-1"></i>Active</span>'
                                        : '<span class="text-xs text-gray-400"><i class="fas fa-circle mr-1"></i>Inactive</span>'
                                    }
                                </div>
                            </div>
                        `;
                    });

                    html += `
                            </div>
                        </div>
                    `;
                } else if (!hasDevices) {
                    html += `
                        <div class="mt-3 pt-3 border-t border-gray-200">
                            <p class="text-xs text-orange-600">
                                <i class="fas fa-info-circle mr-1"></i>
                                This user has no registered devices. They will only receive email notifications.
                            </p>
                        </div>
                    `;
                }

                html += '</div>';
            });

            html += '</div>';
        } else {
            html += '<div class="text-center py-8 text-gray-500">No device information available</div>';
        }

        container.replaceChildren();
        const frag = document.createRange().createContextualFragment(html);
        container.appendChild(frag);
    }

    openDeviceStatusModal() {
        // Check if we have device status data
        if (this.deviceStatusData) {
            this.displayDeviceStatusDetails(this.deviceStatusData);
        } else {
            // Fetch fresh data
            this.checkDeviceStatus();
        }

        const modal = document.getElementById('device-status-modal');
        if (modal) {
            modal.classList.remove('hidden');
        }
    }

    closeDeviceStatusModal() {
        const modal = document.getElementById('device-status-modal');
        if (modal) {
            modal.classList.add('hidden');
        }
    }

    async handleSubmit(e) {
        e.preventDefault();

        const sendEmail = document.getElementById('send-email').checked;
        const sendPush = document.getElementById('send-push').checked;
        const title = document.getElementById('admin-notification-title').value.trim();
        const message = document.getElementById('admin-notification-message').value.trim();
        const priority = document.getElementById('admin-notification-priority').value;
        const overridePreferences = document.getElementById('override-preferences').checked;
        const category = document.getElementById('admin-notification-category')?.value || null;
        const tagsInput = document.getElementById('admin-notification-tags')?.value.trim();
        const tags = tagsInput ? tagsInput.split(',').map(t => t.trim()).filter(t => t.length > 0) : null;

        // Get redirect URL based on selected type (only for push)
        // IMPORTANT: Only process redirect URL if push notifications are enabled
        let redirectUrl = null;
        if (sendPush) {
            const appGroup = document.getElementById('redirect-app-screen-group');
            if (appGroup && !appGroup.classList.contains('hidden')) {
                redirectUrl = document.getElementById('admin-notification-redirect-screen').value.trim() || null;
            } else {
                redirectUrl = document.getElementById('admin-notification-redirect-url').value.trim() || null;
            }
        } else {
            // Ensure redirect URL is not sent if push is not selected
            redirectUrl = null;
        }

        // Check campaign type
        const campaignType = document.querySelector('input[name="campaign-type"]:checked')?.value || 'user';

        // Handle entity-based campaigns
        if (campaignType === 'entity') {
            return this.handleEntityCampaignSubmit(e, sendEmail, sendPush, title, message, priority, overridePreferences, category, tags, redirectUrl);
        }

        const userIds = Array.from(this.selectedUsers.keys());

        // Client-side validation for immediate UX feedback
        // Note: All validation is also done server-side for security
        if (!sendEmail && !sendPush) {
            // No JS status: rely on backend flash (user can submit again after fixing)
            return;
        }

        if (userIds.length === 0) {
            return;
        }

        if (!title) {
            document.getElementById('admin-notification-title').focus();
            return;
        }

        if (!message) {
            document.getElementById('admin-notification-message').focus();
            return;
        }

        if (title.length > 100) {
            return;
        }

        if (message.length > 500) {
            return;
        }

        // Validate redirect URL only if push notifications are enabled and URL is provided
        if (sendPush && redirectUrl) {
            if (redirectUrl.length > 500) {
                return;
            }

            if (!redirectUrl.startsWith('/') && !redirectUrl.startsWith('http://') && !redirectUrl.startsWith('https://')) {
                return;
            }
        }

        // Disable submit button
        const submitButton = document.getElementById('send-admin-notification');
        const originalNodes = Array.from(submitButton.childNodes).map((n) => n.cloneNode(true));
        const restoreSubmitButton = () => {
            submitButton.replaceChildren(...originalNodes.map((n) => n.cloneNode(true)));
        };
        submitButton.disabled = true;
        submitButton.replaceChildren();
        {
            const icon = document.createElement('i');
            icon.className = 'fas fa-spinner fa-spin mr-2';
            submitButton.append(icon, document.createTextNode('Sending...'));
        }

        try {

            // Note: Currently only push notifications are supported via API
            // Email notifications are sent automatically when notification is created
            const data = await _anFetch('/notifications/api/admin/send-push', {
                method: 'POST',
                body: JSON.stringify({
                    user_ids: userIds,
                    title: title,
                    message: message,
                    priority: priority,
                    redirect_url: sendPush ? (redirectUrl || null) : null,  // Only include redirect_url if push is enabled
                    override_preferences: overridePreferences,  // Allow admin to override user preferences
                    send_email: sendEmail,  // Include delivery method flags
                    send_push: sendPush  // Include delivery method flags
                })
            });

            if (data && data.success === false) {
                // Stay on the same tab and keep form state; render backend-provided message into the standard flash area.
                this.renderBackendFlash(
                    data.flash_message || data.error || 'Request failed.',
                    data.flash_category || 'danger'
                );
                return;
            }

            // Success: reload (campaign list / counts are server-rendered)
            window.location.reload();
        } catch (error) {
            console.error('Error sending notification:', error);
            // If request fails before we get JSON, we can't show backend flash without a reload.
            window.location.reload();
        } finally {
            submitButton.disabled = false;
            restoreSubmitButton();
        }
    }

    // Flash messages are now managed by the backend routes via Flask's flash() function
    // This method is kept for backwards compatibility but should not be used
    // Instead, reload the page after AJAX operations to show flash messages from the backend

    loadTemplate(templateType) {
        console.log('loadTemplate called with:', templateType);
        const titleInput = document.getElementById('admin-notification-title');
        const messageInput = document.getElementById('admin-notification-message');
        const prioritySelect = document.getElementById('admin-notification-priority');

        console.log('Input elements found:', {
            titleInput: !!titleInput,
            messageInput: !!messageInput,
            prioritySelect: !!prioritySelect
        });

        if (!titleInput || !messageInput) {
            console.error('Required input elements not found');
            return;
        }

        // Load templates from DB (injected via window.NOTIFICATION_TEMPLATES)
        const dbTemplates = window.NOTIFICATION_TEMPLATES || {};
        const template = dbTemplates[templateType];

        if (!template) {
            console.error('Template not found:', templateType);
            return;
        }

        console.log('Applying template:', template);

        // Replace {{org_name}} placeholder with actual org name
        const orgName = window.ORG_NAME || 'NGO Databank';
        const interpolate = (text) => (text || '').replace(/\{\{\s*org_name\s*\}\}/gi, orgName);

        titleInput.value = interpolate(template.title);
        titleInput.dispatchEvent(new Event('input', { bubbles: true }));

        messageInput.value = interpolate(template.message);
        messageInput.dispatchEvent(new Event('input', { bubbles: true }));

        if (prioritySelect && template.priority) {
            prioritySelect.value = template.priority;
            prioritySelect.dispatchEvent(new Event('change', { bubbles: true }));
        }

        // Ensure email and push are enabled
        const emailCheckbox = document.getElementById('send-email');
        const pushCheckbox = document.getElementById('send-push');
        if (emailCheckbox) {
            emailCheckbox.checked = true;
            emailCheckbox.dispatchEvent(new Event('change', { bubbles: true }));
        }
        if (pushCheckbox) {
            pushCheckbox.checked = true;
            pushCheckbox.dispatchEvent(new Event('change', { bubbles: true }));
        }

        // Force a re-render by focusing and blurring
        titleInput.focus();
        setTimeout(() => {
            titleInput.blur();
            this.updatePreview();
        }, 50);

        console.log('Template applied successfully');
    }

    resetForm() {
        document.getElementById('admin-notification-form')?.reset();
        this.selectedUsers.clear();
        this.updateSelectedUsersDisplay();
        const userSearchInput = document.getElementById('admin-notification-user-search');
        if (userSearchInput) userSearchInput.value = '';
        document.getElementById('admin-notification-user-results')?.classList.add('hidden');

        // Reset entity-based campaign fields
        this.selectedEntities.clear();
        this.updateEntityCount();
        this.updateSelectedEntitiesDisplay();
        // Reset entity type checkboxes (only country checked by default)
        document.querySelectorAll('.entity-type-checkbox').forEach(cb => {
            cb.checked = (cb.value === 'country');
        });
        // Clear entity list
        const entityList = document.getElementById('entity-selection-list');
        if (entityList) {
            entityList.classList.add('hidden');
            entityList.replaceChildren();
        }
        const loadingIndicator = document.getElementById('entity-selection-loading');
        if (loadingIndicator) {
            loadingIndicator.classList.remove('hidden');
        }
        const campaignTypeUser = document.getElementById('campaign-type-user');
        if (campaignTypeUser) {
            campaignTypeUser.checked = true;
            this.handleCampaignTypeChange('user');
        }

        // Reset drag and drop distribution rules
        if (this.distributionRules) {
            this.distributionRules = { to: [], cc: [] };
            this.updateFieldDisplay('to');
            this.updateFieldDisplay('cc');
            this.updateDistributionPreview();
            this.updateUserTypesPool();
        }

        // Reset redirect type to app screen
        this.handleRedirectTypeChange('app');

        // Reset checkboxes to checked
        const emailCheckbox = document.getElementById('send-email');
        const pushCheckbox = document.getElementById('send-push');
        if (emailCheckbox) {
            emailCheckbox.checked = true;
            emailCheckbox.disabled = false;
        }
        if (pushCheckbox) pushCheckbox.checked = true;

        // Reset campaign modal fields
        const campaignModalName = document.getElementById('campaign-modal-name');
        if (campaignModalName) campaignModalName.value = '';
        const campaignModalDescription = document.getElementById('campaign-modal-description');
        if (campaignModalDescription) campaignModalDescription.value = '';
        const campaignModalScheduled = document.getElementById('campaign-modal-scheduled-for');
        if (campaignModalScheduled) campaignModalScheduled.value = '';

        // Reset campaign edit fields
        this.hideCampaignEditFields();
        this.editingCampaignId = null;
        this.updateTabNameForEdit(false);
        this.closeCampaignModal();

        // Reset attachment section
        const staticAttachmentsInput = document.getElementById('notification-static-attachments');
        const staticAttachmentsList = document.getElementById('static-attachments-list');
        const clearStaticBtn = document.getElementById('clear-static-attachments');
        if (staticAttachmentsInput) {
            staticAttachmentsInput.value = '';
            staticAttachmentsList?.classList.add('hidden');
            staticAttachmentsList?.replaceChildren();
            clearStaticBtn?.classList.add('hidden');
        }
        const assignmentSelect = document.getElementById('attachment-assignment-select');
        if (assignmentSelect && assignmentSelect.options.length) {
            assignmentSelect.selectedIndex = 0;
        }
        document.getElementById('attachment-autogenerated-section')?.classList.add('hidden');

        // Clear preview (will update based on checkbox states)
        this.updatePreview();
    }

    switchTab(tab) {
        // Hide all tab contents
        document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.add('hidden');
        });

        // Remove active class from all tabs
        document.querySelectorAll('.tab-button').forEach(button => {
            button.classList.remove('active', 'border-blue-600', 'text-blue-600');
            button.classList.add('border-transparent', 'text-gray-500');
        });

        // Show selected tab content
        const contentId = `tab-content-${tab}`;
        const content = document.getElementById(contentId);
        if (content) {
            content.classList.remove('hidden');
        }

        // Activate selected tab button
        const tabId = `tab-${tab}`;
        const tabButton = document.getElementById(tabId);
        if (tabButton) {
            tabButton.classList.add('active', 'border-blue-600', 'text-blue-600');
            tabButton.classList.remove('border-transparent', 'text-gray-500');
        }

        // Initialize grid if needed
        if (tab === 'view-all' && window.initializeNotificationsGridIfNeeded) {
            window.initializeNotificationsGridIfNeeded();
        } else if (tab === 'campaigns' && window.initializeCampaignsGridIfNeeded) {
            window.initializeCampaignsGridIfNeeded();
        }
    }

    async loadCampaigns(statusFilter = '') {
        // Campaigns are now loaded via AG Grid, so this function just refreshes the grid
        // The grid is initialized from server-rendered data
        if (window.campaignsGridHelper) {
            try {
                let url = '/notifications/api/admin/campaigns';
                if (statusFilter) {
                    url += `?status=${statusFilter}`;
                }

                const data = await _anFetch(url);

                if (data.success && data.campaigns) {
                    // Update grid data using the helper method
                    window.campaignsGridHelper.setRowData(data.campaigns);
                    window.campaignsGridHelper.refresh();
                }
            } catch (error) {
                console.error('Error refreshing campaigns:', error);
            }
        } else {
            // Grid not initialized yet, trigger initialization
            if (window.initializeCampaignsGridIfNeeded) {
                window.initializeCampaignsGridIfNeeded();
            }
        }
    }

    async sendCampaign(campaignId) {
        if (window.showSubmitConfirmation) {
            window.showSubmitConfirmation(
                'Send this campaign now? This will immediately send notifications to all selected users.',
                () => {
                    this.performSendCampaign(campaignId);
                },
                null
            );
            return;
        } else {
            this.performSendCampaign(campaignId);
        }
    }

    async performSendCampaign(campaignId) {

        try {
            await _anFetch(`/notifications/api/admin/campaigns/${campaignId}/send`, {
                method: 'POST'
            });
            // No JS status: reload to show backend flash and updated campaign status.
            window.location.reload();
        } catch (error) {
            console.error('Error sending campaign:', error);
            window.location.reload();
        }
    }

    async deleteCampaign(campaignId) {
        if (window.showDangerConfirmation) {
            window.showDangerConfirmation(
                'Are you sure you want to delete this campaign? This action cannot be undone.',
                () => {
                    this.performDeleteCampaign(campaignId);
                },
                null,
                'Delete',
                'Cancel',
                'Delete Campaign?'
            );
            return;
        } else {
            this.performDeleteCampaign(campaignId);
        }
    }

    async performDeleteCampaign(campaignId) {

        try {
            const data = await _anFetch(`/notifications/api/admin/campaigns/${campaignId}`, {
                method: 'DELETE'
            });
            if (data && data.success) {
                window.location.reload();
            } else {
                window.location.reload();
            }
        } catch (error) {
            console.error('Error deleting campaign:', error);
            window.location.reload();
        }
    }

    async editCampaign(campaignId) {
        try {
            // Fetch campaign data
            const data = await _anFetch(`/notifications/api/admin/campaigns/${campaignId}`);
            if (!data.success || !data.campaign) {
                throw new Error('Campaign not found');
            }

            const campaign = data.campaign;

            // Check if campaign can be edited
            if (campaign.status !== 'draft' && campaign.status !== 'scheduled') {
                return;
            }

            // Switch to send tab
            this.switchTab('send');

            // Populate the main form with campaign data
            document.getElementById('admin-notification-title').value = campaign.title || '';
            document.getElementById('admin-notification-message').value = campaign.message || '';
            document.getElementById('admin-notification-priority').value = campaign.priority || 'normal';
            document.getElementById('send-email').checked = campaign.send_email !== false;
            document.getElementById('send-push').checked = campaign.send_push !== false;
            document.getElementById('override-preferences').checked = campaign.override_preferences || false;

            if (campaign.category) {
                const categoryInput = document.getElementById('admin-notification-category');
                if (categoryInput) {
                    categoryInput.value = campaign.category;
                }
            }

            if (campaign.tags && Array.isArray(campaign.tags)) {
                const tagsInput = document.getElementById('admin-notification-tags');
                if (tagsInput) {
                    tagsInput.value = campaign.tags.join(', ');
                }
            }

            // Handle redirect URL
            if (campaign.redirect_url) {
                if (campaign.redirect_type === 'app') {
                    document.getElementById('admin-notification-redirect-type').value = 'app';
                    document.getElementById('admin-notification-redirect-screen').value = campaign.redirect_url;
                    document.getElementById('redirect-app-screen-group').classList.remove('hidden');
                    document.getElementById('redirect-custom-url-group').classList.add('hidden');
                } else {
                    document.getElementById('admin-notification-redirect-type').value = 'custom';
                    document.getElementById('admin-notification-redirect-url').value = campaign.redirect_url;
                    document.getElementById('redirect-app-screen-group').classList.add('hidden');
                    document.getElementById('redirect-custom-url-group').classList.remove('hidden');
                }
            }

            // Load selected users
            if (campaign.user_ids && Array.isArray(campaign.user_ids)) {
                this.selectedUsers.clear();
                // For now, store user IDs - users can be re-selected if needed
                // The campaign will work with the stored user IDs
                campaign.user_ids.forEach(userId => {
                    // Store with minimal info - user details will be loaded if they search
                    this.selectedUsers.set(userId, {
                        id: userId,
                        name: `User ${userId}`,
                        email: '',
                        role: ''
                    });
                });
                this.updateSelectedUsersDisplay();
                // Note: User names/emails will be populated if user searches for them
                // For editing, the user IDs are preserved which is what matters
            }

            // Store campaign ID for update
            this.editingCampaignId = campaignId;

            // Show campaign edit fields in the main form
            this.showCampaignEditFields(campaign);

            // Update tab name
            this.updateTabNameForEdit(true);

        } catch (error) {
            console.error('Error loading campaign:', error);
            // No JS status; let console show details.
        }
    }

    async viewCampaignRecipients(campaignId) {
        const modal = document.getElementById('campaign-recipients-modal');
        const loadingEl = document.getElementById('recipients-loading');
        const listEl = document.getElementById('recipients-list');
        const totalCountEl = document.getElementById('recipients-total-count');
        const searchInput = document.getElementById('recipients-search');

        if (!modal) return;

        // Show modal
        modal.classList.remove('hidden');

        // Clear previous results
        listEl.replaceChildren();
        searchInput.value = '';

        // Show loading
        loadingEl.classList.remove('hidden');
        listEl.classList.add('hidden');

        // Fetch recipients
        try {
            const data = await _anFetch(`/admin/api/notifications/campaigns/${campaignId}/recipients`);

            if (!data.success) {
                throw new Error(data.error || 'Failed to load recipients');
            }

            // Store recipients for filtering
            this.campaignRecipients = data.recipients || [];

            // Hide loading and show list
            loadingEl.classList.add('hidden');
            listEl.classList.remove('hidden');

            // Display recipients
            this.displayCampaignRecipients(this.campaignRecipients);

            // Update total count
            if (totalCountEl) {
                totalCountEl.textContent = data.total || 0;
            }

        } catch (error) {
            console.error('Error loading recipients:', error);
            loadingEl.classList.add('hidden');
            listEl.replaceChildren();
            const p = document.createElement('p');
            p.className = 'text-red-600 text-center py-4';
            p.textContent = `Error loading recipients: ${error?.message || ''}`;
            listEl.appendChild(p);
        }
    }

    displayCampaignRecipients(recipients) {
        const listEl = document.getElementById('recipients-list');

        if (!recipients || recipients.length === 0) {
            listEl.replaceChildren();
            const p = document.createElement('p');
            p.className = 'text-gray-500 text-center py-8';
            p.textContent = 'No recipients found';
            listEl.appendChild(p);
            return;
        }

        let html = '<div class="space-y-2">';
        recipients.forEach(recipient => {
            const roleText = this.formatRbacRoleCodes(recipient.rbac_role_codes || []);
            html += `
                <div class="flex items-center justify-between p-3 bg-white border border-gray-200 rounded-lg hover:bg-gray-50">
                    <div class="flex-1">
                        <div class="font-medium text-gray-900">${this.escapeHtml(recipient.name || recipient.email)}</div>
                        <div class="text-sm text-gray-600">${this.escapeHtml(recipient.email)}</div>
                    </div>
                    <div class="ml-4">
                        <span class="px-2 py-1 text-xs font-medium rounded bg-gray-100 text-gray-800">${this.escapeHtml(roleText)}</span>
                    </div>
                </div>
            `;
        });
        html += '</div>';

        listEl.replaceChildren();
        const frag = document.createRange().createContextualFragment(html);
        listEl.appendChild(frag);
    }

    filterCampaignRecipients(searchQuery) {
        if (!this.campaignRecipients) return;

        const query = searchQuery.toLowerCase().trim();
        let filtered = this.campaignRecipients;

        if (query) {
            filtered = this.campaignRecipients.filter(recipient => {
                const name = (recipient.name || '').toLowerCase();
                const email = (recipient.email || '').toLowerCase();
                return name.includes(query) || email.includes(query);
            });
        }

        this.displayCampaignRecipients(filtered);

        // Update total count
        const totalCountEl = document.getElementById('recipients-total-count');
        if (totalCountEl) {
            totalCountEl.textContent = filtered.length;
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    closeCampaignRecipientsModal() {
        const modal = document.getElementById('campaign-recipients-modal');
        if (modal) {
            modal.classList.add('hidden');
        }
        this.campaignRecipients = null;
    }

    openCampaignModal() {
        // Validate form before opening modal
        const userIds = Array.from(this.selectedUsers.keys());
        const title = document.getElementById('admin-notification-title')?.value.trim();
        const message = document.getElementById('admin-notification-message')?.value.trim();

        if (userIds.length === 0) {
            return;
        }

        if (!title) {
            document.getElementById('admin-notification-title')?.focus();
            return;
        }

        if (!message) {
            document.getElementById('admin-notification-message')?.focus();
            return;
        }

        // Clear editing state
        this.editingCampaignId = null;

        // Reset modal to create mode
        this.setCampaignModalMode('create');

        // Update min date for scheduled input
        const campaignScheduledInput = document.getElementById('campaign-modal-scheduled-for');
        if (campaignScheduledInput) {
            const now = new Date();
            now.setMinutes(now.getMinutes() + 1);
            campaignScheduledInput.min = now.toISOString().slice(0, 16);
            campaignScheduledInput.value = '';
        }

        // Clear modal fields
        document.getElementById('campaign-modal-name').value = '';
        document.getElementById('campaign-modal-description').value = '';

        // Show modal
        const modal = document.getElementById('campaign-modal');
        if (modal) {
            modal.classList.remove('hidden');
        }
    }

    showCampaignEditFields(campaign) {
        // Show campaign edit fields section
        const campaignFields = document.getElementById('campaign-edit-fields');
        if (campaignFields) {
            campaignFields.classList.remove('hidden');
        }

        // Enable and require name input only when edit fields are visible
        const nameInput = document.getElementById('campaign-edit-name');
        const descInput = document.getElementById('campaign-edit-description');
        const scheduledInput = document.getElementById('campaign-edit-scheduled-for');
        if (nameInput) {
            nameInput.disabled = false;
            nameInput.required = true;
        }
        if (descInput) descInput.disabled = false;
        if (scheduledInput) scheduledInput.disabled = false;

        // Populate campaign fields
        document.getElementById('campaign-edit-name').value = campaign.name || '';
        document.getElementById('campaign-edit-description').value = campaign.description || '';

        // Set scheduled date if exists
        const campaignScheduledInput = document.getElementById('campaign-edit-scheduled-for');
        if (campaignScheduledInput) {
            if (campaign.scheduled_for) {
                // Convert ISO string to datetime-local format
                const scheduledDate = new Date(campaign.scheduled_for);
                const localDate = new Date(scheduledDate.getTime() - scheduledDate.getTimezoneOffset() * 60000);
                campaignScheduledInput.value = localDate.toISOString().slice(0, 16);
            } else {
                campaignScheduledInput.value = '';
            }
            // Update min date
            const now = new Date();
            now.setMinutes(now.getMinutes() + 1);
            campaignScheduledInput.min = now.toISOString().slice(0, 16);
        }

        // Hide "Save as Campaign" button, show "Update Campaign" button
        const saveAsCampaignBtn = document.getElementById('save-as-campaign-btn');
        const updateCampaignBtn = document.getElementById('update-campaign-btn');
        const sendNotificationBtn = document.getElementById('send-admin-notification');

        if (saveAsCampaignBtn) saveAsCampaignBtn.classList.add('hidden');
        if (updateCampaignBtn) updateCampaignBtn.classList.remove('hidden');
        if (sendNotificationBtn) sendNotificationBtn.classList.add('hidden');
    }

    hideCampaignEditFields() {
        // Hide campaign edit fields section
        const campaignFields = document.getElementById('campaign-edit-fields');
        if (campaignFields) {
            campaignFields.classList.add('hidden');
        }

        // When hidden, remove required + disable inputs so they don't participate in HTML validation
        const nameInput = document.getElementById('campaign-edit-name');
        const descInput = document.getElementById('campaign-edit-description');
        const scheduledInput = document.getElementById('campaign-edit-scheduled-for');
        if (nameInput) {
            nameInput.required = false;
            nameInput.disabled = true;
        }
        if (descInput) descInput.disabled = true;
        if (scheduledInput) scheduledInput.disabled = true;

        // Clear campaign fields
        document.getElementById('campaign-edit-name').value = '';
        document.getElementById('campaign-edit-description').value = '';
        document.getElementById('campaign-edit-scheduled-for').value = '';

        // Show "Save as Campaign" button, hide "Update Campaign" button
        const saveAsCampaignBtn = document.getElementById('save-as-campaign-btn');
        const updateCampaignBtn = document.getElementById('update-campaign-btn');
        const sendNotificationBtn = document.getElementById('send-admin-notification');

        if (saveAsCampaignBtn) saveAsCampaignBtn.classList.remove('hidden');
        if (updateCampaignBtn) updateCampaignBtn.classList.add('hidden');
        if (sendNotificationBtn) sendNotificationBtn.classList.remove('hidden');
    }

    updateTabNameForEdit(isEditing) {
        const tabLabel = document.getElementById('tab-send-label');
        if (tabLabel) {
            if (isEditing) {
                tabLabel.textContent = 'Edit Campaign';
            } else {
                tabLabel.textContent = 'Create Notification';
            }
        }
    }

    async handleCampaignUpdate() {
        // Validate campaign edit fields
        const campaignName = document.getElementById('campaign-edit-name')?.value.trim();
        const campaignDescription = document.getElementById('campaign-edit-description')?.value.trim();
        const campaignScheduledFor = document.getElementById('campaign-edit-scheduled-for')?.value;

        if (!this.editingCampaignId) {
            return;
        }

        if (!campaignName) {
            document.getElementById('campaign-edit-name')?.focus();
            return;
        }

        // Validate scheduled time if provided
        if (campaignScheduledFor) {
            const scheduledDate = new Date(campaignScheduledFor);
            const now = new Date();
            if (scheduledDate <= now) {
                return;
            }
        }

        // Validate core notification fields (same as send/create)
        const userIds = Array.from(this.selectedUsers.keys());
        const title = document.getElementById('admin-notification-title')?.value.trim();
        const message = document.getElementById('admin-notification-message')?.value.trim();

        if (userIds.length === 0) {
            return;
        }
        if (!title) {
            document.getElementById('admin-notification-title')?.focus();
            return;
        }
        if (!message) {
            document.getElementById('admin-notification-message')?.focus();
            return;
        }

        // Collect remaining form data
        const sendEmail = document.getElementById('send-email')?.checked ?? true;
        const sendPush = document.getElementById('send-push')?.checked ?? true;
        const priority = document.getElementById('admin-notification-priority')?.value || 'normal';
        const overridePreferences = document.getElementById('override-preferences')?.checked ?? false;
        const category = document.getElementById('admin-notification-category')?.value || null;
        const tagsInput = document.getElementById('admin-notification-tags')?.value.trim();
        const tags = tagsInput ? tagsInput.split(',').map(t => t.trim()).filter(t => t.length > 0) : null;

        // Get redirect URL
        let redirectUrl = null;
        if (sendPush) {
            const appGroup = document.getElementById('redirect-app-screen-group');
            if (appGroup && !appGroup.classList.contains('hidden')) {
                redirectUrl = document.getElementById('admin-notification-redirect-screen')?.value.trim() || null;
            } else {
                redirectUrl = document.getElementById('admin-notification-redirect-url')?.value.trim() || null;
            }
        }

        // Disable submit button while saving
        const updateBtn = document.getElementById('update-campaign-btn');
        const sendBtn = document.getElementById('send-admin-notification');
        const btnToDisable = updateBtn || sendBtn;
        const originalNodes = btnToDisable ? Array.from(btnToDisable.childNodes).map((n) => n.cloneNode(true)) : null;
        const restoreBtn = () => {
            if (!btnToDisable || !originalNodes) return;
            btnToDisable.replaceChildren(...originalNodes.map((n) => n.cloneNode(true)));
        };
        if (btnToDisable) {
            btnToDisable.disabled = true;
            btnToDisable.replaceChildren();
            {
                const icon = document.createElement('i');
                icon.className = 'fas fa-spinner fa-spin mr-2';
                btnToDisable.append(icon, document.createTextNode('Updating...'));
            }
        }

        try {
            const requestBody = {
                name: campaignName,
                description: campaignDescription || null,
                title: title,
                message: message,
                priority: priority,
                category: category,
                tags: tags,
                send_email: sendEmail,
                send_push: sendPush,
                override_preferences: overridePreferences,
                redirect_type: sendPush && redirectUrl ? (redirectUrl.startsWith('/') ? 'app' : 'custom') : null,
                redirect_url: sendPush ? redirectUrl : null,
                scheduled_for: campaignScheduledFor || null,
                user_selection_type: 'manual',
                user_ids: userIds,
                user_filters: null
            };

            const data = await _anFetch(`/notifications/api/admin/campaigns/${this.editingCampaignId}`, {
                method: 'PUT',
                body: JSON.stringify(requestBody)
            });
            if (data.success) {
                window.location.reload();
            } else {
                throw new Error(data.error || 'Failed to update campaign');
            }
        } catch (error) {
            console.error('Error updating campaign:', error);
            window.location.reload();
        } finally {
            if (btnToDisable) {
                btnToDisable.disabled = false;
                restoreBtn();
            }
        }
    }

    setCampaignModalMode(mode) {
        const modalTitle = document.querySelector('#campaign-modal h3');
        const submitButton = document.getElementById('create-campaign-submit');

        if (mode === 'edit') {
            if (modalTitle) {
                modalTitle.replaceChildren();
                {
                    const icon = document.createElement('i');
                    icon.className = 'fas fa-pen mr-2 text-blue-600';
                    modalTitle.append(icon, document.createTextNode('Edit Campaign'));
                }
            }
            if (submitButton) {
                submitButton.replaceChildren();
                {
                    const icon = document.createElement('i');
                    icon.className = 'fas fa-save w-4 h-4 inline-block mr-2';
                    submitButton.append(icon, document.createTextNode('Update Campaign'));
                }
            }
        } else {
            if (modalTitle) {
                modalTitle.replaceChildren();
                {
                    const icon = document.createElement('i');
                    icon.className = 'fas fa-calendar-alt mr-2 text-blue-600';
                    modalTitle.append(icon, document.createTextNode('Save as Campaign'));
                }
            }
            if (submitButton) {
                submitButton.replaceChildren();
                {
                    const icon = document.createElement('i');
                    icon.className = 'fas fa-save w-4 h-4 inline-block mr-2';
                    submitButton.append(icon, document.createTextNode('Create Campaign'));
                }
            }
        }
    }

    closeCampaignModal() {
        const modal = document.getElementById('campaign-modal');
        if (modal) {
            modal.classList.add('hidden');
        }
        // Clear editing state
        this.editingCampaignId = null;
    }

    async handleCampaignSubmit() {
        const campaignName = document.getElementById('campaign-modal-name')?.value.trim();
        const campaignDescription = document.getElementById('campaign-modal-description')?.value.trim();
        const campaignScheduledFor = document.getElementById('campaign-modal-scheduled-for')?.value;

        // Validate campaign name
        if (!campaignName) {
            document.getElementById('campaign-modal-name')?.focus();
            return;
        }

        // Validate scheduled time if provided
        if (campaignScheduledFor) {
            const scheduledDate = new Date(campaignScheduledFor);
            const now = new Date();
            if (scheduledDate <= now) {
                return;
            }
        }

        // Get form data
        const sendEmail = document.getElementById('send-email').checked;
        const sendPush = document.getElementById('send-push').checked;
        const title = document.getElementById('admin-notification-title').value.trim();
        const message = document.getElementById('admin-notification-message').value.trim();
        const priority = document.getElementById('admin-notification-priority').value;
        const overridePreferences = document.getElementById('override-preferences').checked;
        const category = document.getElementById('admin-notification-category')?.value || null;
        const tagsInput = document.getElementById('admin-notification-tags')?.value.trim();
        const tags = tagsInput ? tagsInput.split(',').map(t => t.trim()).filter(t => t.length > 0) : null;
        const userIds = Array.from(this.selectedUsers.keys());

        // Get redirect URL
        let redirectUrl = null;
        if (sendPush) {
            const appGroup = document.getElementById('redirect-app-screen-group');
            if (appGroup && !appGroup.classList.contains('hidden')) {
                redirectUrl = document.getElementById('admin-notification-redirect-screen').value.trim() || null;
            } else {
                redirectUrl = document.getElementById('admin-notification-redirect-url').value.trim() || null;
            }
        }

        // Disable submit button
        const submitButton = document.getElementById('create-campaign-submit');
        const originalNodes = Array.from(submitButton.childNodes).map((n) => n.cloneNode(true));
        const restoreSubmitButton = () => {
            submitButton.replaceChildren(...originalNodes.map((n) => n.cloneNode(true)));
        };
        submitButton.disabled = true;
        const isEdit = !!this.editingCampaignId;
        submitButton.replaceChildren();
        {
            const icon = document.createElement('i');
            icon.className = 'fas fa-spinner fa-spin mr-2';
            submitButton.append(icon, document.createTextNode(isEdit ? 'Updating...' : 'Creating...'));
        }

        try {
            const requestBody = {
                name: campaignName,
                description: campaignDescription || null,
                title: title,
                message: message,
                priority: priority,
                category: category,
                tags: tags,
                send_email: sendEmail,
                send_push: sendPush,
                override_preferences: overridePreferences,
                redirect_type: sendPush && redirectUrl ? (redirectUrl.startsWith('/') ? 'app' : 'custom') : null,
                redirect_url: sendPush ? redirectUrl : null,
                scheduled_for: campaignScheduledFor || null,
                user_selection_type: 'manual',
                user_ids: userIds,
                user_filters: null
            };

            const url = isEdit
                ? `/notifications/api/admin/campaigns/${this.editingCampaignId}`
                : '/notifications/api/admin/campaigns';
            const method = isEdit ? 'PUT' : 'POST';

            const data = await _anFetch(url, {
                method: method,
                body: JSON.stringify(requestBody)
            });
            if (data.success) {
                window.location.reload();
            } else {
                throw new Error(data.error || `Failed to ${isEdit ? 'update' : 'create'} campaign`);
            }
        } catch (error) {
            console.error(`Error ${isEdit ? 'updating' : 'creating'} campaign:`, error);
            window.location.reload();
        } finally {
            submitButton.disabled = false;
            restoreSubmitButton();
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    switchTab(tab) {
        const sendTab = document.getElementById('tab-send');
        const viewAllTab = document.getElementById('tab-view-all');
        const campaignsTab = document.getElementById('tab-campaigns');
        const sendContent = document.getElementById('tab-content-send');
        const viewAllContent = document.getElementById('tab-content-view-all');
        const campaignsContent = document.getElementById('tab-content-campaigns');

        // Remove active state from all tabs
        [sendTab, viewAllTab, campaignsTab].forEach(t => {
            if (t) {
                t.classList.remove('active', 'border-blue-600', 'text-blue-600');
                t.classList.add('border-transparent', 'text-gray-500');
            }
        });

        // Hide all content
        [sendContent, viewAllContent, campaignsContent].forEach(c => {
            if (c) c.classList.add('hidden');
        });

        if (tab === 'send') {
            window.location.hash = '#send';
            sendTab?.classList.add('active', 'border-blue-600', 'text-blue-600');
            sendTab?.classList.remove('border-transparent', 'text-gray-500');
            sendContent?.classList.remove('hidden');
        } else if (tab === 'view-all') {
            window.location.hash = '#view-all';
            viewAllTab?.classList.add('active', 'border-blue-600', 'text-blue-600');
            viewAllTab?.classList.remove('border-transparent', 'text-gray-500');
            viewAllContent?.classList.remove('hidden');
            // Trigger grid initialization (data is server-rendered, no API call needed)
            if (window.initializeNotificationsGridIfNeeded) {
                setTimeout(() => window.initializeNotificationsGridIfNeeded(), 300);
            }
        } else if (tab === 'campaigns') {
            window.location.hash = '#campaigns';
            campaignsTab?.classList.add('active', 'border-blue-600', 'text-blue-600');
            campaignsTab?.classList.remove('border-transparent', 'text-gray-500');
            campaignsContent?.classList.remove('hidden');
            this.loadCampaigns();
        }
    }

    // View All tab now uses AG Grid - no need for custom loading/filtering methods
    // All filtering is handled by AG Grid's built-in column filters

    escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // ========== Bulk Selection Enhanced Features ==========

    initBulkSelectionFeatures() {
        // Text search with debouncing
        const searchInput = document.getElementById('bulk-search-users');
        if (searchInput) {
            searchInput.addEventListener('input', () => {
                clearTimeout(this.previewTimeout);
                this.previewTimeout = setTimeout(() => {
                    this.previewPage = 1;
                    this.loadPreviewUsers();
                }, 500);
            });
        }

        // Role checkboxes
        document.querySelectorAll('.bulk-role-checkbox').forEach(checkbox => {
            checkbox.addEventListener('change', () => {
                this.updateRoleCount();
                this.previewPage = 1;
                this.loadPreviewUsers();
            });
        });

        // Toggle collapsible sections
        const toggleRoleFilters = document.getElementById('toggle-role-filters');
        const roleFiltersContent = document.getElementById('role-filters-content');
        const roleFiltersChevron = document.getElementById('role-filters-chevron');
        if (toggleRoleFilters && roleFiltersContent && roleFiltersChevron) {
            toggleRoleFilters.addEventListener('click', () => {
                const isHidden = roleFiltersContent.classList.contains('hidden');
                roleFiltersContent.classList.toggle('hidden');
                roleFiltersChevron.style.transform = isHidden ? 'rotate(180deg)' : 'rotate(0deg)';
            });
        }

        const toggleAssignmentFilters = document.getElementById('toggle-assignment-filters');
        const assignmentFiltersContent = document.getElementById('assignment-filters-content');
        const assignmentFiltersChevron = document.getElementById('assignment-filters-chevron');
        if (toggleAssignmentFilters && assignmentFiltersContent && assignmentFiltersChevron) {
            toggleAssignmentFilters.addEventListener('click', () => {
                const isHidden = assignmentFiltersContent.classList.contains('hidden');
                assignmentFiltersContent.classList.toggle('hidden');
                assignmentFiltersChevron.style.transform = isHidden ? 'rotate(180deg)' : 'rotate(0deg)';
            });
        }

        const toggleAccountStatus = document.getElementById('toggle-account-status');
        const accountStatusContent = document.getElementById('account-status-content');
        const accountStatusChevron = document.getElementById('account-status-chevron');
        if (toggleAccountStatus && accountStatusContent && accountStatusChevron) {
            toggleAccountStatus.addEventListener('click', () => {
                const isHidden = accountStatusContent.classList.contains('hidden');
                accountStatusContent.classList.toggle('hidden');
                accountStatusChevron.style.transform = isHidden ? 'rotate(180deg)' : 'rotate(0deg)';
            });
        }

        const toggleTemplateFilters = document.getElementById('toggle-template-filters');
        const templateFiltersContent = document.getElementById('template-filters-content');
        const templateFiltersChevron = document.getElementById('template-filters-chevron');
        if (toggleTemplateFilters && templateFiltersContent && templateFiltersChevron) {
            toggleTemplateFilters.addEventListener('click', () => {
                const isHidden = templateFiltersContent.classList.contains('hidden');
                templateFiltersContent.classList.toggle('hidden');
                templateFiltersChevron.style.transform = isHidden ? 'rotate(180deg)' : 'rotate(0deg)';
            });
        }

        const toggleAssignmentFormFilters = document.getElementById('toggle-assignment-form-filters');
        const assignmentFormFiltersContent = document.getElementById('assignment-form-filters-content');
        const assignmentFormFiltersChevron = document.getElementById('assignment-form-filters-chevron');
        if (toggleAssignmentFormFilters && assignmentFormFiltersContent && assignmentFormFiltersChevron) {
            toggleAssignmentFormFilters.addEventListener('click', () => {
                const isHidden = assignmentFormFiltersContent.classList.contains('hidden');
                assignmentFormFiltersContent.classList.toggle('hidden');
                assignmentFormFiltersChevron.style.transform = isHidden ? 'rotate(180deg)' : 'rotate(0deg)';
            });
        }

        // Account status checkboxes
        document.querySelectorAll('.bulk-account-status-checkbox').forEach(checkbox => {
            checkbox.addEventListener('change', () => {
                this.updateAccountStatusCount();
                this.previewPage = 1;
                this.loadPreviewUsers();
            });
        });

        // Assignment status checkboxes
        document.querySelectorAll('.bulk-assignment-status-checkbox').forEach(checkbox => {
            checkbox.addEventListener('change', () => {
                this.updateAssignmentStatusCount();
                this.checkAssignmentStatusForTemplateGroup();
                this.previewPage = 1;
                this.loadPreviewUsers();
            });
        });

        // Country multi-select (handled by Select2, but also listen for native change as fallback)
        const countrySelect = document.getElementById('bulk-select-country');
        if (countrySelect) {
            countrySelect.addEventListener('change', () => {
                this.updateCountryCount();
                this.previewPage = 1;
                this.loadPreviewUsers();
            });
        }

        // Entity type filter
        const entitySelect = document.getElementById('bulk-select-entity');
        if (entitySelect) {
            entitySelect.addEventListener('change', () => {
                this.previewPage = 1;
                this.loadPreviewUsers();
            });
        }


        // Template multi-select (handled by Select2, but also listen for native change as fallback)
        const templateSelect = document.getElementById('bulk-select-template');
        if (templateSelect) {
            templateSelect.addEventListener('change', () => {
                this.previewPage = 1;
                this.loadPreviewUsers();
            });
        }

        // Exclude already selected checkbox
        const excludeCheckbox = document.getElementById('bulk-exclude-selected');
        if (excludeCheckbox) {
            excludeCheckbox.addEventListener('change', () => {
                // Reload preview with new exclusion filter
                this.previewPage = 1;
                this.loadPreviewUsers();
            });
        }

        // Refresh preview button
        const refreshBtn = document.getElementById('refresh-preview');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', () => {
                this.previewPage = 1;
                this.loadPreviewUsers();
            });
        }

        // Select all/none buttons
        const selectAllBtn = document.getElementById('bulk-select-all-preview');
        const deselectAllBtn = document.getElementById('bulk-deselect-all-preview');
        if (selectAllBtn) {
            selectAllBtn.addEventListener('click', () => {
                this.selectedPreviewUsers.clear();
                const excludeSelected = document.getElementById('bulk-exclude-selected')?.checked;
                this.previewUsers.forEach(user => {
                    if (!excludeSelected || !this.selectedUsers.has(user.id)) {
                        this.selectedPreviewUsers.add(user.id);
                    }
                });
                this.renderPreviewUsers();
            });
        }
        if (deselectAllBtn) {
            deselectAllBtn.addEventListener('click', () => {
                this.selectedPreviewUsers.clear();
                this.renderPreviewUsers();
            });
        }

        // Add selected users button
        const addSelectedBtn = document.getElementById('add-selected-users');
        if (addSelectedBtn) {
            addSelectedBtn.addEventListener('click', () => {
                this.addSelectedPreviewUsers();
            });
        }

        // Pagination
        const prevBtn = document.getElementById('preview-prev');
        const nextBtn = document.getElementById('preview-next');
        if (prevBtn) {
            prevBtn.addEventListener('click', () => {
                if (this.previewPage > 1) {
                    this.previewPage--;
                    this.loadPreviewUsers();
                }
            });
        }
        if (nextBtn) {
            nextBtn.addEventListener('click', () => {
                if (this.previewPage < this.previewTotalPages) {
                    this.previewPage++;
                    this.loadPreviewUsers();
                }
            });
        }

        // Load preview when modal opens
        const modal = document.getElementById('bulk-selection-modal');
        if (modal) {
            const observer = new MutationObserver((mutations) => {
                mutations.forEach((mutation) => {
                    if (!modal.classList.contains('hidden')) {
                        // Modal opened, load preview
                        this.previewPage = 1;
                        this.loadPreviewUsers();
                    }
                });
            });
            observer.observe(modal, { attributes: true, attributeFilter: ['class'] });
        }
    }

    updateRoleCount() {
        const checked = document.querySelectorAll('.bulk-role-checkbox:checked');
        const countEl = document.getElementById('bulk-role-count');
        if (countEl) {
            if (checked.length > 0) {
                countEl.textContent = `${checked.length} role(s) selected`;
            } else {
                countEl.textContent = '';
            }
        }
    }

    updateAccountStatusCount() {
        const checked = document.querySelectorAll('.bulk-account-status-checkbox:checked');
        const countEl = document.getElementById('bulk-account-status-count');
        if (countEl) {
            if (checked.length > 0) {
                countEl.textContent = `${checked.length} status${checked.length === 1 ? '' : 'es'} selected`;
            } else {
                countEl.textContent = '';
            }
        }
    }

    updateAssignmentStatusCount() {
        const checked = document.querySelectorAll('.bulk-assignment-status-checkbox:checked');
        const countEl = document.getElementById('bulk-assignment-status-count');
        if (countEl) {
            if (checked.length > 0) {
                countEl.textContent = `${checked.length} status${checked.length === 1 ? '' : 'es'} selected`;
            } else {
                countEl.textContent = '';
            }
        }
    }

    updateTemplateFilterCount() {
        const templateFilterSelect = document.getElementById('bulk-select-template-filter');
        const countEl = document.getElementById('bulk-template-filter-count');
        if (templateFilterSelect && countEl) {
            let selected = 0;
            if (window.jQuery && window.jQuery.fn.select2 && $(templateFilterSelect).hasClass('select2-hidden-accessible')) {
                selected = $(templateFilterSelect).val() ? $(templateFilterSelect).val().length : 0;
            } else {
                selected = templateFilterSelect.selectedOptions.length;
            }
            if (selected > 0) {
                countEl.textContent = `${selected} template${selected === 1 ? '' : 's'} selected`;
                countEl.className = 'text-xs text-blue-600 font-medium mt-1';
            } else {
                countEl.textContent = 'No templates selected';
                countEl.className = 'text-xs text-gray-500 mt-1';
            }
        }
    }

    updateAssignmentFormCount() {
        const assignmentFormSelect = document.getElementById('bulk-select-assignment-form');
        const countEl = document.getElementById('bulk-assignment-form-count');
        if (assignmentFormSelect && countEl) {
            let selected = 0;
            if (window.jQuery && window.jQuery.fn.select2 && $(assignmentFormSelect).hasClass('select2-hidden-accessible')) {
                selected = $(assignmentFormSelect).val() ? $(assignmentFormSelect).val().length : 0;
            } else {
                selected = assignmentFormSelect.selectedOptions.length;
            }
            if (selected > 0) {
                countEl.textContent = `${selected} assignment${selected === 1 ? '' : 's'} selected`;
                countEl.className = 'text-xs text-blue-600 font-medium mt-1';
            } else {
                countEl.textContent = 'No assignments selected';
                countEl.className = 'text-xs text-gray-500 mt-1';
            }
        }
    }

    loadAssignmentsDropdown() {
        const assignmentFormSelect = document.getElementById('bulk-select-assignment-form');
        if (!assignmentFormSelect || !this.allAssignments) return;

        // Get selected template IDs
        const templateFilterSelect = document.getElementById('bulk-select-template-filter');
        let selectedTemplateIds = [];
        if (templateFilterSelect) {
            if (window.jQuery && window.jQuery.fn.select2 && $(templateFilterSelect).hasClass('select2-hidden-accessible')) {
                const selected = $(templateFilterSelect).val();
                selectedTemplateIds = selected ? (Array.isArray(selected) ? selected : [selected]).map(id => parseInt(id)) : [];
            } else {
                selectedTemplateIds = Array.from(templateFilterSelect.selectedOptions).map(opt => parseInt(opt.value)).filter(v => !isNaN(v));
            }
        }

        // Store currently selected assignment IDs to restore after filtering
        let currentSelected = [];
        if (window.jQuery && window.jQuery.fn.select2 && $(assignmentFormSelect).hasClass('select2-hidden-accessible')) {
            const selected = $(assignmentFormSelect).val();
            currentSelected = selected ? (Array.isArray(selected) ? selected : [selected]).map(id => parseInt(id)) : [];
        } else {
            currentSelected = Array.from(assignmentFormSelect.selectedOptions).map(opt => parseInt(opt.value)).filter(v => !isNaN(v));
        }

        // Clear existing options
        assignmentFormSelect.replaceChildren();

        // Filter assignments by selected templates (if any)
        let assignmentsToShow = this.allAssignments;
        if (selectedTemplateIds.length > 0) {
            assignmentsToShow = this.allAssignments.filter(assignment =>
                selectedTemplateIds.includes(assignment.template_id)
            );
        }

        // Populate dropdown with filtered assignments
        assignmentsToShow.forEach(assignment => {
            const option = document.createElement('option');
            option.value = assignment.id;
            option.textContent = assignment.name;
            option.dataset.templateId = assignment.template_id;
            option.dataset.periodName = assignment.period_name;
            assignmentFormSelect.appendChild(option);
        });

        // Restore Select2 if it was initialized
        if (window.jQuery && window.jQuery.fn.select2 && $(assignmentFormSelect).hasClass('select2-hidden-accessible')) {
            // Destroy and reinitialize Select2 to update options
            $(assignmentFormSelect).select2('destroy');
            const modal = document.getElementById('bulk-selection-modal');
            $(assignmentFormSelect).select2({
                placeholder: 'Search and select assignments...',
                allowClear: true,
                width: '100%',
                closeOnSelect: false,
                theme: 'default',
                dropdownParent: modal ? $(modal) : $('body')
            });

            // Restore selected values that are still available
            const availableIds = currentSelected.filter(id =>
                assignmentsToShow.some(a => a.id === id)
            );
            if (availableIds.length > 0) {
                $(assignmentFormSelect).val(availableIds).trigger('change');
            }

            // Reattach event listener
            $(assignmentFormSelect).on('select2:select select2:unselect', () => {
                this.updateAssignmentFormCount();
                this.previewPage = 1;
                this.loadPreviewUsers();
            });

            // Update count
            this.updateAssignmentFormCount();
        } else {
            // For native select, restore selected values
            currentSelected.forEach(id => {
                const option = assignmentFormSelect.querySelector(`option[value="${id}"]`);
                if (option) option.selected = true;
            });
            this.updateAssignmentFormCount();
        }
    }

    filterAssignmentsByTemplates() {
        this.loadAssignmentsDropdown();
    }

    checkAssignmentStatusForTemplateGroup() {
        const templateGroup = document.getElementById('bulk-select-template-group');
        const checkedStatuses = Array.from(document.querySelectorAll('.bulk-assignment-status-checkbox:checked'));

        if (templateGroup) {
            if (checkedStatuses.length > 0) {
                templateGroup.classList.remove('hidden');
            } else {
                templateGroup.classList.add('hidden');
                // Clear template selection when no status is selected
                const templateSelect = document.getElementById('bulk-select-template');
                if (templateSelect) {
                    if (window.jQuery && window.jQuery.fn.select2 && $(templateSelect).hasClass('select2-hidden-accessible')) {
                        $(templateSelect).val(null).trigger('change');
                    } else {
                        templateSelect.value = '';
                    }
                }
            }
        }
    }

    updateCountryCount() {
        const countrySelect = document.getElementById('bulk-select-country');
        const countEl = document.getElementById('bulk-country-count');
        if (countrySelect && countEl) {
            let selected = 0;
            // Check if Select2 is initialized
            if (window.jQuery && window.jQuery.fn.select2 && $(countrySelect).hasClass('select2-hidden-accessible')) {
                selected = $(countrySelect).val() ? $(countrySelect).val().length : 0;
            } else {
                selected = countrySelect.selectedOptions.length;
            }
            if (selected > 0) {
                countEl.textContent = `${selected} countr${selected === 1 ? 'y' : 'ies'} selected`;
                countEl.className = 'text-xs text-blue-600 font-medium mt-1';
            } else {
                countEl.textContent = 'No countries selected';
                countEl.className = 'text-xs text-gray-500 mt-1';
            }
        }
    }

    async loadPreviewUsers() {
        const loadingEl = document.getElementById('preview-loading');
        const previewList = document.getElementById('preview-users-list');

        if (loadingEl) loadingEl.classList.remove('hidden');
        if (previewList) previewList.replaceChildren();

        try {
            const params = this.buildFilterParams();
            params.append('page', this.previewPage);
            params.append('per_page', this.previewPerPage);

            const data = await _anFetch(`/notifications/api/admin/users/bulk?${params.toString()}`);
            if (data && data.success) {
                this.previewUsers = data.users || [];
                this.previewTotal = data.total || 0;
                this.previewTotalPages = data.total_pages || 1;
            } else {
                this.previewUsers = [];
                this.previewTotal = 0;
            }
            this.renderPreviewUsers();
            this.updatePreviewPagination();
        } catch (error) {
            console.error('Error loading preview users:', error);
            if (previewList) {
                previewList.replaceChildren();
                const p = document.createElement('p');
                p.className = 'text-sm text-red-600 text-center py-4';
                p.textContent = 'Error loading users. Please try again.';
                previewList.appendChild(p);
            }
        } finally {
            if (loadingEl) loadingEl.classList.add('hidden');
        }
    }

    buildFilterParams() {
        const params = new URLSearchParams();

        // Text search
        const search = document.getElementById('bulk-search-users')?.value.trim();
        if (search) {
            params.append('search', search);
        }

        // Roles (multi-select checkboxes)
        const selectedRoles = Array.from(document.querySelectorAll('.bulk-role-checkbox:checked')).map(cb => cb.value);
        if (selectedRoles.length > 0) {
            selectedRoles.forEach(role => params.append('role', role));
        }

        // Active status (checkboxes)
        const activeStatuses = Array.from(document.querySelectorAll('.bulk-account-status-checkbox:checked')).map(cb => cb.value);
        if (activeStatuses.length > 0) {
            // If both are selected, don't filter by active status
            // If only one is selected, filter by that value
            if (activeStatuses.length === 1) {
                params.append('active', activeStatuses[0]);
            }
        }

        // Countries (multi-select) - support both Select2 and native select
        const countrySelect = document.getElementById('bulk-select-country');
        if (countrySelect) {
            let selectedCountries = [];
            if (window.jQuery && window.jQuery.fn.select2 && $(countrySelect).hasClass('select2-hidden-accessible')) {
                // Select2 is initialized
                const selected = $(countrySelect).val();
                selectedCountries = selected ? (Array.isArray(selected) ? selected : [selected]) : [];
            } else {
                // Native select
                selectedCountries = Array.from(countrySelect.selectedOptions).map(opt => opt.value).filter(v => v);
            }
            if (selectedCountries.length > 0) {
                selectedCountries.forEach(cid => params.append('country_id', cid));
            }
        }

        // Entity type
        const entityType = document.getElementById('bulk-select-entity')?.value;
        if (entityType) {
            params.append('entity_type', entityType);
        }

        // Assignment status (checkboxes)
        const assignmentStatuses = Array.from(document.querySelectorAll('.bulk-assignment-status-checkbox:checked')).map(cb => cb.value);
        if (assignmentStatuses.length > 0) {
            assignmentStatuses.forEach(status => {
                params.append('assignment_status', status);
            });
            const templateSelect = document.getElementById('bulk-select-template');
            if (templateSelect) {
                let selectedTemplates = [];
                // Support both Select2 and native select
                if (window.jQuery && window.jQuery.fn.select2 && $(templateSelect).hasClass('select2-hidden-accessible')) {
                    const selected = $(templateSelect).val();
                    selectedTemplates = selected ? (Array.isArray(selected) ? selected : [selected]) : [];
                } else {
                    selectedTemplates = Array.from(templateSelect.selectedOptions).map(opt => opt.value).filter(v => v);
                }
                selectedTemplates.forEach(tid => params.append('template_id', tid));
            }
        }

        // Template filter (standalone, not requiring assignment status)
        const templateFilterSelect = document.getElementById('bulk-select-template-filter');
        if (templateFilterSelect) {
            let selectedTemplates = [];
            if (window.jQuery && window.jQuery.fn.select2 && $(templateFilterSelect).hasClass('select2-hidden-accessible')) {
                const selected = $(templateFilterSelect).val();
                selectedTemplates = selected ? (Array.isArray(selected) ? selected : [selected]) : [];
            } else {
                selectedTemplates = Array.from(templateFilterSelect.selectedOptions).map(opt => opt.value).filter(v => v);
            }
            if (selectedTemplates.length > 0 && assignmentStatuses.length === 0) {
                // Only add template filter if assignment status is not selected (to avoid conflicts)
                selectedTemplates.forEach(tid => params.append('template_id', tid));
            }
        }

        // Assignment form filter (standalone)
        const assignmentFormSelect = document.getElementById('bulk-select-assignment-form');
        if (assignmentFormSelect) {
            let selectedAssignments = [];
            if (window.jQuery && window.jQuery.fn.select2 && $(assignmentFormSelect).hasClass('select2-hidden-accessible')) {
                const selected = $(assignmentFormSelect).val();
                selectedAssignments = selected ? (Array.isArray(selected) ? selected : [selected]) : [];
            } else {
                selectedAssignments = Array.from(assignmentFormSelect.selectedOptions).map(opt => opt.value).filter(v => v);
            }
            if (selectedAssignments.length > 0) {
                selectedAssignments.forEach(afid => params.append('assigned_form_id', afid));
            }
        }

        // Exclude already selected
        const excludeSelected = document.getElementById('bulk-exclude-selected')?.checked;
        if (excludeSelected) {
            Array.from(this.selectedUsers.keys()).forEach(uid => {
                params.append('exclude_user_id', uid);
            });
        }

        return params;
    }

    renderPreviewUsers() {
        const previewList = document.getElementById('preview-users-list');
        const previewCount = document.getElementById('preview-count');
        const excludeSelected = document.getElementById('bulk-exclude-selected')?.checked;

        if (!previewList) return;

        // Update count
        if (previewCount) {
            previewCount.textContent = this.previewTotal;
        }

        if (this.previewUsers.length === 0) {
            previewList.replaceChildren();
            const p = document.createElement('p');
            p.className = 'text-sm text-gray-500 text-center py-8';
            p.textContent = 'No users match the current filters.';
            previewList.appendChild(p);
            document.getElementById('bulk-select-all-preview')?.classList.add('hidden');
            document.getElementById('bulk-deselect-all-preview')?.classList.add('hidden');
            document.getElementById('add-selected-users')?.classList.add('hidden');
            document.getElementById('bulk-selected-count')?.classList.add('hidden');
            return;
        }

        // Show select buttons
        document.getElementById('bulk-select-all-preview')?.classList.remove('hidden');
        document.getElementById('bulk-deselect-all-preview')?.classList.remove('hidden');
        const selectedCount = this.selectedPreviewUsers.size;
        if (selectedCount > 0) {
            document.getElementById('add-selected-users')?.classList.remove('hidden');
            document.getElementById('bulk-selected-count')?.classList.remove('hidden');
            const countNumber = document.getElementById('bulk-selected-number');
            if (countNumber) countNumber.textContent = selectedCount;
        } else {
            document.getElementById('add-selected-users')?.classList.add('hidden');
            document.getElementById('bulk-selected-count')?.classList.add('hidden');
        }

        // Render user table
        previewList.replaceChildren();
        const previewFrag = document.createRange().createContextualFragment(`
            <div class="overflow-x-auto">
                <table class="min-w-full divide-y divide-gray-200">
                    <thead class="bg-gray-50">
                        <tr>
                            <th scope="col" class="w-12 px-3 py-2 text-left">
                                <input type="checkbox"
                                       id="select-all-users-checkbox"
                                       class="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded">
                            </th>
                            <th scope="col" class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
                            <th scope="col" class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Email</th>
                            <th scope="col" class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Title</th>
                            <th scope="col" class="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Role</th>
                        </tr>
                    </thead>
                    <tbody class="bg-white divide-y divide-gray-200">
                        ${this.previewUsers.map(user => {
                            const isAlreadySelected = this.selectedUsers.has(user.id);
                            const isPreviewSelected = this.selectedPreviewUsers.has(user.id);
                            const canSelect = !excludeSelected || !isAlreadySelected;
                            const rowClass = isPreviewSelected ? 'bg-blue-50' : (isAlreadySelected ? 'bg-gray-50 opacity-75' : 'hover:bg-gray-50');

                            return `
                                <tr class="${rowClass} transition-colors">
                                    <td class="px-3 py-2 whitespace-nowrap">
                                        <input type="checkbox"
                                               class="preview-user-checkbox h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded cursor-pointer ${!canSelect ? 'cursor-not-allowed opacity-50' : ''}"
                                               data-user-id="${user.id}"
                                               ${isPreviewSelected ? 'checked' : ''}
                                               ${!canSelect ? 'disabled' : ''}>
                                    </td>
                                    <td class="px-3 py-2 whitespace-nowrap">
                                        <div class="text-sm font-medium text-gray-900">
                                            ${this.escapeHtml(user.name || '—')}
                                            ${isAlreadySelected ? '<span class="ml-2 text-xs text-amber-600"><i class="fas fa-check-circle"></i></span>' : ''}
                                        </div>
                                    </td>
                                    <td class="px-3 py-2 whitespace-nowrap">
                                        <div class="text-sm text-gray-600">${this.escapeHtml(user.email)}</div>
                                    </td>
                                    <td class="px-3 py-2 whitespace-nowrap">
                                        <div class="text-sm text-gray-500">${user.title ? this.escapeHtml(user.title) : '—'}</div>
                                    </td>
                                    <td class="px-3 py-2 whitespace-nowrap">
                                        <span class="inline-flex px-2 py-0.5 text-xs font-medium rounded-full bg-blue-100 text-blue-800 capitalize">
                                            ${this.escapeHtml(this.formatRbacRoleCodes(user.rbac_role_codes || []))}
                                        </span>
                                    </td>
                                </tr>
                            `;
                        }).join('')}
                    </tbody>
                </table>
            </div>
        `);
        previewList.appendChild(previewFrag);

        // Add select all checkbox handler
        const selectAllCheckbox = document.getElementById('select-all-users-checkbox');
        if (selectAllCheckbox) {
            const allSelected = this.previewUsers.length > 0 &&
                               this.previewUsers.every(u => this.selectedPreviewUsers.has(u.id) || (excludeSelected && this.selectedUsers.has(u.id)));
            selectAllCheckbox.checked = allSelected;

            selectAllCheckbox.addEventListener('change', (e) => {
                if (e.target.checked) {
                    // Select all selectable users
                    this.previewUsers.forEach(user => {
                        if (!excludeSelected || !this.selectedUsers.has(user.id)) {
                            this.selectedPreviewUsers.add(user.id);
                        }
                    });
                } else {
                    // Deselect all
                    this.previewUsers.forEach(user => {
                        this.selectedPreviewUsers.delete(user.id);
                    });
                }
                this.renderPreviewUsers();
            });
        }

        // Attach checkbox handlers
        previewList.querySelectorAll('.preview-user-checkbox').forEach(checkbox => {
            checkbox.addEventListener('change', (e) => {
                const userId = parseInt(e.target.dataset.userId);
                if (e.target.checked) {
                    this.selectedPreviewUsers.add(userId);
                } else {
                    this.selectedPreviewUsers.delete(userId);
                }
                this.renderPreviewUsers();
            });
        });
    }

    updatePreviewPagination() {
        const paginationEl = document.getElementById('preview-pagination');
        const prevBtn = document.getElementById('preview-prev');
        const nextBtn = document.getElementById('preview-next');
        const pageInfo = document.getElementById('preview-page-info');
        const paginationInfo = document.getElementById('preview-pagination-info');

        if (this.previewTotalPages > 1) {
            if (paginationEl) paginationEl.classList.remove('hidden');
            if (prevBtn) prevBtn.disabled = this.previewPage <= 1;
            if (nextBtn) nextBtn.disabled = this.previewPage >= this.previewTotalPages;
            if (pageInfo) {
                pageInfo.textContent = `Page ${this.previewPage} of ${this.previewTotalPages}`;
            }
            if (paginationInfo) {
                const start = (this.previewPage - 1) * this.previewPerPage + 1;
                const end = Math.min(this.previewPage * this.previewPerPage, this.previewTotal);
                paginationInfo.textContent = `Showing ${start}-${end} of ${this.previewTotal} users`;
            }
        } else {
            if (paginationEl) paginationEl.classList.add('hidden');
            if (paginationInfo) {
                paginationInfo.textContent = this.previewTotal > 0 ? `Total: ${this.previewTotal} user(s)` : '';
            }
        }
    }

    async addSelectedPreviewUsers() {
        const selectedIds = Array.from(this.selectedPreviewUsers);
        if (selectedIds.length === 0) {
            return;
        }

        try {
            const params = this.buildFilterParams();
            params.append('page', this.previewPage);
            params.append('per_page', this.previewPerPage);

            const data = await _anFetch(`/notifications/api/admin/users/bulk?${params.toString()}`);
            if (data && data.success && data.users) {
                let added = 0;
                data.users.forEach(user => {
                    if (this.selectedPreviewUsers.has(user.id) && !this.selectedUsers.has(user.id)) {
                        this.selectedUsers.set(user.id, {
                            id: user.id,
                            name: user.name || user.email,
                            email: user.email,
                            rbac_role_codes: user.rbac_role_codes || []
                        });
                        added++;
                    }
                });
                this.updateSelectedUsersDisplay();
                this.selectedPreviewUsers.clear();
                this.loadPreviewUsers();
            }
        } catch (error) {
            console.error('Error adding selected users:', error);
        }
    }

    // Update addUsersByFilters to use new filter system
    async addUsersByFilters() {
        // Use preview loading logic but add all users
        const params = this.buildFilterParams();

        try {
            const data = await _anFetch(`/notifications/api/admin/users/bulk?${params.toString()}`);
            if (data && data.success && data.users) {
                    // For "Add All", we need to get all pages
                    let allUsers = [...(data.users || [])];
                    if (data.total_pages > 1) {
                        for (let page = 2; page <= data.total_pages; page++) {
                            const pageParams = this.buildFilterParams();
                            pageParams.append('page', page);
                            pageParams.append('per_page', this.previewPerPage);
                            try {
                                const pageData = await _anFetch(`/notifications/api/admin/users/bulk?${pageParams.toString()}`);
                                if (pageData?.success && pageData?.users) allUsers.push(...pageData.users);
                            } catch (_) { /* skip page */ }
                        }
                    }

                    let added = 0;
                    allUsers.forEach(user => {
                        if (!this.selectedUsers.has(user.id)) {
                            this.selectedUsers.set(user.id, {
                                id: user.id,
                                name: user.name || user.email,
                                email: user.email,
                                rbac_role_codes: user.rbac_role_codes || []
                            });
                            added++;
                        }
                    });

                    this.updateSelectedUsersDisplay();

                    if (added > 0) {
                        setTimeout(() => this.closeBulkSelectionModal(), 1500);
                    }
            }
        } catch (error) {
            console.error('Error loading users by filters:', error);
        }
    }

    // Entity-based campaign methods
    handleCampaignTypeChange(type) {
        this.campaignType = type;
        const userBased = document.getElementById('user-based-recipients');
        const entityBased = document.getElementById('entity-based-recipients');

        const attachmentAutogenerated = document.getElementById('attachment-autogenerated-section');
        if (type === 'entity') {
            userBased?.classList.add('hidden');
            entityBased?.classList.remove('hidden');
            attachmentAutogenerated?.classList.remove('hidden');
            // Entity campaigns require email
            const sendEmailCheckbox = document.getElementById('send-email');
            if (sendEmailCheckbox) {
                sendEmailCheckbox.checked = true;
                sendEmailCheckbox.disabled = true;
            }
            // Load hierarchical entities
            this.loadHierarchicalEntities();
            // Load assignments for attachment dropdown if not yet loaded
            this.loadAssignmentsForAttachments();
            // Initialize entity display
            this.updateSelectedEntitiesDisplay();
            // Initialize drag and drop if not already initialized
            if (!this.distributionRules) {
                this.initDragAndDrop();
            }
        } else {
            userBased?.classList.remove('hidden');
            entityBased?.classList.add('hidden');
            attachmentAutogenerated?.classList.add('hidden');
            const sendEmailCheckbox = document.getElementById('send-email');
            if (sendEmailCheckbox) {
                sendEmailCheckbox.disabled = false;
            }
            // Clear selected entities when switching away
            this.selectedEntities.clear();
        }
        this.updateDistributionPreview();
    }

    async loadAssignmentsForAttachments() {
        const select = document.getElementById('attachment-assignment-select');
        if (!select) return;
        if (select.options.length > 1) return; // Already populated (first option is placeholder)
        try {
            const data = await _anFetch('/notifications/api/admin/assignments');
            if (data.success && data.assignments && data.assignments.length) {
                data.assignments.forEach(a => {
                    const opt = document.createElement('option');
                    opt.value = a.id;
                    opt.textContent = a.label;
                    select.appendChild(opt);
                });
            }
        } catch (e) {
            console.error('Error loading assignments for attachments:', e);
        }
    }

    async loadHierarchicalEntities() {
        const loadingIndicator = document.getElementById('entity-selection-loading');
        const listContainer = document.getElementById('entity-selection-list');

        // Get selected entity types
        const selectedTypes = Array.from(document.querySelectorAll('.entity-type-checkbox:checked')).map(cb => cb.value);

        if (selectedTypes.length === 0) {
            loadingIndicator.classList.add('hidden');
            listContainer.classList.remove('hidden');
            listContainer.replaceChildren();
            {
                const p = document.createElement('p');
                p.className = 'text-sm text-gray-500 text-center py-8';
                p.textContent = 'Select at least one entity type above';
                listContainer.appendChild(p);
            }
            return;
        }

        loadingIndicator.classList.remove('hidden');
        listContainer.classList.add('hidden');

        try {
            const typesParam = selectedTypes.map(t => `types=${encodeURIComponent(t)}`).join('&');
            const data = await _anFetch(`/admin/entities/hierarchical?${typesParam}`);

            loadingIndicator.classList.add('hidden');
            listContainer.classList.remove('hidden');

            // Render hierarchical list
            listContainer.replaceChildren();
            {
                const html = this.renderHierarchicalEntityList(data);
                const frag = document.createRange().createContextualFragment(html);
                listContainer.appendChild(frag);
            }

            // Attach event handlers
            this.attachEntityCheckboxHandlers();

        } catch (error) {
            console.error('Error loading hierarchical entities:', error);
            loadingIndicator.classList.add('hidden');
            listContainer.classList.remove('hidden');
            listContainer.replaceChildren();
            {
                const p = document.createElement('p');
                p.className = 'text-sm text-red-600 text-center py-8';
                p.textContent = 'Error loading entities. Please try again.';
                listContainer.appendChild(p);
            }
        }
    }

    renderHierarchicalEntityList(data) {
        let html = '';

        const esc = (v) => this.escapeHtml(v);
        const safeId = (v) =>
            String(v || '')
                .toLowerCase()
                .trim()
                .replace(/\s+/g, '-')
                .replace(/[^a-z0-9_-]/g, '');

        // Countries grouped by region
        if (data.countries) {
            html += '<div class="mb-6">';
            html += '<h4 class="text-sm font-semibold text-gray-900 mb-3 uppercase tracking-wide">Countries</h4>';
            for (const [region, countries] of Object.entries(data.countries)) {
                const regionId = `region-country-${safeId(region)}`;
                html += `<div class="mb-2 ml-4 border-l-2 border-gray-200 pl-3">`;
                html += `<div class="flex items-center mb-1">`;
                html += `<button type="button" class="group-toggle-btn mr-2 text-gray-500 hover:text-gray-700 focus:outline-none" data-target="${regionId}-content">`;
                html += `<i class="fas fa-chevron-down text-xs transition-transform duration-200"></i>`;
                html += `</button>`;
                html += `<input type="checkbox" class="form-checkbox h-4 w-4 text-blue-600 region-checkbox" data-region="country:${esc(region)}" id="${regionId}">`;
                html += `<label for="${regionId}" class="ml-2 text-sm font-medium text-gray-700 cursor-pointer flex-1">${esc(region)} <span class="text-gray-500 font-normal">(${countries.length})</span></label>`;
                html += `</div>`;
                html += `<div id="${regionId}-content" class="ml-6 space-y-1 mt-1">`;
                countries.forEach(country => {
                    const entityKey = `${country.entity_type}:${country.id}`;
                    const isSelected = this.selectedEntities.has(entityKey);
                    html += `
                        <label class="flex items-center space-x-2 cursor-pointer hover:bg-gray-50 p-1 rounded">
                            <input type="checkbox"
                                   class="form-checkbox h-4 w-4 text-blue-600 entity-checkbox"
                                   data-entity-key="${entityKey}"
                                   data-entity-type="${country.entity_type}"
                                   data-entity-id="${country.id}"
                                   data-entity-name="${esc(country.name)}"
                                   data-group="country:${esc(region)}"
                                   ${isSelected ? 'checked' : ''}>
                            <span class="text-sm text-gray-700">${esc(country.name)}</span>
                        </label>
                    `;
                });
                html += `</div></div>`;
            }
            html += '</div>';
        }

        // National Societies grouped by country
        if (data.national_societies) {
            html += '<div class="mb-6">';
            html += '<h4 class="text-sm font-semibold text-gray-900 mb-3 uppercase tracking-wide">National Societies</h4>';
            for (const [country, nationalSocieties] of Object.entries(data.national_societies)) {
                const groupId = `region-national_society-${safeId(country)}`;
                html += `<div class="mb-2 ml-4 border-l-2 border-gray-200 pl-3">`;
                html += `<div class="flex items-center mb-1">`;
                html += `<button type="button" class="group-toggle-btn mr-2 text-gray-500 hover:text-gray-700 focus:outline-none" data-target="${groupId}-content">`;
                html += `<i class="fas fa-chevron-down text-xs transition-transform duration-200"></i>`;
                html += `</button>`;
                html += `<input type="checkbox" class="form-checkbox h-4 w-4 text-blue-600 region-checkbox" data-region="national_society:${esc(country)}" id="${groupId}">`;
                html += `<label for="${groupId}" class="ml-2 text-sm font-medium text-gray-700 cursor-pointer flex-1">${esc(country)} <span class="text-gray-500 font-normal">(${nationalSocieties.length})</span></label>`;
                html += `</div>`;
                html += `<div id="${groupId}-content" class="ml-6 space-y-1 mt-1">`;
                nationalSocieties.forEach(ns => {
                    const entityKey = `${ns.entity_type}:${ns.id}`;
                    const isSelected = this.selectedEntities.has(entityKey);
                    html += `
                        <label class="flex items-center space-x-2 cursor-pointer hover:bg-gray-50 p-1 rounded">
                            <input type="checkbox"
                                   class="form-checkbox h-4 w-4 text-blue-600 entity-checkbox"
                                   data-entity-key="${entityKey}"
                                   data-entity-type="${ns.entity_type}"
                                   data-entity-id="${ns.id}"
                                   data-entity-name="${esc(ns.name)}"
                                   data-group="national_society:${esc(country)}"
                                   ${isSelected ? 'checked' : ''}>
                            <span class="text-sm text-gray-700">${esc(ns.name)}</span>
                        </label>
                    `;
                });
                html += `</div></div>`;
            }
            html += '</div>';
        }

        // NS Branches grouped by country
        if (data.ns_branches) {
            html += '<div class="mb-6">';
            html += '<h4 class="text-sm font-semibold text-gray-900 mb-3 uppercase tracking-wide">NS Branches</h4>';
            for (const [country, branches] of Object.entries(data.ns_branches)) {
                const groupId = `region-ns_branch-${safeId(country)}`;
                html += `<div class="mb-2 ml-4 border-l-2 border-gray-200 pl-3">`;
                html += `<div class="flex items-center mb-1">`;
                html += `<button type="button" class="group-toggle-btn mr-2 text-gray-500 hover:text-gray-700 focus:outline-none" data-target="${groupId}-content">`;
                html += `<i class="fas fa-chevron-down text-xs transition-transform duration-200"></i>`;
                html += `</button>`;
                html += `<input type="checkbox" class="form-checkbox h-4 w-4 text-blue-600 region-checkbox" data-region="ns_branch:${esc(country)}" id="${groupId}">`;
                html += `<label for="${groupId}" class="ml-2 text-sm font-medium text-gray-700 cursor-pointer flex-1">${esc(country)} <span class="text-gray-500 font-normal">(${branches.length})</span></label>`;
                html += `</div>`;
                html += `<div id="${groupId}-content" class="ml-6 space-y-1 mt-1">`;
                branches.forEach(branch => {
                    const entityKey = `${branch.entity_type}:${branch.id}`;
                    const isSelected = this.selectedEntities.has(entityKey);
                    html += `
                        <label class="flex items-center space-x-2 cursor-pointer hover:bg-gray-50 p-1 rounded">
                            <input type="checkbox"
                                   class="form-checkbox h-4 w-4 text-blue-600 entity-checkbox"
                                   data-entity-key="${entityKey}"
                                   data-entity-type="${branch.entity_type}"
                                   data-entity-id="${branch.id}"
                                   data-entity-name="${esc(branch.name)}"
                                   data-group="ns_branch:${esc(country)}"
                                   ${isSelected ? 'checked' : ''}>
                            <span class="text-sm text-gray-700">${esc(branch.name)}</span>
                        </label>
                    `;
                });
                html += `</div></div>`;
            }
            html += '</div>';
        }

        // NS Sub-branches grouped by country
        if (data.ns_subbranches) {
            html += '<div class="mb-6">';
            html += '<h4 class="text-sm font-semibold text-gray-900 mb-3 uppercase tracking-wide">NS Sub-branches</h4>';
            for (const [country, subbranches] of Object.entries(data.ns_subbranches)) {
                const groupId = `region-ns_subbranch-${safeId(country)}`;
                html += `<div class="mb-2 ml-4 border-l-2 border-gray-200 pl-3">`;
                html += `<div class="flex items-center mb-1">`;
                html += `<button type="button" class="group-toggle-btn mr-2 text-gray-500 hover:text-gray-700 focus:outline-none" data-target="${groupId}-content">`;
                html += `<i class="fas fa-chevron-down text-xs transition-transform duration-200"></i>`;
                html += `</button>`;
                html += `<input type="checkbox" class="form-checkbox h-4 w-4 text-blue-600 region-checkbox" data-region="ns_subbranch:${esc(country)}" id="${groupId}">`;
                html += `<label for="${groupId}" class="ml-2 text-sm font-medium text-gray-700 cursor-pointer flex-1">${esc(country)} <span class="text-gray-500 font-normal">(${subbranches.length})</span></label>`;
                html += `</div>`;
                html += `<div id="${groupId}-content" class="ml-6 space-y-1 mt-1">`;
                subbranches.forEach(subbranch => {
                    const entityKey = `${subbranch.entity_type}:${subbranch.id}`;
                    const isSelected = this.selectedEntities.has(entityKey);
                    html += `
                        <label class="flex items-center space-x-2 cursor-pointer hover:bg-gray-50 p-1 rounded">
                            <input type="checkbox"
                                   class="form-checkbox h-4 w-4 text-blue-600 entity-checkbox"
                                   data-entity-key="${entityKey}"
                                   data-entity-type="${subbranch.entity_type}"
                                   data-entity-id="${subbranch.id}"
                                   data-entity-name="${esc(subbranch.name)}"
                                   data-group="ns_subbranch:${esc(country)}"
                                   ${isSelected ? 'checked' : ''}>
                            <span class="text-sm text-gray-700">${esc(subbranch.name)}</span>
                        </label>
                    `;
                });
                html += `</div></div>`;
            }
            html += '</div>';
        }

        // NS Local Units grouped by country
        if (data.ns_localunits) {
            html += '<div class="mb-6">';
            html += '<h4 class="text-sm font-semibold text-gray-900 mb-3 uppercase tracking-wide">NS Local Units</h4>';
            for (const [country, localUnits] of Object.entries(data.ns_localunits)) {
                const groupId = `region-ns_localunit-${safeId(country)}`;
                html += `<div class="mb-2 ml-4 border-l-2 border-gray-200 pl-3">`;
                html += `<div class="flex items-center mb-1">`;
                html += `<button type="button" class="group-toggle-btn mr-2 text-gray-500 hover:text-gray-700 focus:outline-none" data-target="${groupId}-content">`;
                html += `<i class="fas fa-chevron-down text-xs transition-transform duration-200"></i>`;
                html += `</button>`;
                html += `<input type="checkbox" class="form-checkbox h-4 w-4 text-blue-600 region-checkbox" data-region="ns_localunit:${esc(country)}" id="${groupId}">`;
                html += `<label for="${groupId}" class="ml-2 text-sm font-medium text-gray-700 cursor-pointer flex-1">${esc(country)} <span class="text-gray-500 font-normal">(${localUnits.length})</span></label>`;
                html += `</div>`;
                html += `<div id="${groupId}-content" class="ml-6 space-y-1 mt-1">`;
                localUnits.forEach(localUnit => {
                    const entityKey = `${localUnit.entity_type}:${localUnit.id}`;
                    const isSelected = this.selectedEntities.has(entityKey);
                    html += `
                        <label class="flex items-center space-x-2 cursor-pointer hover:bg-gray-50 p-1 rounded">
                            <input type="checkbox"
                                   class="form-checkbox h-4 w-4 text-blue-600 entity-checkbox"
                                   data-entity-key="${entityKey}"
                                   data-entity-type="${localUnit.entity_type}"
                                   data-entity-id="${localUnit.id}"
                                   data-entity-name="${esc(localUnit.name)}"
                                   data-group="ns_localunit:${esc(country)}"
                                   ${isSelected ? 'checked' : ''}>
                            <span class="text-sm text-gray-700">${esc(localUnit.name)}</span>
                        </label>
                    `;
                });
                html += `</div></div>`;
            }
            html += '</div>';
        }

        // Divisions (flat list)
        if (data.divisions && data.divisions.length > 0) {
            html += '<div class="mb-6">';
            html += '<h4 class="text-sm font-semibold text-gray-900 mb-3 uppercase tracking-wide">Divisions</h4>';
            html += '<div class="ml-4 space-y-1">';
            data.divisions.forEach(division => {
                const entityKey = `${division.entity_type}:${division.id}`;
                const isSelected = this.selectedEntities.has(entityKey);
                html += `
                    <label class="flex items-center space-x-2 cursor-pointer hover:bg-gray-50 p-1 rounded">
                        <input type="checkbox"
                               class="form-checkbox h-4 w-4 text-blue-600 entity-checkbox"
                               data-entity-key="${entityKey}"
                               data-entity-type="${division.entity_type}"
                               data-entity-id="${division.id}"
                               data-entity-name="${esc(division.name)}"
                               ${isSelected ? 'checked' : ''}>
                        <span class="text-sm text-gray-700">${esc(division.name)}</span>
                    </label>
                `;
            });
            html += '</div></div>';
        }

        // Departments grouped by division
        if (data.departments) {
            html += '<div class="mb-6">';
            html += '<h4 class="text-sm font-semibold text-gray-900 mb-3 uppercase tracking-wide">Departments</h4>';
            for (const [division, departments] of Object.entries(data.departments)) {
                const groupId = `region-department-${safeId(division)}`;
                html += `<div class="mb-2 ml-4 border-l-2 border-gray-200 pl-3">`;
                html += `<div class="flex items-center mb-1">`;
                html += `<button type="button" class="group-toggle-btn mr-2 text-gray-500 hover:text-gray-700 focus:outline-none" data-target="${groupId}-content">`;
                html += `<i class="fas fa-chevron-down text-xs transition-transform duration-200"></i>`;
                html += `</button>`;
                html += `<input type="checkbox" class="form-checkbox h-4 w-4 text-blue-600 region-checkbox" data-region="department:${esc(division)}" id="${groupId}">`;
                html += `<label for="${groupId}" class="ml-2 text-sm font-medium text-gray-700 cursor-pointer flex-1">${esc(division)} <span class="text-gray-500 font-normal">(${departments.length})</span></label>`;
                html += `</div>`;
                html += `<div id="${groupId}-content" class="ml-6 space-y-1 mt-1">`;
                departments.forEach(dept => {
                    const entityKey = `${dept.entity_type}:${dept.id}`;
                    const isSelected = this.selectedEntities.has(entityKey);
                    html += `
                        <label class="flex items-center space-x-2 cursor-pointer hover:bg-gray-50 p-1 rounded">
                            <input type="checkbox"
                                   class="form-checkbox h-4 w-4 text-blue-600 entity-checkbox"
                                   data-entity-key="${entityKey}"
                                   data-entity-type="${dept.entity_type}"
                                   data-entity-id="${dept.id}"
                                   data-entity-name="${esc(dept.name)}"
                                   data-group="department:${esc(division)}"
                                   ${isSelected ? 'checked' : ''}>
                            <span class="text-sm text-gray-700">${esc(dept.name)}</span>
                        </label>
                    `;
                });
                html += `</div></div>`;
            }
            html += '</div>';
        }

        // Regional Offices (flat list)
        if (data.regional_offices && data.regional_offices.length > 0) {
            html += '<div class="mb-6">';
            html += '<h4 class="text-sm font-semibold text-gray-900 mb-3 uppercase tracking-wide">Regional Offices</h4>';
            html += '<div class="ml-4 space-y-1">';
            data.regional_offices.forEach(ro => {
                const entityKey = `${ro.entity_type}:${ro.id}`;
                const isSelected = this.selectedEntities.has(entityKey);
                html += `
                    <label class="flex items-center space-x-2 cursor-pointer hover:bg-gray-50 p-1 rounded">
                        <input type="checkbox"
                               class="form-checkbox h-4 w-4 text-blue-600 entity-checkbox"
                               data-entity-key="${entityKey}"
                               data-entity-type="${ro.entity_type}"
                               data-entity-id="${ro.id}"
                               data-entity-name="${esc(ro.name)}"
                               ${isSelected ? 'checked' : ''}>
                        <span class="text-sm text-gray-700">${esc(ro.name)}</span>
                    </label>
                `;
            });
            html += '</div></div>';
        }

        // Cluster Offices grouped by regional office
        if (data.cluster_offices) {
            html += '<div class="mb-6">';
            html += '<h4 class="text-sm font-semibold text-gray-900 mb-3 uppercase tracking-wide">Cluster Offices</h4>';
            for (const [region, clusterOffices] of Object.entries(data.cluster_offices)) {
                const groupId = `region-cluster_office-${safeId(region)}`;
                html += `<div class="mb-2 ml-4 border-l-2 border-gray-200 pl-3">`;
                html += `<div class="flex items-center mb-1">`;
                html += `<button type="button" class="group-toggle-btn mr-2 text-gray-500 hover:text-gray-700 focus:outline-none" data-target="${groupId}-content">`;
                html += `<i class="fas fa-chevron-down text-xs transition-transform duration-200"></i>`;
                html += `</button>`;
                html += `<input type="checkbox" class="form-checkbox h-4 w-4 text-blue-600 region-checkbox" data-region="cluster_office:${esc(region)}" id="${groupId}">`;
                html += `<label for="${groupId}" class="ml-2 text-sm font-medium text-gray-700 cursor-pointer flex-1">${esc(region)} <span class="text-gray-500 font-normal">(${clusterOffices.length})</span></label>`;
                html += `</div>`;
                html += `<div id="${groupId}-content" class="ml-6 space-y-1 mt-1">`;
                clusterOffices.forEach(co => {
                    const entityKey = `${co.entity_type}:${co.id}`;
                    const isSelected = this.selectedEntities.has(entityKey);
                    html += `
                        <label class="flex items-center space-x-2 cursor-pointer hover:bg-gray-50 p-1 rounded">
                            <input type="checkbox"
                                   class="form-checkbox h-4 w-4 text-blue-600 entity-checkbox"
                                   data-entity-key="${entityKey}"
                                   data-entity-type="${co.entity_type}"
                                   data-entity-id="${co.id}"
                                   data-entity-name="${esc(co.name)}"
                                   data-group="cluster_office:${esc(region)}"
                                   ${isSelected ? 'checked' : ''}>
                            <span class="text-sm text-gray-700">${esc(co.name)}</span>
                        </label>
                    `;
                });
                html += `</div></div>`;
            }
            html += '</div>';
        }

        if (!html) {
            html = '<p class="text-sm text-gray-500 text-center py-8">No entities found for selected types</p>';
        }

        return html;
    }

    attachEntityCheckboxHandlers() {
        // Collapse/expand toggle buttons
        document.querySelectorAll('.group-toggle-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const targetId = btn.dataset.target;
                const content = document.getElementById(targetId);
                const icon = btn.querySelector('i');

                if (content) {
                    if (content.classList.contains('hidden')) {
                        content.classList.remove('hidden');
                        if (icon) {
                            icon.classList.remove('fa-chevron-right');
                            icon.classList.add('fa-chevron-down');
                        }
                    } else {
                        content.classList.add('hidden');
                        if (icon) {
                            icon.classList.remove('fa-chevron-down');
                            icon.classList.add('fa-chevron-right');
                        }
                    }
                }
            });
        });

        // Individual entity checkboxes
        document.querySelectorAll('.entity-checkbox').forEach(checkbox => {
            checkbox.addEventListener('change', (e) => {
                const entityKey = checkbox.dataset.entityKey;
                const entityType = checkbox.dataset.entityType;
                const entityId = parseInt(checkbox.dataset.entityId);
                const entityName = checkbox.dataset.entityName;

                if (checkbox.checked) {
                    this.selectedEntities.set(entityKey, {
                        entity_type: entityType,
                        entity_id: entityId,
                        display_name: entityName
                    });
                } else {
                    this.selectedEntities.delete(entityKey);
                }

                this.updateEntityCount();
                this.updateSelectedEntitiesDisplay();
                this.updateRegionCheckboxState(checkbox.dataset.group);
            });
        });

        // Region/group checkboxes (select all in group)
        document.querySelectorAll('.region-checkbox').forEach(checkbox => {
            checkbox.addEventListener('change', (e) => {
                const region = checkbox.dataset.region;
                const checkboxes = document.querySelectorAll(`.entity-checkbox[data-group="${region}"]`);

                checkboxes.forEach(cb => {
                    cb.checked = checkbox.checked;
                    const entityKey = cb.dataset.entityKey;
                    const entityType = cb.dataset.entityType;
                    const entityId = parseInt(cb.dataset.entityId);
                    const entityName = cb.dataset.entityName;

                    if (checkbox.checked) {
                        this.selectedEntities.set(entityKey, {
                            entity_type: entityType,
                            entity_id: entityId,
                            display_name: entityName
                        });
                    } else {
                        this.selectedEntities.delete(entityKey);
                    }
                });

                this.updateEntityCount();
                this.updateSelectedEntitiesDisplay();
            });
        });
    }

    updateRegionCheckboxState(group) {
        if (!group) return;
        const checkboxes = document.querySelectorAll(`.entity-checkbox[data-group="${group}"]`);
        const regionCheckbox = document.querySelector(`.region-checkbox[data-region="${group}"]`);
        if (!regionCheckbox || checkboxes.length === 0) return;

        const allChecked = Array.from(checkboxes).every(cb => cb.checked);
        const someChecked = Array.from(checkboxes).some(cb => cb.checked);

        regionCheckbox.checked = allChecked;
        regionCheckbox.indeterminate = someChecked && !allChecked;
    }

    selectAllVisibleEntities() {
        document.querySelectorAll('.entity-checkbox:not(:checked)').forEach(checkbox => {
            checkbox.checked = true;
            checkbox.dispatchEvent(new Event('change'));
        });
    }

    deselectAllEntities() {
        document.querySelectorAll('.entity-checkbox:checked').forEach(checkbox => {
            checkbox.checked = false;
            checkbox.dispatchEvent(new Event('change'));
        });
    }

    updateEntityCount() {
        const countElement = document.getElementById('entity-count');
        if (countElement) {
            countElement.textContent = this.selectedEntities.size;
        }
    }

    updateSelectedEntitiesDisplay() {
        const container = document.getElementById('selected-entities');
        if (!container) return;

        if (this.selectedEntities.size === 0) {
            container.replaceChildren();
            return;
        }
        container.replaceChildren();

        Array.from(this.selectedEntities.values()).forEach((entity) => {
            const entityKey = `${entity.entity_type}:${entity.entity_id}`;

            const pill = document.createElement('div');
            pill.className = 'inline-flex items-center space-x-2 px-3 py-1.5 bg-blue-100 text-blue-800 rounded-full text-sm border border-blue-200';

            const icon = document.createElement('i');
            icon.className = `fas ${this.getEntityIcon(entity.entity_type)} text-xs`;

            const name = document.createElement('span');
            name.textContent = String(entity.display_name || '');

            const btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'ml-2 text-blue-600 hover:text-blue-800 remove-entity-btn';
            btn.dataset.entityKey = entityKey;

            const x = document.createElement('i');
            x.className = 'fas fa-times text-xs';
            btn.appendChild(x);

            pill.append(icon, name, btn);
            container.appendChild(pill);
        });

        // Attach remove handlers
        container.querySelectorAll('.remove-entity-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const entityKey = btn.dataset.entityKey;
                this.selectedEntities.delete(entityKey);
                // Uncheck checkbox if it exists
                const checkbox = document.querySelector(`.entity-checkbox[data-entity-key="${entityKey}"]`);
                if (checkbox) {
                    checkbox.checked = false;
                    this.updateRegionCheckboxState(checkbox.dataset.group);
                }
                this.updateEntityCount();
                this.updateSelectedEntitiesDisplay();
            });
        });
    }

    getEntityIcon(entityType) {
        const icons = {
            'country': 'fa-flag',
            'national_society': 'fa-hand-holding-heart',
            'ns_branch': 'fa-sitemap',
            'ns_subbranch': 'fa-code-branch',
            'ns_localunit': 'fa-map-marker-alt',
            'division': 'fa-building',
            'department': 'fa-briefcase',
            'regional_office': 'fa-globe-americas',
            'cluster_office': 'fa-map-pin'
        };
        return icons[entityType] || 'fa-folder';
    }

    formatEntityType(entityType) {
        const names = {
            'country': 'Country',
            'national_society': 'National Society',
            'ns_branch': 'NS Branch',
            'ns_subbranch': 'NS Sub-branch',
            'ns_localunit': 'NS Local Unit',
            'division': 'Secretariat Division',
            'department': 'Secretariat Department',
            'regional_office': 'Regional Office',
            'cluster_office': 'Cluster Office'
        };
        return names[entityType] || entityType;
    }

    initDragAndDrop() {
        // Distribution rules state: {to: ['ifrc', 'focal_point'], cc: ['admin']}
        // Initialize if not already set
        if (!this.distributionRules) {
            this.distributionRules = { to: [], cc: [] };
        }

        // Make user types draggable
        document.querySelectorAll('.draggable-user-type').forEach(item => {
            item.addEventListener('dragstart', (e) => {
                e.dataTransfer.effectAllowed = 'move';
                e.dataTransfer.setData('text/plain', item.dataset.userType);
                e.dataTransfer.setData('user-type-label', item.dataset.userTypeLabel);
                item.style.opacity = '0.5';
            });

            item.addEventListener('dragend', (e) => {
                item.style.opacity = '1';
            });
        });

        // Setup drop zones
        const toDropZone = document.getElementById('to-drop-zone');
        const ccDropZone = document.getElementById('cc-drop-zone');

        [toDropZone, ccDropZone].forEach(zone => {
            if (!zone) return;

            zone.addEventListener('dragover', (e) => {
                e.preventDefault();
                e.dataTransfer.dropEffect = 'move';
                zone.classList.add('drag-over');
            });

            zone.addEventListener('dragleave', (e) => {
                // Only remove drag-over if we're actually leaving the zone
                if (!zone.contains(e.relatedTarget)) {
                    zone.classList.remove('drag-over');
                }
            });

            zone.addEventListener('drop', (e) => {
                e.preventDefault();
                zone.classList.remove('drag-over');

                const userType = e.dataTransfer.getData('text/plain');
                const userTypeLabel = e.dataTransfer.getData('user-type-label');
                const field = zone.dataset.field; // 'to' or 'cc'

                this.addUserTypeToField(userType, userTypeLabel, field);
            });
        });

        // Initialize with default: non-IFRC in To, IFRC in CC
        this.addUserTypeToField('non_ifrc', 'Non-IFRC', 'to', false);
        this.addUserTypeToField('ifrc', 'IFRC', 'cc', false);
    }

    addUserTypeToField(userType, userTypeLabel, field, removeFromOther = true) {
        // Remove from other field if it exists there
        if (removeFromOther) {
            const otherField = field === 'to' ? 'cc' : 'to';
            this.distributionRules[otherField] = this.distributionRules[otherField].filter(t => t !== userType);
            this.updateFieldDisplay(otherField);
        }

        // Add to target field if not already there
        if (!this.distributionRules[field].includes(userType)) {
            this.distributionRules[field].push(userType);
        }

        this.updateFieldDisplay(field);
        this.updateDistributionPreview();
        this.updateUserTypesPool();
    }

    removeUserTypeFromField(userType, field) {
        this.distributionRules[field] = this.distributionRules[field].filter(t => t !== userType);
        this.updateFieldDisplay(field);
        this.updateDistributionPreview();
        this.updateUserTypesPool();
    }

    updateFieldDisplay(field) {
        const itemsContainer = document.getElementById(`${field}-items`);
        const emptyMessage = document.getElementById(`${field}-empty-message`);
        const dropZone = document.getElementById(`${field}-drop-zone`);

        if (!itemsContainer || !emptyMessage) return;

        const userTypes = this.distributionRules[field];

        if (userTypes.length === 0) {
            itemsContainer.replaceChildren();
            emptyMessage.classList.remove('hidden');
            dropZone.classList.add('border-dashed');
        } else {
            emptyMessage.classList.add('hidden');
            dropZone.classList.remove('border-dashed');

            const userTypeLabels = {
                'ifrc': { label: 'IFRC', icon: 'fa-building', bgClass: 'bg-blue-100', textClass: 'text-blue-800', borderClass: 'border-blue-300', btnClass: 'text-blue-600 hover:text-blue-800' },
                'non_ifrc': { label: 'Non-IFRC', icon: 'fa-globe', bgClass: 'bg-green-100', textClass: 'text-green-800', borderClass: 'border-green-300', btnClass: 'text-green-600 hover:text-green-800' },
                'focal_point': { label: 'Focal Points', icon: 'fa-user-tie', bgClass: 'bg-purple-100', textClass: 'text-purple-800', borderClass: 'border-purple-300', btnClass: 'text-purple-600 hover:text-purple-800' },
                'admin': { label: 'Admins', icon: 'fa-user-shield', bgClass: 'bg-red-100', textClass: 'text-red-800', borderClass: 'border-red-300', btnClass: 'text-red-600 hover:text-red-800' },
                'system_manager': { label: 'System Managers', icon: 'fa-user-cog', bgClass: 'bg-orange-100', textClass: 'text-orange-800', borderClass: 'border-orange-300', btnClass: 'text-orange-600 hover:text-orange-800' }
            };
            itemsContainer.replaceChildren();

            userTypes.forEach((userType) => {
                const config = userTypeLabels[userType] || {
                    label: userType,
                    icon: 'fa-user',
                    bgClass: 'bg-gray-100',
                    textClass: 'text-gray-800',
                    borderClass: 'border-gray-300',
                    btnClass: 'text-gray-600 hover:text-gray-800'
                };

                const item = document.createElement('div');
                item.className = `inline-flex items-center space-x-2 px-3 py-2 ${config.bgClass} ${config.textClass} rounded-lg border ${config.borderClass}`;

                const icon = document.createElement('i');
                icon.className = `fas ${config.icon} mr-1`;

                const label = document.createElement('span');
                label.className = 'text-sm font-medium';
                label.textContent = String(config.label || '');

                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = `ml-2 ${config.btnClass} remove-user-type-btn`;
                btn.dataset.userType = String(userType || '');
                btn.dataset.field = String(field || '');

                const x = document.createElement('i');
                x.className = 'fas fa-times text-xs';
                btn.appendChild(x);

                item.append(icon, label, btn);
                itemsContainer.appendChild(item);
            });

            // Attach remove handlers
            itemsContainer.querySelectorAll('.remove-user-type-btn').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    e.stopPropagation();
                    const userType = btn.dataset.userType;
                    const field = btn.dataset.field;
                    this.removeUserTypeFromField(userType, field);
                });
            });
        }
    }

    updateUserTypesPool() {
        const pool = document.getElementById('user-types-pool');
        if (!pool) return;

        // Get all user types currently in use
        const usedTypes = [...this.distributionRules.to, ...this.distributionRules.cc];

        // Show/hide user types in pool based on whether they're already assigned
        pool.querySelectorAll('.draggable-user-type').forEach(item => {
            const userType = item.dataset.userType;
            if (usedTypes.includes(userType)) {
                item.style.opacity = '0.5';
                item.style.pointerEvents = 'none';
            } else {
                item.style.opacity = '1';
                item.style.pointerEvents = 'auto';
            }
        });
    }

    updateDistributionPreview() {
        const preview = document.getElementById('distribution-preview');
        if (!preview) return;

        const toTypes = this.distributionRules.to || [];
        const ccTypes = this.distributionRules.cc || [];

        const userTypeLabels = {
            'ifrc': 'IFRC',
            'non_ifrc': 'Non-IFRC',
            'focal_point': 'Focal Points',
            'admin': 'Admins',
            'system_manager': 'System Managers'
        };

        const toLabels = toTypes.map(t => userTypeLabels[t] || t).join(', ');
        const ccLabels = ccTypes.map(t => userTypeLabels[t] || t).join(', ');

        let previewText = '';
        if (toLabels && ccLabels) {
            previewText = `To: ${toLabels} | CC: ${ccLabels}`;
        } else if (toLabels) {
            previewText = `To: ${toLabels}`;
        } else if (ccLabels) {
            previewText = `CC: ${ccLabels}`;
        } else {
            previewText = 'Drag user types to configure distribution';
        }

        preview.textContent = previewText;
    }

    async handleEntityCampaignSubmit(e, sendEmail, sendPush, title, message, priority, overridePreferences, category, tags, redirectUrl) {
        // Entity-based campaigns require email
        if (!sendEmail) {
            window.showAlert('Entity-based campaigns require email to be enabled.', 'warning');
            return;
        }

        const entitySelections = Array.from(this.selectedEntities.values());
        if (entitySelections.length === 0) {
            window.showAlert('Please select at least one entity.', 'warning');
            return;
        }

        if (!title || !message) {
            return;
        }

        // Get distribution rules from drag and drop state
        const distributionRules = {
            to: this.distributionRules.to || [],
            cc: this.distributionRules.cc || []
        };

        // Validate that at least one user type is assigned
        if (distributionRules.to.length === 0 && distributionRules.cc.length === 0) {
            window.showAlert('Please assign at least one user type to To or CC field.', 'warning');
            return;
        }

        // Disable submit button
        const submitButton = document.getElementById('send-admin-notification');
        const originalNodes = Array.from(submitButton.childNodes).map((n) => n.cloneNode(true));
        const restoreSubmitButton = () => {
            submitButton.replaceChildren(...originalNodes.map((n) => n.cloneNode(true)));
        };
        submitButton.disabled = true;
        submitButton.replaceChildren();
        {
            const icon = document.createElement('i');
            icon.className = 'fas fa-spinner fa-spin mr-2';
            submitButton.append(icon, document.createTextNode('Sending...'));
        }

        try {
            // Build attachment_config: static files (base64) and optional assignment PDF
            const attachmentConfig = {};
            const staticInput = document.getElementById('notification-static-attachments');
            if (staticInput && staticInput.files && staticInput.files.length > 0) {
                const staticAttachments = [];
                const readFile = (file) => new Promise((resolve) => {
                    const reader = new FileReader();
                    reader.onload = () => {
                        const dataUrl = reader.result;
                        const base64 = (typeof dataUrl === 'string' && dataUrl.indexOf(',') >= 0) ? dataUrl.split(',')[1] : '';
                        resolve({
                            filename: file.name,
                            content_base64: base64,
                            content_type: file.type || 'application/octet-stream'
                        });
                    };
                    reader.readAsDataURL(file);
                });
                for (let i = 0; i < staticInput.files.length; i++) {
                    staticAttachments.push(await readFile(staticInput.files[i]));
                }
                attachmentConfig.static_attachments = staticAttachments;
            }
            const assignmentSelect = document.getElementById('attachment-assignment-select');
            if (assignmentSelect && assignmentSelect.value) {
                const afId = parseInt(assignmentSelect.value, 10);
                if (!isNaN(afId)) attachmentConfig.assignment_pdf_assigned_form_id = afId;
            }
            const hasAttachments = attachmentConfig.static_attachments?.length || attachmentConfig.assignment_pdf_assigned_form_id;
            if (hasAttachments) attachmentConfig.static_attachments = attachmentConfig.static_attachments || [];

            // Create campaign with entity selection
            const data = await _anFetch('/notifications/api/admin/campaigns', {
                method: 'POST',
                body: JSON.stringify({
                    name: `Entity Campaign: ${title.substring(0, 50)}`,
                    description: `Entity-based email campaign`,
                    title: title,
                    message: message,
                    priority: priority,
                    category: category,
                    tags: tags,
                    send_email: sendEmail,
                    send_push: sendPush,
                    override_preferences: overridePreferences,
                    redirect_type: redirectUrl ? (redirectUrl.startsWith('/') ? 'app' : 'custom') : null,
                    redirect_url: redirectUrl,
                    user_selection_type: 'entity',
                    entity_selection: entitySelections.map(e => ({
                        entity_type: e.entity_type,
                        entity_id: e.entity_id
                    })),
                    email_distribution_rules: distributionRules,
                    attachment_config: hasAttachments ? attachmentConfig : undefined
                })
            });

            if (data.success && (data.campaign?.id || data.campaign_id)) {
                const campaignId = data.campaign?.id ?? data.campaign_id;
                // Send the campaign immediately
                const sendData = await _anFetch(`/notifications/api/admin/campaigns/${campaignId}/send`, {
                    method: 'POST'
                });

                if (sendData.success) {
                    this.resetForm();
                    // Show success message
                    if (sendData.flash_message) {
                        // Flash message will be shown by backend
                        window.location.reload();
                    }
                } else {
                    window.showAlert(sendData.error || 'Failed to send campaign', 'error');
                }
            } else {
                window.showAlert(data.error || 'Failed to create campaign', 'error');
            }
        } catch (error) {
            console.error('Error sending entity campaign:', error);
            window.showAlert('An error occurred while sending the campaign.', 'error');
        } finally {
            submitButton.disabled = false;
            restoreSubmitButton();
        }
    }
}

// Initialize when DOM is ready
let adminNotifications;
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => {
        adminNotifications = new AdminNotifications();
        window.adminNotifications = adminNotifications;
    });
} else {
    adminNotifications = new AdminNotifications();
    window.adminNotifications = adminNotifications;
}
