/* Auto-generated from manage_settings.html — tab modules live under js/admin/settings/ */
/* Config is bootstrapped via window.settingsPageConfig in the template */

(function () {
    'use strict';
    var cfg = window.settingsPageConfig || {};

    function escCssSelector(s) {
      if (window.escapeCssSelector) return window.escapeCssSelector(s);
      return String(s == null ? '' : s).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
    }

    // --- Block 2 (original lines 1721-1747) ---
(function () {
  'use strict';
  var A = window.AdminUnderlineTabs;
  var tabs = document.querySelectorAll('#settings-tabs .settings-tab');
  var panels = document.querySelectorAll('.settings-panel');
  if (!tabs.length || !panels.length || !A) return;

  function activate(tabId) {
    A.activateStripTab('#settings-tabs', tabId, { panelSelector: '.settings-panel' });
  }

  tabs.forEach(function (btn) {
    btn.addEventListener('click', function () {
      var id = this.getAttribute('data-tab');
      activate(id);
      history.replaceState(null, '', '#' + id);
      document.dispatchEvent(new CustomEvent('settings-tab-activated', { detail: { tab: id } }));
    });
  });

  var hash = (location.hash || '').replace('#', '');
  if (hash && document.getElementById('panel-' + hash)) {
    activate(hash);
  }
})();

    // --- Block 5 (original lines 1943-2004) ---
/* ── Check for updates via GitHub releases ─────────── */
(function () {
  'use strict';
  var btn   = document.getElementById('check-updates-btn');
  var badge = document.getElementById('version-badge');
  if (!btn) return;

  function escAttr(s) {
    if (window.escapeHtmlAttr) return window.escapeHtmlAttr(s);
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;')
      .replace(/\\/g, '\\\\')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  function checkForUpdates() {
    btn.disabled = true;
    btn.innerHTML = '<i class="fas fa-spinner fa-spin text-[10px]"></i> ' + cfg.t.checkingText + '';

    ((window.getFetch && window.getFetch()) || fetch)(cfg.urls.apiCheckUpdates)
      .then(function (r) {
        return r.json().then(function (data) {
          return { ok: r.ok, data: data || {} };
        }, function () {
          return { ok: false, data: { error: 'Invalid response from server (expected JSON).' } };
        });
      })
      .then(function (result) {
        var data = result.data;
        if (!result.ok || data.success === false) {
          var errMsg = data.error || data.message || 'Unknown error';
          btn.innerHTML = '<i class="fas fa-exclamation-triangle text-[10px] text-amber-500"></i> ' + cfg.t.errorText + '';
          btn.title = errMsg;
          if (window.__clientDebug) {
            window.__clientDebug('[settings] GitHub update check failed', { status: result.ok, data: data });
          }
          setTimeout(function () { resetBtn(); }, 4000);
          return;
        }
        if (data.update_available) {
          var esc = function (s) {
            if (s == null) return '';
            var d = document.createElement('div');
            d.textContent = String(s);
            return d.innerHTML;
          };
          var raw = String(data.release_url || '').trim();
          var safeUrl = (raw.indexOf('https://') === 0 || raw.indexOf('http://') === 0) ? escAttr(raw) : '#';
          badge.innerHTML =
            '<span class="text-xs text-gray-500">v' + (cfg.appVersion || '') + '</span>' +
            '<a href="' + safeUrl + '" target="_blank" rel="noopener" ' +
            '   class="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-green-50 border border-green-300 text-green-700 hover:bg-green-100 transition text-xs" ' +
            '   title="' + esc(data.latest_name || data.latest_version) + '">' +
            '<i class="fas fa-arrow-up text-[10px]"></i> v' + esc(data.latest_version) + ' ' + cfg.t.availableText +
            '</a>';
        } else {
          btn.innerHTML = '<i class="fas fa-check text-[10px] text-green-600"></i> ' + cfg.t.upToDate + '';
          btn.classList.add('border-green-300', 'text-green-600');
          btn.classList.remove('text-gray-500', 'border-gray-300');
          btn.disabled = true;
        }
      })
      .catch(function (err) {
        var errMsg = (err && err.message) ? String(err.message) : (cfg.t.networkError || 'Network error');
        btn.innerHTML = '<i class="fas fa-exclamation-triangle text-[10px] text-amber-500"></i> ' + cfg.t.failedText + '';
        btn.title = errMsg;
        if (window.__clientWarn) {
          window.__clientWarn('[settings] GitHub update check request failed', err);
        }
        setTimeout(function () { resetBtn(); }, 4000);
      });
  }

  btn.addEventListener('click', checkForUpdates);

  function resetBtn() {
    btn.disabled = false;
    btn.innerHTML = '<i class="fas fa-sync-alt text-[10px]"></i> ' + cfg.t.updatesText + '';
    btn.className = 'inline-flex items-center gap-1 px-2 py-0.5 rounded border border-gray-300 text-gray-500 hover:text-blue-600 hover:border-blue-400 transition text-xs';
  }

  // Automatically check for updates on page load
  checkForUpdates();
})();

    // --- Block 6 (original lines 2006-2133) ---
/* ── Unified editable chip-list initializer ─────────── */
(function () {
  'use strict';
  var CLOSE_SVG = '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">'
                + '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>';

  function initChipList(container) {
    var fieldName  = container.dataset.field;
    var maxLen     = parseInt(container.dataset.maxlength, 10) || 100;
    var sentinel   = container.querySelector('.chip-list-sentinel');
    var addInput   = container.querySelector('.chip-add-input');
    if (!sentinel || !addInput) return;

    /* ── Create a new chip element ──────────────────── */
    function createChip(value) {
      var chip = document.createElement('div');
      chip.className = 'chip-item inline-flex items-center gap-2 border border-gray-200 rounded px-2 py-1 bg-gray-50 select-none text-sm';
      chip.draggable = true;

      var handle = document.createElement('span');
      handle.className = 'cursor-move text-gray-400';
      handle.textContent = '≡';

      var label = document.createElement('span');
      label.className = 'chip-label text-gray-700';
      label.contentEditable = 'true';
      label.spellcheck = false;
      label.textContent = value;

      var hidden = document.createElement('input');
      hidden.type = 'hidden';
      hidden.name = fieldName;
      hidden.value = value;

      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'chip-remove ml-0.5 text-gray-400 hover:text-red-600 transition-colors';
      btn.innerHTML = CLOSE_SVG;

      chip.appendChild(handle);
      chip.appendChild(label);
      chip.appendChild(hidden);
      chip.appendChild(btn);

      // Sync hidden input when label is edited
      label.addEventListener('input', function () {
        var txt = this.textContent.trim().substring(0, maxLen);
        hidden.value = txt;
      });
      label.addEventListener('blur', function () {
        var txt = this.textContent.trim().substring(0, maxLen);
        this.textContent = txt;
        hidden.value = txt;
        if (!txt) chip.remove();
      });
      label.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') { e.preventDefault(); this.blur(); }
      });

      // Remove
      btn.addEventListener('click', function () { chip.remove(); });

      // Drag events
      chip.addEventListener('dragstart', onDragStart);
      chip.addEventListener('dragend',   onDragEnd);
      chip.addEventListener('dragover',  onDragOver);

      return chip;
    }

    /* ── Add via input ──────────────────────────────── */
    addInput.addEventListener('keydown', function (e) {
      if (e.key !== 'Enter') return;
      e.preventDefault();
      var val = this.value.trim();
      if (!val) return;
      container.insertBefore(createChip(val), sentinel);
      this.value = '';
    });

    /* ── Drag-and-drop ──────────────────────────────── */
    var dragSrc = null;
    function onDragStart(e) {
      dragSrc = this;
      this.style.opacity = '0.5';
      try { e.dataTransfer.effectAllowed = 'move'; } catch (_) {}
    }
    function onDragEnd() { this.style.opacity = ''; dragSrc = null; }
    function onDragOver(e) {
      e.preventDefault();
      var target = e.target.closest('.chip-item');
      if (!target || !dragSrc || target === dragSrc) return;
      var mid = target.getBoundingClientRect().left + target.offsetWidth / 2;
      var ref = (e.clientX < mid) ? target : (target.nextElementSibling || sentinel);
      if (!ref.classList || !ref.classList.contains('chip-item')) ref = sentinel;
      container.insertBefore(dragSrc, ref);
    }

    // Attach drag events to server-rendered chips
    container.querySelectorAll('.chip-item').forEach(function (chip) {
      var label  = chip.querySelector('.chip-label');
      var hidden = chip.querySelector('input[type="hidden"]');
      var btn    = chip.querySelector('.chip-remove');
      if (label && hidden) {
        label.addEventListener('input', function () { hidden.value = this.textContent.trim().substring(0, maxLen); });
        label.addEventListener('blur', function () {
          var txt = this.textContent.trim().substring(0, maxLen);
          this.textContent = txt;
          hidden.value = txt;
          if (!txt) chip.remove();
        });
        label.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); this.blur(); } });
      }
      if (btn) btn.addEventListener('click', function () { chip.remove(); });
      chip.addEventListener('dragstart', onDragStart);
      chip.addEventListener('dragend',   onDragEnd);
      chip.addEventListener('dragover',  onDragOver);
    });
  }

  // Initialize all chip-list containers
  document.querySelectorAll('[data-field]').forEach(initChipList);
  try {
    document.dispatchEvent(new CustomEvent('settings:section-ready', { detail: { section: 'chip-lists' } }));
  } catch (_) { /* fallback timer still captures snapshot */ }
})();

    // --- Block 7 (original lines 2135-2487) ---
/* ── Chip-list translation matrix controller ─────────── */
(function () {
  'use strict';

  var MODAL_ID   = 'chip-list-translations-modal';
  var TBODY_ID   = 'chip-list-translations-tbody';
  var PREFIX     = 'chip-translations';
  var activeList = null;  // the [data-field] container currently being translated

  var modal   = document.getElementById(MODAL_ID);
  var saveBtn = document.getElementById('save-' + PREFIX + '-btn');
  var autoBtn = document.getElementById('auto-translate-' + PREFIX + '-btn');
  var clearBtn = document.getElementById('clear-' + PREFIX + '-btn');
  if (!modal) return;

  function decodeEntities(s) {
    if (window.decodeHtmlEntities) return window.decodeHtmlEntities(s);
    if (!s) return '';
    var txt = document.createElement('textarea');
    txt.textContent = s;
    return txt.value;
  }

  function getChips(container) {
    return Array.from(container.querySelectorAll('.chip-item'));
  }

  function getChipText(chip) {
    var label = chip.querySelector('.chip-label');
    return label ? label.textContent.trim() : '';
  }

  function getChipTranslations(chip) {
    var raw = chip.getAttribute('data-translations') || '{}';
    try { return normalizeTranslationsObject(JSON.parse(decodeEntities(raw))); } catch (_) { return {}; }
  }

  function normalizeTranslationsObject(input) {
    var source = input;
    if (typeof source === 'string') {
      try { source = JSON.parse(source); } catch (_) { return {}; }
    }
    if (!source || typeof source !== 'object' || Array.isArray(source)) return {};

    var normalized = {};
    for (var lang in source) {
      if (!Object.prototype.hasOwnProperty.call(source, lang)) continue;
      var value = source[lang];
      if (typeof value !== 'string') continue;
      var text = value.trim();
      if (!text) continue;
      var code = String(lang || '').toLowerCase().split('_')[0].split('-')[0].trim();
      if (!code || code === 'en') continue;
      normalized[code] = text;
    }
    return normalized;
  }

  function getListTranslationsMap(container) {
    if (!container || !container.id) return {};
    var jsonInput = document.getElementById(container.id + '-translations-json');
    if (!jsonInput) return {};
    var raw = (jsonInput.value || '').trim();
    if (!raw) return {};
    try {
      var parsed = JSON.parse(decodeEntities(raw));
      if (typeof parsed === 'string') {
        try { parsed = JSON.parse(parsed); } catch (_) { return {}; }
      }
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
      var out = {};
      for (var key in parsed) {
        if (!Object.prototype.hasOwnProperty.call(parsed, key)) continue;
        out[String(key)] = normalizeTranslationsObject(parsed[key]);
      }
      return out;
    } catch (_) {
      return {};
    }
  }

  function resolveTranslationsForText(translationsMap, text) {
    if (!translationsMap || !text) return {};
    if (translationsMap[text] && typeof translationsMap[text] === 'object') return translationsMap[text];

    var trimmedText = String(text).trim();
    if (translationsMap[trimmedText] && typeof translationsMap[trimmedText] === 'object') return translationsMap[trimmedText];

    var lowerText = trimmedText.toLowerCase();
    for (var key in translationsMap) {
      if (!Object.prototype.hasOwnProperty.call(translationsMap, key)) continue;
      if (String(key).trim().toLowerCase() === lowerText && typeof translationsMap[key] === 'object') {
        return translationsMap[key];
      }
    }

    // Robust fallback: normalize punctuation/spacing to match near-identical labels
    function canonicalize(value) {
      return String(value || '')
        .toLowerCase()
        .replace(/['"`.,:;!?()[\]{}\-_/\\]+/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
    }

    var canonicalText = canonicalize(trimmedText);
    if (!canonicalText) return {};
    for (var key2 in translationsMap) {
      if (!Object.prototype.hasOwnProperty.call(translationsMap, key2)) continue;
      if (canonicalize(key2) === canonicalText && typeof translationsMap[key2] === 'object') {
        return translationsMap[key2];
      }
    }

    return {};
  }

  function generateCells(translations) {
    if (window.TranslationModalUtils && typeof window.TranslationModalUtils.generateMatrixCells === 'function') {
      return window.TranslationModalUtils.generateMatrixCells(translations || {});
    }
    return '';
  }

  /* ── Populate the matrix table from chips ─────────── */
  function populate() {
    var tbody = document.getElementById(TBODY_ID);
    if (!tbody || !activeList) return;
    tbody.replaceChildren();
    var translationsMap = getListTranslationsMap(activeList);

    getChips(activeList).forEach(function (chip, idx) {
      var text = getChipText(chip);
      if (!text) return;
      var chipTranslations = getChipTranslations(chip);
      var translations = chipTranslations;
      if (!chipTranslations || Object.keys(chipTranslations).length === 0) {
        translations = resolveTranslationsForText(translationsMap, text);
      }

      var tr = document.createElement('tr');
      tr.className = 'border-b border-gray-200 hover:bg-gray-50';
      tr.dataset.chipIndex = idx;

      // Build full row HTML so <td> elements are parsed inside <tr> context
      var firstCell = '<td class="px-4 py-3 text-sm font-medium text-gray-900 border-r border-gray-300 whitespace-nowrap">' + escapeHtml(text) + '</td>';
      tr.innerHTML = firstCell + generateCells(translations);

      tbody.appendChild(tr);
    });
  }

  /* ── Save back from matrix rows to chip data-attrs ── */
  function saveToChips() {
    if (!activeList) return;
    var chips = getChips(activeList);
    var matrixRows = document.querySelectorAll('#' + TBODY_ID + ' tr');
    var allTranslations = {};

    matrixRows.forEach(function (row) {
      var idx = parseInt(row.dataset.chipIndex, 10);
      var chip = chips[idx];
      if (!chip) return;
      var enText = getChipText(chip);
      var translations = {};
      row.querySelectorAll('textarea[data-language]').forEach(function (ta) {
        var val = ta.value.trim();
        if (val) translations[ta.dataset.language] = val;
      });
      chip.setAttribute('data-translations', JSON.stringify(translations));
      if (Object.keys(translations).length > 0) {
        allTranslations[enText] = translations;
      }
    });

    // Write to the hidden JSON input for form submission
    var jsonInput = document.getElementById(activeList.id + '-translations-json');
    if (jsonInput) jsonInput.value = JSON.stringify(allTranslations);
  }

  /* ── Open button handler ─────────────────────────── */
  document.querySelectorAll('.open-chip-translations-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var listId = this.getAttribute('data-list-id');
      activeList = document.getElementById(listId);
      if (!activeList) return;
      populate();
      modal.classList.remove('hidden');
    });
  });

  /* ── Save handler ────────────────────────────────── */
  if (saveBtn) {
    saveBtn.addEventListener('click', function () {
      saveToChips();
      modal.classList.add('hidden');
    });
  }

  /* ── Clear handler ───────────────────────────────── */
  if (clearBtn) {
    clearBtn.addEventListener('click', function () {
      document.querySelectorAll('#' + TBODY_ID + ' textarea').forEach(function (ta) { ta.value = ''; });
    });
  }

  /* ── Auto-translate handler ──────────────────────── */
  if (autoBtn) {
    autoBtn.addEventListener('click', function () {
      if (!activeList) return;
      var permCtx  = modal.dataset.autoTranslatePermissionContext || '';
      var permCode = modal.dataset.autoTranslatePermissionCode || '';
      var chips = getChips(activeList);
      var texts = chips.map(getChipText).filter(function (t) { return !!t; });
      if (!texts.length) return;

      var origNodes = Array.from(autoBtn.childNodes).map(function (n) { return n.cloneNode(true); });
      function restoreAutoButton() {
        autoBtn.replaceChildren.apply(autoBtn, origNodes.map(function (n) { return n.cloneNode(true); }));
        autoBtn.disabled = false;
      }

      autoBtn.replaceChildren();
      var icon = document.createElement('i');
      icon.className = 'fas fa-spinner fa-spin w-4 h-4 mr-2';
      autoBtn.append(icon, document.createTextNode('Translating...'));
      autoBtn.disabled = true;

      var targetLangs = window.TranslationModalUtils ? window.TranslationModalUtils.getTargetLanguages() : [];

      function requestTranslation(text, translationType) {
        return window.AutoTranslateService.translate({
          type: translationType,
          permission_context: permCtx,
          permission_code: permCode,
          text: text,
          target_languages: targetLangs
        });
      }

      Promise.all(texts.map(function (text) {
        // First try option mode; if provider returns empty/no-result, retry as template_name.
        return requestTranslation(text, 'question_option')
          .then(function (res) {
            return { ok: true, text: text, res: res };
          })
          .catch(function (firstErr) {
            return requestTranslation(text, 'template_name')
              .then(function (res) {
                return { ok: true, text: text, res: res };
              })
              .catch(function (secondErr) {
                return {
                  ok: false,
                  text: text,
                  error: (secondErr && secondErr.message) || (firstErr && firstErr.message) || 'Unknown translation error'
                };
              });
          });
      }))
      .then(function (results) {
        var rows = document.querySelectorAll('#' + TBODY_ID + ' tr');
        var successCount = 0;
        var failed = [];

        results.forEach(function (entry, i) {
          if (entry && entry.ok && entry.res && entry.res.success && entry.res.translations && rows[i]) {
            successCount += 1;
            rows[i].querySelectorAll('textarea[data-language]').forEach(function (ta) {
              if (entry.res.translations[ta.dataset.language]) ta.value = entry.res.translations[ta.dataset.language];
            });
          } else if (entry && !entry.ok) {
            failed.push(entry.text);
          }
        });

        if (successCount > 0) {
          autoBtn.replaceChildren();
          var ok = document.createElement('i');
          ok.className = 'fas fa-check w-4 h-4 mr-2';
          autoBtn.append(ok, document.createTextNode(failed.length ? ('Translated with ' + failed.length + ' skipped') : 'Translated!'));
          setTimeout(function () {
            restoreAutoButton();
          }, 2200);
          if (failed.length) {
            var m = 'Some items could not be translated automatically: ' + failed.join(', ');
            if (window.showAlert) window.showAlert(m, 'warning'); else window.__clientWarn && window.__clientWarn(m);
          }
        } else {
          var firstFailure = (results.find(function (r) { return r && !r.ok; }) || {});
          if (window.TranslationModalUtils) {
            window.TranslationModalUtils.showAutoTranslateError(
              autoBtn,
              '',
              firstFailure.error || 'Translation failed for all items',
              { originalNodes: origNodes, restoreDelayMs: 2500 }
            );
          } else {
            restoreAutoButton();
          }
        }
      })
      .catch(function (err) {
        if (window.TranslationModalUtils) {
          window.TranslationModalUtils.showAutoTranslateError(
            autoBtn,
            '',
            (err && err.message) || 'Unexpected translation error',
            { originalNodes: origNodes, restoreDelayMs: 2500 }
          );
        } else {
          restoreAutoButton();
        }
      });
    });
  }

  /* ── Close handlers ──────────────────────────────── */
  modal.querySelectorAll('.close-modal').forEach(function (btn) {
    btn.addEventListener('click', function () { modal.classList.add('hidden'); });
  });
  modal.addEventListener('click', function (e) { if (e.target === modal) modal.classList.add('hidden'); });

  /* ── Sync translations JSON on form submit ─────── */
  var form = document.getElementById('manage-settings-form');
  if (form) {
    form.addEventListener('submit', function () {
      try {
        document.querySelectorAll('[data-translations-key]').forEach(function (container) {
          var chips = getChips(container);
          var all = {};
          chips.forEach(function (chip) {
            var t = getChipTranslations(chip);
            var text = getChipText(chip);
            if (text && Object.keys(t).length > 0) all[text] = t;
          });
          var jsonInput = document.getElementById(container.id + '-translations-json');
          if (jsonInput) jsonInput.value = JSON.stringify(all);
        });
      } catch (err) {
        /* Don't let a sync failure block the orchestrator's fetch — but surface it
           so an admin can spot drift between chip data and the hidden JSON inputs. */
        if (typeof window.__clientWarn === 'function') {
          window.__clientWarn('[settings-save] chip-translation sync failed: ' + ((err && err.message) || err));
        } else if (window.console && console.warn) {
          console.warn('[settings-save] chip-translation sync failed', err);
        }
      }
    });
  }
})();

    // --- Block 8 (original lines 2489-2732) ---
(function () {
  'use strict';

  /* ── Constants & config ────────────────────────────────── */
  var BASE_LANG  = 'en';
  var CHIP_CLASS = 'lang-order-chip';
  var CHIP_CLS_EXTRA = 'inline-flex items-center gap-2 border border-gray-200 rounded px-2 py-1 bg-gray-50 select-none text-sm';
  var CLOSE_SVG  = '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">'
                 + '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>';

  /* ── DOM refs ──────────────────────────────────────────── */
  var hiddenSelect = document.getElementById('supported-languages-select');
  var addSelect    = document.getElementById('add-language-select');
  var rowEl        = document.getElementById('languages-row');
  var sentinel     = document.getElementById('languages-add-sentinel');
  var hiddenInput  = document.getElementById('languages-order-input');
  if (!hiddenSelect || !addSelect || !rowEl || !sentinel || !hiddenInput) return;

  /* ── Utility helpers ───────────────────────────────────── */
  function norm(code) {
    return code ? String(code).toLowerCase().replace('-', '_').split('_')[0] : '';
  }

  function dedupe(arr) {
    var seen = {}, out = [];
    (arr || []).forEach(function (x) {
      var c = norm(x);
      if (c && !seen[c]) { seen[c] = true; out.push(c); }
    });
    return out;
  }

  function pinBase(arr) {
    var out = dedupe(arr).filter(function (c) { return c !== BASE_LANG; });
    out.unshift(BASE_LANG);
    return out;
  }

  function toSet(arr) {
    var s = {};
    arr.forEach(function (c) { s[c] = true; });
    return s;
  }

  /* ── Build display-name map from hidden <select> options ─ */
  var nameMap = {};
  Array.prototype.forEach.call(hiddenSelect.options, function (opt) {
    var c = norm(opt.value);
    if (c) nameMap[c] = (opt.textContent || '').trim() || c.toUpperCase();
  });

  /* ── State ─────────────────────────────────────────────── */
  var order = pinBase(cfg.currentSupported || []);

  /* ── Sync: hidden <select multiple> ← order ───────────── */
  function syncHiddenSelect() {
    var set = toSet(order);
    Array.prototype.forEach.call(hiddenSelect.options, function (opt) {
      opt.selected = !!set[norm(opt.value)];
    });
  }

  /* ── Sync: "Add" dropdown — hide already-selected ──────── */
  function syncAddDropdown() {
    var set = toSet(order);
    Array.prototype.forEach.call(addSelect.options, function (opt) {
      if (!opt.value) return;
      var added = !!set[norm(opt.value)];
      opt.disabled     = added;
      opt.style.display = added ? 'none' : '';
    });
    addSelect.value = '';
    if (window.jQuery) {
      try { window.jQuery(addSelect).val('').trigger('change.select2'); } catch (_) {}
    }
  }

  /* ── Sync: hidden input ← order ────────────────────────── */
  function writeHidden() { hiddenInput.value = order.join(','); }

  /* ── Read chip order from DOM (after drag) ─────────────── */
  function readChipOrder() {
    var codes = [];
    rowEl.querySelectorAll('.' + CHIP_CLASS).forEach(function (el) {
      if (el.dataset.code) codes.push(el.dataset.code);
    });
    return pinBase(codes);
  }

  /* ── Build a single chip element ───────────────────────── */
  function createChip(code) {
    var isBase = (code === BASE_LANG);

    var chip = document.createElement('div');
    chip.className = CHIP_CLASS + ' ' + CHIP_CLS_EXTRA;
    chip.dataset.code = code;
    chip.draggable = !isBase;

    var handle = document.createElement('span');
    handle.className = isBase ? 'text-gray-300' : 'cursor-move text-gray-400';
    handle.textContent = '≡';

    var label = document.createElement('span');
    label.className = 'text-sm text-gray-700';
    label.textContent = nameMap[code] || code.toUpperCase();

    chip.appendChild(handle);
    chip.appendChild(label);

    if (!isBase) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'ml-1 text-gray-400 hover:text-red-600 transition-colors';
      btn.innerHTML = CLOSE_SVG;
      btn.addEventListener('click', function () { removeLanguage(code); });
      chip.appendChild(btn);

      chip.addEventListener('dragstart', onDragStart);
      chip.addEventListener('dragend',   onDragEnd);
      chip.addEventListener('dragover',  onDragOver);
    }

    return chip;
  }

  /* ── Render all chips ──────────────────────────────────── */
  function render() {
    rowEl.querySelectorAll('.' + CHIP_CLASS).forEach(function (el) { el.remove(); });
    order.forEach(function (code) { rowEl.insertBefore(createChip(code), sentinel); });
    syncHiddenSelect();
    syncAddDropdown();
    writeHidden();
  }

  /* ── Add / remove handlers ─────────────────────────────── */
  function addLanguage(code) {
    var c = norm(code);
    if (!c || c === BASE_LANG || order.indexOf(c) !== -1) return;
    order.push(c);
    render();
  }

  function removeLanguage(code) {
    order = order.filter(function (c) { return c !== code; });
    render();
  }

  /* ── Drag-and-drop ─────────────────────────────────────── */
  var dragSrc = null;

  function onDragStart(e) {
    dragSrc = this;
    this.style.opacity = '0.5';
    try { e.dataTransfer.effectAllowed = 'move'; } catch (_) {}
  }

  function onDragEnd() {
    this.style.opacity = '';
    dragSrc = null;
  }

  function onDragOver(e) {
    e.preventDefault();
    var target = e.target.closest('.' + CHIP_CLASS);
    if (!target || !dragSrc || target === dragSrc || target.dataset.code === BASE_LANG) return;
    var mid = target.getBoundingClientRect().left + target.offsetWidth / 2;
    var ref = (e.clientX < mid) ? target : (target.nextElementSibling || sentinel);
    if (!ref.classList || !ref.classList.contains(CHIP_CLASS)) ref = sentinel;
    rowEl.insertBefore(dragSrc, ref);
    order = readChipOrder();
    writeHidden();
  }

  /* ── "Add language" event wiring ───────────────────────── */
  addSelect.addEventListener('change', function () { addLanguage(this.value); });
  if (window.jQuery) {
    try {
      window.jQuery(addSelect).on('select2:select', function (e) {
        addLanguage(e.params && e.params.data ? e.params.data.id : '');
      });
    } catch (_) {}
  }

  /* ── Form submit safety ────────────────────────────────── */
  var form = hiddenSelect.closest('form');
  if (form) {
    form.addEventListener('submit', function () {
      try {
        syncHiddenSelect();
        writeHidden();
      } catch (err) {
        if (typeof window.__clientWarn === 'function') {
          window.__clientWarn('[settings-save] language-chip sync failed: ' + ((err && err.message) || err));
        } else if (window.console && console.warn) {
          console.warn('[settings-save] language-chip sync failed', err);
        }
      }
    });
  }

  /* ── Select2 upgrade for the "Add" dropdown ────────────── */
  function upgradeToSelect2() {
    if (!window.jQuery || !window.jQuery.fn.select2) return false;
    try {
      var $el = window.jQuery(addSelect);
      $el.select2({
        width: '14rem',
        placeholder: (addSelect.options[0] || {}).textContent || '+ Add…',
        allowClear: true,
        templateResult: function (d) {
          return (!d.id || d.disabled) ? null : d.text;
        }
      });
      var s2 = $el.data('select2');
      if (s2 && s2.$container) {
        s2.$container.addClass('select2-compact select2-dashed select2-muted');
      }
    } catch (_) {}
    return true;
  }

  /* ── Bootstrap ─────────────────────────────────────────── */
  function boot() {
    function done() {
      render();
      try {
        document.dispatchEvent(new CustomEvent('settings:section-ready', { detail: { section: 'languages' } }));
      } catch (_) { /* very old browsers — fallback timer still captures snapshot */ }
    }
    if (upgradeToSelect2() || !window.jQuery) { done(); return; }
    var n = 0;
    var t = setInterval(function () {
      if (upgradeToSelect2() || ++n >= 30) { clearInterval(t); done(); }
    }, 100);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();

    // --- Block 9 (original lines 2735-4120) ---
/* ── Email template editor: selector, language tabs, variable insertion ─── */
(function () {
  'use strict';

  /* ── In-memory store: { templateKey: { lang: content } } ── */
  var templateLangData = {};
  var templateInitialData = {};
  var emailTemplatesDirty = false;

  /* Decode HTML entities that Jinja's forceescape may introduce */
  function decodeEntities(s) {
    if (!s) return '';
    var t = document.createElement('textarea');
    t.innerHTML = s;
    return t.value;
  }

  function stableStringify(obj) {
    try {
      if (!obj || typeof obj !== 'object') return JSON.stringify(obj || {});
      var keys = Object.keys(obj).sort();
      var out = {};
      keys.forEach(function (k) {
        out[k] = obj[k];
      });
      return JSON.stringify(out);
    } catch (_) {
      try { return JSON.stringify(obj || {}); } catch (__) { return '{}'; }
    }
  }

  function normalizeTemplateMap(input) {
    var parsed = input;
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
    var out = {};
    Object.keys(parsed).forEach(function (lang) {
      var val = parsed[lang];
      if (typeof val !== 'string') return;
      var trimmed = val.trim();
      if (!trimmed) return;
      out[String(lang)] = trimmed;
    });
    return out;
  }

  /* HTML escape, then mark Jinja mustache variable spans (syntax backdrop under transparent textarea) */
  function escapeHtmlText(s) {
    if (s == null) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  function highlightJinjaMustacheToHtml(raw) {
    if (!raw) return '';
    var oB = String.fromCharCode(123);
    var cB = String.fromCharCode(125);
    var open = oB + oB;
    var close = cB + cB;
    var out = [];
    var last = 0;
    var i = 0;
    while (i < raw.length) {
      var start = raw.indexOf(open, i);
      if (start === -1) break;
      if (start > last) out.push(escapeHtmlText(raw.slice(last, start)));
      var end = raw.indexOf(close, start + 2);
      if (end === -1) break;
      out.push('<span class="email-template-jinja-var">');
      out.push(escapeHtmlText(raw.slice(start, end + 2)));
      out.push('</span>');
      last = end + 2;
      i = end + 2;
    }
    out.push(escapeHtmlText(raw.slice(last)));
    return out.join('');
  }

  function updateEmailTemplateSyntaxHighlight(ta) {
    if (!ta) return;
    var wrap = ta.closest('.email-template-edit-wrap');
    var pre = wrap ? wrap.querySelector('.email-template-syntax-backdrop') : null;
    if (!pre) return;
    pre.innerHTML = highlightJinjaMustacheToHtml(ta.value);
    pre.style.height = ta.scrollHeight + 'px';
    pre.style.minHeight = ta.clientHeight + 'px';
    pre.style.transform = 'translateY(' + (-ta.scrollTop) + 'px)';
  }

  function bindEmailTemplateSyntaxToTextarea(ta) {
    if (!ta) return;
    function onInput() { updateEmailTemplateSyntaxHighlight(ta); }
    function onScroll() {
      var w = ta.closest('.email-template-edit-wrap');
      var p = w ? w.querySelector('.email-template-syntax-backdrop') : null;
      if (p) p.style.transform = 'translateY(' + (-ta.scrollTop) + 'px)';
    }
    ta.addEventListener('input', onInput);
    ta.addEventListener('scroll', onScroll);
    if (window.ResizeObserver) {
      (new ResizeObserver(function () { updateEmailTemplateSyntaxHighlight(ta); })).observe(ta);
    }
  }

  /* Initialise in-memory data from hidden inputs */
  document.querySelectorAll('.email-template-editor').forEach(function (editor) {
    var hiddenInput = editor.querySelector('input[type="hidden"][id$="-translations"]');
    var textarea    = editor.querySelector('textarea');
    if (!hiddenInput || !textarea) return;
    var key = textarea.id;
    var parsed = {};
    try { parsed = JSON.parse(decodeEntities(hiddenInput.value)) || {}; } catch (_) {}
    if (typeof parsed !== 'object' || Array.isArray(parsed)) parsed = {};
    templateInitialData[key] = normalizeTemplateMap(parsed);
    templateLangData[key] = Object.assign({}, templateInitialData[key]);
    // Ensure textarea shows the English content
    textarea.value = (templateLangData[key] && templateLangData[key]['en']) ? templateLangData[key]['en'] : '';
    textarea.dataset.currentLang = 'en';
  });

  document.querySelectorAll('.email-template-body-textarea').forEach(function (ta) {
    bindEmailTemplateSyntaxToTextarea(ta);
    updateEmailTemplateSyntaxHighlight(ta);
    applyEmailTemplateTextDirection(ta);
  });


  /* ── Email template: HTML / visual (TinyMCE) toggle (inline in code area) ── */
  var EMAIL_PREVIEW_URL = cfg.urls.emailPreview;
  var EMAIL_TEST_SEND_URL = cfg.urls.emailTestSend;
  var CAMPAIGN_EMAIL_PREVIEW_URL = cfg.urls.campaignEmailPreview;
  var CAMPAIGN_EMAIL_TEST_SEND_URL = cfg.urls.campaignEmailTestSend;
  var CAMPAIGN_EMAIL_SEED_URL = cfg.urls.campaignEmailSeed;
  var L_TINYMCE_VAR_TIP = cfg.t.tinymceVarTip;
  var L_TINYMCE_VAR_BTN = cfg.t.variables;
  var MSG_TINYMCE_VAR_PREVIEW_FAIL = cfg.t.couldNotLoadSampleValues;
  var MSG_TINYMCE_VAR_PREVIEW_EMPTY = cfg.t.addContentFirst;
  var EMAIL_SEED_URL = cfg.urls.emailSeed;
  var MSG_SEED_CONFIRM_FORCE = cfg.t.seedConfirmForce;
  var L_SEED_BODIES = cfg.t.templateHtml;
  var L_SEED_UPD = cfg.t.updatedFromDefaults;
  var L_SEED_LEFT = cfg.t.leftUnchanged;
  var emailTemplateViewMode = 'edit';
  /** Set false to silence console logs for test-send / seed API. */
  var DEBUG_EMAIL_SETTINGS_API = false;
  function _debugEmailSettingsApi(phase, info) {
    if (!DEBUG_EMAIL_SETTINGS_API) return;
    try {
      console.log('[email-settings API]', phase, info);
    } catch (_) {}
  }
  try {
    window.setDebugEmailSettingsApi = function (v) {
      DEBUG_EMAIL_SETTINGS_API = v !== false && v !== '0';
      return DEBUG_EMAIL_SETTINGS_API;
    };
  } catch (_) {}
  var MSG_EMAIL_AUTOTRANS_EN_EMPTY = cfg.t.enTemplateEmpty;
  var MSG_TEST_EMAIL_NO_ADDR = cfg.t.noEmailAddr;
  var MSG_TEST_EMAIL_SELECT_USER = cfg.t.testSendSelectUser;
  var MSG_TEST_EMAIL_SENT = cfg.t.testEmailSent;
  var MSG_TEST_EMAIL_FAIL = cfg.t.testEmailFail;

  function base64EncodeUtf8Preview(str) {
    try {
      return btoa(unescape(encodeURIComponent(String(str || ''))));
    } catch (_) {
      return '';
    }
  }

  /** WAF-friendly POST body: { "payload": b64(JSON.stringify(inner)) } — same pattern as settings save. */
  function wrapEmailTemplateApiJsonBody(innerObj) {
    try {
      var payloadB64 = btoa(unescape(encodeURIComponent(JSON.stringify(innerObj))));
      return JSON.stringify({ payload: payloadB64 });
    } catch (_) {
      return null;
    }
  }

  function getCsrfForEmailPreview() {
    var m = document.querySelector('meta[name="csrf-token"]');
    if (m && m.getAttribute('content')) return m.getAttribute('content');
    var f = document.getElementById('manage-settings-form');
    if (f) {
      var inp = f.querySelector('input[name="csrf_token"]');
      if (inp) return inp.value || '';
    }
    return '';
  }

  function getEmailTinymceForKey(templateKey) {
    if (!templateKey || !window.tinymce) return null;
    return tinymce.get(String(templateKey) + '-visual') || null;
  }

  /* Visual mode: 'placeholders' = Jinja source, 'values' = server-rendered sample (read-only for save) */
  var emailTinymceVarMode = {};
  var emailTinymceVarToggleApi = {};
  /** Last <head> innerHTML for a template (TinyMCE 6 has no fullpage; body in editor, head re-applied to iframe). */
  var emailTinymceHeadByKey = {};
  function getEmailTinymceVarMode(tk) {
    return (emailTinymceVarMode[tk] || 'placeholders') === 'values' ? 'values' : 'placeholders';
  }
  function setEmailTinymceVarMode(tk, m) {
    if (!tk) return;
    emailTinymceVarMode[tk] = m === 'values' ? 'values' : 'placeholders';
  }
  function setEmailTinymceVarToggleVisual(tk, isValues) {
    var a = emailTinymceVarToggleApi[tk];
    if (a && typeof a.setActive === 'function') {
      try { a.setActive(!!isValues); } catch (e) {}
    }
  }

  function applyRtlToEmailPreviewHtml(html, langCode) {
    if (!isEmailTemplateRtlLang(langCode)) return html;
    if (!html || typeof html !== 'string') return html;
    if (/<html[^>]*\bdir\s*=/i.test(html)) return html;
    var trimmed = html.trim();
    if (/^<!DOCTYPE/i.test(trimmed) || /^<html/i.test(trimmed)) {
      return html.replace(/<html(\s[^>]*)?>/i, function (full, inner) {
        if (inner && /\bdir\s*=/.test(inner)) return full;
        return '<html' + (inner || '') + ' dir="rtl">';
      });
    }
    return '<div dir="rtl" style="direction:rtl;text-align:start;">' + html + '</div>';
  }

  function isFullHtmlDocumentFragment(s) {
    if (!s || typeof s !== 'string') return false;
    var t = s.trim();
    return t.indexOf('<!DOCTYPE') === 0 || /^<html[\s>]/i.test(t);
  }

  function injectEmailTemplateHeadIntoTinymceEd(ed, headInner) {
    if (!ed) return;
    if (!ed.getDoc || !ed.getDoc()) return;
    var doc = ed.getDoc();
    if (!doc.head) return;
    [].forEach.call(doc.head.querySelectorAll('[data-email-template-head="1"]'), function (n) {
      try { n.remove(); } catch (e) {}
    });
    if (!headInner || !String(headInner).trim()) return;
    var container;
    try {
      container = new window.DOMParser().parseFromString(
        '<!DOCTYPE html><html><head>' + String(headInner) + '</head><body></body></html>',
        'text/html'
      );
    } catch (e) {
      return;
    }
    if (!container || !container.head) return;
    [].forEach.call(container.head.children, function (el) {
      if (!el || el.nodeName === '#text') return;
      var tag = (el.nodeName || '').toUpperCase();
      if (tag !== 'TITLE' && tag !== 'STYLE' && tag !== 'LINK' && tag !== 'META') return;
      try {
        var imp = doc.importNode(el, true);
        imp.setAttribute('data-email-template-head', '1');
        doc.head.appendChild(imp);
      } catch (e) {}
    });
  }

  /* Visual: wrap Jinja2 double-brace placeholders in body text; strip on save. Matches HTML-tab .email-template-jinja-var. */
  var HTE_JINJA_CLS = 'htd-email-jinja';
  /* No literal double-open-brace in this Jinja2 file; that would start a Jinja print. */
  var HTE_JINJA_OPEN = '{' + '{';
  var HTE_JINJA_RE = new RegExp('\\{\\{[\\s\\S]*?\\}\\}', 'g');
  function shouldSkipJinjaWalkEl(el) {
    if (!el || el.nodeType !== 1) return false;
    var tag = (el.nodeName || '').toLowerCase();
    if (tag === 'script' || tag === 'style' || tag === 'noscript' || tag === 'textarea') return true;
    if (el.classList && el.classList.contains(HTE_JINJA_CLS)) return true;
    return false;
  }
  function jinjaTextNodeHasPlaceholder(t) {
    if (!t || t.indexOf(HTE_JINJA_OPEN) < 0) return false;
    HTE_JINJA_RE.lastIndex = 0;
    return HTE_JINJA_RE.test(t);
  }
  function processJinjaInTextNode(textNode, doc) {
    if (!textNode || textNode.nodeType !== 3) return;
    var t = textNode.nodeValue;
    if (!jinjaTextNodeHasPlaceholder(t)) return;
    HTE_JINJA_RE.lastIndex = 0;
    var parent = textNode.parentNode;
    if (!parent) return;
    var m;
    var last = 0;
    var fr = doc.createDocumentFragment();
    HTE_JINJA_RE.lastIndex = 0;
    while ((m = HTE_JINJA_RE.exec(t)) !== null) {
      if (m.index > last) {
        fr.appendChild(doc.createTextNode(t.slice(last, m.index)));
      }
      var sp = doc.createElement('span');
      sp.setAttribute('class', HTE_JINJA_CLS);
      sp.setAttribute('data-htd-jinja', '1');
      sp.appendChild(doc.createTextNode(m[0]));
      fr.appendChild(sp);
      last = m.index + m[0].length;
    }
    if (last < t.length) {
      fr.appendChild(doc.createTextNode(t.slice(last)));
    }
    if (fr.childNodes.length) {
      try {
        parent.replaceChild(fr, textNode);
      } catch (e) {}
    }
  }
  function walkJinjaInNode(root, doc) {
    if (!root) return;
    var n = root.firstChild;
    while (n) {
      var next = n.nextSibling;
      if (n.nodeType === 1) {
        if (!shouldSkipJinjaWalkEl(n)) walkJinjaInNode(n, doc);
      } else if (n.nodeType === 3) {
        processJinjaInTextNode(n, doc);
      }
      n = next;
    }
  }
  function applyJinjaHighlightToBodyHtmlString(bodyHtml) {
    if (bodyHtml == null || !String(bodyHtml) || String(bodyHtml).indexOf(HTE_JINJA_OPEN) < 0) return String(bodyHtml || '');
    var d, wrap, doc;
    try {
      d = new window.DOMParser().parseFromString(
        '<!DOCTYPE html><html><body id="__htd_ja"><div id="__htd_jw">' + String(bodyHtml) + '</div></body></html>',
        'text/html'
      );
      doc = d;
      wrap = d.getElementById('__htd_jw');
    } catch (e) {
      return String(bodyHtml);
    }
    if (!wrap || !doc) return String(bodyHtml);
    walkJinjaInNode(wrap, doc);
    return wrap.innerHTML;
  }
  function stripJinjaHighlightFromBodyHtmlString(bodyHtml) {
    var s = String(bodyHtml || '');
    if ((s.indexOf(HTE_JINJA_CLS) < 0) && (s.indexOf('data-htd-jinja') < 0)) return s;
    var d, wrap;
    try {
      d = new window.DOMParser().parseFromString(
        '<!DOCTYPE html><html><body id="__htd_ja2"><div id="__htd_jw2">' + String(bodyHtml) + '</div></body></html>',
        'text/html'
      );
      wrap = d.getElementById('__htd_jw2');
    } catch (e) {
      return s;
    }
    if (!wrap) return s;
    [].forEach.call(wrap.querySelectorAll('span.' + HTE_JINJA_CLS + ',span[data-htd-jinja]'), function (sp) {
      var p = sp.parentNode;
      if (!p) return;
      while (sp.firstChild) p.insertBefore(sp.firstChild, sp);
      p.removeChild(sp);
    });
    return wrap.innerHTML;
  }
  function normalizeBodyForTinymceDisplay(bodyStr, templateKey) {
    var s0 = String(bodyStr || '');
    s0 = stripJinjaHighlightFromBodyHtmlString(s0);
    if (getEmailTinymceVarMode(templateKey) === 'values') return s0;
    return applyJinjaHighlightToBodyHtmlString(s0);
  }
  function injectJinjaVarHighlightStyleInTinymceEd(ed) {
    if (!ed || !ed.getDoc) return;
    var doc = ed.getDoc();
    if (!doc || !doc.head) return;
    /* Drop previous build so we can update highlight rules; version bump when styles change. */
    [].forEach.call(doc.querySelectorAll('style[data-email-jinja-hl]'), function (n) {
      try {
        n.remove();
      } catch (e) {}
    });
    var st = doc.createElement('style');
    st.setAttribute('data-email-jinja-hl', '2');
    st.textContent =
      '.' + HTE_JINJA_CLS + '{' +
      'box-sizing:border-box;' +
      'color:#0f3d3a;' +
      'background:#fff;' +
      'border:1.5px solid #115e59;' +
      'box-shadow:0 0 0 1px rgba(255,255,255,0.9),0 1px 3px rgba(0,0,0,0.2);' +
      'border-radius:4px;padding:0.08em 0.24em;font-weight:600;' +
      'font-family:ui-monospace,Consolas,Monaco,Menlo,monospace;font-size:0.9em;' +
      'letter-spacing:0.02em' +
      '}';
    try {
      doc.head.appendChild(st);
    } catch (e) {}
  }
  function afterTinymceEmailBodySet(ed, templateKey) {
    if (!ed) return;
    window.setTimeout(function () {
      injectEmailTemplateHeadIntoTinymceEd(ed, (templateKey && emailTinymceHeadByKey[templateKey] != null) ? String(emailTinymceHeadByKey[templateKey]) : '');
      injectJinjaVarHighlightStyleInTinymceEd(ed);
    }, 0);
  }

  /**
   * TinyMCE 6 removed the fullpage plugin. Store <head> separately and edit <body> only, then
   * inject <style> / <link> into the editor iframe and rebuild full documents on save.
   */
  function setEmailTinymceContentPreservingDocument(ed, html, templateKey) {
    if (!ed || !templateKey) return;
    if (html == null) {
      emailTinymceHeadByKey[templateKey] = '';
      ed.setContent('');
      return;
    }
    var h = String(html);
    if (!h.trim()) {
      emailTinymceHeadByKey[templateKey] = '';
      ed.setContent('');
      return;
    }
    var done = function (bodyInner) {
      var inner = normalizeBodyForTinymceDisplay(bodyInner, templateKey);
      ed.setContent(inner, { format: 'html' });
      afterTinymceEmailBodySet(ed, templateKey);
    };
    try {
      var d = new window.DOMParser().parseFromString(h, 'text/html');
      var headInner = (d.head && d.head.innerHTML) ? d.head.innerHTML.trim() : '';
      var bodyEl = d.body;
      if (!bodyEl) {
        emailTinymceHeadByKey[templateKey] = '';
        ed.setContent(normalizeBodyForTinymceDisplay(h, templateKey), { format: 'html' });
        afterTinymceEmailBodySet(ed, templateKey);
        return;
      }
      if (!headInner && !isFullHtmlDocumentFragment(h) && h.indexOf('<head') < 0) {
        emailTinymceHeadByKey[templateKey] = '';
        ed.setContent(normalizeBodyForTinymceDisplay(h, templateKey), { format: 'html' });
        afterTinymceEmailBodySet(ed, templateKey);
        return;
      }
      emailTinymceHeadByKey[templateKey] = headInner;
      done(bodyEl.innerHTML);
    } catch (e) {
      if (window.console && console.debug) window.console.debug('setEmailTinymceContent', e);
      try {
        ed.setContent(normalizeBodyForTinymceDisplay(h, templateKey), { format: 'html' });
        afterTinymceEmailBodySet(ed, templateKey);
      } catch (e2) {}
      emailTinymceHeadByKey[templateKey] = '';
    }
  }

  function rebuildCurrentEmailFromTinymce(templateKey) {
    var m = getEmailTinymceForKey(templateKey);
    if (!m) {
      var ta0 = document.getElementById(templateKey);
      return ta0 ? ta0.value : '';
    }
    var headInner = (emailTinymceHeadByKey[templateKey] != null) ? String(emailTinymceHeadByKey[templateKey]) : '';
    var bodyInner = stripJinjaHighlightFromBodyHtmlString(m.getContent() || '');
    if (!headInner.trim()) return bodyInner;
    return '<!DOCTYPE html>\n<html><head>' + headInner + '</head><body>' + bodyInner + '</body></html>';
  }

  function copyEmailTinymceToTextareaByKey(templateKey) {
    if (getEmailTinymceVarMode(templateKey) === 'values') return;
    var m = getEmailTinymceForKey(templateKey);
    if (!m) return;
    var ta = document.getElementById(templateKey);
    if (ta) ta.value = rebuildCurrentEmailFromTinymce(templateKey);
  }

  function copyEmailTinymceToTextareaForAll() {
    document.querySelectorAll('.email-template-editor').forEach(function (ed) {
      if (!ed.id || ed.id.indexOf('editor-') !== 0) return;
      var key = ed.id.replace(/^editor-/, '');
      copyEmailTinymceToTextareaByKey(key);
    });
  }

  function destroyEmailTinymceByKey(templateKey) {
    if (!templateKey || !window.tinymce) return;
    var m = getEmailTinymceForKey(templateKey);
    if (m) m.remove();
    setEmailTinymceVarMode(templateKey, 'placeholders');
    try { delete emailTinymceVarToggleApi[templateKey]; } catch (e) {}
    try { delete emailTinymceHeadByKey[templateKey]; } catch (e) {}
  }

  function getPlaceholderHtmlForTemplateKey(templateKey) {
    var mainTa = document.getElementById(templateKey);
    if (!mainTa) return '';
    var l = mainTa.dataset.currentLang || 'en';
    if (templateLangData[templateKey] && templateLangData[templateKey][l] != null) {
      return String(templateLangData[templateKey][l]);
    }
    return mainTa.value;
  }

  function syncTinymcePlaceholderToMapForPreview(templateKey) {
    if (getEmailTinymceVarMode(templateKey) === 'values') return;
    copyEmailTinymceToTextareaByKey(templateKey);
    var mainTa = document.getElementById(templateKey);
    if (!mainTa) return;
    if (!templateLangData[templateKey]) templateLangData[templateKey] = {};
    templateLangData[templateKey][mainTa.dataset.currentLang || 'en'] = mainTa.value;
  }

  /**
   * Server preview runs bleach, which strips or empties <style> in <head> for admin safety.
   * Reuse the <head> from the unsent placeholder source (same template) and the rendered <body> from the API
   * so the Visual "sample values" view keeps the same CSS as the Placeholders view.
   */
  function mergeEmailPreviewWithSourceHead(placeholderSource, serverHtml) {
    if (!serverHtml || typeof serverHtml !== 'string') return serverHtml || '';
    var ph = (placeholderSource || '').trim();
    if (!ph) return serverHtml;
    if (!/<style[\s>]/i.test(ph) && !/<link[^>]+rel\s*=\s*["']?stylesheet/i.test(ph)) {
      return serverHtml;
    }
    try {
      var parser = new window.DOMParser();
      var dPh = parser.parseFromString(ph, 'text/html');
      var dSv = parser.parseFromString(serverHtml, 'text/html');
      var headInner = (dPh.head && dPh.head.innerHTML) ? dPh.head.innerHTML.trim() : '';
      if (!headInner) return serverHtml;
      var bodyInner = (dSv.body && dSv.body.innerHTML) ? dSv.body.innerHTML : serverHtml;
      return '<!DOCTYPE html>\n<html><head>' + headInner + '</head><body>' + bodyInner + '</body></html>';
    } catch (e) {
      return serverHtml;
    }
  }

  function isCampaignEmailTemplateKey(templateKey) {
    return !!(templateKey && String(templateKey).indexOf('campaign_template_') === 0);
  }

  function getEmailPreviewUrlForKey(templateKey) {
    if (isCampaignEmailTemplateKey(templateKey) && CAMPAIGN_EMAIL_PREVIEW_URL) {
      return CAMPAIGN_EMAIL_PREVIEW_URL;
    }
    return EMAIL_PREVIEW_URL;
  }

  function getEmailTestSendUrlForKey(templateKey) {
    if (isCampaignEmailTemplateKey(templateKey) && CAMPAIGN_EMAIL_TEST_SEND_URL) {
      return CAMPAIGN_EMAIL_TEST_SEND_URL;
    }
    return EMAIL_TEST_SEND_URL;
  }

  function runEmailTinymceSampleValuesRequest(templateKey, onDone) {
    var previewUrl = getEmailPreviewUrlForKey(templateKey);
    if (!previewUrl) {
      onDone(new Error('url'));
      return;
    }
    var mainTa = document.getElementById(templateKey);
    if (!mainTa) { onDone(new Error('no ta')); return; }
    var plang = (mainTa.dataset && mainTa.dataset.currentLang) ? String(mainTa.dataset.currentLang).trim() : 'en';
    var src = getPlaceholderHtmlForTemplateKey(templateKey);
    var trimmed = (src || '').trim();
    if (!trimmed) { onDone(new Error('empty')); return; }
    var b64 = base64EncodeUtf8Preview(trimmed);
    if (!b64) { onDone(new Error('b64')); return; }
    var bodyStr = wrapEmailTemplateApiJsonBody({ template_key: templateKey, html_b64: b64, template_language: plang });
    if (!bodyStr) { onDone(new Error('wrap')); return; }
    var csrf = getCsrfForEmailPreview();
    _debugEmailSettingsApi('template-var-preview request', { url: previewUrl, template_key: templateKey, template_language: plang });
    ((window.getFetch && window.getFetch()) || fetch)(previewUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf,
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: bodyStr
    }).then(function (resp) {
      return window.responseAsResult(resp);
    }).then(function (result) {
      _debugEmailSettingsApi('template-var-preview response', { ok: result.ok, status: result.status, payload: result.payload });
      var p = result.payload || {};
      if (result.ok && p.success && typeof p.html === 'string' && p.html.trim()) {
        var merged = mergeEmailPreviewWithSourceHead(src, p.html);
        onDone(null, applyRtlToEmailPreviewHtml(merged, plang));
        return;
      }
      onDone(new Error(p.error || p.message || (MSG_TINYMCE_VAR_PREVIEW_FAIL + (result.status ? ' (' + result.status + ')' : ''))));
    }).catch(function (err) {
      onDone(err, null);
    });
  }

  function getTemplateKeyFromEditorBlock(el) {
    if (!el || !el.id || el.id.indexOf('editor-') !== 0) return '';
    return el.id.replace(/^editor-/, '');
  }

  /* Self-hosted (same origin) to avoid third-party “Tracking Prevention” storage noise from cdnjs. */
  var TINYMCE_BASE_URL = cfg.urls.tinymceBase;

  var tinymceLoadPromise = null;
  function loadTinymceIfNeeded(done) {
    if (window.tinymce) {
      setTimeout(done, 0);
      return;
    }
    if (tinymceLoadPromise) {
      tinymceLoadPromise.then(function () { done(); });
      return;
    }
    tinymceLoadPromise = new Promise(function (resolve) {
      var s = document.createElement('script');
      s.src = TINYMCE_BASE_URL + '/tinymce.min.js';
      s.onload = function () { resolve(1); };
      s.onerror = function () { resolve(0); };
      document.head.appendChild(s);
    });
    tinymceLoadPromise.then(function () { done(); });
  }

  function buildTinymceEmailOptions(templateKey) {
    var ta = document.getElementById(templateKey);
    var lang = (ta && ta.dataset && ta.dataset.currentLang) ? String(ta.dataset.currentLang) : 'en';
    var rtl = isEmailTemplateRtlLang(lang);
    return {
      selector: '#' + escCssSelector(templateKey) + '-visual',
      /* Fixed viewport; do not use autoresize (it grows the frame to full document height). */
      height: 480,
      resize: false,
      statusbar: false,
      /* Wrap toolbar to match narrow card; no DOM path bar. */
      toolbar_mode: 'wrap',
      menubar: false,
      branding: false,
      promotion: false,
      /* fullpage was removed in TinyMCE 6; we split head/body in JS. */
      plugins: 'image link lists table visualblocks',
      /* forecolor / backcolor: free core toolbar; image: URL/alt in dialog (upload needs a custom images_upload_url handler). */
      toolbar: 'undo redo | blocks | bold italic underline | forecolor backcolor | alignleft aligncenter alignright | bullist numlist outdent indent | link image table | emailvarmode | removeformat',
      /* When the caret is in a table, show row/column + cell formatting (contextual bar). */
      table_toolbar: 'tableprops tabledelete | tablecellprops tablerowprops | tablemergecells tablesplitcells | tablecellvalign | tableinsertrowbefore tableinsertrowafter tabledeleterow | tableinsertcolbefore tableinsertcolafter tabledeletecol | tablecellbackgroundcolor | tablecellborderwidth tablecellborderstyle',
      valid_elements: '*[*]',
      invalid_elements: '',
      verify_html: false,
      entity_encoding: 'raw',
      apply_source_formatting: false,
      remove_trailing_brs: false,
      convert_urls: false,
      relative_urls: false,
      remove_script_host: false,
      base_url: TINYMCE_BASE_URL,
      suffix: '.min',
      skin: 'oxide',
      /* Do not load TinyMCE 'default' content.css — it overrides body/typography and makes emails look unstyled. */
      content_css: false,
      directionality: rtl ? 'rtl' : 'ltr',
      setup: function (ed) {
        ed.on('input change keyup', function () { emailTemplatesDirty = true; });
        if (ed.ui && ed.ui.registry) {
          var tk = templateKey;
          ed.ui.registry.addToggleButton('emailvarmode', {
            text: L_TINYMCE_VAR_BTN || 'Var',
            icon: 'preview',
            tooltip: L_TINYMCE_VAR_TIP,
            onAction: function (api) {
              if (getEmailTinymceVarMode(tk) === 'values') {
                var ph = getPlaceholderHtmlForTemplateKey(tk);
                setEmailTinymceVarMode(tk, 'placeholders');
                setEmailTinymceContentPreservingDocument(ed, ph, tk);
                var b0 = ed.getBody();
                if (b0) {
                  var main0 = document.getElementById(tk);
                  if (main0) {
                    var cl0 = main0.dataset.currentLang || 'en';
                    b0.setAttribute('dir', isEmailTemplateRtlLang(cl0) ? 'rtl' : 'ltr');
                    b0.style.direction = isEmailTemplateRtlLang(cl0) ? 'rtl' : 'ltr';
                    b0.setAttribute('lang', cl0);
                  }
                }
                api.setActive(false);
                return;
              }
              if (api) { api.setActive(false); }
              syncTinymcePlaceholderToMapForPreview(tk);
              if (api) api.setEnabled(false);
              runEmailTinymceSampleValuesRequest(tk, function (err, outHtml) {
                if (api) api.setEnabled(true);
                if (err) {
                  var m = (err && err.message === 'empty') ? MSG_TINYMCE_VAR_PREVIEW_EMPTY
                    : (err && err.message) ? String(err.message) : MSG_TINYMCE_VAR_PREVIEW_FAIL;
                  if (api) api.setActive(false);
                  if (window.showAlert) window.showAlert(m, 'warning');
                  return;
                }
                setEmailTinymceVarMode(tk, 'values');
                setEmailTinymceContentPreservingDocument(ed, outHtml, tk);
                var b2 = ed.getBody();
                if (b2) {
                  var main2 = document.getElementById(tk);
                  if (main2) {
                    var cl2 = main2.dataset.currentLang || 'en';
                    b2.setAttribute('dir', isEmailTemplateRtlLang(cl2) ? 'rtl' : 'ltr');
                    b2.style.direction = isEmailTemplateRtlLang(cl2) ? 'rtl' : 'ltr';
                    b2.setAttribute('lang', cl2);
                  }
                }
                if (api) api.setActive(true);
              });
            },
            onSetup: function (api) {
              emailTinymceVarToggleApi[tk] = api;
              try { api.setActive(false); } catch (e) {}
              return function () {
                if (emailTinymceVarToggleApi[tk] === api) emailTinymceVarToggleApi[tk] = null;
              };
            }
          });
        }
      }
    };
  }

  function startEmailTinymceForKey(templateKey) {
    if (!templateKey || !window.tinymce) return;
    var vId = templateKey + '-visual';
    if (getEmailTinymceForKey(templateKey)) return;
    var visTa = document.getElementById(vId);
    if (!visTa) return;
    if (!visTa.parentNode || (visTa.closest('.email-template-editor') && visTa.closest('.email-template-editor').style.display === 'none')) return;
    try {
      tinymce.init(Object.assign({
        init_instance_callback: function (ed) {
          var b = ed.getBody();
          if (b) b.setAttribute('spellcheck', 'true');
          /* Re-apply the full source so <head><style>…</head> is kept (html format can drop it). */
          if (visTa && visTa.value) {
            setEmailTinymceContentPreservingDocument(ed, visTa.value, templateKey);
          }
          b = ed.getBody();
          if (b) {
            var mainT = document.getElementById(templateKey);
            if (mainT) {
              var clang = mainT.dataset.currentLang || 'en';
              var dr = isEmailTemplateRtlLang(clang) ? 'rtl' : 'ltr';
              b.setAttribute('dir', dr);
              b.style.direction = dr;
              b.setAttribute('lang', clang);
            }
          }
        }
      }, buildTinymceEmailOptions(templateKey)));
    } catch (e) {
      if (window.console && console.warn) console.warn('TinyMCE init', e);
    }
  }

  function loadEmailTemplateVisualInEditor(editorBlock) {
    if (!editorBlock) return;
    var templateKey = getTemplateKeyFromEditorBlock(editorBlock);
    if (!templateKey) return;
    var mainTa = document.getElementById(templateKey);
    var visTa = document.getElementById(templateKey + '-visual');
    if (!visTa) return;
    setEmailTinymceVarMode(templateKey, 'placeholders');
    setEmailTinymceVarToggleVisual(templateKey, false);
    var html = '';
    if (mainTa) html = mainTa.value;
    if (!html.trim() && templateLangData[templateKey] && mainTa) {
      var l = mainTa.dataset.currentLang || 'en';
      if (templateLangData[templateKey][l] != null) {
        html = String(templateLangData[templateKey][l]);
      }
    }
    visTa.value = html;
    var existing = getEmailTinymceForKey(templateKey);
    if (existing) {
      setEmailTinymceContentPreservingDocument(existing, html, templateKey);
      var b = existing.getBody();
      if (b && mainTa) {
        var clang = mainTa.dataset.currentLang || 'en';
        var dr = isEmailTemplateRtlLang(clang) ? 'rtl' : 'ltr';
        b.setAttribute('dir', dr);
        b.style.direction = dr;
        b.setAttribute('lang', clang);
      }
      return;
    }
    loadTinymceIfNeeded(function () {
      if (typeof window.tinymce === 'undefined') {
        if (window.showAlert) {
          window.showAlert(cfg.t.editorLoadFailed, 'error');
        }
        return;
      }
      startEmailTinymceForKey(templateKey);
    });
  }

  function syncActiveEmailTemplateToMap() {
    copyEmailTinymceToTextareaForAll();
    document.querySelectorAll('.email-template-editor').forEach(function (editor) {
      var textarea = editor.querySelector('textarea[id^="email_template_"]');
      if (!textarea) return;
      var key = textarea.id;
      var currentLang = textarea.dataset.currentLang || 'en';
      if (!templateLangData[key]) templateLangData[key] = {};
      templateLangData[key][currentLang] = textarea.value;
    });
  }

  function isEmailTemplateRtlLang(code) {
    if (!code || typeof code !== 'string') return false;
    var base = String(code).trim().toLowerCase().split('_')[0].split('-')[0];
    return (
      base === 'ar' || base === 'he' || base === 'iw' || base === 'fa' || base === 'ur' ||
      base === 'ps' || base === 'dv' || base === 'ckb' || base === 'sd' || base === 'ug'
    );
  }

  function applyEmailTemplateTextDirection(textarea) {
    if (!textarea) return;
    var lang = (textarea.dataset && textarea.dataset.currentLang) ? String(textarea.dataset.currentLang) : 'en';
    var rtl = isEmailTemplateRtlLang(lang);
    var dir = rtl ? 'rtl' : 'ltr';
    var wrap = textarea.closest('.email-template-edit-wrap');
    var surface = textarea.closest('.email-template-code-surface');
    textarea.setAttribute('dir', dir);
    textarea.setAttribute('lang', lang);
    if (wrap) {
      wrap.setAttribute('dir', dir);
      wrap.setAttribute('lang', lang);
    }
    if (surface) {
      surface.setAttribute('dir', dir);
    }
    var pre = wrap ? wrap.querySelector('.email-template-syntax-backdrop') : null;
    if (pre) {
      pre.setAttribute('dir', dir);
    }
  }

  var ETM_CLASS_EDIT = 'email-template-mode-btn email-template-mode-edit-btn inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-medium min-w-[4.75rem] border-0 transition-colors';
  var ETM_CLASS_VISUAL = 'email-template-mode-btn email-template-mode-visual-btn inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-medium min-w-[4.75rem] border-0 transition-colors';

  function updateEmailTemplateViewToggle() {
    var isEdit = emailTemplateViewMode === 'edit';
    document.querySelectorAll('.email-template-mode-edit-btn').forEach(function (btn) {
      btn.className = ETM_CLASS_EDIT + (isEdit
        ? ' bg-white text-blue-600 relative z-10'
        : ' bg-gray-50 text-gray-500 hover:text-gray-700 hover:bg-gray-100');
      btn.setAttribute('aria-pressed', isEdit ? 'true' : 'false');
    });
    document.querySelectorAll('.email-template-mode-visual-btn').forEach(function (btn) {
      btn.className = ETM_CLASS_VISUAL + (isEdit
        ? ' bg-gray-50 text-gray-500 hover:text-gray-700 hover:bg-gray-100'
        : ' bg-white text-blue-600 relative z-10');
      btn.setAttribute('aria-pressed', isEdit ? 'false' : 'true');
    });
  }

  function setEmailTemplateViewMode(mode) {
    if (mode !== 'edit' && mode !== 'visual') return;
    emailTemplateViewMode = mode;
    updateEmailTemplateViewToggle();
    applyEmailTemplateViewMode();
  }

  function applyEmailTemplateViewMode() {
    var activeKey = getActiveTemplateSelectorValue();
    document.querySelectorAll('.email-template-editor').forEach(function (ed) {
      var key = getTemplateKeyFromEditorBlock(ed);
      var isActive = activeKey && ed.id === 'editor-' + activeKey;
      var editPane = ed.querySelector('.email-template-edit-pane');
      var visPane = ed.querySelector('.email-template-visual-pane');
      if (!editPane || !visPane) return;
      if (!isActive) {
        copyEmailTinymceToTextareaByKey(key);
        destroyEmailTinymceByKey(key);
        editPane.classList.remove('hidden');
        visPane.classList.add('hidden');
        return;
      }
      if (emailTemplateViewMode === 'edit') {
        copyEmailTinymceToTextareaByKey(key);
        destroyEmailTinymceByKey(key);
        editPane.classList.remove('hidden');
        visPane.classList.add('hidden');
        var taEdit = ed.querySelector('.email-template-body-textarea');
        if (taEdit) {
          setTimeout(function () { updateEmailTemplateSyntaxHighlight(taEdit); }, 0);
        }
      } else {
        editPane.classList.add('hidden');
        visPane.classList.remove('hidden');
        loadEmailTemplateVisualInEditor(ed);
      }
    });
  }

  function setEmailAutotransVisibleForKey(templateKey) {
    if (!templateKey) return;
    document.querySelectorAll('.email-template-autotrans-wrap').forEach(function (w) {
      var key = w.getAttribute('data-template-key') || '';
      if (key !== templateKey) {
        w.classList.add('hidden');
        return;
      }
      var ta = document.getElementById(key);
      var lang = (ta && ta.dataset && ta.dataset.currentLang) || 'en';
      if (lang === 'en') w.classList.add('hidden');
      else w.classList.remove('hidden');
    });
  }

  /* ── Template selector (dropdown) ── */
  function showEmailTemplate(templateKey) {
    document.querySelectorAll('.email-template-editor').forEach(function (ed) {
      ed.style.display = 'none';
    });
    if (templateKey) {
      var el = document.getElementById('editor-' + templateKey);
      if (el) el.style.display = 'block';
    }
    applyEmailTemplateViewMode();
    setEmailAutotransVisibleForKey(templateKey);
    if (templateKey) {
      var taActive = document.getElementById(templateKey);
      if (taActive) applyEmailTemplateTextDirection(taActive);
    }
  }

  function getActiveTemplateSelectorValue() {
    var campaignPanel = document.getElementById('panel-campaign-emails');
    var campaignSel = document.getElementById('campaign-email-template-selector');
    if (campaignPanel && campaignSel && !campaignPanel.classList.contains('hidden')) {
      return campaignSel.value;
    }
    var sel = document.getElementById('email-template-selector');
    return sel ? sel.value : '';
  }

  var selector = document.getElementById('email-template-selector');
  if (selector) {
    selector.addEventListener('change', function () { showEmailTemplate(this.value); });
    if (selector.value) {
      showEmailTemplate(selector.value);
    }
  }
  var campaignSelector = document.getElementById('campaign-email-template-selector');
  if (campaignSelector) {
    campaignSelector.addEventListener('change', function () { showEmailTemplate(this.value); });
  }
  updateEmailTemplateViewToggle();

  /* ── Language tab switching ── */
  function switchLangClasses(btn, active) {
    if (active) {
      btn.classList.add('border-blue-500', 'text-blue-600');
      btn.classList.remove('border-transparent', 'text-gray-500', 'hover:text-gray-700', 'hover:border-gray-300');
    } else {
      btn.classList.remove('border-blue-500', 'text-blue-600');
      btn.classList.add('border-transparent', 'text-gray-500', 'hover:text-gray-700', 'hover:border-gray-300');
    }
  }

  document.querySelectorAll('.email-lang-tab').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var templateKey = this.dataset.templateKey;
      var lang        = this.dataset.lang;
      var textarea    = document.getElementById(templateKey);
      if (!textarea || !templateKey) return;

      var currentLang = textarea.dataset.currentLang || 'en';
      if (!templateLangData[templateKey]) templateLangData[templateKey] = {};
      if (emailTemplateViewMode === 'visual' && getEmailTinymceForKey(templateKey)) {
        if (getEmailTinymceVarMode(templateKey) === 'values') {
          templateLangData[templateKey][currentLang] = textarea.value;
        } else {
          var m0 = getEmailTinymceForKey(templateKey);
          if (m0) {
            templateLangData[templateKey][currentLang] = rebuildCurrentEmailFromTinymce(templateKey);
          } else {
            templateLangData[templateKey][currentLang] = textarea.value;
          }
        }
      } else {
        templateLangData[templateKey][currentLang] = textarea.value;
      }
      emailTemplatesDirty = true;

      textarea.value = templateLangData[templateKey][lang] || '';
      textarea.dataset.currentLang = lang;

      var tabRow = this.closest('[data-lang-tabs-for]');
      if (tabRow) {
        tabRow.querySelectorAll('.email-lang-tab').forEach(function (t) {
          switchLangClasses(t, t.dataset.lang === lang);
        });
      }

      if (emailTemplateViewMode === 'visual') {
        var edLang = document.getElementById('editor-' + templateKey);
        if (edLang) loadEmailTemplateVisualInEditor(edLang);
      } else {
        updateEmailTemplateSyntaxHighlight(textarea);
      }
      applyEmailTemplateTextDirection(textarea);
      setEmailAutotransVisibleForKey(templateKey);
    });
  });

  /* Edit / visual: one state; buttons duplicated per template — delegate from Emails panel */
  (function initEmailViewToggle() {
    document.querySelectorAll('.email-templates-panel').forEach(function (panel) {
      if (!panel) return;
      panel.addEventListener('click', function (e) {
        var btn = e.target.closest('.email-template-mode-btn');
        if (!btn || !panel.contains(btn)) return;
        var mode = btn.getAttribute('data-mode');
        if (mode === 'edit') setEmailTemplateViewMode('edit');
        else if (mode === 'visual') setEmailTemplateViewMode('visual');
      });
    });
  })();

  (function initEmailTemplateAutotrans() {
    document.querySelectorAll('.email-templates-panel').forEach(function (panel) {
      if (!panel) return;

    panel.addEventListener('click', function (e) {
      var btn = e.target.closest('.email-template-autotrans-btn');
      if (!btn || !panel.contains(btn)) return;
      if (!window.AutoTranslateService || typeof window.AutoTranslateService.translate !== 'function') {
        var msg = cfg.t.autoTranslateUnavailable;
        if (window.showAlert) window.showAlert(msg, 'warning');
        else if (window.__clientWarn) window.__clientWarn(msg);
        return;
      }
      var templateKey = btn.getAttribute('data-template-key') || '';
      if (!templateKey) return;
      var textarea = document.getElementById(templateKey);
      if (!textarea) return;

      syncActiveEmailTemplateToMap();
      var currentLang = textarea.dataset.currentLang || 'en';
      if (currentLang === 'en') return;
      if (!templateLangData[templateKey]) templateLangData[templateKey] = {};
      var sourceEn = (templateLangData[templateKey]['en'] != null) ? String(templateLangData[templateKey]['en']) : '';
      if (!sourceEn.trim()) {
        if (window.showAlert) window.showAlert(MSG_EMAIL_AUTOTRANS_EN_EMPTY, 'warning');
        else if (window.__clientWarn) window.__clientWarn(MSG_EMAIL_AUTOTRANS_EN_EMPTY);
        return;
      }

      var origNodes = Array.from(btn.childNodes).map(function (n) { return n.cloneNode(true); });
      function restoreBtn() {
        btn.replaceChildren.apply(btn, origNodes.map(function (n) { return n.cloneNode(true); }));
        btn.classList.remove('btn-loading');
        btn.disabled = false;
      }
      btn.classList.add('btn-loading');
      btn.disabled = true;

      window.AutoTranslateService.translate({
        type: 'email_template_html',
        text: sourceEn,
        target_languages: [currentLang],
        permission_context: 'settings',
        permission_code: 'admin.settings.manage'
      }).then(function (res) {
        if (!res || !res.translations) {
          if (window.TranslationModalUtils) {
            window.TranslationModalUtils.showAutoTranslateError(
              btn,
              '',
              cfg.t.translationInvalidResponse,
              { originalNodes: origNodes, restoreDelayMs: 2000 }
            );
          } else { restoreBtn(); }
          return;
        }
        var translated = res.translations[currentLang];
        if (typeof translated !== 'string' || !translated.trim()) {
          if (window.TranslationModalUtils) {
            window.TranslationModalUtils.showAutoTranslateError(
              btn,
              '',
              (res && res.message) || cfg.t.noTranslationReturned,
              { originalNodes: origNodes, restoreDelayMs: 2500 }
            );
          } else { restoreBtn(); }
          return;
        }
        textarea.value = translated;
        if (!templateLangData[templateKey]) templateLangData[templateKey] = {};
        templateLangData[templateKey][currentLang] = translated;
        emailTemplatesDirty = true;
        updateEmailTemplateSyntaxHighlight(textarea);
        if (emailTemplateViewMode === 'visual') {
          var ed = document.getElementById('editor-' + templateKey);
          if (ed) loadEmailTemplateVisualInEditor(ed);
        }
        restoreBtn();
      }).catch(function (err) {
        if (window.TranslationModalUtils) {
          window.TranslationModalUtils.showAutoTranslateError(
            btn,
            '',
            (err && err.message) || cfg.t.translationRequestFailed,
            { originalNodes: origNodes, restoreDelayMs: 2500 }
          );
        } else {
          restoreBtn();
        }
      });
    });
    });
  })();

  (function initEmailTemplateTestSend() {
    var panel = document.getElementById('panel-emails');
    var campaignPanel = document.getElementById('panel-campaign-emails');
    var modal = document.getElementById('email-template-test-send-modal');
    var recipientRoot = document.getElementById('email-template-test-recipient');
    var userWrap = document.getElementById('email-template-test-user-wrap');
    var userSelect = document.getElementById('email-template-test-user-select');
    var confirmBtn = modal ? modal.querySelector('.email-template-test-send-confirm') : null;
    if ((!panel && !campaignPanel) || !modal || !recipientRoot || !userWrap || !userSelect || !confirmBtn) return;
    if (!EMAIL_TEST_SEND_URL && !CAMPAIGN_EMAIL_TEST_SEND_URL) return;

    var currentUserEmail = (recipientRoot.getAttribute('data-current-user-email') || '').trim();
    var pendingSend = null;
    var select2Ready = false;

    function isOtherUserMode() {
      var other = modal.querySelector('input[name="email_test_recipient_mode"][value="user"]');
      return !!(other && other.checked && !other.disabled);
    }

    function initEmailTestUserSelect2() {
      var $ = window.jQuery;
      if (!$ || !$.fn || !$.fn.select2) return false;
      if ($(userSelect).data('select2')) return true;
      try {
        $(userSelect).select2({
          width: '100%',
          placeholder: cfg.t.selectUsers || '',
          allowClear: true,
          dropdownParent: $(modal)
        });
        select2Ready = true;
        return true;
      } catch (_) {
        return false;
      }
    }

    function resetRecipientForm() {
      var selfRadio = modal.querySelector('input[name="email_test_recipient_mode"][value="self"]');
      if (selfRadio) selfRadio.checked = true;
      userSelect.value = '';
      if (window.jQuery && window.jQuery(userSelect).data('select2')) {
        try { window.jQuery(userSelect).val('').trigger('change'); } catch (_) {}
      }
      syncRecipientUi();
    }

    function canConfirmSend() {
      if (isOtherUserMode()) return !!(userSelect.value || '').trim();
      return !!currentUserEmail;
    }

    function updateConfirmButtonState() {
      var ok = canConfirmSend();
      confirmBtn.disabled = !ok;
      confirmBtn.classList.toggle('opacity-50', !ok);
      confirmBtn.classList.toggle('cursor-not-allowed', !ok);
    }

    function syncRecipientUi() {
      var other = isOtherUserMode();
      userWrap.classList.toggle('hidden', !other);
      userSelect.disabled = !other;
      if (other) initEmailTestUserSelect2();
      updateConfirmButtonState();
    }

    function getEmailTestRecipientPayload() {
      if (!isOtherUserMode()) return {};
      var uid = userSelect.value ? parseInt(String(userSelect.value), 10) : 0;
      if (!uid || Number.isNaN(uid)) return null;
      return { recipient_user_id: uid };
    }

    function closeTestSendModal() {
      modal.classList.add('hidden');
      pendingSend = null;
      confirmBtn.classList.remove('btn-loading');
      updateConfirmButtonState();
    }

    function openTestSendModal(data) {
      pendingSend = data;
      resetRecipientForm();
      modal.classList.remove('hidden');
      if (!select2Ready) {
        var n = 0;
        var t = setInterval(function () {
          if (initEmailTestUserSelect2() || ++n >= 40) clearInterval(t);
        }, 100);
      }
      try { confirmBtn.focus(); } catch (_) {}
    }

    function restoreConfirmBtn() {
      confirmBtn.classList.remove('btn-loading');
      updateConfirmButtonState();
    }

    function executeTestSend() {
      if (!pendingSend) return;
      var recipientPayload = getEmailTestRecipientPayload();
      if (recipientPayload === null) {
        if (window.showAlert) window.showAlert(MSG_TEST_EMAIL_SELECT_USER, 'warning');
        return;
      }
      if (!canConfirmSend()) {
        var msg = isOtherUserMode() ? MSG_TEST_EMAIL_SELECT_USER : MSG_TEST_EMAIL_NO_ADDR;
        if (window.showAlert) window.showAlert(msg, 'warning');
        return;
      }

      var templateKey = pendingSend.templateKey;
      var lang = pendingSend.lang;
      var b64 = pendingSend.b64;
      var testSendUrl = getEmailTestSendUrlForKey(templateKey);
      if (!testSendUrl) {
        restoreConfirmBtn();
        if (window.showAlert) window.showAlert(cfg.t.couldNotPrepareEmailBody, 'error');
        return;
      }
      confirmBtn.classList.add('btn-loading');
      confirmBtn.disabled = true;

      var csrf = getCsrfForEmailPreview();
      var testBodyInner = Object.assign(
        { template_key: templateKey, html_b64: b64, template_language: lang },
        recipientPayload
      );
      var testBodyStr = wrapEmailTemplateApiJsonBody(testBodyInner);
      if (!testBodyStr) {
        restoreConfirmBtn();
        if (window.showAlert) window.showAlert(cfg.t.couldNotPrepareEmailBody, 'error');
        return;
      }
      _debugEmailSettingsApi('test-send request', {
        url: testSendUrl,
        template_key: templateKey,
        template_language: lang,
        body_wrapped: true,
        post_body_len: testBodyStr.length
      });
      ((window.getFetch && window.getFetch()) || fetch)(testSendUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': csrf,
          'X-Requested-With': 'XMLHttpRequest'
        },
        body: testBodyStr
      }).then(function (resp) {
        return window.responseAsResult(resp);
      }).then(function (result) {
        var p = result.payload || {};
        _debugEmailSettingsApi('test-send response', {
          ok: result.ok,
          httpStatus: result.status,
          success: p.success,
          sent_to: p.sent_to,
          subject: p.subject,
          error: p.error,
          message: p.message,
          payload: p
        });
        restoreConfirmBtn();
        if (result.ok && p.success) {
          closeTestSendModal();
          var to = p.sent_to || '';
          if (window.showAlert) {
            window.showAlert(MSG_TEST_EMAIL_SENT + (to ? ' ' + to : ''), 'success');
          }
          return;
        }
        var errMsg = (p && (p.error || p.message)) ? (p.error || p.message) : (MSG_TEST_EMAIL_FAIL + (result.status ? ' (' + result.status + ')' : ''));
        if (window.showAlert) window.showAlert(errMsg, 'error');
        else if (window.__clientWarn) window.__clientWarn(errMsg);
      }).catch(function (err) {
        _debugEmailSettingsApi('test-send error', { name: err && err.name, message: err && err.message });
        restoreConfirmBtn();
        if (window.showAlert) window.showAlert(cfg.t.networkErrorSendingEmail, 'error');
      });
    }

    modal.querySelectorAll('input[name="email_test_recipient_mode"]').forEach(function (radio) {
      radio.addEventListener('change', syncRecipientUi);
    });
    userSelect.addEventListener('change', updateConfirmButtonState);
    if (window.jQuery) {
      window.jQuery(userSelect).on('change select2:select select2:clear', updateConfirmButtonState);
    }

    modal.querySelectorAll('.email-template-test-send-cancel, .close-modal').forEach(function (btn) {
      btn.addEventListener('click', closeTestSendModal);
    });
    modal.addEventListener('click', function (e) {
      if (e.target === modal) closeTestSendModal();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && !modal.classList.contains('hidden')) closeTestSendModal();
    });
    confirmBtn.addEventListener('click', executeTestSend);

    function bindTestSendPanel(root) {
      if (!root) return;
      root.addEventListener('click', function (e) {
        var btn = e.target.closest('.email-template-test-send-btn, .campaign-email-template-test-send-btn');
        if (!btn || !root.contains(btn)) return;
        var templateKey = btn.getAttribute('data-template-key') || '';
        if (!templateKey) return;
        var textarea = document.getElementById(templateKey);
        if (!textarea) return;

        syncActiveEmailTemplateToMap();
        var lang = (textarea.dataset && textarea.dataset.currentLang) ? String(textarea.dataset.currentLang).trim() : 'en';
        var html = '';
        if (templateLangData[templateKey] && typeof templateLangData[templateKey][lang] === 'string') {
          html = templateLangData[templateKey][lang];
        } else {
          html = textarea.value;
        }
        var trimmed = (html || '').trim();
        if (!trimmed) {
          if (window.showAlert) window.showAlert(cfg.t.noTemplateContent, 'warning');
          return;
        }
        var b64;
        try {
          b64 = base64EncodeUtf8Preview(trimmed);
        } catch (err) {
          if (window.showAlert) window.showAlert(String(err), 'error');
          return;
        }
        if (!b64) {
          if (window.showAlert) window.showAlert(cfg.t.couldNotPrepareEmailBody, 'error');
          return;
        }
        openTestSendModal({ templateKey: templateKey, lang: lang, b64: b64 });
      });
    }

    bindTestSendPanel(panel);
    bindTestSendPanel(campaignPanel);

    syncRecipientUi();
  })();

  /* ── Seed default email templates (flask seed-email-templates) ── */
  (function initEmailTemplateSeed() {
    var gapsBtn = document.getElementById('email-templates-seed-gaps-btn');
    var forceBtn = document.getElementById('email-templates-seed-force-btn');
    var toggleBtn = document.getElementById('email-templates-seed-toggle');
    var seedMenu = document.getElementById('email-templates-seed-menu');
    if (!gapsBtn || !forceBtn || !toggleBtn || !seedMenu) return;

    function closeSeedMenu() {
      seedMenu.classList.add('hidden');
      toggleBtn.setAttribute('aria-expanded', 'false');
    }

    toggleBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      var isOpen = !seedMenu.classList.contains('hidden');
      seedMenu.classList.toggle('hidden', isOpen);
      toggleBtn.setAttribute('aria-expanded', String(!isOpen));
    });
    document.addEventListener('click', closeSeedMenu);
    seedMenu.addEventListener('click', function (e) { e.stopPropagation(); });

    function setBusy(yes, loadingBtn) {
      [toggleBtn, gapsBtn, forceBtn].forEach(function (b) {
        b.disabled = !!yes;
        if (yes) {
          if (loadingBtn && b === loadingBtn) b.classList.add('btn-loading');
          else b.classList.remove('btn-loading');
        } else {
          b.classList.remove('btn-loading');
        }
      });
    }

    function describeSeedStats(st) {
      st = st || {};
      var e = st.email || {};
      var parts = [];
      if (e.seeded != null || e.skipped != null) {
        parts.push(L_SEED_BODIES + ': ' + (e.seeded != null ? e.seeded : '0') + ' ' + L_SEED_UPD + ', ' + (e.skipped != null ? e.skipped : '0') + ' ' + L_SEED_LEFT);
      }
      return parts.join(' — ');
    }

    function doSeed(force, activeBtn) {
      if (force && !window.confirm(MSG_SEED_CONFIRM_FORCE)) return;
      setBusy(true, activeBtn);
      var headers = {
        'Content-Type': 'application/json',
        'X-CSRFToken': getCsrfForEmailPreview()
      };
      _debugEmailSettingsApi('seed request', { url: EMAIL_SEED_URL, force: !!force });
      ((window.getFetch && window.getFetch()) || fetch)(EMAIL_SEED_URL, {
        method: 'POST',
        headers: headers,
        body: JSON.stringify({ force: !!force })
      }).then(function (resp) {
        return window.responseAsResult(resp);
      }).then(function (r) {
        _debugEmailSettingsApi('seed response', { ok: r.ok, status: r.status, success: r.payload && r.payload.success, payload: r.payload || {} });
        setBusy(false);
        if (r.ok && r.payload && r.payload.success) {
          var line = describeSeedStats(r.payload.stats) || cfg.t.seedingCompleted;
          if (window.showAlert) {
            window.showAlert(line, 'success', null, function () { window.location.reload(); });
          } else {
            window.location.reload();
          }
          return;
        }
        var err = (r.payload && (r.payload.message || r.payload.error)) ? (r.payload.message || r.payload.error) : (cfg.t.seedingFailed + (r.status ? ' (' + r.status + ')' : ''));
        if (window.showAlert) window.showAlert(String(err), 'error');
        else if (window.__clientWarn) window.__clientWarn(String(err));
      }).catch(function (err) {
        _debugEmailSettingsApi('seed error', { name: err && err.name, message: err && err.message });
        setBusy(false);
        if (window.showAlert) window.showAlert(cfg.t.networkErrorSeeding, 'error');
      });
    }
    gapsBtn.addEventListener('click', function () {
      closeSeedMenu();
      doSeed(false, toggleBtn);
    });
    forceBtn.addEventListener('click', function () {
      closeSeedMenu();
      doSeed(true, toggleBtn);
    });
  })();

  /* ── Seed default campaign email templates ── */
  (function initCampaignEmailTemplateSeed() {
    var gapsBtn = document.getElementById('campaign-email-templates-seed-gaps-btn');
    var forceBtn = document.getElementById('campaign-email-templates-seed-force-btn');
    var toggleBtn = document.getElementById('campaign-email-templates-seed-toggle');
    var seedMenu = document.getElementById('campaign-email-templates-seed-menu');
    if (!gapsBtn || !forceBtn || !toggleBtn || !seedMenu || !CAMPAIGN_EMAIL_SEED_URL) return;

    function closeSeedMenu() {
      seedMenu.classList.add('hidden');
      toggleBtn.setAttribute('aria-expanded', 'false');
    }

    toggleBtn.addEventListener('click', function (e) {
      e.stopPropagation();
      var isOpen = !seedMenu.classList.contains('hidden');
      seedMenu.classList.toggle('hidden', isOpen);
      toggleBtn.setAttribute('aria-expanded', String(!isOpen));
    });
    document.addEventListener('click', closeSeedMenu);
    seedMenu.addEventListener('click', function (e) { e.stopPropagation(); });

    function setBusy(yes, loadingBtn) {
      [toggleBtn, gapsBtn, forceBtn].forEach(function (b) {
        b.disabled = !!yes;
        if (yes) {
          if (loadingBtn && b === loadingBtn) b.classList.add('btn-loading');
          else b.classList.remove('btn-loading');
        } else {
          b.classList.remove('btn-loading');
        }
      });
    }

    function describeSeedStats(st) {
      st = st || {};
      var e = st.email || {};
      if (e.seeded != null || e.skipped != null) {
        return L_SEED_BODIES + ': ' + (e.seeded != null ? e.seeded : '0') + ' ' + L_SEED_UPD + ', ' + (e.skipped != null ? e.skipped : '0') + ' ' + L_SEED_LEFT;
      }
      return '';
    }

    function doSeed(force, activeBtn) {
      if (force && !window.confirm(MSG_SEED_CONFIRM_FORCE)) return;
      setBusy(true, activeBtn);
      ((window.getFetch && window.getFetch()) || fetch)(CAMPAIGN_EMAIL_SEED_URL, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCsrfForEmailPreview()
        },
        body: JSON.stringify({ force: !!force })
      }).then(function (resp) {
        return window.responseAsResult(resp);
      }).then(function (r) {
        setBusy(false);
        if (r.ok && r.payload && r.payload.success) {
          var line = describeSeedStats(r.payload.stats) || cfg.t.seedingCompleted;
          if (window.showAlert) {
            window.showAlert(line, 'success', null, function () { window.location.reload(); });
          } else {
            window.location.reload();
          }
          return;
        }
        var err = (r.payload && (r.payload.message || r.payload.error)) ? (r.payload.message || r.payload.error) : (cfg.t.seedingFailed + (r.status ? ' (' + r.status + ')' : ''));
        if (window.showAlert) window.showAlert(String(err), 'error');
      }).catch(function () {
        setBusy(false);
        if (window.showAlert) window.showAlert(cfg.t.networkErrorSeeding, 'error');
      });
    }

    gapsBtn.addEventListener('click', function () {
      closeSeedMenu();
      doSeed(false, toggleBtn);
    });
    forceBtn.addEventListener('click', function () {
      closeSeedMenu();
      doSeed(true, toggleBtn);
    });
  })();

  document.addEventListener('settings-tab-activated', function (e) {
    if (!e.detail || e.detail.tab !== 'campaign-emails') return;
    var campaignSel = document.getElementById('campaign-email-template-selector');
    if (campaignSel && campaignSel.value && typeof showEmailTemplate === 'function') {
      showEmailTemplate(campaignSel.value);
    }
  });

  /* ── Sync in-memory data → hidden inputs on form submit ── */
  var form = document.getElementById('manage-settings-form');
  if (form) {
    form.addEventListener('submit', function () {
      try {
        copyEmailTinymceToTextareaForAll();
        document.querySelectorAll('.email-template-editor').forEach(function (editor) {
          var textarea    = editor.querySelector('textarea.email-template-body-textarea');
          var hiddenInput = editor.querySelector('input[type="hidden"][id$="-translations"]');
          if (!textarea || !hiddenInput) return;
          var key = textarea.id;
          if (!templateLangData[key]) templateLangData[key] = {};
          var currentLang = textarea.dataset.currentLang || 'en';
          templateLangData[key][currentLang] = textarea.value;
          var cleaned = {};
          for (var lang in templateLangData[key]) {
            if (templateLangData[key].hasOwnProperty(lang)) {
              var val = (templateLangData[key][lang] || '').trim();
              if (val) cleaned[lang] = val;
            }
          }
          hiddenInput.value = JSON.stringify(cleaned);
        });
        syncCampaignTemplateMetadataHidden();
      } catch (err) {
        if (typeof window.__clientWarn === 'function') {
          window.__clientWarn('[settings-save] email-template sync failed: ' + ((err && err.message) || err));
        } else if (window.console && console.warn) {
          console.warn('[settings-save] email-template sync failed', err);
        }
      }
    });
  }

  /* ── Variable insertion (HTML textarea or TinyMCE when Visual is active) ── */
  document.querySelectorAll('.insert-variable-btn').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var variable = this.getAttribute('data-variable');
      var targetId = this.getAttribute('data-target');
      if (emailTemplateViewMode === 'visual' && getEmailTinymceForKey(targetId)) {
        if (getEmailTinymceVarMode(targetId) === 'values') {
          var tEd0 = getEmailTinymceForKey(targetId);
          var phIns = getPlaceholderHtmlForTemplateKey(targetId);
          setEmailTinymceVarMode(targetId, 'placeholders');
          setEmailTinymceContentPreservingDocument(tEd0, phIns, targetId);
          setEmailTinymceVarToggleVisual(targetId, false);
          if (tEd0 && tEd0.getBody()) {
            var bIns = tEd0.getBody();
            var mIns = document.getElementById(targetId);
            if (mIns) {
              var cIns = mIns.dataset.currentLang || 'en';
              bIns.setAttribute('dir', isEmailTemplateRtlLang(cIns) ? 'rtl' : 'ltr');
              bIns.style.direction = isEmailTemplateRtlLang(cIns) ? 'rtl' : 'ltr';
            }
          }
        }
        var tEd = getEmailTinymceForKey(targetId);
        if (tEd) {
          tEd.insertContent(String(variable || ''), { format: 'raw' });
          tEd.focus();
          emailTemplatesDirty = true;
          return;
        }
        setEmailTemplateViewMode('edit');
      }
      var textarea = document.getElementById(targetId);
      if (!textarea) return;
      var start  = textarea.selectionStart;
      var end    = textarea.selectionEnd;
      var text   = textarea.value;
      textarea.value = text.substring(0, start) + variable + text.substring(end);
      textarea.focus();
      textarea.setSelectionRange(start + variable.length, start + variable.length);
      emailTemplatesDirty = true;
      updateEmailTemplateSyntaxHighlight(textarea);
    });
  });
})();

    // --- Block 10 (original lines 4122-4183) ---
/* ── Branding file inputs: Resource edit page pattern (chosen file name + clear) ── */
(function () {
  'use strict';
  function wireFileInput(inputId, indicatorId) {
    var inp = document.getElementById(inputId);
    var ind = document.getElementById(indicatorId);
    if (!inp || !ind) return;
    var nameEl = ind.querySelector('.name-text');
    var clearBtn = ind.querySelector('button');
    inp.addEventListener('change', function () {
      if (inp.files && inp.files.length > 0) {
        if (nameEl) nameEl.textContent = inp.files[0].name;
        ind.classList.add('visible');
      } else {
        ind.classList.remove('visible');
        if (nameEl) nameEl.textContent = '';
      }
    });
    if (clearBtn) {
      clearBtn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        inp.value = '';
        ind.classList.remove('visible');
        if (nameEl) nameEl.textContent = '';
      });
    }
  }
  wireFileInput('branding-logo-file', 'branding-logo-selected');
  wireFileInput('branding-favicon-file', 'branding-favicon-selected');

  /* Replaces inline ``onerror="…"`` (which is blocked by strict CSP) on the brand-preview
     thumbnails: when the saved image fails to load, hide it and show the fallback caption. */
  document.querySelectorAll('img[data-brand-preview-img]').forEach(function (img) {
    img.addEventListener('error', function () {
      img.style.display = 'none';
      var wrap = img.closest('.brand-preview-thumb');
      if (!wrap) return;
      var fb = wrap.querySelector('[data-brand-preview-fallback]');
      if (fb) fb.style.display = 'block';
    });
  });

  /* Browsers scroll focused controls into view; hidden file inputs at end of long forms jump the page — restore scroll. */
  ['branding-logo-file', 'branding-favicon-file'].forEach(function (fid) {
    var inp = document.getElementById(fid);
    if (!inp) return;
    inp.addEventListener(
      'focus',
      function () {
        var sx = window.scrollX !== undefined ? window.scrollX : (document.documentElement && document.documentElement.scrollLeft);
        var sy = window.scrollY !== undefined ? window.scrollY : (document.documentElement && document.documentElement.scrollTop);
        requestAnimationFrame(function () {
          window.scrollTo(sx, sy);
        });
      },
      true
    );
  });
})();

    // --- Block 11 (original lines 4185-4724) ---
/* ── Settings save orchestrator (avoid WAF) ─────────────────────────────── */
(function () {
  'use strict';

  var LOG = '[settings-save]';
  /** Verbose traces: use window.__clientLog so CLIENT_CONSOLE_LOGGING is respected. */
  var _clientLogFallback = cfg.clientConsoleLogs || false;
  function log(step, extra) {
    var msg = LOG + ' ' + step + (extra !== undefined && extra !== null && extra !== '' ? ' ' + extra : '');
    if (typeof window.__clientLog === 'function') {
      window.__clientLog(msg);
      return;
    }
    if ((_clientLogFallback || window.CLIENT_CONSOLE_LOGGING) && window.console && console.log) {
      console.log(msg);
    }
  }

  var form = document.getElementById('manage-settings-form');
  if (!form) {
    log('init-skip', 'no #manage-settings-form');
    return;
  }
  log('init', 'bound');

  var noChangesMsg = cfg.t.noChanges;
  var emailSavedMsg = cfg.t.settingsSaved;

  /* The hidden inputs that back the chip-lists, the language-chip widget, and the
     email-template editors are written by per-section initializers running after
     ``DOMContentLoaded`` (and, for the language widget, after select2 finishes loading
     asynchronously). Snapshotting too early captures stale empty values, which makes the
     orchestrator's diff always include those keys even when the user did not touch them.
     ``ensureInitialSettingsSnapshot`` is idempotent and can be:
       * dispatched explicitly by an initializer once it has synced its hidden inputs
         (``document.dispatchEvent(new CustomEvent('settings:section-ready'))``); OR
       * captured after a hard fallback delay so we always have *some* baseline. */
  function ensureInitialSettingsSnapshot(reason) {
    if (window.__manageSettingsInitialJson) return;
    if (!window.formDataToJson) return;
    try {
      window.__manageSettingsInitialJson = window.formDataToJson(form);
      log('initial-snapshot', reason || '');
    } catch (err) {
      log('initial-snapshot-failed', (err && err.message) ? err.message : String(err));
    }
  }

  document.addEventListener('settings:section-ready', function () {
    /* Wait one tick so other near-simultaneous section-ready dispatches finish writing
       their hidden inputs before we snapshot. */
    setTimeout(function () { ensureInitialSettingsSnapshot('section-ready'); }, 0);
  });

  window.addEventListener('load', function () {
    /* Hard fallback: even if no initializer dispatches ``settings:section-ready`` (or it
       fires before this script bound the listener), capture after enough time for
       select2's retry loop (30 × 100ms in the language widget). */
    setTimeout(function () { ensureInitialSettingsSnapshot('load-fallback'); }, 1200);
  });

  /** Recursively sort object keys so two JSON blobs compare equal regardless of key order. */
  function sortKeysDeep(val) {
    if (val === null || typeof val !== 'object') return val;
    if (Array.isArray(val)) return val.map(sortKeysDeep);
    var out = {};
    Object.keys(val).sort().forEach(function (k) {
      out[k] = sortKeysDeep(val[k]);
    });
    return out;
  }

  /**
   * Canonical string for comparing JSON settings fields (translations, etc.).
   * Chip-list submit handlers may rewrite hidden JSON with different key ordering than the server HTML.
   */
  function canonicalJsonStringForCompare(s) {
    if (typeof s !== 'string') return null;
    var t = s.trim();
    if (!t || (t[0] !== '{' && t[0] !== '[')) return null;
    try {
      return JSON.stringify(sortKeysDeep(JSON.parse(t)));
    } catch (_) {
      return null;
    }
  }

  function settingsFieldEqual(key, a, b) {
    if (a === b) return true;
    if (typeof a === 'string' && typeof b === 'string') {
      var ca = canonicalJsonStringForCompare(a);
      var cb = canonicalJsonStringForCompare(b);
      if (ca !== null && cb !== null) return ca === cb;
    }

    var isArr = Array.isArray(a) || Array.isArray(b);
    var multiKey = (key.indexOf('[]') !== -1) || key === 'languages';
    if (isArr || multiKey) {
      function listNorm(x) {
        if (x === undefined || x === null) return [];
        if (Array.isArray(x)) return x.map(String);
        return [String(x)];
      }
      var la = listNorm(a);
      var lb = listNorm(b);
      if (la.length !== lb.length) return false;
      for (var i = 0; i < la.length; i++) if (la[i] !== lb[i]) return false;
      return true;
    }
    var sa = a === undefined || a === null ? '' : String(a);
    var sb = b === undefined || b === null ? '' : String(b);
    return sa === sb;
  }

  /* Names that the form renders as a single ``value="1"`` checkbox: when the user unchecks
     them, they vanish from FormData. ``diffSettingsPayload`` must convert that absence to
     "0" so the server-side partial-save merge actually flips the stored value (otherwise
     ``JSON.stringify`` drops the key and ``{...baseline, ...diff}`` keeps the old "1"). */
  var SETTINGS_CHECKBOX_PREFIXES = ['na_fp_', 'na_au_', 'na_sm_'];
  var SETTINGS_CHECKBOX_NAMES = {
    show_language_flags: true,
    restart: true,
    ai_beta_enabled: true,
    ai_settings_present: true,
    email_templates_present: true
  };

  function looksLikeFormCheckbox(form, key) {
    if (!form || !key) return false;
    if (SETTINGS_CHECKBOX_NAMES[key]) return true;
    for (var i = 0; i < SETTINGS_CHECKBOX_PREFIXES.length; i++) {
      if (key.indexOf(SETTINGS_CHECKBOX_PREFIXES[i]) === 0) return true;
    }
    /* AI section emits ``ai_<KEY>`` with value="1" for boolean toggles; clear-password
       inputs use ``ai_<KEY>_clear`` (also value="1"). Both vanish when unchecked. */
    if (key.indexOf('ai_') === 0) {
      try {
        var el = form.querySelector('input[type="checkbox"][name="' + escCssSelector(key) + '"]');
        if (el) return true;
      } catch (_) { /* invalid selector; ignore */ }
    }
    return false;
  }

  function diffSettingsPayload(initial, current, form) {
    var out = {};
    var keys = {};
    Object.keys(initial || {}).forEach(function (k) { keys[k] = true; });
    Object.keys(current || {}).forEach(function (k) { keys[k] = true; });
    Object.keys(keys).forEach(function (k) {
      if (settingsFieldEqual(k, initial[k], current[k])) return;
      var val = current[k];
      if (val === undefined || val === null || val === '') {
        /* Was a present-on-checked checkbox; now unchecked → must explicitly send "0"
           so the server merge writes false instead of preserving the baseline "1". */
        if (looksLikeFormCheckbox(form, k)) {
          val = '0';
        } else if (k.indexOf('[]') !== -1) {
          /* Multi-select cleared to empty: FormData omits the field entirely when no
             option is selected, so current[k] is undefined here. Send an explicit empty
             array so JSON.stringify does not drop the key and the server merge knows to
             clear the list (instead of preserving the baseline's previous values). */
          val = [];
        }
      }
      out[k] = val;
    });
    return out;
  }

  var savingLabel = cfg.t.savingLabel;
  var savingBtnHtml =
    '<span class="inline-flex items-center justify-center gap-2">' +
    '<span class="animate-spin inline-block w-4 h-4 border-2 border-white border-t-transparent rounded-full shrink-0" aria-hidden="true"></span>' +
    '<span>' + savingLabel + '</span></span>';

  function saveButton() {
    return document.getElementById('settings-save-btn') || form.querySelector('button[type="submit"]');
  }

  var SAVING_BTN_CLASSES = ['opacity-50', 'cursor-wait', 'pointer-events-none'];

  function setSaveButtonSaving(isSaving, restoreHtml) {
    var btn = saveButton();
    if (!btn) {
      log('button-missing');
      return;
    }
    if (isSaving) {
      btn.innerHTML = savingBtnHtml;
      btn.setAttribute('disabled', 'disabled');
      btn.disabled = true;
      btn.setAttribute('aria-busy', 'true');
      btn.setAttribute('aria-disabled', 'true');
      SAVING_BTN_CLASSES.forEach(function (c) { btn.classList.add(c); });
      log('ui-saving', 'disabled=' + String(btn.disabled));
      return;
    }
    SAVING_BTN_CLASSES.forEach(function (c) { btn.classList.remove(c); });
    if (restoreHtml != null) btn.innerHTML = restoreHtml;
    btn.removeAttribute('disabled');
    btn.disabled = false;
    btn.removeAttribute('aria-busy');
    btn.removeAttribute('aria-disabled');
    log('ui-restored');
  }

  function decodeEntities(s) {
    if (window.decodeHtmlEntities) return window.decodeHtmlEntities(s);
    if (!s) return '';
    var t = document.createElement('textarea');
    t.textContent = s;
    return t.value;
  }

  function base64EncodeUtf8(str) {
    try {
      return btoa(unescape(encodeURIComponent(String(str || ''))));
    } catch (_) {
      return '';
    }
  }

  function getCsrfToken() {
    var csrfMeta = document.querySelector('meta[name="csrf-token"]');
    if (csrfMeta && csrfMeta.getAttribute('content')) return csrfMeta.getAttribute('content');
    var csrfInput = form.querySelector('input[name="csrf_token"]');
    return csrfInput ? (csrfInput.value || '') : '';
  }

  var BRANDING_UPLOAD_URL = cfg.urls.brandingUpload;
  var BRANDING_UPLOAD_ENABLED = cfg.brandingUploadEnabled || false;

  async function uploadBrandingVisualAssetsIfNeeded() {
    if (!BRANDING_UPLOAD_ENABLED) return { ok: true, skipped: true };
    var logoInp = document.getElementById('branding-logo-file');
    var favInp = document.getElementById('branding-favicon-file');
    var lf = logoInp && logoInp.files && logoInp.files[0];
    var ff = favInp && favInp.files && favInp.files[0];
    if (!lf && !ff) return { ok: true, skipped: true };
    var fd = new FormData();
    fd.append('csrf_token', getCsrfToken());
    var hLogo = document.getElementById('org-branding-logo-path-hidden');
    var hFav = document.getElementById('org-branding-favicon-path-hidden');
    if (hLogo) fd.append('current_organization_logo_path', (hLogo.value || '').trim());
    if (hFav) fd.append('current_organization_favicon_path', (hFav.value || '').trim());
    if (lf) fd.append('organization_logo_file', lf);
    if (ff) fd.append('organization_favicon_file', ff);
    var fetchFn = (window.getFetch && window.getFetch()) || fetch;
    var resp = await fetchFn(BRANDING_UPLOAD_URL, {
      method: 'POST',
      body: fd,
      credentials: 'same-origin',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
        'X-CSRFToken': getCsrfToken()
      }
    });
    var payload = {};
    try { payload = await resp.json(); } catch (_) {}
    if (!resp.ok || !payload || payload.success !== true) {
      var msg = (payload && (payload.message || payload.msg)) ||
        ('Branding upload failed (' + resp.status + ')');
      throw new Error(msg);
    }
    var paths = payload.paths || {};
    if (paths.organization_logo_path && hLogo) {
      hLogo.value = paths.organization_logo_path;
      if (logoInp) logoInp.value = '';
    }
    if (paths.organization_favicon_path && hFav) {
      hFav.value = paths.organization_favicon_path;
      if (favInp) favInp.value = '';
    }
    return { ok: true, skipped: false, paths: paths };
  }

  function collectEmailTemplatesFromHidden() {
    // Each hidden input contains JSON { lang: html }
    var out = {};
    document.querySelectorAll('input[data-settings-email-template-hidden="1"]').forEach(function (inp) {
      var id = inp.id || '';
      if (!id || id.indexOf('-translations') === -1) return;
      var key = id.replace(/-translations$/, '');
      var parsed = {};
      try { parsed = JSON.parse(decodeEntities(inp.value || '') || '{}') || {}; } catch (_) { parsed = {}; }
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) parsed = {};
      out[key] = parsed;
    });
    return out;
  }

  function stableJson(obj) {
    try { return JSON.stringify(obj || {}); } catch (_) { return '{}'; }
  }

  async function saveEmailTemplatesIfChanged() {
    var currentTemplates = collectEmailTemplatesFromHidden();

    // Initial template values are already present in the hidden inputs on load; we compare raw JSON.
    var templatesInitialRaw = {};
    document.querySelectorAll('input[data-settings-email-template-hidden="1"]').forEach(function (inp) {
      var id = inp.id || '';
      var key = id.replace(/-translations$/, '');
      templatesInitialRaw[key] = (decodeEntities(inp.defaultValue || inp.value || '') || '').trim() || '{}';
    });

    var templatesNowRaw = {};
    Object.keys(currentTemplates || {}).forEach(function (k) {
      templatesNowRaw[k] = stableJson(currentTemplates[k]);
    });

    var templatesChanged = false;
    Object.keys(templatesNowRaw).forEach(function (k) {
      if ((templatesInitialRaw[k] || '{}') !== templatesNowRaw[k]) templatesChanged = true;
    });

    if (!templatesChanged) {
      return { success: true, skipped: true };
    }

    // Build base64 payload: { tpl_key: { lang: b64(html) } }
    var b64 = {};
    Object.keys(currentTemplates || {}).forEach(function (tplKey) {
      var langMap = currentTemplates[tplKey] || {};
      if (!langMap || typeof langMap !== 'object') return;
      b64[tplKey] = {};
      Object.keys(langMap).forEach(function (lang) {
        var html = langMap[lang];
        if (typeof html !== 'string') return;
        var trimmed = html.trim();
        if (!trimmed) return;
        b64[tplKey][lang] = base64EncodeUtf8(trimmed);
      });
    });

    var csrf = getCsrfToken();
    var resp = await ((window.getFetch && window.getFetch()) || fetch)(cfg.urls.apiEmailTemplates, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf
      },
      body: JSON.stringify({
        email_templates_b64: b64
      })
    });
    var payload = {};
    try { payload = await resp.json(); } catch (_) {}
    if (!resp.ok || !payload || payload.success !== true) {
      throw new Error((payload && payload.message) ? payload.message : ('Failed to save email templates (' + resp.status + ')'));
    }
    return { success: true, skipped: false };
  }

  function syncCampaignTemplateMetadataHidden() {
    var hidden = document.getElementById('campaign-template-metadata-json');
    if (!hidden) return;
    hidden.value = JSON.stringify(collectCampaignTemplateMetadataFromEditors());
  }

  function collectCampaignEmailTemplatesFromHidden() {
    var out = {};
    document.querySelectorAll('input[data-campaign-email-template-hidden="1"]').forEach(function (inp) {
      var id = inp.id || '';
      if (!id || id.indexOf('-translations') === -1) return;
      var key = id.replace(/-translations$/, '');
      var parsed = {};
      try { parsed = JSON.parse(decodeEntities(inp.value || '') || '{}') || {}; } catch (_) { parsed = {}; }
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) parsed = {};
      out[key] = parsed;
    });
    return out;
  }

  function collectCampaignTemplateMetadataFromEditors() {
    var out = {};
    document.querySelectorAll('.campaign-template-metadata-label').forEach(function (inp) {
      var key = inp.getAttribute('data-tpl-key');
      if (!key) return;
      if (!out[key]) out[key] = {};
      out[key].label = (inp.value || '').trim();
    });
    document.querySelectorAll('.campaign-template-metadata-priority').forEach(function (sel) {
      var key = sel.getAttribute('data-tpl-key');
      if (!key) return;
      if (!out[key]) out[key] = {};
      out[key].priority = (sel.value || 'normal').trim() || 'normal';
    });
    document.querySelectorAll('.campaign-template-metadata-title').forEach(function (inp) {
      var key = inp.getAttribute('data-tpl-key');
      if (!key) return;
      if (!out[key]) out[key] = {};
      out[key].compose_title = (inp.value || '').trim();
    });
    document.querySelectorAll('.campaign-template-metadata-message').forEach(function (ta) {
      var key = ta.getAttribute('data-tpl-key');
      if (!key) return;
      if (!out[key]) out[key] = {};
      out[key].compose_message = (ta.value || '').trim();
    });
    return out;
  }

  async function saveCampaignEmailTemplatesIfChanged() {
    if (!cfg.urls.campaignEmailTemplates) {
      return { success: true, skipped: true };
    }

    syncCampaignTemplateMetadataHidden();
    var currentTemplates = collectCampaignEmailTemplatesFromHidden();
    var currentMetadata = collectCampaignTemplateMetadataFromEditors();

    var templatesInitialRaw = {};
    document.querySelectorAll('input[data-campaign-email-template-hidden="1"]').forEach(function (inp) {
      var id = inp.id || '';
      var key = id.replace(/-translations$/, '');
      templatesInitialRaw[key] = (decodeEntities(inp.defaultValue || inp.value || '') || '').trim() || '{}';
    });

    var metadataHidden = document.getElementById('campaign-template-metadata-json');
    var metadataInitialRaw = metadataHidden
      ? (decodeEntities(metadataHidden.defaultValue || metadataHidden.value || '') || '').trim() || '{}'
      : '{}';

    var templatesNowRaw = {};
    Object.keys(currentTemplates || {}).forEach(function (k) {
      templatesNowRaw[k] = stableJson(currentTemplates[k]);
    });
    var metadataNowRaw = stableJson(currentMetadata);

    var templatesChanged = false;
    Object.keys(templatesNowRaw).forEach(function (k) {
      if ((templatesInitialRaw[k] || '{}') !== templatesNowRaw[k]) templatesChanged = true;
    });
    var metadataChanged = metadataInitialRaw !== metadataNowRaw;
    if (!templatesChanged && !metadataChanged) {
      return { success: true, skipped: true };
    }

    var b64 = {};
    Object.keys(currentTemplates || {}).forEach(function (tplKey) {
      var langMap = currentTemplates[tplKey] || {};
      if (!langMap || typeof langMap !== 'object') return;
      b64[tplKey] = {};
      Object.keys(langMap).forEach(function (lang) {
        var html = langMap[lang];
        if (typeof html !== 'string') return;
        var trimmed = html.trim();
        if (!trimmed) return;
        b64[tplKey][lang] = base64EncodeUtf8(trimmed);
      });
    });

    var csrf = getCsrfToken();
    var resp = await ((window.getFetch && window.getFetch()) || fetch)(cfg.urls.campaignEmailTemplates, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrf
      },
      body: JSON.stringify({
        email_templates_b64: b64,
        template_metadata: currentMetadata
      })
    });
    var payload = {};
    try { payload = await resp.json(); } catch (_) {}
    if (!resp.ok || !payload || payload.success !== true) {
      throw new Error((payload && payload.message) ? payload.message : ('Failed to save campaign email templates (' + resp.status + ')'));
    }
    return { success: true, skipped: false };
  }

  form.addEventListener('submit', async function (e) {
    e.preventDefault();
    if (form.dataset.settingsSaveInFlight === '1') {
      log('submit-blocked', 'already saving');
      return;
    }
    form.dataset.settingsSaveInFlight = '1';
    log('submit');

    var btn = saveButton();
    var originalSubmitHtml = btn ? btn.innerHTML : '';
    setSaveButtonSaving(true);

    try {
      log('email-templates');
      var emailTemplatesSaveResult = await saveEmailTemplatesIfChanged();
      log('email-templates-done');
      var campaignEmailTemplatesSaveResult = await saveCampaignEmailTemplatesIfChanged();
      log('campaign-email-templates-done');

      await uploadBrandingVisualAssetsIfNeeded();

      // Snapshot while email-template hiddens are still enabled so diff matches page-load snapshot.
      var currentPayloadSnapshot = window.formDataToJson ? window.formDataToJson(form) : null;
      if (!currentPayloadSnapshot) throw new Error('JSON payload helper is not available');

      // Second: submit the "light" settings without email-template blobs.
      // Ensure legacy flag stays off so backend doesn't expect those fields.
      var emailPresent = form.querySelector('input[name="email_templates_present"]');
      if (emailPresent) emailPresent.value = '0';

      // Temporarily disable hidden email-template inputs and metadata to keep request small.
      // try/finally below guarantees they are re-enabled even on network/JSON errors.
      var disabled = [];
      document.querySelectorAll('input[data-settings-email-template-hidden="1"], input[data-settings-email-metadata-hidden="1"], input[data-campaign-email-template-hidden="1"], input[data-campaign-email-metadata-hidden="1"]').forEach(function (inp) {
        if (!inp.disabled) {
          inp.disabled = true;
          disabled.push(inp);
        }
      });

      try {
        var fetchFn = (window.getFetch && window.getFetch()) || fetch;
        /* Read the freshest CSRF token (csrf.js periodically refreshes the meta tag but
           does not back-write into the form input), so long-open settings pages do not
           POST a stale token. */
        var csrfToken = getCsrfToken();
        var initialSnap = window.__manageSettingsInitialJson;
        var payloadObj;
        if (initialSnap && window.formDataToJson) {
          var diff = diffSettingsPayload(initialSnap, currentPayloadSnapshot, form);
          var changedKeys = Object.keys(diff).filter(function (k) { return k !== 'csrf_token'; });
          /* Email template JSON lives in inputs without a `name` attribute (WAF / size), so they are
             omitted from FormData and never appear in this diff. Email content is saved via the
             dedicated API above; when that ran, treat as a successful save even if changedKeys is empty. */
          var emailTemplatesPersisted = (emailTemplatesSaveResult && emailTemplatesSaveResult.skipped !== true)
            || (campaignEmailTemplatesSaveResult && campaignEmailTemplatesSaveResult.skipped !== true);
          if (changedKeys.length === 0) {
            delete form.dataset.settingsSaveInFlight;
            setSaveButtonSaving(false, originalSubmitHtml);
            if (emailTemplatesPersisted) {
              log('email-only-save');
              if (window.showAlert) window.showAlert(emailSavedMsg, 'success');
              window.location.reload();
              return;
            }
            log('no-changes');
            if (window.showAlert) window.showAlert(noChangesMsg, 'info');
            else if (typeof window.__clientWarn === 'function') window.__clientWarn(noChangesMsg);
            else console.warn(noChangesMsg);
            return;
          }
          diff.csrf_token = csrfToken;
          diff.settings_partial_save = '1';
          payloadObj = diff;
          log('partial-payload', String(changedKeys.length) + ' keys');
        } else {
          payloadObj = window.formDataToJson(form);
          log('full-payload-fallback');
        }
        if (!payloadObj) throw new Error('JSON payload helper is not available');
        // Encode the entire payload so WAF does not pattern-match rich strings (translations JSON, URLs, etc.)
        var payloadB64 = btoa(unescape(encodeURIComponent(JSON.stringify(payloadObj))));
        log('main-request');
        var resp = await fetchFn(form.action, {
          method: 'POST',
          body: JSON.stringify({ payload: payloadB64 }),
          credentials: 'same-origin',
          headers: {
            'X-Requested-With': 'XMLHttpRequest',
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
          }
        });

        if (!resp.ok) {
          throw new Error('Failed to save settings (' + resp.status + ')');
        }

        log('redirect', String(resp.status));
        window.location.href = (resp.redirected && resp.url) ? resp.url : form.action;
      } finally {
        /* Always re-enable so the user can retry without a page refresh, even if
           fetch threw, the response was non-OK, or we returned early. */
        disabled.forEach(function (inp) { inp.disabled = false; });
      }
    } catch (err) {
      delete form.dataset.settingsSaveInFlight;
      var m = (err && err.message) ? err.message : 'Failed to save settings';
      log('error', m);
      if (window.showAlert) window.showAlert(m, 'error'); else console.error(m);
      setSaveButtonSaving(false, originalSubmitHtml);
    }
  });
})();

    // --- Block 12 (original lines 4750-4906) ---
/* ── Provider tabs + drag-and-drop ───────────────────────────────────────── */
(function () {
  'use strict';

  var row = document.getElementById('provider-priority-row');
  var hiddenInput = document.getElementById('provider-priority-input');
  var panelsContainer = document.getElementById('provider-tab-panels');
  if (!row || !hiddenInput) return;

  var dragSrc = null;
  var justDragged = false;

  /* Show the panel for the given provider id and set active chip */
  function showProviderPanel(providerId) {
    var chips = row.querySelectorAll('.provider-priority-chip');
    var panels = panelsContainer ? panelsContainer.querySelectorAll('.provider-fields-panel') : [];

    chips.forEach(function (chip) {
      var isActive = chip.dataset.providerId === providerId;
      chip.classList.toggle('border-blue-500', isActive);
      chip.classList.toggle('bg-blue-50', isActive);
      chip.classList.toggle('text-blue-700', isActive);
      chip.classList.toggle('shadow-sm', isActive);
      chip.classList.toggle('border-gray-200', !isActive);
      chip.classList.toggle('bg-white', !isActive);
      chip.classList.toggle('text-gray-600', !isActive);
      chip.setAttribute('aria-selected', isActive ? 'true' : 'false');
      var circle = chip.querySelector('.provider-circle');
      if (circle) {
        circle.classList.toggle('bg-blue-200', isActive);
        circle.classList.toggle('text-blue-800', isActive);
        circle.classList.toggle('bg-gray-100', !isActive);
        circle.classList.toggle('text-gray-600', !isActive);
      }
    });

    panels.forEach(function (panel) {
      panel.classList.toggle('hidden', panel.dataset.providerId !== providerId);
    });
  }

  /* Update priority numbers after every reorder and sync hidden input */
  function updateState() {
    var chips = row.querySelectorAll('.provider-priority-chip');
    chips.forEach(function (chip, i) {
      var circle = chip.querySelector('.provider-circle');
      if (circle) circle.textContent = String(i + 1);
    });
    hiddenInput.value = JSON.stringify(
      Array.from(chips).map(function (c) { return c.dataset.providerId; })
    );
  }

  /* Also sync heading labels inside the provider form sections */
  function syncHeadingLabels() {
    var chips = row.querySelectorAll('.provider-priority-chip');
    chips.forEach(function (chip, i) {
      var pid = chip.dataset.providerId;
      var suffix = i === 0 ? ' (Primary)' : ' (Fallback)';
      var num = String(i + 1);
      var heading = document.querySelector(
        '#panel-ai [data-provider-heading="' + pid + '"]'
      );
      if (heading) heading.textContent = num + '. ' + heading.dataset.providerName + suffix;
    });
  }

  /* Tab click: show that provider's panel (unless we just finished a drag) */
  row.addEventListener('click', function (e) {
    var chip = e.target.closest('.provider-priority-chip');
    if (!chip) return;
    if (justDragged) {
      justDragged = false;
      return;
    }
    e.preventDefault();
    showProviderPanel(chip.dataset.providerId);
  });

  row.addEventListener('dragstart', function (e) {
    var chip = e.target.closest('.provider-priority-chip');
    if (!chip) return;
    dragSrc = chip;
    justDragged = true;
    chip.style.opacity = '0.4';
    chip.style.cursor = 'grabbing';
    try { e.dataTransfer.effectAllowed = 'move'; } catch (_) {}
  });

  row.addEventListener('dragend', function (e) {
    var chip = e.target.closest('.provider-priority-chip');
    if (chip) { chip.style.opacity = ''; chip.style.cursor = ''; }
    dragSrc = null;
  });

  row.addEventListener('dragover', function (e) {
    e.preventDefault();
    if (!dragSrc) return;
    var target = e.target.closest('.provider-priority-chip');
    if (!target || target === dragSrc) return;
    var rect = target.getBoundingClientRect();
    var insertBefore = e.clientX < rect.left + rect.width / 2;
    row.insertBefore(dragSrc, insertBefore ? target : target.nextSibling);
    updateState();
    syncHeadingLabels();
  });

  row.addEventListener('drop', function (e) { e.preventDefault(); });

  /* Touch fallback (mobile) */
  var touchDragSrc = null;
  var touchClone = null;
  row.addEventListener('touchstart', function (e) {
    var chip = e.target.closest('.provider-priority-chip');
    if (!chip) return;
    touchDragSrc = chip;
    touchClone = chip.cloneNode(true);
    touchClone.style.position = 'fixed';
    touchClone.style.opacity = '0.7';
    touchClone.style.pointerEvents = 'none';
    touchClone.style.zIndex = '9999';
    touchClone.style.minWidth = chip.offsetWidth + 'px';
    document.body.appendChild(touchClone);
    chip.style.opacity = '0.3';
  }, { passive: true });

  row.addEventListener('touchmove', function (e) {
    if (!touchClone || !touchDragSrc) return;
    var t = e.touches[0];
    touchClone.style.left = (t.clientX - touchClone.offsetWidth / 2) + 'px';
    touchClone.style.top  = (t.clientY - touchClone.offsetHeight / 2) + 'px';
    var chips = Array.from(row.querySelectorAll('.provider-priority-chip'));
    for (var i = 0; i < chips.length; i++) {
      var chip = chips[i];
      if (chip === touchDragSrc) continue;
      var rect = chip.getBoundingClientRect();
      if (t.clientX > rect.left && t.clientX < rect.right && t.clientY > rect.top && t.clientY < rect.bottom) {
        var insertBefore = t.clientX < rect.left + rect.width / 2;
        row.insertBefore(touchDragSrc, insertBefore ? chip : chip.nextSibling);
        break;
      }
    }
  }, { passive: true });

  row.addEventListener('touchend', function () {
    if (touchClone) { touchClone.remove(); touchClone = null; }
    if (touchDragSrc) {
      touchDragSrc.style.opacity = '';
      touchDragSrc = null;
      justDragged = true;
    }
    updateState();
    syncHeadingLabels();
  }, { passive: true });
})();

}());