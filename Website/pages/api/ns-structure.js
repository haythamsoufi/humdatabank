// pages/api/ns-structure.js
// API route for fetching NS organizational structure (branches, sub-branches, local units)

export default async function handler(req, res) {
  if (req.method !== 'GET') {
    return res.status(405).json({ error: 'Method not allowed' });
  }

  try {
    const { country_id, branch_id } = req.query;

    if (!country_id) {
      return res.status(400).json({ error: 'country_id is required' });
    }

    // Use internal URL for server-side requests
    const isServer = typeof window === 'undefined';
    const INTERNAL_API_URL = process.env.NEXT_INTERNAL_API_URL || process.env.INTERNAL_API_URL;
    const PUBLIC_API_URL = process.env.NEXT_PUBLIC_API_URL;

    const API_BASE_URL = isServer
      ? (INTERNAL_API_URL || PUBLIC_API_URL || 'http://backoffice:5000')
      : (PUBLIC_API_URL || 'http://localhost:5000');

    // Fetch branches for the country using public endpoint
    const branchesUrl = `${API_BASE_URL}/admin/organization/api/public/branches/${country_id}`;

    let branchesResponse;
    try {
      branchesResponse = await fetch(branchesUrl, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
        },
      });
    } catch (error) {
      console.error('Error fetching branches:', error);
      return res.status(503).json({ error: 'Backend service unavailable' });
    }

    if (!branchesResponse.ok) {
      // If error, return empty structure
      console.warn(`Failed to fetch branches: ${branchesResponse.status}`);
      return res.status(200).json({
        branches: [],
        subbranches: [],
        localunits: [],
      });
    }

    const branches = await branchesResponse.json();

    // Fetch sub-branches: if branch_id is provided, fetch for that branch; otherwise fetch all for the country
    let subbranches = [];
    let subbranchesUrl;
    if (branch_id) {
      subbranchesUrl = `${API_BASE_URL}/admin/organization/api/public/subbranches/${branch_id}`;
    } else {
      subbranchesUrl = `${API_BASE_URL}/admin/organization/api/public/subbranches/by-country/${country_id}`;
    }

    try {
      const subbranchesResponse = await fetch(subbranchesUrl, {
        method: 'GET',
        headers: {
          'Accept': 'application/json',
          'Content-Type': 'application/json',
        },
      });

      if (subbranchesResponse.ok) {
        subbranches = await subbranchesResponse.json();
      }
    } catch (error) {
      console.error('Error fetching sub-branches:', error);
      // Continue without sub-branches
    }

    // For now, we'll return branches and sub-branches
    // Local units can be added later if needed
    res.status(200).json({
      branches: Array.isArray(branches) ? branches : [],
      subbranches: Array.isArray(subbranches) ? subbranches : [],
    });
  } catch (error) {
    console.error('Error fetching NS structure:', error);
    // Return empty structure on error instead of 500 to prevent UI issues
    return res.status(200).json({
      branches: [],
      subbranches: [],
      localunits: [],
    });
  }
}
