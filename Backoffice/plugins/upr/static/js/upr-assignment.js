(function () {
  const panel = document.getElementById("upr-panel");
  if (!panel) return;

  const aesId = panel.dataset.aesId;
  const body = document.getElementById("upr-body");
  const statusEl = document.getElementById("upr-status");
  const tabsEl = document.getElementById("upr-tabs");
  const downloadBtn = document.getElementById("upr-download");
  const downloadMenu = document.getElementById("upr-download-menu");
  const downloadWrap = downloadBtn && downloadBtn.closest(".upr-download");
  const formArea = document.getElementById("sections-container");
  const toggleBtn = document.getElementById("upr-toggle");
  const scopeRoot = document.getElementById("upr-scope");
  const scopeToggle = document.getElementById("upr-scope-toggle");
  const scopeMenu = document.getElementById("upr-scope-menu");
  const shared = window.UprVisualsShared || {};
  const i18n = {
    loading: panel.dataset.loading || "Loading visuals…",
    translating: panel.dataset.translating || "Translating visuals… {done} of {total}",
    remaining: panel.dataset.remaining || "{pending} remaining",
    failed: panel.dataset.failed || "Could not load visuals.",
  };
  let activeDashboard = "combined";
  let loaded = false;
  let htmlCache = Object.create(null);
  let bundleValue = "";

  window.UprVisualsScope = {
    query() {
      return bundleValue ? "bundle=" + encodeURIComponent(bundleValue) : "";
    },
    value() {
      return bundleValue;
    },
  };

  function csrfHeaders() {
    if (shared.csrfHeaders) return shared.csrfHeaders();
    const token =
      document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") ||
      document.querySelector('input[name="csrf_token"]')?.value ||
      "";
    const headers = { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" };
    if (token) headers["X-CSRFToken"] = token;
    return headers;
  }

  function fetchJson(url, opts) {
    const apiFn = window.getApiFetch && window.getApiFetch();
    if (apiFn) return apiFn(url, opts);
    const csrfFetch = window.getCsrfAwareFetch && window.getCsrfAwareFetch();
    return (csrfFetch || fetch)(url, opts).then(async (response) => {
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.success === false) {
        throw new Error(data.error || "Could not load visuals");
      }
      return data;
    });
  }

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text || "";
  }

  function showLoading(label) {
    setStatus("");
    if (shared.showVisualsSkeleton) {
      shared.showVisualsSkeleton(body, label || i18n.loading);
      return;
    }
    setStatus(label || i18n.loading);
  }

  function setToggleOpen(open) {
    toggleBtn?.classList.toggle("is-active", open);
    toggleBtn?.setAttribute("aria-pressed", open ? "true" : "false");
  }

  function showVisuals() {
    if (formArea) formArea.style.display = "none";
    panel.classList.add("is-visible");
    setToggleOpen(true);
    if (!loaded) loadReport();
  }

  function showForm() {
    panel.classList.remove("is-visible");
    setToggleOpen(false);
    if (formArea) formArea.style.display = "";
  }

  function markActiveTab(dashboardId) {
    if (shared.markActiveTab) {
      shared.markActiveTab(tabsEl, dashboardId);
      return;
    }
    if (!tabsEl) return;
    tabsEl.querySelectorAll(".upr-embed__tab").forEach((el) => {
      el.classList.toggle("is-active", el.dataset.dashboard === dashboardId);
    });
  }

  function setTrustedHtml(container, html) {
    if (shared.setTrustedHtml) {
      shared.setTrustedHtml(container, html);
      return;
    }
    if (!container) return;
    container.replaceChildren();
    const raw = html == null ? "" : String(html);
    if (!raw) return;
    const doc = new DOMParser().parseFromString(raw, "text/html");
    container.append(...Array.from(doc.body.childNodes));
  }

  function showFromCache(dashboardId) {
    const html = htmlCache[dashboardId];
    if (html == null) return false;
    activeDashboard = dashboardId;
    markActiveTab(dashboardId);
    setTrustedHtml(body, html);
    setStatus("");
    return true;
  }

  function renderTabs(dashboards) {
    if (shared.renderDashboardTabs) {
      shared.renderDashboardTabs({
        container: tabsEl,
        dashboards,
        activeId: activeDashboard,
        tablistId: "upr-tabs",
        onSelect: (id) => {
          if (id === activeDashboard) return;
          if (showFromCache(id)) return;
          loadDashboard(id);
        },
      });
      return;
    }
    if (!tabsEl) return;
    tabsEl.replaceChildren();
    (dashboards || []).forEach((dash) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "upr-embed__tab" + (dash.id === activeDashboard ? " is-active" : "");
      btn.textContent = dash.title;
      btn.dataset.dashboard = dash.id;
      btn.addEventListener("click", () => {
        if (dash.id === activeDashboard) return;
        if (showFromCache(dash.id)) return;
        loadDashboard(dash.id);
      });
      tabsEl.appendChild(btn);
    });
  }

  function rememberHtml(dashboardId, data) {
    if (shared.rememberHtml) {
      shared.rememberHtml(htmlCache, dashboardId, data);
      return;
    }
    const byId = data && data.html_by_dashboard;
    if (byId && typeof byId === "object") {
      Object.keys(byId).forEach((id) => {
        if (typeof byId[id] === "string") htmlCache[id] = byId[id];
      });
    } else if (data && typeof data.html === "string") {
      htmlCache[dashboardId] = data.html;
    }
  }

  async function loadDashboard(dashboardId, opts) {
    const force = !!(opts && opts.force);
    const requested = dashboardId;
    if (!force && showFromCache(requested)) return;
    activeDashboard = requested;
    showLoading(i18n.loading);
    const progressId = shared.newProgressId ? shared.newProgressId() : "";
    const stopWatch =
      progressId && shared.watchVisualsProgress
        ? shared.watchVisualsProgress(aesId, progressId, (rec, elapsed) => {
            if (shared.formatVisualsProgress) {
              showLoading(shared.formatVisualsProgress(i18n, rec, elapsed));
            }
          })
        : null;
    try {
      const url = `/assignment/${aesId}/visuals?dashboard=${encodeURIComponent(requested)}`;
      const langUrl = withScope(shared.withLang ? shared.withLang(url) : url);
      const progressUrl = progressId
        ? langUrl + (langUrl.indexOf("?") >= 0 ? "&" : "?") + "progress_id=" + encodeURIComponent(progressId)
        : langUrl;
      const data = await fetchJson(progressUrl, {
        headers: csrfHeaders(),
        credentials: "same-origin",
      });
      if (!data || data.success === false) {
        throw new Error((data && data.error) || i18n.failed);
      }
      rememberHtml(requested, data);
      if (data.payload && data.payload.dashboards) renderTabs(data.payload.dashboards);
      loaded = true;
      if (activeDashboard !== requested) return;
      if (!showFromCache(requested)) setTrustedHtml(body, data.html || "");
      setStatus("");
    } catch (err) {
      if (activeDashboard !== requested) return;
      if (body) {
        body.replaceChildren();
        const p = document.createElement("p");
        p.className = "upr-empty";
        p.textContent = i18n.failed;
        body.appendChild(p);
      }
      setStatus("");
    } finally {
      if (stopWatch) stopWatch();
    }
  }

  function loadReport(opts) {
    return loadDashboard(activeDashboard, opts);
  }

  function withScope(url) {
    const extra = window.UprVisualsScope ? window.UprVisualsScope.query() : "";
    if (!extra) return url;
    return url + (url.indexOf("?") >= 0 ? "&" : "?") + extra;
  }

  function scopeLabel(bundle) {
    const pattern = (scopeRoot && scopeRoot.dataset.countriesLabel) || "{count} countries";
    return pattern.replace("{count}", String(bundle.country_count || (bundle.countries || []).length));
  }

  function markScopeChecks() {
    if (!scopeMenu) return;
    scopeMenu.querySelectorAll("[data-bundle]").forEach((btn) => {
      const selected = (btn.dataset.bundle || "") === bundleValue;
      btn.setAttribute("aria-checked", selected ? "true" : "false");
      btn.classList.toggle("is-selected", selected);
    });
  }

  function setScopeOpen(open) {
    if (!scopeMenu || !scopeToggle || scopeToggle.hidden) return;
    scopeMenu.hidden = !open;
    scopeToggle.setAttribute("aria-expanded", open ? "true" : "false");
    scopeRoot?.classList.toggle("is-open", open);
  }

  function chooseScope(value) {
    const next = value || "";
    setScopeOpen(false);
    if (next === bundleValue) return;
    bundleValue = next;
    markScopeChecks();
    htmlCache = Object.create(null);
    loaded = false;
    activeDashboard = "combined";
    if (panel.classList.contains("is-visible")) loadReport({ force: true });
  }

  function renderScopeMenu(bundles) {
    if (!scopeMenu || !scopeToggle) return;
    scopeMenu.replaceChildren();
    const add = (value, title, detail, hint) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.setAttribute("role", "menuitemradio");
      btn.dataset.bundle = value;
      btn.className = "upr-scope__option";
      if (hint) btn.title = hint;
      const label = document.createElement("span");
      label.textContent = title;
      btn.appendChild(label);
      if (detail) {
        const note = document.createElement("span");
        note.className = "upr-scope__detail";
        note.textContent = detail;
        btn.appendChild(note);
      }
      btn.addEventListener("click", (event) => {
        event.stopPropagation();
        chooseScope(value);
      });
      scopeMenu.appendChild(btn);
    };
    add("", (scopeRoot && scopeRoot.dataset.thisCountry) || "This country", "", "");
    (bundles || []).forEach((bundle) => {
      if (!bundle || !bundle.value) return;
      const names = (bundle.countries || []).join(", ");
      add(String(bundle.value), String(bundle.value), scopeLabel(bundle), names);
    });
    const hasBundles = (bundles || []).some((bundle) => bundle && bundle.value);
    scopeToggle.hidden = !hasBundles;
    if (!hasBundles) setScopeOpen(false);
    markScopeChecks();
  }

  function loadScopeOptions() {
    if (!scopeToggle) return;
    fetchJson(`/assignment/${aesId}/visuals/bundles`, {
      headers: csrfHeaders(),
      credentials: "same-origin",
    })
      .then((data) => renderScopeMenu((data && data.bundles) || []))
      .catch(() => {
        if (scopeToggle) scopeToggle.hidden = true;
      });
  }

  scopeToggle?.addEventListener("click", (event) => {
    event.stopPropagation();
    setScopeOpen(scopeMenu ? scopeMenu.hidden : false);
  });
  document.addEventListener("click", (event) => {
    if (!scopeRoot || scopeRoot.contains(event.target)) return;
    setScopeOpen(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setScopeOpen(false);
  });
  loadScopeOptions();

  toggleBtn?.addEventListener("click", () => {
    if (panel.classList.contains("is-visible")) showForm();
    else showVisuals();
  });

  document.querySelectorAll("a.section-link").forEach((link) => {
    link.addEventListener("click", () => showForm());
  });

  if (window.UprVisualsDownload) {
    window.UprVisualsDownload.bindDownloadMenu({
      button: downloadBtn,
      menu: downloadMenu,
      wrap: downloadWrap,
      aesIdFn: () => aesId,
      dashboardFn: () => activeDashboard,
    });
  }

  document.addEventListener("formSubmitted", () => {
    if (!panel.classList.contains("is-visible")) return;
    htmlCache = Object.create(null);
    loadReport({ force: true });
  });

  document.addEventListener("upr:languagechange", () => {
    htmlCache = Object.create(null);
    if (shared.applyExportDir) shared.applyExportDir(body);
    if (panel.classList.contains("is-visible")) {
      loadReport({ force: true });
    } else {
      loaded = false;
    }
  });
  if (shared.applyExportDir) shared.applyExportDir(body);
})();
