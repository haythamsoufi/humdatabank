// pages/api/health.js
export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    // Test backend connectivity
    const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'https://backoffice-databank.fly.dev';
    const API_KEY = process.env.NEXT_PUBLIC_API_KEY || '';

    const testUrl = `${API_BASE_URL}/api/v1/countrymap?api_key=${API_KEY}&per_page=1`;

    const response = await fetch(testUrl, {
      method: 'GET',
      headers: {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      },
      signal: AbortSignal.timeout(10000), // 10 second timeout
    });

    if (response.ok) {
      const data = await response.json();
      return res.status(200).json({
        status: 'healthy',
        backend: 'connected',
        timestamp: new Date().toISOString(),
        data: {
          countries_count: Array.isArray(data) ? data.length : 'unknown',
          response_time: 'ok'
        }
      });
    } else {
      return res.status(503).json({
        status: 'unhealthy',
        backend: 'error',
        error: `Backoffice returned ${response.status}`,
        timestamp: new Date().toISOString()
      });
    }
  } catch (error) {
    return res.status(503).json({
      status: 'unhealthy',
      backend: 'unreachable',
      error: error.message,
      timestamp: new Date().toISOString()
    });
  }
}
