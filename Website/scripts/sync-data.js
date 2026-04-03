// scripts/sync-data.js
// Standalone script to sync data from backend API to local data store

const fs = require('fs').promises;
const path = require('path');

// Load environment variables from .env.local or .env
let envLoaded = false;
try {
  const dotenv = require('dotenv');
  const fsSync = require('fs');
  // Try .env.local first (Next.js convention), then .env
  const envPath = fsSync.existsSync('.env.local') ? '.env.local' : '.env';
  const result = dotenv.config({ path: envPath });
  if (!result.error) {
    envLoaded = true;
    console.log(`📄 Loaded environment from: ${envPath}`);
  } else if (fsSync.existsSync('.env.local') || fsSync.existsSync('.env')) {
    console.warn(`⚠️  Failed to load ${envPath}: ${result.error.message}`);
  }
} catch (e) {
  console.warn('⚠️  dotenv not available. Install it with: npm install --save-dev dotenv');
  console.warn('   Using system environment variables only.');
}

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || process.env.API_BASE_URL || 'https://backoffice-databank.fly.dev';
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || process.env.API_KEY || 'databank2026';
const DATA_DIR = path.join(__dirname, '..', 'data');
const CLEAN_API_KEY = (API_KEY || '').replace(/^Bearer\s+/i, '').trim();

// Debug: Show where API URL came from
const apiUrlSource = process.env.NEXT_PUBLIC_API_URL
  ? 'NEXT_PUBLIC_API_URL env var'
  : process.env.API_BASE_URL
    ? 'API_BASE_URL env var'
    : 'default (Fly.io)';

async function syncData() {
  console.log('🔄 Starting data sync...');
  console.log(`📡 API: ${API_BASE_URL} (from ${apiUrlSource})`);

  try {
    // Try Bearer auth first (current Backoffice expectation), fall back to query param for compatibility.
    const fetchWithAuthFallback = async (endpoint, { allowQueryFallback = true } = {}) => {
      const base = `${API_BASE_URL}${endpoint}`;
      const bearerResp = await fetch(base, {
        headers: CLEAN_API_KEY ? { Authorization: `Bearer ${CLEAN_API_KEY}` } : {}
      });

      if (bearerResp.ok) return bearerResp;
      if (!allowQueryFallback || bearerResp.status !== 401 || !CLEAN_API_KEY) return bearerResp;

      const sep = endpoint.includes('?') ? '&' : '?';
      return fetch(`${API_BASE_URL}${endpoint}${sep}api_key=${encodeURIComponent(CLEAN_API_KEY)}`);
    };

    // 1. Fetch comprehensive dataset with disaggregation data
    const url = `${API_BASE_URL}/api/v1/data/tables?related=all&per_page=100000&disagg=true`;
    console.log(`📥 Fetching data from: ${url}`);

    const response = await fetchWithAuthFallback('/api/v1/data/tables?related=all&per_page=100000&disagg=true');
    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`);
    }

    const data = await response.json();

    console.log(`✅ Fetched:`);
    console.log(`   - ${data.data?.length || 0} data records`);
    console.log(`   - ${data.form_items?.length || 0} form items`);
    console.log(`   - ${data.countries?.length || 0} countries`);

    // 2. Ensure data directory exists
    await fs.mkdir(DATA_DIR, { recursive: true });

    // 3. Write data files (with atomic writes)
    const tempFiles = {
      data: path.join(DATA_DIR, 'data.json.tmp'),
      formItems: path.join(DATA_DIR, 'form_items.json.tmp'),
      countries: path.join(DATA_DIR, 'countries.json.tmp'),
      metadata: path.join(DATA_DIR, 'metadata.json.tmp')
    };

    const finalFiles = {
      data: path.join(DATA_DIR, 'data.json'),
      formItems: path.join(DATA_DIR, 'form_items.json'),
      countries: path.join(DATA_DIR, 'countries.json'),
      metadata: path.join(DATA_DIR, 'metadata.json')
    };

    // Write to temporary files first
    await fs.writeFile(
      tempFiles.data,
      JSON.stringify(data.data || [], null, 2)
    );

    await fs.writeFile(
      tempFiles.formItems,
      JSON.stringify(data.form_items || [], null, 2)
    );

    await fs.writeFile(
      tempFiles.countries,
      JSON.stringify(data.countries || [], null, 2)
    );

    // 4. Fetch additional data (if needed)
    // Indicators
    let indicators = [];
    try {
      const indicatorsResponse = await fetchWithAuthFallback('/api/v1/indicator-bank');
      if (indicatorsResponse.ok) {
        const indicatorsData = await indicatorsResponse.json();
        indicators = indicatorsData.indicators || [];
        console.log(`   - ${indicators.length} indicators`);
      }
    } catch (error) {
      console.warn('⚠️ Failed to fetch indicators:', error.message);
    }

    // Templates
    let templates = [];
    try {
      const templatesResponse = await fetchWithAuthFallback('/api/v1/templates?per_page=1000');
      if (templatesResponse.ok) {
        const templatesData = await templatesResponse.json();
        templates = templatesData.templates || [];
        console.log(`   - ${templates.length} templates`);
      }
    } catch (error) {
      console.warn('⚠️ Failed to fetch templates:', error.message);
    }

    // Common Words
    let commonWords = [];
    try {
      const commonWordsResponse = await fetchWithAuthFallback('/api/v1/common-words?language=en');
      if (commonWordsResponse.ok) {
        const commonWordsData = await commonWordsResponse.json();
        commonWords = commonWordsData.common_words || [];
        console.log(`   - ${commonWords.length} common words`);
      }
    } catch (error) {
      console.warn('⚠️ Failed to fetch common words:', error.message);
    }

    // Resources (all pages)
    let resources = [];
    try {
      let page = 1;
      let hasMore = true;
      const perPage = 100; // Fetch in batches

      while (hasMore) {
        const resourcesResponse = await fetchWithAuthFallback(`/api/v1/resources?page=${page}&per_page=${perPage}`);
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

    // Submitted Documents (all pages)
    let submittedDocuments = [];
    try {
      let page = 1;
      let hasMore = true;
      const perPage = 100; // Fetch in batches

      while (hasMore) {
        const documentsResponse = await fetchWithAuthFallback(`/api/v1/submitted-documents?page=${page}&per_page=${perPage}&is_public=true&status=approved`);
        if (documentsResponse.ok) {
          const documentsData = await documentsResponse.json();
          const pageDocuments = documentsData.documents || [];
          submittedDocuments.push(...pageDocuments);

          hasMore = pageDocuments.length === perPage && page < (documentsData.total_pages || 1);
          page++;
        } else {
          hasMore = false;
        }
      }
      console.log(`   - ${submittedDocuments.length} submitted documents`);
    } catch (error) {
      console.warn('⚠️ Failed to fetch submitted documents:', error.message);
    }

    // Write indicators, templates, and common words
    if (indicators.length > 0) {
      await fs.writeFile(
        path.join(DATA_DIR, 'indicators.json.tmp'),
        JSON.stringify(indicators, null, 2)
      );
    }

    if (templates.length > 0) {
      await fs.writeFile(
        path.join(DATA_DIR, 'templates.json.tmp'),
        JSON.stringify(templates, null, 2)
      );
    }

    if (commonWords.length > 0) {
      await fs.writeFile(
        path.join(DATA_DIR, 'common_words.json.tmp'),
        JSON.stringify(commonWords, null, 2)
      );
    }

    if (resources.length > 0) {
      await fs.writeFile(
        path.join(DATA_DIR, 'resources.json.tmp'),
        JSON.stringify(resources, null, 2)
      );
    }

    if (submittedDocuments.length > 0) {
      await fs.writeFile(
        path.join(DATA_DIR, 'submitted_documents.json.tmp'),
        JSON.stringify(submittedDocuments, null, 2)
      );
    }

    // 5. Write metadata
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
      submitted_documents_count: submittedDocuments.length || 0,
      api_url: API_BASE_URL
    };

    await fs.writeFile(
      tempFiles.metadata,
      JSON.stringify(metadata, null, 2)
    );

    // Validate temp files
    for (const [key, tempFile] of Object.entries(tempFiles)) {
      try {
        const content = await fs.readFile(tempFile, 'utf-8');
        JSON.parse(content); // Throws if invalid
      } catch (error) {
        throw new Error(`Invalid JSON in ${key} file: ${error.message}`);
      }
    }

    // Atomic rename (atomic on most file systems)
    await fs.rename(tempFiles.data, finalFiles.data);
    await fs.rename(tempFiles.formItems, finalFiles.formItems);
    await fs.rename(tempFiles.countries, finalFiles.countries);
    await fs.rename(tempFiles.metadata, finalFiles.metadata);

    if (indicators.length > 0) {
      await fs.rename(
        path.join(DATA_DIR, 'indicators.json.tmp'),
        path.join(DATA_DIR, 'indicators.json')
      );
    }

    if (templates.length > 0) {
      await fs.rename(
        path.join(DATA_DIR, 'templates.json.tmp'),
        path.join(DATA_DIR, 'templates.json')
      );
    }

    if (commonWords.length > 0) {
      await fs.rename(
        path.join(DATA_DIR, 'common_words.json.tmp'),
        path.join(DATA_DIR, 'common_words.json')
      );
    }

    if (resources.length > 0) {
      await fs.rename(
        path.join(DATA_DIR, 'resources.json.tmp'),
        path.join(DATA_DIR, 'resources.json')
      );
    }

    if (submittedDocuments.length > 0) {
      await fs.rename(
        path.join(DATA_DIR, 'submitted_documents.json.tmp'),
        path.join(DATA_DIR, 'submitted_documents.json')
      );
    }

    console.log('✅ Sync completed successfully');
    console.log(`📁 Data stored in: ${DATA_DIR}`);

  } catch (error) {
    console.error('❌ Sync failed:', error);
    process.exit(1);
  }
}

// Run sync
syncData();
