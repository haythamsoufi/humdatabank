(function () {
  var statusUrl = document.body && document.body.getAttribute("data-status-url");
  var fileUrl = document.body && document.body.getAttribute("data-file-url");
  var openMode = (document.body && document.body.getAttribute("data-file-open")) || "download";
  if (!statusUrl || !fileUrl) return;

  var started = Date.now();
  var maxMs = 8 * 60 * 1000;
  var lastPayload = {};
  var friendly = {
    Queued: "Gathering the latest figures…",
    "Starting export…": "Gathering the latest figures…",
    "Generating PDF…": "Laying out the pages…",
    "Generating PNG…": "Rendering the image…",
    "Generating InDesign package…": "Packaging the layout…",
    Ready: "Opening your file…",
  };

  function fail(message) {
    var card = document.querySelector(".upr-export-wait");
    var status = document.getElementById("upr-export-wait-status");
    var elapsed = document.getElementById("upr-export-wait-elapsed");
    var heading = card && card.querySelector("h1");
    if (card) card.setAttribute("data-failed", "1");
    if (heading) heading.textContent = "Could not prepare this file";
    if (status) status.textContent = message || "Something went wrong. Try again in a moment.";
    if (elapsed) elapsed.textContent = "";
  }

  function formatElapsed(ms) {
    var secs = Math.floor(ms / 1000);
    if (secs <= 0) return "";
    var m = Math.floor(secs / 60);
    var s = secs % 60;
    return m + ":" + (s < 10 ? "0" : "") + s;
  }

  function friendlyMessage(payload) {
    var raw = (payload && payload.message) || "";
    return friendly[raw] || raw || "Gathering the latest figures…";
  }

  function paint(payload) {
    var status = document.getElementById("upr-export-wait-status");
    var elapsed = document.getElementById("upr-export-wait-elapsed");
    if (status) status.textContent = friendlyMessage(payload);
    if (elapsed) elapsed.textContent = formatElapsed(Date.now() - started);
  }

  function showInlineFile() {
    // Navigating this document to the PDF makes Chrome download it and leave
    // this screen in place. A framed load renders the file in the page.
    document.documentElement.style.height = "100%";
    document.body.replaceChildren();
    document.body.style.cssText =
      "margin:0;height:100%;height:100dvh;display:block;background:#525659;overflow:hidden";
    var frame = document.createElement("iframe");
    frame.src = fileUrl;
    frame.title = document.title || "PDF";
    frame.style.cssText =
      "position:fixed;inset:0;border:0;width:100%;height:100%;height:100dvh;background:#525659";
    document.body.appendChild(frame);
  }

  function poll() {
    if (Date.now() - started > maxMs) {
      fail("This is taking longer than expected. Try again in a moment.");
      return;
    }
    fetch(statusUrl, { credentials: "same-origin" })
      .then(function (response) {
        return response.json().then(function (data) {
          return { ok: response.ok, data: data };
        });
      })
      .then(function (result) {
        var data = result.data || {};
        var payload = data.status && typeof data.status === "object" ? data.status : {};
        var status = payload.status || data.status || "";
        lastPayload = payload;
        if (!result.ok) {
          fail(data.error || "Something went wrong. Try again in a moment.");
          return;
        }
        if (status === "completed") {
          if (openMode === "inline") showInlineFile();
          else window.location.replace(fileUrl);
          return;
        }
        if (status === "failed" || status === "cancelled") {
          fail(payload.error || "Something went wrong. Try again in a moment.");
          return;
        }
        paint(payload);
        setTimeout(poll, 400);
      })
      .catch(function () {
        paint(lastPayload);
        setTimeout(poll, 400);
      });
  }

  paint(lastPayload);
  poll();
})();
