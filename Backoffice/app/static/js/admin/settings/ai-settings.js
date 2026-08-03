/**
 * AI tab — password toggles, conditional fields, beta-user Select2, reset action.
 */
import { escCssSelector, getSettingsPageConfig } from './common.js';

function initAiBetaSelect2(cfg) {
  const $ = window.jQuery;
  if (!$ || !$.fn || !$.fn.select2) return false;
  const sel = document.getElementById('ai-beta-users-select');
  if (!sel) return false;
  if ($(sel).data('select2')) return true;
  try {
    $(sel).select2({
      width: '100%',
      placeholder: cfg.t.selectUsers,
      allowClear: true,
      closeOnSelect: false,
    });
    return true;
  } catch (_) {
    return false;
  }
}

export function initAiSettings(cfg = getSettingsPageConfig()) {
  document.querySelectorAll('.ai-toggle-pw').forEach((btn) => {
    btn.addEventListener('click', function onTogglePassword() {
      const input = this.closest('div').querySelector('input[type="password"], input[type="text"]');
      if (!input) return;
      const isPassword = input.type === 'password';
      input.type = isPassword ? 'text' : 'password';
      const icon = this.querySelector('i');
      if (icon) {
        icon.classList.toggle('fa-eye', !isPassword);
        icon.classList.toggle('fa-eye-slash', isPassword);
      }
    });
  });

  const willClearLabel = cfg.t.willBeClearedOnSave;
  const enterNewLabel = cfg.t.enterNewValue;
  document.querySelectorAll('input[type="checkbox"][name$="_clear"][name^="ai_"]').forEach((checkbox) => {
    const name = checkbox.getAttribute('name') || '';
    const passwordName = name.replace(/_clear$/, '');
    if (!passwordName) return;
    const passwordInput = document.querySelector('input[name="' + escCssSelector(passwordName) + '"]');
    if (!passwordInput) return;

    function reflectClearState() {
      if (checkbox.checked) {
        passwordInput.value = '';
        passwordInput.disabled = true;
        passwordInput.setAttribute('aria-disabled', 'true');
        passwordInput.placeholder = willClearLabel;
      } else {
        passwordInput.disabled = false;
        passwordInput.removeAttribute('aria-disabled');
        passwordInput.placeholder = enterNewLabel;
      }
    }

    checkbox.addEventListener('change', reflectClearState);
    passwordInput.addEventListener('input', () => {
      if (passwordInput.value && checkbox.checked) {
        checkbox.checked = false;
        reflectClearState();
      }
    });
    reflectClearState();
  });

  const toggleAllBtn = document.getElementById('ai-toggle-all');
  if (toggleAllBtn) {
    toggleAllBtn.addEventListener('click', () => {
      const groups = document.querySelectorAll('#panel-ai details.ai-group');
      const anyOpen = Array.from(groups).some((details) => details.open);
      groups.forEach((details) => {
        details.open = !anyOpen;
      });
      toggleAllBtn.textContent = anyOpen ? cfg.t.expandAll : cfg.t.collapseAll;
    });
  }

  const resetBtn = document.getElementById('ai-reset-all');
  if (resetBtn) {
    resetBtn.addEventListener('click', () => {
      const message = cfg.t.resetAiConfirm;
      const doReset = () => {
        const csrf = document.querySelector('input[name="csrf_token"]');
        ((window.getFetch && window.getFetch()) || fetch)(cfg.urls.apiAiReset, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrf ? csrf.value : '',
          },
        })
          .then((response) => response.json())
          .then((data) => {
            if (data.success) {
              window.location.reload();
            } else if (window.showAlert) {
              window.showAlert(data.message || cfg.t.resetFailed, 'error');
            } else {
              console.error(data.message || 'Reset failed');
            }
          })
          .catch(() => {
            if (window.showAlert) window.showAlert(cfg.t.networkError, 'error');
            else console.error('Network error');
          });
      };
      if (window.showConfirmation) {
        window.showConfirmation(message, doReset, null, cfg.t.resetBtn, cfg.t.cancel, cfg.t.resetAiTitle);
      } else if (window.confirm(message)) {
        doReset();
      }
    });
  }

  const panel = document.getElementById('panel-ai');
  if (panel) {
    const conditionals = panel.querySelectorAll('[data-ai-show-when]');
    if (conditionals.length) {
      function getFieldValue(key) {
        const input = panel.querySelector('[name="ai_' + key + '"]');
        if (!input) return undefined;
        if (input.type === 'checkbox') return input.checked;
        return input.value;
      }

      function evaluateVisibility() {
        conditionals.forEach((element) => {
          let rules;
          try {
            rules = JSON.parse(element.dataset.aiShowWhen);
          } catch (_) {
            return;
          }
          if (!Array.isArray(rules)) return;
          const visible = rules.every((rule) => {
            const value = getFieldValue(rule.field);
            if (value === undefined) return true;
            if ('not_eq' in rule) {
              if (typeof rule.not_eq === 'boolean') return value !== rule.not_eq;
              return String(value) !== String(rule.not_eq);
            }
            if (typeof rule.eq === 'boolean') return value === rule.eq;
            return String(value) === String(rule.eq);
          });
          element.style.display = visible ? '' : 'none';
        });
      }

      panel.addEventListener('change', evaluateVisibility);
      panel.addEventListener('input', evaluateVisibility);
      evaluateVisibility();
    }
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (initAiBetaSelect2(cfg)) return;
    let attempts = 0;
    const timer = setInterval(() => {
      if (initAiBetaSelect2(cfg) || ++attempts >= 40) clearInterval(timer);
    }, 100);
  });

  document.addEventListener('settings-tab-activated', (event) => {
    if (!event.detail || event.detail.tab !== 'ai') return;
    const $ = window.jQuery;
    if (!$ || !$.fn || !$.fn.select2) return;
    const sel = document.getElementById('ai-beta-users-select');
    if (!sel) return;
    if (!$(sel).data('select2')) {
      initAiBetaSelect2(cfg);
    } else {
      try {
        $(sel).select2('destroy');
      } catch (_) {}
      initAiBetaSelect2(cfg);
    }
  });
}
