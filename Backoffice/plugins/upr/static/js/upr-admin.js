(function () {
  const root = document.getElementById("upr-admin");
  if (!root) return;

  const i18n = (window.UprVisualsAdminConfig && window.UprVisualsAdminConfig.i18n) || {};
  const els = {
    assignment: document.getElementById("upr-vis-assignment"),
    table: document.getElementById("upr-vis-table"),
    tableHead: document.getElementById("upr-vis-table-head"),
    countries: document.getElementById("upr-vis-countries"),
    countryCount: document.getElementById("upr-vis-country-count"),
    countrySearch: document.getElementById("upr-vis-country-search"),
    selectAll: document.getElementById("upr-vis-select-all"),
    selectNone: document.getElementById("upr-vis-select-none"),
    generate: document.getElementById("upr-vis-generate"),
    generateIdml: document.getElementById("upr-vis-generate-idml"),
    generateLabel: root.querySelector("[data-upr-generate-label]"),
    formats: document.getElementById("upr-vis-format"),
    downloadAll: document.getElementById("upr-vis-download-all"),
    narrativePanel: document.getElementById("upr-vis-narrative-panel"),
    includeNarrative: document.getElementById("upr-vis-include-narrative"),
    narrativeFilesWrap: document.getElementById("upr-vis-narrative-files-wrap"),
    narratives: document.getElementById("upr-vis-narratives"),
    narrativeAudience: document.getElementById("upr-vis-narrative-audience"),
    cancel: document.getElementById("upr-vis-cancel"),
    cancelWrap: document.getElementById("upr-vis-cancel-wrap"),
    status: document.getElementById("upr-vis-status"),
    detail: document.getElementById("upr-vis-progress-detail"),
    pct: document.getElementById("upr-vis-pct"),
    progress: document.getElementById("upr-vis-progress"),
    progressBar: document.getElementById("upr-vis-progress-bar"),
    spinner: document.getElementById("upr-vis-progress-spinner"),
    dismiss: document.getElementById("upr-vis-progress-dismiss"),
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
    els.previewDownload && els.previewDownload.closest(".upr-download");
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
  let tableDashboards = [];
  let libraryToken = 0;

  function t(key, vars) {
    let text = i18n[key] || key;
    if (vars) {
      Object.keys(vars).forEach((name) => {
        text = text.split("{" + name + "}").join(String(vars[name]));
      });
    }
    return text;
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
    const item = els.formats && els.formats.querySelector("[data-format][aria-pressed='true']");
    return (item && item.dataset.format) === "pdf" ? "pdf" : "png";
  }

  function setFormat(format) {
    if (!els.formats) return;
    const next = format === "pdf" ? "pdf" : "png";
    els.formats.querySelectorAll("[data-format]").forEach((item) => {
      item.setAttribute("aria-pressed", item.dataset.format === next ? "true" : "false");
    });
    syncFormatUI();
    loadLibrary();
  }

  function includeNarrative(format) {
    const kind = format || selectedFormat();
    if (kind === "png") return false;
    if (kind === "idml" && els.narrativePanel && els.narrativePanel.hidden) return false;
    return Boolean(els.includeNarrative && els.includeNarrative.checked);
  }

  function needsDashboards() {
    const format = selectedFormat();
    return format === "png" || (format === "pdf" && !includeNarrative());
  }

  function syncFormatUI() {
    const format = selectedFormat();
    if (els.narrativePanel) els.narrativePanel.hidden = format === "png";
    if (els.narrativeFilesWrap) els.narrativeFilesWrap.hidden = !includeNarrative();
    if (shared.updateNarrativeTranslateHints) shared.updateNarrativeTranslateHints();
    if (els.generate) {
      const labels = { png: t("generatePng"), pdf: t("generatePdf") };
      const text = els.generate.dataset["label" + format.charAt(0).toUpperCase() + format.slice(1)] || labels[format] || t("generatePng");
      if (els.generateLabel) els.generateLabel.textContent = text;
    }
    updateCounts();
  }

  function fetchFn(url, opts) {
    const csrfFetch = window.getCsrfAwareFetch && window.getCsrfAwareFetch();
    return (csrfFetch || fetch)(url, opts);
  }

  function dashModalRoot() {
    return document.getElementById("upr-vis-dash-modal");
  }

  function setDashModalOpen(open) {
    const root = dashModalRoot();
    if (!root) return;
    root.classList.toggle("hidden", !open);
    if (open) {
      const go = document.getElementById("upr-vis-dash-modal-go");
      if (go) go.focus();
    }
  }

  function chosenDashboardIds() {
    const list = document.getElementById("upr-vis-dash-modal-list");
    if (!list) return [];
    return Array.from(list.querySelectorAll("input[type=checkbox]:checked")).map((input) => input.value);
  }

  function syncDashModalGo() {
    const go = document.getElementById("upr-vis-dash-modal-go");
    if (go) go.disabled = chosenDashboardIds().length === 0;
  }

  function setDashModalChecks(checked) {
    const list = document.getElementById("upr-vis-dash-modal-list");
    if (!list) return;
    list.querySelectorAll(".upr-vis-chip").forEach((chip) => {
      const input = chip.querySelector("input[type=checkbox]");
      if (!input) return;
      input.checked = checked;
      chip.classList.toggle("is-checked", checked);
    });
    syncDashModalGo();
  }

  function openDashboardModal() {
    const list = document.getElementById("upr-vis-dash-modal-list");
    const lead = document.getElementById("upr-vis-dash-modal-lead");
    const note = document.getElementById("upr-vis-dash-modal-note");
    const tools = document.getElementById("upr-vis-dash-modal-tools");
    const go = document.getElementById("upr-vis-dash-modal-go");
    if (!list) return;
    const limited = !needsDashboards();
    const dashes = limited ? tableDashboards.filter((dash) => dash.id === "combined") : tableDashboards.slice();
    list.replaceChildren();
    dashes.forEach((dash) => {
      const label = document.createElement("label");
      label.className = "upr-vis-chip is-checked";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = dash.id;
      input.checked = true;
      input.addEventListener("change", () => {
        label.classList.toggle("is-checked", input.checked);
        syncDashModalGo();
      });
      const title = document.createElement("span");
      title.textContent = dash.title;
      label.append(input, title);
      list.appendChild(label);
    });
    if (lead) lead.textContent = t("dashModalLead", { count: selectedRowCount() });
    if (note) {
      note.hidden = !limited;
      note.textContent = limited ? t("onlyCombined") : "";
    }
    if (tools) tools.hidden = limited || dashes.length < 2;
    if (go) {
      const label = go.querySelector("span");
      if (label && els.generateLabel) label.textContent = els.generateLabel.textContent;
    }
    syncDashModalGo();
    setDashModalOpen(true);
  }

  function countryRows() {
    if (!els.countries) return [];
    return Array.from(els.countries.querySelectorAll("tr.upr-vis-country"));
  }

  function visibleCountryRows() {
    return countryRows().filter((row) => !row.hidden);
  }

  function selectedCountryIds() {
    return countryRows()
      .filter((row) => !row.dataset.bundle)
      .map((row) => row.querySelector("input[type=checkbox]"))
      .filter((input) => input && input.checked && /^\d+$/.test(input.value))
      .map((input) => input.value);
  }

  function selectedBundleNames() {
    return countryRows()
      .filter((row) => row.dataset.bundle)
      .filter((row) => {
        const input = row.querySelector("input[type=checkbox]");
        return input && input.checked;
      })
      .map((row) => row.dataset.bundle);
  }

  function selectedRowCount() {
    return selectedCountryIds().length + selectedBundleNames().length;
  }

  function syncMasterCheck() {
    const master = document.getElementById("upr-vis-check-all");
    if (!master) return;
    const rows = visibleCountryRows();
    const checked = rows.filter((row) => {
      const input = row.querySelector("input[type=checkbox]");
      return input && input.checked;
    }).length;
    master.checked = rows.length > 0 && checked === rows.length;
    master.indeterminate = checked > 0 && checked < rows.length;
    master.disabled = running || !rows.length;
  }

  function updateCounts() {
    const countrySelected = selectedRowCount();
    const countryTotal = countryRows().length;
    if (els.countryCount) {
      els.countryCount.textContent = countryTotal
        ? t("selectedCount", { selected: countrySelected, total: countryTotal })
        : "";
    }
    const dashOk = needsDashboards() ? tableDashboards.length > 0 : Boolean(els.assignment.value);
    const ready = Boolean(els.assignment.value) && dashOk && countrySelected > 0;
    if (els.generate) els.generate.disabled = running || !ready;
    if (els.generateIdml) els.generateIdml.disabled = running || !els.assignment.value || countrySelected === 0;
    syncMasterCheck();
  }

  function setCountryToolsEnabled(on) {
    els.countrySearch.disabled = !on;
    els.selectAll.disabled = !on;
    els.selectNone.disabled = !on;
    if (!on) els.countrySearch.value = "";
  }

  function showProgress(tone, message, pct, detail) {
    els.progress.classList.remove("hidden", "is-success", "is-error", "is-warn");
    if (tone) els.progress.classList.add(tone);
    els.status.textContent = message || "";
    if (els.detail) {
      els.detail.textContent = detail || "";
      els.detail.classList.toggle("hidden", !detail);
    }
    if (els.spinner) els.spinner.classList.toggle("hidden", Boolean(tone));
    if (els.dismiss) els.dismiss.classList.toggle("hidden", !tone);
    if (typeof pct === "number") {
      els.pct.textContent = pct + "%";
      els.pct.classList.remove("hidden");
      els.progressBar.style.width = pct + "%";
    }
  }

  function hideProgress() {
    els.progress.classList.add("hidden");
    els.progress.classList.remove("is-success", "is-error", "is-warn");
    els.status.textContent = "";
    if (els.detail) {
      els.detail.textContent = "";
      els.detail.classList.add("hidden");
    }
    els.pct.textContent = "";
    els.progressBar.style.width = "0%";
    if (els.dismiss) els.dismiss.classList.add("hidden");
  }

  function setRunning(on) {
    running = on;
    els.assignment.disabled = on;
    const hasCountries = countryRows().length > 0;
    els.countrySearch.disabled = on || !hasCountries;
    els.selectAll.disabled = on || !hasCountries;
    els.selectNone.disabled = on || !hasCountries;
    els.previewCountry.disabled = on || !els.previewCountry.querySelector("option[value]:not([value=''])");
    syncPreviewDownload();
    if (els.cancelWrap) els.cancelWrap.classList.toggle("hidden", !on);
    els.countries.querySelectorAll("input").forEach((input) => {
      input.disabled = on;
    });
    if (els.formats) {
      els.formats.querySelectorAll("button").forEach((button) => {
        button.disabled = on;
      });
    }
    if (els.includeNarrative) els.includeNarrative.disabled = on;
    if (els.narratives) els.narratives.disabled = on;
    if (els.narrativeAudience) els.narrativeAudience.disabled = on;
    updateCounts();
  }

  function clearSelection(message) {
    tableDashboards = [];
    emptyTable(message);
    if (els.countryCount) els.countryCount.textContent = "";
    setCountryToolsEnabled(false);
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
      const response = await fetchFn("/admin/data-exploration/upr/assignments", {
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

  function emptyTable(message) {
    if (els.tableHead) els.tableHead.replaceChildren();
    if (!els.countries) return;
    els.countries.replaceChildren();
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = 4;
    td.className = "upr-vis-empty";
    td.textContent = message;
    tr.appendChild(td);
    els.countries.appendChild(tr);
  }

  function formatIcon(format) {
    if (format === "pdf") return "fa-file-pdf";
    if (format === "idml") return "fa-file-archive";
    return "fa-file-image";
  }

  function formatGeneratedAt(iso) {
    if (!iso) return "";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "";
    return date.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function emptyMark() {
    const span = document.createElement("span");
    span.className = "upr-vis-file is-empty";
    span.title = t("notGenerated");
    const icon = document.createElement("i");
    icon.className = "fas fa-minus";
    icon.setAttribute("aria-hidden", "true");
    span.appendChild(icon);
    return span;
  }

  function fileLink(href, icon, label) {
    const link = document.createElement("a");
    link.className = "upr-vis-file";
    link.href = href;
    link.title = label;
    link.setAttribute("aria-label", label);
    const node = document.createElement("i");
    node.className = "fas " + icon;
    node.setAttribute("aria-hidden", "true");
    link.appendChild(node);
    return link;
  }

  function rowQuery(row, extra) {
    const params = Object.assign({}, extra || {});
    if (row.dataset.bundle) params.bundle = row.dataset.bundle;
    else params.aes_id = row.dataset.aes;
    return libraryQuery(params);
  }

  function libraryQuery(extra) {
    const params = new URLSearchParams();
    params.set("assigned_form_id", els.assignment.value || "");
    params.set("export_format", selectedFormat());
    params.set("lang", shared.getExportLanguage ? shared.getExportLanguage() : "en");
    Object.keys(extra || {}).forEach((key) => params.set(key, extra[key]));
    return params.toString();
  }

  function renderGenerateTable(dashboards, countries) {
    tableDashboards = dashboards || [];
    if (!els.tableHead || !els.countries) return;
    els.tableHead.replaceChildren();
    els.countries.replaceChildren();
    if (!tableDashboards.length || !(countries || []).length) {
      emptyTable(!tableDashboards.length ? t("noDashboards") : t("noCountries"));
      setCountryToolsEnabled(false);
      return;
    }

    const headRow = document.createElement("tr");
    const checkHead = document.createElement("th");
    checkHead.scope = "col";
    const master = document.createElement("input");
    master.type = "checkbox";
    master.id = "upr-vis-check-all";
    master.checked = false;
    master.setAttribute("aria-label", t("selectAllCountries"));
    checkHead.appendChild(master);
    const countryHead = document.createElement("th");
    countryHead.scope = "col";
    countryHead.className = "upr-vis-country-cell";
    countryHead.textContent = t("country");
    headRow.append(checkHead, countryHead);
    tableDashboards.forEach((dash) => {
      const th = document.createElement("th");
      th.scope = "col";
      th.textContent = dash.title;
      headRow.appendChild(th);
    });
    const packageHead = document.createElement("th");
    packageHead.scope = "col";
    packageHead.textContent = t("package");
    const whenHead = document.createElement("th");
    whenHead.scope = "col";
    whenHead.textContent = t("generatedAt");
    headRow.append(packageHead, whenHead);
    els.tableHead.appendChild(headRow);

    (countries || []).forEach((row) => {
      const tr = document.createElement("tr");
      tr.className = "upr-vis-country";
      const name = row.country_name || row.iso3 || String(row.aes_id);
      tr.dataset.name = name.toLowerCase();
      tr.dataset.iso = String(row.iso3 || "").toLowerCase();
      tr.dataset.aes = String(row.aes_id);
      tr.dataset.label = name;

      const checkCell = document.createElement("td");
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = String(row.aes_id);
      input.checked = false;
      input.setAttribute("aria-label", t("selectCountryRow", { country: name }));
      checkCell.appendChild(input);

      const nameCell = document.createElement("td");
      nameCell.className = "upr-vis-country-cell";
      nameCell.appendChild(document.createTextNode(name));
      if (row.is_bundle && row.bundle) {
        tr.dataset.bundle = row.bundle;
        tr.dataset.aes = row.library_id || "";
        const tag = document.createElement("span");
        tag.className = "upr-vis-bundle-tag";
        nameCell.appendChild(document.createTextNode(" "));
        tag.textContent = row.member_count
          ? t("bundleTagCount", { count: row.member_count })
          : t("bundleTag");
        nameCell.appendChild(tag);
      }
      tr.append(checkCell, nameCell);
      tableDashboards.forEach((dash) => {
        const cell = document.createElement("td");
        cell.dataset.slot = dash.id;
        tr.appendChild(cell);
      });
      const zipCell = document.createElement("td");
      zipCell.dataset.slot = "zip";
      const whenCell = document.createElement("td");
      whenCell.className = "upr-vis-when";
      whenCell.dataset.slot = "when";
      tr.append(zipCell, whenCell);
      els.countries.appendChild(tr);
    });
    setCountryToolsEnabled(!running);
  }

  function paintLibrary(library) {
    const format = selectedFormat();
    const icon = formatIcon(format);
    countryRows().forEach((row) => {
      const entry = (library && library[row.dataset.aes]) || {};
      const stored = entry.dashboards || {};
      tableDashboards.forEach((dash) => {
        const cell = row.querySelector('[data-slot="' + dash.id + '"]');
        if (!cell) return;
        cell.replaceChildren();
        const item = stored[dash.id];
        if (!item) {
          cell.appendChild(emptyMark());
          return;
        }
        const when = formatGeneratedAt(item.generated_at);
        const label = t("downloadFile", { dashboard: dash.title }) + (when ? " · " + when : "");
        cell.appendChild(
          fileLink(
            "/admin/data-exploration/upr/library/file?" + rowQuery(row, { dashboard_id: dash.id }),
            icon,
            label
          )
        );
      });
      const zipCell = row.querySelector('[data-slot="zip"]');
      const whenCell = row.querySelector('[data-slot="when"]');
      if (zipCell) {
        zipCell.replaceChildren();
        if (entry.zip) {
          const when = formatGeneratedAt(entry.zip.generated_at || entry.generated_at);
          const label = t("downloadPackage", { country: row.dataset.label || row.dataset.aes }) + (when ? " · " + when : "");
          zipCell.appendChild(
            fileLink(
              "/admin/data-exploration/upr/library/package?" + rowQuery(row),
              "fa-file-archive",
              label
            )
          );
        } else {
          zipCell.appendChild(emptyMark());
        }
      }
      if (whenCell) whenCell.textContent = formatGeneratedAt(entry.generated_at) || "—";
    });
    syncFullZip(library);
  }

  function syncFullZip(library) {
    const link = els.downloadAll;
    if (!link) return;
    const ready = Object.keys(library || {}).some((id) => {
      const stored = library[id] && library[id].dashboards;
      return stored && Object.keys(stored).length > 0;
    });
    link.href = ready ? "/admin/data-exploration/upr/library/all?" + libraryQuery() : "#";
    link.setAttribute("aria-disabled", ready ? "false" : "true");
    link.classList.toggle("is-disabled", !ready);
  }

  async function loadLibrary() {
    const token = ++libraryToken;
    const assignedFormId = els.assignment.value;
    if (!assignedFormId || !countryRows().length) {
      paintLibrary({});
      return;
    }
    const format = selectedFormat();
    paintLibrary({});
    try {
      const response = await fetchFn(
        "/admin/data-exploration/upr/library?" + libraryQuery(),
        { headers: csrfHeaders(), credentials: "same-origin" }
      );
      const data = await response.json();
      if (token !== libraryToken) return;
      if (els.assignment.value !== assignedFormId || selectedFormat() !== format) return;
      if (!response.ok || data.success === false) return;
      paintLibrary(data.library || {});
    } catch (err) {
      if (token !== libraryToken) return;
    }
  }

  async function loadCountries() {
    const assignedFormId = els.assignment.value;
    if (!assignedFormId) {
      clearSelection(t("selectAssignmentFirst"));
      return;
    }
    resetPreview();
    emptyTable(t("loadingCountries"));
    setCountryToolsEnabled(false);
    els.generate.disabled = true;
    try {
      const response = await fetchFn(
        shared.withLang
          ? shared.withLang(
              `/admin/data-exploration/upr/countries?assigned_form_id=${encodeURIComponent(assignedFormId)}`
            )
          : `/admin/data-exploration/upr/countries?assigned_form_id=${encodeURIComponent(assignedFormId)}`,
        { headers: csrfHeaders(), credentials: "same-origin" }
      );
      const data = await response.json();
      if (!response.ok || data.success === false) {
        clearSelection(data.error || t("loadFailed"));
        return;
      }
      previewDashboards = data.dashboards || [];
      const bundles = data.bundles || [];
      const countries = data.countries || [];
      renderGenerateTable(previewDashboards, bundles.concat(countries));
      fillPreviewCountries(countries);
      updateCounts();
      loadLibrary();
      if (previewOpen()) loadPreview();
    } catch (err) {
      clearSelection(t("loadFailed"));
    }
  }

  function filterCountries() {
    const q = (els.countrySearch.value || "").trim().toLowerCase();
    countryRows().forEach((row) => {
      const match = !q || row.dataset.name.includes(q) || (row.dataset.iso || "").includes(q);
      row.hidden = !match;
    });
    syncMasterCheck();
  }

  function setVisibleCountries(checked) {
    visibleCountryRows().forEach((row) => {
      const input = row.querySelector("input[type=checkbox]");
      if (input && !input.disabled) input.checked = checked;
    });
    updateCounts();
  }

  function previewOpen() {
    return !els.panePreview.hidden;
  }

  function dismissTransientProgress() {
    const transient = els.progress.classList.contains("is-warn") || els.progress.classList.contains("is-error");
    if (transient) hideProgress();
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
      btn.className = "upr-embed__tab" + (dash.id === previewDashboard ? " is-active" : "");
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
      els.previewTabs.querySelectorAll(".upr-embed__tab").forEach((el) => {
        el.classList.toggle("is-active", el.dataset.dashboard === dashboardId);
      });
    }
    setTrustedHtml(els.previewBody, html);
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
      previewDashboards = tableDashboards.slice();
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
    setPreviewStatus("");
    if (shared.showVisualsSkeleton) {
      shared.showVisualsSkeleton(els.previewBody, t("previewLoading"));
    } else {
      setPreviewStatus(t("previewLoading"));
    }
    const progressId = shared.newProgressId ? shared.newProgressId() : "";
    const progressLabels = {
      loading: t("previewLoading"),
      translating: t("previewTranslating"),
      remaining: t("previewRemaining"),
    };
    const stopWatch =
      progressId && shared.watchVisualsProgress
        ? shared.watchVisualsProgress(aesId, progressId, (rec, elapsed) => {
            if (!shared.formatVisualsProgress) return;
            const text = shared.formatVisualsProgress(progressLabels, rec, elapsed);
            if (shared.showVisualsSkeleton) shared.showVisualsSkeleton(els.previewBody, text);
            else setPreviewStatus(text);
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
        setTrustedHtml(els.previewBody, data.html || "");
        setPreviewStatus("");
      }
      syncPreviewDownload();
    } catch (err) {
      if (els.previewCountry.value !== aesId) return;
      els.previewBody.replaceChildren();
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
    showProgress(
      statusTone(state),
      statusMessage(status),
      pct,
      state === "completed" ? t("doneDetail") : ""
    );
    if (state === "completed") loadLibrary();
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
    if (state === "failed" || state === "cancelled" || state === "cancel_requested" || state === "completed") {
      setRunning(false);
      return;
    }
    applyStatus(status);
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
        `/admin/data-exploration/upr/status${jobId ? "?job_id=" + encodeURIComponent(jobId) : ""}`,
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
    els.formats.addEventListener("click", (event) => {
      const item = event.target.closest("[data-format]");
      if (!item || !els.formats.contains(item) || item.disabled) return;
      if (item.getAttribute("aria-pressed") === "true") return;
      setFormat(item.dataset.format);
    });
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") setDashModalOpen(false);
  });
  if (els.includeNarrative) {
    els.includeNarrative.addEventListener("change", syncFormatUI);
  }
  if (els.narratives && els.narrativeAudience) {
    els.narratives.addEventListener("change", () => {
      const files = Array.from(els.narratives.files || []);
      const detected = new Set();
      files.forEach((file) => {
        const stem = String(file.name || "").replace(/\.[^.]+$/, "");
        if (/(?:^|[\s_\-.])internal(?:[\s_\-.]|$)|not[\s_\-]*for[\s_\-]*public/i.test(stem)) {
          detected.add("internal");
        } else if (/(?:^|[\s_\-])design(?:[\s_\-.]|$)/i.test(stem)) {
          detected.add("public");
        }
      });
      if (detected.size === 1) {
        els.narrativeAudience.value = [...detected][0];
      } else if (files.length) {
        els.narrativeAudience.value = "auto";
      }
    });
  }

  els.assignment.addEventListener("change", () => {
    if (!booting && !running) hideProgress();
    loadCountries();
  });
  els.countrySearch.addEventListener("input", filterCountries);
  els.selectAll.addEventListener("click", () => setVisibleCountries(true));
  els.selectNone.addEventListener("click", () => setVisibleCountries(false));
  if (els.table) {
    els.table.addEventListener("change", (event) => {
      const target = event.target;
      if (!(target instanceof HTMLInputElement) || target.type !== "checkbox") return;
      if (target.id === "upr-vis-check-all") {
        setVisibleCountries(target.checked);
        return;
      }
      updateCounts();
    });
  }
  els.tabGenerate.addEventListener("click", () => setMode("generate"));
  els.tabPreview.addEventListener("click", () => setMode("preview"));
  els.previewCountry.addEventListener("change", () => {
    previewHtmlCache = Object.create(null);
    previewAesId = "";
    loadPreview();
  });
  document.addEventListener("upr:languagechange", () => {
    previewHtmlCache = Object.create(null);
    previewAesId = "";
    if (shared.applyExportDir) shared.applyExportDir(els.previewBody);
    loadPreview();
    loadLibrary();
  });
  els.generate.addEventListener("click", () => {
    const assignedFormId = parseInt(els.assignment.value, 10);
    if (!assignedFormId) {
      showProgress("is-warn", t("needAssignment"), 0);
      return;
    }
    if (!selectedRowCount()) {
      showProgress("is-warn", t("needCountries"), 0);
      return;
    }
    if (!tableDashboards.length) {
      showProgress("is-warn", t("needDashboards"), 0);
      return;
    }
    openDashboardModal();
  });

  const dashModal = dashModalRoot();
  if (dashModal) {
    dashModal.addEventListener("click", (event) => {
      if (event.target === dashModal || event.target.closest(".upr-vis-dash-close")) {
        setDashModalOpen(false);
      }
    });
  }
  const dashModalAll = document.getElementById("upr-vis-dash-modal-all");
  const dashModalNone = document.getElementById("upr-vis-dash-modal-none");
  if (dashModalAll) dashModalAll.addEventListener("click", () => setDashModalChecks(true));
  if (dashModalNone) dashModalNone.addEventListener("click", () => setDashModalChecks(false));
  const dashModalGo = document.getElementById("upr-vis-dash-modal-go");
  if (dashModalGo) dashModalGo.addEventListener("click", () => beginExport(chosenDashboardIds()));

  if (els.generateIdml) {
    els.generateIdml.addEventListener("click", () => {
      const assignedFormId = parseInt(els.assignment.value, 10);
      if (!assignedFormId) {
        showProgress("is-warn", t("needAssignment"), 0);
        return;
      }
      if (!selectedRowCount()) {
        showProgress("is-warn", t("needCountries"), 0);
        return;
      }
      beginExport(["combined"], "idml");
    });
  }

  async function beginExport(dashboardIds, formatOverride) {
    setDashModalOpen(false);
    const assignedFormId = parseInt(els.assignment.value, 10);
    const format = formatOverride || selectedFormat();
    const aesIds = selectedCountryIds().map((v) => parseInt(v, 10));
    const bundles = selectedBundleNames();
    if (!dashboardIds.length) {
      showProgress("is-warn", t("needDashboards"), 0);
      return;
    }
    if (!aesIds.length && !bundles.length) {
      showProgress("is-warn", t("needCountries"), 0);
      return;
    }
    setRunning(true);
    showProgress("", t("generating"), 0);
    try {
      const body = new FormData();
      body.append("assigned_form_id", String(assignedFormId));
      body.append("export_format", format);
      body.append("include_narrative", includeNarrative(format) ? "1" : "0");
      body.append("only_selected", "1");
      dashboardIds.forEach((id) => body.append("dashboard_ids", id));
      aesIds.forEach((id) => body.append("aes_ids", String(id)));
      bundles.forEach((name) => body.append("bundles", name));
      body.append("lang", shared.getExportLanguage ? shared.getExportLanguage() : "en");
      if (includeNarrative() && els.narratives && els.narratives.files) {
        Array.from(els.narratives.files).forEach((file) => body.append("narratives", file));
      }
      body.append("audience", (els.narrativeAudience && els.narrativeAudience.value) || "auto");
      const response = await fetchFn("/admin/data-exploration/upr/generate", {
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
  }
  if (els.dismiss) els.dismiss.addEventListener("click", () => hideProgress());
  els.cancel.addEventListener("click", async () => {
    if (!jobId) return;
    els.cancel.disabled = true;
    try {
      const response = await fetchFn("/admin/data-exploration/upr/cancel", {
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
