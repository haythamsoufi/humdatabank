// lib/dataStore.js
// Server-side data store for caching backend API data locally
// Uses JSON files for storage with in-memory caching for performance

import fs from 'fs/promises';
import path from 'path';

const isServer = typeof window === 'undefined';

const DATA_DIR = path.join(process.cwd(), 'data');
const DATA_FILES = {
  data: path.join(DATA_DIR, 'data.json'),
  formItems: path.join(DATA_DIR, 'form_items.json'),
  countries: path.join(DATA_DIR, 'countries.json'),
  indicators: path.join(DATA_DIR, 'indicators.json'),
  sectorsSubsectors: path.join(DATA_DIR, 'sectors_subsectors.json'),
  templates: path.join(DATA_DIR, 'templates.json'),
  commonWords: path.join(DATA_DIR, 'common_words.json'),
  resources: path.join(DATA_DIR, 'resources.json'),
  submittedDocuments: path.join(DATA_DIR, 'submitted_documents.json'),
  metadata: path.join(DATA_DIR, 'metadata.json')
};

// In-memory cache for faster access
let dataCache = null;
let cacheTimestamp = 0;
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

const USE_LOCAL_STORE = process.env.NEXT_PUBLIC_USE_LOCAL_STORE !== 'false';
const FORCE_API = process.env.NEXT_PUBLIC_FORCE_API === 'true';

async function loadDataFile(fileKey) {
  try {
    const filePath = DATA_FILES[fileKey];
    const content = await fs.readFile(filePath, 'utf-8');
    return JSON.parse(content);
  } catch (error) {
    console.error(`Error loading ${fileKey}:`, error);
    return null;
  }
}

// Apply filters to data (async to support form_items join for indicator_bank_id)
async function applyFilters(data, filters) {
  let filtered = Array.isArray(data) ? [...data] : [];
  console.log(`Applying filters. Initial data count: ${filtered.length}, Filters:`, filters);

  // For country filtering, we need to join with countries table if country_info is not populated
  if (filters.country_iso3 || filters.country_iso2) {
    const beforeCount = filtered.length;
    console.log(`[dataStore] Applying country filter. Initial count: ${beforeCount}, Filters:`, {
      country_iso3: filters.country_iso3,
      country_iso2: filters.country_iso2
    });

    // Check if data has country_info populated (from API responses with related='all')
    // Sample first few items to check
    const hasCountryInfo = filtered.length > 0 &&
                          filtered.some(d => d.country_info && (d.country_info.iso3 || d.country_info.iso2));

    console.log(`[dataStore] Has country_info in data: ${hasCountryInfo}, will ${hasCountryInfo ? 'use direct filter' : 'use countries join'}`);

    if (hasCountryInfo) {
      // Use country_info directly (from API responses)
      if (filters.country_iso3) {
        filtered = filtered.filter(d =>
          d.country_info?.iso3?.toUpperCase() === filters.country_iso3.toUpperCase()
        );
        console.log(`[dataStore] Filtered by country_iso3 using country_info: ${beforeCount} -> ${filtered.length} items`);
      }
      if (filters.country_iso2) {
        filtered = filtered.filter(d =>
          d.country_info?.iso2?.toUpperCase() === filters.country_iso2.toUpperCase()
        );
        console.log(`[dataStore] Filtered by country_iso2 using country_info: ${beforeCount} -> ${filtered.length} items`);
      }
    } else {
      // Need to join with countries table using country_id
      let countriesMap = null;
      try {
        if (isServer) {
          console.log(`[dataStore] Loading countries file for join...`);
          const countries = await loadDataFile('countries');
          console.log(`[dataStore] Loaded ${countries?.length || 0} countries from file`);
          if (countries && Array.isArray(countries)) {
            // Create a map: country_id -> { iso3, iso2 }
            countriesMap = new Map();
            countries.forEach(country => {
              if (country.id && (country.iso3 || country.iso2)) {
                countriesMap.set(country.id, {
                  iso3: country.iso3,
                  iso2: country.iso2
                });
              }
            });
            console.log(`[dataStore] Created countries map with ${countriesMap.size} entries`);
          }
        } else {
          console.warn(`[dataStore] Cannot load countries file on client-side, skipping join`);
        }
      } catch (error) {
        console.error('[dataStore] Failed to load countries for filtering:', error);
      }

      if (countriesMap && countriesMap.size > 0) {
        filtered = filtered.filter(d => {
          const countryId = d.country_id;
          const countryData = countryId ? countriesMap.get(countryId) : null;

          if (!countryData) return false;

          // Match if ISO3 matches OR ISO2 matches (if provided)
          let matches = true;
          if (filters.country_iso3) {
            matches = matches && (countryData.iso3?.toUpperCase() === filters.country_iso3.toUpperCase());
          }
          if (filters.country_iso2) {
            matches = matches && (countryData.iso2?.toUpperCase() === filters.country_iso2.toUpperCase());
          }

          return matches;
        });
        console.log(`[dataStore] Filtered by country using countries join (${filters.country_iso3 || filters.country_iso2}): ${beforeCount} -> ${filtered.length} items`);

        // Debug: log a few sample matches for troubleshooting
        if (filtered.length > 0 && filtered.length <= 5) {
          console.log(`[dataStore] Sample filtered items:`, filtered.slice(0, 3).map(d => ({
            country_id: d.country_id,
            period_name: d.period_name,
            form_item_id: d.form_item_id
          })));
        }
      } else {
        // Fallback: try direct fields if countries map not available
        console.warn(`[dataStore] countriesMap not available (size: ${countriesMap?.size || 0}), falling back to direct fields.`);
        if (filters.country_iso3) {
          filtered = filtered.filter(d =>
            d.country_info?.iso3?.toUpperCase() === filters.country_iso3.toUpperCase()
          );
        }
        if (filters.country_iso2) {
          filtered = filtered.filter(d =>
            d.country_info?.iso2?.toUpperCase() === filters.country_iso2.toUpperCase()
          );
        }
      }
    }
  }

  if (filters.period_name) {
    const beforeCount = filtered.length;
    filtered = filtered.filter(d => d.period_name === filters.period_name);
    console.log(`Filtered by period_name ${filters.period_name}: ${beforeCount} -> ${filtered.length} items`);
  }

  // For indicator_bank_id, we need to join with form_items table
  if (filters.indicator_bank_id) {
    const indicatorId = parseInt(filters.indicator_bank_id);
    const beforeCount = filtered.length;

    // Load form_items to get the mapping from form_item_id to indicator_bank_id
    let formItemsMap = null;
    try {
      if (isServer) {
        const formItems = await loadDataFile('formItems');
        if (formItems && Array.isArray(formItems)) {
          // Create a map: form_item_id -> indicator_bank_id
          formItemsMap = new Map();
          formItems.forEach(fi => {
            const bankId = fi.bank_details?.id || fi.indicator_bank_id;
            if (bankId && fi.id) {
              formItemsMap.set(fi.id, parseInt(bankId));
            }
          });
        }
      }
    } catch (error) {
      console.warn('Failed to load form_items for filtering:', error);
    }

    if (formItemsMap) {
      filtered = filtered.filter(d => {
        const formItemId = d.form_item_id;
        const itemIndicatorId = formItemsMap.get(formItemId);
        return itemIndicatorId === indicatorId;
      });
      console.log(`Filtered by indicator_bank_id ${indicatorId} (using form_items join): ${beforeCount} -> ${filtered.length} items`);
    } else {
      // Fallback: try direct fields (for API responses that might have hydrated data)
      console.warn('formItemsMap not available for indicator_bank_id filtering, falling back to direct fields.');
      filtered = filtered.filter(d => {
        const itemIndicatorId = d.form_item_info?.bank_details?.id ||
                               d.form_item_info?.indicator_bank_id ||
                               d.indicator_bank_id;
        return itemIndicatorId === indicatorId;
      });
      console.log(`Filtered by indicator_bank_id ${indicatorId} (direct fields fallback): ${beforeCount} -> ${filtered.length} items`);
    }
  }

  if (filters.template_id) {
    const beforeCount = filtered.length;
    const templateId = parseInt(filters.template_id);
    filtered = filtered.filter(d => parseInt(d.template_id) === templateId);
    console.log(`Filtered by template_id ${templateId}: ${beforeCount} -> ${filtered.length} items`);
  }

  if (filters.submission_type) {
    const beforeCount = filtered.length;
    filtered = filtered.filter(d => d.submission_type === filters.submission_type);
    console.log(`Filtered by submission_type ${filters.submission_type}: ${beforeCount} -> ${filtered.length} items`);
  }

  console.log(`Finished applying filters. Final data count: ${filtered.length}`);
  return filtered;
}

export async function getDataFromStore(filters = {}) {
  if (!USE_LOCAL_STORE || FORCE_API) {
    throw new Error('Local store not enabled or API forced');
  }

  if (!isServer) {
    // Client-side: use API route
    try {
      const params = new URLSearchParams();
      Object.keys(filters).forEach(key => {
        if (filters[key] !== undefined && filters[key] !== null) {
          params.append(key, filters[key]);
        }
      });

      const response = await fetch(`/api/data?${params.toString()}`);
      if (response.ok) {
        const result = await response.json();
        return result.data || result;
      }
    } catch (error) {
      console.warn('Failed to get data from API route:', error);
      throw error;
    }
    return [];
  }

  // Server-side: read from JSON files
  // Check in-memory cache first
  const now = Date.now();
  if (dataCache && (now - cacheTimestamp) < CACHE_TTL) {
    return await applyFilters(dataCache, filters);
  }

  // Load from file
  const data = await loadDataFile('data');
  if (!data) {
    throw new Error('Data store not available. Please run sync first.');
  }

  // Update cache
  dataCache = data;
  cacheTimestamp = now;

  // Apply filters (async to support form_items join)
  return await applyFilters(data, filters);
}

export async function getFormItemsFromStore(filters = {}) {
  if (!USE_LOCAL_STORE || FORCE_API) {
    throw new Error('Local store not enabled or API forced');
  }

  if (isServer) {
    const formItems = await loadDataFile('formItems');
    if (!formItems) return [];

    let filtered = Array.isArray(formItems) ? [...formItems] : [];

    if (filters.template_id) {
      const templateId = parseInt(filters.template_id);
      filtered = filtered.filter(fi => parseInt(fi.template_id) === templateId);
    }
    if (filters.item_type) {
      filtered = filtered.filter(fi => fi.type === filters.item_type);
    }

    return filtered;
  } else {
    // Client-side: IndexedDB (not implemented yet)
    return [];
  }
}

export async function getCountriesFromStore(filters = {}) {
  if (!USE_LOCAL_STORE || FORCE_API) {
    throw new Error('Local store not enabled or API forced');
  }

  if (isServer) {
    return await loadDataFile('countries') || [];
  } else {
    // Client-side: use API route
    try {
      const response = await fetch('/api/countries');
      if (response.ok) {
        return await response.json();
      }
    } catch (error) {
      console.warn('Failed to get countries from API route:', error);
    }
    return [];
  }
}

export async function getIndicatorsFromStore(filters = {}) {
  if (!USE_LOCAL_STORE || FORCE_API) {
    throw new Error('Local store not enabled or API forced');
  }

  if (isServer) {
    const indicators = await loadDataFile('indicators');
    if (!indicators || !Array.isArray(indicators)) return [];

    let filtered = [...indicators];

    // Apply filters
    if (filters.searchQuery) {
      const searchLower = filters.searchQuery.toLowerCase();
      filtered = filtered.filter(ind =>
        (ind.name || '').toLowerCase().includes(searchLower) ||
        (ind.localized_name || '').toLowerCase().includes(searchLower) ||
        (ind.definition || '').toLowerCase().includes(searchLower) ||
        (ind.localized_definition || '').toLowerCase().includes(searchLower)
      );
    }
    if (filters.type) {
      filtered = filtered.filter(ind => ind.type === filters.type);
    }
    if (filters.sector) {
      const sectorValue = typeof filters.sector === 'object' ? (filters.sector.name || filters.sector.primary) : filters.sector;
      filtered = filtered.filter(ind => {
        const indSector = typeof ind.sector === 'object' ? (ind.sector.name || ind.sector.primary) : ind.sector;
        return indSector === sectorValue;
      });
    }
    if (filters.subSector) {
      const subSectorValue = typeof filters.subSector === 'object' ? (filters.subSector.name || filters.subSector.primary) : filters.subSector;
      filtered = filtered.filter(ind => {
        const indSubSector = typeof ind.sub_sector === 'object' ? (ind.sub_sector.name || ind.sub_sector.primary) : ind.sub_sector;
        return indSubSector === subSectorValue;
      });
    }
    if (filters.archived !== null && filters.archived !== undefined) {
      filtered = filtered.filter(ind => ind.archived === filters.archived);
    }

    return filtered;
  } else {
    // Client-side: use API route (which reads from server-side store)
    return [];
  }
}

export async function getSectorsSubsectorsFromStore() {
  if (!USE_LOCAL_STORE || FORCE_API) {
    throw new Error('Local store not enabled or API forced');
  }

  if (isServer) {
    const payload = await loadDataFile('sectorsSubsectors');
    if (!payload || typeof payload !== 'object') return { sectors: [] };
    const sectors = Array.isArray(payload.sectors) ? payload.sectors : [];
    return { sectors };
  }

  // Client-side: use API route (which reads from server-side store)
  return { sectors: [] };
}

export async function getCommonWordsFromStore(language = 'en') {
  if (!USE_LOCAL_STORE || FORCE_API) {
    return { success: false, common_words: [], total: 0 };
  }

  if (isServer) {
    try {
      const commonWords = await loadDataFile('commonWords');
      if (!commonWords || !Array.isArray(commonWords)) {
        return { success: false, common_words: [], total: 0 };
      }

      // Filter by language if needed (common words may have translations)
      // For now, return all common words as the API handles language filtering
      return {
        success: true,
        common_words: commonWords,
        total: commonWords.length
      };
    } catch (error) {
      // File doesn't exist or other error - return empty structure
      return { success: false, common_words: [], total: 0 };
    }
  } else {
    // Client-side: use API route (which reads from server-side store)
    return { success: false, common_words: [], total: 0 };
  }
}

export async function getTemplatesFromStore(filters = {}) {
  if (!USE_LOCAL_STORE || FORCE_API) {
    throw new Error('Local store not enabled or API forced');
  }

  if (isServer) {
    const templates = await loadDataFile('templates');
    if (!templates || !Array.isArray(templates)) return [];

    let filtered = [...templates];

    // Apply filters if any
    if (filters.id) {
      const templateId = parseInt(filters.id);
      filtered = filtered.filter(t => parseInt(t.id) === templateId);
    }

    return filtered;
  } else {
    // Client-side: use API route
    try {
      const params = new URLSearchParams();
      if (filters.id) params.append('id', filters.id);

      const response = await fetch(`/api/templates?${params.toString()}`);
      if (response.ok) {
        return await response.json();
      }
    } catch (error) {
      console.warn('Failed to get templates from API route:', error);
    }
    return [];
  }
}

export async function getResourcesFromStore(filters = {}) {
  if (!USE_LOCAL_STORE || FORCE_API) {
    throw new Error('Local store not enabled or API forced');
  }

  if (isServer) {
    try {
      const resources = await loadDataFile('resources');
      if (!resources || !Array.isArray(resources)) {
        return {
          resources: [],
          total: 0,
          page: filters.page || 1,
          per_page: filters.per_page || 12,
          total_pages: 0,
          current_page: filters.page || 1
        };
      }

      let filtered = [...resources];

      // Apply search filter
      if (filters.search) {
        const searchLower = filters.search.toLowerCase();
        filtered = filtered.filter(r =>
          (r.title && r.title.toLowerCase().includes(searchLower)) ||
          (r.description && r.description.toLowerCase().includes(searchLower))
        );
      }

      // Apply resource type filter
      if (filters.resource_type) {
        if (filters.resource_type === 'publication') {
          filtered = filtered.filter(r => r.resource_type === 'publication');
        } else if (filters.resource_type === 'other') {
          filtered = filtered.filter(r => r.resource_type !== 'publication');
        }
      }

      // Apply language filter if needed (resources may have multilingual fields)
      // For now, we return all resources as language filtering is handled in the API response

      // Calculate pagination
      const page = parseInt(filters.page) || 1;
      const perPage = parseInt(filters.per_page) || 12;
      const total = filtered.length;
      const totalPages = Math.ceil(total / perPage);
      const startIndex = (page - 1) * perPage;
      const endIndex = startIndex + perPage;
      const paginatedResources = filtered.slice(startIndex, endIndex);

      return {
        resources: paginatedResources,
        total: total,
        page: page,
        per_page: perPage,
        total_pages: totalPages,
        current_page: page
      };
    } catch (error) {
      console.error('Error loading resources from store:', error);
      return {
        resources: [],
        total: 0,
        page: filters.page || 1,
        per_page: filters.per_page || 12,
        total_pages: 0,
        current_page: filters.page || 1
      };
    }
  } else {
    // Client-side: use API route
    try {
      const params = new URLSearchParams();
      if (filters.page) params.append('page', filters.page.toString());
      if (filters.per_page) params.append('per_page', filters.per_page.toString());
      if (filters.search) params.append('search', filters.search);
      if (filters.resource_type) params.append('resource_type', filters.resource_type);
      if (filters.language) params.append('language', filters.language);

      const response = await fetch(`/api/resources?${params.toString()}`);
      if (response.ok) {
        return await response.json();
      }
    } catch (error) {
      console.warn('Failed to get resources from API route:', error);
    }
    return {
      resources: [],
      total: 0,
      page: filters.page || 1,
      per_page: filters.per_page || 12,
      total_pages: 0,
      current_page: filters.page || 1
    };
  }
}

/**
 * Get submitted documents from local store
 * @param {Object} filters - Filter parameters
 * @param {number} filters.country_id - Country ID to filter by
 * @param {string} filters.document_type - Document type filter
 * @param {string} filters.language - Language filter
 * @param {boolean} filters.is_public - Public status filter
 * @param {string} filters.status - Approval status filter
 * @param {number} filters.page - Page number
 * @param {number} filters.per_page - Items per page
 * @returns {Promise<Object>} - Submitted documents data
 */
export async function getSubmittedDocumentsFromStore(filters = {}) {
  if (!USE_LOCAL_STORE || FORCE_API) {
    throw new Error('Local store not enabled or API forced');
  }

  if (isServer) {
    try {
      const documents = await loadDataFile('submittedDocuments');

      // If file doesn't exist or is invalid, return empty structure
      // This signals that store is not available, so API fallback should be attempted
      if (!documents || !Array.isArray(documents)) {
        console.log('[getSubmittedDocumentsFromStore] Submitted documents file not found or invalid, returning empty');
        return {
          documents: [],
          total_items: 0,
          total_pages: 0,
          current_page: filters.page || 1,
          per_page: filters.per_page || 20,
          _storeUnavailable: true // Flag to indicate store file doesn't exist
        };
      }

      console.log(`[getSubmittedDocumentsFromStore] Loaded ${documents.length} documents from store`);

      let filtered = [...documents];

      // Apply country filter
      // Documents may have country_id directly OR country_info.id (nested)
      if (filters.country_id) {
        const countryId = parseInt(filters.country_id);
        filtered = filtered.filter(d => {
          const docCountryId = d.country_id || d.country_info?.id;
          return docCountryId === countryId;
        });
        console.log(`[getSubmittedDocumentsFromStore] Filtered by country_id ${countryId}: ${documents.length} -> ${filtered.length} items`);
      }

      // Apply document type filter
      if (filters.document_type) {
        const beforeCount = filtered.length;
        filtered = filtered.filter(d => d.document_type === filters.document_type);
        console.log(`[getSubmittedDocumentsFromStore] Filtered by document_type "${filters.document_type}": ${beforeCount} -> ${filtered.length} items`);
      }

      // Apply language filter (skip for Cover Images which often have null language)
      if (filters.language && filters.language.trim() !== '' && filters.document_type !== 'Cover Image') {
        const beforeCount = filtered.length;
        filtered = filtered.filter(d => d.language === filters.language);
        console.log(`[getSubmittedDocumentsFromStore] Filtered by language "${filters.language}": ${beforeCount} -> ${filtered.length} items`);
      }

      // Apply public status filter
      if (filters.is_public !== undefined) {
        const beforeCount = filtered.length;
        filtered = filtered.filter(d => d.is_public === filters.is_public);
        console.log(`[getSubmittedDocumentsFromStore] Filtered by is_public ${filters.is_public}: ${beforeCount} -> ${filtered.length} items`);
      }

      // Apply status filter
      if (filters.status) {
        const beforeCount = filtered.length;
        filtered = filtered.filter(d => d.status === filters.status);
        console.log(`[getSubmittedDocumentsFromStore] Filtered by status "${filters.status}": ${beforeCount} -> ${filtered.length} items`);
      }

      // Calculate pagination
      const page = parseInt(filters.page) || 1;
      const perPage = parseInt(filters.per_page) || 20;
      const total = filtered.length;
      const totalPages = Math.ceil(total / perPage);
      const startIndex = (page - 1) * perPage;
      const endIndex = startIndex + perPage;
      const paginatedDocuments = filtered.slice(startIndex, endIndex);

      return {
        documents: paginatedDocuments,
        total_items: total,
        total_pages: totalPages,
        current_page: page,
        per_page: perPage
      };
    } catch (error) {
      console.error('Error loading submitted documents from store:', error);
      return {
        documents: [],
        total_items: 0,
        total_pages: 0,
        current_page: filters.page || 1,
        per_page: filters.per_page || 20
      };
    }
  } else {
    // Client-side: use API route
    try {
      const params = new URLSearchParams();
      if (filters.country_id) params.append('country_id', filters.country_id.toString());
      if (filters.document_type) params.append('document_type', filters.document_type);
      if (filters.language) params.append('language', filters.language);
      if (filters.is_public !== undefined) params.append('is_public', filters.is_public.toString());
      if (filters.status) params.append('status', filters.status);
      if (filters.page) params.append('page', filters.page.toString());
      if (filters.per_page) params.append('per_page', filters.per_page.toString());

      const response = await fetch(`/api/submitted-documents?${params.toString()}`);
      if (response.ok) {
        return await response.json();
      }
    } catch (error) {
      console.warn('Failed to get submitted documents from API route:', error);
    }
    return {
      documents: [],
      total_items: 0,
      total_pages: 0,
      current_page: filters.page || 1,
      per_page: filters.per_page || 20
    };
  }
}

// Sync data from backend (server-side only)
export async function syncDataFromBackend() {
  if (!isServer) {
    throw new Error('syncDataFromBackend can only be called server-side');
  }

  const fs = require('fs').promises;
  const path = require('path');

  const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || process.env.API_BASE_URL;
  const API_KEY = process.env.NEXT_PUBLIC_API_KEY || process.env.API_KEY;

  if (!API_BASE_URL || !API_KEY) {
    throw new Error('API_BASE_URL and API_KEY must be configured');
  }

  console.log('🔄 Starting data sync from backend...');
  console.log(`📡 API: ${API_BASE_URL}`);

  // Ensure data directory exists
  await fs.mkdir(DATA_DIR, { recursive: true });

  try {
    // 1. Fetch comprehensive dataset with disaggregation data
    const url = `${API_BASE_URL}/api/v1/data/tables?api_key=${API_KEY}&related=all&per_page=100000&disagg=true`;
    console.log(`📥 Fetching data from: ${url}`);

    const response = await fetch(url);
    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`);
    }

    const data = await response.json();
    console.log(`✅ Fetched:`);
    console.log(`   - ${data.data?.length || 0} data records`);
    console.log(`   - ${data.form_items?.length || 0} form items`);
    console.log(`   - ${data.countries?.length || 0} countries`);

    // 2. Fetch indicators
    let indicators = [];
    try {
      const indicatorsUrl = `${API_BASE_URL}/api/v1/indicator-bank?api_key=${API_KEY}`;
      const indicatorsResponse = await fetch(indicatorsUrl);
      if (indicatorsResponse.ok) {
        const indicatorsData = await indicatorsResponse.json();
        indicators = indicatorsData.indicators || [];
        console.log(`   - ${indicators.length} indicators`);
      }
    } catch (error) {
      console.warn('⚠️ Failed to fetch indicators:', error.message);
    }

    // 3. Fetch templates
    let templates = [];
    try {
      const templatesUrl = `${API_BASE_URL}/api/v1/templates?api_key=${API_KEY}&per_page=1000`;
      const templatesResponse = await fetch(templatesUrl);
      if (templatesResponse.ok) {
        const templatesData = await templatesResponse.json();
        templates = templatesData.templates || [];
        console.log(`   - ${templates.length} templates`);
      }
    } catch (error) {
      console.warn('⚠️ Failed to fetch templates:', error.message);
    }

    // 4. Fetch common words
    let commonWords = [];
    try {
      const commonWordsUrl = `${API_BASE_URL}/api/v1/common-words?api_key=${API_KEY}&language=en`;
      const commonWordsResponse = await fetch(commonWordsUrl);
      if (commonWordsResponse.ok) {
        const commonWordsData = await commonWordsResponse.json();
        commonWords = commonWordsData.common_words || [];
        console.log(`   - ${commonWords.length} common words`);
      }
    } catch (error) {
      console.warn('⚠️ Failed to fetch common words:', error.message);
    }

    // 5. Fetch resources (all pages)
    let resources = [];
    try {
      let page = 1;
      let hasMore = true;
      const perPage = 100; // Fetch in batches

      while (hasMore) {
        const resourcesUrl = `${API_BASE_URL}/api/v1/resources?api_key=${API_KEY}&page=${page}&per_page=${perPage}`;
        const resourcesResponse = await fetch(resourcesUrl);
        if (resourcesResponse.ok) {
          const resourcesData = await resourcesResponse.json();
          const pageResources = resourcesData.resources || [];
          resources.push(...pageResources);

          hasMore = pageResources.length === perPage && page < (resourcesData.total_pages || 1);
          page++;
        } else {
          hasMore = false;
        }
      }
      console.log(`   - ${resources.length} resources`);
    } catch (error) {
      console.warn('⚠️ Failed to fetch resources:', error.message);
    }

      // 6. Write to temporary files first (atomic writes)
      const tempFiles = {
        data: DATA_FILES.data + '.tmp',
        formItems: DATA_FILES.formItems + '.tmp',
        countries: DATA_FILES.countries + '.tmp',
        indicators: DATA_FILES.indicators + '.tmp',
        templates: DATA_FILES.templates + '.tmp',
        commonWords: DATA_FILES.commonWords + '.tmp',
        resources: DATA_FILES.resources + '.tmp',
        metadata: DATA_FILES.metadata + '.tmp'
      };

    // Backup existing files
    const backupDir = path.join(DATA_DIR, 'backups', Date.now().toString());
    await fs.mkdir(backupDir, { recursive: true });

    try {
      // Backup current files
      for (const [key, filePath] of Object.entries(DATA_FILES)) {
        try {
          await fs.copyFile(filePath, path.join(backupDir, path.basename(filePath)));
        } catch (e) {
          // File might not exist yet
        }
      }

      // Write to temp files
      await fs.writeFile(tempFiles.data, JSON.stringify(data.data || [], null, 2));
      await fs.writeFile(tempFiles.formItems, JSON.stringify(data.form_items || [], null, 2));
      await fs.writeFile(tempFiles.countries, JSON.stringify(data.countries || [], null, 2));
      await fs.writeFile(tempFiles.indicators, JSON.stringify(indicators, null, 2));
      await fs.writeFile(tempFiles.templates, JSON.stringify(templates, null, 2));
      await fs.writeFile(tempFiles.commonWords, JSON.stringify(commonWords, null, 2));
      await fs.writeFile(tempFiles.resources, JSON.stringify(resources, null, 2));

      // 7. Write metadata
      const metadata = {
        last_sync: new Date().toISOString(),
        sync_timestamp: Date.now(),
        version: Date.now(),
        total_items: data.total_items,
        data_count: data.data?.length || 0,
        form_items_count: data.form_items?.length || 0,
        countries_count: data.countries?.length || 0,
        indicators_count: indicators.length || 0,
        templates_count: templates.length || 0,
        common_words_count: commonWords.length || 0,
        resources_count: resources.length || 0,
        api_url: API_BASE_URL
      };

      await fs.writeFile(tempFiles.metadata, JSON.stringify(metadata, null, 2));

      // Validate temp files
      for (const tempFile of Object.values(tempFiles)) {
        const content = await fs.readFile(tempFile, 'utf-8');
        JSON.parse(content); // Throws if invalid
      }

      // Atomic rename (atomic on most file systems)
      await fs.rename(tempFiles.data, DATA_FILES.data);
      await fs.rename(tempFiles.formItems, DATA_FILES.formItems);
      await fs.rename(tempFiles.countries, DATA_FILES.countries);
      await fs.rename(tempFiles.indicators, DATA_FILES.indicators);
      await fs.rename(tempFiles.templates, DATA_FILES.templates);
      await fs.rename(tempFiles.commonWords, DATA_FILES.commonWords);
      await fs.rename(tempFiles.resources, DATA_FILES.resources);
      await fs.rename(tempFiles.metadata, DATA_FILES.metadata);

      // Clear cache
      dataCache = null;
      cacheTimestamp = 0;

      // Cleanup old backups (keep last 5)
      await cleanupOldBackups();

      console.log('✅ Data sync completed successfully');
      console.log(`📁 Data stored in: ${DATA_DIR}`);

      return {
        success: true,
        data_count: data.data?.length || 0,
        form_items_count: data.form_items?.length || 0,
        countries_count: data.countries?.length || 0,
        indicators_count: indicators.length || 0,
        templates_count: templates.length || 0,
        resources_count: resources.length || 0
      };

    } catch (error) {
      // Rollback: restore from backup
      console.error('Sync failed, rolling back...', error);
      await restoreFromBackup(backupDir);
      throw error;
    } finally {
      // Cleanup temp files
      for (const tempFile of Object.values(tempFiles)) {
        try {
          await fs.unlink(tempFile);
        } catch (e) {
          // Ignore if doesn't exist
        }
      }
    }
  } catch (error) {
    console.error('❌ Sync failed:', error);
    throw error;
  }
}

async function cleanupOldBackups() {
  try {
    const backupsDir = path.join(DATA_DIR, 'backups');
    const entries = await fs.readdir(backupsDir);
    const backupDirs = entries.filter(e => /^\d+$/.test(e)).sort().reverse();

    // Keep only last 5 backups
    for (let i = 5; i < backupDirs.length; i++) {
      const oldBackup = path.join(backupsDir, backupDirs[i]);
      await fs.rm(oldBackup, { recursive: true, force: true });
    }
  } catch (error) {
    console.warn('Failed to cleanup old backups:', error);
  }
}

async function restoreFromBackup(backupDir) {
  try {
    const entries = await fs.readdir(backupDir);
    for (const entry of entries) {
      const backupFile = path.join(backupDir, entry);
      const targetFile = path.join(DATA_DIR, entry);
      await fs.copyFile(backupFile, targetFile);
    }
    console.log('✅ Restored from backup');
  } catch (error) {
    console.error('Failed to restore from backup:', error);
  }
}

export async function getMetadata() {
  return await loadDataFile('metadata');
}

export async function isDataStale(maxAgeHours = 24) {
  const metadata = await getMetadata();
  if (!metadata?.sync_timestamp) return true;

  const ageMs = Date.now() - metadata.sync_timestamp;
  const maxAgeMs = maxAgeHours * 60 * 60 * 1000;

  return ageMs > maxAgeMs;
}

export async function getDataStoreHealth() {
  const health = {
    status: 'healthy',
    issues: [],
    metadata: null,
    fileSizes: {},
    lastSync: null,
    dataAge: null
  };

  try {
    // Check if files exist
    for (const [key, filePath] of Object.entries(DATA_FILES)) {
      try {
        const stats = await fs.stat(filePath);
        health.fileSizes[key] = stats.size;

        // Check if file is too large (> 500MB)
        if (stats.size > 500 * 1024 * 1024) {
          health.issues.push(`${key} file is very large: ${(stats.size / 1024 / 1024).toFixed(2)}MB`);
        }
      } catch (error) {
        health.status = 'unhealthy';
        health.issues.push(`${key} file missing: ${error.message}`);
      }
    }

    // Check metadata
    health.metadata = await getMetadata();
    if (health.metadata) {
      health.lastSync = health.metadata.last_sync;
      const ageMs = Date.now() - health.metadata.sync_timestamp;
      health.dataAge = Math.floor(ageMs / 1000 / 60); // minutes

      if (ageMs > 48 * 60 * 60 * 1000) {
        health.status = 'degraded';
        health.issues.push(`Data is ${health.dataAge} minutes old (stale)`);
      }
    }

    // Validate data integrity
    try {
      const sample = await getDataFromStore({});
      if (!Array.isArray(sample) || sample.length === 0) {
        health.status = 'unhealthy';
        health.issues.push('Data file appears empty or invalid');
      }
    } catch (error) {
      health.status = 'unhealthy';
      health.issues.push(`Data validation failed: ${error.message}`);
    }

  } catch (error) {
    health.status = 'unhealthy';
    health.issues.push(`Health check failed: ${error.message}`);
  }

  return health;
}
