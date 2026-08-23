(function () {
  const root = document.getElementById("upr-visuals-admin");
  if (!root) return;

  const i18n = (window.UprVisualsAdminConfig && window.UprVisualsAdminConfig.i18n) || {};
  const els = {
    assignment: document.getElementById("upr-vis-assignment"),
    dashboards: document.getElementById("upr-vis-dashboards"),
    countries: document.getElementById("upr-vis-countries"),
    dashCount: document.getElementById("upr-vis-dash-count"),
    countryCount: document.getElementById("upr-vis-country-count"),
    countrySearch: document.getElementById("upr-vis-country-search"),
    selectAll: document.getElementById("upr-vis-select-all"),
    selectNone: document.getElementById("upr-vis-select-none"),
    dashSelectAll: document.getElementById("upr-vis-dash-select-all"),
    dashSelectNone: document.getElementById("upr-vis-dash-select-none"),
    generate: document.getElementById("upr-vis-generate"),
    generateLabel: document.querySelector("[data-upr-generate-label]"),
    formats: document.getElementById("upr-vis-formats"),
    dashboardsCard: document.getElementById("upr-vis-dashboards-card"),
    narrativePanel: document.getElementById("upr-vis-narrative-panel"),
    includeNarrative: document.getElementById("upr-vis-include-narrative"),
    narrativeFilesWrap: document.getElementById("upr-vis-narrative-files-wrap"),
    narratives: document.getElementById("upr-vis-narratives"),
    cancel: document.getElementById("upr-vis-cancel"),
    status: document.getElementById("upr-vis-status"),
    pct: document.getElementById("upr-vis-pct"),
    progress: document.getElementById("upr-vis-progress"),
    progressBar: document.getElementById("upr-vis-progress-bar"),
    download: document.getElementById("upr-vis-download"),
    tabGenerate: document.getElementById("upr-vis-tab-generate"),
    tabPreview: document.getElementById("upr-vis-tab-preview"),
    paneGenerate: document.getElementById("upr-vis-pane-generate"),
    panePreview: document.getElementById("upr-vis-pane-preview"),
    previewCountry: document.getElementById("upr-vis-preview-country"),
    countryFilter: document.getElementById("upr-vis-country-filter"),
    previewTabs: document.getElementById("upr-vis-preview-tabs"),
    previewDownload: document.getElementById("upr-vis-preview-download"),
    previewDownloadMenu: document.getElementById("upr-vis-preview-download-menu"),
    previewStatus: document.getElementById("upr-vis-preview-status"),
    previewBody: document.getElementById("upr-vis-preview-body"),
  };
  const previewDownloadWrap =
    els.previewDownload && els.previewDownload.closest(".upr-visuals-download");
  const shared = window.UprVisualsShared || {};
  const POLL_INTERVAL_MS = 1500;
  const POLL_MAX_FAILURES = 5;
  const POLL_MAX_MS = 30 * 60 * 1000;
  let pollTimer = null;
  let pollFailures = 0;
  let pollStartedAt = 0;
  let jobId = null;
  let running = false;
  let booting = true;
  let previewDashboards = [];
  let previewHtmlCache = Object.create(null);
  let previewAesId = "";
  let previewDashboard = "combined";

  function t(key, vars) {
    let text = i18n[key] || key;
    if (vars) {
      Object.keys(vars).forEach((name) => {
        text = text.split("{" + name + "}").join(String(vars[name]));
      });
    }
    return text;
  }

  function csrfHeaders(json) {
    const headers = { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" };
    if (json !== false) headers["Content-Type"] = "application/json";
    if (shared.csrfHeaders) {
      return shared.csrfHeaders(headers);
    }
    const token = document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
    if (token) headers["X-CSRFToken"] = token;
    return headers;
  }

  function selectedFormat() {
    const input = els.formats && els.formats.querySelector('input[name="upr-vis-format"]:checked');
    return (input && input.value) || "png";
  }

  function includeNarrative() {
    return Boolean(els.includeNarrative && els.includeNarrative.checked && selectedFormat() !== "png");
  }

  function needsDashboards() {
    const format = selectedFormat();
    return format === "png" || (format === "pdf" && !includeNarrative());
  }

  function syncFormatUI() {
    const format = selectedFormat();
    if (els.formats) {
      els.formats.querySelectorAll(".upr-vis-chip").forEach((chip) => {
        const input = chip.querySelector("input[type=radio]");
        chip.classList.toggle("is-checked", Boolean(input && input.checked));
      });
    }
    if (els.narrativePanel) els.narrativePanel.hidden = format === "png";
    if (els.narrativeFilesWrap) els.narrativeFilesWrap.hidden = !includeNarrative();
    if (shared.updateNarrativeTranslateHints) shared.updateNarrativeTranslateHints();
    if (els.dashboardsCard) els.dashboardsCard.hidden = !needsDashboards();
    if (els.generate) {
      const labels = { png: t("generatePng"), pdf: t("generatePdf"), idml: t("generateIdml") };
      const text = els.generate.dataset["label" + format.charAt(0).toUpperCase() + format.slice(1)] || labels[format] || t("generatePng");
      if (els.generateLabel) els.generateLabel.textContent = text;
    }
    updateCounts();
  }

  function fetchFn(url, opts) {
    const csrfFetch = window.getCsrfAwareFetch && window.getCsrfAwareFetch();
    return (csrfFetch || fetch)(url, opts);
  }

  function emptyState(container, icon, message) {
    container.replaceChildren();
    const wrap = document.createElement("div");
    wrap.className = "upr-vis-empty";
    const ic = document.createElement("i");
    ic.className = "fas " + icon;
    ic.setAttribute("aria-hidden", "true");
    const p = document.createElement("p");
    p.textContent = message;
    wrap.append(ic, p);
    container.appendChild(wrap);
  }

  function selectedValues(container) {
    return Array.from(container.querySelectorAll("input[type=checkbox]:checked")).map((el) => el.value);
  }

  function visibleCountryChecks() {
    return Array.from(els.countries.querySelectorAll(".upr-vis-country")).filter((row) => row.style.display !== "none");
  }

  function updateCounts() {
    const dashInputs = els.dashboards.querySelectorAll("input[type=checkbox]");
    const countryInputs = els.countries.querySelectorAll("input[type=checkbox]");
    const dashSelected = els.dashboards.querySelectorAll("input[type=checkbox]:checked").length;
    const countrySelected = els.countries.querySelectorAll("input[type=checkbox]:checked").length;
    els.dashCount.textContent = dashInputs.length ? t("selectedCount", { selected: dashSelected, total: dashInputs.length }) : "";
    els.countryCount.textContent = countryInputs.length
      ? t("selectedCount", { selected: countrySelected, total: countryInputs.length })
      : "";
    const dashOk = needsDashboards() ? dashSelected > 0 : Boolean(els.assignment.value);
    const ready = Boolean(els.assignment.value) && dashOk && countrySelected > 0;
    if (els.generate) els.generate.disabled = running || !ready;
  }

  function setCountryToolsEnabled(on) {
    els.countrySearch.disabled = !on;
    els.selectAll.disabled = !on;
    els.selectNone.disabled = !on;
    if (!on) els.countrySearch.value = "";
  }

  function setDashToolsEnabled(on) {
    els.dashSelectAll.disabled = !on;
    els.dashSelectNone.disabled = !on;
  }

  function showProgress(tone, message, pct) {
    els.progress.classList.remove("hidden", "is-success", "is-error", "is-warn");
    if (tone) els.progress.classList.add(tone);
    els.status.textContent = message || "";
    if (typeof pct === "number") {
      els.pct.textContent = pct + "%";
      els.progressBar.style.width = pct + "%";
    }
  }

  function hideProgress() {
    els.progress.classList.add("hidden");
    els.progress.classList.remove("is-success", "is-error", "is-warn");
    els.status.textContent = "";
    els.pct.textContent = "";
    els.progressBar.style.width = "0%";
  }

  function setRunning(on) {
    running = on;
    els.assignment.disabled = on;
    els.countrySearch.disabled = on || !els.countries.querySelector("input");
    els.selectAll.disabled = on || !els.countries.querySelector("input");
    els.selectNone.disabled = on || !els.countries.querySelector("input");
    els.dashSelectAll.disabled = on || !els.dashboards.querySelector("input");
    els.dashSelectNone.disabled = on || !els.dashboards.querySelector("input");
    els.previewCountry.disabled = on || !els.previewCountry.querySelector("option[value]:not([value=''])");
    syncPreviewDownload();
    els.cancel.classList.toggle("hidden", !on);
    els.dashboards.querySelectorAll("input").forEach((input) => {
      input.disabled = on;
    });
    els.countries.querySelectorAll("input").forEach((input) => {
      input.disabled = on;
    });
    if (els.formats) {
      els.formats.querySelectorAll("input").forEach((input) => {
        input.disabled = on;
      });
    }
    if (els.includeNarrative) els.includeNarrative.disabled = on;
    if (els.narratives) els.narratives.disabled = on;
    updateCounts();
  }

  function clearSelection(message) {
    emptyState(els.dashboards, "fa-chart-pie", message);
    emptyState(els.countries, "fa-globe", message);
    els.dashCount.textContent = "";
    els.countryCount.textContent = "";
    setCountryToolsEnabled(false);
    setDashToolsEnabled(false);
    resetPreview();
    updateCounts();
  }

  function assignmentLabel(row) {
    return row.display_name || row.period_name || t("unnamedAssignment", { id: row.id });
  }

  async function loadAssignments() {
    els.assignment.disabled = true;
    clearSelection(t("loadingAssignments"));
    try {
      const response = await fetchFn("/admin/data-exploration/upr-visuals/assignments", {
        headers: csrfHeaders(),
        credentials: "same-origin",
      });
      const data = await response.json();
      if (!response.ok || data.success === false) {
        clearSelection(data.error || t("loadFailed"));
        return;
      }
      const rows = data.assignments || [];
      els.assignment.replaceChildren();
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = t("selectAssignment");
      els.assignment.appendChild(placeholder);

      rows.forEach((row) => {
        const opt = document.createElement("option");
        opt.value = row.id;
        opt.textContent = assignmentLabel(row);
        els.assignment.appendChild(opt);
      });

      if (!rows.length) {
        clearSelection(t("noAssignments"));
      } else {
        els.assignment.value = String(rows[0].id);
        await loadCountries();
      }
    } catch (err) {
      clearSelection(t("loadFailed"));
    } finally {
      els.assignment.disabled = false;
      updateCounts();
    }
  }

  async function loadCountries() {
    const assignedFormId = els.assignment.value;
    if (!assignedFormId) {
      clearSelection(t("selectAssignmentFirst"));
      return;
    }
    resetPreview();
    emptyState(els.dashboards, "fa-spinner fa-spin", t("loadingCountries"));
    emptyState(els.countries, "fa-spinner fa-spin", t("loadingCountries"));
    setCountryToolsEnabled(false);
    els.generate.disabled = true;
    try {
      const response = await fetchFn(
        shared.withLang
          ? shared.withLang(
              `/admin/data-exploration/upr-visuals/countries?assigned_form_id=${encodeURIComponent(assignedFormId)}`
            )
          : `/admin/data-exploration/upr-visuals/countries?assigned_form_id=${encodeURIComponent(assignedFormId)}`,
        { headers: csrfHeaders(), credentials: "same-origin" }
      );
      const data = await response.json();
      if (!response.ok || data.success === false) {
        clearSelection(data.error || t("loadFailed"));
        return;
      }

      els.dashboards.replaceChildren();
      (data.dashboards || []).forEach((dash) => {
        const label = document.createElement("label");
        label.className = "upr-vis-chip";
        const input = document.createElement("input");
        input.type = "checkbox";
        input.value = dash.id;
        input.checked = true;
        label.classList.toggle("is-checked", input.checked);
        input.addEventListener("change", () => {
          label.classList.toggle("is-checked", input.checked);
          updateCounts();
        });
        const title = document.createElement("span");
        title.textContent = dash.title;
        label.append(input, title);
        els.dashboards.appendChild(label);
      });
      if (!els.dashboards.querySelector("input")) {
        emptyState(els.dashboards, "fa-chart-pie", t("noDashboards"));
        setDashToolsEnabled(false);
      } else {
        setDashToolsEnabled(true);
      }

      els.countries.replaceChildren();
      (data.countries || []).forEach((row) => {
        const label = document.createElement("label");
        label.className = "upr-vis-country";
        const name = row.country_name || row.iso3 || String(row.aes_id);
        label.dataset.name = name.toLowerCase();
        label.dataset.iso = String(row.iso3 || "").toLowerCase();
        const input = document.createElement("input");
        input.type = "checkbox";
        input.value = String(row.aes_id);
        input.checked = true;
        input.addEventListener("change", updateCounts);
        const text = document.createElement("span");
        text.textContent = name;
        label.append(input, text);
        if (row.iso3) {
          const iso = document.createElement("span");
          iso.className = "upr-vis-iso";
          iso.textContent = row.iso3;
          label.appendChild(iso);
        }
        els.countries.appendChild(label);
      });
      if (!els.countries.querySelector("input")) {
        emptyState(els.countries, "fa-globe", t("noCountries"));
        setCountryToolsEnabled(false);
      } else {
        setCountryToolsEnabled(true);
      }
      previewDashboards = data.dashboards || [];
      fillPreviewCountries(data.countries || []);
      updateCounts();
      if (previewOpen()) loadPreview();
    } catch (err) {
      clearSelection(t("loadFailed"));
    }
  }

  function filterCountries() {
    const q = (els.countrySearch.value || "").trim().toLowerCase();
    Array.from(els.countries.querySelectorAll(".upr-vis-country")).forEach((row) => {
      const match = !q || row.dataset.name.includes(q) || row.dataset.iso.includes(q);
      row.style.display = match ? "" : "none";
    });
  }

  function setVisibleCountries(checked) {
    visibleCountryChecks().forEach((row) => {
      const input = row.querySelector("input[type=checkbox]");
      if (input) input.checked = checked;
    });
    updateCounts();
  }

  function previewOpen() {
    return !els.panePreview.hidden;
  }

  function dismissTransientProgress() {
    const transient = els.progress.classList.contains("is-warn") || els.progress.classList.contains("is-error");
    const hasDownload = !els.download.classList.contains("hidden");
    if (transient && !hasDownload) {
      hideProgress();
    }
  }

  function setMode(mode) {
    const preview = mode === "preview";
    els.tabGenerate.classList.toggle("is-active", !preview);
    els.tabPreview.classList.toggle("is-active", preview);
    els.tabGenerate.setAttribute("aria-selected", preview ? "false" : "true");
    els.tabPreview.setAttribute("aria-selected", preview ? "true" : "false");
    els.paneGenerate.hidden = preview;
    els.panePreview.hidden = !preview;
    if (els.countryFilter) els.countryFilter.hidden = !preview;
    if (preview) {
      dismissTransientProgress();
      loadPreview();
    }
  }

  function setPreviewStatus(text) {
    els.previewStatus.textContent = text || "";
  }

  function resetPreview() {
    previewHtmlCache = Object.create(null);
    previewAesId = "";
    previewDashboard = "combined";
    previewDashboards = [];
    els.previewCountry.replaceChildren();
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = t("selectCountry");
    els.previewCountry.appendChild(placeholder);
    els.previewCountry.disabled = true;
    els.previewTabs.replaceChildren();
    els.previewBody.replaceChildren();
    setPreviewDownloadOpen(false);
    syncPreviewDownload();
    setPreviewStatus("");
  }

  function fillPreviewCountries(rows) {
    els.previewCountry.replaceChildren();
    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = t("selectCountry");
    els.previewCountry.appendChild(placeholder);
    (rows || []).forEach((row) => {
      const opt = document.createElement("option");
      opt.value = String(row.aes_id);
      const name = row.country_name || row.iso3 || String(row.aes_id);
      opt.textContent = row.iso3 ? name + " (" + row.iso3 + ")" : name;
      els.previewCountry.appendChild(opt);
    });
    els.previewCountry.disabled = running || !rows || !rows.length;
    if (rows && rows.length) {
      els.previewCountry.value = String(rows[0].aes_id);
    }
    syncPreviewDownload();
  }

  function renderPreviewTabs(dashboards) {
    if (shared.renderDashboardTabs) {
      shared.renderDashboardTabs({
        container: els.previewTabs,
        dashboards,
        activeId: previewDashboard,
        tablistId: "upr-vis-preview-tabs",
        onSelect: (id) => {
          if (id === previewDashboard) return;
          previewDashboard = id;
          loadPreview();
        },
      });
      return;
    }
    els.previewTabs.replaceChildren();
    (dashboards || []).forEach((dash) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "upr-visuals-embed__tab" + (dash.id === previewDashboard ? " is-active" : "");
      btn.textContent = dash.title;
      btn.dataset.dashboard = dash.id;
      btn.addEventListener("click", () => {
        if (dash.id === previewDashboard) return;
        previewDashboard = dash.id;
        loadPreview();
      });
      els.previewTabs.appendChild(btn);
    });
  }

  function showPreviewHtml(aesId, dashboardId) {
    const html = previewHtmlCache[aesId] && previewHtmlCache[aesId][dashboardId];
    if (html == null) return false;
    previewDashboard = dashboardId;
    if (shared.markActiveTab) {
      shared.markActiveTab(els.previewTabs, dashboardId);
    } else {
      els.previewTabs.querySelectorAll(".upr-visuals-embed__tab").forEach((el) => {
        el.classList.toggle("is-active", el.dataset.dashboard === dashboardId);
      });
    }
    els.previewBody.innerHTML = html;
    setPreviewStatus("");
    return true;
  }

  function rememberPreviewHtml(aesId, dashboardId, data) {
    if (!previewHtmlCache[aesId]) previewHtmlCache[aesId] = Object.create(null);
    if (shared.rememberHtml) {
      shared.rememberHtml(previewHtmlCache[aesId], dashboardId, data);
      return;
    }
    const byId = data && data.html_by_dashboard;
    if (byId && typeof byId === "object") {
      Object.keys(byId).forEach((id) => {
        if (typeof byId[id] === "string") previewHtmlCache[aesId][id] = byId[id];
      });
    } else if (data && typeof data.html === "string") {
      previewHtmlCache[aesId][dashboardId] = data.html;
    }
  }

  async function loadPreview() {
    if (!previewOpen()) return;
    if (!els.assignment.value) {
      setPreviewStatus(t("previewNeedAssignment"));
      els.previewBody.replaceChildren();
      syncPreviewDownload();
      return;
    }
    if (!els.previewCountry.value) {
      const first = Array.from(els.previewCountry.options).find((opt) => opt.value);
      if (first) els.previewCountry.value = first.value;
    }
    const aesId = els.previewCountry.value;
    if (!aesId) {
      setPreviewStatus(t("previewNeedCountry"));
      els.previewBody.replaceChildren();
      syncPreviewDownload();
      return;
    }
    if (!previewDashboards.length) {
      previewDashboards = Array.from(els.dashboards.querySelectorAll("input[type=checkbox]")).map((input) => ({
        id: input.value,
        title: input.parentElement ? input.parentElement.textContent.trim() : input.value,
      }));
    }
    if (previewDashboards.length && !previewDashboards.some((dash) => dash.id === previewDashboard)) {
      previewDashboard = previewDashboards[0].id;
    }
    renderPreviewTabs(previewDashboards);
    if (aesId === previewAesId && showPreviewHtml(aesId, previewDashboard)) {
      syncPreviewDownload();
      return;
    }
    const requestedDashboard = previewDashboard;
    previewAesId = aesId;
    setPreviewStatus(t("previewLoading"));
    const progressId = shared.newProgressId ? shared.newProgressId() : "";
    const progressLabels = {
      loading: t("previewLoading"),
      translating: t("previewTranslating"),
      remaining: t("previewRemaining"),
    };
    const stopWatch =
      progressId && shared.watchVisualsProgress
        ? shared.watchVisualsProgress(aesId, progressId, (rec, elapsed) => {
            if (shared.formatVisualsProgress) {
              setPreviewStatus(shared.formatVisualsProgress(progressLabels, rec, elapsed));
            }
          })
        : null;
    try {
      const baseUrl = `/assignment/${encodeURIComponent(aesId)}/visuals?dashboard=${encodeURIComponent(requestedDashboard)}`;
      const langUrl = shared.withLang ? shared.withLang(baseUrl) : baseUrl;
      const progressUrl = progressId
        ? langUrl + (langUrl.indexOf("?") >= 0 ? "&" : "?") + "progress_id=" + encodeURIComponent(progressId)
        : langUrl;
      const response = await fetchFn(progressUrl, { headers: csrfHeaders(), credentials: "same-origin" });
      const data = await response.json();
      if (!response.ok || data.success === false) {
        throw new Error(data.error || t("previewFailed"));
      }
      rememberPreviewHtml(aesId, requestedDashboard, data);
      if (els.previewCountry.value !== aesId) return;
      if (data.payload && data.payload.dashboards) {
        previewDashboards = data.payload.dashboards;
        renderPreviewTabs(previewDashboards);
      }
      if (previewDashboard !== requestedDashboard) {
        if (showPreviewHtml(aesId, previewDashboard)) {
          syncPreviewDownload();
          return;
        }
      }
      if (!showPreviewHtml(aesId, requestedDashboard)) {
        els.previewBody.innerHTML = data.html || "";
        setPreviewStatus("");
      }
      syncPreviewDownload();
    } catch (err) {
      if (els.previewCountry.value !== aesId) return;
      els.previewBody.innerHTML = "";
      setPreviewStatus(t("previewFailed"));
      syncPreviewDownload();
    } finally {
      if (stopWatch) stopWatch();
    }
  }

  function setPreviewDownloadOpen(open) {
    previewDownloadWrap?.classList.toggle("is-open", open);
    els.previewDownload?.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function syncPreviewDownload() {
    const ready = Boolean(els.previewCountry.value && previewDashboard && !running);
    if (els.previewDownload) els.previewDownload.disabled = !ready;
    if (!ready) setPreviewDownloadOpen(false);
  }

  if (window.UprVisualsDownload) {
    window.UprVisualsDownload.bindDownloadMenu({
      button: els.previewDownload,
      menu: els.previewDownloadMenu,
      wrap: previewDownloadWrap,
      aesIdFn: () => els.previewCountry.value,
      dashboardFn: () => previewDashboard,
    });
  }

  function setDashboards(checked) {
    els.dashboards.querySelectorAll(".upr-vis-chip").forEach((chip) => {
      const input = chip.querySelector("input[type=checkbox]");
      if (!input) return;
      input.checked = checked;
      chip.classList.toggle("is-checked", checked);
    });
    updateCounts();
  }

  function statusMessage(status) {
    const state = status.status || "";
    if (state === "completed") return t("done");
    if (state === "failed") return status.error || t("failed");
    if (state === "cancelled" || state === "cancel_requested") return t("cancelled");
    if (state === "queued") return t("queued");
    return status.message || t("rendering");
  }

  function statusTone(state) {
    if (state === "completed") return "is-success";
    if (state === "failed") return "is-error";
    if (state === "cancelled" || state === "cancel_requested") return "is-warn";
    return "";
  }

  function applyStatus(status) {
    const total = status.total || 0;
    const progress = status.progress || 0;
    const pct = total ? Math.round((progress / total) * 100) : 0;
    const state = status.status || "";
    jobId = status.job_id || jobId;
    showProgress(statusTone(state), statusMessage(status), pct);
    if (state === "completed" && status.zip_key) {
      els.download.href = `/admin/data-exploration/upr-visuals/download/${encodeURIComponent(jobId)}`;
      els.download.classList.remove("hidden");
    }
    return state;
  }

  function startPolling() {
    stopPolling();
    pollFailures = 0;
    pollStartedAt = Date.now();
    pollTimer = setInterval(poll, POLL_INTERVAL_MS);
    poll();
  }

  function resumeActiveJob() {
    const status = (window.UprVisualsAdminConfig && window.UprVisualsAdminConfig.activeJob) || null;
    if (!status || !status.job_id) return;
    const state = status.status || "";
    jobId = status.job_id;
    if (state === "failed" || state === "cancelled" || state === "cancel_requested") {
      setRunning(false);
      return;
    }
    applyStatus(status);
    if (state === "completed" && status.zip_key) {
      setRunning(false);
      return;
    }
    setRunning(true);
    startPolling();
  }

  function stopPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = null;
    pollFailures = 0;
  }

  async function poll() {
    if (pollStartedAt && Date.now() - pollStartedAt > POLL_MAX_MS) {
      stopPolling();
      setRunning(false);
      showProgress("is-error", t("loadFailed"), 0);
      return;
    }
    try {
      const response = await fetchFn(
        `/admin/data-exploration/upr-visuals/status${jobId ? "?job_id=" + encodeURIComponent(jobId) : ""}`,
        { headers: csrfHeaders(), credentials: "same-origin" }
      );
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.success === false) {
        throw new Error(data.error || t("loadFailed"));
      }
      pollFailures = 0;
      const status = data.status || {};
      const state = applyStatus(status);

      if (state === "completed" && status.zip_key) {
        setRunning(false);
        stopPolling();
      }
      if (state === "failed" || state === "cancelled" || state === "cancel_requested") {
        setRunning(false);
        stopPolling();
      }
    } catch (err) {
      pollFailures += 1;
      if (pollFailures >= POLL_MAX_FAILURES) {
        stopPolling();
        setRunning(false);
        const offline = err instanceof TypeError || /failed to fetch|networkerror/i.test(String(err));
        showProgress("is-error", offline ? t("serverStopped") : t("loadFailed"), 0);
      }
    }
  }

  if (els.formats) {
    els.formats.addEventListener("change", syncFormatUI);
  }
  if (els.includeNarrative) {
    els.includeNarrative.addEventListener("change", syncFormatUI);
  }

  els.assignment.addEventListener("change", () => {
    if (!booting && !running) {
      hideProgress();
      els.download.classList.add("hidden");
    }
    loadCountries();
  });
  els.countrySearch.addEventListener("input", filterCountries);
  els.selectAll.addEventListener("click", () => setVisibleCountries(true));
  els.selectNone.addEventListener("click", () => setVisibleCountries(false));
  els.dashSelectAll.addEventListener("click", () => setDashboards(true));
  els.dashSelectNone.addEventListener("click", () => setDashboards(false));
  els.tabGenerate.addEventListener("click", () => setMode("generate"));
  els.tabPreview.addEventListener("click", () => setMode("preview"));
  els.previewCountry.addEventListener("change", () => {
    previewHtmlCache = Object.create(null);
    previewAesId = "";
    loadPreview();
  });
  document.addEventListener("upr-visuals:languagechange", () => {
    previewHtmlCache = Object.create(null);
    previewAesId = "";
    if (shared.applyExportDir) shared.applyExportDir(els.previewBody);
    loadPreview();
  });
  els.generate.addEventListener("click", async () => {
    const assignedFormId = parseInt(els.assignment.value, 10);
    if (!assignedFormId) {
      showProgress("is-warn", t("needAssignment"), 0);
      return;
    }
    const format = selectedFormat();
    const dashboardIds = needsDashboards() ? selectedValues(els.dashboards) : ["combined"];
    const aesIds = selectedValues(els.countries).map((v) => parseInt(v, 10));
    if (needsDashboards() && !dashboardIds.length) {
      showProgress("is-warn", t("needDashboards"), 0);
      return;
    }
    if (!aesIds.length) {
      showProgress("is-warn", t("needCountries"), 0);
      return;
    }
    els.download.classList.add("hidden");
    setRunning(true);
    showProgress("", t("generating"), 0);
    try {
      const body = new FormData();
      body.append("assigned_form_id", String(assignedFormId));
      body.append("export_format", format);
      body.append("include_narrative", includeNarrative() ? "1" : "0");
      dashboardIds.forEach((id) => body.append("dashboard_ids", id));
      aesIds.forEach((id) => body.append("aes_ids", String(id)));
      body.append("lang", shared.getExportLanguage ? shared.getExportLanguage() : "en");
      if (includeNarrative() && els.narratives && els.narratives.files) {
        Array.from(els.narratives.files).forEach((file) => body.append("narratives", file));
      }
      const response = await fetchFn("/admin/data-exploration/upr-visuals/generate", {
        method: "POST",
        headers: csrfHeaders(false),
        credentials: "same-origin",
        body,
      });
      const data = await response.json();
      if (!response.ok || data.success === false) {
        setRunning(false);
        showProgress("is-error", data.error || t("startFailed"), 0);
        return;
      }
      jobId = data.job_id;
      startPolling();
    } catch (err) {
      setRunning(false);
      showProgress("is-error", t("startFailed"), 0);
    }
  });
  els.cancel.addEventListener("click", async () => {
    if (!jobId) return;
    els.cancel.disabled = true;
    try {
      const response = await fetchFn("/admin/data-exploration/upr-visuals/cancel", {
        method: "POST",
        headers: csrfHeaders(),
        credentials: "same-origin",
        body: JSON.stringify({ job_id: jobId }),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.success === false) {
        showProgress("is-error", data.error || t("loadFailed"));
        return;
      }
      await poll();
    } catch (err) {
      showProgress("is-error", t("loadFailed"));
    } finally {
      els.cancel.disabled = false;
    }
  });

  if (shared.applyExportDir) shared.applyExportDir(els.previewBody);
  clearSelection(t("loadingAssignments"));
  syncFormatUI();
  loadAssignments().finally(() => {
    resumeActiveJob();
    booting = false;
  });
})();
