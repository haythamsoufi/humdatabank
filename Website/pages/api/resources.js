// pages/api/resources.js
// API route for client-side access to resources from server-side data store

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const { getResourcesFromStore } = await import('../../lib/dataStore');

    const filters = {
      page: parseInt(req.query.page) || 1,
      per_page: parseInt(req.query.per_page) || 12,
      search: req.query.search || '',
      resource_type: req.query.resource_type || '',
      language: req.query.language || 'en'
    };

    const result = await getResourcesFromStore(filters);

    res.status(200).json(result);
  } catch (error) {
    console.error('Error fetching resources:', error);

    // If local store is not available, return empty response gracefully
    // This allows pages to show empty state instead of errors
    const page = parseInt(req.query.page) || 1;
    const perPage = parseInt(req.query.per_page) || 12;

    res.status(200).json({
      resources: [],
      total: 0,
      page: page,
      per_page: perPage,
      total_pages: 0,
      current_page: page
    });
  }
}
