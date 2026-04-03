// pages/api/common-words.js
// API route for client-side access to common words from the local data store

import { getCommonWordsFromStore } from '../../lib/dataStore';

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const language = req.query.language || 'en';

    // Get common words from store (returns empty structure if not available)
    const data = await getCommonWordsFromStore(language);

    // Always return a valid structure, even if empty
    res.status(200).json(data || { success: false, common_words: [], total: 0 });
  } catch (error) {
    console.error('Error fetching common words:', error);
    // Return empty structure instead of error to allow app to continue
    res.status(200).json({ success: false, common_words: [], total: 0 });
  }
}
