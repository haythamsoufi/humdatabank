(function () {
  'use strict';

  function init() {
    var section = document.getElementById('assignment-access-section');
    if (!section) return;

    var selectedMode = section.getAttribute('data-selected-mode') || 'selected';
    var templatesMode = section.getAttribute('data-templates-mode') || 'templates';
    var assignmentPicker = document.getElementById('assignment-access-picker');
    var templatePicker = document.getElementById('assignment-template-picker');
    var assignmentFilter = document.getElementById('assignment-access-filter');
    var templateFilter = document.getElementById('assignment-template-filter');
    var radios = section.querySelectorAll('input[name="assignment_access_mode"]');

    function checkedMode() {
      var mode = 'all';
      radios.forEach(function (r) {
        if (r.checked) mode = r.value;
      });
      return mode;
    }

    function syncPickers() {
      var mode = checkedMode();
      if (assignmentPicker) {
        assignmentPicker.classList.toggle('hidden', mode !== selectedMode);
      }
      if (templatePicker) {
        templatePicker.classList.toggle('hidden', mode !== templatesMode);
      }
    }

    function bindFilter(input, root, rowSelector) {
      if (!input || !root) return;
      input.addEventListener('input', function () {
        var q = input.value.trim().toLowerCase();
        root.querySelectorAll(rowSelector).forEach(function (el) {
          var hay = el.getAttribute('data-search') || '';
          el.classList.toggle('hidden', q !== '' && hay.indexOf(q) === -1);
        });
      });
    }

    radios.forEach(function (r) {
      r.addEventListener('change', syncPickers);
    });
    bindFilter(assignmentFilter, assignmentPicker, '.assignment-access-option');
    bindFilter(templateFilter, templatePicker, '.assignment-template-option');
    syncPickers();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
