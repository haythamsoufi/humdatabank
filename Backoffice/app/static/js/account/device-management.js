/**
 * Account Settings — registered device remove / kickout actions.
 * Uses apiFetch/responseAsResult for safe JSON handling behind AppGW/WAF.
 */
(function () {
    'use strict';

    function getCsrfToken() {
        return document.querySelector('input[name="csrf_token"]')?.value
            || document.querySelector('meta[name="csrf-token"]')?.getAttribute('content')
            || '';
    }

    async function deviceApiJson(url, options = {}) {
        const apiFn = (window.getApiFetch && window.getApiFetch()) || window.apiFetch;
        const headers = Object.assign({
            'Content-Type': 'application/json',
            'X-CSRFToken': getCsrfToken(),
        }, options.headers || {});
        const opts = Object.assign({}, options, { headers, credentials: 'same-origin' });

        if (apiFn) {
            return apiFn(url, opts);
        }

        const fetchFn = (window.getFetch && window.getFetch()) || fetch;
        const response = await fetchFn(url, opts);
        if (window.responseAsResult) {
            const result = await window.responseAsResult(response);
            if (!result.ok) {
                throw new Error(result.data?.error || `HTTP ${result.status}`);
            }
            return result.data;
        }
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }
        const ct = response.headers.get('Content-Type') || '';
        if (!ct.includes('application/json')) {
            throw new Error(`HTTP ${response.status}: non-JSON response`);
        }
        return response.json();
    }

    function attachRemoveDeviceListener(button) {
        if (!button) return;

        button.addEventListener('click', async function () {
            const deviceId = this.getAttribute('data-device-id');
            if (!deviceId) {
                if (window.showAlert) window.showAlert('Error: Missing device information.', 'error');
                return;
            }

            const msg = 'Are you sure you want to remove this device from the registry? This will permanently delete the device record and you will need to register again to receive push notifications on this device.';
            const btn = this;

            const doRemove = async () => {
                const originalContent = btn.innerHTML;
                btn.disabled = true;
                btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-1.5"></i>Removing...';

                try {
                    const data = await deviceApiJson(`/auth/account-settings/devices/${deviceId}/remove`, {
                        method: 'DELETE',
                    });

                    if (!data || !data.success) {
                        throw new Error((data && data.error) || 'Failed to remove device');
                    }

                    const row = btn.closest('tr');
                    row.style.transition = 'opacity 0.3s ease-out';
                    row.style.opacity = '0';

                    setTimeout(() => {
                        row.remove();
                        const tbody = document.querySelector('tbody');
                        if (tbody && tbody.children.length === 0) {
                            location.reload();
                        }
                    }, 300);

                    const successMsg = document.createElement('div');
                    successMsg.className = 'fixed top-4 right-4 bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded shadow-lg z-50';
                    successMsg.innerHTML = '<i class="fas fa-check-circle mr-2"></i>Device removed successfully.';
                    document.body.appendChild(successMsg);
                    setTimeout(() => successMsg.remove(), 3000);
                } catch (error) {
                    console.error('Error removing device:', error);
                    btn.disabled = false;
                    btn.innerHTML = originalContent;
                    if (window.showAlert) {
                        window.showAlert('Error: ' + (error.message || 'Failed to remove device. Please try again.'), 'error');
                    }
                }
            };

            if (window.showDangerConfirmation) {
                window.showDangerConfirmation(msg, () => { void doRemove(); }, null, 'Remove', 'Cancel', 'Remove Device?');
            } else if (window.confirm(msg)) {
                void doRemove();
            }
        });
    }

    function attachKickoutDeviceListener(button) {
        if (!button) return;

        button.addEventListener('click', async function () {
            const deviceId = this.getAttribute('data-device-id');
            if (!deviceId) {
                if (window.showAlert) window.showAlert('Error: Missing device information.', 'error');
                return;
            }

            const msg = 'Are you sure you want to end this device\'s session? You will be logged out on this device, but the device will remain registered.';
            const btn = this;

            const doKickout = async () => {
                const originalContent = btn.innerHTML;
                btn.disabled = true;
                btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-1.5"></i>Ending Session...';

                try {
                    const data = await deviceApiJson(`/auth/account-settings/devices/${deviceId}/kickout`, {
                        method: 'POST',
                    });

                    if (!data || !data.success) {
                        throw new Error((data && data.error) || 'Failed to end device session');
                    }

                    const row = btn.closest('tr');
                    const statusCell = row.querySelector('td:nth-last-child(2)');
                    if (statusCell) {
                        const now = new Date();
                        const formattedDate = window.DateTimeUtils
                            ? window.DateTimeUtils.format(now, 'datetime')
                            : now.toLocaleString();
                        const escHtml = window.escapeHtml || function (v) {
                            const d = document.createElement('div');
                            d.textContent = String(v == null ? '' : v);
                            return d.innerHTML;
                        };

                        statusCell.innerHTML = `
                            ${(window.StatusLabels && StatusLabels.render('Logged Out', 'danger')) || '<span class="status-label status-label--danger">Logged Out</span>'}
                            <div class="text-xs text-gray-500 mt-1">${escHtml(formattedDate)}</div>
                        `;
                    }

                    const actionsCell = row.querySelector('td:last-child');
                    if (actionsCell) {
                        const removeBtn = actionsCell.querySelector('.remove-device-btn');
                        if (removeBtn) {
                            const deviceIdAttr = removeBtn.getAttribute('data-device-id');
                            const escAttr = window.escapeHtmlAttr || function (v) {
                                return String(v == null ? '' : v)
                                    .replace(/&/g, '&amp;').replace(/\\/g, '\\\\').replace(/"/g, '&quot;')
                                    .replace(/'/g, '&#39;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
                            };
                            actionsCell.innerHTML = `
                                <div class="flex items-center space-x-2">
                                    <button type="button"
                                            class="remove-device-btn inline-flex items-center px-3 py-1.5 border border-gray-300 shadow-sm text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500 disabled:opacity-50 disabled:cursor-not-allowed"
                                            data-device-id="${escAttr(deviceIdAttr)}"
                                            title="Remove this device from registry">
                                        <i class="fas fa-trash mr-1.5"></i>
                                        Remove
                                    </button>
                                </div>
                            `;
                            attachRemoveDeviceListener(actionsCell.querySelector('.remove-device-btn'));
                        }
                    }

                    row.classList.remove('hover:bg-gray-50');
                    row.classList.add('bg-gray-50', 'hover:bg-gray-100');

                    const successMsg = document.createElement('div');
                    successMsg.className = 'fixed top-4 right-4 bg-green-100 border border-green-400 text-green-700 px-4 py-3 rounded shadow-lg z-50';
                    successMsg.innerHTML = '<i class="fas fa-check-circle mr-2"></i>Device session ended successfully.';
                    document.body.appendChild(successMsg);
                    setTimeout(() => successMsg.remove(), 3000);
                } catch (error) {
                    console.error('Error ending device session:', error);
                    btn.disabled = false;
                    btn.innerHTML = originalContent;
                    if (window.showAlert) {
                        window.showAlert('Error: ' + (error.message || 'Failed to end device session. Please try again.'), 'error');
                    }
                }
            };

            if (window.showConfirmation) {
                window.showConfirmation(msg, () => { void doKickout(); }, null, 'End Session', 'Cancel', 'End Device Session?');
            } else {
                void doKickout();
            }
        });
    }

    function initAccountDeviceManagement() {
        document.querySelectorAll('.kickout-device-btn').forEach(attachKickoutDeviceListener);
        document.querySelectorAll('.remove-device-btn').forEach(attachRemoveDeviceListener);
    }

    window.initAccountDeviceManagement = initAccountDeviceManagement;
})();
