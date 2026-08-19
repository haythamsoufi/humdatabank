(function () {
  const root = document.getElementById("upr-visuals-admin");
  if (!root) return;

  const els = {
    template: document.getElementById("upr-vis-template"),
    period: document.getElementById("upr-vis-period"),
    dashboards: document.getElementById("upr-vis-dashboards"),
    countries: document.getElementById("upr-vis-countries"),
    generate: document.getElementById("upr-vis-generate"),
    cancel: document.getElementById("upr-vis-cancel"),
    status: document.getElementById("upr-vis-status"),
    download: document.getElementById("upr-vis-download"),
  };
  let pollTimer = null;
  let jobId = null;

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

  async function loadPeriods() {
    const templateId = els.template.value;
    const response = await fetchFn(`/admin/data-exploration/upr-visuals/periods?template_id=${templateId}`, {
      headers: csrfHeaders(),
      credentials: "same-origin",
    });
    const data = await response.json();
    els.period.innerHTML = '<option value="">Select a period</option>';
    (data.periods || []).forEach((name) => {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = name;
      els.period.appendChild(opt);
    });
    els.countries.innerHTML = "";
    els.dashboards.innerHTML = "";
  }

  async function loadAssignments() {
    const templateId = els.template.value;
    const period = els.period.value;
    if (!period) return;
    const response = await fetchFn(
      `/admin/data-exploration/upr-visuals/assignments?template_id=${templateId}&period_name=${encodeURIComponent(period)}`,
      { headers: csrfHeaders(), credentials: "same-origin" }
    );
    const data = await response.json();
    els.dashboards.innerHTML = "";
    (data.dashboards || []).forEach((dash) => {
      const id = `upr-dash-${dash.id}`;
      const label = document.createElement("label");
      label.className = "flex items-center gap-2 text-sm";
      label.innerHTML = `<input type="checkbox" value="${dash.id}" ${dash.id === "combined" ? "checked" : ""}> ${dash.title}`;
      els.dashboards.appendChild(label);
    });
    els.countries.innerHTML = "";
    (data.assignments || []).forEach((row) => {
      const label = document.createElement("label");
      label.className = "flex items-center gap-2 text-sm";
      label.innerHTML = `<input type="checkbox" value="${row.aes_id}" checked> ${row.country_name || row.iso3} (${row.iso3})`;
      els.countries.appendChild(label);
    });
  }

  function selectedValues(container) {
    return Array.from(container.querySelectorAll("input[type=checkbox]:checked")).map((el) => el.value);
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
    els.status.textContent = `${status.status || ""} — ${status.message || ""} (${pct}%)`;
    if (status.status === "completed" && status.zip_key) {
      els.download.href = `/admin/data-exploration/upr-visuals/download/${encodeURIComponent(jobId)}`;
      els.download.classList.remove("hidden");
      clearInterval(pollTimer);
      pollTimer = null;
    }
    if (status.status === "failed" || status.status === "cancelled") {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  els.template.addEventListener("change", loadPeriods);
  els.period.addEventListener("change", loadAssignments);
  els.generate.addEventListener("click", async () => {
    const dashboardIds = selectedValues(els.dashboards);
    const aesIds = selectedValues(els.countries).map((v) => parseInt(v, 10));
    els.download.classList.add("hidden");
    const response = await fetchFn("/admin/data-exploration/upr-visuals/generate", {
      method: "POST",
      headers: csrfHeaders(),
      credentials: "same-origin",
      body: JSON.stringify({
        template_id: parseInt(els.template.value, 10),
        period_name: els.period.value,
        dashboard_ids: dashboardIds,
        aes_ids: aesIds,
      }),
    });
    const data = await response.json();
    if (!response.ok || data.success === false) {
      els.status.textContent = data.error || "Could not start export.";
      return;
    }
    jobId = data.job_id;
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(poll, 1500);
    poll();
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

  loadPeriods();
})();
