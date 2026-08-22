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

  global.UprVisualsShared = {
    csrfToken,
    csrfHeaders,
    rememberHtml,
    renderDashboardTabs,
    markActiveTab,
  };
})(window);
