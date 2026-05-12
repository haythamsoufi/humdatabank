// Provides a global positionTooltip function used by templates

export function initTooltips() {
  window.positionTooltip = function positionTooltip(tooltipContainer) {
    const tooltip = tooltipContainer.querySelector('.tooltip-text');
    if (!tooltip) return;
    // Use fixed positioning so tooltips are not clipped by overflow-hidden parents
    tooltip.style.position = 'fixed';
    const iconRect = tooltipContainer.getBoundingClientRect();
    const viewportWidth = window.innerWidth;

    // Reset position to calculate true dimensions
    tooltip.style.left = '0';
    tooltip.style.transform = 'none';

    const spaceToRight = viewportWidth - (iconRect.left + iconRect.width);
    const spaceToLeft = iconRect.left;
    const tooltipRect = tooltip.getBoundingClientRect();
    const tooltipWidth = tooltipRect.width;

    if (spaceToLeft >= tooltipWidth) {
      tooltip.style.left = `${iconRect.left}px`;
      tooltip.style.transform = 'translateX(-100%) translateX(-8px)';
      tooltip.style.top = `${iconRect.top + iconRect.height + 8}px`;
    } else if (spaceToRight >= tooltipWidth) {
      tooltip.style.left = `${iconRect.right}px`;
      tooltip.style.transform = 'translateX(8px)';
      tooltip.style.top = `${iconRect.top + iconRect.height + 8}px`;
    } else {
      tooltip.style.left = `${iconRect.left + iconRect.width / 2}px`;
      tooltip.style.transform = 'translateX(-50%)';
      tooltip.style.top = `${iconRect.top - 8}px`;
    }
    // Ensure visibility
    tooltip.style.visibility = 'visible';
    tooltip.style.opacity = '1';
    tooltip.style.display = 'block';
  };
}
