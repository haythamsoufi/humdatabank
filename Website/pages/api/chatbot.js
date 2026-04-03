// pages/api/chatbot.js
// Proxy endpoint that forwards chat requests to Backoffice AI brain (v2).

function resolveBackofficeBaseUrl() {
  const isDev = process.env.NODE_ENV === 'development';
  const publicUrl = process.env.NEXT_PUBLIC_API_URL;
  const internalUrl = process.env.NEXT_INTERNAL_API_URL || process.env.INTERNAL_API_URL;

  if (internalUrl) return internalUrl.replace(/\/$/, '');
  if (publicUrl) return publicUrl.replace(/\/$/, '');
  return isDev ? 'http://localhost:5000' : 'https://backoffice-databank.fly.dev';
}

export default async function handler(req, res) {
  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const { message, conversation_id, page_context, preferred_language, conversationHistory } = req.body || {};

    if (!message || typeof message !== 'string' || !message.trim()) {
      return res.status(400).json({ error: 'Message is required' });
    }

    const API_BASE_URL = resolveBackofficeBaseUrl();
    const url = `${API_BASE_URL}/api/ai/v2/chat`;

    // Forward Authorization header if present (for logged-in Website users later)
    const authHeader = req.headers.authorization;
    // Shared secret header that allows Backoffice to accept anonymous (public) chat safely.
    // This is server-side only; do NOT use NEXT_PUBLIC_* for this value.
    const proxySecret = process.env.AI_PUBLIC_PROXY_SECRET || process.env.NEXT_AI_PUBLIC_PROXY_SECRET;

    // Preserve client IP for Backoffice rate limiting behind proxies/CDN.
    const xForwardedFor = req.headers['x-forwarded-for'];
    const xRealIp = req.headers['x-real-ip'];

    // If the user is anonymous (no Bearer token), we must present the proxy secret in production.
    // In development, allow forwarding without the header so Backoffice can accept anonymous chat.
    const isDev = process.env.NODE_ENV === 'development';
    if (!authHeader && !proxySecret && !isDev) {
      return res.status(500).json({
        error: 'AI proxy misconfigured (missing AI_PUBLIC_PROXY_SECRET)',
      });
    }

    const resp = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(authHeader ? { Authorization: authHeader } : {}),
        ...(proxySecret ? { 'X-NGO-Databank-AI-Proxy': proxySecret } : {}),
        ...(xForwardedFor ? { 'X-Forwarded-For': xForwardedFor } : {}),
        ...(xRealIp ? { 'X-Real-IP': xRealIp } : {}),
      },
      body: JSON.stringify({
        message,
        conversation_id,
        page_context,
        preferred_language,
        conversationHistory,
        client: 'website',
      }),
      signal: AbortSignal.timeout(60000),
    });

    const data = await resp.json().catch(() => null);

    if (!resp.ok) {
      return res.status(resp.status).json({
        error: data?.error || `Backoffice returned ${resp.status}`,
      });
    }

    return res.status(200).json(data);
  } catch (error) {
    const isTimeout = error.name === 'TimeoutError' || error.message?.includes('timeout') || error.message?.includes('aborted');
    const isConnection = error.cause?.code === 'ECONNREFUSED' || error.cause?.code === 'ECONNRESET' || error.message?.includes('fetch failed');
    const message = isConnection || isTimeout
      ? `Backoffice unreachable at ${API_BASE_URL}. Ensure it is running (e.g. \`cd Backoffice && python run.py\`).`
      : (error.message || 'Proxy error');
    return res.status(502).json({ error: message });
  }
}
