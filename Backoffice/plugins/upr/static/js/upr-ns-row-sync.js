/**
 * Unified Country Plan (template 24): a National Society listed in the bilateral
 * support table (955) or in any Funding Requirements table (967, 968, 974) is
 * added to the others when it is not there yet. Removing a row is not propagated.
 */
(function () {
  const MATRIX_IDS = ["955", "967", "968", "974"];
  const NS_ROW_ID = /^\d+$/;
  const INIT_POLL_MS = 300;
  const INIT_POLL_MAX = 200;
  const DEBOUNCE_MS = 150;

  const pending = new Map();
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

  async function reconcile() {
    const rows = Array.from(pending.values());
    pending.clear();
    if (!rows.length) return;
    for (const fieldId of MATRIX_IDS) {
      try {
        await addTo(fieldId, rows);
      } catch (error) {
        (window.__clientWarn || console.warn)("UPR NS row sync failed for matrix " + fieldId, error);
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
    const handler = window.matrixHandler;
    const state = handler && typeof handler.getInitStatus === "function" ? handler.getInitStatus().state : "";
    if (state === "ready") {
      queueAllRows();
      return;
    }
    if (state === "error" || attempt >= INIT_POLL_MAX) return;
    setTimeout(function () { waitForMatrixInit(attempt + 1); }, INIT_POLL_MS);
  }

  function start() {
    if (!MATRIX_IDS.some(containerFor)) return;
    new MutationObserver(onMutations).observe(document.body, { childList: true, subtree: true });
    waitForMatrixInit(0);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
