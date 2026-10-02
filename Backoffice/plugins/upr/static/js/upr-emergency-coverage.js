/**
 * Non-blocking notice when a UPR form is missing applicable emergencies
 * or still has an emergency that is no longer in the calculated list.
 * Reporting uses a repeat section. Planning uses the Emergency Appeals matrix
 * rows and the Funding Requirements column headers.
 * This does not register a form-validation error, so submission stays allowed.
 */
(function () {
  const LOOKUP = "emergency_operations";

  function codeFromOption(option) {
    const explicit = (option.dataset.emergencyCode || "").trim();
    if (explicit) return explicit.toUpperCase();
    const text = (option.value || "").trim();
    const part = text.match(/\(part of [A-Za-z0-9]+\)\s*$/i);
    const body = part ? text.slice(0, part.index).trim() : text;
    const codeFirst = body.match(/^([A-Z][A-Z0-9]{4,})\b/);
    if (codeFirst) return codeFirst[1].toUpperCase();
    const nameFirst = body.match(/\(([A-Z][A-Z0-9]{4,})\)\s*$/);
    if (nameFirst) return nameFirst[1].toUpperCase();
    return "";
  }

  function sectionOf(select) {
    return select.closest('[id^="section-container-"]') || select.closest("[data-collapsible-id]");
  }

  function selectsIn(section) {
    return Array.from(section.querySelectorAll('select[data-lookup-list-id="' + LOOKUP + '"]'));
  }

  function listLoaded(selects) {
    return selects.some(function (select) {
      return Array.from(select.options).some(function (option) {
        return option.value && option.value !== "__other__";
      });
    });
  }

  function summarize(section) {
    const selects = selectsIn(section);
    if (!selects.length || !listLoaded(selects)) return null;

    const applicable = new Map();
    const stale = [];
    const selectedCodes = new Set();

    selects.forEach(function (select) {
      Array.from(select.options).forEach(function (option) {
        if (!option.value || option.value === "__other__") return;
        const code = codeFromOption(option);
        if (option.dataset.staleSavedValue === "true") return;
        if (code && !applicable.has(code)) {
          applicable.set(code, option.textContent.trim());
        }
      });
      const chosen = select.options[select.selectedIndex];
      if (!select.value || !chosen) return;
      const code = codeFromOption(chosen);
      if (code) selectedCodes.add(code);
      if (chosen.dataset.staleSavedValue === "true" || (code && !applicable.has(code))) {
        stale.push(chosen.textContent.trim());
      }
    });

    const missing = [];
    applicable.forEach(function (label, code) {
      if (!selectedCodes.has(code)) missing.push(label);
    });
    return { missing: missing, stale: stale };
  }

  function codeFromText(text) {
    return codeFromOption({ dataset: {}, value: text || "" });
  }

  function matrixConfigOf(container) {
    try {
      return JSON.parse(container.getAttribute("data-matrix-config") || "{}");
    } catch (error) {
      return {};
    }
  }

  function headerSelects(container) {
    return Array.from(container.querySelectorAll(
      'select.matrix-header-select[data-header-lookup-list-id="' + LOOKUP + '"]'
    ));
  }

  function matrixHasEmergencyRows(config) {
    const rowMode = String(config.row_mode || "").toLowerCase();
    return (rowMode === "list_library" || rowMode === "hybrid")
      && String(config.lookup_list_id || "") === LOOKUP;
  }

  const rowOptions = new Map();
  const rowOptionLoads = new Set();

  function ensureRowOptions(container) {
    const fieldId = container.dataset.fieldId || "";
    if (!fieldId || rowOptions.has(fieldId) || rowOptionLoads.has(fieldId)) return;
    const csrf = document.querySelector('input[name="csrf_token"]');
    if (!csrf || !csrf.value) return;
    const config = matrixConfigOf(container);
    const search = container.querySelector("[data-display-column]");
    let filters = [];
    try {
      filters = JSON.parse((search && search.getAttribute("data-filters")) || "[]");
    } catch (error) {
      filters = [];
    }
    const body = {
      lookup_list_id: LOOKUP,
      display_column: (search && search.dataset.displayColumn) || "name_with_code",
      filters: filters,
      search_term: "",
      existing_rows: [],
      limit: 5000,
      plugin_config: config.plugin_config || {},
    };
    const aes = document.querySelector('input[name="assignment_entity_status_id"]');
    if (aes && aes.value) body.assignment_entity_status_id = Number(aes.value);
    rowOptionLoads.add(fieldId);
    fetch("/forms/matrix/search-rows", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrf.value,
      },
      body: JSON.stringify(body),
    }).then(function (response) {
      return response.json();
    }).then(function (data) {
      rowOptions.set(fieldId, data && data.success && Array.isArray(data.options) ? data.options : null);
    }).catch(function () {
      rowOptions.set(fieldId, null);
    }).then(function () {
      schedule();
    });
  }

  function realHeaderOptions(select) {
    return Array.from(select.options).filter(function (option) {
      if (!option.value || option.value === "__other__") return false;
      if (option.dataset.storedHeaderValue === "true") return false;
      if (option.dataset.filterMismatch === "true") return false;
      if (option.dataset.goUnmatched === "true") return false;
      return true;
    });
  }

  function summarizeHeaders(selects) {
    if (selects.some(function (select) { return select.dataset.headerState === "error"; })) return null;
    const pending = selects.some(function (select) {
      return select.dataset.headerState !== "ready" && !realHeaderOptions(select).length;
    });
    if (pending) return null;
    const applicable = new Map();
    selects.forEach(function (select) {
      realHeaderOptions(select).forEach(function (option) {
        const label = option.textContent.trim() || option.value;
        const code = codeFromOption(option) || label;
        if (!applicable.has(code)) applicable.set(code, label);
      });
    });
    const selectedCodes = new Set();
    const stale = [];
    selects.forEach(function (select) {
      const chosen = select.options[select.selectedIndex];
      if (!select.value || !chosen || select.value === "__other__") return;
      const label = chosen.textContent.trim() || select.value;
      const code = codeFromOption(chosen) || label;
      const stored = chosen.dataset.storedHeaderValue === "true"
        || chosen.dataset.filterMismatch === "true"
        || chosen.dataset.goUnmatched === "true";
      if (stored || !applicable.has(code)) {
        stale.push(label);
        return;
      }
      selectedCodes.add(code);
    });
    const missing = [];
    applicable.forEach(function (label, code) {
      if (!selectedCodes.has(code)) missing.push(label);
    });
    return { missing: missing, stale: stale };
  }

  function summarizeRows(container, options) {
    const applicable = new Map();
    options.forEach(function (opt) {
      const label = String((opt && (opt.value || opt.label)) || "").trim();
      if (!label) return;
      const code = codeFromText(label) || label;
      if (!applicable.has(code)) applicable.set(code, label);
    });
    const selectedCodes = new Set();
    const stale = [];
    container.querySelectorAll("tr.matrix-data-row[data-row-id]").forEach(function (row) {
      const label = (row.getAttribute("data-row-label") || row.getAttribute("data-row-id") || "").trim();
      if (!label) return;
      const code = codeFromText(label) || label;
      const unmatched = !!row.querySelector(".matrix-go-unmatched-row-header");
      if (unmatched || !applicable.has(code)) {
        stale.push(label);
        return;
      }
      selectedCodes.add(code);
    });
    const missing = [];
    applicable.forEach(function (label, code) {
      if (!selectedCodes.has(code)) missing.push(label);
    });
    return { missing: missing, stale: stale };
  }

  function summarizeMatrix(container) {
    const config = matrixConfigOf(container);
    const selects = headerSelects(container);
    const hasRows = matrixHasEmergencyRows(config);
    if (!hasRows && !selects.length) return undefined;
    if (hasRows) {
      const fieldId = container.dataset.fieldId || "";
      if (!rowOptions.has(fieldId)) {
        ensureRowOptions(container);
        return null;
      }
      const options = rowOptions.get(fieldId);
      if (!options) return null;
      const summary = summarizeRows(container, options);
      if (selects.length) {
        const headers = summarizeHeaders(selects);
        if (!headers) return null;
        summary.missing = summary.missing.concat(headers.missing);
        summary.stale = summary.stale.concat(headers.stale);
      }
      return summary;
    }
    return summarizeHeaders(selects);
  }

  function matrixTitle(container) {
    const block = container.closest(".form-item-block");
    const label = block && block.querySelector("label");
    const text = label ? label.textContent.replace("*", "").trim() : "";
    if (text && text !== "-" && text !== "—") return text;
    const section = sectionOf(container);
    const heading = section && section.querySelector("h2, h3, h4");
    return heading ? heading.textContent.trim() : "";
  }

  function placeMatrixBanner(container, banner) {
    const block = container.closest(".form-item-block");
    const label = block && block.querySelector("label");
    const text = label ? label.textContent.replace("*", "").trim() : "";
    if (label && text && text !== "-" && text !== "—") {
      label.insertAdjacentElement("afterend", banner);
      return;
    }
    const section = sectionOf(container);
    const heading = section && section.querySelector("h2, h3, h4");
    if (heading) heading.insertAdjacentElement("afterend", banner);
    else container.prepend(banner);
  }

  function displayItem(label) {
    const part = String(label || "").match(/\s*\(part of ([A-Za-z0-9]+)\)\s*$/i);
    const parent = part ? part[1].toUpperCase() : "";
    let body = part ? label.slice(0, part.index).trim() : String(label || "").trim();
    let code = "";
    const codeFirst = body.match(/^([A-Z][A-Z0-9]{4,})\s+(.+)$/);
    const nameFirst = body.match(/^(.+?)\s+\(([A-Z][A-Z0-9]{4,})\)\s*$/);
    if (codeFirst) {
      code = codeFirst[1];
      body = codeFirst[2].trim();
    } else if (nameFirst) {
      code = nameFirst[2];
      body = nameFirst[1].trim();
    }
    return { name: body || label, code: code, parent: parent };
  }

  function listGroup(heading, labels) {
    const group = document.createElement("div");
    group.className = "upr-emergency-coverage__group";
    const title = document.createElement("p");
    title.className = "upr-emergency-coverage__heading";
    title.textContent = heading;
    const list = document.createElement("ul");
    labels.forEach(function (label) {
      const item = displayItem(label);
      const li = document.createElement("li");
      const name = document.createElement("span");
      name.className = "upr-emergency-coverage__name";
      name.textContent = item.name;
      li.appendChild(name);
      const metaBits = [];
      if (item.code) metaBits.push(item.code);
      if (item.parent) metaBits.push("part of " + item.parent);
      if (metaBits.length) {
        const meta = document.createElement("span");
        meta.className = "upr-emergency-coverage__meta";
        meta.textContent = metaBits.join(" · ");
        li.appendChild(meta);
      }
      list.appendChild(li);
    });
    group.appendChild(title);
    group.appendChild(list);
    return group;
  }

  function lineFor(label) {
    const item = displayItem(label);
    return item.code ? item.name + " (" + item.code + ")" : item.name;
  }

  const matrixSummaries = new Map();

  function summariesFor(button) {
    let ids = null;
    if (button && button.value === "submit_page") {
      const group = button.closest(".sidebar-scope-group");
      if (!group) return [];
      ids = new Set(Array.from(group.querySelectorAll("a.section-link[data-section-id]")).map(function (link) {
        return link.getAttribute("data-section-id");
      }));
    }
    const seen = new Set();
    const summaries = [];
    document.querySelectorAll('select[data-lookup-list-id="' + LOOKUP + '"]').forEach(function (select) {
      const section = sectionOf(select);
      if (!section || seen.has(section)) return;
      if (ids && !ids.has(section.id)) return;
      seen.add(section);
      const summary = summarize(section);
      if (summary && (summary.missing.length || summary.stale.length)) summaries.push(summary);
    });
    matrixSummaries.forEach(function (entry) {
      if (ids && (!entry.section || !ids.has(entry.section.id))) return;
      if (entry.summary.missing.length || entry.summary.stale.length) {
        summaries.push({ missing: entry.summary.missing, stale: entry.summary.stale, title: entry.title });
      }
    });
    return summaries;
  }

  function confirmBlock(button) {
    const lines = [];
    summariesFor(button).forEach(function (summary) {
      if (summary.title) {
        if (lines.length) lines.push("");
        lines.push(summary.title);
      }
      if (summary.missing.length) {
        if (lines.length) lines.push("");
        lines.push("Not added:");
        summary.missing.forEach(function (label) { lines.push("• " + lineFor(label)); });
      }
      if (summary.stale.length) {
        if (lines.length) lines.push("");
        lines.push("Not applicable:");
        summary.stale.forEach(function (label) { lines.push("• " + lineFor(label)); });
      }
    });
    return lines.join("\n");
  }

  function applyConfirmMessage(button) {
    if (!button || button.type !== "submit") return;
    if (button.value !== "submit" && button.value !== "submit_page") return;
    if (!button.hasAttribute("data-confirm-message") && !button.hasAttribute("data-upr-confirm-base")) return;
    if (!button.hasAttribute("data-upr-confirm-base")) {
      button.setAttribute("data-upr-confirm-base", button.getAttribute("data-confirm-message") || "");
    }
    const base = button.getAttribute("data-upr-confirm-base");
    const extra = confirmBlock(button);
    button.setAttribute("data-confirm-message", extra ? base + "\n\n" + extra : base);
  }

  document.addEventListener("click", function (event) {
    const target = event.target;
    if (!target || !target.closest) return;
    if (target.closest("#fab-submit-btn")) {
      const form = document.getElementById("focalDataEntryForm");
      const pageMode = form && form.dataset.pageSubmission === "true";
      if (pageMode) {
        const activeLink = document.querySelector("#sidebar-nav-scroll a.section-link.is-active");
        const pageId = activeLink && activeLink.closest("[data-page-id]") && activeLink.closest("[data-page-id]").dataset.pageId;
        const pageButton = pageId && document.querySelector('.page-submit-btn[data-page-id="' + CSS.escape(pageId) + '"]');
        if (pageButton) applyConfirmMessage(pageButton);
      } else {
        document.querySelectorAll('#focalDataEntryForm button[type="submit"][name="action"][value="submit"]').forEach(applyConfirmMessage);
      }
      return;
    }
    const button = target.closest('button[type="submit"]');
    if (button) applyConfirmMessage(button);
  }, true);

  function flagText(summary) {
    const parts = [];
    if (summary.missing.length) {
      const noun = summary.missing.length === 1 ? "emergency" : "emergencies";
      parts.push(summary.missing.length + " applicable " + noun + " not added");
    }
    if (summary.stale.length) {
      const noun = summary.stale.length === 1 ? "emergency is" : "emergencies are";
      parts.push(summary.stale.length + " entered " + noun + " not applicable");
    }
    return parts.join(". ");
  }

  function navLinks(section) {
    if (!section.id || typeof CSS === "undefined" || !CSS.escape) return [];
    return Array.from(document.querySelectorAll(
      '#section-navigation-sidebar a.section-link[data-section-id="' + CSS.escape(section.id) + '"]'
    ));
  }

  function statusIcon(link) {
    return link.querySelector(":scope > .section-status-icon");
  }

  function applyStatusWarning(icon, text) {
    if (!icon.classList.contains("upr-emergency-status-icon")) {
      icon.dataset.uprStatusBackup = icon.className;
    }
    const backup = icon.dataset.uprStatusBackup || "";
    const sizeClass = backup.indexOf("w-3") !== -1 ? "w-3 h-3" : "w-4 h-4";
    icon.className = "section-status-icon upr-emergency-status-icon fas fa-exclamation-triangle flex-shrink-0 " + sizeClass;
    icon.title = text;
  }

  function setNavFlag(link, text) {
    const extra = link.querySelector(":scope > .upr-emergency-nav-flag");
    if (extra) extra.remove();
    const icon = statusIcon(link);
    let note = link.querySelector(":scope > .upr-emergency-nav-note");
    if (!text) {
      if (icon && icon.dataset.uprStatusBackup) {
        icon.className = icon.dataset.uprStatusBackup;
        delete icon.dataset.uprStatusBackup;
        icon.removeAttribute("title");
      }
      if (note) note.remove();
      link.classList.remove("upr-emergency-nav-flagged");
      link.removeAttribute("data-upr-emergency-note");
      return;
    }
    if (icon) applyStatusWarning(icon, text);
    if (!note) {
      note = document.createElement("span");
      note.className = "upr-emergency-nav-note";
      link.appendChild(note);
    }
    note.textContent = text;
    link.classList.add("upr-emergency-nav-flagged");
    link.setAttribute("data-upr-emergency-note", text);
  }

  function watchStatusIcons() {
    const root = document.getElementById("section-navigation-sidebar");
    if (!root || root.dataset.uprStatusWatch === "true") return;
    root.dataset.uprStatusWatch = "true";
    const observer = new MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) {
        const icon = mutation.target;
        if (!icon.classList || !icon.classList.contains("section-status-icon")) return;
        if (icon.classList.contains("upr-emergency-status-icon")) return;
        const link = icon.closest("a.section-link.upr-emergency-nav-flagged");
        if (!link) return;
        const text = link.getAttribute("data-upr-emergency-note") || "";
        if (!text) return;
        applyStatusWarning(icon, text);
      });
    });
    observer.observe(root, { subtree: true, attributes: true, attributeFilter: ["class"] });
  }

  function render(section) {
    const summary = summarize(section);
    const bannerId = "upr-emergency-coverage-" + (section.id || "section");
    let banner = document.getElementById(bannerId);
    if (!summary) return;
    const text = summary.missing.length || summary.stale.length ? flagText(summary) : "";
    navLinks(section).forEach(function (link) { setNavFlag(link, text); });
    if (!text) {
      if (banner) banner.remove();
      return;
    }
    if (!banner) {
      banner = document.createElement("div");
      banner.id = bannerId;
      banner.className = "upr-emergency-coverage";
      banner.setAttribute("role", "status");
      const header = section.querySelector("h2, h3, h4");
      if (header && header.parentElement) {
        header.insertAdjacentElement("afterend", banner);
      } else {
        section.prepend(banner);
      }
    }
    banner.replaceChildren();
    if (summary.missing.length) banner.appendChild(listGroup("Not added", summary.missing));
    if (summary.stale.length) banner.appendChild(listGroup("Not applicable", summary.stale));
  }

  function renderMatrix(container, summary) {
    const fieldId = container.dataset.fieldId || "matrix";
    const bannerId = "upr-emergency-coverage-matrix-" + fieldId;
    let banner = document.getElementById(bannerId);
    const text = summary && (summary.missing.length || summary.stale.length);
    if (!text) {
      if (banner) banner.remove();
      matrixSummaries.delete(fieldId);
      return;
    }
    matrixSummaries.set(fieldId, {
      summary: summary,
      section: sectionOf(container),
      title: matrixTitle(container),
    });
    if (!banner) {
      banner = document.createElement("div");
      banner.id = bannerId;
      banner.className = "upr-emergency-coverage";
      banner.setAttribute("role", "status");
      placeMatrixBanner(container, banner);
    }
    banner.replaceChildren();
    if (summary.missing.length) banner.appendChild(listGroup("Not added", summary.missing));
    if (summary.stale.length) banner.appendChild(listGroup("Not applicable", summary.stale));
  }

  function refreshAll() {
    const navText = new Map();
    function addNav(section, summary) {
      if (!section || !summary) return;
      const text = flagText(summary);
      if (!text) return;
      const previous = navText.get(section) || "";
      navText.set(section, previous ? previous + ". " + text : text);
    }

    const seen = new Set();
    document.querySelectorAll('select[data-lookup-list-id="' + LOOKUP + '"]').forEach(function (select) {
      const section = sectionOf(select);
      if (!section || seen.has(section)) return;
      seen.add(section);
      const summary = summarize(section);
      render(section);
      addNav(section, summary);
    });

    const seenMatrices = new Set();
    document.querySelectorAll(".matrix-container").forEach(function (container) {
      const summary = summarizeMatrix(container);
      if (summary === undefined) return;
      const fieldId = container.dataset.fieldId || "";
      seenMatrices.add(fieldId);
      watchMatrix(container);
      if (summary === null) {
        const previous = matrixSummaries.get(fieldId);
        if (previous) addNav(previous.section, previous.summary);
        else scheduleRetry();
        return;
      }
      renderMatrix(container, summary);
      addNav(sectionOf(container), summary);
    });
    matrixSummaries.forEach(function (entry, fieldId) {
      if (!seenMatrices.has(fieldId)) matrixSummaries.delete(fieldId);
    });

    const flagged = new Set();
    navText.forEach(function (text, section) {
      navLinks(section).forEach(function (link) {
        setNavFlag(link, text);
        flagged.add(link);
      });
    });
    document.querySelectorAll("#section-navigation-sidebar a.section-link.upr-emergency-nav-flagged").forEach(function (link) {
      if (!flagged.has(link)) setNavFlag(link, "");
    });
    document.querySelectorAll("#section-navigation-sidebar .sidebar-page-heading > .upr-emergency-nav-flag").forEach(function (flag) {
      flag.remove();
    });
  }

  function watchMatrix(container) {
    if (container.dataset.uprEmergencyWatch === "true") return;
    container.dataset.uprEmergencyWatch = "true";
    const observer = new MutationObserver(schedule);
    observer.observe(container, { childList: true, subtree: true });
  }

  let pending = 0;
  let retryTimer = 0;
  let retries = 0;
  function schedule() {
    if (pending) return;
    pending = window.requestAnimationFrame(function () {
      pending = 0;
      refreshAll();
    });
  }

  function scheduleRetry() {
    if (retryTimer || retries > 20) return;
    retries += 1;
    retryTimer = window.setTimeout(function () {
      retryTimer = 0;
      schedule();
    }, 500);
  }

  document.addEventListener("ifrc:calculated-list-refreshed", schedule);
  document.addEventListener("repeatEntryAdded", schedule);
  document.addEventListener("change", function (event) {
    const target = event.target;
    if (!target || !target.matches) return;
    if (target.matches('select[data-lookup-list-id="' + LOOKUP + '"]')
      || target.matches('select.matrix-header-select[data-header-lookup-list-id="' + LOOKUP + '"]')) {
      schedule();
    }
  });

  watchStatusIcons();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      watchStatusIcons();
      schedule();
    });
  } else {
    schedule();
  }
})();
