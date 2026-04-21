/**
 * Collapsible sections/sub-sections with persisted state
 *
 * Required HTML structure:
 * <div data-collapsible-id="unique-id" [data-aes-id="optional-id"] class="p-6">
 *   <h3 class="border-b"> or <h4 class="border-b">
 *     <button class="collapse-toggle" aria-expanded="true">
 *       <i class="fa fa-chevron-up"></i>
 *       Title
 *     </button>
 *   </h3>
 *   <div data-collapsible-content>
 *     <!-- Collapsible content here -->
 *   </div>
 * </div>
 */

function getStorageKey(aesId, collapsibleId) {
  return `form-collapsible:${aesId || '0'}:${collapsibleId}`;
}

function readPersistedState(aesId, collapsibleId) {
  try {
    let raw = localStorage.getItem(getStorageKey(aesId, collapsibleId));
    if (raw === null) {
      raw = localStorage.getItem(`form-collapsible:${aesId || '0'}:${collapsibleId}`);
    }
    if (raw === '0') return false; // collapsed
    if (raw === '1') return true; // expanded
    return true; // default expanded
  } catch (e) {
    return true;
  }
}

function persistState(aesId, collapsibleId, expanded) {
  try {
    localStorage.setItem(getStorageKey(aesId, collapsibleId), expanded ? '1' : '0');
  } catch (e) {
    console.warn('Failed to persist collapsible state:', e);
  }
}

function setIconExpanded(button, expanded) {
  if (!button) return;
  const icon = button.querySelector('i');
  if (!icon) return;
  icon.classList.remove('fa-chevron-up', 'fa-chevron-down');
  icon.classList.add(expanded ? 'fa-chevron-up' : 'fa-chevron-down');
}

function animateHeight(element, expanded) {
  if (!element) return;
  element.style.overflow = 'hidden';
  const startHeight = expanded ? 0 : element.scrollHeight;
  const endHeight = expanded ? element.scrollHeight : 0;

  element.style.height = `${startHeight}px`;
  // Force reflow
  // eslint-disable-next-line no-unused-expressions
  element.offsetHeight;
  element.style.transition = 'height 200ms ease';
  element.style.height = `${endHeight}px`;

  const cleanup = () => {
    element.style.transition = '';
    element.style.height = '';
    element.style.overflow = '';
    if (!expanded) {
      element.style.display = 'none';
    }
  };

  const onEnd = () => {
    clearTimeout(timeoutId);
    cleanup();
  };

  // Fallback timeout in case transitionend doesn't fire (e.g., interrupted animation)
  const timeoutId = setTimeout(cleanup, 300);

  element.addEventListener('transitionend', onEnd, { once: true });
}

function setExpanded(container, content, button, expanded) {
  if (!content) return;
  if (expanded) {
    content.style.display = '';
    // When expanding, initialize any child collapsibles that might not have been initialized yet
    // (e.g., sub-sections inside a collapsed parent)
    // Use requestAnimationFrame for better performance and timing
    requestAnimationFrame(() => {
      const childContainers = content.querySelectorAll('[data-collapsible-id]');
      childContainers.forEach(childContainer => {
        initCollapsible(childContainer);
      });
    });
  }

  // Always animate if possible (browsers support transition)
  animateHeight(content, expanded);

  if (button) {
    button.setAttribute('aria-expanded', String(expanded));
    setIconExpanded(button, expanded);
    // Toggle border-b class on the h3 or h4 header when collapsed/expanded
    const header = button.closest('h3, h4');
    if (header) {
      if (expanded) {
        header.classList.add('border-b');
      } else {
        header.classList.remove('border-b');
      }
    }
    // Reduce container padding-bottom when collapsed to remove blank space (only for main sections with p-6)
    if (container.classList.contains('p-6')) {
      if (expanded) {
        container.style.paddingBottom = '';
      } else {
        container.style.paddingBottom = '0.5rem'; // pb-2 equivalent
      }
    }
  }
}

function initCollapsible(container) {
  const collapsibleId = container.getAttribute('data-collapsible-id');
    const aesId = container.getAttribute('data-aes-id') || container.closest('[data-aes-id]')?.getAttribute('data-aes-id') || '0';
  const content = container.querySelector('[data-collapsible-content]');
  const button = container.querySelector('.collapse-toggle');
  if (!collapsibleId || !content || !button) return;

  // Prevent duplicate initialization
  if (button.hasAttribute('data-collapsible-initialized')) {
    return;
  }
  // Mark initialized immediately to prevent duplicate event handlers when:
  // - parent sections expand and re-init children
  // - MutationObserver re-inits when content becomes visible
  button.setAttribute('data-collapsible-initialized', 'true');

  // Initial state
  const initialExpanded = readPersistedState(aesId, collapsibleId);
  if (!initialExpanded) {
    content.style.display = 'none';
    button.setAttribute('aria-expanded', 'false');
    setIconExpanded(button, false);
    // Hide border-b on h3 or h4 when initially collapsed
    const header = button.closest('h3, h4');
    if (header) {
      header.classList.remove('border-b');
    }
    // Reduce container padding-bottom when initially collapsed (only for main sections with p-6)
    if (container.classList.contains('p-6')) {
      container.style.paddingBottom = '0.5rem'; // pb-2 equivalent
    }
  } else {
    button.setAttribute('aria-expanded', 'true');
    setIconExpanded(button, true);
    // Ensure border-b is present on h3 or h4 when initially expanded
    const header = button.closest('h3, h4');
    if (header) {
      header.classList.add('border-b');
    }
    // Ensure normal padding when initially expanded (only for main sections with p-6)
    if (container.classList.contains('p-6')) {
      container.style.paddingBottom = '';
    }
  }

  // Prevent rapid toggling with debounce
  let toggleTimeout = null;
  const toggle = () => {
    if (toggleTimeout) return; // ignore if animation in progress
    toggleTimeout = setTimeout(() => toggleTimeout = null, 250);

    const isExpanded = button.getAttribute('aria-expanded') === 'true';
    const next = !isExpanded;
    setExpanded(container, content, button, next);
    persistState(aesId, collapsibleId, next);
  };

  button.addEventListener('click', toggle);
  button.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      toggle();
    }
  });
}

// Make initCollapsible globally available for re-initialization of dynamically added sections
window.initCollapsible = initCollapsible;

// Function to initialize all collapsibles (can be called multiple times safely)
function initializeAllCollapsibles() {
  try {
    const containers = document.querySelectorAll('[data-collapsible-id]');
    containers.forEach(container => {
      initCollapsible(container);
    });
  } catch (e) {
    console.error('Error initializing collapsibles:', e);
  }
}

// Initialize collapsible when DOM is ready (handle both loading and already-loaded states)
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    initializeAllCollapsibles();
  });
} else {
  // DOM is already loaded, initialize immediately
  initializeAllCollapsibles();
}

// Re-initialize collapsibles when content becomes visible (for sections inside collapsed parents)
// Use MutationObserver to watch for display changes
if (typeof MutationObserver !== 'undefined') {
  const observer = new MutationObserver((mutations) => {
    mutations.forEach((mutation) => {
      if (mutation.type === 'attributes' && mutation.attributeName === 'style') {
        const target = mutation.target;
        // If a collapsible content becomes visible, ensure its child collapsibles are initialized
        if (target.hasAttribute('data-collapsible-content') &&
            target.style.display !== 'none' &&
            !target.hasAttribute('data-collapsible-children-initialized')) {
          const childContainers = target.querySelectorAll('[data-collapsible-id]');
          childContainers.forEach(container => {
            initCollapsible(container);
          });
          target.setAttribute('data-collapsible-children-initialized', 'true');
        }
      }
    });
  });

  // Observe all collapsible content elements
  document.addEventListener('DOMContentLoaded', () => {
    const collapsibleContents = document.querySelectorAll('[data-collapsible-content]');
    collapsibleContents.forEach(content => {
      observer.observe(content, { attributes: true, attributeFilter: ['style'] });
    });
  });
}

// Listen for repeat entry additions to reinitialize collapsibles
document.addEventListener('repeatEntryAdded', function(event) {
  const container = event.detail.container;
  if (container) {
    // Initialize all collapsibles within the newly added repeat entry
    const collapsibles = container.querySelectorAll('[data-collapsible-id]');
    collapsibles.forEach(collapsible => {
      initCollapsible(collapsible);
    });
  }
});
