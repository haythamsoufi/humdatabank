// Client-side filtering, sorting and thumbnail state for the public UPR documents gallery.
// Loaded by plugins/upr/templates/documents_gallery.html (a framed, anonymous page whose CSP
// allows scripts from this origin only).
(function () {
  var form = document.getElementById("gallery-filters");
  var grid = document.getElementById("gallery-grid");
  var empty = document.getElementById("gallery-empty");
  var count = document.getElementById("gallery-count");
  var clearLink = document.getElementById("gallery-clear");
  if (!form || !grid) return;
  var cards = Array.prototype.slice.call(grid.querySelectorAll("[data-doc]"));
  var total = cards.length;

  function field(name) {
    var el = form.elements[name];
    return el && el.value ? String(el.value).trim() : "";
  }

  function matches(card) {
    var q = field("q").toLowerCase();
    var country = field("country").toLowerCase();
    var typeId = field("type");
    var year = field("year");
    if (country && (card.getAttribute("data-country") || "") !== country) return false;
    if (typeId && (card.getAttribute("data-type") || "") !== typeId) return false;
    if (year && (card.getAttribute("data-year") || "") !== year) return false;
    if (q && (card.getAttribute("data-search") || "").indexOf(q) === -1) return false;
    return true;
  }

  function compare(a, b, mode) {
    var title = (a.getAttribute("data-title") || "").localeCompare(b.getAttribute("data-title") || "");
    if (mode === "country_az" || mode === "country_za") {
      var ca = a.getAttribute("data-country") || "";
      var cb = b.getAttribute("data-country") || "";
      if (!ca && !cb) return title;
      if (!ca) return 1;
      if (!cb) return -1;
      var byCountry = mode === "country_za" ? cb.localeCompare(ca) : ca.localeCompare(cb);
      return byCountry || title;
    }
    var da = a.getAttribute("data-published") || "";
    var db = b.getAttribute("data-published") || "";
    if (!da && !db) return title;
    if (!da) return 1;
    if (!db) return -1;
    if (da === db) return title;
    if (mode === "oldest") return da < db ? -1 : 1;
    return da > db ? -1 : 1;
  }

  function apply() {
    var mode = field("sort") || "newest";
    var visible = cards.filter(matches);
    visible.sort(function (a, b) { return compare(a, b, mode); });
    cards.forEach(function (card) { card.hidden = true; });
    visible.forEach(function (card) {
      card.hidden = false;
      grid.appendChild(card);
    });
    if (empty) empty.hidden = visible.length !== 0;
    if (count) {
      count.textContent = visible.length === total
        ? (total === 1 ? "1 document" : total + " documents")
        : (visible.length + " of " + total);
    }
    var params = new URLSearchParams();
    if (field("q")) params.set("q", field("q"));
    if (field("country")) params.set("country", field("country"));
    if (field("type")) params.set("type", field("type"));
    if (field("year")) params.set("year", field("year"));
    if (mode && mode !== "newest") params.set("sort", mode);
    var query = params.toString();
    history.replaceState(null, "", query ? (location.pathname + "?" + query) : location.pathname);
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    apply();
  });
  form.addEventListener("change", apply);
  if (form.elements.q) form.elements.q.addEventListener("input", apply);
  if (clearLink) {
    clearLink.addEventListener("click", function (event) {
      event.preventDefault();
      form.elements.q.value = "";
      form.elements.country.value = "";
      form.elements.type.value = "";
      form.elements.year.value = "";
      form.elements.sort.value = "newest";
      apply();
    });
  }
  if (!document.getElementById("gallery-error")) apply();

  Array.prototype.forEach.call(document.querySelectorAll(".thumb img"), function (img) {
    var thumb = img.closest(".thumb");
    function ready() {
      thumb.classList.add("is-ready");
      thumb.classList.remove("is-failed");
      thumb.removeAttribute("aria-busy");
    }
    function failed() {
      if (thumb.classList.contains("is-ready")) return;
      thumb.classList.add("is-failed");
      thumb.removeAttribute("aria-busy");
    }
    img.addEventListener("load", ready);
    img.addEventListener("error", failed);
    if (img.complete && img.naturalWidth > 0) ready();
    else if (img.complete && img.currentSrc) failed();
  });
})();
