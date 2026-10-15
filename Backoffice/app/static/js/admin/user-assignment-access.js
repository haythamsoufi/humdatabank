(function () {
  'use strict';

  function init() {
    var section = document.getElementById('assignment-access-section');
    if (!section) return;

    var selectedMode = section.getAttribute('data-selected-mode') || 'selected';
    var picker = document.getElementById('assignment-access-picker');
    var filter = document.getElementById('assignment-access-filter');
    var radios = section.querySelectorAll('input[name="assignment_access_mode"]');
    if (!picker) return;

    function syncPicker() {
      var show = false;
      radios.forEach(function (r) {
        if (r.checked && r.value === selectedMode) show = true;
      });
      picker.classList.toggle('hidden', !show);
    }

    radios.forEach(function (r) {
      r.addEventListener('change', syncPicker);
    });

    if (filter) {
      filter.addEventListener('input', function () {
        var q = filter.value.trim().toLowerCase();
        picker.querySelectorAll('.assignment-access-option').forEach(function (el) {
          var hay = el.getAttribute('data-search') || '';
          el.classList.toggle('hidden', q !== '' && hay.indexOf(q) === -1);
        });
      });
    }

    syncPicker();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
