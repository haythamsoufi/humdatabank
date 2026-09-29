(function () {
  'use strict';

  var root = document.getElementById('apiKeyPermissions');
  if (!root) return;

  var picker = document.getElementById('apiKeyPermissionPicker');
  var boxes = Array.prototype.slice.call(root.querySelectorAll('input[name="capabilities"]'));
  var scopePanel = document.getElementById('apiKeyScopePanel');
  var scopeFields = document.getElementById('apiKeyScopeFields');
  var restrict = document.getElementById('restrictData');
  var sensitiveWarning = document.getElementById('apiKeySensitiveWarning');
  var piiWarning = document.getElementById('apiKeyPiiWarning');
  var queryKey = document.getElementById('allowQueryApiKey');
  var keepLegacy = document.getElementById('keepLegacyFullAccess');

  function checked() {
    return boxes.filter(function (b) { return b.checked; });
  }

  function refresh() {
    var legacyKept = !!(keepLegacy && keepLegacy.checked);
    if (picker) {
      picker.classList.toggle('opacity-50', legacyKept);
      boxes.forEach(function (b) { b.disabled = legacyKept; });
      Array.prototype.forEach.call(root.querySelectorAll('[data-api-key-preset]'), function (btn) {
        btn.disabled = legacyKept;
      });
      if (restrict) restrict.disabled = legacyKept;
      if (scopeFields) {
        Array.prototype.forEach.call(scopeFields.querySelectorAll('select'), function (s) {
          s.disabled = legacyKept;
        });
      }
    }

    var on = checked();
    var hasSensitive = legacyKept || on.some(function (b) {
      return b.dataset.sensitivity === 'sensitive' || b.dataset.sensitivity === 'pii';
    });
    var hasPii = legacyKept || on.some(function (b) { return b.dataset.sensitivity === 'pii'; });
    var hasScopable = on.some(function (b) { return b.dataset.scopable === 'true'; });

    if (sensitiveWarning) sensitiveWarning.classList.toggle('hidden', !hasSensitive);
    if (piiWarning) piiWarning.classList.toggle('hidden', !hasPii);

    if (queryKey) {
      queryKey.disabled = hasPii;
      if (hasPii) queryKey.checked = false;
    }

    if (!hasScopable && !legacyKept && restrict) restrict.checked = false;
    if (scopePanel) scopePanel.classList.toggle('hidden', !hasScopable && !legacyKept);
    if (scopeFields && restrict) scopeFields.classList.toggle('hidden', !restrict.checked);
  }

  root.addEventListener('change', refresh);

  Array.prototype.forEach.call(root.querySelectorAll('[data-api-key-preset]'), function (btn) {
    btn.addEventListener('click', function () {
      var wanted = (btn.getAttribute('data-api-key-preset') || '').split(',').filter(Boolean);
      boxes.forEach(function (b) { b.checked = wanted.indexOf(b.value) !== -1; });
      refresh();
    });
  });

  refresh();
})();
