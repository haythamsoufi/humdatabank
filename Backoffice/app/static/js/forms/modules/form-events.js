// Centralizes form-level custom events
import { triggerSave, saveFormBeforeSubmit } from './ajax-save.js';
import { debugLog } from './debug.js';

const MODULE_NAME = 'form-events';

export function initFormEvents() {
  const form = document.getElementById('focalDataEntryForm');
  if (!form) return;

  function showSubmittingMessage() {
    if (typeof window.showFlashMessage === 'function') {
      window.showFlashMessage('Submitting form…', 'info');
    }
  }

  function showSavingBeforeSubmitMessage() {
    if (typeof window.showFlashMessage === 'function') {
      window.showFlashMessage('Saving your latest changes…', 'info');
    }
  }

  function showSavedBeforeSubmitMessage() {
    if (typeof window.showFlashMessage === 'function') {
      window.showFlashMessage('Changes saved.', 'info');
    }
  }

  // Helper to set/replace hidden action input
  function setHiddenAction(actionValue) {
    const existingActions = form.querySelectorAll('input[name="action"][type="hidden"]');
    existingActions.forEach(input => input.remove());
    const actionInput = document.createElement('input');
    actionInput.type = 'hidden';
    actionInput.name = 'action';
    actionInput.value = actionValue;
    form.appendChild(actionInput);
    return actionValue;
  }

  // Add CSRF token refresh functionality for public forms (uses page fetch; admin API not available)
  if (form.closest('[data-is-public-submission]') && typeof window.refreshCsrfFromCurrentPage === 'function') {
    window.refreshCsrfFromCurrentPage();
  }

  // Save-before-submit (draft save) to prevent data loss:
  // - Save via AJAX (action=save) WITHOUT showing "Progress saved successfully!"
  // - Then re-trigger a real submit (action=submit) so validation + backend submission runs
  //
  // This ensures: if Submit is blocked (frontend or backend), the user's latest changes are still saved.
  form.addEventListener('submit', async function (event) {
    // Only handle the submit action (not save)
    const submitter = event.submitter;
    const submitBtn =
      (submitter && submitter.name === 'action' && submitter.value === 'submit') ? submitter :
      form.querySelector('button[type="submit"][name="action"][value="submit"]');
    const actionValue =
      (submitter && submitter.name === 'action') ? submitter.value :
      (form.querySelector('input[name="action"][type="hidden"]')?.value || null);

    if (actionValue !== 'submit') return;

    // If this submit was triggered programmatically by our own flow (presave -> requestSubmit,
    // or CSRF refresh -> requestSubmit), do NOT presave again (prevents loops / duplicate saves).
    if (form.dataset.ifrcInternalSubmit === '1') {
      delete form.dataset.ifrcInternalSubmit;
      debugLog(MODULE_NAME, '🧩 presave intercept: skipping internal submit');
      return;
    }

    // Only presave on *user-intended* submits.
    //
    // - User clicking the real submit button produces a trusted submit event.
    // - Programmatic requestSubmit() (used by our presave chain and CSRF refresh) is not trusted.
    // - For confirmation dialogs, we explicitly mark the next submit as user-intended.
    const forcePresave = form.dataset.ifrcForcePresave === '1';
    if (forcePresave) delete form.dataset.ifrcForcePresave;
    if (!event.isTrusted && !forcePresave) return;

    debugLog(MODULE_NAME, '🧩 presave intercept: submit detected', {
      isTrusted: event.isTrusted,
      forcePresave,
      hasSubmitter: !!submitter,
      submitterName: submitter?.name,
      submitterValue: submitter?.value,
      hasSubmitBtn: !!submitBtn,
      skipPresaveInProgress: form.dataset.ifrcPresaveInProgress === '1',
    });

    // Avoid duplicate presave cycles
    if (form.dataset.ifrcPresaveInProgress === '1') {
      event.preventDefault();
      event.stopPropagation();
      return;
    }

    form.dataset.ifrcPresaveInProgress = '1';

    // We will run a presave; stop the native submit for now.
    event.preventDefault();
    // Stop other submit handlers (validation, CSRF refresh, etc.) for this first attempt.
    // We'll run a real submit after the presave completes.
    try { event.stopImmediatePropagation(); } catch (_) { event.stopPropagation(); }

    // Reset FormSubmitGuard state for this prevented submit, otherwise the follow-up
    // requestSubmit can be blocked as a "duplicate" and/or the submit button can stay stuck.
    try {
      if (window.FormSubmitGuard) {
        if (typeof window.FormSubmitGuard.reset === 'function') {
          window.FormSubmitGuard.reset(form);
        } else if (submitBtn && typeof window.FormSubmitGuard.resetButton === 'function') {
          window.FormSubmitGuard.resetButton(submitBtn);
        }
      }
    } catch (_) { /* no-op */ }

    debugLog(MODULE_NAME, '🧩 presave intercept: prevented submit and reset submit-guard');

    // Collect hidden fields for server clearing before saving
    try {
      if (window.collectHiddenFieldsForSubmission) {
        window.collectHiddenFieldsForSubmission();
      }
    } catch (_) { /* no-op */ }

    showSavingBeforeSubmitMessage();

    try {
      debugLog(MODULE_NAME, '🧩 presave: starting ajax save-before-submit');
      // Save draft silently (no "Progress saved successfully!" toast)
      await saveFormBeforeSubmit({ toast: false });
      debugLog(MODULE_NAME, '🧩 presave: ajax save-before-submit complete');
      showSavedBeforeSubmitMessage();

      // Now allow the real submit to proceed
      setHiddenAction('submit');

      // Make the submit button text clearer on the final submit.
      try {
        if (submitBtn && submitBtn.dataset) {
          submitBtn.dataset.loadingText = 'Submitting...';
        }
      } catch (_) { /* no-op */ }

      // Ensure no stale submit-guard state remains before the final submit.
      try {
        if (window.FormSubmitGuard && typeof window.FormSubmitGuard.reset === 'function') {
          window.FormSubmitGuard.reset(form);
        }
        if (submitBtn) {
          submitBtn.disabled = false;
          delete submitBtn.dataset.submitGuardActive;
        }
      } catch (_) { /* no-op */ }

      debugLog(MODULE_NAME, '🧩 presave: triggering final submit', {
        usingRequestSubmit: !!form.requestSubmit,
        hasSubmitBtn: !!submitBtn,
      });

      if (form.requestSubmit) {
        // Mark the upcoming submit event as internal so we don't run presave again.
        form.dataset.ifrcInternalSubmit = '1';
        if (submitBtn) form.requestSubmit(submitBtn);
        else form.requestSubmit();
      } else {
        // Fallback: submit without submitter
        form.submit();
      }

      // Watchdog: if submission is prevented but guard wasn't reset, unstick.
      // (Only runs if we remain on this page.)
      setTimeout(() => {
        try {
          const stuck = form.querySelector('[data-submit-guard-active="1"]');
          if (stuck && window.FormSubmitGuard && typeof window.FormSubmitGuard.reset === 'function') {
            debugLog(MODULE_NAME, '🧩 watchdog: submit button still guarded, resetting', { id: stuck.id, name: stuck.name });
            window.FormSubmitGuard.reset(form);
          }
        } catch (_) { /* no-op */ }
      }, 1500);
    } catch (e) {
      debugLog(MODULE_NAME, '🧩 presave: failed', e);
      // Leave the user on the page; explicit Save still works.
      if (typeof window.showFlashMessage === 'function') {
        const msg = (e && e.message) ? String(e.message) : 'Unknown error';
        window.showFlashMessage('Could not save changes before submitting: ' + msg, 'danger');
      }
    } finally {
      delete form.dataset.ifrcPresaveInProgress;
    }
  }, true); // capture: run before other submit handlers/validation

  // Handle submit button confirmation dialogs
  // Use custom styled dialog instead of native alert
  const confirmSubmitButtons = form.querySelectorAll('button[type="submit"][data-confirm-message]');
  confirmSubmitButtons.forEach(button => {
    // Guard against double-initialization (which can cause stacked modals and double submits)
    if (button.dataset.confirmHandlerBound === 'true') return;
    button.dataset.confirmHandlerBound = 'true';

    button.addEventListener('click', function(event) {
      const confirmMessage = this.getAttribute('data-confirm-message');
      if (confirmMessage) {
        // If a confirmation is already open for this button, ignore repeat clicks
        if (button.dataset.confirmInProgress === 'true') {
          event.preventDefault();
          event.stopPropagation();
          return false;
        }

        // Prevent default form submission until user confirms
        event.preventDefault();
        event.stopPropagation();

        button.dataset.confirmInProgress = 'true';

        // Use custom confirmation dialog with green submit button
        if (window.showSubmitConfirmation) {
          window.showSubmitConfirmation(
            confirmMessage,
            async () => {
              try {
                const form = document.getElementById('focalDataEntryForm');
                if (form) {
                  // The submit we'll trigger from this callback is programmatic; mark it as user-intended
                  // so the presave handler runs once.
                  form.dataset.ifrcForcePresave = '1';
                  // Set the action value and submit
                  const actionInput = form.querySelector('input[name="action"][type="hidden"]');
                  if (actionInput) {
                    actionInput.value = 'submit';
                  } else {
                    const newActionInput = document.createElement('input');
                    newActionInput.type = 'hidden';
                    newActionInput.name = 'action';
                    newActionInput.value = 'submit';
                    form.appendChild(newActionInput);
                  }
                  // Submit the form
                  if (form.requestSubmit) {
                    form.requestSubmit(button);
                  } else {
                    form.submit();
                  }
                }
              } catch (error) {
                const form = document.getElementById('focalDataEntryForm');
                if (form) {
                  const actionInput = form.querySelector('input[name="action"][type="hidden"]');
                  if (actionInput) {
                    actionInput.value = 'submit';
                  } else {
                    const newActionInput = document.createElement('input');
                    newActionInput.type = 'hidden';
                    newActionInput.name = 'action';
                    newActionInput.value = 'submit';
                    form.appendChild(newActionInput);
                  }
                  if (form.requestSubmit) {
                    form.requestSubmit(button);
                  } else {
                    form.submit();
                  }
                }
              }
              button.dataset.confirmInProgress = 'false';
            },
            () => {
              // User cancelled - do nothing
              console.log('Submit cancelled by user');
              button.dataset.confirmInProgress = 'false';
            }
          );
        } else if (window.showConfirmation) {
          // Avoid native confirm; use the generic custom confirmation dialog if submit-specific is unavailable
          window.showConfirmation(
            confirmMessage,
            async () => {
              // User confirmed - proceed with submission (server saves in the submit request)
              const form = document.getElementById('focalDataEntryForm');
              if (form) {
                // The submit we'll trigger from this callback is programmatic; mark it as user-intended
                // so the presave handler runs once.
                form.dataset.ifrcForcePresave = '1';
                const actionInput = form.querySelector('input[name="action"][type="hidden"]');
                if (actionInput) {
                  actionInput.value = 'submit';
                } else {
                  const newActionInput = document.createElement('input');
                  newActionInput.type = 'hidden';
                  newActionInput.name = 'action';
                  newActionInput.value = 'submit';
                  form.appendChild(newActionInput);
                }
                if (form.requestSubmit) {
                  form.requestSubmit(button);
                } else {
                  form.submit();
                }
              }
              button.dataset.confirmInProgress = 'false';
            },
            () => {
              button.dataset.confirmInProgress = 'false';
            },
            'Submit',
            'Cancel',
            'Submit Form?'
          );
        } else {
          console.warn('Custom confirmation dialog not available:', confirmMessage);
          button.dataset.confirmInProgress = 'false';
        }
        return false;
      }
    }, false);
  });

  form.addEventListener('submit', function (event) {
    console.log('Form submit event fired');
    const submitButton = event.submitter;
    console.log('Submitter:', submitButton);

    // If another module (e.g., client-side validation) already blocked submission,
    // do not run submit-side effects (like CSRF refresh + re-submit) as that can
    // cause duplicate submit cycles and duplicate flash/error UI.
    if (event.defaultPrevented) {
      // If another module prevented submission (e.g., form-validation), ensure submit guard resets.
      try {
        if (window.FormSubmitGuard && typeof window.FormSubmitGuard.reset === 'function') {
          window.FormSubmitGuard.reset(form);
        }
      } catch (_) { /* no-op */ }
      debugLog(MODULE_NAME, '🧩 submit bubble: defaultPrevented, reset guard and returning');
      console.log('Submit already prevented; skipping form-events submit handler');
      return;
    }

    // Ensure action is always set in form data based on submitter
    // This handles cases where submitter exists and where form.submit() is called directly
    let actionValue = null;

    if (submitButton && submitButton.name === 'action') {
      actionValue = submitButton.value;
      console.log('Action from submitter:', actionValue);
    } else {
      // If no submitter (form.submit() was called directly), check for existing action input
      const existingActionInput = form.querySelector('input[name="action"][type="hidden"]');
      if (existingActionInput) {
        actionValue = existingActionInput.value;
        console.log('Action from existing input:', actionValue);
      }
    }

    // Default action fallback when none found:
    // - Prefer 'save' if a save submit button exists (non-public forms)
    // - Otherwise default to 'submit'
    if (!actionValue) {
      const hasSaveButton = !!form.querySelector('button[type="submit"][name="action"][value="save"]');
      actionValue = hasSaveButton ? 'save' : 'submit';
      console.log('No action found; defaulting to:', actionValue);
    }

    // Always ensure action is set as a hidden input
    setHiddenAction(actionValue);

    if (actionValue === 'submit') {
      // Refresh CSRF token before submission for public forms
      if (form.closest('[data-is-public-submission]') && form.dataset.csrfRefreshed !== 'true') {
        event.preventDefault();
        const originalSubmitter = submitButton;
        debugLog(MODULE_NAME, '🧩 submit bubble: public form CSRF refresh intercept', { hasSubmitter: !!originalSubmitter });
        (typeof window.refreshCsrfFromCurrentPage === 'function' ? window.refreshCsrfFromCurrentPage() : Promise.resolve(null))
          .then(() => {
            // Mark as refreshed to avoid recursive interception
            form.dataset.csrfRefreshed = 'true';
            setHiddenAction('submit');
            debugLog(MODULE_NAME, '🧩 submit bubble: CSRF refreshed, resubmitting');
            // Use requestSubmit to preserve submitter and trigger validation
            if (form.requestSubmit) {
              // Mark as internal submit so presave won't run again
              form.dataset.ifrcInternalSubmit = '1';
              if (originalSubmitter) {
                form.requestSubmit(originalSubmitter);
              } else {
                form.requestSubmit();
              }
            } else {
              // Fallback: submit normally - action is already set as hidden input
              form.submit();
            }
          })
          .catch(() => {
            // If refresh fails, still proceed with a single submission
            form.dataset.csrfRefreshed = 'true';
            setHiddenAction('submit');
            debugLog(MODULE_NAME, '🧩 submit bubble: CSRF refresh failed, resubmitting anyway');
            if (form.requestSubmit) {
              form.dataset.ifrcInternalSubmit = '1';
              if (originalSubmitter) {
                form.requestSubmit(originalSubmitter);
              } else {
                form.requestSubmit();
              }
            } else {
              form.submit();
            }
          });
        return;
      }

      // Non-public (or already refreshed) submissions: show once here.
      showSubmittingMessage();
      debugLog(MODULE_NAME, '🧩 submit bubble: submitting (non-public or already refreshed)');

      setTimeout(() => {
        document.dispatchEvent(new CustomEvent('formSubmitted', {
          detail: { action: 'submit' }
        }));
      }, 100);
    }
  });

  // Wire FAB buttons (mobile) to submit the form consistently
  // These handlers replace the ones in sidebar-collapse.js to avoid duplication
  const fabSaveBtn = document.getElementById('fab-save-btn');
  if (fabSaveBtn) {
    fabSaveBtn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();

      // Use the same AJAX save function as the main save button
      // First try to trigger click on the original save button (which has the AJAX handler)
      const saveSubmitter = form.querySelector('button[type="submit"][name="action"][value="save"]');
      if (saveSubmitter) {
        // Simulate a click on the original save button to trigger its AJAX save handler
        // This ensures the FAB button uses the exact same function as the main save button
        saveSubmitter.click();
      } else if (typeof triggerSave === 'function') {
        // Fallback: use the exported triggerSave function directly
        triggerSave();
      } else {
        // Last resort: submit form with save action
        setHiddenAction('save');
        if (form.requestSubmit) {
          form.requestSubmit();
        } else {
          form.submit();
        }
      }
    });
  }

  const fabSubmitBtn = document.getElementById('fab-submit-btn');
  if (fabSubmitBtn) {
    fabSubmitBtn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();

      // Get confirmation message from FAB menu container or original submit button
      const fabMenu = document.getElementById('fab-menu');
      const submitSubmitter = form.querySelector('button[type="submit"][name="action"][value="submit"]');
      const confirmMessage = fabMenu?.dataset?.submitConfirm ||
                            submitSubmitter?.dataset?.confirmMessage ||
                            null;

      if (confirmMessage) {
        // Use custom confirmation dialog with green submit button
        if (window.showSubmitConfirmation) {
          window.showSubmitConfirmation(
            confirmMessage,
            () => {
              // User confirmed - proceed with submission
              if (submitSubmitter) {
                // Prefer requestSubmit to trigger normal submit/validation flow without re-opening confirm
                setHiddenAction('submit');
                if (form.requestSubmit) {
                  form.requestSubmit(submitSubmitter);
                } else {
                  // Fallback: temporarily remove confirm attribute to avoid re-prompting
                  const prevConfirm = submitSubmitter.getAttribute('data-confirm-message');
                  submitSubmitter.removeAttribute('data-confirm-message');
                  submitSubmitter.click();
                  if (prevConfirm !== null) submitSubmitter.setAttribute('data-confirm-message', prevConfirm);
                }
              } else {
                // Fallback: submit form with submit action
                setHiddenAction('submit');
                if (form.requestSubmit) {
                  form.requestSubmit();
                } else {
                  form.submit();
                }
              }
            },
            () => {
              // User cancelled - do nothing
              console.log('Submit cancelled by user');
            }
          );
          return; // Exit early, submission will happen in callback if confirmed
        } else if (window.showConfirmation) {
          // Avoid native confirm; use generic custom confirmation dialog if submit-specific is unavailable
          window.showConfirmation(
            confirmMessage,
            () => {
              // User confirmed - proceed with submission
              if (submitSubmitter) {
                setHiddenAction('submit');
                if (form.requestSubmit) {
                  form.requestSubmit(submitSubmitter);
                } else {
                  const prevConfirm = submitSubmitter.getAttribute('data-confirm-message');
                  submitSubmitter.removeAttribute('data-confirm-message');
                  submitSubmitter.click();
                  if (prevConfirm !== null) submitSubmitter.setAttribute('data-confirm-message', prevConfirm);
                }
              } else {
                setHiddenAction('submit');
                if (form.requestSubmit) {
                  form.requestSubmit();
                } else {
                  form.submit();
                }
              }
            },
            () => {
              console.log('Submit cancelled by user');
            },
            'Submit',
            'Cancel',
            'Submit Form?'
          );
          return; // Exit early; submission will happen in callback if confirmed
        } else {
          console.warn('Custom confirmation dialog not available:', confirmMessage);
          return;
        }
      }

      // If no confirmation needed or confirmed via native dialog, proceed with submission
      if (submitSubmitter) {
        setHiddenAction('submit');
        if (form.requestSubmit) {
          form.requestSubmit(submitSubmitter);
        } else {
          const prevConfirm = submitSubmitter.getAttribute('data-confirm-message');
          submitSubmitter.removeAttribute('data-confirm-message');
          submitSubmitter.click();
          if (prevConfirm !== null) submitSubmitter.setAttribute('data-confirm-message', prevConfirm);
        }
      } else {
        // Fallback: submit form with submit action
        setHiddenAction('submit');
        if (form.requestSubmit) {
          form.requestSubmit();
        } else {
          form.submit();
        }
      }
    });
  }

  // Wire chatbot FAB hover to show/hide the AI action popup above it
  const chatbotFAB = document.getElementById('aiChatbotFAB');
  const chatbotAiMenu = document.getElementById('chatbot-ai-hover-menu');
  if (chatbotFAB && chatbotAiMenu) {
    let hideTimer = null;
    const menuGapFromFab = 16;

    const alignMenuToFab = () => {
      const fabRect = chatbotFAB.getBoundingClientRect();
      const rightOffset = Math.max(0, window.innerWidth - fabRect.right);
      const bottomOffset = Math.max(0, window.innerHeight - fabRect.top + menuGapFromFab);

      chatbotAiMenu.style.right = `${rightOffset}px`;
      chatbotAiMenu.style.bottom = `${bottomOffset}px`;
    };

    const showMenu = () => {
      clearTimeout(hideTimer);
      alignMenuToFab();
      chatbotAiMenu.style.pointerEvents = 'auto';
      chatbotAiMenu.style.opacity = '1';
    };
    const scheduleHide = () => {
      hideTimer = setTimeout(() => {
        chatbotAiMenu.style.opacity = '0';
        chatbotAiMenu.style.pointerEvents = 'none';
      }, 200);
    };

    chatbotFAB.addEventListener('mouseenter', showMenu);
    chatbotFAB.addEventListener('mouseleave', scheduleHide);
    chatbotAiMenu.addEventListener('mouseenter', showMenu);
    chatbotAiMenu.addEventListener('mouseleave', scheduleHide);
    window.addEventListener('resize', alignMenuToFab);
    alignMenuToFab();
  }

  // Validation Summary button — directly initialised via initValidationSummaryExport (main.js)
  // Run AI opinions button — directly initialised via initAiOpinions (main.js / ai-opinions.js)
  // Both buttons are identified by their own IDs so no click delegation needed here.
}

// Note: Initialization is handled by main.js to avoid double initialization
// This module is imported and called explicitly in the main initialization sequence
