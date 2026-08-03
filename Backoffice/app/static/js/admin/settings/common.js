/** Shared helpers for System Configuration tab modules. */

export function escCssSelector(value) {
  if (window.escapeCssSelector) return window.escapeCssSelector(value);
  return String(value == null ? '' : value).replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}

export function getSettingsPageConfig() {
  return window.settingsPageConfig || {};
}
