/**
 * Unified Country Plan (template 24): a National Society listed in the planned
 * bilateral support table (955) or in any Funding Requirements table (967, 968, 974)
 * is added to the others when it is not there yet. Removing a row is not propagated.
 *
 * A funding amount entered for that society under a strategic-priority or enabling
 * column of the first funding-requirements matrix (967) also ticks the same
 * column on planned bilateral support. The later-year matrices do not. Clearing
 * the amount does not untick it.
 */
(function () {
  const BILATERAL_ID = "955";
  const FUNDING_IDS = ["967", "968", "974"];
  // Only the first funding-requirements matrix drives planned-support ticks.
  const TICK_FUNDING_ID = FUNDING_IDS[0];
  const MATRIX_IDS = [BILATERAL_ID].concat(FUNDING_IDS);
  const NS_ROW_ID = /^\d+$/;
  const INIT_POLL_MS = 300;
  const INIT_POLL_MAX = 200;
  const DEBOUNCE_MS = 150;

  const pending = new Map();
  // rowId -> Set of bilateral tick column names to check.
  const pendingTicks = new Map();
  // Sorting re-inserts existing rows; only rows not seen before are propagated.
  const seenRows = new WeakSet();
  let timer = null;
  let queue = Promise.resolve();

  function containerFor(fieldId) {
    return document.querySelector('.matrix-container[data-field-id="' + fieldId + '"]');
  }

  function readRow(tr) {
    const rowId = tr.getAttribute("data-row-id") || "";
    if (!NS_ROW_ID.test(rowId)) return null;
    let data = null;
    try {
      data = JSON.parse(tr.getAttribute("data-row-data") || "null");
    } catch (error) {
      data = null;
    }
    return {
      rowId: rowId,
      label: tr.getAttribute("data-row-label") || rowId,
      data: data || { _id: rowId, id: rowId },
    };
  }

  function hasRow(container, rowId) {
    return !!container.querySelector('tr.matrix-data-row[data-row-id="' + rowId + '"]');
  }

  function queueRow(tr, force) {
    if (!force && seenRows.has(tr)) return;
    seenRows.add(tr);
    const container = tr.closest(".matrix-container");
    if (!container || MATRIX_IDS.indexOf(container.dataset.fieldId) === -1) return;
    const row = readRow(tr);
    if (row) pending.set(row.rowId, row);
  }

  // A matrix grouped by a lookup column needs that column on the row data.
  async function withLookupData(handler, config, rows) {
    if (!config.group_by_column || typeof handler.resolveRowIdsToNames !== "function") return rows;
    const infos = new Map(rows.map(function (row) {
      return [row.rowId, { rowId: row.rowId, rowName: null, cellKeys: [], values: {} }];
    }));
    await handler.resolveRowIdsToNames(infos, config.lookup_list_id, config.list_display_column);
    return rows.map(function (row) {
      const info = infos.get(row.rowId);
      if (info && info.rowData && info.rowName && info.rowName !== row.rowId) {
        return { rowId: row.rowId, label: info.rowName, data: info.rowData };
      }
      return row;
    });
  }

  async function addTo(fieldId, rows) {
    const handler = window.matrixHandler;
    const container = containerFor(fieldId);
    if (!handler || !container || !handler.matrices || !handler.matrices.has(fieldId)) return;
    if (typeof handler._canEditMatrix === "function" && !handler._canEditMatrix(container)) return;

    const missing = rows.filter(function (row) { return !hasRow(container, row.rowId); });
    if (!missing.length) return;

    const config = handler.matrices.get(fieldId).config || {};
    const resolved = await withLookupData(handler, config, missing);
    resolved.forEach(function (row) {
      handler.addDynamicRow(fieldId, row.label, row.data, row.rowId, false);
    });
    if (typeof handler.sortMatrixRows === "function") handler.sortMatrixRows(fieldId);
    if (typeof handler.updateLegendVisibility === "function") handler.updateLegendVisibility(fieldId);
  }

  function bilateralTickColumns() {
    const matrix = window.matrixHandler && window.matrixHandler.matrices
      ? window.matrixHandler.matrices.get(BILATERAL_ID)
      : null;
    const names = new Set();
    ((matrix && matrix.config && matrix.config.columns) || []).forEach(function (column) {
      if (column && typeof column === "object" && column.type === "tick" && column.name) {
        names.add(column.name);
      }
    });
    return names;
  }

  function fundingAmount(input) {
    const raw = String(input.value == null ? "" : input.value).replace(/[\s,]/g, "");
    if (!raw) return null;
    const amount = Number(raw);
    return Number.isFinite(amount) ? amount : null;
  }

  // The queued keystroke can be deleted before the tick runs. Only the first
  // funding matrix counts; an amount in a later year does not keep the tick.
  function fundingColumnHasAmount(rowId, column) {
    const container = containerFor(TICK_FUNDING_ID);
    if (!container) return false;
    return Array.from(container.querySelectorAll(
      'input[data-row-id="' + rowId + '"][data-column="' + column + '"]'
    )).some(function (input) {
      if (input.type === "checkbox") return false;
      const amount = fundingAmount(input);
      return amount != null && amount !== 0;
    });
  }

  // A non-zero funding figure for a PNS under a column that planned bilateral
  // support ticks (SP1–SP5, Enabling Functions). Emergency columns have no tick.
  function queueTickFromInput(fieldId, input) {
    if (String(fieldId) !== TICK_FUNDING_ID || !input || input.type === "checkbox") return;
    const rowId = input.dataset.rowId || "";
    const column = input.dataset.column || "";
    if (!NS_ROW_ID.test(rowId) || !bilateralTickColumns().has(column)) return;
    const amount = fundingAmount(input);
    if (amount == null || amount === 0) return;

    let columns = pendingTicks.get(rowId);
    if (!columns) {
      columns = new Set();
      pendingTicks.set(rowId, columns);
    }
    columns.add(column);

    const bilateral = containerFor(BILATERAL_ID);
    if (!bilateral || !hasRow(bilateral, rowId)) {
      const tr = input.closest("tr.matrix-data-row");
      if (tr) queueRow(tr, true);
    }
    schedule();
  }

  function installFundingHook() {
    const handler = window.matrixHandler;
    if (!handler || handler.__uprFundingTickHook || typeof handler.updateMatrixData !== "function") return;
    const original = handler.updateMatrixData;
    handler.updateMatrixData = function (fieldId, input) {
      const result = original.apply(this, arguments);
      try {
        queueTickFromInput(fieldId, input);
      } catch (error) {
        (window.__clientWarn || console.warn)("UPR bilateral tick sync failed", error);
      }
      return result;
    };
    handler.__uprFundingTickHook = true;
  }

  // Typing, change, and paste all end in updateMatrixData. The document
  // listener covers the keystroke itself, including when the matrix handler
  // object is replaced, and re-binds the paste hook onto the current one.
  function onFundingEdit(event) {
    const input = event.target;
    if (!input || input.nodeType !== 1 || typeof input.closest !== "function") return;
    const container = input.closest(".matrix-container");
    if (!container || FUNDING_IDS.indexOf(container.dataset.fieldId) === -1) return;
    installFundingHook();
    queueTickFromInput(container.dataset.fieldId, input);
  }

  async function applyTicks(ticks) {
    const handler = window.matrixHandler;
    const container = containerFor(BILATERAL_ID);
    if (!handler || !container || typeof handler.updateMatrixData !== "function") return;
    if (typeof handler._canEditMatrix === "function" && !handler._canEditMatrix(container)) return;

    let touched = false;
    ticks.forEach(function (columns, rowId) {
      columns.forEach(function (column) {
        const input = container.querySelector(
          'input[type="checkbox"][data-row-id="' + rowId + '"][data-column="' + column + '"]'
        );
        if (!input || input.checked || input.disabled) return;
        if (!fundingColumnHasAmount(rowId, column)) return;
        input.checked = true;
        input.dataset.userEdited = "1";
        handler.updateMatrixData(BILATERAL_ID, input);
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
        touched = true;
      });
    });
    if (touched && typeof handler.calculateMatrixTotals === "function") {
      handler.calculateMatrixTotals(BILATERAL_ID);
    }
  }

  async function reconcile() {
    const rows = Array.from(pending.values());
    const ticks = new Map();
    pendingTicks.forEach(function (columns, rowId) {
      ticks.set(rowId, new Set(columns));
    });
    pending.clear();
    pendingTicks.clear();
    if (!rows.length && !ticks.size) return;
    for (const fieldId of MATRIX_IDS) {
      try {
        await addTo(fieldId, rows);
      } catch (error) {
        (window.__clientWarn || console.warn)("UPR NS row sync failed for matrix " + fieldId, error);
      }
    }
    if (ticks.size) {
      try {
        await applyTicks(ticks);
      } catch (error) {
        (window.__clientWarn || console.warn)("UPR bilateral tick sync failed", error);
      }
    }
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(function () {
      queue = queue.then(reconcile);
    }, DEBOUNCE_MS);
  }

  function onMutations(mutations) {
    let queued = false;
    mutations.forEach(function (mutation) {
      mutation.addedNodes.forEach(function (node) {
        if (node.nodeType !== 1) return;
        if (node.matches("tr.matrix-data-row")) {
          queueRow(node, false);
          queued = true;
        } else if (node.matches("tbody")) {
          node.querySelectorAll("tr.matrix-data-row").forEach(function (tr) { queueRow(tr, false); });
          queued = true;
        }
      });
    });
    if (queued && pending.size) schedule();
  }

  function queueAllRows() {
    MATRIX_IDS.forEach(function (fieldId) {
      const container = containerFor(fieldId);
      if (container) container.querySelectorAll("tr.matrix-data-row").forEach(function (tr) { queueRow(tr, true); });
    });
    if (pending.size) schedule();
  }

  function waitForMatrixInit(attempt) {
    installFundingHook();
    const handler = window.matrixHandler;
    const state = handler && typeof handler.getInitStatus === "function" ? handler.getInitStatus().state : "";
    if (state === "ready") {
      queueAllRows();
      return;
    }
    if (state === "error" || attempt >= INIT_POLL_MAX) return;
    setTimeout(function () { waitForMatrixInit(attempt + 1); }, INIT_POLL_MS);
  }

  let rowObserver = null;

  function stop() {
    if (rowObserver) rowObserver.disconnect();
    rowObserver = null;
    clearTimeout(timer);
    document.removeEventListener("input", onFundingEdit);
    document.removeEventListener("change", onFundingEdit);
  }

  function start() {
    if (!MATRIX_IDS.some(containerFor)) return;
    if (typeof window.__uprNsRowSyncStop === "function") window.__uprNsRowSyncStop();
    window.__uprNsRowSyncStop = stop;
    installFundingHook();
    document.addEventListener("input", onFundingEdit);
    document.addEventListener("change", onFundingEdit);
    rowObserver = new MutationObserver(onMutations);
    rowObserver.observe(document.body, { childList: true, subtree: true });
    waitForMatrixInit(0);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
