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
  let activeDashboard = "combined";
  let loaded = false;
  let htmlCache = Object.create(null);

  function csrfHeaders() {
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
    if (!force && showFromCache(dashboardId)) return;
    setStatus("Loading visuals…");
    try {
      const data = await fetchJson(`/assignment/${aesId}/visuals?dashboard=${encodeURIComponent(dashboardId)}`, {
        headers: csrfHeaders(),
        credentials: "same-origin",
      });
      if (!data || data.success === false) {
        throw new Error((data && data.error) || "Could not load visuals");
      }
      rememberHtml(dashboardId, data);
      if (data.payload && data.payload.dashboards) renderTabs(data.payload.dashboards);
      loaded = true;
      if (!showFromCache(dashboardId) && body) body.innerHTML = data.html || "";
      setStatus("");
    } catch (err) {
      if (body) body.innerHTML = `<p class="upr-empty">Could not load visuals.</p>`;
      setStatus("");
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
})();
