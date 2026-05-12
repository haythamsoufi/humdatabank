// pages/api/ai-conversations.js
// Proxy endpoint for fetching AI conversations (logged-in users only)

function resolveBackofficeBaseUrl() {
  const isDev = process.env.NODE_ENV === 'development';
  const publicUrl = process.env.NEXT_PUBLIC_API_URL;
  const internalUrl = process.env.NEXT_INTERNAL_API_URL || process.env.INTERNAL_API_URL;

  if (internalUrl) return internalUrl.replace(/\/$/, '');
  if (publicUrl) return publicUrl.replace(/\/$/, '');
  return isDev ? 'http://localhost:5000' : 'https://backoffice-databank.fly.dev';
}

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const API_BASE_URL = resolveBackofficeBaseUrl();
    const { conversation_id } = req.query;

    // Forward Authorization header if present
    const authHeader = req.headers.authorization;

    let url;
    if (conversation_id) {
      // Get specific conversation
      url = `${API_BASE_URL}/api/ai/v2/conversations/${conversation_id}`;
    } else {
      // List all conversations
      const limit = req.query.limit || '50';
      url = `${API_BASE_URL}/api/ai/v2/conversations?limit=${limit}`;
    }

    const resp = await fetch(url, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...(authHeader ? { Authorization: authHeader } : {}),
      },
    });

    const data = await resp.json().catch(() => null);

    if (!resp.ok) {
      // 401/403 means not authenticated - return empty list
      if (resp.status === 401 || resp.status === 403) {
        return res.status(200).json(conversation_id ? { conversation: null, messages: [] } : { conversations: [] });
      }
      return res.status(resp.status).json({
        error: data?.error || `Backoffice returned ${resp.status}`,
      });
    }

    return res.status(200).json(data);
  } catch (error) {
    return res.status(500).json({ error: error.message || 'Proxy error' });
  }
}
