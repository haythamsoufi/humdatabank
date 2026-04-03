// action-router.js
// Delegated event router for CSP-safe, scalable UI interactions.
// Usage:
//   <button data-action="notifications:retry">...</button>
//   ActionRouter.register('notifications:retry', (el, event) => { ... })
// Exposes: window.ActionRouter

(function () {
  'use strict';

  const handlers = new Map();

  function register(action, handler) {
    if (!action || typeof action !== 'string') {
      throw new Error('ActionRouter.register: action must be a string');
    }
    if (typeof handler !== 'function') {
      throw new Error('ActionRouter.register: handler must be a function');
    }
    handlers.set(action, handler);
  }

  function unregister(action) {
    handlers.delete(action);
  }

  function getActionElement(target) {
    if (!target || typeof target.closest !== 'function') return null;
    return target.closest('[data-action]');
  }

  function dispatch(event) {
    const el = getActionElement(event.target);
    if (!el) return;

    const action = el.getAttribute('data-action');
    if (!action) return;

    const handler = handlers.get(action);
    if (!handler) return;

    handler(el, event);
  }

  // Global delegated listeners (capture false; you can stopPropagation in handlers)
  document.addEventListener('click', dispatch);
  document.addEventListener('keydown', (event) => {
    // Optional keyboard activation for elements using data-action
    if (event.key !== 'Enter' && event.key !== ' ') return;
    const el = getActionElement(event.target);
    if (!el) return;
    // Only for elements that should act like buttons
    const tag = (el.tagName || '').toLowerCase();
    if (tag === 'button' || tag === 'a' || el.getAttribute('role') === 'button') {
      dispatch(event);
    }
  });

  window.ActionRouter = {
    register,
    unregister,
  };
})();
