/**
 * Entry-form sections pane splitter (hover divider + drag/keyboard resize).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const FIXTURE = `
<div id="entry-form-layout">
  <div id="section-navigation-sidebar" data-collapsed="false"></div>
  <div id="entry-form-sidebar-resizer" role="separator" tabindex="0">
    <span class="entry-form-sidebar-resizer__line"></span>
  </div>
  <div id="main-form-area"></div>
</div>
`;

function mockRects({ layoutWidth = 1200, sidebarWidth = 240 } = {}) {
  const original = HTMLElement.prototype.getBoundingClientRect;
  HTMLElement.prototype.getBoundingClientRect = function mockGetBoundingClientRect() {
    if (this.id === 'entry-form-layout') {
      return {
        width: layoutWidth,
        height: 800,
        top: 0,
        left: 0,
        right: layoutWidth,
        bottom: 800,
        x: 0,
        y: 0,
        toJSON() {},
      };
    }
    if (this.id === 'section-navigation-sidebar') {
      const fromStyle = parseFloat(this.style.width);
      const width = Number.isFinite(fromStyle) ? fromStyle : sidebarWidth;
      return {
        width,
        height: 600,
        top: 0,
        left: 0,
        right: width,
        bottom: 600,
        x: 0,
        y: 0,
        toJSON() {},
      };
    }
    return original.call(this);
  };
  return () => {
    HTMLElement.prototype.getBoundingClientRect = original;
  };
}

async function loadModule({
  innerWidth = 1400,
  storedWidth = null,
  collapsed = false,
  dir = 'ltr',
} = {}) {
  vi.resetModules();
  localStorage.clear();
  if (storedWidth != null) {
    localStorage.setItem('ifrc-sidebar-width', String(storedWidth));
  }
  if (collapsed) {
    localStorage.setItem('ifrc-sidebar-collapsed', 'true');
  }
  document.documentElement.setAttribute('dir', dir);
  document.body.innerHTML = FIXTURE;
  const sidebar = document.getElementById('section-navigation-sidebar');
  sidebar.setAttribute('data-collapsed', collapsed ? 'true' : 'false');
  Object.defineProperty(window, 'innerWidth', { configurable: true, value: innerWidth });
  HTMLElement.prototype.setPointerCapture = vi.fn();
  HTMLElement.prototype.releasePointerCapture = vi.fn();
  return import('../../../app/static/js/forms/modules/sidebar-collapse.js');
}

describe('clampEntryFormSidebarWidth', () => {
  it('enforces a 200px floor', async () => {
    const { clampEntryFormSidebarWidth } = await loadModule();
    expect(clampEntryFormSidebarWidth(80, 1200)).toBe(200);
  });

  it('enforces a 560px ceiling on a wide layout', async () => {
    const { clampEntryFormSidebarWidth } = await loadModule();
    expect(clampEntryFormSidebarWidth(900, 1600)).toBe(560);
  });

  it('caps at half the layout width when that is smaller than 560', async () => {
    const { clampEntryFormSidebarWidth } = await loadModule();
    expect(clampEntryFormSidebarWidth(500, 800)).toBe(400);
  });

  it('falls back to the minimum for non-numeric input', async () => {
    const { clampEntryFormSidebarWidth } = await loadModule();
    expect(clampEntryFormSidebarWidth(NaN, 1200)).toBe(200);
  });
});

describe('entry-form sidebar resize', () => {
  let restoreRects;

  beforeEach(() => {
    restoreRects = mockRects();
  });

  afterEach(() => {
    restoreRects?.();
    document.body.classList.remove('entry-form-sidebar-resizing');
    document.documentElement.removeAttribute('dir');
    document.body.innerHTML = '';
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it('applies a stored pane width on large screens', async () => {
    await loadModule({ storedWidth: 360 });
    const sidebar = document.getElementById('section-navigation-sidebar');
    expect(sidebar.style.width).toBe('360px');
    expect(sidebar.style.maxWidth).toBe('360px');
  });

  it('does not apply a stored width while the pane is collapsed', async () => {
    await loadModule({ storedWidth: 360, collapsed: true });
    const sidebar = document.getElementById('section-navigation-sidebar');
    expect(sidebar.style.width).toBe('');
  });

  it('widens the pane when the splitter is dragged right', async () => {
    await loadModule();
    const resizer = document.getElementById('entry-form-sidebar-resizer');
    const sidebar = document.getElementById('section-navigation-sidebar');

    resizer.dispatchEvent(new PointerEvent('pointerdown', {
      bubbles: true,
      pointerId: 1,
      pointerType: 'mouse',
      button: 0,
      clientX: 240,
    }));
    window.dispatchEvent(new PointerEvent('pointermove', {
      bubbles: true,
      pointerId: 1,
      clientX: 320,
    }));
    window.dispatchEvent(new PointerEvent('pointerup', {
      bubbles: true,
      pointerId: 1,
      clientX: 320,
    }));

    expect(sidebar.style.width).toBe('320px');
    expect(localStorage.getItem('ifrc-sidebar-width')).toBe('320');
    expect(document.body.classList.contains('entry-form-sidebar-resizing')).toBe(false);
  });

  it('inverts drag direction in RTL', async () => {
    await loadModule({ dir: 'rtl' });
    const resizer = document.getElementById('entry-form-sidebar-resizer');
    const sidebar = document.getElementById('section-navigation-sidebar');

    resizer.dispatchEvent(new PointerEvent('pointerdown', {
      bubbles: true,
      pointerId: 1,
      pointerType: 'mouse',
      button: 0,
      clientX: 960,
    }));
    window.dispatchEvent(new PointerEvent('pointermove', {
      bubbles: true,
      pointerId: 1,
      clientX: 880,
    }));
    window.dispatchEvent(new PointerEvent('pointerup', {
      bubbles: true,
      pointerId: 1,
      clientX: 880,
    }));

    expect(sidebar.style.width).toBe('320px');
  });

  it('nudges width with arrow keys and resets on Home', async () => {
    await loadModule();
    const resizer = document.getElementById('entry-form-sidebar-resizer');
    const sidebar = document.getElementById('section-navigation-sidebar');

    resizer.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    expect(sidebar.style.width).toBe('256px');

    resizer.dispatchEvent(new KeyboardEvent('keydown', { key: 'Home', bubbles: true }));
    expect(sidebar.style.width).toBe('');
    expect(localStorage.getItem('ifrc-sidebar-width')).toBeNull();
  });

  it('resets to the default width on double-click', async () => {
    await loadModule({ storedWidth: 400 });
    const resizer = document.getElementById('entry-form-sidebar-resizer');
    const sidebar = document.getElementById('section-navigation-sidebar');
    expect(sidebar.style.width).toBe('400px');

    resizer.dispatchEvent(new MouseEvent('dblclick', { bubbles: true }));
    expect(sidebar.style.width).toBe('');
    expect(localStorage.getItem('ifrc-sidebar-width')).toBeNull();
  });
});
