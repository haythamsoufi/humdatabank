(function () {
  const panel = document.getElementById("upr-visuals-panel");
  if (!panel) return;

  const aesId = panel.dataset.aesId;
  const body = document.getElementById("upr-visuals-body");
  const statusEl = document.getElementById("upr-visuals-status");
  const tabsEl = document.getElementById("upr-visuals-tabs");
  const downloadBtn = document.getElementById("upr-visuals-download");
  const downloadMenu = document.getElementById("upr-visuals-download-menu");
  const downloadWrap = downloadBtn && downloadBtn.closest(".upr-visuals-download");
  const formArea = document.getElementById("sections-container");
  const toggleBtn = document.getElementById("upr-visuals-toggle");
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
    tabsEl.querySelectorAll(".upr-visuals-embed__tab").forEach((el) => {
      el.classList.toggle("is-active", el.dataset.dashboard === dashboardId);
    });
  }

  function showFromCache(dashboardId) {
    const html = htmlCache[dashboardId];
    if (html == null) return false;
    activeDashboard = dashboardId;
    markActiveTab(dashboardId);
    if (body) body.innerHTML = html;
    setStatus("");
    return true;
  }

  function renderTabs(dashboards) {
    if (shared.renderDashboardTabs) {
      shared.renderDashboardTabs({
        container: tabsEl,
        dashboards,
        activeId: activeDashboard,
        tablistId: "upr-visuals-tabs",
        onSelect: (id) => {
          if (id === activeDashboard) return;
          if (showFromCache(id)) return;
          loadDashboard(id);
        },
      });
      return;
    }
    if (!tabsEl) return;
    tabsEl.innerHTML = "";
    (dashboards || []).forEach((dash) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "upr-visuals-embed__tab" + (dash.id === activeDashboard ? " is-active" : "");
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
      const langUrl = shared.withLang ? shared.withLang(url) : url;
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
      if (!showFromCache(requested) && body) body.innerHTML = data.html || "";
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

  document.addEventListener("upr-visuals:languagechange", () => {
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
