/**
 * Admin → Projects → Monitoring tab.
 *
 * Loads /admin/projects/monitoring/data once the tab is opened (and whenever a filter changes),
 * then renders KPI tiles, Chart.js charts and the worklists. All text comes from
 * window.ProjectMonitoringConfig (server-translated); all dynamic values are escaped.
 */
(function () {
  'use strict';

  var cfg = window.ProjectMonitoringConfig;
  if (!cfg) return;
  var T = cfg.i18n || {};

  var COLORS = {
    green: '#22c55e', amber: '#f59e0b', red: '#ef4444', grey: '#cbd5e1',
    blue: '#3b82f6', slate: '#94a3b8', navy: '#1e3a8a'
  };
  var LIGHT_CLASS = {
    green: 'bg-green-100 text-green-800',
    amber: 'bg-amber-100 text-amber-800',
    red: 'bg-red-100 text-red-800',
    grey: 'bg-gray-100 text-gray-600'
  };
  var PACE_COLOR = {
    on_pace: COLORS.green, ahead: COLORS.amber, behind: COLORS.amber,
    far_behind: COLORS.red, overspent: COLORS.red, no_data: COLORS.grey
  };

  var state = { loaded: false, loading: false, data: null, list: 'overdue', search: '', charts: {} };
  var debounceTimer = null;

  function $(id) { return document.getElementById(id); }

  function esc(value) {
    return String(value == null ? '' : value)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function fmtInt(n) { return n == null ? '—' : Number(n).toLocaleString(); }
  function fmtPct(n) { return n == null ? '—' : Number(n).toFixed(1) + '%'; }
  function fmtChf(n) {
    if (!n) return '—';
    if (n >= 1e6) return 'CHF ' + (n / 1e6).toFixed(2) + 'M';
    if (n >= 1e3) return 'CHF ' + Math.round(n / 1e3) + 'K';
    return 'CHF ' + Math.round(n);
  }
  function parseIso(iso) { return iso ? new Date(iso + 'T00:00:00') : null; }
  function fmtDate(iso) {
    var d = parseIso(iso);
    if (!d || isNaN(d)) return '—';
    return d.toLocaleDateString(undefined, { day: '2-digit', month: 'short', year: 'numeric' });
  }
  function fmtMonth(key) {
    var d = parseIso(key + '-01');
    return d && !isNaN(d) ? d.toLocaleDateString(undefined, { month: 'short', year: '2-digit' }) : key;
  }
  function label(group, key) {
    var g = T[group] || {};
    return g[key] || key;
  }

  function badge(light, text) {
    return '<span class="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded ' +
      (LIGHT_CLASS[light] || LIGHT_CLASS.grey) + '">' + esc(text) + '</span>';
  }
  function dot(light) {
    return '<span class="inline-block w-2.5 h-2.5 rounded-full" style="background:' +
      (COLORS[light] || COLORS.grey) + '"></span>';
  }

  function detailUrl(id) { return cfg.detailUrlTemplate.replace('__ID__', encodeURIComponent(id)); }

  function projectCell(row) {
    var sub = [row.title, row.country].filter(Boolean).map(esc).join(' · ');
    return '<a class="text-blue-700 hover:underline font-semibold" href="' + esc(detailUrl(row.project_id)) + '">' +
      esc(row.reference) + '</a>' + (sub ? '<div class="text-xs text-gray-500 max-w-xs truncate">' + sub + '</div>' : '');
  }

  function contactCell(row) {
    var parts = [];
    if (row.pm || row.pm_email) parts.push('<div>' + esc(row.pm || row.pm_email) + '</div>');
    if (row.focal || row.focal_email) parts.push('<div class="text-xs text-gray-500">' + esc(row.focal || row.focal_email) + '</div>');
    return parts.join('') || '—';
  }

  function remindCell(row) {
    var to = row.focal_email || row.pm_email;
    if (!to) return '<span class="text-gray-400">—</span>';
    var cc = row.focal_email && row.pm_email && row.pm_email !== row.focal_email ? row.pm_email : '';
    var fill = function (s) {
      return String(s || '').replace('{reference}', row.reference).replace('{period}', row.period)
        .replace('{due}', fmtDate(row.due));
    };
    var href = 'mailto:' + encodeURIComponent(to).replace('%40', '@') + '?subject=' + encodeURIComponent(fill(T.reminderSubject)) +
      (cc ? '&cc=' + encodeURIComponent(cc).replace('%40', '@') : '') +
      '&body=' + encodeURIComponent(fill(T.reminderBody));
    return '<a class="inline-flex items-center gap-1 text-blue-600 hover:text-blue-800" href="' + esc(href) + '" title="' +
      esc(T.remind) + '"><i class="fas fa-envelope"></i><span class="text-xs">' + esc(T.remind) + '</span></a>';
  }

  function flagChips(flags) {
    if (!flags || !flags.length) return '—';
    return flags.map(function (f) {
      var txt = label('flags', f.key) + (f.count && f.count > 1 ? ' (' + f.count + ')' : '');
      return badge(f.level, txt);
    }).join(' ');
  }

  function spendCell(row) {
    if (row.spending_rate == null) return '<span class="text-gray-400">' + esc(label('pace', 'no_data')) + '</span>';
    var light = { on_pace: 'green', ahead: 'amber', behind: 'amber', far_behind: 'red', overspent: 'red' }[row.pace] || 'grey';
    return fmtPct(row.spending_rate) + ' ' + badge(light, label('pace', row.pace)) +
      (row.elapsed_pct != null ? '<div class="text-xs text-gray-500">' + esc(T.timeElapsed) + ' ' + fmtPct(row.elapsed_pct) + '</div>' : '');
  }

  function lightCell(light) {
    return light ? badge(light, label('assessment', light)) : '<span class="text-gray-400">—</span>';
  }

  var LISTS = {
    overdue: {
      empty: 'noOverdue',
      cols: [
        { h: 'project', r: projectCell },
        { h: 'report', r: function (r) { return esc(r.period); } },
        { h: 'dueDate', r: function (r) { return fmtDate(r.due); } },
        { h: 'daysOverdue', r: function (r) {
          return badge(r.days_overdue > cfg.limits.severe_overdue_days ? 'red' : 'amber', r.days_overdue + ' ' + T.days);
        } },
        { h: 'status', r: function (r) {
          return esc(label('statuses', r.status)) + (r.completion != null ? '<div class="text-xs text-gray-500">' + fmtPct(r.completion) + '</div>' : '');
        } },
        { h: 'contacts', r: contactCell },
        { h: 'action', r: remindCell }
      ]
    },
    upcoming: {
      empty: 'noUpcoming',
      cols: [
        { h: 'project', r: projectCell },
        { h: 'report', r: function (r) { return esc(r.period); } },
        { h: 'dueDate', r: function (r) { return fmtDate(r.due); } },
        { h: 'dueIn', r: function (r) {
          var soon = r.days_to_due <= cfg.limits.due_soon_days;
          return badge(soon ? 'amber' : 'grey', r.days_to_due + ' ' + T.days);
        } },
        { h: 'status', r: function (r) {
          return esc(label('statuses', r.status)) + (r.completion != null ? '<div class="text-xs text-gray-500">' + fmtPct(r.completion) + '</div>' : '');
        } },
        { h: 'contacts', r: contactCell },
        { h: 'action', r: remindCell }
      ]
    },
    attention: {
      empty: 'noAttention',
      cols: [
        { h: 'project', r: projectCell },
        { h: 'health', r: function (r) { return badge(r.severity, label('lights', r.severity)); } },
        { h: 'overall', r: function (r) { return lightCell(r.overall); } },
        { h: 'activities', r: function (r) { return lightCell(r.activities); } },
        { h: 'spending', r: spendCell },
        { h: 'reasons', r: function (r) { return flagChips(r.flags); } },
        { h: 'contacts', r: contactCell }
      ]
    },
    ending_soon: {
      empty: 'noEnding',
      cols: [
        { h: 'project', r: projectCell },
        { h: 'endDate', r: function (r) { return fmtDate(r.end); } },
        { h: 'daysLeft', r: function (r) {
          if (r.days_to_end < 0) return badge('red', T.endedAgo.replace('{n}', Math.abs(r.days_to_end)));
          return badge(r.days_to_end <= 30 ? 'amber' : 'grey', r.days_to_end + ' ' + T.days);
        } },
        { h: 'finalReport', r: function (r) {
          var light = r.final_state === 'done' ? 'green' : (r.final_state === 'overdue' ? 'red' : (r.final_state === 'none' ? 'amber' : 'grey'));
          return badge(light, label('buckets', r.final_state));
        } },
        { h: 'spending', r: spendCell },
        { h: 'contacts', r: contactCell }
      ]
    },
    pm_workload: {
      empty: 'noPm',
      cols: [
        { h: 'manager', r: function (r) {
          return '<div class="font-medium">' + esc(r.pm || r.pm_email || T.unassigned) + '</div>' +
            (r.pm && r.pm_email ? '<div class="text-xs text-gray-500">' + esc(r.pm_email) + '</div>' : '');
        } },
        { h: 'openProjects', r: function (r) { return fmtInt(r.projects); } },
        { h: 'overdueReports', r: function (r) { return r.overdue ? badge('red', r.overdue) : '0'; } },
        { h: 'dueSoon', r: function (r) { return r.due_soon ? badge('amber', r.due_soon) : '0'; } },
        { h: 'critical', r: function (r) { return r.red ? badge('red', r.red) : '0'; } },
        { h: 'needAttention', r: function (r) { return r.amber ? badge('amber', r.amber) : '0'; } },
        { h: 'portfolio', r: function (r) { return fmtChf(r.granted); } }
      ]
    },
    data_quality: {
      empty: 'noGaps',
      cols: [
        { h: 'project', r: projectCell },
        { h: 'missing', r: function (r) {
          return r.missing.map(function (m) { return badge('amber', label('missing', m)); }).join(' ');
        } },
        { h: 'contacts', r: contactCell }
      ]
    }
  };

  // ------------------------------------------------------------------ loading
  function showState(which) {
    $('pmLoading').classList.toggle('hidden', which !== 'loading');
    $('pmError').classList.toggle('hidden', which !== 'error');
    $('pmContent').classList.toggle('hidden', which !== 'content');
  }

  function queryString() {
    var params = new URLSearchParams();
    ['status', 'portfolio', 'fund', 'region', 'country', 'manager'].forEach(function (k) {
      var el = $('pmFilter-' + k);
      if (el && el.value) params.set(k, el.value);
    });
    return params.toString();
  }

  function syncExportLink() {
    var link = $('pmExport');
    if (link) link.href = cfg.exportUrl + (queryString() ? '?' + queryString() : '');
  }

  function load() {
    if (state.loading) return;
    state.loading = true;
    syncExportLink();
    showState('loading');
    fetch(cfg.dataUrl + (queryString() ? '?' + queryString() : ''), {
      credentials: 'same-origin', headers: { 'Accept': 'application/json' }
    })
      .then(function (r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.json();
      })
      .then(function (data) {
        if (data && data.success === false) throw new Error(data.message || 'error');
        state.data = data;
        state.loaded = true;
        render(data);
        showState('content');
      })
      .catch(function (err) {
        console.error('Project monitoring failed', err);
        showState('error');
      })
      .then(function () { state.loading = false; });
  }

  // ------------------------------------------------------------------ rendering
  function render(data) {
    cfg.limits = data.limits || {};
    renderKpis(data);
    renderHealthBar(data);
    renderCharts(data);
    renderListTabs(data);
    renderList();
    $('pmNoAnswers').classList.toggle('hidden', !!data.answers_available);
    $('pmEmpty').classList.toggle('hidden', data.kpis.projects_total > 0);
    $('pmBody').classList.toggle('hidden', data.kpis.projects_total === 0);
  }

  function tile(opts) {
    var tone = opts.tone ? ' border-l-4 ' + opts.tone : '';
    var attrs = opts.list ? ' data-pm-list="' + esc(opts.list) + '" role="button" tabindex="0"' : '';
    return '<div class="bg-white border border-gray-200 p-4' + tone + (opts.list ? ' cursor-pointer hover:bg-gray-50' : '') + '"' + attrs + '>' +
      '<div class="text-xs font-semibold uppercase tracking-wide text-gray-500">' + esc(opts.label) + '</div>' +
      '<div class="mt-1 text-2xl font-semibold text-gray-900">' + opts.value + '</div>' +
      (opts.hint ? '<div class="mt-0.5 text-xs text-gray-500">' + esc(opts.hint) + '</div>' : '') + '</div>';
  }

  function renderKpis(data) {
    var k = data.kpis;
    var html = [
      tile({ label: T.kpiOpenProjects, value: fmtInt(k.projects_open), hint: T.kpiOfTotal.replace('{n}', k.projects_total) }),
      tile({ label: T.kpiPortfolio, value: esc(fmtChf(k.granted_open)), hint: T.kpiGrantedOpen }),
      tile({ label: T.kpiOverdue, value: fmtInt(k.reports_overdue), tone: k.reports_overdue ? 'border-red-500' : 'border-green-500',
        hint: k.reports_overdue ? T.kpiAvgOverdue.replace('{n}', k.avg_days_overdue) : T.kpiNoneOverdue, list: 'overdue' }),
      tile({ label: T.kpiDueSoon, value: fmtInt(k.reports_due_soon), tone: k.reports_due_soon ? 'border-amber-500' : '',
        hint: T.kpiDueSoonHint.replace('{n}', cfg.limits.due_soon_days), list: 'upcoming' }),
      tile({ label: T.kpiSubmissionRate, value: fmtPct(k.submission_rate), hint: T.kpiSubmissionHint }),
      tile({ label: T.kpiOntimeRate, value: fmtPct(k.ontime_rate), hint: T.kpiOntimeHint }),
      tile({ label: T.kpiAttention, value: fmtInt(k.attention_total), tone: k.projects_red ? 'border-red-500' : (k.projects_amber ? 'border-amber-500' : 'border-green-500'),
        hint: T.kpiAttentionHint.replace('{red}', k.projects_red).replace('{amber}', k.projects_amber), list: 'attention' }),
      tile({ label: T.kpiSpending, value: fmtPct(k.avg_spending_rate),
        hint: T.kpiSpendingHint.replace('{n}', k.spending_coverage).replace('{total}', k.projects_open) })
    ];
    $('pmKpis').innerHTML = html.join('');
  }

  function renderHealthBar(data) {
    var k = data.kpis, total = k.projects_open || 0;
    var parts = [['red', k.projects_red], ['amber', k.projects_amber], ['green', k.projects_green], ['grey', k.projects_grey]];
    if (!total) { $('pmHealth').innerHTML = ''; return; }
    var bar = parts.filter(function (p) { return p[1] > 0; }).map(function (p) {
      return '<div style="width:' + (100 * p[1] / total) + '%;background:' + COLORS[p[0]] + '" title="' +
        esc(label('lights', p[0]) + ': ' + p[1]) + '"></div>';
    }).join('');
    var legend = parts.map(function (p) {
      return '<span class="inline-flex items-center gap-1">' + dot(p[0]) + esc(label('lights', p[0])) + ' <strong>' + p[1] + '</strong></span>';
    }).join('');
    $('pmHealth').innerHTML = '<div class="flex h-3 overflow-hidden rounded bg-gray-100">' + bar + '</div>' +
      '<div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-600">' + legend + '</div>';
  }

  function destroyCharts() {
    Object.keys(state.charts).forEach(function (k) {
      try { state.charts[k].destroy(); } catch (e) { /* ignore */ }
    });
    state.charts = {};
  }

  var emptyFlags = {};

  // Call before makeChart(): an empty chart is not created (Chart.js writes an inline
  // display style, so toggling a class on the canvas would not hide it).
  function setEmpty(id, isEmpty) {
    emptyFlags[id] = !!isEmpty;
    var msg = $(id + 'Empty');
    if (msg) msg.classList.toggle('hidden', !isEmpty);
    var canvas = $(id);
    if (canvas) canvas.style.display = isEmpty ? 'none' : '';
  }

  function makeChart(id, config) {
    var canvas = $(id);
    if (!canvas || emptyFlags[id] || typeof Chart === 'undefined') return;
    state.charts[id] = new Chart(canvas.getContext('2d'), config);
  }

  function sum(obj) {
    return Object.keys(obj).reduce(function (a, k) { return a + (obj[k] || 0); }, 0);
  }

  function renderCharts(data) {
    destroyCharts();
    var c = data.charts;
    var legend = { position: 'bottom', labels: { boxWidth: 12, font: { size: 11 } } };

    // report pipeline
    var pKeys = ['done', 'in_progress', 'not_started', 'overdue', 'closed_unreported'];
    var pColors = [COLORS.green, COLORS.blue, COLORS.slate, COLORS.red, COLORS.grey];
    setEmpty('pmChartPipeline', sum(c.pipeline) === 0);
    makeChart('pmChartPipeline', {
      type: 'doughnut',
      data: {
        labels: pKeys.map(function (k) { return label('buckets', k); }),
        datasets: [{ data: pKeys.map(function (k) { return c.pipeline[k] || 0; }), backgroundColor: pColors, borderWidth: 1 }]
      },
      options: { responsive: true, maintainAspectRatio: false, cutout: '60%', plugins: { legend: legend } }
    });

    // deadlines
    var dl = c.deadlines || [];
    setEmpty('pmChartDeadlines', dl.every(function (d) { return d.count === 0; }));
    makeChart('pmChartDeadlines', {
      type: 'bar',
      data: {
        labels: dl.map(function (d) { return d.bucket === 'overdue' ? T.overdue : fmtMonth(d.bucket); }),
        datasets: [{
          label: T.reports,
          data: dl.map(function (d) { return d.count; }),
          backgroundColor: dl.map(function (d) { return d.bucket === 'overdue' ? COLORS.red : COLORS.blue; })
        }]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: { y: { beginAtZero: true, ticks: { precision: 0 } } }
      }
    });

    // regions
    var rg = c.regions || [];
    setEmpty('pmChartRegions', rg.length === 0);
    makeChart('pmChartRegions', {
      type: 'bar',
      data: {
        labels: rg.map(function (r) { return r.region; }),
        datasets: [
          { label: label('buckets', 'done'), data: rg.map(function (r) { return r.done; }), backgroundColor: COLORS.green },
          { label: T.outstanding, data: rg.map(function (r) { return r.in_progress; }), backgroundColor: COLORS.blue },
          { label: label('buckets', 'overdue'), data: rg.map(function (r) { return r.overdue; }), backgroundColor: COLORS.red },
          { label: label('buckets', 'closed_unreported'), data: rg.map(function (r) { return r.other; }), backgroundColor: COLORS.grey }
        ]
      },
      options: {
        indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        plugins: { legend: legend },
        scales: { x: { stacked: true, beginAtZero: true, ticks: { precision: 0 } }, y: { stacked: true } }
      }
    });

    // assessment
    var aKeys = ['green', 'amber', 'red', 'grey'];
    setEmpty('pmChartAssessment', sum(c.assessment) === 0);
    makeChart('pmChartAssessment', {
      type: 'doughnut',
      data: {
        labels: aKeys.map(function (k) { return label('assessment', k); }),
        datasets: [{ data: aKeys.map(function (k) { return c.assessment[k] || 0; }), backgroundColor: aKeys.map(function (k) { return COLORS[k]; }), borderWidth: 1 }]
      },
      options: { responsive: true, maintainAspectRatio: false, cutout: '60%', plugins: { legend: legend } }
    });

    // spending pace scatter
    var pts = c.pace_points || [];
    setEmpty('pmChartPace', pts.length === 0);
    var maxY = Math.max.apply(null, [100].concat(pts.map(function (p) { return p.y; })));
    makeChart('pmChartPace', {
      type: 'scatter',
      data: {
        datasets: [
          {
            label: T.projects,
            data: pts.map(function (p) { return { x: p.x, y: p.y, p: p }; }),
            backgroundColor: pts.map(function (p) { return PACE_COLOR[p.pace] || COLORS.grey; }),
            pointRadius: 5, pointHoverRadius: 7
          },
          {
            label: T.idealPace, type: 'line', data: [{ x: 0, y: 0 }, { x: 100, y: 100 }],
            borderColor: COLORS.slate, borderDash: [6, 4], borderWidth: 1.5, pointRadius: 0, fill: false
          }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        onClick: function (evt, els) {
          var hit = els.filter(function (e) { return e.datasetIndex === 0; })[0];
          if (!hit) return;
          var p = pts[hit.index];
          if (p) window.location.href = detailUrl(p.project_id);
        },
        onHover: function (evt, els) { evt.native.target.style.cursor = els.length ? 'pointer' : 'default'; },
        plugins: {
          legend: {
            position: 'bottom',
            labels: {
              boxWidth: 12, font: { size: 11 },
              // the project dots are coloured per pace state, so only the reference line gets a legend entry
              filter: function (item) { return item.datasetIndex === 1; }
            }
          },
          tooltip: {
            callbacks: {
              label: function (ctx) {
                var p = ctx.raw && ctx.raw.p;
                if (!p) return ctx.dataset.label;
                return p.reference + (p.title ? ' — ' + p.title : '') + ' (' + T.spent + ' ' + p.y + '%, ' + T.timeElapsed + ' ' + p.x + '%)';
              }
            }
          }
        },
        scales: {
          x: { min: 0, max: 100, title: { display: true, text: T.timeElapsed + ' (%)' } },
          y: { min: 0, suggestedMax: maxY, title: { display: true, text: T.spent + ' (%)' } }
        }
      }
    });

    // funding by portfolio
    var fu = c.funding || [];
    setEmpty('pmChartFunding', fu.length === 0 || fu.every(function (f) { return !f.granted; }));
    makeChart('pmChartFunding', {
      type: 'bar',
      data: {
        labels: fu.map(function (f) { return f.portfolio + ' (' + f.projects + ')'; }),
        datasets: [{ label: T.kpiGrantedOpen, data: fu.map(function (f) { return Math.round(f.granted); }), backgroundColor: COLORS.navy }]
      },
      options: {
        indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: function (ctx) { return fmtChf(ctx.parsed.x); } } }
        },
        scales: { x: { beginAtZero: true, ticks: { callback: function (v) { return fmtChf(v); } } } }
      }
    });
  }

  function renderListTabs(data) {
    var totals = data.totals || {};
    var counts = {
      overdue: totals.overdue, upcoming: totals.upcoming, attention: totals.attention,
      ending_soon: totals.ending_soon, pm_workload: totals.pm_workload, data_quality: totals.data_quality
    };
    document.querySelectorAll('[data-pm-list-tab]').forEach(function (btn) {
      var key = btn.getAttribute('data-pm-list-tab');
      var active = key === state.list;
      btn.setAttribute('aria-selected', active ? 'true' : 'false');
      btn.classList.toggle('bg-blue-600', active);
      btn.classList.toggle('text-white', active);
      btn.classList.toggle('bg-white', !active);
      btn.classList.toggle('text-gray-700', !active);
      var count = btn.querySelector('[data-pm-count]');
      if (count) count.textContent = counts[key] == null ? '0' : counts[key];
    });
  }

  function renderList() {
    var data = state.data;
    if (!data) return;
    var def = LISTS[state.list];
    var rows = (data.lists[state.list] || []);
    var term = state.search.trim().toLowerCase();
    var wrap = $('pmListBody');
    var rendered = rows.map(function (row) {
      var cells = def.cols.map(function (col) { return '<td class="px-3 py-2 align-top">' + col.r(row) + '</td>'; });
      var text = [row.reference, row.title, row.country, row.pm, row.pm_email, row.focal, row.focal_email, row.period]
        .filter(Boolean).join(' ').toLowerCase();
      return { text: text, html: '<tr class="border-t border-gray-100 hover:bg-gray-50">' + cells.join('') + '</tr>' };
    }).filter(function (r) { return !term || r.text.indexOf(term) !== -1; });

    if (!rendered.length) {
      wrap.innerHTML = '<div class="p-6 text-sm text-gray-500 text-center">' + esc(term ? T.noMatches : T[def.empty]) + '</div>';
    } else {
      var head = def.cols.map(function (col) {
        return '<th class="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-gray-500 whitespace-nowrap">' + esc(T.cols[col.h] || col.h) + '</th>';
      }).join('');
      wrap.innerHTML = '<div class="overflow-x-auto"><table class="min-w-full text-sm"><thead class="bg-gray-50"><tr>' + head +
        '</tr></thead><tbody>' + rendered.map(function (r) { return r.html; }).join('') + '</tbody></table></div>';
    }
    var total = (data.totals || {})[state.list];
    var note = $('pmListNote');
    if (note) {
      var truncated = total != null && total > rows.length;
      note.textContent = truncated ? T.truncated.replace('{shown}', rows.length).replace('{total}', total) : '';
      note.classList.toggle('hidden', !truncated);
    }
    $('pmListHelp').textContent = T.listHelp[state.list] || '';
  }

  function setList(key) {
    if (!LISTS[key]) return;
    state.list = key;
    if (state.data) { renderListTabs(state.data); renderList(); }
  }

  // ------------------------------------------------------------------ wiring
  function bind() {
    document.querySelectorAll('[data-pm-list-tab]').forEach(function (btn) {
      btn.addEventListener('click', function () { setList(btn.getAttribute('data-pm-list-tab')); });
    });
    $('pmKpis').addEventListener('click', function (e) {
      var t = e.target.closest('[data-pm-list]');
      if (t) { setList(t.getAttribute('data-pm-list')); $('pmListSection').scrollIntoView({ behavior: 'smooth', block: 'start' }); }
    });
    $('pmKpis').addEventListener('keydown', function (e) {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      var t = e.target.closest('[data-pm-list]');
      if (t) { e.preventDefault(); t.click(); }
    });
    document.querySelectorAll('[id^="pmFilter-"]').forEach(function (el) {
      el.addEventListener('change', function () {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(load, 150);
      });
    });
    var search = $('pmSearch');
    if (search) search.addEventListener('input', function () { state.search = search.value; renderList(); });
    var refresh = $('pmRefresh');
    if (refresh) refresh.addEventListener('click', load);
    var retry = $('pmRetry');
    if (retry) retry.addEventListener('click', load);
    syncExportLink();
  }

  window.ProjectMonitoring = {
    onTabActivated: function () {
      if (!state.loaded && !state.loading) load();
      else if (state.loaded) {
        Object.keys(state.charts).forEach(function (k) { try { state.charts[k].resize(); } catch (e) { /* ignore */ } });
      }
    }
  };

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', bind);
  else bind();
})();
