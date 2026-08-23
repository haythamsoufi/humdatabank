(function (global) {
  let dropzoneApi = null;
  let dropzoneReady = null;

  function csrfToken() {
    if (global.UprVisualsShared && typeof global.UprVisualsShared.csrfToken === "function") {
      return global.UprVisualsShared.csrfToken();
    }
    if (typeof global.getCSRFToken === "function") {
      return global.getCSRFToken() || "";
    }
    return (
      document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") ||
      document.querySelector('input[name="csrf_token"]')?.value ||
      ""
    );
  }

  function filenameFromHeader(header, fallback) {
    const raw = header || "";
    const utf = raw.match(/filename\*=UTF-8''([^;]+)/i);
    if (utf) {
      try {
        return decodeURIComponent(utf[1]);
      } catch (_err) {
        return fallback;
      }
    }
    const ascii = raw.match(/filename="([^"]+)"/i);
    return ascii ? ascii[1] : fallback;
  }

  function saveBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function modalEls() {
    return {
      root: document.getElementById("upr-visuals-narrative-modal"),
      format: document.getElementById("upr-visuals-narrative-format"),
      file: document.getElementById("upr-visuals-narrative-file"),
      status: document.getElementById("upr-visuals-narrative-status"),
      submit: document.getElementById("upr-visuals-narrative-submit"),
      dropzone: document.getElementById("upr-visuals-narrative-dropzone"),
      progress: document.getElementById("upr-visuals-narrative-progress"),
      progressBar: document.querySelector("#upr-visuals-narrative-progress .upr-visuals-narrative-progress__bar"),
      progressLabel: document.getElementById("upr-visuals-narrative-progress-label"),
    };
  }

  let lastModalFocus = null;
  let modalKeyHandler = null;

  function focusableIn(root) {
    return Array.from(
      root.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])')
    ).filter((el) => !el.disabled && el.offsetParent !== null);
  }

  function setModalOpen(open) {
    const { root } = modalEls();
    if (!root) return;
    if (open) {
      lastModalFocus = document.activeElement;
      root.classList.remove("hidden");
      root.removeAttribute("hidden");
      const focusable = focusableIn(root);
      (focusable[0] || root).focus();
      modalKeyHandler = (event) => {
        if (event.key !== "Tab") return;
        const items = focusableIn(root);
        if (!items.length) return;
        const first = items[0];
        const last = items[items.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      };
      document.addEventListener("keydown", modalKeyHandler);
    } else {
      root.classList.add("hidden");
      root.setAttribute("hidden", "");
      if (modalKeyHandler) {
        document.removeEventListener("keydown", modalKeyHandler);
        modalKeyHandler = null;
      }
      if (lastModalFocus && typeof lastModalFocus.focus === "function") {
        lastModalFocus.focus();
      }
    }
  }

  function setModalStatus(text, isError) {
    const { status } = modalEls();
    if (!status) return;
    status.textContent = text || "";
    status.classList.toggle("is-error", !!isError);
    status.hidden = !text;
  }

  function formatElapsed(seconds) {
    const s = Math.max(0, Math.floor(Number(seconds) || 0));
    const m = Math.floor(s / 60);
    return m + ":" + String(s % 60).padStart(2, "0");
  }

  let liveTimer = null;
  let liveStartedAt = 0;
  let lastProgress = { extras: null, message: "" };

  function stopLiveTimer() {
    if (liveTimer) {
      clearInterval(liveTimer);
      liveTimer = null;
    }
    liveStartedAt = 0;
    lastProgress = { extras: null, message: "" };
  }

  function liveElapsedSeconds(serverElapsed) {
    const fromClient = liveStartedAt ? Math.floor((Date.now() - liveStartedAt) / 1000) : 0;
    const fromServer = Math.max(0, Math.floor(Number(serverElapsed) || 0));
    return Math.max(fromClient, fromServer);
  }

  function paintProgressLabel(message, extras) {
    const { progressLabel } = modalEls();
    if (!progressLabel) return;
    const step = extras && Number(extras.progress);
    const total = extras && Number(extras.total);
    const parts = [];
    if (total > 0 && step >= 0) parts.push(step + "/" + total);
    if (message) parts.push(message);
    const elapsed = liveElapsedSeconds(extras && extras.elapsed_s);
    if (elapsed > 0) parts.push(formatElapsed(elapsed));
    if (parts.length) progressLabel.textContent = parts.join(" · ");
  }

  function setBusy(busy, message, extras) {
    const { root, submit, file, dropzone, progress, progressBar } = modalEls();
    root?.classList.toggle("is-generating", !!busy);
    dropzone?.classList.toggle("is-generating", !!busy);
    if (submit) submit.disabled = busy || !(file && file.files && file.files[0]);
    if (file) file.disabled = busy;
    if (dropzone) dropzone.style.pointerEvents = busy ? "none" : "";
    if (busy && !liveStartedAt) {
      liveStartedAt = Date.now();
      liveTimer = setInterval(() => {
        if (lastProgress.message || lastProgress.extras) {
          paintProgressLabel(lastProgress.message, lastProgress.extras);
        }
      }, 1000);
    }
    if (!busy) stopLiveTimer();
    if (progress) {
      progress.hidden = !busy;
      const step = extras && Number(extras.progress);
      const total = extras && Number(extras.total);
      const chunkDone = extras && Number(extras.chunk_done);
      const chunkTotal = extras && Number(extras.chunk_total);
      if (progressBar) {
        const determinate = busy && total > 0 && step > 0;
        progressBar.classList.toggle("is-determinate", determinate);
        if (determinate) {
          const intra = chunkTotal > 0 ? Math.min(1, chunkDone / chunkTotal) : 0;
          const ratio = chunkTotal > 0 ? (step - 1 + intra) / total : step / total;
          progressBar.style.width = Math.max(8, Math.min(100, Math.round(ratio * 100))) + "%";
        } else {
          progressBar.style.width = "";
        }
      }
      if (busy) {
        lastProgress = { extras: extras || {}, message: message || "" };
        paintProgressLabel(message, extras);
      }
    }
    if (busy) setModalStatus("");
  }

  function setSubmitLabel(format) {
    const { submit } = modalEls();
    if (!submit) return;
    const labelEl = submit.querySelector("[data-upr-narrative-submit-label]");
    const key = format === "idml" ? "labelIdml" : "labelPdf";
    const text = submit.dataset[key] || (format === "idml" ? "Generate InDesign" : "Generate PDF");
    if (labelEl) labelEl.textContent = text;
  }

  function ensureDropzone() {
    if (dropzoneReady) return dropzoneReady;
    const { root, dropzone, submit } = modalEls();
    if (!dropzone) {
      dropzoneReady = Promise.resolve(null);
      return dropzoneReady;
    }
    const moduleUrl = root?.dataset?.dropzoneModule || "/static/js/components/excel-import-dropzone.js";
    dropzoneReady = import(moduleUrl)
      .then((mod) => {
        dropzoneApi = mod.initExcelImportDropzone(dropzone, {
          acceptExtensions: [".docx"],
          variant: "neutral",
          submitBtn: submit,
          requireValidation: false,
          maxSizeBytes: 20 * 1024 * 1024,
          invalidFileTypeLabel: "Please upload a Word document (.docx)",
          maxSizeLabel: "File is too large (20 MB maximum)",
        });
        return dropzoneApi;
      })
      .catch(() => {
        setModalStatus("Could not load the file picker. Use a .docx file of 20 MB or less.", true);
        return null;
      });
    return dropzoneReady;
  }

  let narrativeAesId = "";

  function openNarrativeModal(format, aesId) {
    const { format: formatEl } = modalEls();
    narrativeAesId = String(aesId || "");
    if (formatEl) formatEl.value = format === "idml" ? "idml" : "pdf";
    setSubmitLabel(format === "idml" ? "idml" : "pdf");
    setModalStatus("");
    if (global.UprVisualsShared && typeof global.UprVisualsShared.updateNarrativeTranslateHints === "function") {
      global.UprVisualsShared.updateNarrativeTranslateHints();
    }
    setModalOpen(true);
    ensureDropzone().then((api) => {
      if (api && typeof api.reset === "function") api.reset();
      setBusy(false);
    });
  }

  async function submitNarrative() {
    const { format, file, submit } = modalEls();
    const aesId = narrativeAesId;
    const chosen = file && file.files && file.files[0];
    if (!aesId) {
      setModalStatus("Select an assignment first.", true);
      return;
    }
    if (!chosen) {
      setModalStatus("Choose a Word document (.docx).", true);
      return;
    }
    const name = (chosen.name || "").toLowerCase();
    if (!name.endsWith(".docx")) {
      setModalStatus("Please upload a Word document (.docx)", true);
      return;
    }
    if (chosen.size > 20 * 1024 * 1024) {
      setModalStatus("File is too large (20 MB maximum)", true);
      return;
    }
    const fmt = format && format.value === "idml" ? "idml" : "pdf";
    const body = new FormData();
    body.append("file", chosen);
    body.append("format", fmt);
    const lang =
      (global.UprVisualsShared && typeof global.UprVisualsShared.getExportLanguage === "function"
        ? global.UprVisualsShared.getExportLanguage()
        : "") || "en";
    body.append("lang", lang);
    setBusy(true, fmt === "idml" ? "Queued InDesign package…" : "Queued PDF…");
    try {
      const headers = { "X-Requested-With": "XMLHttpRequest" };
      const token = csrfToken();
      if (token) {
        headers["X-CSRFToken"] = token;
        body.append("csrf_token", token);
      }
      const response = await fetch(`/assignment/${encodeURIComponent(aesId)}/visuals/narrative`, {
        method: "POST",
        body,
        headers,
        credentials: "same-origin",
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.job_id) {
        throw new Error(data.error || "Could not generate this report.");
      }
      const fileResponse = await pollExportJob(aesId, data.job_id, fmt);
      const blob = await fileResponse.blob();
      const fallback = fmt === "idml" ? "UPR visuals - InDesign.zip" : "UPR visuals.pdf";
      saveBlob(blob, filenameFromHeader(fileResponse.headers.get("Content-Disposition"), fallback));
      setModalOpen(false);
    } catch (err) {
      setModalStatus(err && err.message ? err.message : "Could not generate this report.", true);
    } finally {
      setBusy(false);
      if (submit && file && file.files && file.files[0]) submit.disabled = false;
    }
  }

  const POLL_INTERVAL_MS = 1500;
  const POLL_MAX_MS = 8 * 60 * 1000;

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function pollExportJob(aesId, jobId, fmt, onStatus) {
    const started = Date.now();
    const statusUrl =
      `/assignment/${encodeURIComponent(aesId)}/visuals/narrative/status?job_id=${encodeURIComponent(jobId)}`;
    while (Date.now() - started < POLL_MAX_MS) {
      const response = await fetch(statusUrl, { credentials: "same-origin" });
      const data = await response.json().catch(() => ({}));
      const status = (data.status && data.status.status) || data.status || "";
      const payload = data.status && typeof data.status === "object" ? data.status : {};
      const message = payload.message || "";
      if (typeof onStatus === "function") {
        onStatus(payload);
      } else if (message || payload.progress) {
        setBusy(true, message, payload);
      }
      if (!response.ok) {
        throw new Error(data.error || "Could not generate this report.");
      }
      if (status === "completed") {
        const fileResponse = await fetch(
          `/assignment/${encodeURIComponent(aesId)}/visuals/narrative/file/${encodeURIComponent(jobId)}`,
          { credentials: "same-origin" }
        );
        const type = fileResponse.headers.get("Content-Type") || "";
        if (!fileResponse.ok || type.includes("application/json")) {
          const errBody = await fileResponse.json().catch(() => ({}));
          throw new Error(errBody.error || "Could not generate this report.");
        }
        return fileResponse;
      }
      if (status === "failed" || status === "cancelled") {
        throw new Error((data.status && data.status.error) || "Could not generate this report.");
      }
      await sleep(POLL_INTERVAL_MS);
    }
    throw new Error(
      fmt === "idml"
        ? "InDesign export is taking too long. Try again in a moment."
        : fmt === "png"
          ? "PNG export is taking too long. Try again in a moment."
          : "PDF export is taking too long. Try again in a moment."
    );
  }

  function bindNarrativeModal() {
    const { root, submit } = modalEls();
    if (!root || root.dataset.bound === "1") return;
    root.dataset.bound = "1";
    root.querySelectorAll(".close-modal, .upr-visuals-narrative-close").forEach((el) => {
      el.addEventListener("click", () => setModalOpen(false));
    });
    root.addEventListener("click", (event) => {
      if (event.target === root) setModalOpen(false);
    });
    submit?.addEventListener("click", () => {
      submitNarrative();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      if (!root.classList.contains("hidden")) setModalOpen(false);
    });
    ensureDropzone();
  }

  function withLang(url) {
    if (global.UprVisualsShared && typeof global.UprVisualsShared.withLang === "function") {
      return global.UprVisualsShared.withLang(url);
    }
    return url;
  }

  function downloadStatusEl(box) {
    if (!box) return null;
    let el = box.querySelector(".upr-visuals-download__status");
    if (el) return el;
    el = document.createElement("span");
    el.className = "upr-visuals-download__status";
    el.setAttribute("role", "status");
    el.hidden = true;
    box.appendChild(el);
    return el;
  }

  function setDownloadBusy(box, button, busy, message, isError) {
    if (box) box.classList.toggle("is-busy", !!busy || !!isError);
    if (button) {
      button.disabled = !!busy;
      button.setAttribute("aria-busy", busy ? "true" : "false");
    }
    const icon = button && button.querySelector("i");
    if (icon) {
      icon.classList.toggle("fa-download", !busy);
      icon.classList.toggle("fa-spinner", !!busy);
      icon.classList.toggle("fa-spin", !!busy);
    }
    const status = downloadStatusEl(box);
    if (!status) return;
    const text = message || "";
    status.textContent = text;
    status.hidden = !text;
    status.classList.toggle("is-error", !!isError);
  }

  async function startInPagePngDownload(aesId, dashboardId, ui) {
    const box = ui && ui.box;
    const button = ui && ui.button;
    if (box && box.classList.contains("is-busy") && button && button.disabled) return;
    const url = withLang(`/assignment/${encodeURIComponent(aesId)}/png/${encodeURIComponent(dashboardId)}`);
    setDownloadBusy(box, button, true, "Preparing PNG…");
    try {
      const response = await fetch(url, {
        headers: { Accept: "application/json", "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin",
      });
      const type = response.headers.get("Content-Type") || "";
      if (type.includes("text/html")) {
        window.location.href = url;
        return;
      }
      const data = await response.json().catch(() => ({}));
      if (!response.ok || !data.job_id) {
        throw new Error(data.error || "Could not generate this image.");
      }
      const fileResponse = await pollExportJob(aesId, data.job_id, "png", (payload) => {
        const raw = (payload && payload.message) || "";
        const label =
          raw === "Ready" || raw === "Generating PNG…" || raw.indexOf("Waiting for PDF") === 0
            ? "Preparing PNG…"
            : raw || "Preparing PNG…";
        setDownloadBusy(box, button, true, label);
      });
      const blob = await fileResponse.blob();
      saveBlob(blob, filenameFromHeader(fileResponse.headers.get("Content-Disposition"), "visuals.png"));
      setDownloadBusy(box, button, false, "");
    } catch (err) {
      setDownloadBusy(
        box,
        button,
        false,
        err && err.message ? err.message : "Could not generate this image.",
        true
      );
    }
  }

  function startSimpleDownload(aesId, dashboardId, format, ui) {
    if (format === "png") {
      startInPagePngDownload(aesId, dashboardId, ui);
      return;
    }
    if (format === "idml") {
      window.location.href = withLang(`/assignment/${encodeURIComponent(aesId)}/idml`);
      return;
    }
    const kind = format === "pdf" ? "pdf" : "png";
    const path =
      kind === "pdf" && dashboardId === "combined"
        ? withLang(`/assignment/${encodeURIComponent(aesId)}/pdf`)
        : withLang(`/assignment/${encodeURIComponent(aesId)}/${kind}/${encodeURIComponent(dashboardId)}`);
    if (kind === "pdf" && dashboardId === "combined") {
      window.open(path, "_blank", "noopener");
    } else {
      window.location.href = path;
    }
  }

  function bindDownloadMenu({ button, menu, wrap, aesIdFn, dashboardFn }) {
    if (!button || !menu) return;
    bindNarrativeModal();
    const box = wrap || button.closest(".upr-visuals-download");
    function setOpen(open) {
      box?.classList.toggle("is-open", open);
      button.setAttribute("aria-expanded", open ? "true" : "false");
    }
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      if (button.disabled) return;
      setOpen(!box?.classList.contains("is-open"));
    });
    menu.addEventListener("click", (event) => {
      const item = event.target.closest("[data-format]");
      if (!item) return;
      const format = item.dataset.format;
      const aesId = aesIdFn();
      const dashboardId = dashboardFn() || "combined";
      setOpen(false);
      if (!aesId) return;
      if (box && box.classList.contains("is-busy") && button && button.disabled) return;
      if (format === "pdf-narrative") {
        openNarrativeModal("pdf", aesId);
        return;
      }
      if (format === "idml-narrative") {
        openNarrativeModal("idml", aesId);
        return;
      }
      startSimpleDownload(aesId, dashboardId, format, { box, button });
    });
    document.addEventListener("click", (event) => {
      if (!box || box.contains(event.target)) return;
      setOpen(false);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") setOpen(false);
    });
  }

  global.UprVisualsDownload = {
    bindDownloadMenu,
    openNarrativeModal,
  };
})(window);
