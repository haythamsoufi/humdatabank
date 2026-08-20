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
  let pollTimer = null;
  let jobId = null;
  let running = false;
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

  function csrfHeaders() {
    const token = document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
    const headers = { Accept: "application/json", "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" };
    if (token) headers["X-CSRFToken"] = token;
    return headers;
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
    const ready = Boolean(els.assignment.value) && dashSelected > 0 && countrySelected > 0;
    els.generate.disabled = running || !ready;
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
        loadCountries();
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
        `/admin/data-exploration/upr-visuals/countries?assigned_form_id=${encodeURIComponent(assignedFormId)}`,
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

  function setMode(mode) {
    const preview = mode === "preview";
    els.tabGenerate.classList.toggle("is-active", !preview);
    els.tabPreview.classList.toggle("is-active", preview);
    els.tabGenerate.setAttribute("aria-selected", preview ? "false" : "true");
    els.tabPreview.setAttribute("aria-selected", preview ? "true" : "false");
    els.paneGenerate.hidden = preview;
    els.panePreview.hidden = !preview;
    if (els.countryFilter) els.countryFilter.hidden = !preview;
    if (preview) loadPreview();
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
    els.previewTabs.querySelectorAll(".upr-visuals-embed__tab").forEach((el) => {
      el.classList.toggle("is-active", el.dataset.dashboard === dashboardId);
    });
    els.previewBody.innerHTML = html;
    setPreviewStatus("");
    return true;
  }

  function rememberPreviewHtml(aesId, dashboardId, data) {
    if (!previewHtmlCache[aesId]) previewHtmlCache[aesId] = Object.create(null);
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
    previewAesId = aesId;
    setPreviewStatus(t("previewLoading"));
    try {
      const response = await fetchFn(
        `/upr-visuals/assignment/${encodeURIComponent(aesId)}?dashboard=${encodeURIComponent(previewDashboard)}`,
        { headers: csrfHeaders(), credentials: "same-origin" }
      );
      const data = await response.json();
      if (!response.ok || data.success === false) {
        throw new Error(data.error || t("previewFailed"));
      }
      rememberPreviewHtml(aesId, previewDashboard, data);
      if (data.payload && data.payload.dashboards) {
        previewDashboards = data.payload.dashboards;
        renderPreviewTabs(previewDashboards);
      }
      if (!showPreviewHtml(aesId, previewDashboard)) {
        els.previewBody.innerHTML = data.html || "";
        setPreviewStatus("");
      }
      syncPreviewDownload();
    } catch (err) {
      els.previewBody.innerHTML = "";
      setPreviewStatus(t("previewFailed"));
      syncPreviewDownload();
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

  function downloadPreviewVisual(format) {
    const aesId = els.previewCountry.value;
    if (!aesId || !previewDashboard) return;
    const kind = format === "pdf" ? "pdf" : "png";
    window.location.href = `/upr-visuals/assignment/${encodeURIComponent(aesId)}/${kind}/${encodeURIComponent(previewDashboard)}`;
    setPreviewDownloadOpen(false);
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
    if (state === "cancelled") return t("cancelled");
    if (state === "queued") return t("queued");
    return status.message || t("rendering");
  }

  function statusTone(state) {
    if (state === "completed") return "is-success";
    if (state === "failed") return "is-error";
    if (state === "cancelled") return "is-warn";
    return "";
  }

  async function poll() {
    const response = await fetchFn(
      `/admin/data-exploration/upr-visuals/status${jobId ? "?job_id=" + encodeURIComponent(jobId) : ""}`,
      { headers: csrfHeaders(), credentials: "same-origin" }
    );
    const data = await response.json();
    const status = data.status || {};
    jobId = status.job_id || jobId;
    const total = status.total || 0;
    const progress = status.progress || 0;
    const pct = total ? Math.round((progress / total) * 100) : 0;
    const state = status.status || "";
    showProgress(statusTone(state), statusMessage(status), pct);

    if (state === "completed" && status.zip_key) {
      els.download.href = `/admin/data-exploration/upr-visuals/download/${encodeURIComponent(jobId)}`;
      els.download.classList.remove("hidden");
      setRunning(false);
      if (pollTimer) clearInterval(pollTimer);
      pollTimer = null;
    }
    if (state === "failed" || state === "cancelled") {
      setRunning(false);
      if (pollTimer) clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  els.assignment.addEventListener("change", () => {
    hideProgress();
    els.download.classList.add("hidden");
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
  els.previewDownload?.addEventListener("click", (event) => {
    event.stopPropagation();
    if (els.previewDownload.disabled) return;
    setPreviewDownloadOpen(!previewDownloadWrap?.classList.contains("is-open"));
  });
  els.previewDownloadMenu?.addEventListener("click", (event) => {
    const item = event.target.closest("[data-format]");
    if (!item) return;
    downloadPreviewVisual(item.dataset.format);
  });
  document.addEventListener("click", (event) => {
    if (!previewDownloadWrap || previewDownloadWrap.contains(event.target)) return;
    setPreviewDownloadOpen(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setPreviewDownloadOpen(false);
  });
  els.generate.addEventListener("click", async () => {
    const assignedFormId = parseInt(els.assignment.value, 10);
    if (!assignedFormId) {
      showProgress("is-warn", t("needAssignment"), 0);
      return;
    }
    const dashboardIds = selectedValues(els.dashboards);
    const aesIds = selectedValues(els.countries).map((v) => parseInt(v, 10));
    if (!dashboardIds.length) {
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
      const response = await fetchFn("/admin/data-exploration/upr-visuals/generate", {
        method: "POST",
        headers: csrfHeaders(),
        credentials: "same-origin",
        body: JSON.stringify({
          assigned_form_id: assignedFormId,
          dashboard_ids: dashboardIds,
          aes_ids: aesIds,
        }),
      });
      const data = await response.json();
      if (!response.ok || data.success === false) {
        setRunning(false);
        showProgress("is-error", data.error || t("startFailed"), 0);
        return;
      }
      jobId = data.job_id;
      if (pollTimer) clearInterval(pollTimer);
      pollTimer = setInterval(poll, 1500);
      poll();
    } catch (err) {
      setRunning(false);
      showProgress("is-error", t("startFailed"), 0);
    }
  });
  els.cancel.addEventListener("click", async () => {
    if (!jobId) return;
    await fetchFn("/admin/data-exploration/upr-visuals/cancel", {
      method: "POST",
      headers: csrfHeaders(),
      credentials: "same-origin",
      body: JSON.stringify({ job_id: jobId }),
    });
    poll();
  });

  clearSelection(t("loadingAssignments"));
  loadAssignments();
})();
