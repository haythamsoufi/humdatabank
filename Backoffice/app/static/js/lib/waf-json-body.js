/**
 * WAF-safe JSON POST body: wrap the real object as base64 and split it
 * across sibling keys so signature rules (941/942) never see HTML/SQL-like
 * tokens, and no single argument exceeds CRS 920370 example length.
 *
 * Wire format (same envelope as manage-settings / get_request_data):
 *   { "payload": "<first ≤350 chars>", "payload__c1": "...", ... }
 * Plain saves are base64. Form-builder saves whose base64 would be longer
 * than gzip+hex use a "gz:" prefix plus lowercase hex of the gzip bytes.
 *
 * Server: unwrap_waf_json_envelope() in app/utils/request_utils.py.
 *
 * @module lib/waf-json-body
 */

export const WAF_JSON_MAX_CHUNK = 350;

const HEX = '0123456789abcdef';

export function encodeUtf8ToB64(text) {
  return btoa(unescape(encodeURIComponent(String(text))));
}

/** Split an already-encoded wire string across payload / payload__cN. */
export function chunkWafPayload(wire) {
  const text = String(wire);
  if (text.length <= WAF_JSON_MAX_CHUNK) {
    return { payload: text };
  }
  const out = { payload: text.slice(0, WAF_JSON_MAX_CHUNK) };
  let index = 1;
  for (let i = WAF_JSON_MAX_CHUNK; i < text.length; i += WAF_JSON_MAX_CHUNK) {
    out['payload__c' + index] = text.slice(i, i + WAF_JSON_MAX_CHUNK);
    index += 1;
  }
  return out;
}

export function wrapWafJsonBody(innerObj) {
  return chunkWafPayload(encodeUtf8ToB64(JSON.stringify(innerObj)));
}

function bytesToHex(bytes) {
  const out = new Array(bytes.length);
  for (let i = 0; i < bytes.length; i += 1) {
    const b = bytes[i];
    out[i] = HEX[b >> 4] + HEX[b & 15];
  }
  return out.join('');
}

/**
 * Gzip UTF-8 text. Returns null when the runtime has no CompressionStream
 * (older browsers); callers then keep the plain base64 envelope.
 */
async function gzipUtf8(text) {
  const Ctor = globalThis.CompressionStream;
  if (typeof Ctor !== 'function' || typeof ReadableStream !== 'function') return null;
  const source = new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(text));
      controller.close();
    },
  });
  const reader = source.pipeThrough(new Ctor('gzip')).getReader();
  const chunks = [];
  let total = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    chunks.push(value);
    total += value.length;
  }
  const out = new Uint8Array(total);
  let offset = 0;
  chunks.forEach((chunk) => {
    out.set(chunk, offset);
    offset += chunk.length;
  });
  return out;
}

/**
 * Same envelope as wrapWafJsonBody, but gzip+hex when that wire is shorter.
 *
 * Chunking alone still leaves ARGS_COMBINED_SIZE equal to the whole blob.
 * A production matrix save (template 22, item 1303, 2026-10-15) was already
 * 70×350 base64 characters and Application Gateway still answered 403.
 * Gzip of that repetitive config is ~3KB; hex keeps the alphabet free of
 * '+', '/' and the '0x' sequence those rules key on. Prefix ``gz:`` so the
 * server can tell it from a base64 envelope.
 */
export async function wrapWafJsonBodyCompact(innerObj) {
  const json = JSON.stringify(innerObj);
  const plain = encodeUtf8ToB64(json);
  let wire = plain;
  try {
    const gz = await gzipUtf8(json);
    if (gz) {
      const packed = 'gz:' + bytesToHex(gz);
      if (packed.length < wire.length) wire = packed;
    }
  } catch (_) {
    wire = plain;
  }
  return chunkWafPayload(wire);
}

export function stringifyWafJsonBody(innerObj) {
  try {
    return JSON.stringify(wrapWafJsonBody(innerObj));
  } catch (_) {
    return JSON.stringify(innerObj);
  }
}
