/**
 * Utility functions for processing common words in indicator names
 */

/**
 * Process indicator name to highlight common words with tooltips
 * @param {string} indicatorName - The indicator name to process
 * @param {Array} commonWords - Array of common word objects
 * @param {string} language - Current language code
 * @returns {string} - HTML string with highlighted common words
 */
export function processIndicatorName(indicatorName, commonWords, language = 'en') {
  if (!indicatorName || !commonWords || commonWords.length === 0) {
    return indicatorName;
  }

  let processedName = indicatorName;

  // Sort common words by length (longest first) to avoid partial matches
  const sortedWords = [...commonWords].sort((a, b) => b.term.length - a.term.length);

  // Create a map for quick lookup
  const commonWordsMap = new Map();
  sortedWords.forEach(word => {
    commonWordsMap.set(word.term.toLowerCase(), word);
  });

  // Find and replace common words with highlighted versions
  sortedWords.forEach(word => {
    const regex = new RegExp(`\\b${escapeRegExp(word.term)}\\b`, 'gi');
    processedName = processedName.replace(regex, (match) => {
      const tooltipContent = word.meaning || word.term;
      return `<span class="common-word-highlight" data-tooltip="${escapeHtml(tooltipContent)}">${match}</span>`;
    });
  });

  return processedName;
}

/**
 * Escape special regex characters
 * @param {string} string - String to escape
 * @returns {string} - Escaped string
 */
function escapeRegExp(string) {
  return string.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Escape HTML special characters
 * @param {string} string - String to escape
 * @returns {string} - Escaped string
 */
function escapeHtml(string) {
  const div = document.createElement('div');
  div.textContent = string;
  return div.innerHTML;
}

/**
 * Initialize tooltips for common word highlights
 * @param {string} containerSelector - CSS selector for the container
 */
export function initializeTooltips(containerSelector = 'body') {
  const container = document.querySelector(containerSelector);
  if (!container) return;

  // Remove existing tooltip event listeners
  container.removeEventListener('mouseover', handleTooltipMouseOver);
  container.removeEventListener('mouseout', handleTooltipMouseOut);

  // Add new event listeners
  container.addEventListener('mouseover', handleTooltipMouseOver);
  container.addEventListener('mouseout', handleTooltipMouseOut);
}

/**
 * Handle mouse over for tooltips
 * @param {Event} event - Mouse over event
 */
function handleTooltipMouseOver(event) {
  const target = event.target;
  if (target.classList.contains('common-word-highlight')) {
    const tooltipContent = target.getAttribute('data-tooltip');
    if (tooltipContent) {
      showTooltip(target, tooltipContent, event);
    }
  }
}

/**
 * Handle mouse out for tooltips
 * @param {Event} event - Mouse out event
 */
function handleTooltipMouseOut(event) {
  const target = event.target;
  if (target.classList.contains('common-word-highlight')) {
    hideTooltip();
  }
}

/**
 * Show tooltip
 * @param {HTMLElement} element - Element to show tooltip for
 * @param {string} content - Tooltip content
 * @param {Event} event - Mouse event
 */
function showTooltip(element, content, event) {
  // Remove existing tooltip
  hideTooltip();

  // Create tooltip element
  const tooltip = document.createElement('div');
  tooltip.className = 'common-word-tooltip';
  tooltip.innerHTML = content;

  // Style the tooltip
  Object.assign(tooltip.style, {
    position: 'fixed',
    zIndex: '10000',
    backgroundColor: '#1f2937',
    color: 'white',
    padding: '8px 12px',
    borderRadius: '6px',
    fontSize: '14px',
    maxWidth: '300px',
    wordWrap: 'break-word',
    boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06)',
    pointerEvents: 'none',
    opacity: '0',
    transition: 'opacity 0.2s ease-in-out'
  });

  // Add arrow
  const arrow = document.createElement('div');
  arrow.className = 'tooltip-arrow';
  Object.assign(arrow.style, {
    position: 'absolute',
    width: '0',
    height: '0',
    borderLeft: '6px solid transparent',
    borderRight: '6px solid transparent',
    borderTop: '6px solid #1f2937'
  });

  tooltip.appendChild(arrow);
  document.body.appendChild(tooltip);

  // Position tooltip
  const rect = element.getBoundingClientRect();
  const tooltipRect = tooltip.getBoundingClientRect();

  let left = rect.left + (rect.width / 2) - (tooltipRect.width / 2);
  let top = rect.top - tooltipRect.height - 10;

  // Ensure tooltip stays within viewport
  if (left < 10) left = 10;
  if (left + tooltipRect.width > window.innerWidth - 10) {
    left = window.innerWidth - tooltipRect.width - 10;
  }
  if (top < 10) {
    top = rect.bottom + 10;
    arrow.style.borderTop = 'none';
    arrow.style.borderBottom = '6px solid #1f2937';
    arrow.style.top = '-6px';
  }

  tooltip.style.left = `${left}px`;
  tooltip.style.top = `${top}px`;

  // Show tooltip with animation
  setTimeout(() => {
    tooltip.style.opacity = '1';
  }, 10);

  // Store reference to current tooltip
  window.currentTooltip = tooltip;
}

/**
 * Hide tooltip
 */
function hideTooltip() {
  if (window.currentTooltip) {
    window.currentTooltip.remove();
    window.currentTooltip = null;
  }
}

/**
 * Add CSS styles for common word highlights and tooltips
 */
export function addCommonWordsStyles() {
  if (document.getElementById('common-words-styles')) {
    return; // Styles already added
  }

  const style = document.createElement('style');
  style.id = 'common-words-styles';
  style.textContent = `
    .common-word-highlight {
      text-decoration: underline;
      font-weight: bold;
      color: #dc2626;
      cursor: help;
      position: relative;
    }

    .common-word-highlight:hover {
      color: #b91c1c;
    }

    .common-word-tooltip {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
    }

    .tooltip-arrow {
      position: absolute;
      bottom: -6px;
      left: 50%;
      transform: translateX(-50%);
    }
  `;

  document.head.appendChild(style);
}
