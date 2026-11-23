/**
 * Interactive Map field: user-entered marker text and geocoder results must never become markup.
 *
 * The builders below feed Leaflet tooltips/popups and innerHTML, so a title such as
 * `<img onerror=...>` would run in every viewer's browser if it were interpolated raw.
 */
import { describe, it, expect } from 'vitest';
import { InteractiveMapField } from '../../plugins/interactive_map/static/js/map_field.js';

const proto = InteractiveMapField.prototype;
const HOSTILE = '"><img src=x onerror=alert(1)>';

function parse(html) {
  const host = document.createElement('div');
  host.innerHTML = html;
  return host;
}

describe('InteractiveMapField escaping', () => {
  const ctx = { canEdit: true, fieldId: 'f1' };
  const marker = { id: HOSTILE, title: '<b>t</b>', description: '<script>alert(1)</script>', lat: 1, lng: 2 };

  it('escapes title, description and id in the marker tooltip', () => {
    const dom = parse(proto.buildMarkerTooltipContent.call(ctx, marker));
    expect(dom.querySelector('img, script, b')).toBeNull();
    expect(dom.textContent).toContain('<b>t</b>');
    expect(dom.textContent).toContain('<script>alert(1)</script>');
    const editButton = dom.querySelector('[data-action="map:edit-marker"]');
    expect(editButton.getAttribute('data-marker-id')).toBe(HOSTILE);
  });

  it('escapes a hostile title shown when the marker has no description', () => {
    const dom = parse(proto.buildMarkerTooltipContent.call({ canEdit: false }, { ...marker, description: '' }));
    expect(dom.querySelector('img, script, b')).toBeNull();
  });

  it('escapes geocoder text and keeps the match highlight', () => {
    const html = proto.highlightMatch.call({}, 'Nairobi <img src=x onerror=1>', 'nair');
    const dom = parse(html);
    expect(dom.querySelector('img')).toBeNull();
    expect(dom.querySelector('strong').textContent).toBe('Nair');
    expect(dom.textContent).toBe('Nairobi <img src=x onerror=1>');
  });

  it('does not let a markup query add elements', () => {
    const dom = parse(proto.highlightMatch.call({}, 'a <b> c', '<b>'));
    expect(dom.querySelector('b')).toBeNull();
    expect(dom.querySelector('strong').textContent).toBe('<b>');
  });

  it('escapes address parts', () => {
    const html = proto.formatAddress.call({}, { city: '<i>x</i>', country: 'Kenya' });
    expect(parse(html).querySelector('i')).toBeNull();
    expect(parse(html).textContent).toBe('<i>x</i>, Kenya');
  });
});
