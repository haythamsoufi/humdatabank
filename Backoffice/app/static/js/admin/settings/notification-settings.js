/**
 * Notifications tab — AG Grid for delivery audience / priority settings.
 */
import { getSettingsPageConfig } from './common.js';

function escHtml(value) {
  if (window.AgGridRenderers && typeof AgGridRenderers.escapeHtml === 'function') {
    return AgGridRenderers.escapeHtml(value == null ? '' : String(value));
  }
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/"/g, '&quot;');
}

function escAttr(value) {
  if (window.escapeHtmlAttr) return window.escapeHtmlAttr(value);
  return String(value == null ? '' : value)
    .replace(/&/g, '&amp;')
    .replace(/\\/g, '\\\\')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function setupNotificationSettingsGrid(cfg) {
  const jsonEl = document.getElementById('notification-settings-grid-rows');
  const gridEl = document.getElementById('notificationSettingsGrid');
  if (!jsonEl || !gridEl || typeof AgGridHelper === 'undefined' || !AgGridHelper.createTabAware) return;

  let rows = [];
  try {
    rows = JSON.parse(jsonEl.textContent || '[]');
  } catch (_) {
    return;
  }

  const priorityLabels = {
    normal: cfg.t.priorityNormal,
    high: cfg.t.priorityHigh,
    urgent: cfg.t.priorityUrgent,
    low: cfg.t.priorityLow,
  };
  const audienceNaTitle = cfg.t.audienceNaTitle;

  function fitNotificationColumnsIfVisible(api) {
    if (!api || typeof api.sizeColumnsToFit !== 'function' || !gridEl) return;
    const width = gridEl.clientWidth || gridEl.getBoundingClientRect().width;
    if (width < 200) return;
    try {
      api.sizeColumnsToFit();
    } catch (_) {}
  }

  function audienceCheckbox(prefix, audienceKey, propKey, titleStr) {
    return function audienceCheckboxRenderer(params) {
      const audiences = params.data.audiences || [];
      if (audiences.indexOf(audienceKey) === -1) {
        return (
          '<label class="inline-flex items-center justify-center cursor-default pointer-events-none opacity-70" title="' +
          escAttr(audienceNaTitle) +
          '">' +
          '<input type="checkbox" disabled tabindex="-1" ' +
          'class="rounded border-gray-200 bg-gray-50 text-gray-300 cursor-not-allowed opacity-80" ' +
          'aria-label="' +
          escAttr(audienceNaTitle) +
          '" /></label>'
        );
      }
      const typeKey = params.data.type_key;
      const checked = params.data[propKey] ? ' checked' : '';
      return (
        '<label class="inline-flex items-center justify-center cursor-pointer" title="' +
        escAttr(titleStr) +
        '">' +
        '<input type="checkbox" class="rounded border-gray-300 text-blue-600 focus:ring-blue-500" name="' +
        prefix +
        typeKey +
        '" value="1"' +
        checked +
        ' /></label>'
      );
    };
  }

  function prioritySelect(params) {
    const typeKey = params.data.type_key;
    const current = (params.data.current_priority || 'normal').toLowerCase();
    function opt(val, label) {
      const selected = current === val ? ' selected' : '';
      return '<option value="' + escAttr(val) + '"' + selected + '>' + escHtml(label) + '</option>';
    }
    return (
      '<select name="notification_priority_' +
      typeKey +
      '" class="w-full min-w-[7.5rem] rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 text-sm capitalize">' +
      opt('normal', priorityLabels.normal) +
      opt('high', priorityLabels.high) +
      opt('urgent', priorityLabels.urgent) +
      opt('low', priorityLabels.low) +
      '</select>'
    );
  }

  function typeCell(params) {
    const data = params.data || {};
    const iconClass = escAttr(data.icon_class || '');
    const isHypothetical = data.emitter_active === false || data.emitter_active === 0;
    let hypotheticalHtml = '';
    if (isHypothetical) {
      hypotheticalHtml =
        '<span class="mt-1 inline-flex w-fit rounded-full border border-slate-300 bg-slate-50 px-2 py-0.5 text-[11px] font-semibold text-slate-700" title="' +
        escAttr(data.emitter_status_hint || '') +
        '">' +
        escHtml(data.emitter_status_display || '') +
        '</span>';
    }
    return (
      '<div class="flex items-start gap-2">' +
      '<span class="inline-flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full bg-gray-100 text-gray-600" aria-hidden="true">' +
      '<i class="' +
      iconClass +
      ' text-xs"></i></span>' +
      '<div class="min-w-0">' +
      '<div class="font-medium text-gray-900">' +
      escHtml(data.label) +
      '</div>' +
      '<div class="font-mono text-[11px] text-gray-500 break-all">' +
      escHtml(data.type_key) +
      '</div>' +
      hypotheticalHtml +
      '</div></div>'
    );
  }

  const columnDefs = [
    {
      field: 'group_display',
      headerName: cfg.t.colGroup,
      flex: 0.55,
      minWidth: 96,
      maxWidth: 200,
      filter: 'agTextColumnFilter',
      sortable: true,
      wrapHeaderText: true,
      autoHeaderHeight: true,
    },
    {
      field: 'label',
      headerName: cfg.t.colType,
      flex: 0.85,
      minWidth: 168,
      maxWidth: 340,
      filter: 'agTextColumnFilter',
      sortable: true,
      cellRenderer: typeCell,
      autoHeight: true,
      wrapHeaderText: true,
      autoHeaderHeight: true,
      cellStyle: { 'white-space': 'normal', 'line-height': '1.4', 'align-items': 'flex-start' },
    },
    {
      field: 'recipients_display',
      headerName: cfg.t.colRecipients,
      flex: 3.5,
      minWidth: 280,
      filter: 'agTextColumnFilter',
      sortable: true,
      wrapText: true,
      autoHeight: true,
      wrapHeaderText: true,
      autoHeaderHeight: true,
      cellStyle: { 'white-space': 'normal', 'line-height': '1.4', 'font-size': '12px', color: '#374151' },
    },
    {
      field: 'audience_focal_points',
      headerName: cfg.t.colFocalPoints,
      width: 128,
      minWidth: 118,
      maxWidth: 152,
      sortable: false,
      filter: false,
      wrapHeaderText: true,
      autoHeaderHeight: true,
      cellRenderer: audienceCheckbox('na_fp_', 'focal_points', 'audience_focal_points', cfg.t.notifyFocalPoints),
      cellStyle: { display: 'flex', 'align-items': 'center', 'justify-content': 'center' },
    },
    {
      field: 'audience_admin_users',
      headerName: cfg.t.colOrgAdmins,
      width: 108,
      minWidth: 96,
      maxWidth: 132,
      sortable: false,
      filter: false,
      wrapHeaderText: true,
      autoHeaderHeight: true,
      cellRenderer: audienceCheckbox('na_au_', 'admin_users', 'audience_admin_users', cfg.t.notifyOrgAdmins),
      cellStyle: { display: 'flex', 'align-items': 'center', 'justify-content': 'center' },
    },
    {
      field: 'audience_system_managers',
      headerName: cfg.t.colSystemManagers,
      width: 116,
      minWidth: 100,
      maxWidth: 140,
      sortable: false,
      filter: false,
      wrapHeaderText: true,
      autoHeaderHeight: true,
      cellRenderer: audienceCheckbox('na_sm_', 'system_managers', 'audience_system_managers', cfg.t.notifySystemManagers),
      cellStyle: { display: 'flex', 'align-items': 'center', 'justify-content': 'center' },
    },
    {
      field: 'ttl_days',
      headerName: cfg.t.colTtl,
      width: 84,
      minWidth: 72,
      maxWidth: 104,
      filter: 'agNumberColumnFilter',
      sortable: true,
      wrapHeaderText: true,
      autoHeaderHeight: true,
      cellStyle: { 'text-align': 'center', fontFamily: 'ui-monospace, monospace', fontSize: '12px' },
    },
    {
      field: 'current_priority',
      headerName: cfg.t.colPriority,
      width: 136,
      minWidth: 124,
      maxWidth: 168,
      sortable: false,
      filter: false,
      wrapHeaderText: true,
      autoHeaderHeight: true,
      cellRenderer: prioritySelect,
    },
  ];

  const gridResult = AgGridHelper.createTabAware(
    'notificationSettingsGrid',
    'system-notification-settings',
    columnDefs,
    rows,
    {
      columnVisibility: { enableExport: false, showPanelButton: false, persistOnChange: false },
      autoDetectFilters: false,
      gridOptions: {
        suppressRowVirtualisation: true,
        suppressColumnVirtualisation: true,
        animateRows: false,
        domLayout: 'normal',
        sizeColumnsToFitOnInit: false,
        getRowClass(params) {
          const row = params.data;
          if (!row || row.emitter_active !== false) return '';
          return 'notification-settings-grid-row-hypothetical';
        },
      },
      onReady(api) {
        window.__notificationSettingsGridApi = api;
        try {
          if (api && typeof api.applyColumnState === 'function') {
            const columnOrder = [
              'group_display',
              'label',
              'recipients_display',
              'audience_focal_points',
              'audience_admin_users',
              'audience_system_managers',
              'ttl_days',
              'current_priority',
            ];
            api.applyColumnState({
              state: columnOrder.map((colId) => ({ colId })),
              applyOrder: true,
            });
          }
        } catch (_) {}
        setTimeout(() => fitNotificationColumnsIfVisible(api), 50);
      },
    },
    {
      eventName: 'settings-tab-activated',
      tabId: 'notifications',
      onTabActivated(api) {
        window.__notificationSettingsGridApi = api;
        setTimeout(() => fitNotificationColumnsIfVisible(api), 80);
      },
    },
  );

  if (gridResult && gridResult.api) {
    window.__notificationSettingsGridApi = gridResult.api;
  }
}

function bootstrapNotificationSettingsGrid(cfg) {
  if (typeof AgGridHelper === 'undefined' || !AgGridHelper.createTabAware) return;
  setupNotificationSettingsGrid(cfg);
  const hash = (location.hash || '').replace('#', '');
  if (hash === 'notifications' && window.__notificationSettingsGridApi) {
    const api = window.__notificationSettingsGridApi;
    const gridEl = document.getElementById('notificationSettingsGrid');
    setTimeout(() => {
      if (!gridEl || (gridEl.clientWidth || gridEl.getBoundingClientRect().width) < 200) return;
      try {
        if (typeof api.doLayout === 'function') api.doLayout();
        if (typeof api.sizeColumnsToFit === 'function') api.sizeColumnsToFit();
      } catch (_) {}
    }, 100);
  }
}

export function initNotificationSettings(cfg = getSettingsPageConfig()) {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => bootstrapNotificationSettingsGrid(cfg));
  } else {
    bootstrapNotificationSettingsGrid(cfg);
  }
}
