(function (global) {
  function csrfToken() {
    if (typeof global.getCSRFToken === "function") {
      return global.getCSRFToken() || "";
    }
    return (
      document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") ||
      document.querySelector('input[name="csrf_token"]')?.value ||
      ""
    );
  }

  function csrfHeaders(extra) {
    const headers = Object.assign(
      { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
      extra || {}
    );
    const token = csrfToken();
    if (token) headers["X-CSRFToken"] = token;
    return headers;
  }

  function rememberHtml(cache, dashboardId, data) {
    const byId = data && data.html_by_dashboard;
    if (byId && typeof byId === "object") {
      Object.keys(byId).forEach((id) => {
        if (typeof byId[id] === "string") cache[id] = byId[id];
      });
    } else if (data && typeof data.html === "string") {
      cache[dashboardId] = data.html;
    }
    return cache;
  }

  function renderDashboardTabs({ container, dashboards, activeId, onSelect, tablistId }) {
    if (!container) return;
    container.replaceChildren();
    (dashboards || []).forEach((dash, index) => {
      const btn = document.createElement("button");
      btn.type = "button";
      const selected = dash.id === activeId;
      btn.className = "upr-visuals-embed__tab" + (selected ? " is-active" : "");
      btn.textContent = dash.title;
      btn.dataset.dashboard = dash.id;
      btn.setAttribute("role", "tab");
      btn.setAttribute("aria-selected", selected ? "true" : "false");
      if (tablistId) {
        btn.id = tablistId + "-" + dash.id;
        btn.setAttribute("aria-controls", tablistId.replace(/-tabs$/, "-body") || "");
      }
      btn.tabIndex = selected || (!activeId && index === 0) ? 0 : -1;
      btn.addEventListener("click", () => onSelect(dash.id));
      container.appendChild(btn);
    });
    bindTabOverflow(container);
  }

  function ensureTabOverflowButton(wrap, className, icon) {
    let button = wrap.querySelector("." + className);
    if (button) return button;
    button = document.createElement("button");
    button.type = "button";
    button.className = className;
    button.tabIndex = -1;
    button.setAttribute("aria-hidden", "true");
    button.innerHTML = '<i class="fas ' + icon + '" aria-hidden="true"></i>';
    wrap.appendChild(button);
    return button;
  }

  function updateTabOverflow(scroller) {
    const wrap = scroller && scroller.closest(".upr-visuals-embed__tabs-wrap");
    if (!wrap) return;
    const max = scroller.scrollWidth - scroller.clientWidth;
    wrap.classList.toggle("is-overflow-start", scroller.scrollLeft > 2);
    wrap.classList.toggle("is-overflow-end", max - scroller.scrollLeft > 2);
  }

  function bindTabOverflow(scroller) {
    if (!scroller) return;
    let wrap = scroller.closest(".upr-visuals-embed__tabs-wrap");
    if (!wrap) {
      wrap = document.createElement("div");
      wrap.className = "upr-visuals-embed__tabs-wrap";
      scroller.parentNode.insertBefore(wrap, scroller);
      wrap.appendChild(scroller);
    }
    const more = ensureTabOverflowButton(wrap, "upr-visuals-embed__tabs-more", "fa-chevron-right");
    const prev = ensureTabOverflowButton(wrap, "upr-visuals-embed__tabs-prev", "fa-chevron-left");
    if (scroller.dataset.uprOverflowBound !== "1") {
      scroller.dataset.uprOverflowBound = "1";
      const step = () => Math.max(scroller.clientWidth * 0.7, 160);
      more.addEventListener("click", () => {
        scroller.scrollBy({ left: step(), behavior: "smooth" });
      });
      prev.addEventListener("click", () => {
        scroller.scrollBy({ left: -step(), behavior: "smooth" });
      });
      scroller.addEventListener("scroll", () => updateTabOverflow(scroller), { passive: true });
      if (typeof ResizeObserver !== "undefined") {
        new ResizeObserver(() => updateTabOverflow(scroller)).observe(scroller);
      }
      window.addEventListener("resize", () => updateTabOverflow(scroller));
    }
    requestAnimationFrame(() => updateTabOverflow(scroller));
  }

  const LANG_STORAGE_KEY = "upr-visuals-export-lang";
  // Fallbacks must match i18n.RTL_LANGS / ARABIC_FONT_LANGS.
  const RTL_LANGS_FALLBACK = { ar: 1, fa: 1, he: 1, ur: 1 };
  const ARABIC_FONT_LANGS_FALLBACK = { ar: 1, fa: 1, ur: 1 };

  function normalizeLang(value) {
    const raw = String(value || "")
      .trim()
      .toLowerCase()
      .replace("_", "-");
    return raw.split("-")[0] || "";
  }

  function langSetFromSelect(attr, fallback) {
    const select = document.querySelector("[data-upr-lang-select]");
    const raw = select && select.getAttribute(attr);
    if (!raw) return fallback;
    const set = Object.create(null);
    String(raw)
      .split(",")
      .forEach((part) => {
        const code = normalizeLang(part);
        if (code) set[code] = 1;
      });
    return Object.keys(set).length ? set : fallback;
  }

  function isRtlLang(value) {
    const code = normalizeLang(value || getExportLanguage());
    return Boolean(langSetFromSelect("data-rtl-langs", RTL_LANGS_FALLBACK)[code]);
  }

  function isArabicFontLang(value) {
    const code = normalizeLang(value || getExportLanguage());
    return Boolean(langSetFromSelect("data-arabic-font-langs", ARABIC_FONT_LANGS_FALLBACK)[code]);
  }

  function applyExportDir(el) {
    if (!el) return;
    const code = getExportLanguage();
    el.dir = isRtlLang(code) ? "rtl" : "ltr";
    el.lang = code || "en";
    el.classList.toggle("upr-arabic-font", isArabicFontLang(code));
  }

  function storedExportLanguage() {
    try {
      return normalizeLang(global.localStorage && global.localStorage.getItem(LANG_STORAGE_KEY));
    } catch (_err) {
      return "";
    }
  }

  function getExportLanguage() {
    const select = document.querySelector("[data-upr-lang-select]");
    const fromSelect = normalizeLang(select && select.value);
    if (fromSelect) return fromSelect;
    const stored = storedExportLanguage();
    if (stored) return stored;
    const fallback = normalizeLang(
      (select && select.dataset.defaultLang) || document.documentElement.lang || "en"
    );
    return fallback || "en";
  }

  function getExportLanguageLabel() {
    const select = document.querySelector("[data-upr-lang-select]");
    const opt = select && select.options[select.selectedIndex];
    const text = ((opt && opt.textContent) || "").replace(/\s+/g, " ").trim();
    const withoutCode = text.replace(/\s*\([A-Za-z]{2,3}\)\s*$/, "").trim();
    return withoutCode || String(getExportLanguage() || "en").toUpperCase();
  }

  function updateNarrativeTranslateHints() {
    const lang = getExportLanguage();
    const label = getExportLanguageLabel();
    document.querySelectorAll("[data-upr-narrative-translate]").forEach((el) => {
      const template = el.getAttribute("data-template") || "";
      const show = Boolean(lang && lang !== "en" && template);
      el.hidden = !show;
      if (show) {
        el.textContent = template.replace("%(language)s", label).replace("{language}", label);
      }
    });
  }

  function setExportLanguage(lang) {
    const code = normalizeLang(lang);
    if (!code) return;
    try {
      if (global.localStorage) global.localStorage.setItem(LANG_STORAGE_KEY, code);
    } catch (_err) {
      /* ignore quota / private mode */
    }
    document.querySelectorAll("[data-upr-lang-select]").forEach((el) => {
      if (el.querySelector('option[value="' + code + '"]')) {
        el.value = code;
        if (global.jQuery && global.jQuery.fn && global.jQuery.fn.select2 && global.jQuery(el).data("select2")) {
          global.jQuery(el).val(code).trigger("change.select2");
        }
      }
    });
    updateNarrativeTranslateHints();
  }

  function formatElapsed(seconds) {
    const s = Math.max(0, Math.floor(Number(seconds) || 0));
    const m = Math.floor(s / 60);
    return m + ":" + String(s % 60).padStart(2, "0");
  }

  function newProgressId() {
    if (global.crypto && typeof global.crypto.randomUUID === "function") {
      return global.crypto.randomUUID();
    }
    return "p" + Date.now().toString(36) + Math.random().toString(36).slice(2, 10);
  }

  function _skelBone(className) {
    const el = document.createElement("div");
    el.className = "upr-vis-skel__bone " + className;
    return el;
  }

  function buildVisualsSkeleton() {
    const root = document.createElement("div");
    root.className = "upr-vis-skel";
    root.setAttribute("role", "status");
    root.setAttribute("aria-live", "polite");
    root.setAttribute("aria-busy", "true");
    const label = document.createElement("span");
    label.className = "upr-vis-skel__label";
    root.appendChild(label);

    const cover = document.createElement("div");
    cover.className = "upr-vis-skel__cover";
    cover.appendChild(_skelBone("upr-vis-skel__logo"));
    const titles = document.createElement("div");
    titles.className = "upr-vis-skel__titles";
    titles.appendChild(_skelBone("upr-vis-skel__line--lg"));
    titles.appendChild(_skelBone("upr-vis-skel__line--sm"));
    cover.appendChild(titles);
    cover.appendChild(_skelBone("upr-vis-skel__logo"));
    root.appendChild(cover);

    const kpis = document.createElement("div");
    kpis.className = "upr-vis-skel__kpis";
    for (let i = 0; i < 4; i += 1) kpis.appendChild(_skelBone("upr-vis-skel__kpi"));
    root.appendChild(kpis);

    const block = document.createElement("div");
    block.className = "upr-vis-skel__block";
    block.appendChild(_skelBone("upr-vis-skel__line--md"));
    [0.92, 0.7, 0.48, 0.32].forEach((width) => {
      const row = document.createElement("div");
      row.className = "upr-vis-skel__bar-row";
      row.appendChild(_skelBone("upr-vis-skel__bar-label"));
      const track = _skelBone("upr-vis-skel__bar-track");
      track.style.width = width * 100 + "%";
      track.style.flex = "0 1 " + width * 100 + "%";
      row.appendChild(track);
      block.appendChild(row);
    });
    root.appendChild(block);
    return root;
  }

  function showVisualsSkeleton(container, label) {
    if (!container) return;
    let root = container.querySelector(":scope > .upr-vis-skel");
    if (!root) {
      container.replaceChildren(buildVisualsSkeleton());
      root = container.querySelector(":scope > .upr-vis-skel");
    }
    const sr = root && root.querySelector(".upr-vis-skel__label");
    if (sr) sr.textContent = label || "Loading visuals…";
  }

  function formatVisualsProgress(i18n, data, elapsed) {
    const labels = i18n || {};
    const done = Math.max(0, Number(data && data.done) || 0);
    const total = Math.max(0, Number(data && data.total) || 0);
    const pending = Math.max(0, Number(data && data.pending) || Math.max(0, total - done));
    const clock = Math.max(0, Number(elapsed) || Number(data && data.elapsed) || 0);
    if (total > 0) {
      let text = (labels.translating || "Translating visuals… {done} of {total}")
        .replace("{done}", String(done))
        .replace("{total}", String(total));
      if (pending > 0) {
        const remain = (labels.remaining || "{pending} remaining").replace("{pending}", String(pending));
        text += " · " + remain;
      }
      if (clock > 0) text += " · " + formatElapsed(clock);
      return text;
    }
    const fallback = labels.loading || "Loading visuals…";
    return clock > 0 ? fallback + " · " + formatElapsed(clock) : fallback;
  }

  function watchVisualsProgress(aesId, progressId, onUpdate) {
    let stopped = false;
    const started = Date.now();
    const tick = () => {
      if (stopped) return;
      const url =
        "/assignment/" +
        encodeURIComponent(aesId) +
        "/visuals/progress?progress_id=" +
        encodeURIComponent(progressId);
      const apiFn = global.getApiFetch && global.getApiFetch();
      const req = apiFn
        ? apiFn(url, { headers: csrfHeaders(), credentials: "same-origin" })
        : fetch(url, { headers: csrfHeaders(), credentials: "same-origin" }).then((response) =>
            response.json()
          );
      Promise.resolve(req)
        .then((data) => {
          if (stopped) return;
          const rec = data && typeof data === "object" ? data : {};
          const elapsed = Math.max(
            Math.floor((Date.now() - started) / 1000),
            Number(rec.elapsed) || 0
          );
          onUpdate(rec, elapsed);
        })
        .catch(() => {});
    };
    const timer = setInterval(tick, 400);
    tick();
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }

  function withLang(url, lang) {
    const code = normalizeLang(lang) || getExportLanguage();
    const sep = url.indexOf("?") >= 0 ? "&" : "?";
    return url + sep + "lang=" + encodeURIComponent(code);
  }

  function matchLanguageOption(params, data) {
    const term = String((params && params.term) || "").trim().toLowerCase();
    if (!term) return data;
    if (data.children && data.children.length) {
      const children = data.children
        .map((child) => matchLanguageOption(params, child))
        .filter(Boolean);
      if (!children.length) return null;
      return Object.assign({}, data, { children });
    }
    const extra =
      (data.element && data.element.getAttribute && data.element.getAttribute("data-search-text")) || "";
    const haystack = [data.text, data.id, extra].join(" ").toLowerCase();
    return haystack.indexOf(term) !== -1 ? data : null;
  }

  function initLanguageSelects(root) {
    const scope = root || document;
    const selects = Array.from(scope.querySelectorAll("[data-upr-lang-select]"));
    if (!selects.length) return;
    const preferred = storedExportLanguage() || normalizeLang(selects[0].dataset.defaultLang) || "en";
    selects.forEach((select) => {
      if (select.dataset.uprLangBound === "1") return;
      select.dataset.uprLangBound = "1";
      if (select.querySelector('option[value="' + preferred + '"]')) {
        select.value = preferred;
      }
      if (global.jQuery && global.jQuery.fn && global.jQuery.fn.select2) {
        try {
          const $el = global.jQuery(select);
          $el.select2({
            width: "1.725rem",
            dropdownAutoWidth: false,
            dropdownCssClass: "upr-visuals-lang__dropdown",
            placeholder: select.dataset.placeholder || "Language",
            matcher: matchLanguageOption,
            templateSelection: function (data) {
              const code = String(data.id || "").toUpperCase();
              return code || data.text || "";
            },
            templateResult: function (data) {
              return data.text;
            },
          });
          const alignDropdown = () => {
            const s2 = $el.data("select2");
            const adapter = s2 && s2.dropdown;
            const chip = s2 && s2.$container && s2.$container[0];
            const host =
              (adapter && adapter.$dropdownContainer && adapter.$dropdownContainer[0]) ||
              (s2 && s2.$dropdown && s2.$dropdown[0]);
            const drop = host && (host.querySelector(".select2-dropdown") || host);
            if (!s2 || !chip || !host || !drop) return;
            const rect = chip.getBoundingClientRect();
            const area =
              chip.closest("#upr-visuals-panel, #upr-visuals-admin, .upr-vis-preview-pane, main") ||
              document.querySelector("main") ||
              document.documentElement;
            const box = area.getBoundingClientRect();
            const pad = 8;
            const minX = Math.max(pad, box.left + pad);
            const maxX = Math.min(window.innerWidth - pad, box.right - pad);
            const width = Math.min(256, Math.max(180, maxX - minX));
            let left = rect.right - width;
            if (left < minX) left = minX;
            if (left + width > maxX) left = Math.max(minX, maxX - width);
            host.style.setProperty("width", width + "px", "important");
            host.style.right = "auto";
            host.style.left = left + window.scrollX + "px";
            drop.style.setProperty("width", width + "px", "important");
            drop.style.setProperty("min-width", width + "px", "important");
            drop.style.setProperty("max-width", width + "px", "important");
          };
          const s2 = $el.data("select2");
          const adapter = s2 && s2.dropdown;
          if (adapter && !adapter._uprLangWidthLocked) {
            adapter._uprLangWidthLocked = true;
            const resize = adapter._resizeDropdown.bind(adapter);
            const position = adapter._positionDropdown.bind(adapter);
            adapter._resizeDropdown = function () {
              resize();
              alignDropdown();
            };
            adapter._positionDropdown = function () {
              position();
              requestAnimationFrame(alignDropdown);
            };
          }
          $el.on("select2:open", () => {
            requestAnimationFrame(alignDropdown);
            setTimeout(alignDropdown, 0);
            setTimeout(alignDropdown, 50);
          });
          const wrap = select.closest("[data-upr-lang-wrap]");
          const syncTitle = () => {
            const opt = select.options[select.selectedIndex];
            const label = (opt && opt.textContent || "").replace(/\s+/g, " ").trim();
            const code = String(select.value || "").toUpperCase();
            if (wrap) wrap.title = label || code;
            select.setAttribute("aria-label", label || code || select.dataset.placeholder || "Language");
          };
          $el.on("change select2:select", syncTitle);
          syncTitle();
        } catch (_err) {
          /* native select remains usable */
        }
      }
      const onChange = () => {
        const lang = normalizeLang(select.value) || "en";
        setExportLanguage(lang);
        document.dispatchEvent(new CustomEvent("upr-visuals:languagechange", { detail: { lang } }));
        updateNarrativeTranslateHints();
      };
      if (global.jQuery) {
        global.jQuery(select).on("change", onChange);
      } else {
        select.addEventListener("change", onChange);
      }
    });
    setExportLanguage(preferred);
    updateNarrativeTranslateHints();
  }

  function markActiveTab(container, dashboardId) {
    if (!container) return;
    container.querySelectorAll('[role="tab"], .upr-visuals-embed__tab').forEach((el) => {
      const selected = el.dataset.dashboard === dashboardId;
      el.classList.toggle("is-active", selected);
      if (el.getAttribute("role") === "tab") {
        el.setAttribute("aria-selected", selected ? "true" : "false");
        el.tabIndex = selected ? 0 : -1;
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => initLanguageSelects());
  } else {
    initLanguageSelects();
  }

  global.UprVisualsShared = {
    csrfToken,
    csrfHeaders,
    rememberHtml,
    renderDashboardTabs,
    markActiveTab,
    getExportLanguage,
    getExportLanguageLabel,
    updateNarrativeTranslateHints,
    setExportLanguage,
    initLanguageSelects,
    matchLanguageOption,
    withLang,
    isRtlLang,
    isArabicFontLang,
    applyExportDir,
    formatElapsed,
    newProgressId,
    formatVisualsProgress,
    watchVisualsProgress,
    showVisualsSkeleton,
  };
})(window);
