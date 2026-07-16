// Notification preferences on Account Settings

async function _prefFetch(url, options = {}) {
    const fn = (window.getApiFetch && window.getApiFetch()) || window.apiFetch || fetch;
    if (options.body && !options.headers) options.headers = { 'Content-Type': 'application/json' };
    return fn(url, options);
}

class AccountNotificationPreferences {
    constructor() {
        this.root = document.getElementById('notification-preferences-form');
    }

    init() {
        if (!this.root) return;

        document.getElementById('save-preferences')?.addEventListener('click', () => this.savePreferences());
        document.getElementById('pref-frequency')?.addEventListener('change', (e) => this.toggleDigestSchedule(e.target.value));
        document.getElementById('pref-digest-day')?.addEventListener('change', () => this.updateDigestPreviewFromForm());
        document.getElementById('pref-digest-time')?.addEventListener('change', () => this.updateDigestPreviewFromForm());
        document.getElementById('select-all-email')?.addEventListener('change', (e) => this.toggleSelectAll('email', e.target.checked));
        document.getElementById('select-all-push')?.addEventListener('change', (e) => this.toggleSelectAll('push', e.target.checked));

        this.root.addEventListener('change', (e) => {
            if (e.target.classList.contains('notification-type-email')) {
                this.updateSelectAllState('email');
            } else if (e.target.classList.contains('notification-type-push')) {
                this.updateSelectAllState('push');
            }
        });

        this.loadPreferences();
    }

    async loadPreferences() {
        try {
            const data = await _prefFetch('/notifications/api/preferences');
            if (data.success) {
                this.populatePreferences(data.preferences);
            }
        } catch (error) {
            console.error('Error loading notification preferences:', error);
        }
    }

    populatePreferences(preferences) {
        const soundEl = document.getElementById('pref-sound-enabled');
        if (soundEl) soundEl.checked = preferences.sound_enabled;

        const frequency = preferences.notification_frequency || 'instant';
        const frequencyEl = document.getElementById('pref-frequency');
        if (frequencyEl) frequencyEl.value = frequency;

        this.toggleDigestSchedule(frequency);

        const digestDayEl = document.getElementById('pref-digest-day');
        if (digestDayEl && preferences.digest_day) {
            digestDayEl.value = preferences.digest_day;
        }

        const digestTimeEl = document.getElementById('pref-digest-time');
        if (digestTimeEl) {
            digestTimeEl.value = preferences.digest_time || '09:00';
        }

        const emailEnabledTypes = preferences.notification_types_enabled || [];
        const allEmailEnabled = emailEnabledTypes.length === 0;
        this.root.querySelectorAll('.notification-type-email').forEach((checkbox) => {
            const type = checkbox.getAttribute('data-type');
            checkbox.checked = allEmailEnabled || emailEnabledTypes.includes(type);
        });
        this.updateSelectAllState('email');

        const pushEnabledTypes = preferences.push_notification_types_enabled || [];
        const allPushEnabled = pushEnabledTypes.length === 0;
        this.root.querySelectorAll('.notification-type-push').forEach((checkbox) => {
            const type = checkbox.getAttribute('data-type');
            checkbox.checked = allPushEnabled || pushEnabledTypes.includes(type);
        });
        this.updateSelectAllState('push');

        this.updateDigestPreview(preferences);
    }

    toggleDigestSchedule(frequency) {
        const scheduleGroup = document.getElementById('digest-schedule-group');
        const dayGroup = document.getElementById('digest-day-group');

        if (frequency === 'daily' || frequency === 'weekly') {
            if (scheduleGroup) scheduleGroup.style.display = 'grid';
            if (dayGroup) dayGroup.style.display = frequency === 'weekly' ? 'block' : 'none';
        } else if (scheduleGroup) {
            scheduleGroup.style.display = 'none';
        }

        this.updateDigestPreview({
            notification_frequency: frequency,
            digest_day: document.getElementById('pref-digest-day')?.value,
            digest_time: document.getElementById('pref-digest-time')?.value || '09:00',
        });
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
        this.updateDigestPreview({
            notification_frequency: document.getElementById('pref-frequency')?.value || 'instant',
            digest_day: document.getElementById('pref-digest-day')?.value,
            digest_time: document.getElementById('pref-digest-time')?.value || '09:00',
        });
    }

    toggleSelectAll(type, checked) {
        const selector = type === 'email' ? '.notification-type-email' : '.notification-type-push';
        this.root.querySelectorAll(selector).forEach((checkbox) => {
            checkbox.checked = checked;
        });
    }

    updateSelectAllState(type) {
        const selector = type === 'email' ? '.notification-type-email' : '.notification-type-push';
        const selectAllId = type === 'email' ? 'select-all-email' : 'select-all-push';
        const checkboxes = Array.from(this.root.querySelectorAll(selector));
        const allChecked = checkboxes.length > 0 && checkboxes.every((cb) => cb.checked);
        const selectAllCheckbox = document.getElementById(selectAllId);
        if (selectAllCheckbox) selectAllCheckbox.checked = allChecked;
    }

    async savePreferences() {
        const saveButton = document.getElementById('save-preferences');
        let originalNodes = null;

        if (saveButton) {
            originalNodes = document.createElement('div');
            Array.from(saveButton.childNodes).forEach((node) => {
                originalNodes.appendChild(node.cloneNode(true));
            });
            saveButton.disabled = true;
            saveButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
        }

        const allNotificationTypes = Array.from(this.root.querySelectorAll('.notification-type-email'))
            .map((cb) => cb.getAttribute('data-type'));
        const enabledEmailTypes = Array.from(this.root.querySelectorAll('.notification-type-email:checked'))
            .map((cb) => cb.getAttribute('data-type'));
        const enabledPushTypes = Array.from(this.root.querySelectorAll('.notification-type-push:checked'))
            .map((cb) => cb.getAttribute('data-type'));

        const allEmailSelected = enabledEmailTypes.length === allNotificationTypes.length;
        const allPushSelected = enabledPushTypes.length === allNotificationTypes.length;
        const emailTypesToSend = allEmailSelected ? [] : enabledEmailTypes;
        const pushTypesToSend = allPushSelected ? [] : enabledPushTypes;
        const emailNotifications = allEmailSelected || enabledEmailTypes.length > 0;
        const pushNotifications = allPushSelected || enabledPushTypes.length > 0;

        const frequency = document.getElementById('pref-frequency').value;
        const preferences = {
            email_notifications: emailNotifications,
            sound_enabled: document.getElementById('pref-sound-enabled').checked,
            notification_frequency: frequency,
            notification_types_enabled: emailTypesToSend,
            push_notifications: pushNotifications,
            push_notification_types_enabled: pushTypesToSend,
        };

        if (frequency === 'daily' || frequency === 'weekly') {
            preferences.digest_time = document.getElementById('pref-digest-time').value;
            preferences.digest_day = frequency === 'weekly'
                ? document.getElementById('pref-digest-day').value
                : null;
        } else {
            preferences.digest_day = null;
            preferences.digest_time = null;
        }

        if (!emailNotifications && !pushNotifications) {
            const message = 'You are disabling all email and push notifications. '
                + 'You will not receive any notifications. Are you sure?';
            const restoreButton = () => {
                if (saveButton && originalNodes) {
                    saveButton.disabled = false;
                    saveButton.replaceChildren();
                    Array.from(originalNodes.childNodes).forEach((node) => {
                        saveButton.appendChild(node.cloneNode(true));
                    });
                } else if (saveButton) {
                    saveButton.disabled = false;
                }
            };

            if (window.showDangerConfirmation) {
                return window.showDangerConfirmation(
                    message,
                    () => { void this.savePreferencesInternal(preferences, saveButton, originalNodes); },
                    restoreButton,
                    'Disable All',
                    'Cancel',
                    'Disable All Notifications?'
                );
            }
            if (window.showConfirmation) {
                return window.showConfirmation(
                    message,
                    () => { void this.savePreferencesInternal(preferences, saveButton, originalNodes); },
                    restoreButton,
                    'Disable All',
                    'Cancel',
                    'Disable All Notifications?'
                );
            }
            restoreButton();
            return;
        }

        await this.savePreferencesInternal(preferences, saveButton, originalNodes);
    }

    async savePreferencesInternal(preferences, saveButton, originalNodes) {
        try {
            const data = await _prefFetch('/notifications/api/preferences', {
                method: 'POST',
                body: JSON.stringify(preferences),
            });

            if (data.success) {
                if (typeof window.showFlashMessage === 'function') {
                    window.showFlashMessage('Preferences saved successfully', 'success');
                }
                if (data.preferences) {
                    this.updateDigestPreview(data.preferences);
                    // Keep the sound-preference cache (components.js) in sync so this tab
                    // doesn't act on a stale preference until its TTL expires.
                    try {
                        localStorage.setItem('notification_preferences', JSON.stringify(data.preferences));
                    } catch (e) { /* localStorage unavailable — ignore */ }
                    if (typeof window.forceRefreshNotificationPreferencesCache === 'function') {
                        window.forceRefreshNotificationPreferencesCache();
                    }
                }
            } else {
                throw new Error(data.error || 'Failed to save preferences');
            }
        } catch (error) {
            console.error('Error saving notification preferences:', error);
            let errorMessage = 'Failed to save preferences. ';
            if (error.message.includes('Validation')) {
                errorMessage += 'Please check your settings and try again.';
            } else if (error.message.includes('network') || error.message.includes('fetch')) {
                errorMessage += 'Network error. Please check your connection and try again.';
            } else {
                errorMessage += error.message || 'Please try again.';
            }
            if (typeof window.showFlashMessage === 'function') {
                window.showFlashMessage(errorMessage, 'error');
            }
        } finally {
            if (saveButton && originalNodes) {
                saveButton.disabled = false;
                saveButton.replaceChildren();
                Array.from(originalNodes.childNodes).forEach((node) => {
                    saveButton.appendChild(node.cloneNode(true));
                });
            } else if (saveButton) {
                saveButton.disabled = false;
            }
        }
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const manager = new AccountNotificationPreferences();
    manager.init();
});
