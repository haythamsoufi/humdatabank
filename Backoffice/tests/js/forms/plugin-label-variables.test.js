/**
 * Unit tests for plugin-label-variables.js (EO1/EO2/EO3 label substitution).
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

vi.mock('../../../app/static/js/forms/modules/debug.js', () => ({
  debugLog: vi.fn(),
  debugWarn: vi.fn(),
  debugError: vi.fn(),
}));

async function loadPluginLabelVariables() {
  vi.resetModules();
  return import('../../../app/static/js/forms/modules/plugin-label-variables.js');
}

function pluginEl({ eo1 = '', eo2 = '', eo3 = '', operationsCount, ready } = {}) {
  const el = document.createElement('div');
  el.setAttribute('data-eo1', eo1);
  el.setAttribute('data-eo2', eo2);
  el.setAttribute('data-eo3', eo3);
  if (operationsCount != null) el.setAttribute('data-operations-count', String(operationsCount));
  if (ready != null) el.setAttribute('data-plugin-data-ready', String(ready));
  return el;
}

function setupLabelRoots({
  sidebar = 'Ops [EO1]',
  heading = 'Title [EO2]',
  label = 'Field [EO3]',
  paragraph = 'Note [EO1]',
} = {}) {
  document.body.innerHTML = `
    <nav id="section-navigation-sidebar">
      <a class="section-link"><span>${sidebar}</span></a>
    </nav>
    <div id="entry-form-ui">
      <h2>${heading}</h2>
      <label>${label}<textarea>[EO1]</textarea><style>.x { content: '[EO2]'; }</style></label>
      <div class="form-item-block"><p>${paragraph}</p></div>
      <script type="text/plain">keep [EO1]</script>
      <input type="text" value="[EO1]">
    </div>
    <div id="outside-root">Outside [EO1]</div>`;
}

describe('getPluginVariableValues', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    delete window.__ifrcPluginVariables;
  });

  afterEach(() => {
    document.body.innerHTML = '';
    delete window.__ifrcPluginVariables;
    vi.useRealTimers();
  });

  it('reads EO1/EO2/EO3 from data-eo attributes on the event target', async () => {
    const { getPluginVariableValues } = await loadPluginLabelVariables();
    const target = pluginEl({ eo1: 'Flood', eo2: 'MDRXX001', eo3: '3' });
    expect(getPluginVariableValues({ target })).toEqual({
      EO1: 'Flood',
      EO2: 'MDRXX001',
      EO3: '3',
    });
  });

  it('prefers event target values over DOM candidates and caches lastValues', async () => {
    const { getPluginVariableValues } = await loadPluginLabelVariables();
    document.body.appendChild(pluginEl({ eo1: 'FromDom', eo2: 'DOM', eo3: '1' }));
    const target = pluginEl({ eo1: 'FromEvent', eo2: 'EVT', eo3: '9' });

    expect(getPluginVariableValues({ target }).EO1).toBe('FromEvent');
    expect(getPluginVariableValues()).toEqual({
      EO1: 'FromEvent',
      EO2: 'EVT',
      EO3: '9',
    });
  });

  it('pickBestSourceElement prefers a non-empty data-eo1 over operations-count', async () => {
    const { getPluginVariableValues } = await loadPluginLabelVariables();
    document.body.appendChild(pluginEl({ eo1: '', operationsCount: 5, eo2: 'count-only' }));
    document.body.appendChild(pluginEl({ eo1: 'Named Op', eo2: 'CODE' }));

    expect(getPluginVariableValues()).toEqual({
      EO1: 'Named Op',
      EO2: 'CODE',
      EO3: '',
    });
  });

  it('pickBestSourceElement falls back to operations-count > 0 when data-eo1 is empty', async () => {
    const { getPluginVariableValues } = await loadPluginLabelVariables();
    document.body.appendChild(pluginEl({ eo1: '', eo2: 'empty-first' }));
    document.body.appendChild(pluginEl({ eo1: '', eo2: 'has-ops', operationsCount: 2 }));

    expect(getPluginVariableValues().EO2).toBe('has-ops');
  });

  it('returns null when there is no cache and no data-eo candidate', async () => {
    const { getPluginVariableValues } = await loadPluginLabelVariables();
    expect(getPluginVariableValues()).toBeNull();
  });
});

describe('replacePluginLabelVariablesInPage', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    delete window.__ifrcPluginVariables;
  });

  afterEach(() => {
    document.body.innerHTML = '';
    delete window.__ifrcPluginVariables;
  });

  it('replaces [EO1] [EO2] [EO3] in label roots but not SCRIPT/STYLE/TEXTAREA/INPUT', async () => {
    const { replacePluginLabelVariablesInPage } = await loadPluginLabelVariables();
    setupLabelRoots();
    const source = pluginEl({ eo1: 'Cyclone', eo2: 'MDRYY002', eo3: '12', ready: true });
    document.body.appendChild(source);

    replacePluginLabelVariablesInPage({ target: source });

    expect(document.querySelector('#section-navigation-sidebar .section-link span').textContent)
      .toBe('Ops Cyclone');
    expect(document.querySelector('#entry-form-ui h2').textContent).toBe('Title MDRYY002');
    expect(document.querySelector('#entry-form-ui label').childNodes[0].textContent)
      .toBe('Field 12');
    expect(document.querySelector('#entry-form-ui .form-item-block p').textContent)
      .toBe('Note Cyclone');
    expect(document.querySelector('#entry-form-ui textarea').textContent).toBe('[EO1]');
    expect(document.querySelector('#entry-form-ui style').textContent).toContain('[EO2]');
    expect(document.querySelector('#entry-form-ui script').textContent).toBe('keep [EO1]');
    expect(document.querySelector('#entry-form-ui input').value).toBe('[EO1]');
    expect(document.getElementById('outside-root').textContent).toBe('Outside [EO1]');
  });

  it('leaves placeholders in place when the matching value is empty', async () => {
    const { replacePluginLabelVariablesInPage } = await loadPluginLabelVariables();
    setupLabelRoots({ sidebar: 'Ops [EO1] / [EO2]' });
    const source = pluginEl({ eo1: 'Named', eo2: '   ' });
    document.body.appendChild(source);

    replacePluginLabelVariablesInPage({ target: source });

    expect(document.querySelector('#section-navigation-sidebar .section-link span').textContent)
      .toBe('Ops Named / [EO2]');
  });

  it('re-applies from original text when plugin values arrive after an empty pass', async () => {
    const { replacePluginLabelVariablesInPage } = await loadPluginLabelVariables();
    setupLabelRoots({ sidebar: 'Ops [EO1]' });
    const source = pluginEl({ eo1: '' });
    document.body.appendChild(source);

    replacePluginLabelVariablesInPage({ target: source });
    expect(document.querySelector('#section-navigation-sidebar .section-link span').textContent)
      .toBe('Ops [EO1]');

    source.setAttribute('data-eo1', 'Second');
    replacePluginLabelVariablesInPage({ target: source });
    expect(document.querySelector('#section-navigation-sidebar .section-link span').textContent)
      .toBe('Ops Second');
  });

  it('publishes __ifrcPluginVariables only when the source is data-ready', async () => {
    const { replacePluginLabelVariablesInPage } = await loadPluginLabelVariables();
    setupLabelRoots({ sidebar: 'Ops [EO1]' });
    const source = pluginEl({ eo1: 'Pending', ready: false });
    document.body.appendChild(source);

    replacePluginLabelVariablesInPage({ target: source });
    expect(window.__ifrcPluginVariables).toBeUndefined();
    expect(document.querySelector('#section-navigation-sidebar .section-link span').textContent)
      .toBe('Ops Pending');

    source.setAttribute('data-plugin-data-ready', 'true');
    replacePluginLabelVariablesInPage({ target: source });
    expect(window.__ifrcPluginVariables.EO1).toBe('Pending');
  });

  it('is a no-op when no plugin values are available', async () => {
    const { replacePluginLabelVariablesInPage } = await loadPluginLabelVariables();
    setupLabelRoots({ sidebar: 'Ops [EO1]' });
    replacePluginLabelVariablesInPage();
    expect(document.querySelector('#section-navigation-sidebar .section-link span').textContent)
      .toBe('Ops [EO1]');
  });
});

describe('initPluginLabelVariableReplacement', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
    delete window.__ifrcPluginVariables;
  });

  afterEach(() => {
    document.body.innerHTML = '';
    delete window.__ifrcPluginVariables;
    vi.useRealTimers();
  });

  it('replaces labels on init and on operationsCountUpdated', async () => {
    vi.useFakeTimers();
    const { initPluginLabelVariableReplacement } = await loadPluginLabelVariables();
    setupLabelRoots({ sidebar: 'Ops [EO1]' });
    const source = pluginEl({ eo1: '' });
    document.body.appendChild(source);

    initPluginLabelVariableReplacement();
    await vi.advanceTimersByTimeAsync(0);
    expect(document.querySelector('#section-navigation-sidebar .section-link span').textContent)
      .toBe('Ops [EO1]');

    source.setAttribute('data-eo1', 'Updated');
    source.dispatchEvent(new CustomEvent('operationsCountUpdated', { bubbles: true }));
    await vi.advanceTimersByTimeAsync(0);
    expect(document.querySelector('#section-navigation-sidebar .section-link span').textContent)
      .toBe('Ops Updated');
  });

  it('schedules replacement when data-eo attributes change', async () => {
    const { initPluginLabelVariableReplacement } = await loadPluginLabelVariables();
    setupLabelRoots({ sidebar: 'Ops [EO1]' });
    const source = pluginEl({ eo1: '' });
    document.body.appendChild(source);

    initPluginLabelVariableReplacement();
    await vi.waitFor(() => {
      expect(document.querySelector('#section-navigation-sidebar .section-link span').textContent)
        .toBe('Ops [EO1]');
    });

    source.setAttribute('data-eo1', 'Observed');
    await vi.waitFor(() => {
      expect(document.querySelector('#section-navigation-sidebar .section-link span').textContent)
        .toBe('Ops Observed');
    });
  });
});
