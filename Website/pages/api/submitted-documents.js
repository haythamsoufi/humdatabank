// pages/api/submitted-documents.js
// API route for client-side access to submitted documents from server-side data store

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const { getSubmittedDocumentsFromStore } = await import('../../lib/dataStore');

    const filters = {
      country_id: req.query.country_id ? parseInt(req.query.country_id) : undefined,
      document_type: req.query.document_type || '',
      language: req.query.language || 'en',
      is_public: req.query.is_public !== undefined ? req.query.is_public === 'true' : true,
      status: req.query.status || 'approved',
      page: parseInt(req.query.page) || 1,
      per_page: parseInt(req.query.per_page) || 20
    };

    // Remove undefined filters
    Object.keys(filters).forEach(key =>
      filters[key] === undefined && delete filters[key]
    );

    const result = await getSubmittedDocumentsFromStore(filters);

    res.status(200).json(result);
  } catch (error) {
    console.error('Error fetching submitted documents:', error);

    // If local store is not available, return empty response gracefully
    // This allows pages to show empty state instead of errors
    const page = parseInt(req.query.page) || 1;
    const perPage = parseInt(req.query.per_page) || 20;

    res.status(200).json({
      documents: [],
      total_items: 0,
      total_pages: 0,
      current_page: page,
      per_page: perPage
    });
  }
}
