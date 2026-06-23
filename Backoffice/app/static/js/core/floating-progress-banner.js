// floating-progress-banner.js
// Shared floating progress/status banner controller (non-module; attaches to window).
//
// Works with the shared Jinja macro `components/_floating_progress_banner.html` by wiring
// to passed element IDs. Designed to be used by both classic scripts and ES modules.

(function () {
  'use strict';

  function byId(id) {
    if (!id) return null;
    try { return document.getElementById(String(id)); } catch (_e) { return null; }
  }

  class FloatingProgressBanner {
    constructor(opts) {
      const o = opts || {};
      this.banner = o.bannerEl || byId(o.bannerId);
      this.title = o.titleEl || byId(o.titleId);
      this.detail = o.detailEl || byId(o.detailId);
      this.percent = o.percentEl || byId(o.percentId);
      this.bar = o.barEl || byId(o.barId);
      this.spinner = o.spinnerEl || byId(o.spinnerId);
      this.cancelWrap = o.cancelWrapEl || byId(o.cancelWrapId);
      this.cancelBtn = o.cancelBtnEl || byId(o.cancelBtnId);

      this._buttonEls = Object.create(null);
      const buttons = Array.isArray(o.buttons) ? o.buttons : [];
      buttons.forEach((b) => {
        if (!b || !b.id) return;
        const el = byId(b.id);
        if (el) this._buttonEls[String(b.id)] = el;
      });
    }

    exists() {
      return !!this.banner;
    }

    show() {
      if (!this.banner) return;
      this.banner.classList.remove('hidden');
    }

    hide() {
      if (!this.banner) return;
      this.banner.classList.add('hidden');
      this.setCancelVisible(false);
    }

    setTitle(text) {
      if (!this.title) return;
      this.title.textContent = (text === null || text === undefined) ? '' : String(text);
    }

    setDetail(text, { autoHideIfEmpty = true } = {}) {
      if (!this.detail) return;
      const s = (text === null || text === undefined) ? '' : String(text);
      this.detail.textContent = s;
      if (autoHideIfEmpty) {
        const has = !!s.trim();
        this.detail.classList.toggle('hidden', !has);
      }
    }

    setPercent(progress, { visible = true, text = null } = {}) {
      if (!this.percent) return;
      const pctText = (text !== null && text !== undefined)
        ? String(text)
        : `${Number.isFinite(Number(progress)) ? Math.round(Number(progress)) : 0}%`;
      this.percent.textContent = pctText;
      this.percent.classList.toggle('hidden', !visible);
    }

    setProgress(progress, { barColor = null } = {}) {
      if (!this.bar) return;
      const p = Number(progress);
      const clamped = Number.isFinite(p) ? Math.max(0, Math.min(100, Math.round(p))) : 0;
      this.bar.style.width = `${clamped}%`;
      if (barColor) {
        this.bar.style.background = String(barColor);
      }
    }

    setBar(width, { barColor = null } = {}) {
      if (!this.bar) return;
      this.bar.style.width = String(width);
      if (barColor) {
        this.bar.style.background = String(barColor);
      }
    }

    setSpinnerVisible(visible) {
      if (!this.spinner) return;
      this.spinner.classList.toggle('hidden', !visible);
    }

    setCancelVisible(visible) {
      if (!this.cancelWrap) return;
      this.cancelWrap.classList.toggle('hidden', !visible);
    }

    setButtonVisible(buttonId, visible) {
      const el = this._buttonEls[String(buttonId)];
      if (!el) return;
      el.classList.toggle('hidden', !visible);
    }

    // Convenience: show and update everything in one call.
    update({ title, detail, progress, showPercent = true, percentText = null, showSpinner = null, barColor = null } = {}) {
      this.show();
      if (title !== undefined) this.setTitle(title);
      if (detail !== undefined) this.setDetail(detail, { autoHideIfEmpty: false });
      if (progress !== undefined) this.setProgress(progress, { barColor });
      if (this.percent) {
        this.setPercent(progress, { visible: !!showPercent, text: percentText });
      }
      if (showSpinner !== null && showSpinner !== undefined) {
        this.setSpinnerVisible(!!showSpinner);
      }
    }
  }

  FloatingProgressBanner.fromIds = function fromIds(ids) {
    return new FloatingProgressBanner(ids || {});
  };

  // Export to window for both classic scripts and modules.
  try {
    window.FloatingProgressBanner = FloatingProgressBanner;
  } catch (_e) {}
})();

