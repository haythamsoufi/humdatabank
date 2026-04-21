// pages/api/templates.js
// API route for client-side access to templates from server-side data store

import { getTemplatesFromStore } from '../../lib/dataStore';

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const filters = {};
    if (req.query.id) {
      filters.id = req.query.id;
    }

    const templates = await getTemplatesFromStore(filters);

    // Return in the same format as the backend API
    res.status(200).json({ templates });
  } catch (error) {
    console.error('Error fetching templates:', error);
    res.status(500).json({ error: error.message });
  }
}
