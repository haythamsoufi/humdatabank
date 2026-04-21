// Notification Center - Comprehensive notification management interface

async function _ncFetch(url, options = {}) {
    const fn = (window.getApiFetch && window.getApiFetch()) || window.apiFetch || fetch;
    if (options.body && !options.headers) options.headers = { 'Content-Type': 'application/json' };
    return fn(url, options);
}

class NotificationCenter {
    constructor() {
        this.currentPage = 1;
        this.perPage = 20;
        this.currentTab = 'all';
        this.filters = {
            unread_only: false,
            type: null,
            category: null,
            tags: null,
            date_from: null,
            date_to: null,
            search: null,
            include_archived: false
        };
        this.selectedNotifications = new Set();
        this.expandedGroups = new Set(); // Track expanded notification groups
        this.csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');
        this._actionsRegistered = false;

        // Admin push notification state
    }

    init() {
        this.attachEventListeners();
        this.loadNotifications();
        this.loadPreferences();
    }

    attachEventListeners() {
        // Tab switching
        document.querySelectorAll('.tab-button').forEach(button => {
            button.addEventListener('click', (e) => this.handleTabSwitch(e.target.dataset.tab));
        });

        // Filter controls
        document.getElementById('apply-filters')?.addEventListener('click', () => this.applyFilters());
        document.getElementById('clear-filters')?.addEventListener('click', () => this.clearFilters());

        // Preferences toggle
        document.getElementById('preferences-toggle')?.addEventListener('click', () => this.togglePreferences());
        document.getElementById('save-preferences')?.addEventListener('click', () => this.savePreferences());
        document.getElementById('cancel-preferences')?.addEventListener('click', () => this.togglePreferences());

        // Frequency change handler to show/hide digest schedule
        document.getElementById('pref-frequency')?.addEventListener('change', (e) => this.toggleDigestSchedule(e.target.value));

        // Update digest preview when day or time changes
        document.getElementById('pref-digest-day')?.addEventListener('change', () => this.updateDigestPreviewFromForm());
        document.getElementById('pref-digest-time')?.addEventListener('change', () => this.updateDigestPreviewFromForm());

        // Select All checkboxes
        document.getElementById('select-all-email')?.addEventListener('change', (e) => this.toggleSelectAll('email', e.target.checked));
        document.getElementById('select-all-push')?.addEventListener('change', (e) => this.toggleSelectAll('push', e.target.checked));

        // Update select all checkboxes when individual checkboxes change
        document.addEventListener('change', (e) => {
            if (e.target.classList.contains('notification-type-email')) {
                this.updateSelectAllState('email');
            } else if (e.target.classList.contains('notification-type-push')) {
                this.updateSelectAllState('push');
            }
        });

        // Bulk actions
        document.getElementById('bulk-mark-read')?.addEventListener('click', () => this.handleBulkAction('mark_read'));
        document.getElementById('bulk-mark-unread')?.addEventListener('click', () => this.handleBulkAction('mark_unread'));
        document.getElementById('bulk-archive')?.addEventListener('click', () => this.handleBulkAction('archive'));
        document.getElementById('bulk-delete')?.addEventListener('click', () => this.handleBulkAction('delete'));

        // Export
        document.getElementById('export-notifications')?.addEventListener('click', () => this.exportNotifications());

        // Search - use debounced search
        const searchInput = document.getElementById('search-filter');
        if (searchInput) {
            let searchTimeout;
            searchInput.addEventListener('input', (e) => {
                clearTimeout(searchTimeout);
                searchTimeout = setTimeout(() => {
                    this.filters.search = e.target.value.trim() || null;
                    this.currentPage = 1;
                    this.loadNotifications();
                }, 500); // Debounce 500ms
            });
        }

        // Delegated checkbox selection (replaces inline onchange)
        const listContainer = document.getElementById('notifications-center-list');
        if (listContainer) {
            listContainer.addEventListener('change', (e) => {
                const target = e.target;
                if (!(target instanceof HTMLElement)) return;
                if (!target.classList.contains('notification-checkbox')) return;
                const id = parseInt(target.getAttribute('data-notification-id') || '', 10);
                if (!Number.isFinite(id)) return;
                this.toggleSelection(id);
            });
        }

        // Centralized delegated actions via ActionRouter (replaces inline onclick)
        if (window.ActionRouter && !this._actionsRegistered) {
            this._actionsRegistered = true;

            window.ActionRouter.register('notifications-center:retry', (_el, event) => {
                event?.preventDefault?.();
                this.loadNotifications();
            });
            window.ActionRouter.register('notifications-center:clear-filters', (_el, event) => {
                event?.preventDefault?.();
                this.clearFilters();
            });
            window.ActionRouter.register('notifications-center:toggle-group', (el, event) => {
                event?.preventDefault?.();
                const groupId = el.getAttribute('data-group-id');
                if (!groupId) return;
                this.toggleGroup(groupId);
            });

            const singleIdHandler = (fn) => (el, event) => {
                event?.preventDefault?.();
                const id = parseInt(el.getAttribute('data-notification-id') || '', 10);
                if (!Number.isFinite(id)) return;
                fn.call(this, [id]);
            };

            window.ActionRouter.register('notifications-center:mark-read', singleIdHandler(this.markAsRead));
            window.ActionRouter.register('notifications-center:mark-unread', singleIdHandler(this.markAsUnread));
            window.ActionRouter.register('notifications-center:archive', singleIdHandler(this.archiveNotifications));
            window.ActionRouter.register('notifications-center:delete', singleIdHandler(this.deleteNotifications));

            window.ActionRouter.register('notifications-center:view-related', (el, event) => {
                event?.preventDefault?.();
                const relatedUrl = el.getAttribute('data-related-url') || '';
                if (window.SafeDom) {
                    window.SafeDom.navigate(relatedUrl, { allowSameOrigin: true });
                } else {
                    // Fallback: same-origin only
                    try {
                        const u = new URL(relatedUrl, window.location.origin);
                        if (u.origin === window.location.origin) window.location.href = relatedUrl;
                    } catch (_) {}
                }
            });

            window.ActionRouter.register('notifications-center:custom-action', (el, event) => {
                event?.preventDefault?.();
                const id = parseInt(el.getAttribute('data-notification-id') || '', 10);
                const action = el.getAttribute('data-action-key') || '';
                if (!Number.isFinite(id) || !action) return;
                this.handleAction(id, action);
            });

            window.ActionRouter.register('notifications-center:go-to-page', (el, event) => {
                event?.preventDefault?.();
                const page = parseInt(el.getAttribute('data-page') || '', 10);
                if (!Number.isFinite(page) || page < 1) return;
                this.goToPage(page);
            });
        }

    }

    handleTabSwitch(tab) {
        this.currentTab = tab;
        this.currentPage = 1;

        // Update tab UI
        document.querySelectorAll('.tab-button').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.tab === tab);
        });

        // Update filters based on tab
        this.filters.unread_only = (tab === 'unread');
        this.filters.include_archived = (tab === 'archived');

        this.loadNotifications();
    }

    async loadNotifications() {
        const container = document.getElementById('notifications-center-list');
        if (!container) {
            console.error('Notifications center list container not found');
            return;
        }

        container.replaceChildren();
        const loadingDiv = document.createElement('div');
        loadingDiv.className = 'loading-state';
        const spinner = document.createElement('i');
        spinner.className = 'fas fa-spinner loading-spinner';
        const loadingP = document.createElement('p');
        loadingP.className = 'mt-3 text-gray-600';
        loadingP.textContent = 'Loading notifications...';
        loadingDiv.appendChild(spinner);
        loadingDiv.appendChild(loadingP);
        container.appendChild(loadingDiv);

        try {
            // Use search API if search query is provided
            if (this.filters.search) {
                const params = new URLSearchParams();
                if (this.filters.search) params.append('q', this.filters.search);
                if (this.filters.type) params.append('type', this.filters.type);
                if (this.filters.date_from) params.append('date_from', this.filters.date_from);
                if (this.filters.date_to) params.append('date_to', this.filters.date_to);

                const data = await _ncFetch(`/notifications/api/search?${params}`);

                if (data.success) {
                    // Format search results to match regular notification format
                    this.renderNotifications({
                        notifications: data.notifications,
                        total_count: data.total,
                        page: 1,
                        per_page: data.total
                    });
                } else {
                    throw new Error(data.error || 'Search failed');
                }
                return;
            }

            // Regular API call
            const params = new URLSearchParams({
                page: this.currentPage,
                per_page: this.perPage,
                unread_only: this.filters.unread_only,
                include_archived: this.filters.include_archived,
                archived_only: this.currentTab === 'archived'  // Only show archived when on archived tab
            });

            if (this.filters.type) params.append('type', this.filters.type);
            if (this.filters.category) params.append('category', this.filters.category);
            if (this.filters.tags) params.append('tags', this.filters.tags);
            if (this.filters.date_from) params.append('date_from', this.filters.date_from);
            if (this.filters.date_to) params.append('date_to', this.filters.date_to);

            const data = await _ncFetch(`/notifications/api?${params}`);

            if (data.success) {
                this.renderNotifications(data);
                this.updateTabCounts(data);
                this.updateStats(data);
            } else {
                throw new Error(data.error || 'Failed to load notifications');
            }
        } catch (error) {
            console.error('Error loading notifications:', error);
            container.replaceChildren();
            const errorDiv = document.createElement('div');
            errorDiv.className = 'empty-state';
            const errorIcon = document.createElement('i');
            errorIcon.className = 'fas fa-exclamation-triangle empty-state-icon';
            const errorTitle = document.createElement('h3');
            errorTitle.className = 'empty-state-title';
            errorTitle.textContent = 'Unable to Load Notifications';
            const errorMessage = document.createElement('p');
            errorMessage.className = 'empty-state-message';
            errorMessage.textContent = error.message || 'Please try again later';
            const retryBtn = document.createElement('button');
            retryBtn.type = 'button';
            retryBtn.setAttribute('data-action', 'notifications-center:retry');
            retryBtn.className = 'btn-primary mt-4';
            const retryIcon = document.createElement('i');
            retryIcon.className = 'fas fa-redo mr-2';
            retryBtn.appendChild(retryIcon);
            retryBtn.appendChild(document.createTextNode('Retry'));
            errorDiv.appendChild(errorIcon);
            errorDiv.appendChild(errorTitle);
            errorDiv.appendChild(errorMessage);
            errorDiv.appendChild(retryBtn);
            container.appendChild(errorDiv);
        }
    }

    renderNotifications(data) {
        const container = document.getElementById('notifications-center-list');
        const notifications = data.notifications || [];

        // Filter by search term (client-side)
        let filteredNotifications = notifications;
        if (this.filters.search) {
            const searchLower = this.filters.search.toLowerCase();
            filteredNotifications = notifications.filter(n =>
                n.title.toLowerCase().includes(searchLower) ||
                n.message.toLowerCase().includes(searchLower)
            );
        }

        if (filteredNotifications.length === 0) {
            const emptyStateMessage = this.getEmptyStateMessage();
            container.replaceChildren();
            const emptyDiv = document.createElement('div');
            emptyDiv.className = 'empty-state';
            const emptyIcon = document.createElement('i');
            emptyIcon.className = 'fas fa-bell-slash empty-state-icon';
            const emptyTitle = document.createElement('h3');
            emptyTitle.className = 'empty-state-title';
            emptyTitle.textContent = emptyStateMessage.title;
            const emptyMessage = document.createElement('p');
            emptyMessage.className = 'empty-state-message';
            emptyMessage.textContent = emptyStateMessage.message;
            emptyDiv.appendChild(emptyIcon);
            emptyDiv.appendChild(emptyTitle);
            emptyDiv.appendChild(emptyMessage);
            if (emptyStateMessage.actionKey) {
                const actionBtn = document.createElement('button');
                actionBtn.type = 'button';
                actionBtn.setAttribute('data-action', emptyStateMessage.actionKey);
                actionBtn.className = 'btn-primary mt-4';
                actionBtn.textContent = emptyStateMessage.actionText;
                emptyDiv.appendChild(actionBtn);
            }
            container.appendChild(emptyDiv);
            return;
        }

        // Render all notifications individually (no grouping)
        container.replaceChildren();
        const toRender = [];
        for (const notification of filteredNotifications) {
            if (notification.is_group && notification.notifications) {
                toRender.push(...notification.notifications);
            } else {
                toRender.push(notification);
            }
        }
        toRender.forEach(n => {
            const cardNode = this.renderNotificationCard(n);
            if (cardNode) container.appendChild(cardNode);
        });

        // Render pagination
        this.renderPagination(data);

        // Update selected checkboxes
        this.updateSelectedCheckboxes();

        // Attach event listeners for grouping
        this.attachGroupEventListeners();

        // Track viewing for visible notifications
        this.trackViewingForVisible();
    }

    trackViewingForVisible() {
        // Track viewing for notifications that are visible but not yet viewed
        const notificationCards = document.querySelectorAll('.notification-card[data-notification-id]');
        notificationCards.forEach(card => {
            const notificationId = card.dataset.notificationId;
            const notification = this.getNotificationById(notificationId);

            // Only track if not already viewed
            if (notification && !notification.viewed_at) {
                // Use Intersection Observer to track when notification becomes visible
                const observer = new IntersectionObserver((entries) => {
                    entries.forEach(entry => {
                        if (entry.isIntersecting) {
                            this.trackViewing(notificationId);
                            observer.unobserve(entry.target);
                        }
                    });
                }, { threshold: 0.5 });

                observer.observe(card);
            }
        });
    }

    getNotificationById(id) {
        // This would need to be implemented to get notification from current data
        // For now, we'll track viewing directly
        return null;
    }

    async trackViewing(notificationId) {
        try {
            await _ncFetch(`/notifications/api/${notificationId}/view`, {
                method: 'POST',
                body: JSON.stringify({})
            });
        } catch (error) {
            console.error('Error tracking notification view:', error);
        }
    }

    groupNotifications(notifications) {
        const grouped = { 'ungrouped': [] };

        for (const notification of notifications) {
            if (notification.group_id) {
                if (!grouped[notification.group_id]) {
                    grouped[notification.group_id] = [];
                }
                grouped[notification.group_id].push(notification);
            } else {
                grouped['ungrouped'].push(notification);
            }
        }

        return grouped;
    }

    renderNotificationGroup(groupId, notifications) {
        if (notifications.length === 0) return null;
        if (notifications.length === 1) {
            // Single notification in group, render as individual
            return this.renderNotificationCard(notifications[0]);
        }

        const firstNotification = notifications[0];
        const isExpanded = this.expandedGroups && this.expandedGroups.has(groupId);

        const groupDiv = document.createElement('div');
        groupDiv.className = 'notification-group';
        groupDiv.setAttribute('data-group-id', groupId);

        const headerDiv = document.createElement('div');
        headerDiv.className = `notification-group-header ${isExpanded ? 'expanded' : ''}`;
        headerDiv.setAttribute('data-action', 'notifications-center:toggle-group');
        headerDiv.setAttribute('data-group-id', groupId);

        const headerFlex = document.createElement('div');
        headerFlex.className = 'flex items-center justify-between';

        const leftDiv = document.createElement('div');
        leftDiv.className = 'flex items-center';
        const chevronIcon = document.createElement('i');
        chevronIcon.className = `fas fa-chevron-${isExpanded ? 'down' : 'right'} mr-2 text-gray-500`;
        const titleSpan = document.createElement('span');
        titleSpan.className = 'notification-group-title';
        titleSpan.textContent = firstNotification.title;
        const countSpan = document.createElement('span');
        countSpan.className = 'notification-group-count';
        countSpan.textContent = `(${notifications.length})`;
        leftDiv.appendChild(chevronIcon);
        leftDiv.appendChild(titleSpan);
        leftDiv.appendChild(countSpan);

        const timeSpan = document.createElement('span');
        timeSpan.className = 'notification-group-time';
        timeSpan.textContent = this.formatNotificationTimeDisplay(notifications[notifications.length - 1]);

        headerFlex.appendChild(leftDiv);
        headerFlex.appendChild(timeSpan);
        headerDiv.appendChild(headerFlex);
        groupDiv.appendChild(headerDiv);

        const contentDiv = document.createElement('div');
        contentDiv.className = `notification-group-content ${isExpanded ? '' : 'hidden'}`;
        notifications.forEach(n => {
            const card = this.renderNotificationCard(n, true);
            contentDiv.appendChild(card);
        });
        groupDiv.appendChild(contentDiv);

        return groupDiv;
    }

    toggleGroup(groupId) {
        if (!this.expandedGroups) {
            this.expandedGroups = new Set();
        }

        const escaped = (window.CSS && typeof window.CSS.escape === 'function') ? window.CSS.escape(groupId) : groupId.replace(/"/g, '\\"');
        const groupElement = document.querySelector(`[data-group-id="${escaped}"]`);
        if (!groupElement) return;

        const header = groupElement.querySelector('.notification-group-header');
        const content = groupElement.querySelector('.notification-group-content');
        const icon = header.querySelector('.fa-chevron-right, .fa-chevron-down');

        if (this.expandedGroups.has(groupId)) {
            // Collapse
            this.expandedGroups.delete(groupId);
            content.classList.add('hidden');
            header.classList.remove('expanded');
            icon.classList.remove('fa-chevron-down');
            icon.classList.add('fa-chevron-right');
        } else {
            // Expand
            this.expandedGroups.add(groupId);
            content.classList.remove('hidden');
            header.classList.add('expanded');
            icon.classList.remove('fa-chevron-right');
            icon.classList.add('fa-chevron-down');
        }
    }

    attachGroupEventListeners() {
        // Deprecated: groups are handled via delegated data-action handlers
    }

    /** Local calendar date + time for display (API sends ISO UTC in created_at / timestamp). */
    formatNotificationDateTime(iso) {
        if (!iso) return '';
        const d = new Date(iso);
        if (Number.isNaN(d.getTime())) return '';
        try {
            return new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(d);
        } catch (_) {
            return d.toLocaleString();
        }
    }

    /** Relative time from API plus absolute local date/time. */
    formatNotificationTimeDisplay(notification) {
        const timeAgo = (notification && notification.time_ago) ? String(notification.time_ago).trim() : '';
        const absolute = this.formatNotificationDateTime(
            (notification && (notification.created_at || notification.timestamp)) || ''
        );
        if (timeAgo && absolute) return `${timeAgo} · ${absolute}`;
        return timeAgo || absolute || '';
    }

    getTranslation(key) {
        // Get translation from window object, fallback to key if not found
        if (!window.NOTIFICATION_TRANSLATIONS) {
            console.warn('NOTIFICATION_TRANSLATIONS not loaded yet');
            return key;
        }
        const translation = window.NOTIFICATION_TRANSLATIONS[key];
        if (!translation) {
            console.warn(`Translation not found for key: ${key}`);
            return key;
        }
        return translation;
    }

    updateEmptyState() {
        const container = document.getElementById('notifications-center-list');
        if (!container) return;
        const hasCards = container.querySelector('.notification-card');
        if (hasCards) return;
        const emptyStateMessage = this.getEmptyStateMessage();
        container.replaceChildren();
        const emptyDiv = document.createElement('div');
        emptyDiv.className = 'empty-state';
        const emptyIcon = document.createElement('i');
        emptyIcon.className = 'fas fa-bell-slash empty-state-icon';
        const emptyTitle = document.createElement('h3');
        emptyTitle.className = 'empty-state-title';
        emptyTitle.textContent = emptyStateMessage.title;
        const emptyMessage = document.createElement('p');
        emptyMessage.className = 'empty-state-message';
        emptyMessage.textContent = emptyStateMessage.message;
        emptyDiv.appendChild(emptyIcon);
        emptyDiv.appendChild(emptyTitle);
        emptyDiv.appendChild(emptyMessage);
        if (emptyStateMessage.actionKey) {
            const actionBtn = document.createElement('button');
            actionBtn.type = 'button';
            actionBtn.setAttribute('data-action', emptyStateMessage.actionKey);
            actionBtn.className = 'btn-primary mt-4';
            actionBtn.textContent = emptyStateMessage.actionText;
            emptyDiv.appendChild(actionBtn);
        }
        container.appendChild(emptyDiv);
    }

    getEmptyStateMessage() {
        if (this.filters.search) {
            return {
                title: 'No Results Found',
                message: `No notifications match "${this.filters.search}". Try adjusting your search terms.`,
                actionKey: 'notifications-center:clear-filters',
                actionText: 'Clear Search'
            };
        } else if (this.currentTab === 'unread') {
            return {
                title: 'All Caught Up!',
                message: 'You have no unread notifications. Great job staying on top of things!',
                actionKey: null
            };
        } else if (this.currentTab === 'archived') {
            return {
                title: 'No Archived Notifications',
                message: 'You haven\'t archived any notifications yet.',
                actionKey: null
            };
        } else {
            return {
                title: 'No Notifications',
                message: 'You\'re all caught up!',
                actionKey: null
            };
        }
    }

    renderNotificationCard(notification, isInGroup = false) {
        const isUnread = !notification.is_read;
        const isArchived = notification.is_archived;
        const isSelected = this.selectedNotifications.has(notification.id);

        const isUrgent = notification.priority === 'urgent';
        const isHighPriority = notification.priority === 'high' || isUrgent;
        const priorityClass = isUrgent
            ? (isUnread ? 'urgent-priority' : 'urgent-priority urgent-priority-read')
            : isHighPriority
                ? (isUnread ? 'high-priority' : 'high-priority high-priority-read')
                : '';
        const safeIcon = notification.icon ? this.safeCssClasses(notification.icon) : '';
        const rawTitle = notification.title || '';
        const rawMessage = notification.message || '';
        const primaryIsMessage = notification.primary_is_message === true;
        let primaryText = rawTitle;
        let secondaryText = rawMessage;
        if (primaryIsMessage) {
            primaryText = rawMessage || rawTitle;
            secondaryText = rawTitle && rawTitle !== primaryText ? rawTitle : '';
        }
        const actor = notification.actor && typeof notification.actor === 'object' ? notification.actor : null;
        const actionIconSuffix = notification.actor_action_icon && typeof notification.actor_action_icon === 'string'
            ? notification.actor_action_icon.replace(/[^a-zA-Z0-9\-]/g, '')
            : '';
        const actionIconClass = actionIconSuffix
            ? `fas ${actionIconSuffix}`
            : (safeIcon || 'fas fa-bell');
        const typeLabelRaw = notification.notification_type_label || (notification.notification_type ? notification.notification_type.replace('_', ' ') : 'notification');
        const typeLabel = typeLabelRaw;
        const timeDisplay = this.formatNotificationTimeDisplay(notification);
        const priorityLabel = (notification.priority || '').toUpperCase();
        const relatedUrlRaw = notification.related_url;
        const safeRelatedUrl = (window.SafeDom && relatedUrlRaw) ? window.SafeDom.safeUrl(relatedUrlRaw, { allowSameOrigin: true }) : relatedUrlRaw;

        // Build notification card using DOM construction
        const card = document.createElement('div');
        card.className = `notification-card ${isUnread ? 'unread' : ''} ${isArchived ? 'archived' : ''} ${priorityClass} fade-in`;
        card.setAttribute('data-notification-id', notification.id.toString());

        const flexDiv = document.createElement('div');
        flexDiv.className = 'flex items-start';

        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.className = 'notification-checkbox form-checkbox';
        checkbox.setAttribute('data-notification-id', notification.id.toString());
        checkbox.checked = isSelected;

        let actorWrap = null;
        if (actor && actor.initials) {
            actorWrap = document.createElement('div');
            actorWrap.className = 'notification-card-actor flex-shrink-0 relative mr-3 mt-0.5';
            const circle = document.createElement('div');
            circle.className = 'notification-card-actor-circle flex items-center justify-center rounded-full text-white text-sm font-semibold';
            circle.style.width = '2.5rem';
            circle.style.height = '2.5rem';
            circle.style.backgroundColor = actor.profile_color || '#64748b';
            circle.textContent = String(actor.initials || '?').slice(0, 2);
            circle.setAttribute('aria-hidden', 'true');
            actorWrap.appendChild(circle);
            if (actionIconSuffix) {
                const badge = document.createElement('span');
                badge.className = 'notification-card-actor-badge';
                const badgeIcon = document.createElement('i');
                badgeIcon.className = `fas ${actionIconSuffix} notification-card-actor-badge-icon`;
                badge.appendChild(badgeIcon);
                actorWrap.appendChild(badge);
            }
        } else {
            actorWrap = document.createElement('div');
            actorWrap.className = 'notification-card-actor flex-shrink-0 relative mr-3 mt-0.5';
            const circle = document.createElement('div');
            circle.className = 'notification-card-action-circle flex items-center justify-center rounded-full';
            circle.style.width = '2.5rem';
            circle.style.height = '2.5rem';
            circle.setAttribute('aria-hidden', 'true');
            const innerIcon = document.createElement('i');
            innerIcon.className = `${actionIconClass} text-sm`;
            if (isUrgent) {
                innerIcon.classList.add('text-red-600');
            } else if (isHighPriority) {
                innerIcon.classList.add('text-orange-600');
            } else if (isUnread) {
                innerIcon.classList.add('text-blue-600');
            } else {
                innerIcon.classList.add('text-gray-500');
            }
            circle.appendChild(innerIcon);
            actorWrap.appendChild(circle);
        }

        const contentDiv = document.createElement('div');
        contentDiv.className = 'notification-content';

        const headerDiv = document.createElement('div');
        headerDiv.className = 'notification-header';

        const innerDiv = document.createElement('div');

        const titleH3 = document.createElement('h3');
        titleH3.className = 'notification-title';
        if (isUnread) {
            const unreadDot = document.createElement('span');
            unreadDot.className = 'notification-unread-dot';
            titleH3.appendChild(unreadDot);
        }
        titleH3.appendChild(document.createTextNode(primaryText || rawTitle));

        const metaDiv = document.createElement('div');
        metaDiv.className = 'notification-meta';

        const typeBadge = document.createElement('span');
        typeBadge.className = 'notification-type-badge';
        typeBadge.style.backgroundColor = '#e0e7ff';
        typeBadge.style.color = '#3730a3';
        typeBadge.textContent = typeLabel;
        metaDiv.appendChild(typeBadge);

        if (notification.category) {
            const categoryBadge = document.createElement('span');
            categoryBadge.className = 'notification-category-badge';
            categoryBadge.style.backgroundColor = '#fef3c7';
            categoryBadge.style.color = '#92400e';
            categoryBadge.style.padding = '2px 8px';
            categoryBadge.style.borderRadius = '4px';
            categoryBadge.style.fontSize = '0.75rem';
            categoryBadge.style.fontWeight = '500';
            const tagIcon = document.createElement('i');
            tagIcon.className = 'fas fa-tag mr-1';
            categoryBadge.appendChild(tagIcon);
            categoryBadge.appendChild(document.createTextNode(notification.category));
            metaDiv.appendChild(categoryBadge);
        }

        if (notification.tags && notification.tags.length > 0) {
            notification.tags.forEach(tag => {
                const tagBadge = document.createElement('span');
                tagBadge.className = 'notification-tag-badge';
                tagBadge.style.backgroundColor = '#e0e7ff';
                tagBadge.style.color = '#3730a3';
                tagBadge.style.padding = '2px 6px';
                tagBadge.style.borderRadius = '3px';
                tagBadge.style.fontSize = '0.7rem';
                tagBadge.style.marginRight = '4px';
                tagBadge.textContent = tag;
                metaDiv.appendChild(tagBadge);
            });
        }

        if (notification.entity_name) {
            const entityBadge = document.createElement('span');
            entityBadge.className = 'notification-entity-badge';
            entityBadge.style.backgroundColor = '#f0f9ff';
            entityBadge.style.color = '#0369a1';
            entityBadge.style.padding = '2px 8px';
            entityBadge.style.borderRadius = '4px';
            entityBadge.style.fontSize = '0.75rem';
            entityBadge.style.fontWeight = '500';
            const mapIcon = document.createElement('i');
            mapIcon.className = 'fas fa-map-marker-alt mr-1';
            entityBadge.appendChild(mapIcon);
            entityBadge.appendChild(document.createTextNode(notification.entity_name));
            metaDiv.appendChild(entityBadge);
        }

        if (notification.viewed_at) {
            const viewedIndicator = document.createElement('span');
            viewedIndicator.className = 'notification-viewed-indicator';
            viewedIndicator.style.color = '#6b7280';
            viewedIndicator.style.fontSize = '0.7rem';
            viewedIndicator.setAttribute('title', 'Viewed');
            const eyeIcon = document.createElement('i');
            eyeIcon.className = 'fas fa-eye mr-1';
            viewedIndicator.appendChild(eyeIcon);
            metaDiv.appendChild(viewedIndicator);
        }

        const timeSpan = document.createElement('span');
        timeSpan.className = 'notification-time';
        timeSpan.textContent = timeDisplay;
        const absOnly = this.formatNotificationDateTime(notification.created_at || notification.timestamp);
        if (absOnly) timeSpan.setAttribute('title', absOnly);
        metaDiv.appendChild(timeSpan);

        if (notification.priority !== 'normal') {
            const priorityBadge = document.createElement('span');
            const isUrgentBadge = notification.priority === 'urgent';
            priorityBadge.className = 'notification-priority-badge ml-1 px-2 py-0.5 text-xs font-bold text-white rounded';
            priorityBadge.style.display = 'inline-block';
            priorityBadge.style.fontSize = '9px';
            priorityBadge.style.letterSpacing = '0.5px';
            priorityBadge.style.backgroundColor = isUrgentBadge ? '#dc2626' : '#f97316';
            priorityBadge.style.color = '#ffffff';
            priorityBadge.style.paddingLeft = '0.5rem';
            priorityBadge.style.paddingRight = '0.5rem';
            priorityBadge.textContent = priorityLabel;
            metaDiv.appendChild(priorityBadge);
        }

        innerDiv.appendChild(titleH3);
        innerDiv.appendChild(metaDiv);
        headerDiv.appendChild(innerDiv);
        contentDiv.appendChild(headerDiv);

        const messageP = document.createElement('p');
        messageP.className = 'notification-message';
        messageP.textContent = notification.message;
        contentDiv.appendChild(messageP);

        const actionsDiv = document.createElement('div');
        actionsDiv.className = 'notification-actions';

        if (isUnread) {
            const markReadBtn = document.createElement('button');
            markReadBtn.type = 'button';
            markReadBtn.className = 'notification-action-btn group';
            markReadBtn.setAttribute('data-action', 'notifications-center:mark-read');
            markReadBtn.setAttribute('data-notification-id', notification.id.toString());
            const openIcon = document.createElement('i');
            openIcon.className = 'far fa-envelope-open text-gray-300 group-hover:text-gray-600';
            markReadBtn.appendChild(openIcon);
            markReadBtn.appendChild(document.createTextNode(` ${this.getTranslation('Mark as Read')}`));
            markReadBtn.addEventListener('mouseenter', () => { openIcon.classList.replace('far', 'fas'); });
            markReadBtn.addEventListener('mouseleave', () => { openIcon.classList.replace('fas', 'far'); });
            actionsDiv.appendChild(markReadBtn);
        } else {
            const markUnreadBtn = document.createElement('button');
            markUnreadBtn.type = 'button';
            markUnreadBtn.className = 'notification-action-btn group';
            markUnreadBtn.setAttribute('data-action', 'notifications-center:mark-unread');
            markUnreadBtn.setAttribute('data-notification-id', notification.id.toString());
            const envelopeIcon = document.createElement('i');
            envelopeIcon.className = 'far fa-envelope text-gray-300 group-hover:text-gray-600';
            markUnreadBtn.appendChild(envelopeIcon);
            markUnreadBtn.appendChild(document.createTextNode(` ${this.getTranslation('Mark as Unread')}`));
            markUnreadBtn.addEventListener('mouseenter', () => { envelopeIcon.classList.replace('far', 'fas'); });
            markUnreadBtn.addEventListener('mouseleave', () => { envelopeIcon.classList.replace('fas', 'far'); });
            actionsDiv.appendChild(markUnreadBtn);
        }

        if (!isArchived) {
            const archiveBtn = document.createElement('button');
            archiveBtn.type = 'button';
            archiveBtn.className = 'notification-action-btn';
            archiveBtn.setAttribute('data-action', 'notifications-center:archive');
            archiveBtn.setAttribute('data-notification-id', notification.id.toString());
            const archiveIcon = document.createElement('i');
            archiveIcon.className = 'fas fa-archive';
            archiveBtn.appendChild(archiveIcon);
            archiveBtn.appendChild(document.createTextNode(` ${this.getTranslation('Archive')}`));
            actionsDiv.appendChild(archiveBtn);
        }

        if (safeRelatedUrl && safeRelatedUrl !== 'None') {
            const viewBtn = document.createElement('button');
            viewBtn.type = 'button';
            viewBtn.className = 'notification-action-btn';
            viewBtn.setAttribute('data-action', 'notifications-center:view-related');
            viewBtn.setAttribute('data-related-url', safeRelatedUrl);
            const externalIcon = document.createElement('i');
            externalIcon.className = 'fas fa-external-link-alt';
            viewBtn.appendChild(externalIcon);
            viewBtn.appendChild(document.createTextNode(` ${this.getTranslation('View')}`));
            actionsDiv.appendChild(viewBtn);
        }

        if (notification.action_buttons && notification.action_buttons.length > 0) {
            notification.action_buttons.forEach(btn => {
                const customBtn = document.createElement('button');
                customBtn.type = 'button';
                customBtn.className = `notification-action-btn ${btn.style === 'danger' ? 'btn-danger' : btn.style === 'primary' ? 'btn-primary' : ''}`;
                customBtn.setAttribute('data-action', 'notifications-center:custom-action');
                customBtn.setAttribute('data-notification-id', notification.id.toString());
                customBtn.setAttribute('data-action-key', btn.action);
                customBtn.textContent = btn.label;
                actionsDiv.appendChild(customBtn);
            });
        }

        const deleteBtn = document.createElement('button');
        deleteBtn.type = 'button';
        deleteBtn.className = 'notification-action-btn';
        deleteBtn.setAttribute('data-action', 'notifications-center:delete');
        deleteBtn.setAttribute('data-notification-id', notification.id.toString());
        const trashIcon = document.createElement('i');
        trashIcon.className = 'fas fa-trash';
        deleteBtn.appendChild(trashIcon);
        deleteBtn.appendChild(document.createTextNode(` ${this.getTranslation('Delete')}`));
        actionsDiv.appendChild(deleteBtn);

        contentDiv.appendChild(actionsDiv);
        flexDiv.appendChild(checkbox);
        if (actorWrap) {
            flexDiv.appendChild(actorWrap);
        }
        flexDiv.appendChild(contentDiv);
        card.appendChild(flexDiv);

        return card;
    }

    renderPagination(data) {
        const container = document.getElementById('pagination-controls');
        const totalPages = Math.ceil(data.total_count / this.perPage);

        if (totalPages <= 1) {
            container.replaceChildren();
            return;
        }

        container.replaceChildren();

        // Previous button
        const prevBtn = document.createElement('button');
        prevBtn.className = 'pagination-btn';
        if (this.currentPage === 1) prevBtn.disabled = true;
        prevBtn.setAttribute('data-action', 'notifications-center:go-to-page');
        prevBtn.setAttribute('data-page', (this.currentPage - 1).toString());
        const prevIcon = document.createElement('i');
        prevIcon.className = 'fas fa-chevron-left';
        prevBtn.appendChild(prevIcon);
        container.appendChild(prevBtn);

        // Show page numbers
        const showPages = 5;
        let startPage = Math.max(1, this.currentPage - Math.floor(showPages / 2));
        let endPage = Math.min(totalPages, startPage + showPages - 1);

        if (endPage - startPage < showPages - 1) {
            startPage = Math.max(1, endPage - showPages + 1);
        }

        if (startPage > 1) {
            const firstBtn = document.createElement('button');
            firstBtn.type = 'button';
            firstBtn.className = 'pagination-btn';
            firstBtn.setAttribute('data-action', 'notifications-center:go-to-page');
            firstBtn.setAttribute('data-page', '1');
            firstBtn.textContent = '1';
            container.appendChild(firstBtn);
            if (startPage > 2) {
                const ellipsis1 = document.createElement('span');
                ellipsis1.className = 'pagination-info';
                ellipsis1.textContent = '...';
                container.appendChild(ellipsis1);
            }
        }

        for (let i = startPage; i <= endPage; i++) {
            const pageBtn = document.createElement('button');
            pageBtn.type = 'button';
            pageBtn.className = `pagination-btn ${i === this.currentPage ? 'active' : ''}`;
            pageBtn.setAttribute('data-action', 'notifications-center:go-to-page');
            pageBtn.setAttribute('data-page', i.toString());
            pageBtn.textContent = i.toString();
            container.appendChild(pageBtn);
        }

        if (endPage < totalPages) {
            if (endPage < totalPages - 1) {
                const ellipsis2 = document.createElement('span');
                ellipsis2.className = 'pagination-info';
                ellipsis2.textContent = '...';
                container.appendChild(ellipsis2);
            }
            const lastBtn = document.createElement('button');
            lastBtn.type = 'button';
            lastBtn.className = 'pagination-btn';
            lastBtn.setAttribute('data-action', 'notifications-center:go-to-page');
            lastBtn.setAttribute('data-page', totalPages.toString());
            lastBtn.textContent = totalPages.toString();
            container.appendChild(lastBtn);
        }

        // Next button
        const nextBtn = document.createElement('button');
        nextBtn.className = 'pagination-btn';
        if (this.currentPage === totalPages) nextBtn.disabled = true;
        nextBtn.setAttribute('data-action', 'notifications-center:go-to-page');
        nextBtn.setAttribute('data-page', (this.currentPage + 1).toString());
        const nextIcon = document.createElement('i');
        nextIcon.className = 'fas fa-chevron-right';
        nextBtn.appendChild(nextIcon);
        container.appendChild(nextBtn);

        // Total count
        const totalSpan = document.createElement('span');
        totalSpan.className = 'pagination-info';
        totalSpan.textContent = `${data.total_count} total`;
        container.appendChild(totalSpan);
    }

    goToPage(page) {
        const p = parseInt(page, 10);
        if (!Number.isFinite(p) || p < 1) return;
        this.currentPage = p;
        this.loadNotifications();
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    toggleSelection(notificationId) {
        if (this.selectedNotifications.has(notificationId)) {
            this.selectedNotifications.delete(notificationId);
        } else {
            this.selectedNotifications.add(notificationId);
        }
        this.updateBulkActionsBar();
    }

    updateSelectedCheckboxes() {
        document.querySelectorAll('.notification-checkbox').forEach(checkbox => {
            const id = parseInt(checkbox.dataset.notificationId);
            checkbox.checked = this.selectedNotifications.has(id);
        });
    }

    updateBulkActionsBar() {
        const bar = document.getElementById('bulk-actions-bar');
        const count = document.getElementById('selected-count');

        count.textContent = this.selectedNotifications.size;

        if (this.selectedNotifications.size > 0) {
            bar.classList.remove('hidden');
        } else {
            bar.classList.add('hidden');
        }
    }

    async handleBulkAction(action) {
        const ids = Array.from(this.selectedNotifications);

        if (ids.length === 0) {
            window.showAlert('Please select notifications first', 'warning');
            return;
        }

        if (action === 'delete') {
            const performDelete = async () => {
                try {
                    await this.deleteNotifications(ids);
                    this.selectedNotifications.clear();
                    this.updateBulkActionsBar();
                    this.loadNotifications();
                } catch (error) {
                    console.error('Error deleting notifications:', error);
                    window.showAlert('Failed to delete notifications. Please try again.', 'error');
                }
            };

            if (window.showDangerConfirmation) {
                window.showDangerConfirmation(
                    `Are you sure you want to delete ${ids.length} notification(s)?`,
                    performDelete,
                    null,
                    'Delete',
                    'Cancel',
                    'Delete Notifications?'
                );
                return;
            } else {
                return;
            }
        }

        try {
            switch (action) {
                case 'mark_read':
                    await this.markAsRead(ids);
                    break;
                case 'mark_unread':
                    await this.markAsUnread(ids);
                    break;
                case 'archive':
                    await this.archiveNotifications(ids);
                    break;
                case 'delete':
                    await this.deleteNotifications(ids);
                    break;
            }

            // Clear selection
            this.selectedNotifications.clear();
            this.updateBulkActionsBar();
        } catch (error) {
            console.error(`Error performing ${action}:`, error);
            window.showAlert(`Failed to ${action} notifications. Please try again.`, 'error');
        }
    }

    async markAsUnread(notificationIds) {
        try {
            const data = await _ncFetch('/notifications/mark-unread', {
                method: 'POST',
                body: JSON.stringify({ notification_ids: notificationIds })
            });

            if (data.success) {
                // Update unread count badge if available
                if (data.unread_count !== undefined && window.updateNotificationBadge) {
                    window.updateNotificationBadge(data.unread_count);
                }

                // Update tab counts if provided
                if (data.all_count !== undefined || data.archived_count !== undefined) {
                    this.updateTabCounts(data);
                }

                // Update cards in place (no reload)
                this.updateCardsReadState(notificationIds, false);
            } else {
                throw new Error(data.error || 'Failed to mark as unread');
            }
        } catch (error) {
            console.error('Error marking notifications as unread:', error);
            window.showAlert('Failed to mark notifications as unread. Please try again.', 'error');
        }
    }

    async markAsRead(notificationIds) {
        try {
            const data = await _ncFetch('/notifications/mark-read', {
                method: 'POST',
                body: JSON.stringify({ notification_ids: notificationIds })
            });

            if (data.success) {
                // Update unread count badge if available
                if (data.unread_count !== undefined && window.updateNotificationBadge) {
                    window.updateNotificationBadge(data.unread_count);
                }

                // Update tab counts if provided
                if (data.all_count !== undefined || data.archived_count !== undefined) {
                    this.updateTabCounts(data);
                }

                // Update cards in place (no reload)
                this.updateCardsReadState(notificationIds, true);
            } else {
                throw new Error(data.error || 'Failed to mark as read');
            }
        } catch (error) {
            console.error('Error marking notifications as read:', error);
            window.showAlert('Failed to mark notifications as read. Please try again.', 'error');
        }
    }

    /**
     * Update notification cards in place after mark read/unread (no page reload).
     * @param {number[]} notificationIds - IDs to update
     * @param {boolean} isRead - true = mark as read, false = mark as unread
     */
    updateCardsReadState(notificationIds, isRead) {
        const ids = Array.isArray(notificationIds) ? notificationIds : [notificationIds];
        const removeIfMismatch = (id) => {
            if (this.currentTab === 'unread' && isRead) return true;
            if (this.currentTab === 'read' && !isRead) return true;
            return false;
        };

        ids.forEach(id => {
            const card = document.querySelector(`.notification-card[data-notification-id="${id}"]`);
            if (!card) return;

            if (removeIfMismatch(id)) {
                card.remove();
                return;
            }

            if (isRead) {
                card.classList.remove('unread');
                const dot = card.querySelector('.notification-unread-dot');
                if (dot) dot.remove();
                const markReadBtn = card.querySelector('[data-action="notifications-center:mark-read"]');
                if (markReadBtn) {
                    const markUnreadBtn = document.createElement('button');
                    markUnreadBtn.type = 'button';
                    markUnreadBtn.className = 'notification-action-btn group';
                    markUnreadBtn.setAttribute('data-action', 'notifications-center:mark-unread');
                    markUnreadBtn.setAttribute('data-notification-id', id.toString());
                    const envelopeIcon = document.createElement('i');
                    envelopeIcon.className = 'far fa-envelope text-gray-300 group-hover:text-gray-600';
                    markUnreadBtn.appendChild(envelopeIcon);
                    markUnreadBtn.appendChild(document.createTextNode(` ${this.getTranslation('Mark as Unread')}`));
                    markUnreadBtn.addEventListener('mouseenter', () => { envelopeIcon.classList.replace('far', 'fas'); });
                    markUnreadBtn.addEventListener('mouseleave', () => { envelopeIcon.classList.replace('fas', 'far'); });
                    markReadBtn.replaceWith(markUnreadBtn);
                }
            } else {
                card.classList.add('unread');
                const titleH3 = card.querySelector('.notification-title');
                if (titleH3 && !titleH3.querySelector('.notification-unread-dot')) {
                    const unreadDot = document.createElement('span');
                    unreadDot.className = 'notification-unread-dot';
                    titleH3.insertBefore(unreadDot, titleH3.firstChild);
                }
                const markUnreadBtn = card.querySelector('[data-action="notifications-center:mark-unread"]');
                if (markUnreadBtn) {
                    const markReadBtn = document.createElement('button');
                    markReadBtn.type = 'button';
                    markReadBtn.className = 'notification-action-btn group';
                    markReadBtn.setAttribute('data-action', 'notifications-center:mark-read');
                    markReadBtn.setAttribute('data-notification-id', id.toString());
                    const openIcon = document.createElement('i');
                    openIcon.className = 'far fa-envelope-open text-gray-300 group-hover:text-gray-600';
                    markReadBtn.appendChild(openIcon);
                    markReadBtn.appendChild(document.createTextNode(` ${this.getTranslation('Mark as Read')}`));
                    markReadBtn.addEventListener('mouseenter', () => { openIcon.classList.replace('far', 'fas'); });
                    markReadBtn.addEventListener('mouseleave', () => { openIcon.classList.replace('fas', 'far'); });
                    markUnreadBtn.replaceWith(markReadBtn);
                }
            }
        });

        this.updateEmptyState();
    }

    async archiveNotifications(notificationIds) {
        try {
            const data = await _ncFetch('/notifications/api/archive', {
                method: 'POST',
                body: JSON.stringify({ notification_ids: notificationIds })
            });

            if (data.success) {
                // Clear selection
                this.selectedNotifications.clear();
                this.updateBulkActionsBar();

                // Update unread count badge if available
                if (data.unread_count !== undefined && window.updateNotificationBadge) {
                    window.updateNotificationBadge(data.unread_count);
                }

                // Update tab counts if provided
                if (data.all_count !== undefined || data.archived_count !== undefined) {
                    this.updateTabCounts(data);
                }

                // Reload notifications to reflect changes
                this.loadNotifications();
            } else {
                throw new Error(data.error || 'Failed to archive notifications');
            }
        } catch (error) {
            console.error('Error archiving notifications:', error);
            window.showAlert('Failed to archive notifications. Please try again.', 'error');
        }
    }

    async deleteNotifications(notificationIds) {
        try {
            const data = await _ncFetch('/notifications/api/delete', {
                method: 'DELETE',
                body: JSON.stringify({ notification_ids: notificationIds })
            });

            if (data.success) {
                // Clear selection
                this.selectedNotifications.clear();
                this.updateBulkActionsBar();

                // Update unread count badge if available
                if (data.unread_count !== undefined && window.updateNotificationBadge) {
                    window.updateNotificationBadge(data.unread_count);
                }

                // Update tab counts if provided
                if (data.all_count !== undefined || data.archived_count !== undefined) {
                    this.updateTabCounts(data);
                }

                // Reload notifications to reflect changes
                this.loadNotifications();
            } else {
                throw new Error(data.error || 'Failed to delete notifications');
            }
        } catch (error) {
            console.error('Error deleting notifications:', error);
            window.showAlert('Failed to delete notifications. Please try again.', 'error');
        }
    }

    applyFilters() {
        this.filters.type = document.getElementById('type-filter').value || null;
        this.filters.category = document.getElementById('category-filter').value || null;
        const tagsInput = document.getElementById('tags-filter')?.value.trim();
        this.filters.tags = tagsInput ? tagsInput : null;
        this.filters.date_from = document.getElementById('date-from-filter').value || null;
        this.filters.date_to = document.getElementById('date-to-filter').value || null;
        this.filters.search = document.getElementById('search-filter').value.trim() || null;

        this.currentPage = 1;
        this.loadNotifications();
    }

    clearFilters() {
        document.getElementById('type-filter').value = '';
        document.getElementById('category-filter').value = '';
        document.getElementById('tags-filter').value = '';
        document.getElementById('date-from-filter').value = '';
        document.getElementById('date-to-filter').value = '';
        document.getElementById('search-filter').value = '';

        this.filters = {
            unread_only: this.currentTab === 'unread',
            type: null,
            category: null,
            tags: null,
            date_from: null,
            date_to: null,
            search: null,
            include_archived: this.currentTab === 'archived'
        };

        this.currentPage = 1;
        this.loadNotifications();
    }

    updateTabCounts(data) {
        // Update tab counts with accurate counts from backend
        const countAllEl = document.getElementById('count-all');
        const countUnreadEl = document.getElementById('count-unread');
        const countArchivedEl = document.getElementById('count-archived');

        if (countAllEl) {
            countAllEl.textContent = data.all_count || 0;
        }
        if (countUnreadEl) {
            countUnreadEl.textContent = data.unread_count || 0;
        }
        if (countArchivedEl) {
            countArchivedEl.textContent = data.archived_count || 0;
        }
    }

    updateStats(data) {
        // Update statistics cards
        const statUnread = document.getElementById('stat-unread');
        const statTotal = document.getElementById('stat-total');

        if (statUnread) {
            statUnread.textContent = data.unread_count || 0;
        }
        if (statTotal) {
            statTotal.textContent = data.all_count || 0;
        }

        // Calculate week and month stats from notifications if available
        if (data.notifications && Array.isArray(data.notifications)) {
            const now = new Date();
            const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
            const monthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);

            const weekCount = data.notifications.filter(n => {
                const created = new Date(n.created_at);
                return created >= weekAgo;
            }).length;

            const monthCount = data.notifications.filter(n => {
                const created = new Date(n.created_at);
                return created >= monthAgo;
            }).length;

            const statWeek = document.getElementById('stat-week');
            const statMonth = document.getElementById('stat-month');

            if (statWeek) {
                statWeek.textContent = weekCount;
            }
            if (statMonth) {
                statMonth.textContent = monthCount;
            }
        }
    }

    togglePreferences() {
        const panel = document.getElementById('preferences-panel');
        panel.classList.toggle('hidden');
    }

    async loadPreferences() {
        try {
            const data = await _ncFetch('/notifications/api/preferences');

            if (data.success) {
                this.populatePreferences(data.preferences);
            }
        } catch (error) {
            console.error('Error loading preferences:', error);
        }
    }

    populatePreferences(preferences) {
        document.getElementById('pref-sound-enabled').checked = preferences.sound_enabled;
        const frequency = preferences.notification_frequency || 'instant';
        document.getElementById('pref-frequency').value = frequency;

        // Toggle digest schedule visibility based on frequency
        this.toggleDigestSchedule(frequency);

        // Set digest day and time if they exist
        if (preferences.digest_day) {
            document.getElementById('pref-digest-day').value = preferences.digest_day;
        }
        if (preferences.digest_time) {
            document.getElementById('pref-digest-time').value = preferences.digest_time;
        } else {
            // Default to 9:00 AM if no time set
            document.getElementById('pref-digest-time').value = '09:00';
        }

        // Set notification type email checkboxes
        // Empty array means all enabled
        const emailEnabledTypes = preferences.notification_types_enabled || [];
        const allEmailEnabled = emailEnabledTypes.length === 0;

        document.querySelectorAll('.notification-type-email').forEach(checkbox => {
            const type = checkbox.getAttribute('data-type');
            checkbox.checked = allEmailEnabled || emailEnabledTypes.includes(type);
        });

        // Update select all email checkbox
        this.updateSelectAllState('email');

        // Set notification type push checkboxes
        // Empty array means all enabled
        const pushEnabledTypes = preferences.push_notification_types_enabled || [];
        const allPushEnabled = pushEnabledTypes.length === 0;

        document.querySelectorAll('.notification-type-push').forEach(checkbox => {
            const type = checkbox.getAttribute('data-type');
            checkbox.checked = allPushEnabled || pushEnabledTypes.includes(type);
        });

        // Update select all push checkbox
        this.updateSelectAllState('push');

        // Update digest preview
        this.updateDigestPreview(preferences);
    }

    toggleDigestSchedule(frequency) {
        const scheduleGroup = document.getElementById('digest-schedule-group');
        const dayGroup = document.getElementById('digest-day-group');

        if (frequency === 'daily' || frequency === 'weekly') {
            if (scheduleGroup) scheduleGroup.style.display = 'grid';
            // Show day selector only for weekly
            if (dayGroup) {
                dayGroup.style.display = frequency === 'weekly' ? 'block' : 'none';
            }
        } else {
            if (scheduleGroup) scheduleGroup.style.display = 'none';
        }

        // Update digest preview when frequency changes
        const preferences = {
            notification_frequency: frequency,
            digest_day: document.getElementById('pref-digest-day')?.value,
            digest_time: document.getElementById('pref-digest-time')?.value || '09:00'
        };
        this.updateDigestPreview(preferences);
    }

    updateDigestPreview(preferences) {
        const previewEl = document.getElementById('digest-preview');
        const previewText = document.getElementById('digest-preview-text');
        if (!previewEl || !previewText) return;

        const frequency = preferences.notification_frequency || 'instant';
        const digestDay = preferences.digest_day;
        const digestTime = preferences.digest_time || '09:00';

        if (frequency === 'instant') {
            previewEl.classList.add('hidden');
        } else if (frequency === 'daily') {
            previewEl.classList.remove('hidden');
            previewText.textContent = `You will receive a daily digest email at ${digestTime}.`;
        } else if (frequency === 'weekly') {
            const dayName = digestDay ? digestDay.charAt(0).toUpperCase() + digestDay.slice(1) : 'Monday';
            previewEl.classList.remove('hidden');
            previewText.textContent = `You will receive a weekly digest email every ${dayName} at ${digestTime}.`;
        }
    }

    updateDigestPreviewFromForm() {
        const preferences = {
            notification_frequency: document.getElementById('pref-frequency')?.value || 'instant',
            digest_day: document.getElementById('pref-digest-day')?.value,
            digest_time: document.getElementById('pref-digest-time')?.value || '09:00'
        };
        this.updateDigestPreview(preferences);
    }

    toggleSelectAll(type, checked) {
        const selector = type === 'email' ? '.notification-type-email' : '.notification-type-push';
        document.querySelectorAll(selector).forEach(checkbox => {
            checkbox.checked = checked;
        });
    }

    updateSelectAllState(type) {
        const selector = type === 'email' ? '.notification-type-email' : '.notification-type-push';
        const selectAllId = type === 'email' ? 'select-all-email' : 'select-all-push';

        const checkboxes = Array.from(document.querySelectorAll(selector));
        const allChecked = checkboxes.length > 0 && checkboxes.every(cb => cb.checked);
        const selectAllCheckbox = document.getElementById(selectAllId);

        if (selectAllCheckbox) {
            selectAllCheckbox.checked = allChecked;
        }
    }

    async savePreferences() {
        // Get save button and store original state
        const saveButton = document.getElementById('save-preferences');
        let originalNodes = null;

        if (saveButton) {
            // Store original button content
            originalNodes = document.createElement('div');
            Array.from(saveButton.childNodes).forEach(node => {
                originalNodes.appendChild(node.cloneNode(true));
            });

            // Disable button and show loading state
            saveButton.disabled = true;
            saveButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
        }

        // Get all notification types (from email checkboxes)
        const allNotificationTypes = Array.from(document.querySelectorAll('.notification-type-email'))
            .map(cb => cb.getAttribute('data-type'));

        // Get enabled email notification types
        const enabledEmailTypes = Array.from(document.querySelectorAll('.notification-type-email:checked'))
            .map(cb => cb.getAttribute('data-type'));

        // Get enabled push notification types
        const enabledPushTypes = Array.from(document.querySelectorAll('.notification-type-push:checked'))
            .map(cb => cb.getAttribute('data-type'));

        // If all types are enabled, send empty array (backend interprets as all enabled)
        const allEmailSelected = enabledEmailTypes.length === allNotificationTypes.length;
        const allPushSelected = enabledPushTypes.length === allNotificationTypes.length;

        const emailTypesToSend = allEmailSelected ? [] : enabledEmailTypes;
        const pushTypesToSend = allPushSelected ? [] : enabledPushTypes;

        // Determine email_notifications and push_notifications
        // True if all types selected (empty array) OR if some types are selected
        const emailNotifications = allEmailSelected || enabledEmailTypes.length > 0;
        const pushNotifications = allPushSelected || enabledPushTypes.length > 0;

        const frequency = document.getElementById('pref-frequency').value;
        const preferences = {
            email_notifications: emailNotifications,
            sound_enabled: document.getElementById('pref-sound-enabled').checked,
            notification_frequency: frequency,
            notification_types_enabled: emailTypesToSend,
            push_notifications: pushNotifications,
            push_notification_types_enabled: pushTypesToSend
        };

        // Add digest day and time if daily or weekly is selected
        if (frequency === 'daily' || frequency === 'weekly') {
            preferences.digest_time = document.getElementById('pref-digest-time').value;
            if (frequency === 'weekly') {
                preferences.digest_day = document.getElementById('pref-digest-day').value;
            } else {
                preferences.digest_day = null; // Clear day for daily
            }
        } else {
            preferences.digest_day = null;
            preferences.digest_time = null;
        }

        // Check if user is disabling all notifications
        if (!emailNotifications && !pushNotifications) {
            const message = 'You are disabling all email and push notifications. ' +
                'You will not receive any notifications. Are you sure?';
            if (window.showDangerConfirmation) {
                return new Promise((resolve) => {
                    window.showDangerConfirmation(
                        message,
                        async () => {
                            // Continue with save after confirmation
                            await this.savePreferencesInternal(preferences, saveButton, originalNodes);
                            resolve();
                        },
                        () => {
                            // User cancelled - restore button state
                            if (saveButton && originalNodes) {
                                saveButton.disabled = false;
                                saveButton.replaceChildren();
                                Array.from(originalNodes.childNodes).forEach(node => {
                                    saveButton.appendChild(node.cloneNode(true));
                                });
                            } else if (saveButton) {
                                saveButton.disabled = false;
                            }
                            resolve();
                        },
                        'Disable All',
                        'Cancel',
                        'Disable All Notifications?'
                    );
                });
            } else if (window.showConfirmation) {
                return new Promise((resolve) => {
                    window.showConfirmation(
                        message,
                        async () => {
                            await this.savePreferencesInternal(preferences, saveButton, originalNodes);
                            resolve();
                        },
                        () => {
                            if (saveButton && originalNodes) {
                                saveButton.disabled = false;
                                saveButton.replaceChildren();
                                Array.from(originalNodes.childNodes).forEach(node => {
                                    saveButton.appendChild(node.cloneNode(true));
                                });
                            } else if (saveButton) {
                                saveButton.disabled = false;
                            }
                            resolve();
                        },
                        'Disable All',
                        'Cancel',
                        'Disable All Notifications?'
                    );
                });
            } else {
                if (saveButton && originalNodes) {
                    saveButton.disabled = false;
                    saveButton.replaceChildren();
                    Array.from(originalNodes.childNodes).forEach(node => {
                        saveButton.appendChild(node.cloneNode(true));
                    });
                } else if (saveButton) {
                    saveButton.disabled = false;
                }
                return;
            }
        }

        // Continue with save if not using custom dialog (or if confirmed via native)
        await this.savePreferencesInternal(preferences, saveButton, originalNodes);
    }

    async savePreferencesInternal(preferences, saveButton, originalNodes) {
        try {
            const data = await _ncFetch('/notifications/api/preferences', {
                method: 'POST',
                body: JSON.stringify(preferences)
            });

            if (data.success) {
                // Show success message
                this.showFlashMessage('Preferences saved successfully', 'success');
                this.togglePreferences();

                // Update digest preview with saved preferences
                if (data.preferences) {
                    this.updateDigestPreview(data.preferences);
                }
            } else {
                throw new Error(data.error || 'Failed to save preferences');
            }
        } catch (error) {
            console.error('Error saving preferences:', error);

            // Show detailed error message
            let errorMessage = 'Failed to save preferences. ';
            if (error.message.includes('Validation')) {
                errorMessage += 'Please check your settings and try again.';
            } else if (error.message.includes('network') || error.message.includes('fetch')) {
                errorMessage += 'Network error. Please check your connection and try again.';
            } else {
                errorMessage += error.message || 'Please try again.';
            }

            this.showFlashMessage(errorMessage, 'error');
        } finally {
            // Restore button state
            if (saveButton && originalNodes) {
                saveButton.disabled = false;
                saveButton.replaceChildren();
                // Clone and append original nodes
                Array.from(originalNodes.childNodes).forEach(node => {
                    saveButton.appendChild(node.cloneNode(true));
                });
            } else if (saveButton) {
                saveButton.disabled = false;
            }
        }
    }


    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    safeCssClasses(value) {
        // Defensive: prevent breaking out of class="" attribute.
        // Allow only common CSS class token characters.
        const raw = String(value || '').trim();
        if (!raw) return '';
        const cleaned = raw.replace(/[^a-zA-Z0-9 _:-]/g, '').trim();
        return cleaned;
    }

    async handleAction(notificationId, action) {
        try {
            const data = await _ncFetch(`/notifications/api/${notificationId}/action`, {
                method: 'POST',
                body: JSON.stringify({ action })
            });

            if (data.success) {
                // Reload notifications to reflect action taken
                this.loadNotifications();

                // If endpoint is provided, navigate to it
                if (data.endpoint) {
                    if (window.SafeDom) {
                        window.SafeDom.navigate(data.endpoint, { allowSameOrigin: true });
                    } else {
                        window.location.href = data.endpoint;
                    }
                } else {
                    window.showAlert('Action recorded successfully', 'success');
                }
            } else {
                throw new Error(data.error || 'Action failed');
            }
        } catch (error) {
            console.error('Error handling action:', error);
            window.showAlert('Failed to process action. Please try again.', 'error');
        }
    }

    exportNotifications() {
        if (window.showConfirmation) {
            // Use custom dialog for format selection
            window.showConfirmation(
                'Export as CSV? (Click Confirm for CSV, Cancel for JSON)',
                () => this.performExport('csv'),
                () => this.performExport('json'),
                'CSV',
                'JSON',
                'Export Format'
            );
        } else {
            if (window.showConfirmation) {
                window.showConfirmation('Export as CSV? (Click OK for CSV, Cancel for JSON)', () => this.performExport('csv'), () => this.performExport('json'), 'CSV', 'JSON', 'Export Format');
            } else {
                this.performExport('csv');
            }
        }
    }

    performExport(format) {
        const params = new URLSearchParams({ format });

        if (this.filters.date_from) params.append('date_from', this.filters.date_from);
        if (this.filters.date_to) params.append('date_to', this.filters.date_to);
        if (this.filters.type) params.append('type', this.filters.type);
        if (this.filters.category) params.append('category', this.filters.category);
        if (this.filters.tags) params.append('tags', this.filters.tags);
        if (this.filters.search) params.append('search', this.filters.search);

        const url = `/notifications/api/export?${params.toString()}`;
        window.open(url, '_blank');
    }


    showFlashMessage(message, type = 'success') {
        if (typeof window.showFlashMessage === 'function') {
            window.showFlashMessage(message, type);
        }
    }
}

// Initialize notification center when DOM is ready
let notificationCenter;
document.addEventListener('DOMContentLoaded', () => {
    notificationCenter = new NotificationCenter();
    notificationCenter.init();
});
