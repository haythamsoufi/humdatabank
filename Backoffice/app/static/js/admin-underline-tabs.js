/**
 * Shared underline tab strip (admin settings / org / account settings style).
 * Class tokens must match Jinja macros in components/_scroll_tab_bar.html (admin_underline_*).
 */
(function (global) {
  'use strict';

  var C = {
    active: ['border-blue-500', 'text-blue-600'],
    inactive: ['border-transparent', 'text-gray-500'],
    badgeActive: ['border-blue-200', 'bg-blue-50', 'text-blue-600'],
    badgeInactive: ['border-gray-200', 'bg-gray-100', 'text-gray-600']
  };

  function addAll(el, arr) {
    if (!el) return;
    arr.forEach(function (c) { el.classList.add(c); });
  }

  function removeAll(el, arr) {
    if (!el) return;
    arr.forEach(function (c) { el.classList.remove(c); });
  }

  /**
   * Tab button without count badge (settings, account settings, secretariat sub-tabs).
   */
  function setStripButtonActive(btn, active) {
    if (!btn) return;
    if (active) {
      removeAll(btn, C.inactive);
      addAll(btn, C.active);
    } else {
      removeAll(btn, C.active);
      addAll(btn, C.inactive);
    }
  }

  /** Sub-strips that keep a literal .active class (org secretariat, NS hierarchy). */
  function setSubTabButton(btn, active) {
    setStripButtonActive(btn, active);
    if (!btn) return;
    if (active) btn.classList.add('active');
    else btn.classList.remove('active');
  }

  /**
   * Organization main tabs: button + .org-main-tab-badge
   */
  function setOrgMainTabButton(btn, active, badgeSelector) {
    badgeSelector = badgeSelector || '.org-main-tab-badge';
    setStripButtonActive(btn, active);
    var badge = btn.querySelector(badgeSelector);
    if (!badge) return;
    if (active) {
      removeAll(badge, C.badgeInactive);
      addAll(badge, C.badgeActive);
    } else {
      removeAll(badge, C.badgeActive);
      addAll(badge, C.badgeInactive);
    }
  }

  global.AdminUnderlineTabs = {
    CLASSES: C,
    setStripButtonActive: setStripButtonActive,
    setSubTabButton: setSubTabButton,
    setOrgMainTabButton: setOrgMainTabButton,
    /**
     * Sync aria-selected + strip classes for all .settings-tab under tablist; show matching panel-*.
     * opts.panelSelector default '.settings-panel'; opts.panelIdPrefix default 'panel-'.
     */
    activateStripTab: function (tablistSelector, tabId, opts) {
      opts = opts || {};
      var panelSel = opts.panelSelector || '.settings-panel';
      var prefix = opts.panelIdPrefix != null ? opts.panelIdPrefix : 'panel-';
      var tabs = document.querySelectorAll(tablistSelector + ' .settings-tab');
      var panels = document.querySelectorAll(panelSel);
      tabs.forEach(function (btn) {
        var isActive = btn.getAttribute('data-tab') === tabId;
        setStripButtonActive(btn, isActive);
        btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
      });
      panels.forEach(function (p) {
        p.classList.toggle('hidden', p.id !== prefix + tabId);
      });
    }
  };
})(typeof window !== 'undefined' ? window : this);
