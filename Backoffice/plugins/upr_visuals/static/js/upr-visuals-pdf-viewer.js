(function () {
  function prefersNativePdf() {
    var coarse =
      window.matchMedia && window.matchMedia("(hover: none) and (pointer: coarse)").matches;
    var iPad = navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1;
    return !!(coarse || iPad);
  }

  var url = document.body && document.body.getAttribute("data-pdf-url");
  if (url && prefersNativePdf()) {
    window.location.replace(url);
  }
})();
