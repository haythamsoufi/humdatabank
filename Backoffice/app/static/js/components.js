// Components JavaScript - Profile popup, Language selector, Notifications

document.addEventListener('DOMContentLoaded', function() {

    // --- Global image error handler (replaces inline onerror for CSP) ---
    // Hide images that opt-in via data-hide-on-error="true"
    window.addEventListener('error', (e) => {
        const target = e.target;
        if (!(target instanceof HTMLImageElement)) return;
        if (target.getAttribute('data-hide-on-error') !== 'true') return;
        target.style.display = 'none';

        // Optional: show next sibling on error (commonly used for initials fallback)
        const display = target.getAttribute('data-show-next-on-error');
        if (display && target.nextElementSibling && target.nextElementSibling instanceof HTMLElement) {
            target.nextElementSibling.style.display = display;
        }
    }, true);

    // --- Global data-action handlers (CSP-safe) ---
    // Generic "toggle next element" helper:
    // <button data-action="ui:toggle-next" aria-controls="id-of-next" aria-expanded="false">...</button>
    if (window.ActionRouter && window.__ActionRouterDefaultsRegistered !== true) {
        window.__ActionRouterDefaultsRegistered = true;

        window.ActionRouter.register('ui:toggle-next', (el, e) => {
            e?.preventDefault?.();
            const next = el.parentElement ? el.parentElement.nextElementSibling : null;
            if (!(next instanceof HTMLElement)) return;

            const willShow = next.classList.contains('hidden');
            next.classList.toggle('hidden', !willShow);
            el.setAttribute('aria-expanded', willShow ? 'true' : 'false');
        });

        // Generic dismiss handler:
        // - <button data-action="ui:dismiss" data-dismiss-target="closest:.alert">X</button>
        // - <button data-action="ui:dismiss" data-dismiss-target="parent">X</button>
        // - <button data-action="ui:dismiss" data-dismiss-target="parent:2">X</button>
        window.ActionRouter.register('ui:dismiss', (el, e) => {
            e?.preventDefault?.();
            const target = el.getAttribute('data-dismiss-target') || 'closest:.alert';
            let node = null;

            if (target.startsWith('closest:')) {
                const selector = target.slice('closest:'.length);
                node = el.closest(selector);
            } else if (target === 'parent') {
                node = el.parentElement;
            } else if (target.startsWith('parent:')) {
                const n = parseInt(target.slice('parent:'.length), 10);
                if (Number.isFinite(n) && n > 0) {
                    node = el;
                    for (let i = 0; i < n; i++) {
                        node = node && node.parentElement;
                    }
                }
            } else if (target.startsWith('#')) {
                node = document.getElementById(target.slice(1));
            }

            if (node && node.parentNode) {
                node.remove();
            }
        });
    }

    // Plugin action handlers must be registered by each plugin itself (via `registerActions(ActionRouter)`).
    // Keep only generic host actions here.
    if (window.ActionRouter) {
        const getFieldId = (el) => el.getAttribute('data-field-id') || '';

        window.ActionRouter.register('plugin-field:reload', (el, e) => {
            e?.preventDefault?.();
            const fieldId = getFieldId(el);
            if (window.pluginFieldLoader && typeof window.pluginFieldLoader.reloadPluginField === 'function' && fieldId) {
                window.pluginFieldLoader.reloadPluginField(fieldId);
            }
        });
    }

    // --- Global confirm-on-submit (replaces inline onclick patterns) ---
    // Supports forms using any of: data-confirm, data-confirm-message, data-confirm-msg, data-confirm-text
    // Use data-confirm-danger="true" for destructive actions (uses showDangerConfirmation)
    // If the user cancels, the submit is prevented.
    document.addEventListener('submit', (e) => {
        const form = e.target;
        if (!(form instanceof HTMLFormElement)) return;

        // Some pages (notably the form builder) attach their own submit handlers
        // for destructive actions (delete/duplicate). Those flows already show a
        // tailored confirmation dialog, so the global confirmation here would
        // result in a double prompt.
        if (
            form.classList.contains('delete-item-form') ||
            form.classList.contains('delete-section-form') ||
            form.classList.contains('duplicate-item-form') ||
            form.classList.contains('duplicate-section-form')
        ) {
            return;
        }

        const msg = (window.getConfirmMessage && window.getConfirmMessage(form)) || null;
        if (!msg) return;

        // Avoid double prompts if something triggers submit twice
        if (form.dataset.confirmed === 'true') return;

        // Check if this is a submit action (for form submission confirmations)
        const submitter = e.submitter;
        const isSubmitAction = submitter && submitter.name === 'action' && submitter.value === 'submit';
        const isDanger = form.hasAttribute('data-confirm-danger') && (form.getAttribute('data-confirm-danger') === 'true' || form.getAttribute('data-confirm-danger') === '');

        // Use custom dialogs if available
        if (isSubmitAction && window.showSubmitConfirmation) {
            e.preventDefault();
            e.stopPropagation();
            window.showSubmitConfirmation(
                msg,
                () => {
                    form.dataset.confirmed = 'true';
                    if (form.requestSubmit && submitter) {
                        form.requestSubmit(submitter);
                    } else {
                        form.submit();
                    }
                },
                () => { /* User cancelled */ }
            );
            return;
        }
        if (isDanger && window.showDangerConfirmation) {
            e.preventDefault();
            e.stopPropagation();
            window.showDangerConfirmation(
                msg,
                () => {
                    form.dataset.confirmed = 'true';
                    if (form.requestSubmit && submitter) {
                        form.requestSubmit(submitter);
                    } else {
                        form.submit();
                    }
                },
                () => { /* User cancelled */ },
                'Delete',
                'Cancel',
                'Confirm Delete'
            );
            return;
        }
        if (window.showConfirmation) {
            e.preventDefault();
            e.stopPropagation();
            window.showConfirmation(
                msg,
                () => {
                    form.dataset.confirmed = 'true';
                    if (form.requestSubmit && submitter) {
                        form.requestSubmit(submitter);
                    } else {
                        form.submit();
                    }
                },
                () => { /* User cancelled */ }
            );
            return;
        }

        // No native confirm fallback: confirm-dialogs.js should provide styled dialogs globally.
        e.preventDefault();
        e.stopPropagation();
        console.warn('Custom confirmation dialog not available:', msg);
        return;
    }, true);

    // --- Profile Popup Logic ---
    const profileIconButton = document.querySelector('.profile-icon-button');
    const profilePopup = document.getElementById('profile-popup');
    if (profileIconButton && profilePopup) {
        profileIconButton.addEventListener('click', (e) => {
            e.stopPropagation();
            const isHidden = profilePopup.classList.contains('hidden');

            // Close other popups if open
            if (languageDropdown && !languageDropdown.classList.contains('hidden')) {
                languageDropdown.classList.add('hidden');
                if (languageSelectorButton) {
                    languageSelectorButton.setAttribute('aria-expanded', 'false');
                    const dropdownArrow = languageSelectorButton.querySelector('.dropdown-arrow');
                    if (dropdownArrow) {
                        dropdownArrow.style.transform = 'rotate(0deg)';
                    }
                }
            }
            if (notificationsDropdown && !notificationsDropdown.classList.contains('hidden')) {
                notificationsDropdown.classList.add('hidden');
            }

            profilePopup.classList.toggle('hidden');
        });
        document.addEventListener('click', (e) => {
            if (!profilePopup.classList.contains('hidden') && !profilePopup.contains(e.target) && !profileIconButton.contains(e.target)) {
                profilePopup.classList.add('hidden');
            }
        });
    }

    // --- Enhanced Language Selector Logic ---
    const languageSelectorButton = document.getElementById('language-selector-button');
    const languageDropdown = document.getElementById('language-dropdown');
    const dropdownArrow = languageSelectorButton?.querySelector('.dropdown-arrow');
    const notificationsDropdown = document.getElementById('notifications-dropdown');

    if (languageSelectorButton && languageDropdown) {
        // Toggle dropdown on button click
        languageSelectorButton.addEventListener('click', (e) => {
            e.stopPropagation();
            const isHidden = languageDropdown.classList.contains('hidden');

            // Close other dropdowns if open
            if (notificationsDropdown && !notificationsDropdown.classList.contains('hidden')) {
                notificationsDropdown.classList.add('hidden');
            }
            if (profilePopup && !profilePopup.classList.contains('hidden')) {
                profilePopup.classList.add('hidden');
            }

            if (isHidden) {
                languageDropdown.classList.remove('hidden');
                languageSelectorButton.setAttribute('aria-expanded', 'true');
                if (dropdownArrow) {
                    dropdownArrow.style.transform = 'rotate(180deg)';
                }
            } else {
                languageDropdown.classList.add('hidden');
                languageSelectorButton.setAttribute('aria-expanded', 'false');
                if (dropdownArrow) {
                    dropdownArrow.style.transform = 'rotate(0deg)';
                }
            }
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', (e) => {
            if (!languageDropdown.classList.contains('hidden') &&
                !languageDropdown.contains(e.target) &&
                !languageSelectorButton.contains(e.target)) {
                languageDropdown.classList.add('hidden');
                languageSelectorButton.setAttribute('aria-expanded', 'false');
                if (dropdownArrow) {
                    dropdownArrow.style.transform = 'rotate(0deg)';
                }
            }
        });

        // Add keyboard navigation
        languageSelectorButton.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                languageSelectorButton.click();
            }
        });

        // Add hover effect for better UX
        languageSelectorButton.addEventListener('mouseenter', () => {
            if (dropdownArrow) {
                dropdownArrow.style.transform = 'rotate(90deg)';
            }
        });

        languageSelectorButton.addEventListener('mouseleave', () => {
            if (dropdownArrow && languageDropdown.classList.contains('hidden')) {
                dropdownArrow.style.transform = 'rotate(0deg)';
            }
        });
    }

    // --- Notifications Bell Logic ---
    const notificationsBellButton = document.getElementById('notifications-bell-button');
    const notificationsList = document.getElementById('notifications-list');
    const notificationsBadge = document.getElementById('notifications-badge');
    const markAllReadBtn = document.getElementById('mark-all-read-btn');
    const _nfetch = (window.getFetch && window.getFetch()) || fetch;

    if (notificationsBellButton && notificationsDropdown) {
        // Toggle dropdown on bell click
        notificationsBellButton.addEventListener('click', (e) => {
            e.stopPropagation();
            const isHidden = notificationsDropdown.classList.contains('hidden');

            // Close other popups if open
            if (profilePopup && !profilePopup.classList.contains('hidden')) {
                profilePopup.classList.add('hidden');
            }
            if (languageDropdown && !languageDropdown.classList.contains('hidden')) {
                languageDropdown.classList.add('hidden');
                if (languageSelectorButton) {
                    languageSelectorButton.setAttribute('aria-expanded', 'false');
                    const dropdownArrow = languageSelectorButton.querySelector('.dropdown-arrow');
                    if (dropdownArrow) {
                        dropdownArrow.style.transform = 'rotate(0deg)';
                    }
                }
            }

            if (isHidden) {
                // Load notifications when opening dropdown
                loadNotifications();
                notificationsDropdown.classList.remove('hidden');
            } else {
                notificationsDropdown.classList.add('hidden');
            }
        });

        // Close dropdown when clicking outside
        document.addEventListener('click', (e) => {
            if (!notificationsDropdown.classList.contains('hidden') &&
                !notificationsDropdown.contains(e.target) &&
                !notificationsBellButton.contains(e.target)) {
                notificationsDropdown.classList.add('hidden');
            }
        });

        // Mark all notifications as read
        if (markAllReadBtn) {
            markAllReadBtn.addEventListener('click', markAllNotificationsRead);
        }
    }

    // Load notifications function with retry
    function loadNotifications(retries = 3) {
        if (!notificationsList) return Promise.resolve();

        // Show loading state
        notificationsList.replaceChildren();
        const loadingDiv = document.createElement('div');
        loadingDiv.className = 'p-4 text-center text-gray-500';
        const loadingSpinner = document.createElement('i');
        loadingSpinner.className = 'fas fa-spinner fa-spin mr-2';
        loadingDiv.appendChild(loadingSpinner);
        loadingDiv.appendChild(document.createTextNode('Loading...'));
        notificationsList.appendChild(loadingDiv);

        // Get CSRF token with validation
        const csrfTokenMeta = document.querySelector('meta[name="csrf-token"]');
        if (!csrfTokenMeta) {
            console.error('CSRF token not found');
            notificationsList.replaceChildren();
            const errorDiv = document.createElement('div');
            errorDiv.className = 'p-4 text-center text-red-500';
            errorDiv.textContent = 'Security error. Please refresh the page.';
            notificationsList.appendChild(errorDiv);
            return Promise.reject(new Error('CSRF token not found'));
        }
        const csrfToken = csrfTokenMeta.getAttribute('content');

        return _nfetch('/notifications/api', {
            method: 'GET',
            headers: {
                'X-CSRFToken': csrfToken,
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'same-origin',
            cache: 'no-cache'
        })
        .then(response => {
            if (!response.ok) {
                throw (window.httpErrorSync && window.httpErrorSync(response)) || new Error(`HTTP ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            // Validate response structure
            if (typeof data !== 'object' || data === null) {
                throw new Error('Invalid response format');
            }

            if (data.success) {
                // Normalize: treat missing or non-array as empty so we never get stuck at "Loading..."
                const list = Array.isArray(data.notifications) ? data.notifications : [];
                displayNotifications(list);
                updateNotificationsBadge(data.unread_count || 0);
            } else {
                throw new Error('API returned success: false');
            }
        })
        .catch(error => {
            // Log detailed error for debugging
            console.error('Error loading notifications:', error.message);

            // Retry mechanism
            if (retries > 0) {
                setTimeout(() => loadNotifications(retries - 1), 2000);
            } else {
                // Show error with retry button
                notificationsList.replaceChildren();
                const errorDiv = document.createElement('div');
                errorDiv.className = 'p-4 text-center';
                const errorP = document.createElement('p');
                errorP.className = 'text-red-500 mb-2';
                errorP.textContent = 'Unable to load notifications';
                const retryBtn = document.createElement('button');
                retryBtn.type = 'button';
                retryBtn.className = 'notifications-retry-btn text-blue-600 hover:underline text-sm';
                const retryIcon = document.createElement('i');
                retryIcon.className = 'fas fa-redo mr-1';
                retryBtn.appendChild(retryIcon);
                retryBtn.appendChild(document.createTextNode('Retry'));
                errorDiv.appendChild(errorP);
                errorDiv.appendChild(retryBtn);
                notificationsList.appendChild(errorDiv);
            }
            throw error;
        });
    }

    // Make loadNotifications available globally for retry button
    window.loadNotifications = loadNotifications;

    // HTML escaping function for security
    function escapeHtml(text) {
        if (typeof text !== 'string') return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Display notifications in dropdown
    function displayNotifications(notifications) {
        if (!notificationsList) return;

        const notificationsFooter = document.getElementById('notifications-footer');

        if (notifications.length === 0) {
            notificationsList.replaceChildren();
            const emptyDiv = document.createElement('div');
            emptyDiv.className = 'p-8 text-center';
            const emptyIcon = document.createElement('i');
            emptyIcon.className = 'fas fa-bell-slash text-gray-400 text-2xl mb-2';
            const emptyP = document.createElement('p');
            emptyP.className = 'text-sm text-gray-500';
            // Use translated message from layout if available
            const emptyMsg = (notificationsList.getAttribute && notificationsList.getAttribute('data-empty-message')) || 'No notifications';
            emptyP.textContent = emptyMsg;
            emptyDiv.appendChild(emptyIcon);
            emptyDiv.appendChild(emptyP);
            notificationsList.appendChild(emptyDiv);
            // Show footer even when there are no notifications
            if (notificationsFooter) {
                notificationsFooter.classList.remove('hidden');
            }
            return;
        }

        // Build notification items using DOM construction
        notificationsList.replaceChildren();

        notifications.forEach(notification => {
            // Validate and sanitize notification data
            const id = parseInt(notification.id);
            if (isNaN(id) || id <= 0) {
                console.warn('Invalid notification ID:', notification.id);
                return;
            }

            const rawTitle = notification.title || 'Notification';
            const rawMessage = notification.message || '';
            const primaryIsMessage = notification.primary_is_message === true;
            let primaryText = rawTitle;
            let secondaryText = rawMessage;
            if (primaryIsMessage) {
                primaryText = rawMessage || rawTitle;
                secondaryText = rawTitle && rawTitle !== primaryText ? rawTitle : '';
            }
            const timeAgo = notification.time_ago || '';
            const iconFull = notification.icon && typeof notification.icon === 'string' ?
                notification.icon.replace(/[^a-zA-Z0-9\-\s]/g, '').trim() : '';
            const actor = notification.actor && typeof notification.actor === 'object' ? notification.actor : null;
            const actionIconSuffix = notification.actor_action_icon && typeof notification.actor_action_icon === 'string'
                ? notification.actor_action_icon.replace(/[^a-zA-Z0-9\-]/g, '')
                : '';
            const actionIconClass = actionIconSuffix
                ? `fas ${actionIconSuffix}`
                : (iconFull && iconFull.length ? iconFull : 'fas fa-bell');
            const relatedUrl = notification.related_url && typeof notification.related_url === 'string' ?
                               notification.related_url : '';
            const priority = notification.priority || 'normal';
            const isUrgent = priority === 'urgent';
            const isHighPriority = priority === 'high' || isUrgent;
            const bgColor = isHighPriority
                ? (!notification.is_read ? (isUrgent ? 'bg-red-50' : 'bg-orange-50') : '')
                : (!notification.is_read ? 'bg-blue-50' : '');
            const stripeColor = !notification.is_read
                ? (isUrgent ? '#dc2626' : isHighPriority ? '#f97316' : '#3b82f6')
                : null;
            const iconColor = notification.is_read ? 'text-gray-500' : (isUrgent ? 'text-red-600' : (isHighPriority ? 'text-orange-600' : 'text-blue-600'));
            const titleColor = notification.is_read ? 'text-gray-700' : (isUrgent ? 'text-red-900' : (isHighPriority ? 'text-orange-900' : 'text-gray-900'));
            const dotColor = isUrgent ? 'bg-red-500' : (isHighPriority ? 'bg-orange-500' : 'bg-blue-500');

            const notificationItem = document.createElement('div');
            notificationItem.className = `notification-item p-3 border-b border-gray-100 hover:bg-sky-100 cursor-pointer transition-colors duration-150 ${bgColor}`;
            if (stripeColor) {
                notificationItem.style.borderLeft = `4px solid ${stripeColor}`;
            }
            notificationItem.setAttribute('data-notification-id', id.toString());
            notificationItem.setAttribute('data-related-url', relatedUrl);
            notificationItem.setAttribute('data-priority', priority || 'normal');

            const mainFlex = document.createElement('div');
            mainFlex.className = 'flex items-start justify-between';

            if (actor && actor.initials) {
                const actorWrap = document.createElement('div');
                actorWrap.className = 'notification-item-actor flex-shrink-0 relative mr-2 mt-0.5';
                const circle = document.createElement('div');
                circle.className = 'notification-item-actor-circle flex items-center justify-center rounded-full text-white text-xs font-semibold';
                circle.style.width = '2.25rem';
                circle.style.height = '2.25rem';
                circle.style.backgroundColor = actor.profile_color || '#64748b';
                circle.textContent = String(actor.initials || '?').slice(0, 2);
                circle.setAttribute('aria-hidden', 'true');
                actorWrap.appendChild(circle);
                if (actionIconSuffix) {
                    const badge = document.createElement('span');
                    badge.className = 'notification-item-actor-badge';
                    const badgeIcon = document.createElement('i');
                    badgeIcon.className = `fas ${actionIconSuffix} notification-item-actor-badge-icon`;
                    badge.appendChild(badgeIcon);
                    actorWrap.appendChild(badge);
                }
                mainFlex.appendChild(actorWrap);
            } else {
                const actionWrap = document.createElement('div');
                actionWrap.className = 'notification-item-actor flex-shrink-0 mr-2 mt-0.5';
                const actionCircle = document.createElement('div');
                actionCircle.className = 'notification-item-action-circle flex items-center justify-center rounded-full';
                actionCircle.style.width = '2.25rem';
                actionCircle.style.height = '2.25rem';
                actionCircle.setAttribute('aria-hidden', 'true');
                const innerIcon = document.createElement('i');
                innerIcon.className = `${actionIconClass} text-sm ${iconColor}`;
                actionCircle.appendChild(innerIcon);
                actionWrap.appendChild(actionCircle);
                mainFlex.appendChild(actionWrap);
            }

            const contentDiv = document.createElement('div');
            contentDiv.className = 'flex-1 min-w-0';

            const headerDiv = document.createElement('div');
            headerDiv.className = 'flex items-center flex-wrap gap-1';

            if (isHighPriority && !notification.is_read) {
                const exclamationIcon = document.createElement('i');
                exclamationIcon.className = `fas fa-exclamation-circle mr-1 text-xs ${isUrgent ? 'text-red-600' : 'text-orange-600'}`;
                headerDiv.appendChild(exclamationIcon);
            }

            const titleH4 = document.createElement('h4');
            titleH4.className = `text-sm font-medium ${titleColor} ${!notification.is_read ? 'font-semibold' : ''}`;
            titleH4.style.color = notification.is_read ? '#4b5563' : (isUrgent ? '#b91c1c' : (isHighPriority ? '#c2410c' : '#111827'));
            titleH4.textContent = primaryText;
            headerDiv.appendChild(titleH4);

            if (isHighPriority) {
                const priorityBadge = document.createElement('span');
                priorityBadge.className = 'ml-1 px-2 py-0.5 text-xs font-bold rounded notification-priority-badge';
                priorityBadge.style.display = 'inline-block';
                priorityBadge.style.fontSize = '9px';
                priorityBadge.style.letterSpacing = '0.5px';
                priorityBadge.style.paddingLeft = '0.5rem';
                priorityBadge.style.paddingRight = '0.5rem';
                if (notification.is_read) {
                    priorityBadge.style.backgroundColor = '#e5e7eb';
                    priorityBadge.style.color = '#6b7280';
                } else {
                    priorityBadge.style.backgroundColor = isUrgent ? '#dc2626' : '#f97316';
                    priorityBadge.style.color = '#ffffff';
                }
                priorityBadge.textContent = (priority || '').toUpperCase();
                headerDiv.appendChild(priorityBadge);
            }

            if (!notification.is_read) {
                const dot = document.createElement('span');
                dot.className = `ml-2 w-2 h-2 ${dotColor} rounded-full`;
                headerDiv.appendChild(dot);
            }

            const messageP = document.createElement('p');
            messageP.className = primaryIsMessage
                ? 'text-xs mt-0.5 notification-message-text leading-snug'
                : 'text-sm mt-1 notification-message-text';
            messageP.style.color = notification.is_read ? '#6b7280' : (isUrgent ? '#991b1b' : (isHighPriority ? '#7c2d12' : '#4b5563'));
            messageP.textContent = secondaryText;

            const metaDiv = document.createElement('div');
            metaDiv.className = 'flex items-center gap-2 mt-1';

            if (notification.entity_name) {
                const entityBadge = document.createElement('span');
                entityBadge.className = 'text-xs inline-flex items-center px-2 py-0.5 rounded notification-entity-badge';
                if (notification.is_read) {
                    entityBadge.style.backgroundColor = '#f3f4f6';
                    entityBadge.style.color = '#6b7280';
                } else {
                    entityBadge.style.backgroundColor = '#f0f9ff';
                    entityBadge.style.color = '#0369a1';
                }
                entityBadge.style.fontWeight = '500';
                const mapIcon = document.createElement('i');
                mapIcon.className = 'fas fa-map-marker-alt mr-1';
                mapIcon.style.fontSize = '0.65rem';
                entityBadge.appendChild(mapIcon);
                entityBadge.appendChild(document.createTextNode(notification.entity_name));
                metaDiv.appendChild(entityBadge);
            }

            const timeSpan = document.createElement('span');
            timeSpan.className = 'text-xs';
            timeSpan.style.color = '#6b7280';
            timeSpan.textContent = timeAgo;
            metaDiv.appendChild(timeSpan);

            contentDiv.appendChild(headerDiv);
            if (secondaryText) {
                contentDiv.appendChild(messageP);
            }
            contentDiv.appendChild(metaDiv);

            mainFlex.appendChild(contentDiv);

            if (!notification.is_read) {
                const markReadBtn = document.createElement('button');
                markReadBtn.type = 'button';
                markReadBtn.setAttribute('data-notification-id', id.toString());
                markReadBtn.className = 'mark-notification-read-btn group ml-2 text-gray-300 hover:text-gray-600 p-1 rounded-full hover:bg-gray-100';
                markReadBtn.setAttribute('title', 'Mark as read');
                const openIcon = document.createElement('i');
                openIcon.className = 'far fa-envelope-open text-xs text-gray-300 group-hover:text-gray-600';
                markReadBtn.appendChild(openIcon);
                markReadBtn.addEventListener('mouseenter', () => { openIcon.classList.replace('far', 'fas'); });
                markReadBtn.addEventListener('mouseleave', () => { openIcon.classList.replace('fas', 'far'); });
                mainFlex.appendChild(markReadBtn);
            } else {
                const markUnreadBtn = document.createElement('button');
                markUnreadBtn.type = 'button';
                markUnreadBtn.setAttribute('data-notification-id', id.toString());
                markUnreadBtn.className = 'mark-notification-unread-btn group ml-2 text-gray-300 hover:text-gray-600 p-1 rounded-full hover:bg-gray-100';
                markUnreadBtn.setAttribute('title', 'Mark as unread');
                const closedIcon = document.createElement('i');
                closedIcon.className = 'far fa-envelope text-xs text-gray-300 group-hover:text-gray-600';
                markUnreadBtn.appendChild(closedIcon);
                markUnreadBtn.addEventListener('mouseenter', () => { closedIcon.classList.replace('far', 'fas'); });
                markUnreadBtn.addEventListener('mouseleave', () => { closedIcon.classList.replace('fas', 'far'); });
                mainFlex.appendChild(markUnreadBtn);
            }

            notificationItem.appendChild(mainFlex);
            notificationsList.appendChild(notificationItem);
        });

        // Ensure footer is visible
        if (notificationsFooter) {
            notificationsFooter.classList.remove('hidden');
        }

        // Show/hide mark all read button
        const hasUnread = notifications.some(n => !n.is_read);
        if (markAllReadBtn) {
            markAllReadBtn.classList.toggle('hidden', !hasUnread);
        }
    }

    // Update notifications badge
    function updateNotificationsBadge(count) {
        if (!notificationsBadge) return;

        if (count > 0) {
            notificationsBadge.textContent = count > 99 ? '99+' : count.toString();
            notificationsBadge.classList.remove('hidden');
        } else {
            notificationsBadge.classList.add('hidden');
        }
    }

    // Handle notification click
    function handleNotificationClick(notificationId, relatedUrl) {
        // Validate notification ID
        const id = parseInt(notificationId);
        if (isNaN(id) || id <= 0) {
            console.error('Invalid notification ID:', notificationId);
            return;
        }

        // Mark as read if not already read
        const notificationElement = document.querySelector(`[data-notification-id="${id}"]`);
        if (notificationElement && (notificationElement.classList.contains('bg-blue-50') ||
                                    notificationElement.classList.contains('bg-red-50') ||
                                    notificationElement.classList.contains('bg-orange-50'))) {
            markNotificationRead(id);
        }

        // Navigate to related URL if available and safe
        if (relatedUrl && typeof relatedUrl === 'string' && relatedUrl !== 'None' && relatedUrl !== '') {
            // Basic URL validation to prevent javascript: or data: URLs
            try {
                const url = new URL(relatedUrl, window.location.origin);
                if (url.origin === window.location.origin && !relatedUrl.toLowerCase().includes('javascript:')) {
                    window.location.href = relatedUrl;
                }
            } catch (error) {
                console.error('Invalid URL:', relatedUrl);
            }
        }

        // Close dropdown
        if (notificationsDropdown) {
            notificationsDropdown.classList.add('hidden');
        }
    }

    // Mark single notification as read
    function markNotificationRead(notificationId) {
        // Validate notification ID
        const id = parseInt(notificationId);
        if (isNaN(id) || id <= 0) {
            console.error('Invalid notification ID:', notificationId);
            return;
        }

        const csrfTokenMeta = document.querySelector('meta[name="csrf-token"]');
        if (!csrfTokenMeta) {
            console.error('CSRF token not found');
            return;
        }
        const csrfToken = csrfTokenMeta.getAttribute('content');

        _nfetch('/notifications/mark-read', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'same-origin',
            body: JSON.stringify({
                notification_ids: [id]
            })
        })
        .then(response => {
            if (!response.ok) {
                throw (window.httpErrorSync && window.httpErrorSync(response)) || new Error(`HTTP ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            // Validate response structure
            if (typeof data !== 'object' || data === null) {
                throw new Error('Invalid response format');
            }

            if (data.success) {
                // Update UI: swap mark-read for mark-unread button
                const notificationElement = document.querySelector(`[data-notification-id="${id}"]`);
                if (notificationElement) {
                    notificationElement.classList.remove('bg-blue-50', 'bg-red-50', 'bg-orange-50');
                    notificationElement.style.borderLeft = '';
                    const unreadDot = notificationElement.querySelector('.bg-blue-500.rounded-full, .bg-orange-500.rounded-full, .bg-red-500.rounded-full');
                    if (unreadDot) unreadDot.remove();
                    const markReadBtn = notificationElement.querySelector('.mark-notification-read-btn');
                    if (markReadBtn) {
                        const markUnreadBtn = document.createElement('button');
                        markUnreadBtn.type = 'button';
                        markUnreadBtn.setAttribute('data-notification-id', id.toString());
                        markUnreadBtn.className = 'mark-notification-unread-btn group ml-2 text-gray-300 hover:text-gray-600 p-1 rounded-full hover:bg-gray-100';
                        markUnreadBtn.setAttribute('title', 'Mark as unread');
                        const closedIcon = document.createElement('i');
                        closedIcon.className = 'far fa-envelope text-xs text-gray-300 group-hover:text-gray-600';
                        markUnreadBtn.appendChild(closedIcon);
                        markUnreadBtn.addEventListener('mouseenter', () => { closedIcon.classList.replace('far', 'fas'); });
                        markUnreadBtn.addEventListener('mouseleave', () => { closedIcon.classList.replace('fas', 'far'); });
                        markReadBtn.replaceWith(markUnreadBtn);
                    }
                    const titleElement = notificationElement.querySelector('h4');
                    if (titleElement) {
                        titleElement.classList.remove('font-semibold');
                        titleElement.style.color = '#4b5563';
                    }
                    const messageEl = notificationElement.querySelector('.notification-message-text');
                    if (messageEl) messageEl.style.color = '#6b7280';
                    const contentArea = notificationElement.querySelector('.flex-1');
                    const headerIcons = contentArea ? contentArea.querySelectorAll('i') : [];
                    headerIcons.forEach(icon => {
                        icon.classList.remove('text-red-600', 'text-orange-600', 'text-blue-600', 'text-red-900', 'text-orange-900');
                        icon.classList.add('text-gray-500');
                    });
                    const priorityBadge = notificationElement.querySelector('.notification-priority-badge');
                    if (priorityBadge) {
                        priorityBadge.style.backgroundColor = '#e5e7eb';
                        priorityBadge.style.color = '#6b7280';
                    }
                    const entityBadge = notificationElement.querySelector('.notification-entity-badge');
                    if (entityBadge) {
                        entityBadge.style.backgroundColor = '#f3f4f6';
                        entityBadge.style.color = '#6b7280';
                    }
                }

                // Update badge count from API response (fixes race condition)
                if (data.unread_count !== undefined) {
                    updateNotificationsBadge(data.unread_count);
                }

                // Hide mark all read button if no more unread
                const hasUnread = document.querySelectorAll('.notification-item.bg-blue-50, .notification-item.bg-red-50, .notification-item.bg-orange-50').length > 0;
                if (markAllReadBtn) {
                    markAllReadBtn.classList.toggle('hidden', !hasUnread);
                }
            }
        })
        .catch(error => {
            console.error('Error marking notification as read:', error.message);
            // Don't expose error details to user
        });
    }

    // Mark single notification as unread
    function markNotificationUnread(notificationId) {
        const id = parseInt(notificationId);
        if (isNaN(id) || id <= 0) {
            console.error('Invalid notification ID:', notificationId);
            return;
        }

        const csrfTokenMeta = document.querySelector('meta[name="csrf-token"]');
        if (!csrfTokenMeta) {
            console.error('CSRF token not found');
            return;
        }
        const csrfToken = csrfTokenMeta.getAttribute('content');

        _nfetch('/notifications/mark-unread', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'same-origin',
            body: JSON.stringify({ notification_ids: [id] })
        })
        .then(response => {
            if (!response.ok) throw (window.httpErrorSync && window.httpErrorSync(response)) || new Error(`HTTP ${response.status}`);
            return response.json();
        })
        .then(data => {
            if (data && data.success) {
                const notificationElement = document.querySelector(`[data-notification-id="${id}"]`);
                if (notificationElement) {
                    const priority = notificationElement.getAttribute('data-priority') || 'normal';
                    const isUrgent = priority === 'urgent';
                    const isHighPriority = priority === 'high' || isUrgent;
                    const bgClass = isHighPriority ? (isUrgent ? 'bg-red-50' : 'bg-orange-50') : 'bg-blue-50';
                    const stripeColor = isUrgent ? '#dc2626' : (isHighPriority ? '#f97316' : '#3b82f6');
                    const dotClass = isUrgent ? 'bg-red-500' : (isHighPriority ? 'bg-orange-500' : 'bg-blue-500');
                    notificationElement.classList.add(bgClass);
                    notificationElement.style.borderLeft = `4px solid ${stripeColor}`;
                    const titleH4 = notificationElement.querySelector('h4');
                    const headerDiv = titleH4 ? titleH4.closest('.flex') : notificationElement.querySelector('.flex');
                    if (headerDiv) {
                        const dot = document.createElement('span');
                        dot.className = `ml-2 w-2 h-2 ${dotClass} rounded-full`;
                        headerDiv.appendChild(dot);
                    }
                    if (titleH4) {
                        titleH4.classList.add('font-semibold');
                        titleH4.style.color = isUrgent ? '#b91c1c' : (isHighPriority ? '#c2410c' : '#111827');
                    }
                    const messageEl = notificationElement.querySelector('.notification-message-text');
                    if (messageEl) {
                        messageEl.style.color = isUrgent ? '#991b1b' : (isHighPriority ? '#7c2d12' : '#4b5563');
                    }
                    const markUnreadBtn = notificationElement.querySelector('.mark-notification-unread-btn');
                    if (markUnreadBtn) {
                        const markReadBtn = document.createElement('button');
                        markReadBtn.type = 'button';
                        markReadBtn.setAttribute('data-notification-id', id.toString());
                        markReadBtn.className = 'mark-notification-read-btn group ml-2 text-gray-300 hover:text-gray-600 p-1 rounded-full hover:bg-gray-100';
                        markReadBtn.setAttribute('title', 'Mark as read');
                        const openIcon = document.createElement('i');
                        openIcon.className = 'far fa-envelope-open text-xs text-gray-300 group-hover:text-gray-600';
                        markReadBtn.appendChild(openIcon);
                        markReadBtn.addEventListener('mouseenter', () => { openIcon.classList.replace('far', 'fas'); });
                        markReadBtn.addEventListener('mouseleave', () => { openIcon.classList.replace('fas', 'far'); });
                        markUnreadBtn.replaceWith(markReadBtn);
                    }
                    const priorityBadge = notificationElement.querySelector('.notification-priority-badge');
                    if (priorityBadge) {
                        priorityBadge.style.backgroundColor = isUrgent ? '#dc2626' : (isHighPriority ? '#f97316' : '#e5e7eb');
                        priorityBadge.style.color = isHighPriority ? '#ffffff' : '#6b7280';
                    }
                    const entityBadge = notificationElement.querySelector('.notification-entity-badge');
                    if (entityBadge) {
                        entityBadge.style.backgroundColor = '#f0f9ff';
                        entityBadge.style.color = '#0369a1';
                    }
                    const contentArea = notificationElement.querySelector('.flex-1');
                    const headerIcons = contentArea ? contentArea.querySelectorAll('i') : [];
                    const iconColorClass = isUrgent ? 'text-red-600' : (isHighPriority ? 'text-orange-600' : 'text-blue-600');
                    headerIcons.forEach(icon => {
                        icon.classList.remove('text-gray-500', 'text-red-600', 'text-orange-600', 'text-blue-600');
                        icon.classList.add(iconColorClass);
                    });
                }
                if (data.unread_count !== undefined) {
                    updateNotificationsBadge(data.unread_count);
                }
                if (markAllReadBtn) {
                    markAllReadBtn.classList.remove('hidden');
                }
            }
        })
        .catch(error => {
            console.error('Error marking notification as unread:', error.message);
        });
    }

    // Mark all notifications as read
    function markAllNotificationsRead() {
        const unreadElements = document.querySelectorAll('.notification-item.bg-blue-50, .notification-item.bg-red-50, .notification-item.bg-orange-50');
        const notificationIds = Array.from(unreadElements).map(el =>
            parseInt(el.getAttribute('data-notification-id'))
        );

        if (notificationIds.length === 0) return;

        const csrfTokenMeta = document.querySelector('meta[name="csrf-token"]');
        if (!csrfTokenMeta) {
            console.error('CSRF token not found');
            return;
        }
        const csrfToken = csrfTokenMeta.getAttribute('content');

        _nfetch('/notifications/mark-read', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'same-origin',
            body: JSON.stringify({
                notification_ids: notificationIds
            })
        })
        .then(response => {
            if (!response.ok) {
                throw (window.httpErrorSync && window.httpErrorSync(response)) || new Error(`HTTP ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (data.success) {
                // Update all unread notifications
                unreadElements.forEach(notificationElement => {
                    notificationElement.classList.remove('bg-blue-50', 'bg-red-50', 'bg-orange-50');
                    notificationElement.style.borderLeft = '';
                    const unreadDot = notificationElement.querySelector('.bg-blue-500.rounded-full, .bg-orange-500.rounded-full, .bg-red-500.rounded-full');
                    if (unreadDot) unreadDot.remove();
                    const markReadBtn = notificationElement.querySelector('.mark-notification-read-btn');
                    if (markReadBtn) {
                        const id = notificationElement.getAttribute('data-notification-id');
                        const markUnreadBtn = document.createElement('button');
                        markUnreadBtn.type = 'button';
                        markUnreadBtn.setAttribute('data-notification-id', id);
                        markUnreadBtn.className = 'mark-notification-unread-btn group ml-2 text-gray-300 hover:text-gray-600 p-1 rounded-full hover:bg-gray-100';
                        markUnreadBtn.setAttribute('title', 'Mark as unread');
                        const closedIcon = document.createElement('i');
                        closedIcon.className = 'far fa-envelope text-xs text-gray-300 group-hover:text-gray-600';
                        markUnreadBtn.appendChild(closedIcon);
                        markUnreadBtn.addEventListener('mouseenter', () => { closedIcon.classList.replace('far', 'fas'); });
                        markUnreadBtn.addEventListener('mouseleave', () => { closedIcon.classList.replace('fas', 'far'); });
                        markReadBtn.replaceWith(markUnreadBtn);
                    }
                    const titleElement = notificationElement.querySelector('h4');
                    if (titleElement) {
                        titleElement.classList.remove('font-semibold');
                        titleElement.style.color = '#4b5563';
                    }
                    const messageEl = notificationElement.querySelector('.notification-message-text');
                    if (messageEl) messageEl.style.color = '#6b7280';
                    const contentArea = notificationElement.querySelector('.flex-1');
                    const headerIcons = contentArea ? contentArea.querySelectorAll('i') : [];
                    headerIcons.forEach(icon => {
                        icon.classList.remove('text-red-600', 'text-orange-600', 'text-blue-600', 'text-red-900', 'text-orange-900');
                        icon.classList.add('text-gray-500');
                    });
                    const priorityBadge = notificationElement.querySelector('.notification-priority-badge');
                    if (priorityBadge) {
                        priorityBadge.style.backgroundColor = '#e5e7eb';
                        priorityBadge.style.color = '#6b7280';
                    }
                    const entityBadge = notificationElement.querySelector('.notification-entity-badge');
                    if (entityBadge) {
                        entityBadge.style.backgroundColor = '#f3f4f6';
                        entityBadge.style.color = '#6b7280';
                    }
                });

                // Update badge and hide mark all button
                if (data.unread_count !== undefined) {
                    updateNotificationsBadge(data.unread_count);
                } else {
                    updateNotificationsBadge(0);
                }
                if (markAllReadBtn) {
                    markAllReadBtn.classList.add('hidden');
                }
            }
        })
        .catch(error => {
            console.error('Error marking all notifications as read:', error);
        });
    }

    // --- Notifications event delegation (no inline onclick) ---
    if (notificationsList) {
        notificationsList.addEventListener('click', (e) => {
            const retryBtn = e.target.closest('.notifications-retry-btn');
            if (retryBtn) {
                e.preventDefault();
                loadNotifications(3);
                return;
            }

            const markReadBtn = e.target.closest('.mark-notification-read-btn');
            if (markReadBtn) {
                e.preventDefault();
                e.stopPropagation();
                const id = markReadBtn.getAttribute('data-notification-id');
                markNotificationRead(id);
                return;
            }

            const markUnreadBtn = e.target.closest('.mark-notification-unread-btn');
            if (markUnreadBtn) {
                e.preventDefault();
                e.stopPropagation();
                const id = markUnreadBtn.getAttribute('data-notification-id');
                markNotificationUnread(id);
                return;
            }

            const item = e.target.closest('.notification-item');
            if (item) {
                const id = item.getAttribute('data-notification-id');
                const relatedUrl = item.getAttribute('data-related-url') || '';
                handleNotificationClick(id, relatedUrl);
            }
        });
    }

    // Track last badge count for sound notification
    let lastBadgeCount = 0;
    let wsConnection = null;
    let reconnectAttempts = 0;
    let reconnectTimeout = null;
    let pingIntervalId = null;
    let stableConnectionTimeoutId = null;
    let pollingInterval = null; // Track polling interval to prevent duplicates
    const MAX_RECONNECT_ATTEMPTS = 10;
    const INITIAL_RECONNECT_DELAY = 1000; // 1 second
    const WS_PING_INTERVAL_MS = 15000; // 15s keeps idle links alive better than 30s

    // Play notification sound
    function playNotificationSound() {
        // Check preferences from localStorage (cached from API)
        const preferences = localStorage.getItem('notification_preferences');
        if (preferences) {
            try {
                const prefs = JSON.parse(preferences);
                if (prefs.sound_enabled) {
                    // Create audio element for notification sound
                    const soundUrl = (window.getStaticUrl && window.getStaticUrl('sounds/notification.mp3')) || '/static/sounds/notification.mp3';
                    const audio = new Audio(soundUrl);
                    audio.volume = 0.5;
                    audio.play().catch(e => console.debug('Sound play failed:', e));
                }
            } catch (e) {
                console.debug('Error parsing preferences:', e);
            }
        }
    }

    // Helper function to handle WebSocket connection errors with reconnection logic
    function handleWSError() {
        console.debug('WebSocket connection error, will attempt to reconnect');
        if (pingIntervalId !== null) {
            clearInterval(pingIntervalId);
            pingIntervalId = null;
        }
        if (stableConnectionTimeoutId !== null) {
            clearTimeout(stableConnectionTimeoutId);
            stableConnectionTimeoutId = null;
        }
        if (wsConnection) {
            wsConnection.close();
            wsConnection = null;
        }

        // Reconnect with exponential backoff
        if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
            const delay = INITIAL_RECONNECT_DELAY * Math.pow(2, reconnectAttempts);
            reconnectAttempts++;

            reconnectTimeout = setTimeout(function() {
                console.debug(`Reconnecting WebSocket (attempt ${reconnectAttempts})...`);
                connectWebSocket();
            }, delay);
        } else {
            console.warn('Max WebSocket reconnection attempts reached, falling back to polling');
            // Fallback to polling if WebSocket fails completely
            fallbackToPolling();
        }
    }

    // Helper function to create WebSocket connection
    function createWebSocketConnection() {
        try {
            // Determine WebSocket URL (ws:// for http, wss:// for https)
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const wsUrl = `${protocol}//${window.location.host}/api/notifications/ws`;

            // Create WebSocket connection
            wsConnection = new WebSocket(wsUrl);

            // Handle connection open
            wsConnection.onopen = function(event) {
                console.debug('WebSocket connection established');
                // Reset reconnect attempts only if the socket survives for a bit.
                // This avoids endless "attempt 1" loops on immediately dropped links.
                if (stableConnectionTimeoutId !== null) {
                    clearTimeout(stableConnectionTimeoutId);
                }
                stableConnectionTimeoutId = setTimeout(() => {
                    reconnectAttempts = 0;
                }, 20000);

                // Clear polling interval since WebSocket is now active
                if (pollingInterval !== null) {
                    clearInterval(pollingInterval);
                    pollingInterval = null;
                }

                // Keep exactly one heartbeat timer active.
                if (pingIntervalId !== null) {
                    clearInterval(pingIntervalId);
                    pingIntervalId = null;
                }
                pingIntervalId = setInterval(() => {
                    if (wsConnection && wsConnection.readyState === WebSocket.OPEN) {
                        wsConnection.send(JSON.stringify({type: 'ping'}));
                    } else {
                        if (pingIntervalId !== null) {
                            clearInterval(pingIntervalId);
                            pingIntervalId = null;
                        }
                    }
                }, WS_PING_INTERVAL_MS);
            };

            // Handle incoming messages
            wsConnection.onmessage = function(event) {
                try {
                    const message = JSON.parse(event.data);

                    // Handle pong (heartbeat response)
                    if (message.type === 'pong') {
                        return; // Just acknowledge, no action needed
                    }

                    // Handle connected message
                    if (message.type === 'connected') {
                        console.debug('WebSocket connection confirmed');
                        // Update badge with initial unread count if provided
                        if (message.data && typeof message.data.unread_count === 'number') {
                            const count = message.data.unread_count;
                            lastBadgeCount = count;
                            updateNotificationsBadge(count);
                        }
                        return;
                    }

                    // Handle notification
                    if (message.type === 'notification' && message.data) {
                        const data = message.data;
                        if (data.type === 'new_notification' && data.notification) {
                            // Play sound if enabled
                            playNotificationSound();

                            // Reload notifications if dropdown is open
                            if (notificationsDropdown && !notificationsDropdown.classList.contains('hidden')) {
                                loadNotifications();
                            } else {
                                // Increment badge count locally (WebSocket will send unread_count update)
                                // This provides immediate feedback while waiting for the count update
                                if (lastBadgeCount >= 0) {
                                    updateNotificationsBadge(lastBadgeCount + 1);
                                    lastBadgeCount += 1;
                                }
                            }
                        }
                        return;
                    }

                    // Handle unread count update
                    if (message.type === 'unread_count' && message.data) {
                        const data = message.data;
                        if (data.type === 'unread_count_update' && typeof data.unread_count === 'number') {
                            const count = data.unread_count;
                            lastBadgeCount = count;
                            updateNotificationsBadge(count);
                        }
                        return;
                    }

                    // Handle error message
                    if (message.type === 'error') {
                        console.warn('WebSocket error message:', message.data);
                        if (message.data && message.data.message && message.data.message.includes('limit exceeded')) {
                            // Connection limit exceeded - fallback to polling
                            console.warn('WebSocket connection limit exceeded, using polling');
                            fallbackToPolling();
                        }
                        return;
                    }
                } catch (e) {
                    console.error('Error handling WebSocket message:', e);
                }
            };

            // Handle connection errors
            wsConnection.onerror = function(error) {
                console.debug('WebSocket connection error:', error);
                // Error handling will be done in onclose
            };

            // Handle connection close
            wsConnection.onclose = function(event) {
                console.debug('WebSocket connection closed', event.code, event.reason);
                if (pingIntervalId !== null) {
                    clearInterval(pingIntervalId);
                    pingIntervalId = null;
                }
                if (stableConnectionTimeoutId !== null) {
                    clearTimeout(stableConnectionTimeoutId);
                    stableConnectionTimeoutId = null;
                }
                wsConnection = null;

                // Check if it was a normal closure or error
                if (event.code !== 1000 && event.code !== 1001) {
                    // Abnormal closure - attempt reconnection
                    handleWSError();
                } else {
                    // Normal closure - don't reconnect
                    console.debug('WebSocket closed normally');
                }
            };
        } catch (e) {
            console.error('Error creating WebSocket connection:', e);
            // Fallback to polling if WebSocket is not supported
            fallbackToPolling();
        }
    }

    // Check WebSocket status once and cache the result permanently if disabled
    function checkWebSocketStatusOnce() {
        // Always check WebSocket status (even if previously disabled)
        // This allows the frontend to pick up configuration changes
        _nfetch('/notifications/api/stream/status')
            .then(response => response.json())
            .then(data => {
                // Server returns { success: true, websocket_enabled: <bool> }
                if (!data?.success || data.websocket_enabled === false) {
                    // WebSocket is disabled - mark it permanently and use polling
                    localStorage.setItem('websocket_permanently_disabled', 'true');
                    fallbackToPolling();
                } else {
                    // WebSocket is enabled - clear any cached disabled state and proceed with connection
                    if (localStorage.getItem('websocket_permanently_disabled') === 'true') {
                        console.debug('WebSocket is now enabled (was previously disabled), clearing cache and connecting...');
                        localStorage.removeItem('websocket_permanently_disabled');
                    } else {
                        console.debug('WebSocket is enabled, connecting...');
                    }
                    connectWebSocket();
                }
            })
            .catch(error => {
                console.debug('Error checking WebSocket status, falling back to polling:', error);
                // On error, check if we have a cached disabled state
                const cachedDisabled = localStorage.getItem('websocket_permanently_disabled') === 'true';
                if (cachedDisabled) {
                    // Use cached disabled state
                    fallbackToPolling();
                } else {
                    // No cache, assume temporary error and don't mark permanently
                    fallbackToPolling();
                }
            });
    }

    // Phase 2: Real-time notifications via WebSocket
    function connectWebSocket() {
        // Close existing connection if any
        if (wsConnection) {
            wsConnection.close();
            wsConnection = null;
        }
        if (pingIntervalId !== null) {
            clearInterval(pingIntervalId);
            pingIntervalId = null;
        }
        if (stableConnectionTimeoutId !== null) {
            clearTimeout(stableConnectionTimeoutId);
            stableConnectionTimeoutId = null;
        }

        // Check if WebSocket is supported
        if (typeof WebSocket === 'undefined') {
            console.warn('WebSocket not supported, using polling');
            fallbackToPolling();
            return;
        }

        // Proceed with WebSocket connection (status was already checked)
        createWebSocketConnection();
    }

    // Fallback to polling if WebSocket is not available
    function fallbackToPolling() {
        // Clear any existing polling interval to prevent duplicates
        if (pollingInterval !== null) {
            clearInterval(pollingInterval);
            pollingInterval = null;
        }
        // Poll for badge count every 120 seconds (reduced frequency to minimize server load)
        pollingInterval = setInterval(updateBadgeCountFromAPI, 120000);
    }

    // Badge update from API (used as fallback and for initial load)
    function updateBadgeCountFromAPI() {
        const csrfTokenMeta = document.querySelector('meta[name="csrf-token"]');
        if (!csrfTokenMeta) {
            console.debug('CSRF token not found');
            return;
        }
        const csrfToken = csrfTokenMeta.getAttribute('content');

        _nfetch('/notifications/api/count', {
            method: 'GET',
            headers: {
                'X-CSRFToken': csrfToken,
                'Content-Type': 'application/json',
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'same-origin',
            cache: 'no-cache'
        })
        .then(response => {
            if (!response.ok) {
                throw (window.httpErrorSync && window.httpErrorSync(response)) || new Error(`HTTP ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            if (typeof data !== 'object' || data === null) {
                throw new Error('Invalid response format');
            }

            if (data.success) {
                const count = parseInt(data.unread_count) || 0;

                // Play sound if count increased (only if not from WebSocket)
                if (count > lastBadgeCount && lastBadgeCount > 0 && !wsConnection) {
                    playNotificationSound();
                }

                lastBadgeCount = count;
                updateNotificationsBadge(count);
            }
        })
        .catch(error => {
            console.debug('Badge update failed:', error.message);
        });
    }

    // Cache notification preferences for sound feature
    function cacheNotificationPreferences() {
        const csrfTokenMeta = document.querySelector('meta[name="csrf-token"]');
        if (!csrfTokenMeta) return;

        _nfetch('/notifications/api/preferences', {
            method: 'GET',
            headers: {
                'X-CSRFToken': csrfTokenMeta.getAttribute('content'),
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success && data.preferences) {
                localStorage.setItem('notification_preferences', JSON.stringify(data.preferences));
            }
        })
        .catch(error => console.debug('Failed to cache preferences:', error));
    }

    // Initial setup
    if (notificationsBellButton) {
        // Check if WebSocket was previously disabled (for initial badge load)
        const websocketPermanentlyDisabled = localStorage.getItem('websocket_permanently_disabled') === 'true';
        if (websocketPermanentlyDisabled) {
            // Load badge count immediately if WebSocket was disabled
            setTimeout(updateBadgeCountFromAPI, 1000);
        }

        // Cache notification preferences for sound feature (only once on page load)
        setTimeout(cacheNotificationPreferences, 2000);

        // Always check WebSocket status (even if previously disabled)
        // This allows picking up configuration changes (e.g., switching from Flask dev server to Waitress)
        if (typeof WebSocket !== 'undefined') {
            // Check WebSocket status - will clear cache if now enabled
            checkWebSocketStatusOnce();
        } else {
            // Browser doesn't support WebSocket, use polling
            console.warn('WebSocket not supported, using polling');
            fallbackToPolling();
        }

        // Expose helper function for debugging WebSocket status
        window.clearWebSocketCache = function() {
            console.log('Clearing WebSocket cache and re-checking status...');
            localStorage.removeItem('websocket_permanently_disabled');
            if (typeof WebSocket !== 'undefined') {
                checkWebSocketStatusOnce();
            } else {
                console.warn('WebSocket not supported in this browser');
            }
        };

        // Cleanup on page unload
        window.addEventListener('beforeunload', function() {
            if (wsConnection) {
                wsConnection.close();
            }
            if (pingIntervalId !== null) {
                clearInterval(pingIntervalId);
            }
            if (stableConnectionTimeoutId !== null) {
                clearTimeout(stableConnectionTimeoutId);
            }
            if (reconnectTimeout) {
                clearTimeout(reconnectTimeout);
            }
            if (pollingInterval !== null) {
                clearInterval(pollingInterval);
            }
        });
    }

    // --- Global Escape-to-close for open popups ---
    document.addEventListener('keydown', (e) => {
        if (e.key !== 'Escape') return;

        if (profilePopup && !profilePopup.classList.contains('hidden')) {
            profilePopup.classList.add('hidden');
        }
        if (languageDropdown && !languageDropdown.classList.contains('hidden')) {
            languageDropdown.classList.add('hidden');
            if (languageSelectorButton) {
                languageSelectorButton.setAttribute('aria-expanded', 'false');
            }
            if (dropdownArrow) {
                dropdownArrow.style.transform = 'rotate(0deg)';
            }
        }
        if (notificationsDropdown && !notificationsDropdown.classList.contains('hidden')) {
            notificationsDropdown.classList.add('hidden');
        }
    });
});
