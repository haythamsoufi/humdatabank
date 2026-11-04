/* Decision Maker UI. All server data is inserted with textContent, never as HTML. */
(function () {
  'use strict';

  var app = document.getElementById('dec-app');
  if (!app) return;

  var L = {};
  try {
    L = JSON.parse(document.getElementById('dec-i18n').textContent || '{}');
  } catch (e) {
    L = {};
  }
  var SUPPORTED = ['en', 'fr', 'es', 'ar'];
  var lang = SUPPORTED.indexOf(app.dataset.lang) >= 0 ? app.dataset.lang : 'en';
  var view = app.dataset.view;
  var numberFormat = new Intl.NumberFormat(lang, { maximumFractionDigits: 1 });
  var intFormat = new Intl.NumberFormat(lang, { maximumFractionDigits: 0 });

  function t(key) {
    return Object.prototype.hasOwnProperty.call(L, key) ? L[key] : key;
  }

  function h(tag, props) {
    var node = document.createElement(tag);
    var children = Array.prototype.slice.call(arguments, 2);
    Object.keys(props || {}).forEach(function (key) {
      var value = props[key];
      if (value === null || value === undefined || value === false) return;
      if (key === 'class') node.className = value;
      else if (key === 'text') node.textContent = value;
      else if (key.indexOf('on') === 0 && typeof value === 'function') node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? '' : String(value));
    });
    children.forEach(function add(child) {
      if (child === null || child === undefined || child === false) return;
      if (Array.isArray(child)) child.forEach(add);
      else node.appendChild(typeof child === 'string' || typeof child === 'number' ? document.createTextNode(String(child)) : child);
    });
    return node;
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
    return node;
  }

  function csrfToken() {
    var meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') || '' : '';
  }

  function setStatus(message, isError) {
    var node = document.getElementById('dec-status');
    if (!node) return;
    node.textContent = message || '';
    node.className = 'dec-muted' + (isError ? ' dec-error' : '');
  }

  function api(url, options) {
    var opts = Object.assign({ credentials: 'same-origin', headers: {} }, options || {});
    opts.headers = Object.assign({ Accept: 'application/json' }, opts.headers);
    if (opts.body && typeof opts.body !== 'string') {
      opts.body = JSON.stringify(opts.body);
      opts.headers['Content-Type'] = 'application/json';
    }
    if (opts.method && opts.method !== 'GET') opts.headers['X-CSRFToken'] = csrfToken();
    return fetch(url, opts).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (body) {
        if (!response.ok) {
          var error = new Error((body && body.error) || t('error'));
          error.status = response.status;
          error.body = body;
          throw error;
        }
        return body;
      });
    });
  }

  function query(params) {
    var usp = new URLSearchParams();
    Object.keys(params).forEach(function (key) {
      if (params[key]) usp.set(key, params[key]);
    });
    var s = usp.toString();
    return s ? '?' + s : '';
  }

  function formatValue(value, unit) {
    if (value === null || value === undefined) return '';
    var text = unit === 'percent' ? numberFormat.format(value) + '%' : (Math.abs(value) >= 100 ? intFormat : numberFormat).format(value);
    if (unit === 'CHF') return text + ' ' + t('currency');
    if (unit === 'days') return text + ' ' + t('days');
    return text;
  }

  function stateText(state) {
    var map = { reported: 'reported', not_reported: 'notReported', unavailable: 'dataUnavailable', not_applicable: 'notApplicable' };
    return t(map[state] || 'notReported');
  }

  function formatDate(iso) {
    if (!iso) return '';
    var d = new Date(iso);
    return isNaN(d.getTime()) ? String(iso) : d.toLocaleString(lang);
  }

  var SEVERITY_MARK = { information: 'i', review: '?', important: '!', urgent: '!!' };

  function severityBadge(severity) {
    return h('span', { class: 'dec-badge dec-sev-' + severity }, h('span', { 'aria-hidden': 'true', text: SEVERITY_MARK[severity] || '' }), ' ', t(severity));
  }

  function readinessBadge(readiness) {
    var key = String(readiness || 'Unavailable').toLowerCase();
    return h('span', { class: 'dec-badge dec-badge-' + key, text: t(key) });
  }

  function mdLite(text) {
    var box = h('div', {});
    String(text || '').split(/\n\n+/).forEach(function (para) {
      var p = h('p', { class: 'dec-muted' });
      para.split('**').forEach(function (part, i) {
        p.appendChild(i % 2 ? h('strong', { text: part }) : document.createTextNode(part.replace(/\*/g, '')));
      });
      box.appendChild(p);
    });
    return box;
  }

  function csvCell(value) {
    var text = value === null || value === undefined ? '' : String(value);
    if (/^[=+\-@\t\r]/.test(text)) text = "'" + text;
    return '"' + text.replace(/"/g, '""') + '"';
  }

  function downloadCsv(name, rows) {
    var body = rows.map(function (row) { return row.map(csvCell).join(','); }).join('\r\n');
    var blob = new Blob(['\ufeff' + body], { type: 'text/csv;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var link = h('a', { href: url, download: name });
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  function askAssistant(prompt) {
    var input = document.getElementById('chatInput');
    if (input) {
      input.value = prompt;
      input.dispatchEvent(new Event('input', { bubbles: true }));
    }
    var fab = document.getElementById('aiChatbotFAB');
    var windowEl = document.getElementById('aiChatbotWindow');
    if (fab && (!windowEl || windowEl.classList.contains('hidden'))) fab.click();
    if (input) input.focus();
  }

  // -------------------------------------------------------------------------
  // Catalogue
  // -------------------------------------------------------------------------

  function initTabs() {
    var tabs = Array.prototype.slice.call(document.querySelectorAll('.dec-tab[data-tab]'));
    if (!tabs.length) return;

    function select(name, focus) {
      tabs.forEach(function (tab) {
        var active = tab.dataset.tab === name;
        tab.setAttribute('aria-selected', active ? 'true' : 'false');
        tab.tabIndex = active ? 0 : -1;
        var panel = document.getElementById(tab.getAttribute('aria-controls'));
        if (panel) panel.hidden = !active;
        if (active && focus) tab.focus();
      });
      if (window.history && history.replaceState) {
        history.replaceState(null, '', name === 'decisions' ? location.pathname + location.search : '#' + name);
      }
    }

    tabs.forEach(function (tab, index) {
      tab.addEventListener('click', function () { select(tab.dataset.tab, false); });
      tab.addEventListener('keydown', function (event) {
        var step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
        if (document.documentElement.dir === 'rtl' || app.getAttribute('dir') === 'rtl') step = step ? -step : step;
        if (event.key === 'Home') step = -index;
        if (event.key === 'End') step = tabs.length - 1 - index;
        if (!step) return;
        event.preventDefault();
        select(tabs[(index + step + tabs.length) % tabs.length].dataset.tab, true);
      });
    });
    if (location.hash === '#guidance') select('guidance', false);
  }

  function initCatalogue() {
    initTabs();
    var cards = document.getElementById('dec-cards');

    function render(payload) {
      var list = payload.data.decisions || [];
      clear(cards);
      if (!list.length) {
        setStatus(t('noData'));
        return;
      }
      setStatus(payload.permission_context && payload.permission_context.scope_limited ? t('scopeLimited') : '');
      list.forEach(function (d) {
        var cov = d.coverage || {};
        var counts = d.flag_counts || { open: 0, by_severity: {} };
        var chips = ['urgent', 'important', 'review', 'information']
          .filter(function (s) { return (counts.by_severity || {})[s]; })
          .map(function (s) { return h('span', { class: 'dec-badge dec-sev-' + s, text: counts.by_severity[s] + ' ' + t(s) }); });
        cards.appendChild(
          h('article', { class: 'dec-card' },
            h('h2', { class: 'dec-h2', text: d.title }),
            h('p', { class: 'dec-muted', text: d.question }),
            h('div', {}, readinessBadge(d.readiness), ' ',
              h('span', { class: 'dec-muted', text: t('coverage') + ': ' + (cov.submitted || 0) + ' / ' + (cov.expected || 0) + ' ' + t('expected') })),
            h('div', {}, h('strong', { text: counts.open + ' ' + t('flagsOpen') }), ' ', chips),
            h('p', { class: 'dec-muted', text: t('audience') + ': ' + (d.audience || []).join(', ') }),
            h('p', { class: 'dec-muted', text: t('owner') + ': ' + (d.owner_team || '') + ' | ' + t('lastRefresh') + ': ' + formatDate(d.last_refresh) }),
            h('a', { class: 'dec-open dec-focus', href: app.dataset.workspaceBase.replace(/\/$/, '') + '/' + encodeURIComponent(d.slug), text: t('open') })
          )
        );
      });
    }

    function load() {
      setStatus(t('loading'));
      api(app.dataset.apiList + query({ lang: lang }))
        .then(render)
        .catch(function (error) { setStatus(error.message, true); });
    }

    load();
  }

  // -------------------------------------------------------------------------
  // Workspace
  // -------------------------------------------------------------------------

  var state = { summary: null, flags: null, filters: {} };
  var drawer, drawerTitle, drawerBody;

  function openDrawer(title, bodyNode) {
    drawerTitle.textContent = title;
    clear(drawerBody).appendChild(bodyNode);
    drawer.hidden = false;
    drawer.focus();
  }

  function dl(pairs) {
    var node = h('dl', { class: 'dec-dl' });
    pairs.forEach(function (pair) {
      if (pair[1] === null || pair[1] === undefined || pair[1] === '') return;
      node.appendChild(h('dt', { text: pair[0] }));
      node.appendChild(h('dd', { text: String(pair[1]) }));
    });
    return node;
  }

  function showEvidence(id) {
    openDrawer(t('evidence'), h('p', { class: 'dec-muted', text: t('loading') }));
    api(app.dataset.evidenceBase + '/' + encodeURIComponent(id))
      .then(function (body) {
        var e = body.data;
        var node = h('div', {},
          dl([
            [t('record'), e.id],
            [t('sourceSystem'), e.source_system],
            [t('dataset'), e.dataset],
            [t('record') + ' #', e.submission_id],
            [t('entity'), (e.entity && e.entity.name) + (e.entity && e.entity.id ? ' (' + e.entity.id + ')' : '')],
            [t('region'), e.entity && e.entity.region],
            [t('round'), e.round],
            [t('period'), e.year],
            [t('value'), e.state === 'reported' ? formatValue(e.value, e.unit) : stateText(e.state)],
            [t('validation'), t(e.validation_state)],
            [t('status'), e.assignment_status],
            [t('visibility'), e.visibility],
            [t('synced'), formatDate(e.last_synchronized_at)],
            [t('accessed'), formatDate(e.accessed_at)],
            [t('definition'), e.definition && (e.definition.name + ' v' + e.definition.version)]
          ]),
          h('p', { class: 'dec-muted', text: t('lineageNote') })
        );
        clear(drawerBody).appendChild(node);
      })
      .catch(function (error) {
        clear(drawerBody).appendChild(h('p', { class: 'dec-error', text: error.message }));
      });
  }

  function showMethodology() {
    openDrawer(t('methodology'), h('p', { class: 'dec-muted', text: t('loading') }));
    api(app.dataset.methodologyBase + '/' + encodeURIComponent(app.dataset.decisionId) + query({ lang: lang }))
      .then(function (body) {
        var d = body.data;
        var node = h('div', {}, mdLite(d.methodology_markdown), h('h3', { class: 'dec-h2', text: t('rule') }));
        d.rules.forEach(function (r) {
          node.appendChild(h('div', { class: 'dec-note' },
            h('strong', { text: r.id + ' v' + r.version + ' - ' + r.name }),
            dl([
              [t('threshold'), r.condition.operator + ' ' + r.condition.value],
              [t('severity'), t(r.severity)],
              [t('status'), r.enabled ? 'enabled' : 'paused'],
              ['', r.provisional_note]
            ])));
        });
        node.appendChild(h('h3', { class: 'dec-h2', text: t('metrics') }));
        d.metrics.forEach(function (m) {
          node.appendChild(h('div', { class: 'dec-note' }, h('strong', { text: m.name + ' (' + m.unit + ')' }), h('p', { class: 'dec-muted', text: m.definition })));
        });
        clear(drawerBody).appendChild(node);
      })
      .catch(function (error) {
        clear(drawerBody).appendChild(h('p', { class: 'dec-error', text: error.message }));
      });
  }

  function currentFilters() {
    var params = new URLSearchParams(window.location.search);
    var out = {};
    ['region', 'country', 'round', 'validation_state'].forEach(function (key) {
      var value = params.get(key);
      if (value) out[key] = value;
    });
    if (app.dataset.country) out.country = app.dataset.country;
    if (app.dataset.region && !out.region) out.region = app.dataset.region;
    return out;
  }

  function loadWorkspace() {
    state.filters = currentFilters();
    var qs = query(Object.assign({ lang: lang }, state.filters));
    var base = app.dataset.apiBase + '/' + encodeURIComponent(app.dataset.decisionId);
    setStatus(t('loading'));
    return Promise.all([api(base + '/summary' + qs), api(base + '/flags' + qs)])
      .then(function (results) {
        state.summary = results[0];
        state.flags = results[1];
        setStatus('');
        renderWorkspace();
      })
      .catch(function (error) {
        setStatus(error.message || t('error'), true);
      });
  }

  function section(id, title, body) {
    return h('section', { class: 'dec-section', id: 'dec-sec-' + id, 'aria-labelledby': 'dec-h-' + id },
      h('h2', { class: 'dec-h2', id: 'dec-h-' + id, text: title }), body);
  }

  function table(headers, rows, numericCols) {
    var numeric = numericCols || [];
    return h('div', { class: 'dec-table-wrap' },
      h('table', { class: 'dec-table' },
        h('thead', {}, h('tr', {}, headers.map(function (head, i) { return h('th', { scope: 'col', class: numeric.indexOf(i) >= 0 ? 'num' : '', text: head }); }))),
        h('tbody', {}, rows.map(function (row) {
          return h('tr', {}, row.map(function (cell, i) { return h('td', { class: numeric.indexOf(i) >= 0 ? 'num' : '' }, cell); }));
        }))));
  }

  function renderHeader() {
    var s = state.summary;
    var d = s.data.decision;
    document.title = d.title;
    var ask = document.getElementById('dec-ask');
    ask.onclick = function () { askAssistant((s.data.assistant_prompts || [])[0] || d.question); };
    document.getElementById('dec-export').onclick = exportEvidence;
    document.getElementById('dec-method').onclick = showMethodology;

    var scope = s.scope || {};
    var scopeText = [scope.round || '', scope.region || '', scope.country || ''].filter(Boolean).join(' | ') || '-';
    var cov = s.coverage || {};
    var mix = (s.data_quality && s.data_quality.validation_mix) || {};
    var meta = document.getElementById('dec-meta');
    clear(meta).appendChild(h('span', {}, h('strong', { text: t('scope') + ': ' }), scopeText));
    meta.appendChild(h('span', {}, h('strong', { text: t('dataAsOf') + ': ' }), formatDate(s.refreshed_at)));
    meta.appendChild(h('span', {}, h('strong', { text: t('coverage') + ': ' }), (cov.submitted || 0) + ' / ' + (cov.expected || 0) + ' ' + t('expected')));
    meta.appendChild(h('span', {}, h('strong', { text: t('validation') + ': ' }),
      (mix.validated || 0) + ' ' + t('validated') + ', ' + (mix.provisional || 0) + ' ' + t('provisional')));
    meta.appendChild(readinessBadge(s.data_quality && s.data_quality.readiness));

    var caveats = (s.data_quality && s.data_quality.caveats) || [];
    var box = clear(document.getElementById('dec-caveats'));
    if (caveats.length) {
      var uniq = caveats.filter(function (c, i) { return caveats.indexOf(c) === i; });
      box.appendChild(h('div', { class: 'dec-caveats', role: 'note' }, h('strong', { text: t('caveats') }), h('ul', {}, uniq.map(function (c) { return h('li', { text: c }); }))));
    }
  }

  function renderKpis() {
    return h('div', { class: 'dec-kpis' }, state.summary.data.key_metrics.map(function (m) {
      var shown = m.state === 'reported' ? formatValue(m.value, m.unit) : stateText(m.state);
      var extra = m.extra && m.extra.expected !== undefined ? ' (' + m.extra.submitted + '/' + m.extra.expected + ')' : '';
      return h('div', { class: 'dec-kpi' }, h('div', { class: 'dec-muted', text: m.name }), h('div', { class: 'v', text: shown + extra }));
    }));
  }

  function renderSources() {
    var groups = state.summary.data.funding_by_source || [];
    if (!groups.length) return h('p', { class: 'dec-muted', text: t('noData') });
    var max = Math.max.apply(null, groups.map(function (g) { return g.value || 0; }).concat([1]));
    var rows = groups.map(function (g) {
      var name = (g.key && g.key.funding_source) || '-';
      var width = g.value ? Math.max(1, Math.round((g.value / max) * 100)) : 0;
      return h('div', { class: 'dec-bar-row' },
        h('span', { text: name }),
        h('div', { 'aria-hidden': 'true' }, h('div', { class: 'dec-bar', style: 'width:' + width + '%' })),
        h('span', { class: 'dec-muted', text: g.value !== null ? formatValue(g.value, 'CHF') : stateText(g.state) }));
    });
    return h('div', {}, h('h3', { class: 'dec-h2', text: t('fundingBySource') }), rows);
  }

  function renderTrend() {
    var points = (state.summary.data.trend || []).filter(function (p) { return p.value !== null; });
    if (!points.length) return h('p', { class: 'dec-muted', text: t('noData') });
    var w = 480, hgt = 160, pad = 28;
    var max = Math.max.apply(null, points.map(function (p) { return p.value; }));
    var ns = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 ' + w + ' ' + hgt);
    svg.setAttribute('class', 'dec-chart');
    svg.setAttribute('role', 'img');
    svg.setAttribute('aria-label', t('trend'));
    var path = [];
    points.forEach(function (p, i) {
      var x = points.length === 1 ? w / 2 : pad + (i * (w - 2 * pad)) / (points.length - 1);
      var y = hgt - pad - (p.value / (max || 1)) * (hgt - 2 * pad);
      path.push((i ? 'L' : 'M') + x.toFixed(1) + ' ' + y.toFixed(1));
      var dot = document.createElementNS(ns, 'circle');
      dot.setAttribute('cx', x); dot.setAttribute('cy', y); dot.setAttribute('r', 4); dot.setAttribute('fill', '#b91c1c');
      svg.appendChild(dot);
      var label = document.createElementNS(ns, 'text');
      label.setAttribute('x', x); label.setAttribute('y', hgt - 8); label.setAttribute('text-anchor', 'middle');
      label.textContent = p.round;
      svg.appendChild(label);
    });
    var line = document.createElementNS(ns, 'path');
    line.setAttribute('d', path.join(' ')); line.setAttribute('fill', 'none'); line.setAttribute('stroke', '#b91c1c'); line.setAttribute('stroke-width', 2);
    svg.insertBefore(line, svg.firstChild);
    var rows = points.map(function (p) {
      return [p.round, String(p.year || ''), formatValue(p.value, 'CHF'), String(p.countries)];
    });
    return h('div', {}, h('h3', { class: 'dec-h2', text: t('trend') }), svg,
      table([t('round'), t('period'), t('funding'), t('country')], rows, [2, 3]));
  }

  function renderCountries() {
    var entities = state.summary.data.entities || [];
    if (!entities.length) return h('p', { class: 'dec-muted', text: t('noData') });
    var slug = app.dataset.slug;
    var rows = entities.map(function (e) {
      var change = e.percent_change === null || e.percent_change === undefined ? '' : (e.percent_change > 0 ? '+' : '') + numberFormat.format(e.percent_change) + '%';
      var people = e.people_targeted !== null && e.people_targeted !== undefined ? formatValue(e.people_targeted, 'people') : stateText(e.people_targeted_state);
      return [
        h('a', { class: 'dec-focus', href: app.dataset.catalogueUrl.replace(/\/$/, '') + '/' + encodeURIComponent(slug) + '/country/' + encodeURIComponent(e.country), text: e.name }),
        e.region || '',
        (e.status || '').replace(/_/g, ' ') + ' / ' + t(e.validation_state),
        e.funding_requirement !== null ? formatValue(e.funding_requirement, 'CHF') : t('notReported'),
        e.baseline_funding_requirement !== null ? formatValue(e.baseline_funding_requirement, 'CHF') : '',
        change,
        people,
        e.flag_count ? h('span', {}, e.max_severity ? severityBadge(e.max_severity) : '', ' ' + e.flag_count) : '0'
      ];
    });
    return table(
      [t('country'), t('region'), t('status'), t('funding'), t('previous'), t('change'), t('people'), t('flagsCol')],
      rows, [3, 4, 5, 6]);
  }

  function renderQuality() {
    var s = state.summary;
    var rules = (state.flags.data.rules || []);
    var cov = s.coverage || {};
    var node = h('div', {},
      dl([
        [t('coverage'), (cov.submitted || 0) + ' / ' + (cov.expected || 0) + (cov.coverage_pct !== null && cov.coverage_pct !== undefined ? ' (' + numberFormat.format(cov.coverage_pct) + '%)' : '')],
        [t('validated'), cov.validated],
        [t('status'), s.data_quality.readiness],
        ['', s.data_quality.readiness_basis]
      ]),
      h('h3', { class: 'dec-h2', text: t('ruleRuns') }),
      table([t('rule'), t('status'), t('evaluated'), t('raised'), t('notEvaluated')],
        rules.map(function (r) {
          return [r.rule_id + ' v' + r.rule_version, r.status, String(r.entities_evaluated), String(r.flags_raised), (r.not_evaluated || []).join(' ')];
        }), [2, 3]));
    return node;
  }

  function renderEvidenceList() {
    var ids = [];
    (state.flags.data.flags || []).forEach(function (f) {
      f.evidence_ids.forEach(function (id) { if (ids.indexOf(id) < 0) ids.push(id); });
    });
    if (!ids.length) return h('p', { class: 'dec-muted', text: t('evidenceListEmpty') });
    return h('div', {}, h('p', { class: 'dec-muted', text: t('lineageNote') }),
      h('div', { class: 'dec-prompts' }, ids.slice(0, 60).map(function (id) {
        return h('button', { type: 'button', class: 'dec-btn dec-focus', text: id, onclick: function () { showEvidence(id); } });
      })));
  }

  function renderPrompts() {
    return h('div', {}, h('p', { class: 'dec-muted' }, h('span', { class: 'dec-label-ai', text: 'AI' }), ' ' + t('aiNotice')),
      h('div', { class: 'dec-prompts' }, (state.summary.data.assistant_prompts || []).map(function (p) {
        return h('button', { type: 'button', class: 'dec-btn dec-prompt dec-focus', text: p, onclick: function () { askAssistant(p); } });
      })));
  }

  function reviewedNotes() {
    var reviewed = (state.flags.data.flags || []).filter(function (f) { return f.status !== 'new'; });
    if (!reviewed.length) return h('p', { class: 'dec-muted', text: t('none') });
    return table([t('flags'), t('status'), t('addNote'), t('generated')],
      reviewed.map(function (f) { return [f.entity_name + ' - ' + f.title, t(f.status), f.review_note || '', formatDate(f.reviewed_at)]; }));
  }

  function flagAction(flag, kind, label) {
    return h('button', {
      type: 'button', class: 'dec-btn dec-focus', text: label,
      onclick: function (event) {
        var wrap = event.target.closest('.dec-flag');
        var noteInput = wrap.querySelector('input[data-note]');
        var body = { note: noteInput ? noteInput.value : '' };
        var endpoint = kind;
        if (kind === 'dismiss') { endpoint = 'resolve'; body.dismiss = true; }
        post(app.dataset.flagBase + '/' + encodeURIComponent(flag.id) + '/' + endpoint, body);
      }
    });
  }

  function feedbackButton(flag, verdict, label) {
    return h('button', {
      type: 'button', class: 'dec-btn dec-focus', text: label,
      onclick: function (event) {
        var wrap = event.target.closest('.dec-flag');
        var noteInput = wrap.querySelector('input[data-note]');
        post(app.dataset.flagBase + '/' + encodeURIComponent(flag.id) + '/feedback', { verdict: verdict, note: noteInput ? noteInput.value : '' });
      }
    });
  }

  function post(url, body) {
    setStatus(t('loading'));
    api(url, { method: 'POST', body: body })
      .then(function () { setStatus(t('saved')); return loadWorkspace(); })
      .catch(function (error) { setStatus(error.message, true); });
  }

  function renderFlag(flag) {
    var thr = flag.threshold || {};
    var trigger = Object.keys(flag.trigger_values || {}).map(function (key) {
      var v = flag.trigger_values[key];
      return [key.replace(/_/g, ' '), Array.isArray(v) ? v.join(', ') : (typeof v === 'number' ? numberFormat.format(v) : v)];
    });
    var detail = [
      dl([
        [t('rule'), flag.rule_id + ' v' + flag.rule_version],
        [t('threshold'), thr.operator + ' ' + thr.value + (thr.provisional ? ' (' + t('provisionalThreshold') + ')' : '')],
        [t('baseline'), flag.baseline_period],
        [t('period'), flag.period_id],
        [t('validation'), t(flag.validation_state)],
        [t('visibility'), flag.visibility],
        [t('source'), t('ruleBased')],
        [t('generated'), formatDate(flag.generated_at)]
      ].concat(trigger.map(function (pair) { return [t('trigger') + ': ' + pair[0], pair[1]]; }))),
      flag.suggested_follow_up && !flag.reasons ? h('div', { class: 'dec-note' }, h('strong', { text: t('followUp') + ': ' }), flag.suggested_follow_up) : null,
      h('div', { class: 'dec-flag-actions' }, flag.evidence_ids.slice(0, 8).map(function (id) {
        return h('button', { type: 'button', class: 'dec-btn dec-focus', text: t('viewEvidence') + ' ' + id.slice(5, 11), onclick: function () { showEvidence(id); } });
      })),
      h('div', { class: 'dec-flag-actions' },
        h('input', { type: 'text', 'data-note': '1', maxlength: '2000', placeholder: t('addNote'), 'aria-label': t('addNote') }),
        flagAction(flag, 'acknowledge', t('acknowledge')),
        flagAction(flag, 'review', t('markReview')),
        flagAction(flag, 'resolve', t('resolve')),
        flagAction(flag, 'dismiss', t('dismiss'))),
      h('div', { class: 'dec-flag-actions' },
        feedbackButton(flag, 'useful', t('useful')),
        feedbackButton(flag, 'not_useful', t('notUseful')),
        feedbackButton(flag, 'incorrect', t('incorrect')),
        feedbackButton(flag, 'expected', t('expectedFb')))
    ];
    if (flag.reasons) {
      var met = (flag.trigger_values || {}).signals_met || flag.reasons.length;
      var assessed = (flag.trigger_values || {}).signals_assessed || met;
      return h('article', { class: 'dec-flag sev-' + flag.severity },
        h('div', { class: 'dec-flag-head' },
          h('strong', { text: flag.entity_name }),
          severityBadge(flag.severity),
          h('span', { class: 'dec-badge dec-badge-unavailable', text: t('signals') + ': ' + met + '/' + assessed }),
          h('span', { class: 'dec-badge dec-badge-unavailable', text: t(flag.status) })),
        h('ul', { class: 'dec-reasons' }, flag.reasons.map(function (reason) { return h('li', { text: reason }); })),
        flag.suggested_follow_up ? h('p', { class: 'dec-muted' }, h('strong', { text: t('followUp') + ': ' }), flag.suggested_follow_up) : null,
        h('details', { class: 'dec-details' }, h('summary', { text: t('howDetermined') }), detail));
    }
    return h('article', { class: 'dec-flag sev-' + flag.severity },
      h('div', { class: 'dec-flag-head' },
        severityBadge(flag.severity),
        h('span', { class: 'dec-badge dec-badge-unavailable', text: t(flag.status) }),
        h('strong', { text: flag.title })),
      h('p', { text: flag.message }),
      detail);
  }

  function isPriorityList() {
    return (state.flags.data.flags || []).some(function (flag) { return flag.reasons; });
  }

  function renderFlags() {
    var flags = state.flags.data.flags || [];
    if (!flags.length) return h('p', { class: 'dec-muted', text: t('none') });
    return h('div', {}, isPriorityList() ? h('div', { class: 'dec-note', text: t('priorityNote') }) : null, flags.map(renderFlag));
  }

  function exportEvidence() {
    var rows = [['flag_id', 'decision', 'rule', 'rule_version', 'entity', 'period', 'severity', 'status', 'validation_state', 'message', 'evidence_ids', 'data_as_of']];
    (state.flags.data.flags || []).forEach(function (f) {
      rows.push([f.id, f.decision_id, f.rule_id, f.rule_version, f.entity_name, f.period_id, f.severity, f.status, f.validation_state, f.message, f.evidence_ids.join(' '), f.data_as_of]);
    });
    downloadCsv('decision-evidence-' + app.dataset.decisionId + '.csv', rows);
  }

  function renderWorkspace() {
    renderHeader();
    var d = state.summary.data.decision;
    var root = clear(document.getElementById('dec-sections'));
    root.appendChild(section('question', t('question'), h('div', {},
      h('p', { text: d.description }),
      dl([[t('audience'), (d.audience || []).join(', ')], [t('owner'), d.owner_team], ['v', d.version]]))));
    root.appendChild(section('summary', t('summary'), renderKpis()));
    root.appendChild(section('flags', (isPriorityList() ? t('priorityCountries') : t('flags')) + ' (' + (state.flags.data.counts.total || 0) + ')', renderFlags()));
    root.appendChild(section('metrics', t('metrics'), renderSources()));
    root.appendChild(section('trends', t('trends'), renderTrend()));
    root.appendChild(section('table', t('table'), renderCountries()));
    root.appendChild(section('quality', t('quality'), renderQuality()));
    root.appendChild(section('evidence', t('evidence'), renderEvidenceList()));
    root.appendChild(section('ai', t('ai'), renderPrompts()));
    root.appendChild(section('notes', t('notes'), reviewedNotes()));
    if (app.dataset.focus) {
      var target = document.getElementById('dec-sec-' + app.dataset.focus);
      if (target) target.scrollIntoView();
    }
  }

  function initWorkspace() {
    drawer = document.getElementById('dec-drawer');
    drawerTitle = document.getElementById('dec-drawer-title');
    drawerBody = document.getElementById('dec-drawer-body');
    var close = document.getElementById('dec-drawer-close');
    close.addEventListener('click', function () { drawer.hidden = true; });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && !drawer.hidden) drawer.hidden = true;
    });
    loadWorkspace();
  }

  if (view === 'catalogue') initCatalogue();
  else if (view === 'workspace') initWorkspace();
})();
