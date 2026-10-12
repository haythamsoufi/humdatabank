/**
 * Offer to move saved matrix data when column codes are renamed in the item modal.
 *
 * Saved cells are keyed by column code, so renaming "SP1" to "SP1_[assignment_year]"
 * leaves existing data under the old code. Before saving, we ask the server how much
 * data would move and let the user migrate it, save without migrating, or cancel.
 */

const _t = (k) => (typeof window.t === 'function' ? window.t(k) : k);

/** Ask the server what a rename would touch. Resolves to the preview object or null. */
export async function fetchMatrixColumnMigrationPreview(itemId, renames, versionId) {
    if (!itemId || !Array.isArray(renames) || !renames.length) return null;
    const fetchFn = (window.getFetch && window.getFetch()) || fetch;
    const json = JSON.stringify({ renames, version_id: versionId || undefined });
    // Same base64 envelope as the item save, so codes containing [..] pass the WAF.
    const body = JSON.stringify({ payload: btoa(unescape(encodeURIComponent(json))) });
    const resp = await fetchFn(`/admin/items/${encodeURIComponent(itemId)}/matrix-column-rename-preview`, {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/json' },
        body,
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    return data && data.success ? data.preview : null;
}

/** True when the preview has anything to migrate. */
export function hasMigratableData(preview) {
    if (!preview) return false;
    return (preview.rows_affected || 0) > 0 || (preview.variables || []).length > 0;
}

function _el(tag, className, text) {
    const el = document.createElement(tag);
    if (className) el.className = className;
    if (text != null) el.textContent = text;
    return el;
}

/**
 * Show the migration dialog. Resolves to 'migrate' | 'skip' | 'cancel'.
 */
export function confirmMatrixColumnMigration(preview) {
    return new Promise((resolve) => {
        if (typeof window.createModalShell !== 'function') {
            // No dialog available: never migrate silently.
            resolve('skip');
            return;
        }
        let settled = false;
        const finish = (choice) => {
            if (settled) return;
            settled = true;
            resolve(choice);
        };

        const { contentDiv, closeModal } = window.createModalShell(_t('Migrate saved data?'), {
            iconType: 'warning',
            maxWidth: 'lg',
            zIndex: 12000,
            onCancel: () => finish('cancel'),
        });

        const renames = preview.renames || [];
        const intro = _el(
            'p',
            'text-sm text-gray-600',
            renames.length === 1
                ? _t('A column code was changed. Saved data is stored under the old code:')
                : _t('Column codes were changed. Saved data is stored under the old codes:')
        );
        contentDiv.appendChild(intro);

        const list = _el('div', 'text-sm text-gray-800');
        renames.forEach((r) => {
            const line = _el('p', 'font-mono');
            line.textContent = `${r.from}  \u2192  ${r.to}`;
            list.appendChild(line);
        });
        contentDiv.appendChild(list);

        const facts = [];
        if (preview.cells > 0) {
            facts.push(
                `${preview.cells} ${_t('saved cell(s)')} ${_t('in')} ${preview.assignments} ${_t('assignment(s)')}`
            );
        }
        if ((preview.variables || []).length) {
            facts.push(`${preview.variables.length} ${_t('template variable(s) that look up this column')}`);
        }
        const summary = _el('div', 'bg-yellow-50 border-l-4 border-yellow-400 p-4');
        summary.appendChild(_el('p', 'text-sm text-yellow-700', facts.join('; ') + '.'));
        if (preview.conflicts > 0) {
            summary.appendChild(_el(
                'p',
                'text-sm text-yellow-700',
                `${preview.conflicts} ${_t('cell(s) already have a value under the new code and will be left as they are.')}`
            ));
        }
        if (preview.skipped_unresolved > 0) {
            summary.appendChild(_el(
                'p',
                'text-sm text-yellow-700',
                `${preview.skipped_unresolved} ${_t('submission(s) cannot be matched to a variable value and will be skipped.')}`
            ));
        }
        contentDiv.appendChild(summary);

        contentDiv.appendChild(_el(
            'p',
            'text-sm text-gray-600',
            _t('Migrate moves this data and updates the references to the new code. Without it, existing data stays under the old code and will no longer show in the form.')
        ));

        const buttons = _el('div', 'flex justify-end space-x-3');
        const cancelBtn = _el('button', 'btn btn-secondary', _t('Cancel'));
        cancelBtn.type = 'button';
        const skipBtn = _el('button', 'btn btn-secondary', _t('Save without migrating'));
        skipBtn.type = 'button';
        const migrateBtn = _el('button', 'btn btn-success', _t('Migrate and save'));
        migrateBtn.type = 'button';
        buttons.appendChild(cancelBtn);
        buttons.appendChild(skipBtn);
        buttons.appendChild(migrateBtn);
        contentDiv.appendChild(buttons);

        const choose = (choice) => (e) => {
            e.preventDefault();
            e.stopPropagation();
            closeModal();
            finish(choice);
        };
        cancelBtn.addEventListener('click', choose('cancel'));
        skipBtn.addEventListener('click', choose('skip'));
        migrateBtn.addEventListener('click', choose('migrate'));
        setTimeout(() => migrateBtn.focus(), 100);
    });
}
