import { describe, it, expect } from 'vitest';
import {
  WAF_JSON_MAX_CHUNK,
  encodeUtf8ToB64,
  wrapWafJsonBody,
  stringifyWafJsonBody,
} from '../../../app/static/js/lib/waf-json-body.js';

function decodeB64(b64) {
  return decodeURIComponent(escape(atob(b64)));
}

describe('waf-json-body', () => {
  it('wraps a small object as a single payload argument', () => {
    const inner = { message: 'hello', client: 'backoffice' };
    const envelope = wrapWafJsonBody(inner);
    expect(Object.keys(envelope)).toEqual(['payload']);
    expect(JSON.parse(decodeB64(envelope.payload))).toEqual(inner);
  });

  it('chunks a long payload so no argument exceeds WAF_JSON_MAX_CHUNK', () => {
    const inner = {
      message: 'SELECT <script> ' + 'x'.repeat(2000),
      conversationHistory: [{ message: '<div>{{ name }}</div>', isUser: false }],
    };
    const envelope = wrapWafJsonBody(inner);
    expect(envelope.payload.length).toBe(WAF_JSON_MAX_CHUNK);
    expect(envelope.payload__c1).toBeTruthy();
    let joined = envelope.payload;
    for (let i = 1; envelope['payload__c' + i]; i += 1) {
      joined += envelope['payload__c' + i];
    }
    Object.keys(envelope).forEach((key) => {
      expect(envelope[key].length).toBeLessThanOrEqual(WAF_JSON_MAX_CHUNK);
    });
    expect(JSON.parse(decodeB64(joined))).toEqual(inner);
  });

  it('stringifyWafJsonBody is valid JSON and hides raw HTML', () => {
    const inner = { message: '<script>alert(1)</script>' };
    const raw = stringifyWafJsonBody(inner);
    expect(raw).not.toContain('<script>');
    const parsed = JSON.parse(raw);
    expect(parsed.payload).toBe(encodeUtf8ToB64(JSON.stringify(inner)));
  });
});
