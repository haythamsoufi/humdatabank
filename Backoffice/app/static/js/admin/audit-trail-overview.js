(function () {
  'use strict';

  var cfg = window.auditTrailOverviewConfig || {};
  var t = cfg.t || {};

  var state = { data: null, loaded: false, loading: false, period: 'week', charts: {} };

  function $(id) { return document.getElementById(id); }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function fmt(n) {
    return Number(n || 0).toLocaleString();
  }

  function setText(id, text) {
    var el = $(id);
    if (el) el.textContent = text;
  }

  function deltaHtml(pct, suffix) {
    if (pct === null || pct === undefined) return '';
    var up = pct > 0;
    var flat = pct === 0;
    var cls = flat ? 'text-gray-500' : (up ? 'text-green-700' : 'text-amber-700');
    var icon = flat ? 'fa-minus' : (up ? 'fa-arrow-up' : 'fa-arrow-down');
    return '<span class="' + cls + '"><i class="fas ' + icon + ' mr-1"></i>' +
      Math.abs(pct) + '%</span> ' + escapeHtml(suffix);
  }

  function setHtml(id, html) {
    var el = $(id);
    if (el) el.innerHTML = html;
  }

  // ---- Tabs ---------------------------------------------------------------
  // Shared strip behaviour (AdminUnderlineTabs), same as manage_settings.html.
  function activateTab(name) {
    var isOverview = name === 'overview';
    var A = window.AdminUnderlineTabs;
    if (A) {
      A.activateStripTab('#audit-trail-tabs', name, { panelSelector: '.audit-trail-panel' });
    }
    if (isOverview) {
      if (!state.loaded && !state.loading) loadOverview();
      if (window.history && window.history.replaceState) {
        window.history.replaceState(null, '', '#overview');
      }
    } else if (window.history && window.history.replaceState && window.location.hash === '#overview') {
      window.history.replaceState(null, '', window.location.pathname + window.location.search);
    }
  }

  // ---- Data loading -------------------------------------------------------
  function showState(which) {
    $('auditOverviewLoading').classList.toggle('hidden', which !== 'loading');
    $('auditOverviewError').classList.toggle('hidden', which !== 'error');
    $('auditOverviewContent').classList.toggle('hidden', which !== 'content');
  }

  function loadOverview() {
    state.loading = true;
    showState('loading');
    fetch(cfg.url, { credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        state.data = data;
        state.loaded = true;
        state.loading = false;
        render(data);
        showState('content');
      })
      .catch(function (err) {
        console.error('Audit overview failed', err);
        state.loading = false;
        showState('error');
      });
  }

  // ---- Rendering ----------------------------------------------------------
  function render(d) {
    var tot = d.totals || {};

    setText('auditKpiToday', fmt(tot.today));
    setHtml('auditKpiTodayDelta',
      deltaHtml(tot.today_vs_yesterday_pct, t.vs_yesterday) +
      (tot.today_vs_yesterday_pct === null ? fmt(tot.yesterday) + ' ' + escapeHtml(t.yesterday) : ''));

    setText('auditKpiWeek', fmt(tot.week));
    setHtml('auditKpiWeekDelta',
      deltaHtml(tot.week_vs_prev_pct, t.vs_last_week) +
      (tot.week_vs_prev_pct === null ? escapeHtml(t.week_so_far) + ' ' + escapeHtml(d.week_start || '') : ''));

    setText('auditKpiWindow', fmt(tot.window));
    setText('auditKpiWindowSub', fmt(tot.avg_per_day) + ' ' + t.avg_per_day);

    setText('auditKpiUsersToday', fmt(tot.active_users_today));
    setText('auditKpiUsersSub',
      fmt(tot.active_users_week) + ' ' + t.users_week + ' · ' + fmt(tot.active_users_window) + ' ' + t.users_window);

    setText('auditKpiHighRisk', fmt(tot.high_risk));
    setText('auditKpiNeedsReview', fmt(tot.needs_review));
    setText('auditKpiErrors', fmt(tot.errors_window));
    setText('auditKpiErrorsSub', fmt(tot.errors_today) + ' ' + t.today_errors);

    if (d.peak_hour) {
      var h = d.peak_hour.hour;
      var label = (h < 10 ? '0' : '') + h + ':00 – ' + (h + 1 < 10 ? '0' : '') + ((h + 1) % 24) + ':00';
      setText('auditKpiPeak', label);
      setText('auditKpiPeakSub', fmt(d.peak_hour.count) + ' ' + t.n_activities);
    } else {
      setText('auditKpiPeak', '-');
      setText('auditKpiPeakSub', '');
    }

    var meta = t.updated + ' ' + new Date(d.generated_at).toLocaleString();
    if (tot.truncated) meta += ' · ' + t.truncated;
    setText('auditOverviewMeta', meta);

    renderCharts(d);
    renderSource(d);
    renderPeriodLists();
  }

  function destroyChart(key) {
    if (state.charts[key]) {
      state.charts[key].destroy();
      state.charts[key] = null;
    }
  }

  function renderCharts(d) {
    if (typeof Chart === 'undefined') {
      console.error('Chart.js not loaded');
      return;
    }

    destroyChart('trend');
    var trendEl = $('auditTrendChart');
    if (trendEl) {
      state.charts.trend = new Chart(trendEl.getContext('2d'), {
        type: 'bar',
        data: {
          labels: d.trend.map(function (r) { return r.date.slice(5); }),
          datasets: [{
            label: t.activities,
            data: d.trend.map(function (r) { return r.count; }),
            backgroundColor: 'rgba(37, 99, 235, 0.75)'
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: { y: { beginAtZero: true, ticks: { precision: 0 } } }
        }
      });
    }

    destroyChart('risk');
    var riskEl = $('auditRiskChart');
    if (riskEl) {
      var colors = {
        low: 'rgba(34, 197, 94, 0.8)',
        medium: 'rgba(245, 158, 11, 0.8)',
        high: 'rgba(249, 115, 22, 0.85)',
        critical: 'rgba(220, 38, 38, 0.85)'
      };
      state.charts.risk = new Chart(riskEl.getContext('2d'), {
        type: 'doughnut',
        data: {
          labels: d.risk.map(function (r) { return t[r.level] || r.level; }),
          datasets: [{
            data: d.risk.map(function (r) { return r.count; }),
            backgroundColor: d.risk.map(function (r) { return colors[r.level]; })
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { position: 'bottom' } }
        }
      });
    }

    destroyChart('hour');
    var hourEl = $('auditHourChart');
    if (hourEl) {
      state.charts.hour = new Chart(hourEl.getContext('2d'), {
        type: 'bar',
        data: {
          labels: d.hours.map(function (r) { return (r.hour < 10 ? '0' : '') + r.hour; }),
          datasets: [{
            label: t.activities,
            data: d.hours.map(function (r) { return r.count; }),
            backgroundColor: 'rgba(99, 102, 241, 0.75)'
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: { y: { beginAtZero: true, ticks: { precision: 0 } } }
        }
      });
    }
  }

  function renderSource(d) {
    var src = d.sources || {};
    var total = (src.activity || 0) + (src.admin || 0);
    var rows = [
      { label: t.activity_log, count: src.activity || 0, color: 'bg-blue-500' },
      { label: t.admin_log, count: src.admin || 0, color: 'bg-indigo-500' }
    ];
    setHtml('auditSourceList', rows.map(function (r) {
      var pct = total ? Math.round(100 * r.count / total) : 0;
      return '<div>' +
        '<div class="flex justify-between text-xs text-gray-700 mb-1"><span>' + escapeHtml(r.label) +
        '</span><span>' + fmt(r.count) + ' (' + pct + '%)</span></div>' +
        '<div class="h-2 bg-gray-100"><div class="h-2 ' + r.color + '" style="width:' + pct + '%"></div></div>' +
        '</div>';
    }).join(''));
  }

  function barList(items, period, labelFn, subFn) {
    var ranked = items.slice().sort(function (a, b) { return (b[period] || 0) - (a[period] || 0); })
      .filter(function (r) { return (r[period] || 0) > 0; })
      .slice(0, 10);
    if (!ranked.length) {
      return '<p class="text-sm text-gray-500">' + escapeHtml(t.no_data) + '</p>';
    }
    var max = ranked[0][period] || 1;
    return ranked.map(function (r) {
      var count = r[period] || 0;
      var width = Math.max(2, Math.round(100 * count / max));
      var sub = subFn ? subFn(r) : '';
      return '<div>' +
        '<div class="flex justify-between gap-3 text-xs text-gray-800 mb-1">' +
        '<span class="truncate min-w-0" title="' + escapeHtml(sub || labelFn(r)) + '">' + escapeHtml(labelFn(r)) + '</span>' +
        '<span class="shrink-0 font-medium">' + fmt(count) + '</span></div>' +
        '<div class="h-2 bg-gray-100"><div class="h-2 bg-blue-500" style="width:' + width + '%"></div></div>' +
        '</div>';
    }).join('');
  }

  function renderPeriodLists() {
    var d = state.data;
    if (!d) return;
    var p = state.period;
    setHtml('auditCategoryList', barList(d.categories, p, function (r) { return r.label; }));
    setHtml('auditUserList', barList(d.users, p, function (r) { return r.name; }, function (r) { return r.email; }));

    document.querySelectorAll('.audit-period-btn').forEach(function (btn) {
      var active = btn.getAttribute('data-audit-period') === p;
      btn.classList.toggle('bg-blue-600', active);
      btn.classList.toggle('text-white', active);
      btn.classList.toggle('bg-white', !active);
      btn.classList.toggle('text-gray-600', !active);
    });
  }

  // ---- Wiring -------------------------------------------------------------
  function init() {
    document.querySelectorAll('#audit-trail-tabs .settings-tab').forEach(function (btn) {
      btn.addEventListener('click', function () {
        activateTab(btn.getAttribute('data-tab'));
      });
    });
    document.querySelectorAll('.audit-period-btn').forEach(function (btn) {
      btn.addEventListener('click', function () {
        state.period = btn.getAttribute('data-audit-period');
        renderPeriodLists();
      });
    });
    var retry = $('auditOverviewRetry');
    if (retry) retry.addEventListener('click', loadOverview);
    var refresh = $('auditOverviewRefresh');
    if (refresh) refresh.addEventListener('click', loadOverview);

    if (window.location.hash === '#overview') activateTab('overview');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
