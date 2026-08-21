(function (global) {
  let dropzoneApi = null;
  let dropzoneReady = null;

  function csrfToken() {
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
      progressLabel: document.getElementById("upr-visuals-narrative-progress-label"),
    };
  }

  function setModalOpen(open) {
    const { root } = modalEls();
    if (!root) return;
    root.classList.toggle("hidden", !open);
    if (!open) root.setAttribute("hidden", "");
    else root.removeAttribute("hidden");
  }

  function setModalStatus(text, isError) {
    const { status } = modalEls();
    if (!status) return;
    status.textContent = text || "";
    status.classList.toggle("is-error", !!isError);
    status.hidden = !text;
  }

  function setBusy(busy, message) {
    const { root, submit, file, dropzone, progress, progressLabel } = modalEls();
    root?.classList.toggle("is-generating", !!busy);
    dropzone?.classList.toggle("is-generating", !!busy);
    if (submit) submit.disabled = busy || !(file && file.files && file.files[0]);
    if (file) file.disabled = busy;
    if (dropzone) dropzone.style.pointerEvents = busy ? "none" : "";
    if (progress) {
      progress.hidden = !busy;
      if (busy && progressLabel && message) progressLabel.textContent = message;
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
      .catch(() => null);
    return dropzoneReady;
  }

  let narrativeAesId = "";

  function openNarrativeModal(format, aesId) {
    const { format: formatEl } = modalEls();
    narrativeAesId = String(aesId || "");
    if (formatEl) formatEl.value = format === "idml" ? "idml" : "pdf";
    setSubmitLabel(format === "idml" ? "idml" : "pdf");
    setModalStatus("");
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
    const fmt = format && format.value === "idml" ? "idml" : "pdf";
    const body = new FormData();
    body.append("file", chosen);
    body.append("format", fmt);
    setBusy(true, fmt === "idml" ? "Generating InDesign package…" : "Generating PDF…");
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
      const type = response.headers.get("Content-Type") || "";
      if (!response.ok || type.includes("application/json")) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || "Could not generate this report.");
      }
      const blob = await response.blob();
      const fallback = fmt === "idml" ? "UPR visuals - InDesign.zip" : "UPR visuals.pdf";
      saveBlob(blob, filenameFromHeader(response.headers.get("Content-Disposition"), fallback));
      setModalOpen(false);
    } catch (err) {
      setModalStatus(err && err.message ? err.message : "Could not generate this report.", true);
    } finally {
      setBusy(false);
      if (submit && file && file.files && file.files[0]) submit.disabled = false;
    }
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

  function startSimpleDownload(aesId, dashboardId, format) {
    if (format === "idml") {
      window.location.href = `/assignment/${encodeURIComponent(aesId)}/idml`;
      return;
    }
    const kind = format === "pdf" ? "pdf" : "png";
    const path =
      kind === "pdf" && dashboardId === "combined"
        ? `/assignment/${encodeURIComponent(aesId)}/pdf`
        : `/assignment/${encodeURIComponent(aesId)}/${kind}/${encodeURIComponent(dashboardId)}`;
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
      if (format === "pdf-narrative") {
        openNarrativeModal("pdf", aesId);
        return;
      }
      if (format === "idml-narrative") {
        openNarrativeModal("idml", aesId);
        return;
      }
      startSimpleDownload(aesId, dashboardId, format);
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
