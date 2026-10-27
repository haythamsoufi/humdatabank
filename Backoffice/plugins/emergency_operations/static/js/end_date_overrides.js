/**
 * Emergency Operations — tentative end-date overrides settings tab.
 */
(function (window, document) {
  'use strict';

  const API = '/admin/plugins/emergency_operations/api/end-date-overrides';
  let loaded = false;

  function csrfHeaders() {
    const token =
      document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') ||
      document.querySelector('input[name="csrf_token"]')?.value ||
      '';
    const headers = { 'Content-Type': 'application/json', Accept: 'application/json' };
    if (token) headers['X-CSRFToken'] = token;
    return headers;
  }

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function showFormMsg(text, isError) {
    const el = document.getElementById('eo-override-form-msg');
    if (!el) return;
    el.textContent = text || '';
    el.classList.toggle('hidden', !text);
    el.classList.toggle('text-red-600', !!isError);
    el.classList.toggle('text-green-700', !isError && !!text);
  }

  function syncBadge(row) {
    const status = row.sync_status || 'pending';
    if (status === 'matched') {
      return (
        '<span class="inline-flex items-center gap-1.5 text-green-700" title="Source end date matches override — safe to remove">' +
        '<i class="fas fa-check-circle" aria-hidden="true"></i><span>Matched</span></span>'
      );
    }
    if (status === 'source_ahead') {
      return (
        '<span class="inline-flex items-center gap-1.5 text-green-700" title="Source end date is on or after the override — safe to remove">' +
        '<i class="fas fa-check-circle" aria-hidden="true"></i><span>Source ahead</span></span>'
      );
    }
    if (status === 'missing_source') {
      return (
        '<span class="inline-flex items-center gap-1.5 text-amber-700" title="Appeal not found in current cache">' +
        '<i class="fas fa-question-circle" aria-hidden="true"></i><span>Not in cache</span></span>'
      );
    }
    return (
      '<span class="inline-flex items-center gap-1.5 text-gray-500" title="ERP end date is still earlier than the tentative override">' +
      '<i class="fas fa-clock" aria-hidden="true"></i><span>Pending</span></span>'
    );
  }

  function formatUpdated(row) {
    const when = row.updated_at ? String(row.updated_at).replace('T', ' ').slice(0, 16) : '—';
    const by = row.updated_by ? ` · ${row.updated_by}` : '';
    return esc(when + by);
  }

  function renderRows(rows) {
    const empty = document.getElementById('eo-overrides-empty');
    const wrap = document.getElementById('eo-overrides-table-wrap');
    const tbody = document.getElementById('eo-overrides-tbody');
    if (!empty || !wrap || !tbody) return;

    if (!rows.length) {
      empty.classList.remove('hidden');
      wrap.classList.add('hidden');
      tbody.innerHTML = '';
      return;
    }

    empty.classList.add('hidden');
    wrap.classList.remove('hidden');
    tbody.innerHTML = rows
      .map(function (row) {
        const canRemoveHint = row.can_remove
          ? 'Remove (source caught up)'
          : 'Remove anyway (source not yet matching)';
        return (
          '<tr data-code="' +
          esc(row.code) +
          '">' +
          '<td class="px-3 py-2 font-mono font-medium text-gray-900">' +
          esc(row.code) +
          '</td>' +
          '<td class="px-3 py-2">' +
          esc(row.end_date || '—') +
          '</td>' +
          '<td class="px-3 py-2 text-gray-600">' +
          esc(row.source_end_date || '—') +
          '</td>' +
          '<td class="px-3 py-2">' +
          syncBadge(row) +
          '</td>' +
          '<td class="px-3 py-2 text-gray-600 max-w-xs truncate" title="' +
          esc(row.note || '') +
          '">' +
          esc(row.note || '—') +
          '</td>' +
          '<td class="px-3 py-2 text-gray-500 whitespace-nowrap">' +
          formatUpdated(row) +
          '</td>' +
          '<td class="px-3 py-2 text-right">' +
          '<button type="button" class="eo-override-delete inline-flex items-center gap-1 px-2 py-1 text-xs font-medium rounded border ' +
          (row.can_remove
            ? 'text-green-800 border-green-300 bg-green-50 hover:bg-green-100'
            : 'text-red-700 border-red-200 bg-white hover:bg-red-50') +
          '" data-code="' +
          esc(row.code) +
          '" title="' +
          esc(canRemoveHint) +
          '">' +
          '<i class="fas fa-trash-alt"></i> Delete' +
          '</button>' +
          '</td>' +
          '</tr>'
        );
      })
      .join('');
  }

  function setReloadSpinning(on) {
    const icon = document.getElementById('eo-overrides-reload-icon');
    if (icon) icon.classList.toggle('fa-spin', !!on);
  }

  function loadOverrides() {
    setReloadSpinning(true);
    return fetch(API, { credentials: 'same-origin', headers: { Accept: 'application/json' } })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (!data || !data.success) {
          throw new Error((data && (data.error || data.message)) || 'Failed to load overrides');
        }
        renderRows(data.overrides || []);
        loaded = true;
      })
      .catch(function (err) {
        showFormMsg(err.message || String(err), true);
      })
      .finally(function () {
        setReloadSpinning(false);
      });
  }

  function saveOverride(event) {
    event.preventDefault();
    const code = (document.getElementById('eo-override-code')?.value || '').trim().toUpperCase();
    const endDate = document.getElementById('eo-override-end-date')?.value || '';
    const note = (document.getElementById('eo-override-note')?.value || '').trim();
    if (!code || !endDate) {
      showFormMsg('Appeal code and end date are required.', true);
      return;
    }
    const btn = document.getElementById('eo-override-save-btn');
    if (btn) btn.disabled = true;
    showFormMsg('');
    fetch(API, {
      method: 'POST',
      credentials: 'same-origin',
      headers: csrfHeaders(),
      body: JSON.stringify({ code: code, end_date: endDate, note: note }),
    })
      .then(function (r) {
        return r.json().then(function (data) {
          return { ok: r.ok, data: data };
        });
      })
      .then(function (res) {
        if (!res.ok || !res.data || !res.data.success) {
          throw new Error((res.data && (res.data.error || res.data.message)) || 'Save failed');
        }
        showFormMsg('Saved override for ' + code, false);
        const form = document.getElementById('eo-override-form');
        if (form) form.reset();
        return loadOverrides();
      })
      .catch(function (err) {
        showFormMsg(err.message || String(err), true);
      })
      .finally(function () {
        if (btn) btn.disabled = false;
      });
  }

  function deleteOverride(code) {
    if (!code) return;
    if (!window.confirm('Remove tentative end date for ' + code + '?')) return;
    fetch(API + '/' + encodeURIComponent(code), {
      method: 'DELETE',
      credentials: 'same-origin',
      headers: csrfHeaders(),
    })
      .then(function (r) {
        return r.json().then(function (data) {
          return { ok: r.ok, data: data };
        });
      })
      .then(function (res) {
        if (!res.ok || !res.data || !res.data.success) {
          throw new Error((res.data && (res.data.error || res.data.message)) || 'Delete failed');
        }
        showFormMsg('Removed override for ' + code, false);
        return loadOverrides();
      })
      .catch(function (err) {
        showFormMsg(err.message || String(err), true);
      });
  }

  function init() {
    document.getElementById('eo-override-form')?.addEventListener('submit', saveOverride);
    document.getElementById('eo-overrides-reload-btn')?.addEventListener('click', loadOverrides);
    document.getElementById('eo-overrides-tbody')?.addEventListener('click', function (ev) {
      const btn = ev.target.closest('.eo-override-delete');
      if (!btn) return;
      deleteOverride(btn.getAttribute('data-code'));
    });
    const codeInput = document.getElementById('eo-override-code');
    if (codeInput) {
      codeInput.addEventListener('input', function () {
        codeInput.value = codeInput.value.toUpperCase();
      });
    }
  }

  function onTabShown() {
    if (!loaded) loadOverrides();
    else loadOverrides();
  }

  window.EoEndDateOverrides = {
    init: init,
    onTabShown: onTabShown,
    reload: loadOverrides,
  };
})(window, document);
