// pages/api/data/health.js
// Health check endpoint for data store

import { getDataStoreHealth } from '../../../lib/dataStore';

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const health = await getDataStoreHealth();
    res.status(health.status === 'healthy' ? 200 : 503).json(health);
  } catch (error) {
    console.error('Error checking data store health:', error);
    res.status(500).json({
      status: 'unhealthy',
      error: error.message
    });
  }
}
