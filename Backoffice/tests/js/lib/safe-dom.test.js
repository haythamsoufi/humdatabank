import { describe, it, expect, beforeAll } from 'vitest';

let SafeDom;

beforeAll(async () => {
  await import('../../../app/static/js/lib/safe-dom.js');
  SafeDom = window.SafeDom;
});

const origin = () => window.location.origin;

describe('SafeDom.safeUrl - rejected schemes', () => {
  const dangerous = [
    'javascript:alert(1)',
    'JaVaScRiPt:alert(1)',
    '  javascript:alert(1)',
    '\u00a0javascript:alert(1)',
    '\u0001javascript:alert(1)',
    'java\tscript:alert(1)',
    'java\nscript:alert(1)',
    'java\rscript:alert(1)',
    'jav&#x61;script:alert(1)',
    'data:text/html,<script>alert(1)</script>',
    'DATA:text/html;base64,PHNjcmlwdD4=',
    'vbscript:msgbox(1)',
    'file:///etc/passwd',
    'blob:https://evil.example/uuid',
    'ftp://example.com/x',
    'mailto:a@b.c',
    'tel:+123456',
  ];

  it.each(dangerous)('rejects %j in default mode', (value) => {
    expect(SafeDom.safeUrl(value)).toBe('');
  });

  it.each(dangerous)('rejects %j even when external hosts are allowed', (value) => {
    expect(SafeDom.safeUrl(value, { allowSameOrigin: false })).toBe('');
  });

  it('rejects percent-encoded scheme only by treating it as a harmless relative path', () => {
    const out = SafeDom.safeUrl('%6Aavascript:alert(1)');
    expect(out === '' || !/^javascript:/i.test(out)).toBe(true);
    if (out) {
      expect(new URL(out, origin()).protocol).toMatch(/^https?:$/);
    }
  });

  it('never returns a string whose resolved protocol is not http(s)', () => {
    const inputs = [
      'javascript:alert(1)', 'data:,x', ' \tjavascript:x', 'JAVASCRIPT:x', '\u2028javascript:x',
    ];
    inputs.forEach((value) => {
      [undefined, { allowSameOrigin: false }, { allowRelativeOnly: true }].forEach((opts) => {
        const out = SafeDom.safeUrl(value, opts);
        expect(out).toBe('');
      });
    });
  });
});

describe('SafeDom.safeUrl - host and path handling', () => {
  it('rejects protocol-relative URLs to other hosts', () => {
    expect(SafeDom.safeUrl('//evil.example/x')).toBe('');
    expect(SafeDom.safeUrl('///evil.example/x')).toBe('');
  });

  it('rejects protocol-relative URLs with allowRelativeOnly even when external is allowed', () => {
    expect(SafeDom.safeUrl('//evil.example/x', { allowSameOrigin: false, allowRelativeOnly: true })).toBe('');
  });

  it('rejects backslash tricks', () => {
    expect(SafeDom.safeUrl('/\\evil.example')).toBe('');
    expect(SafeDom.safeUrl('\\\\evil.example')).toBe('');
    expect(SafeDom.safeUrl('/\\evil.example', { allowSameOrigin: false })).toBe('');
  });

  it('rejects embedded control characters', () => {
    expect(SafeDom.safeUrl('/ok\nSet-Cookie: a=b')).toBe('');
    expect(SafeDom.safeUrl('/ok\u0000x')).toBe('');
  });

  it('rejects external absolute URLs by default', () => {
    expect(SafeDom.safeUrl('https://evil.example/x')).toBe('');
  });

  it('allows external http(s) only with allowSameOrigin:false', () => {
    expect(SafeDom.safeUrl('https://docs.example.org/a?b=1', { allowSameOrigin: false }))
      .toBe('https://docs.example.org/a?b=1');
    expect(SafeDom.safeUrl('http://docs.example.org/a', { allowSameOrigin: false }))
      .toBe('http://docs.example.org/a');
  });

  it('allows extra schemes only when requested', () => {
    expect(SafeDom.safeUrl('mailto:a@b.co', { allowSchemes: ['mailto:'] })).toBe('mailto:a@b.co');
    expect(SafeDom.safeUrl('javascript:alert(1)', { allowSchemes: ['mailto:'] })).toBe('');
  });

  it('keeps safe relative paths and same-origin absolute URLs', () => {
    expect(SafeDom.safeUrl('/admin/x?y=1#z')).toBe('/admin/x?y=1#z');
    expect(SafeDom.safeUrl('relative/path')).toBe('relative/path');
    expect(SafeDom.safeUrl('#section')).toBe('#section');
    expect(SafeDom.safeUrl(origin() + '/x')).toBe(origin() + '/x');
  });

  it('returns empty string for empty, null, undefined and "None"', () => {
    ['', '   ', null, undefined, 'None'].forEach((v) => expect(SafeDom.safeUrl(v)).toBe(''));
  });

  it('honours allowPaths', () => {
    expect(SafeDom.safeUrl('/api/x', { allowPaths: ['/api/'] })).toBe('/api/x');
    expect(SafeDom.safeUrl('/other', { allowPaths: ['/api/'] })).toBe('');
  });
});

describe('SafeDom escaping', () => {
  it('escapeHtml escapes quotes so output is safe in attribute values', () => {
    expect(SafeDom.escapeHtml('<a href="x" onclick=\'y\'>&')).toBe(
      '&lt;a href=&quot;x&quot; onclick=&#39;y&#39;&gt;&amp;'
    );
    expect(SafeDom.escapeHtml(null)).toBe('');
    expect(SafeDom.escapeHtml(0)).toBe('0');
  });

  it('escapeHtml output cannot break out of a quoted attribute', () => {
    const host = document.createElement('div');
    host.innerHTML = '<span title="' + SafeDom.escapeHtml('" onmouseover="alert(1)') + '">x</span>';
    const span = host.querySelector('span');
    expect(span.getAttributeNames()).toEqual(['title']);
    expect(span.getAttribute('title')).toBe('" onmouseover="alert(1)');
  });

  it('safeHrefAttr falls back to # and escapes', () => {
    expect(SafeDom.safeHrefAttr('javascript:alert(1)')).toBe('#');
    expect(SafeDom.safeHrefAttr('/a?b="c"')).toBe('/a?b=&quot;c&quot;');
  });
});

describe('SafeDom.html / raw / setHtml', () => {
  it('html`` escapes interpolations and leaves the template literal alone', () => {
    const out = SafeDom.html`<b title="${'"x"'}">${'<img src=x onerror=alert(1)>'}</b>`;
    expect(SafeDom.isSafeHtml(out)).toBe(true);
    expect(String(out)).toBe(
      '<b title="&quot;x&quot;">&lt;img src=x onerror=alert(1)&gt;</b>'
    );
  });

  it('html`` nests SafeHtml and joins arrays with per-item escaping', () => {
    const items = ['a<b', SafeDom.raw('<i>ok</i>')];
    const out = SafeDom.html`<ul>${items}</ul>${SafeDom.html`<p>${'&'}</p>`}`;
    expect(String(out)).toBe('<ul>a&lt;b<i>ok</i></ul><p>&amp;</p>');
  });

  it('setHtml assigns SafeHtml as is and sanitises plain strings', () => {
    const el = document.createElement('div');
    SafeDom.setHtml(el, SafeDom.html`<b>${'x'}</b>`);
    expect(el.innerHTML).toBe('<b>x</b>');

    SafeDom.setHtml(el, '<b onclick="alert(1)">y</b><script>alert(1)</script>');
    expect(el.innerHTML).toBe('<b>y</b>');
  });
});

describe('SafeDom.sanitizeHtml', () => {
  const clean = (h) => SafeDom.sanitizeHtml(h);

  it('strips script, iframe, form controls, style and meta elements', () => {
    const out = clean(
      '<p>a</p><script>x()</script><iframe src="/x"></iframe><form><input></form><style>*{}</style><meta http-equiv="refresh" content="0">'
    );
    expect(out).toBe('<p>a</p>');
  });

  it('strips event handlers and style attributes', () => {
    const out = clean('<img src="/a.png" onerror="alert(1)" style="x:y" ONLOAD="z">');
    expect(out).toBe('<img src="/a.png">');
  });

  it.each([
    'javascript:alert(1)',
    ' JaVaScRiPt:alert(1)',
    'java\tscript:alert(1)',
    'java&#x0A;script:alert(1)',
    '&#106;avascript:alert(1)',
    'vbscript:x',
    'data:text/html,<script>alert(1)</script>',
    'file:///etc/passwd',
    '\\\\evil.example',
  ])('drops href %j', (value) => {
    const out = clean('<a href="' + value.replace(/"/g, '&quot;') + '">x</a>');
    expect(out).toBe('<a>x</a>');
  });

  it('keeps http(s), mailto, tel, relative and fragment hrefs', () => {
    ['https://a.example/x', 'http://a.example', 'mailto:a@b.co', 'tel:+1', '/rel', 'rel', '#frag'].forEach((h) => {
      expect(clean('<a href="' + h + '">x</a>')).toBe('<a href="' + h + '">x</a>');
    });
  });

  it('removes srcdoc / formaction / xlink:href with unsafe values and adds rel to target=_blank', () => {
    expect(clean('<a href="/x" target="_blank">x</a>')).toContain('rel="noopener noreferrer"');
    expect(clean('<svg><a xlink:href="javascript:alert(1)"><text>x</text></a></svg>')).not.toMatch(/javascript/i);
    expect(clean('<div srcdoc="<script>1</script>">x</div>')).toBe('<div>x</div>');
  });

  it('returns empty string for empty input', () => {
    expect(clean('')).toBe('');
    expect(clean(null)).toBe('');
  });
});

describe('SafeDom.setHref / setSrc / setAttr / navigate / openWindow', () => {
  it('setHref sets safe URL and removes the attribute for unsafe values', () => {
    const a = document.createElement('a');
    expect(SafeDom.setHref(a, '/ok')).toBe(true);
    expect(a.getAttribute('href')).toBe('/ok');
    expect(SafeDom.setHref(a, 'javascript:alert(1)')).toBe(false);
    expect(a.hasAttribute('href')).toBe(false);
  });

  it('setHref honours allowSameOrigin:false for http(s) but still denies script schemes', () => {
    const a = document.createElement('a');
    expect(SafeDom.setHref(a, 'https://docs.example.org/x', { allowSameOrigin: false })).toBe(true);
    expect(SafeDom.setHref(a, 'data:text/html,x', { allowSameOrigin: false })).toBe(false);
    expect(a.hasAttribute('href')).toBe(false);
  });

  it('setSrc denies data: and javascript:', () => {
    const img = document.createElement('img');
    expect(SafeDom.setSrc(img, 'data:image/svg+xml,<svg onload=alert(1)>')).toBe(false);
    expect(img.hasAttribute('src')).toBe(false);
    expect(SafeDom.setSrc(img, '/static/x.png')).toBe(true);
  });

  it('setAttr refuses event handler names and validates URL attributes', () => {
    const el = document.createElement('a');
    SafeDom.setAttr(el, 'onclick', 'alert(1)');
    expect(el.hasAttribute('onclick')).toBe(false);
    SafeDom.setAttr(el, 'href', 'javascript:alert(1)');
    expect(el.hasAttribute('href')).toBe(false);
    SafeDom.setAttr(el, 'href', '/safe');
    expect(el.getAttribute('href')).toBe('/safe');
    SafeDom.setAttr(el, 'data-x', '<b>');
    expect(el.getAttribute('data-x')).toBe('<b>');
  });

  it('navigate and openWindow refuse unsafe URLs', () => {
    expect(SafeDom.navigate('javascript:alert(1)')).toBe(false);
    expect(SafeDom.openWindow('javascript:alert(1)')).toBe(null);
  });
});

describe('SafeDom.sanitizeHtml allowControls', () => {
  it('strips form controls by default and keeps them when allowControls is set', () => {
    const src = '<input name="a" value="1"><select name="b"><option>x</option></select>';
    expect(SafeDom.sanitizeHtml(src)).not.toMatch(/<input|<select/i);
    const kept = SafeDom.sanitizeHtml(src, { allowControls: true });
    expect(kept).toMatch(/<input/i);
    expect(kept).toMatch(/<select/i);
  });

  it('still strips handlers and dangerous URLs when allowControls is set', () => {
    const out = SafeDom.sanitizeHtml(
      '<input onfocus="alert(1)" formaction="javascript:alert(1)"><a href="javascript:alert(1)">x</a>',
      { allowControls: true },
    );
    expect(out).not.toMatch(/onfocus|javascript:/i);
  });
});
