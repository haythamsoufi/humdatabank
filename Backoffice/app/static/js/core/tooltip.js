/**
 * Reusable Custom Tooltip System
 * Provides intelligent positioning and easy-to-use tooltip functionality
 */

/**
 * Initialize tooltip positioning for all tooltips on the page.
 * Skips elements already bound (data-tooltip-bound) so safe to call after dynamic content is added.
 */
export function initTooltips() {
    const tooltipContainers = document.querySelectorAll('.custom-info-tooltip');
    tooltipContainers.forEach(container => {
        if (container.getAttribute('data-tooltip-bound') === 'true') return;
        const tooltip = container.querySelector('.tooltip-text');
        if (!tooltip) return;
        container.setAttribute('data-tooltip-bound', 'true');
        container.addEventListener('mouseenter', () => positionTooltip(container));
        container.addEventListener('mouseleave', () => hideTooltip(container));
    });
}

/**
 * Position a tooltip intelligently based on available space
 * @param {HTMLElement} tooltipContainer - The container element with the tooltip
 */
export function positionTooltip(tooltipContainer) {
    // Cache span reference — after portaling, .tooltip-text is not under the container
    // (querySelector would miss), and fixed positioning would break without this.
    let tooltip = tooltipContainer.__tooltipTextEl;
    if (!tooltip) {
        tooltip = tooltipContainer.querySelector('.tooltip-text');
        if (!tooltip) return;
        tooltipContainer.__tooltipTextEl = tooltip;
    }
    // Any ancestor with transform/filter (e.g. modal shell's `transform`) makes
    // position:fixed lay out relative to that ancestor, while getBoundingClientRect
    // returns viewport coordinates — so tooltips appear offset. Portaling to body fixes it.
    if (tooltip.parentNode !== document.body) {
        document.body.appendChild(tooltip);
    }

    const iconRect = tooltipContainer.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    // Reset position to calculate true dimensions
    tooltip.style.position = 'fixed';
    tooltip.style.left = '0';
    tooltip.style.top = '0';
    tooltip.style.transform = 'none';
    tooltip.style.visibility = 'hidden';
    tooltip.style.display = 'block';

    const tooltipRect = tooltip.getBoundingClientRect();
    const tooltipWidth = tooltipRect.width;
    const tooltipHeight = tooltipRect.height;

    // Calculate available space
    const spaceToRight = viewportWidth - iconRect.right;
    const spaceToLeft = iconRect.left;
    const spaceBelow = viewportHeight - iconRect.bottom;
    const spaceAbove = iconRect.top;

    // Default: show below (most common)
    let position = 'bottom';
    let left = iconRect.left + (iconRect.width / 2);
    let top = iconRect.bottom + 8;
    let transform = 'translateX(-50%)';

    // Check if we should position to the left
    if (spaceToRight < tooltipWidth && spaceToLeft >= tooltipWidth) {
        position = 'left';
        left = iconRect.left - 8;
        top = iconRect.top + (iconRect.height / 2);
        transform = 'translateY(-50%) translateX(-100%)';
    }
    // Check if we should position to the right
    else if (spaceToLeft < tooltipWidth && spaceToRight >= tooltipWidth) {
        position = 'right';
        left = iconRect.right + 8;
        top = iconRect.top + (iconRect.height / 2);
        transform = 'translateY(-50%)';
    }
    // Check if we should position above
    else if (spaceBelow < tooltipHeight && spaceAbove >= tooltipHeight) {
        position = 'top';
        left = iconRect.left + (iconRect.width / 2);
        top = iconRect.top - 8;
        transform = 'translateX(-50%) translateY(-100%)';
    }
    // If below, check if we need to adjust horizontally
    else if (spaceBelow >= tooltipHeight) {
        // Check if tooltip would overflow on the right
        if (left + (tooltipWidth / 2) > viewportWidth) {
            left = viewportWidth - (tooltipWidth / 2) - 16;
        }
        // Check if tooltip would overflow on the left
        if (left - (tooltipWidth / 2) < 0) {
            left = (tooltipWidth / 2) + 16;
        }
    }

    // Apply positioning
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
    tooltip.style.transform = transform;

    // Update arrow position class
    tooltip.className = 'tooltip-text tooltip-' + position;

    // Show tooltip
    tooltip.style.visibility = 'visible';
    tooltip.style.opacity = '1';
}

/**
 * Hide a tooltip
 * @param {HTMLElement} tooltipContainer - The container element with the tooltip
 */
export function hideTooltip(tooltipContainer) {
    const tooltip = tooltipContainer.__tooltipTextEl
        || tooltipContainer.querySelector('.tooltip-text');
    if (!tooltip) return;

    tooltip.style.visibility = 'hidden';
    tooltip.style.opacity = '0';
    tooltip.style.display = 'none';
    if (tooltip.parentNode === document.body) {
        tooltipContainer.appendChild(tooltip);
    }
}

/**
 * Create a tooltip element from a title attribute or data attribute
 * @param {HTMLElement} element - Element that should have a tooltip
 * @param {string} text - Tooltip text
 * @returns {HTMLElement} - The tooltip container element
 */
export function createTooltipElement(text) {
    const container = document.createElement('span');
    container.className = 'custom-info-tooltip cursor-help w-5 h-5 inline-flex items-center justify-center ml-1';

    const icon = document.createElement('i');
    icon.className = 'fas fa-info-circle text-gray-400';

    const tooltip = document.createElement('span');
    tooltip.className = 'tooltip-text';
    tooltip.textContent = text;

    container.appendChild(icon);
    container.appendChild(tooltip);

    // Initialize positioning for this tooltip
    container.addEventListener('mouseenter', () => positionTooltip(container));
    container.addEventListener('mouseleave', () => hideTooltip(container));

    return container;
}

/**
 * Initialize tooltips on page load
 */
if (typeof document !== 'undefined') {
    // Auto-initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initTooltips);
    } else {
        initTooltips();
    }

    // Expose for dynamic content (e.g. form builder matrix columns)
    window.positionTooltip = positionTooltip;
    window.hideTooltip = hideTooltip;
    window.initTooltips = initTooltips;
}
