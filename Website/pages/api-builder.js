// pages/api-builder.js (legacy entry)
import Head from 'next/head';
import { useState, useEffect } from 'react';
import { motion } from 'framer-motion';
import Layout from '../components/layout/Layout';
import { downloadExcelFromJson } from '../lib/downloadUtils';
import { useTranslation } from '../lib/useTranslation';

export default function ApiBuilder() {
  const { t } = useTranslation();
  const backendBaseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:5000';
  const apiKey = process.env.NEXT_PUBLIC_API_KEY || 'databank2026';

  // State for parameters
  const [parameters, setParameters] = useState({
    template_id: { enabled: false, value: '' },
    country_id: { enabled: false, value: '' },
    item_type: { enabled: false, value: '' },
    submission_type: { enabled: false, value: '' },
      disagg: { enabled: false, value: '' },
    period_name: { enabled: false, value: '' },
    page: { enabled: false, value: '1' },
    per_page: { enabled: false, value: '20' }
  });

  // State for fetched data
  const [templates, setTemplates] = useState([]);
  const [countries, setCountries] = useState([]);
  const [isLoadingData, setIsLoadingData] = useState(true);
  const [dataError, setDataError] = useState(null);

  // State for URL and response
  const [generatedUrl, setGeneratedUrl] = useState('');
  const [copyStatus, setCopyStatus] = useState('copy');
  const [response, setResponse] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);

  // Fetch data from API routes (which use stored data)
  const fetchData = async () => {
    setIsLoadingData(true);
    setDataError(null);
    try {
      // Import functions that use stored data
      const { getTemplates, getCountriesList } = await import('../lib/apiService');

      // Fetch templates (uses stored data via API route)
      try {
        const templates = await getTemplates();
        setTemplates(templates || []);
      } catch (error) {
        console.error('Failed to fetch templates:', error);
        setTemplates([]); // Set empty array instead of showing error
      }

      // Fetch countries (uses stored data via API route)
      try {
        const countries = await getCountriesList();
        setCountries(countries || []);
      } catch (error) {
        console.error('Failed to fetch countries:', error);
        setCountries([]); // Set empty array instead of showing error
      }
    } catch (error) {
      console.error('Error fetching data:', error);
      // Don't show error message, just set empty arrays
      setTemplates([]);
      setCountries([]);
    } finally {
      setIsLoadingData(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  // Parameter definitions with real data
  const parameterDefinitions = {
    template_id: {
      type: 'select',
      options: templates.map(t => ({ value: t.id.toString(), label: t.name })),
      placeholder: t('apiBuilder.parameters.template_id.placeholder'),
      description: t('apiBuilder.parameters.template_id.description')
    },
    country_id: {
      type: 'select',
      options: countries.map(c => ({ value: c.id.toString(), label: c.name })),
      placeholder: t('apiBuilder.parameters.country_id.placeholder'),
      description: t('apiBuilder.parameters.country_id.description')
    },
    item_type: {
      type: 'select',
      options: [
        { value: 'indicator', label: 'Indicator' },
        { value: 'question', label: 'Question' },
        { value: 'document_field', label: 'Document Field' }
      ],
      placeholder: t('apiBuilder.parameters.item_type.placeholder'),
      description: t('apiBuilder.parameters.item_type.description')
    },
    submission_type: {
      type: 'select',
      options: [
        { value: 'assigned', label: 'Assigned' },
        { value: 'public', label: 'Public' }
      ],
      placeholder: t('apiBuilder.parameters.submission_type.placeholder'),
      description: t('apiBuilder.parameters.submission_type.description')
    },
    disagg: {
      type: 'select',
      options: [
        { value: 'true', label: t('common.yes') },
        { value: 'false', label: t('common.no') }
      ],
      placeholder: t('apiBuilder.parameters.disagg.placeholder', { defaultValue: 'Select yes or no' }),
      description: t('apiBuilder.parameters.disagg.description', { defaultValue: 'Include disaggregation data when available' })
    },
    period_name: {
      type: 'text',
      placeholder: t('apiBuilder.parameters.period_name.placeholder'),
      description: t('apiBuilder.parameters.period_name.description')
    },
    page: {
      type: 'number',
      placeholder: t('apiBuilder.parameters.page.placeholder'),
      description: t('apiBuilder.parameters.page.description')
    },
    per_page: {
      type: 'number',
      placeholder: t('apiBuilder.parameters.per_page.placeholder'),
      description: t('apiBuilder.parameters.per_page.description')
    }
  };

  // Animation variants
  const staggerContainer = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1
      }
    }
  };

  const fadeInUp = {
    hidden: { opacity: 0, y: 20 },
    visible: {
      opacity: 1,
      y: 0,
      transition: {
        duration: 0.5
      }
    }
  };

  // Handle parameter changes
  const handleParameterChange = (key, field, value) => {
    setParameters(prev => ({
      ...prev,
      [key]: {
        ...prev[key],
        [field]: value
      }
    }));
  };

  // Handle example queries
  const handleExampleQuery = (exampleParams) => {
    const newParams = { ...parameters };
    Object.keys(newParams).forEach(key => {
      newParams[key] = { enabled: false, value: '' };
    });

    Object.entries(exampleParams).forEach(([key, value]) => {
      if (newParams[key]) {
        newParams[key] = { enabled: true, value: value.toString() };
      }
    });

    setParameters(newParams);
  };

  // Copy URL to clipboard
  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(generatedUrl);
      setCopyStatus('copied');
      setTimeout(() => setCopyStatus('copy'), 2000);
    } catch (err) {
      console.error('Failed to copy: ', err);
    }
  };

  // Test endpoint
  const testEndpoint = async () => {
    setIsLoading(true);
    setResponse(null);

    try {
      const response = await fetch(generatedUrl);
      const contentType = response.headers.get('content-type');

      if (contentType && contentType.includes('application/json')) {
        const data = await response.json();
        setResponse({
          status: response.status,
          data: data,
          error: null
        });
      } else {
        const text = await response.text();
        setResponse({
          status: response.status,
          data: null,
          error: `Expected JSON response but got ${contentType}. Response starts with: ${text.substring(0, 100)}...`,
          rawResponse: text.substring(0, 500)
        });
      }
    } catch (error) {
      setResponse({
        status: 0,
        data: null,
        error: `Network error: ${error.message}`
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleDownloadExcel = async () => {
    const buildExportUrl = (url) => {
      try {
        const u = new URL(url);
        u.searchParams.set('per_page', '100000');
        return u.toString();
      } catch (_) {
        if (/([?&])per_page=\d+/.test(url)) {
          return url.replace(/per_page=\d+/, 'per_page=100000');
        }
        const joiner = url.includes('?') ? '&' : '?';
        return `${url}${joiner}per_page=100000`;
      }
    };

    try {
      setIsDownloading(true);
      const exportUrl = buildExportUrl(generatedUrl);
      const res = await fetch(exportUrl);
      const contentType = res.headers.get('content-type') || '';
      if (!contentType.includes('application/json')) {
        throw new Error('Endpoint did not return JSON');
      }
      const dataToExport = await res.json();
      await downloadExcelFromJson(dataToExport, 'humdb-api-data.xlsx');
    } catch (err) {
      console.error('Excel download failed:', err);
      alert(t('alerts.failedToDownloadExcel'));
    } finally {
      setIsDownloading(false);
    }
  };

  // Example queries
  const exampleQueries = [
    {
      name: t('apiBuilder.examples.allData'),
      params: {}
    },
    {
      name: t('apiBuilder.examples.assignedSubmissions'),
      params: { submission_type: 'assigned' }
    },
    {
      name: t('apiBuilder.examples.publicSubmissions'),
      params: { submission_type: 'public' }
    },
    {
      name: t('apiBuilder.examples.indicatorsOnly'),
      params: { item_type: 'indicator' }
    },
    {
      name: t('apiBuilder.examples.first10Results'),
      params: { per_page: '10' }
    },
    ...(templates.length > 0 ? [{
      name: t('apiBuilder.examples.dataFromTemplate', { templateName: templates[0].name }),
      params: { template_id: templates[0].id.toString() }
    }] : []),
    ...(countries.length > 0 ? [{
      name: t('apiBuilder.examples.dataFromCountry', { countryName: countries[0].name }),
      params: { country_id: countries[0].id.toString() }
    }] : [])
  ];

  // Generate URL whenever parameters change
  useEffect(() => {
    const baseUrl = `${backendBaseUrl}/api/v1/data?api_key=${apiKey}`;
    const queryParams = [];

    Object.entries(parameters).forEach(([key, param]) => {
      if (param.enabled && param.value !== '') {
        queryParams.push(`${key}=${encodeURIComponent(param.value)}`);
      }
    });

    const url = queryParams.length > 0 ? `${baseUrl}&${queryParams.join('&')}` : baseUrl;
    setGeneratedUrl(url);
  }, [parameters]);

  return (
    <>
      <Head>
        <title>{`${t('apiBuilder.title')} - Humanitarian Databank`}</title>
        <meta name="description" content={t('apiBuilder.meta.description')} />
      </Head>

      {/* Hero Section */}
      <section className="bg-humdb-navy text-humdb-white py-16 md:py-24 -mt-20 md:-mt-[136px] xl:-mt-20 pt-36 md:pt-[156px] xl:pt-36">
        <div className="container mx-auto px-4 sm:px-6 lg:px-8">
          <motion.div
            initial="hidden"
            animate="visible"
            variants={fadeInUp}
            className="text-center"
          >
            <h1 className="text-4xl md:text-5xl font-bold mb-6">
              {t('apiBuilder.hero.title')}
            </h1>
            <p className="text-xl text-humdb-gray-200 max-w-3xl mx-auto">
              {t('apiBuilder.hero.description')}
            </p>
          </motion.div>
        </div>
      </section>

                {/* In-page Navigation */}
          <div className="bg-humdb-gray-50 border-b border-humdb-gray-200">
            <div className="container mx-auto px-4 sm:px-6 lg:px-8">
              <nav className="flex flex-wrap items-center gap-3 py-3 text-sm" aria-label="API page navigation">
                <a href="#overview" className="px-3 py-1 rounded-full bg-white border hover:border-humdb-red hover:text-humdb-red transition-colors">{t('apiBuilder.navigation.overview')}</a>
                <a href="#docs" className="px-3 py-1 rounded-full bg-white border hover:border-humdb-red hover:text-humdb-red transition-colors">{t('apiBuilder.navigation.documentation')}</a>
                <a href="#builder" className="px-3 py-1 rounded-full bg-white border hover:border-humdb-red hover:text-humdb-red transition-colors">{t('apiBuilder.navigation.builder')}</a>
              </nav>
            </div>
          </div>

      {/* Main Content */}
      <div className="container mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <motion.div
          initial="hidden"
          animate="visible"
          variants={staggerContainer}
          className="max-w-6xl mx-auto"
        >
          {/* Overview Section */}
          <motion.div variants={fadeInUp} className="scroll-mt-24 mb-8" id="overview">
            <div className="bg-humdb-white rounded-2xl shadow-sm p-8">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {/* Description */}
                <div className="md:col-span-2">
                  <h2 className="text-2xl font-bold text-humdb-navy mb-4">
                    {t('apiBuilder.description.title')}
                  </h2>
                  <p className="text-humdb-gray-700 mb-4">
                    {t('apiBuilder.description.text')}
                  </p>
                  <div className="bg-humdb-gray-50 rounded-lg p-4">
                    <p className="text-sm text-humdb-gray-600">
                      {(() => {
                        const note = t('apiBuilder.description.note');
                        const email = 'data@example.com';
                        const parts = note.split(email);
                        if (parts.length === 2) {
                          return (
                            <>
                              {parts[0]}
                              <a href={`mailto:${email}`} className="text-humdb-red hover:text-humdb-red-dark underline">{email}</a>
                              {parts[1]}
                            </>
                          );
                        }
                        return note;
                      })()}
                    </p>
                  </div>
                </div>

                {/* Endpoint Info */}
                <div className="bg-humdb-navy text-humdb-white rounded-xl p-6">
                  <h3 className="text-lg font-semibold mb-4">
                    {t('apiBuilder.endpoint.title')}
                  </h3>
                  <div className="space-y-3">
                    <div className="flex items-center space-x-3">
                      <span className="px-2 py-1 bg-humdb-red text-humdb-white text-xs font-semibold rounded">
                        {t('apiBuilder.endpoint.method')}
                      </span>
                    </div>
                    <div className="text-humdb-gray-200 font-mono text-sm break-all">
                      <div className="opacity-80">{t('apiBuilder.labels.baseUrl', { defaultValue: 'Base URL' })}</div>
                      <code>{backendBaseUrl}</code>
                    </div>
                    <div className="text-humdb-gray-200 font-mono text-sm break-all">
                      <div className="opacity-80">{t('apiBuilder.labels.endpoint', { defaultValue: 'Endpoint' })}</div>
                      <code>/api/v1/data</code>
                    </div>
                    <p className="text-humdb-gray-300 text-sm">
                      {t('apiBuilder.endpoint.description')}
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>

          {/* API Documentation */}
          <motion.div variants={fadeInUp} className="scroll-mt-24 mb-8" id="docs">
            <div className="bg-humdb-white rounded-2xl shadow-sm p-8">
              <h2 className="text-2xl font-bold text-humdb-navy mb-2">{t('apiBuilder.docs.title', { defaultValue: 'API Documentation' })}</h2>
              <p className="text-humdb-gray-700 mb-6">{t('apiBuilder.docs.intro', { defaultValue: 'Construct requests and learn how to use the Databank API effectively. Below are essentials for authentication, filtering, pagination, and disaggregation.' })}</p>
              <div className="space-y-6">
                <div>
                  <h3 className="text-lg font-semibold text-humdb-navy">{t('apiBuilder.docs.authentication', { defaultValue: 'Authentication' })}</h3>
                  <p className="text-sm text-humdb-gray-700 mt-2">{t('apiBuilder.docs.authInstruction', { param: 'api_key', defaultValue: 'Pass your API key via the api_key query parameter.' })}</p>
                  <pre className="text-xs whitespace-pre-wrap bg-humdb-gray-50 border border-humdb-gray-200 rounded-lg p-3 mt-2">{`GET ${backendBaseUrl}/api/v1/data?api_key=YOUR_KEY`}</pre>
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-humdb-navy">{t('apiBuilder.endpoint.title')}</h3>
                  <div className="mt-2 p-3 bg-humdb-gray-50 border border-humdb-gray-200 rounded-lg">
                    <code className="text-sm">GET /api/v1/data</code>
                  </div>
                  <p className="text-sm text-humdb-gray-600 mt-2">
                    Returns submitted form data with optional filtering and pagination.
                  </p>
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-humdb-navy">{t('apiBuilder.docs.queryParameters', { defaultValue: 'Query Parameters' })}</h3>
                  <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div className="p-4 bg-humdb-gray-50 rounded-lg border">
                      <ul className="text-sm space-y-2">
                        <li><span className="font-medium">api_key</span>: required API key</li>
                        <li><span className="font-medium">template_id</span>: number</li>
                        <li><span className="font-medium">submission_id</span>: number</li>
                        <li><span className="font-medium">item_id</span>: number</li>
                        <li><span className="font-medium">item_type</span>: 'indicator' | 'question' | 'document_field'</li>
                        <li><span className="font-medium">country_id</span>: number</li>
                        <li><span className="font-medium">submission_type</span>: 'assigned' | 'public'</li>
                      </ul>
                    </div>
                    <div className="p-4 bg-humdb-gray-50 rounded-lg border">
                      <ul className="text-sm space-y-2">
                        <li><span className="font-medium">period_name</span>: string (e.g. '2023', 'FY2023', 'Q1 2024')</li>
                        <li><span className="font-medium">indicator_bank_id</span>: number</li>
                        <li><span className="font-medium">disagg</span>: boolean ('true' to include disaggregation data; omitted/default excludes)</li>
                        <li><span className="font-medium">page</span>: number (default 1)</li>
                        <li><span className="font-medium">per_page</span>: number (default 20; use 50000 to fetch all)</li>
                      </ul>
                    </div>
                  </div>
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-humdb-navy">{t('apiBuilder.docs.examplesTitle', { defaultValue: 'Examples' })}</h3>
                  <div className="mt-3 space-y-4">
                    <div className="p-4 bg-humdb-gray-50 rounded-lg border">
                      <p className="text-sm font-medium mb-2">{t('apiBuilder.docs.exampleBasic', { defaultValue: 'Basic request (without disaggregation)' })}</p>
                      <pre className="text-xs whitespace-pre-wrap">{`GET ${backendBaseUrl}/api/v1/data?api_key=YOUR_KEY`}</pre>
                    </div>
                    <div className="p-4 bg-humdb-gray-50 rounded-lg border">
                      <p className="text-sm font-medium mb-2">{t('apiBuilder.docs.exampleDisagg', { defaultValue: 'Include disaggregation data' })}</p>
                      <pre className="text-xs whitespace-pre-wrap">{`GET ${backendBaseUrl}/api/v1/data?api_key=YOUR_KEY&disagg=true`}</pre>
                    </div>
                    <div className="p-4 bg-humdb-gray-50 rounded-lg border">
                      <p className="text-sm font-medium mb-2">{t('apiBuilder.docs.exampleFilterPaginate', { defaultValue: 'Filter by template, period, and paginate' })}</p>
                      <pre className="text-xs whitespace-pre-wrap">{`GET ${backendBaseUrl}/api/v1/data?api_key=YOUR_KEY&template_id=21&period_name=2023&page=1&per_page=100`}</pre>
                    </div>
                    <div className="p-4 bg-humdb-gray-50 rounded-lg border">
                      <p className="text-sm font-medium mb-2">{t('apiBuilder.docs.exampleCurlTitle', { defaultValue: 'cURL example' })}</p>
                      <pre className="text-xs whitespace-pre-wrap">{`curl -G "${backendBaseUrl}/api/v1/data" \\
  --data-urlencode "api_key=YOUR_KEY" \\
  --data-urlencode "template_id=21" \\
  --data-urlencode "period_name=2023" \\
  --data-urlencode "per_page=100"`}</pre>
                    </div>
                  </div>
                </div>
                <div>
                  <h3 className="text-lg font-semibold text-humdb-navy">{t('apiBuilder.docs.errorsTitle', { defaultValue: 'Errors' })}</h3>
                  <div className="mt-2 p-3 bg-humdb-gray-50 border border-humdb-gray-200 rounded-lg text-sm text-humdb-gray-700">
                    <ul className="list-disc pl-5 space-y-1">
                      <li>{t('apiBuilder.docs.errors.400', { defaultValue: '400: Invalid parameter or value' })}</li>
                      <li>{t('apiBuilder.docs.errors.401', { defaultValue: '401: Missing or invalid api_key' })}</li>
                      <li>{t('apiBuilder.docs.errors.404', { defaultValue: '404: Resource not found' })}</li>
                      <li>{t('apiBuilder.docs.errors.500', { defaultValue: '500: Server error' })}</li>
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>

          {/* Main Builder Section */}
          <h2 className="scroll-mt-24 text-2xl font-bold text-humdb-navy mb-4" id="builder">{t('apiBuilder.builder.title', { defaultValue: 'Build Endpoint' })}</h2>
          <div className="grid grid-cols-1 xl:grid-cols-3 gap-8">
            {/* Left Column - Parameters */}
            <motion.div variants={fadeInUp} className="xl:col-span-2 space-y-6">
              {/* Parameters Section */}
              <div className="bg-humdb-white rounded-2xl shadow-sm p-6">
                <div className="flex items-center justify-between mb-6">
                  <h3 className="text-xl font-semibold text-humdb-navy">
                    {t('apiBuilder.parameters.title')}
                  </h3>
                  <button
                    onClick={() => {
                      setParameters(prev => {
                        const newParams = { ...prev };
                        Object.keys(newParams).forEach(key => {
                          newParams[key] = { enabled: false, value: '' };
                        });
                        return newParams;
                      });
                    }}
                    className="text-sm text-humdb-red hover:text-humdb-red-dark transition-colors"
                  >
                    {t('apiBuilder.parameters.clearAll', { defaultValue: 'Clear All' })}
                  </button>
                </div>
                <p className="text-humdb-gray-600 mb-6">
                  {t('apiBuilder.parameters.description')}
                </p>

                {isLoadingData ? (
                  <div className="text-center py-8">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-humdb-red mx-auto mb-4"></div>
                    <p className="text-humdb-gray-600 text-sm">{t('apiBuilder.parameters.loadingOptions', { defaultValue: 'Loading parameter options...' })}</p>
                  </div>
                ) : dataError ? (
                  <div className="text-center py-8">
                    <div className="text-red-600 mb-4">
                      <svg className="w-12 h-12 mx-auto mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z" />
                      </svg>
                    </div>
                    <p className="text-red-600 text-sm mb-4">{dataError}</p>
                    <button
                      onClick={fetchData}
                      className="px-4 py-2 bg-humdb-red text-humdb-white rounded-lg hover:bg-humdb-red-dark transition-colors text-sm"
                    >
                      Retry
                    </button>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {Object.entries(parameterDefinitions).map(([key, def]) => (
                      <div key={key} className={`border rounded-lg p-4 transition-all duration-200 ${
                        parameters[key].enabled
                          ? 'border-humdb-red bg-humdb-red bg-opacity-5 shadow-sm'
                          : 'border-humdb-gray-200 hover:border-humdb-gray-300'
                      }`}>
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center space-x-3">
                            <input
                              type="checkbox"
                              id={`enable_${key}`}
                              checked={parameters[key].enabled}
                              onChange={(e) => handleParameterChange(key, 'enabled', e.target.checked)}
                              className="w-4 h-4 text-humdb-red border-humdb-gray-300 rounded focus:ring-humdb-red"
                            />
                            <label htmlFor={`enable_${key}`} className={`font-medium transition-colors ${
                              parameters[key].enabled ? 'text-humdb-red' : 'text-humdb-gray-800'
                            }`}>
                              {t(`apiBuilder.parameters.${key}.label`)}
                            </label>
                          </div>
                          {def.type === 'select' && (
                            <span className="text-xs bg-humdb-gray-100 text-humdb-gray-600 px-2 py-1 rounded">{t('apiBuilder.fieldType.select', { defaultValue: 'Select' })}</span>
                          )}
                          {def.type === 'number' && (
                            <span className="text-xs bg-humdb-gray-100 text-humdb-gray-600 px-2 py-1 rounded">{t('apiBuilder.fieldType.number', { defaultValue: 'Number' })}</span>
                          )}
                          {def.type === 'text' && (
                            <span className="text-xs bg-humdb-gray-100 text-humdb-gray-600 px-2 py-1 rounded">{t('apiBuilder.fieldType.text', { defaultValue: 'Text' })}</span>
                          )}
                        </div>

                        {parameters[key].enabled && (
                          <div className="space-y-2 animate-in slide-in-from-top-2 duration-200">
                            {def.type === 'select' ? (
                              <select
                                value={parameters[key].value}
                                onChange={(e) => handleParameterChange(key, 'value', e.target.value)}
                                className="w-full px-3 py-2 border border-humdb-gray-300 rounded-lg focus:ring-2 focus:ring-humdb-red focus:border-humdb-red text-sm"
                              >
                                <option value="">{t('common.select')}</option>
                                {def.options.map(option => (
                                  <option key={option.value} value={option.value}>
                                    {option.label}
                                  </option>
                                ))}
                              </select>
                            ) : (
                              <input
                                type={def.type}
                                value={parameters[key].value}
                                onChange={(e) => handleParameterChange(key, 'value', e.target.value)}
                                placeholder={def.placeholder}
                                className="w-full px-3 py-2 border border-humdb-gray-300 rounded-lg focus:ring-2 focus:ring-humdb-red focus:border-humdb-red text-sm"
                              />
                            )}
                            <p className="text-xs text-humdb-gray-500">
                              {def.description}
                            </p>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>

                          {/* Quick Start Guide */}
            <div className="bg-gradient-to-r from-humdb-red to-humdb-red-dark text-humdb-white rounded-2xl shadow-sm p-6">
              <h3 className="text-xl font-semibold mb-4">{t('apiBuilder.quickStart.title', { defaultValue: 'Quick Start Guide' })}</h3>
              <div className="space-y-3 text-sm">
                <div className="flex items-start space-x-3">
                  <span className="bg-humdb-white text-humdb-red rounded-full w-6 h-6 flex items-center justify-center text-xs font-bold flex-shrink-0 mt-0.5">1</span>
                  <p>{t('apiBuilder.quickStart.step1', { defaultValue: 'Select the parameters you want to filter by using the checkboxes' })}</p>
                </div>
                <div className="flex items-start space-x-3">
                  <span className="bg-humdb-white text-humdb-red rounded-full w-6 h-6 flex items-center justify-center text-xs font-bold flex-shrink-0 mt-0.5">2</span>
                  <p>{t('apiBuilder.quickStart.step2', { defaultValue: 'Enter values for the selected parameters' })}</p>
                </div>
                <div className="flex items-start space-x-3">
                  <span className="bg-humdb-white text-humdb-red rounded-full w-6 h-6 flex items-center justify-center text-xs font-bold flex-shrink-0 mt-0.5">3</span>
                  <p>{t('apiBuilder.quickStart.step3', { defaultValue: 'Copy the generated URL or test it directly' })}</p>
                </div>
                <div className="flex items-start space-x-3">
                  <span className="bg-humdb-white text-humdb-red rounded-full w-6 h-6 flex items-center justify-center text-xs font-bold flex-shrink-0 mt-0.5">4</span>
                  <p>{t('apiBuilder.quickStart.step4', { defaultValue: 'Use the URL in your applications or scripts' })}</p>
                </div>
              </div>
            </div>

            {/* Example Queries */}
            <div className="bg-humdb-white rounded-2xl shadow-sm p-6">
              <h3 className="text-xl font-semibold text-humdb-navy mb-4">
                {t('apiBuilder.examples.title')}
              </h3>
              <p className="text-humdb-gray-600 mb-4">
                {t('apiBuilder.examples.description')}
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {exampleQueries.map((example, index) => (
                  <button
                    key={index}
                    onClick={() => handleExampleQuery(example.params)}
                    className="text-left p-3 border border-humdb-gray-200 rounded-lg hover:bg-humdb-gray-50 hover:border-humdb-red transition-colors group"
                  >
                    <span className="font-medium text-humdb-gray-800 text-sm group-hover:text-humdb-red transition-colors">{example.name}</span>
                  </button>
                ))}
              </div>
            </div>
            </motion.div>

            {/* Right Column - URL Builder & Response */}
            <motion.div variants={fadeInUp} className="space-y-6">
              {/* Active Parameters Summary */}
              <div className="bg-humdb-white rounded-2xl shadow-sm p-6">
                <h3 className="text-lg font-semibold text-humdb-navy mb-4">{t('apiBuilder.activeParams.title', { defaultValue: 'Active Parameters' })}</h3>
                <div className="space-y-2">
                  {Object.entries(parameters).filter(([key, param]) => param.enabled && param.value !== '').length === 0 ? (
                    <p className="text-sm text-humdb-gray-500 italic">{t('apiBuilder.activeParams.none', { defaultValue: 'No parameters selected' })}</p>
                  ) : (
                    Object.entries(parameters)
                      .filter(([key, param]) => param.enabled && param.value !== '')
                      .map(([key, param]) => {
                        // Get the display value for the parameter
                        let displayValue = param.value;
                        if (key === 'template_id') {
                          const template = templates.find(t => t.id.toString() === param.value);
                          displayValue = template ? template.name : param.value;
                        } else if (key === 'country_id') {
                          const country = countries.find(c => c.id.toString() === param.value);
                          displayValue = country ? country.name : param.value;
                        } else if (key === 'item_type') {
                          const itemTypeMap = {
                            'indicator': 'Indicator',
                            'question': 'Question',
                            'document_field': 'Document Field'
                          };
                          displayValue = itemTypeMap[param.value] || param.value;
                        } else if (key === 'submission_type') {
                          const submissionTypeMap = {
                            'assigned': 'Assigned',
                            'public': 'Public'
                          };
                          displayValue = submissionTypeMap[param.value] || param.value;
                        } else if (key === 'disagg') {
                          const yesNoMap = {
                            'true': t('common.yes'),
                            'false': t('common.no')
                          };
                          displayValue = yesNoMap[param.value] || param.value;
                        }

                        return (
                          <div key={key} className="flex items-center justify-between bg-humdb-gray-50 rounded-lg px-3 py-2">
                            <span className="text-sm font-medium text-humdb-gray-700">
                              {t(`apiBuilder.parameters.${key}.label`)}
                            </span>
                            <span className="text-sm text-humdb-gray-600 bg-white px-2 py-1 rounded border">
                              {displayValue}
                            </span>
                          </div>
                        );
                      })
                  )}
                </div>
              </div>

              {/* Generated URL */}
              <div className="bg-humdb-white rounded-2xl shadow-sm p-6 sticky top-24 md:top-[144px] xl:top-24">
                <h3 className="text-xl font-semibold text-humdb-navy mb-4">
                  {t('apiBuilder.generatedUrl.title')}
                </h3>
                <p className="text-humdb-gray-600 mb-4 text-sm">
                  {t('apiBuilder.generatedUrl.description')}
                </p>

                <div className="space-y-4">
                  <div className="relative">
                    <input
                      type="text"
                      value={generatedUrl}
                      readOnly
                      className="w-full px-4 py-3 bg-humdb-gray-50 border border-humdb-gray-300 rounded-lg font-mono text-xs"
                    />
                  </div>

                  <div className="flex flex-col space-y-2">
                    <button
                      onClick={copyToClipboard}
                      className="w-full px-4 py-2 bg-humdb-red text-humdb-white rounded-lg hover:bg-humdb-red-dark transition-colors text-sm font-medium"
                    >
                      {copyStatus === 'copied' ? t('apiBuilder.generatedUrl.copied') : t('apiBuilder.generatedUrl.copy')}
                    </button>
                    <button
                      onClick={testEndpoint}
                      disabled={isLoading}
                      className="w-full px-4 py-2 bg-humdb-navy text-humdb-white rounded-lg hover:bg-humdb-navy-dark transition-colors disabled:opacity-50 text-sm font-medium"
                    >
                      {isLoading ? t('apiBuilder.generatedUrl.testing') : t('apiBuilder.generatedUrl.test')}
                    </button>
                    <button
                      onClick={handleDownloadExcel}
                      disabled={isDownloading}
                      className="w-full px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors disabled:opacity-50 text-sm font-medium"
                    >
                      {isDownloading ? t('apiBuilder.download.preparingExcel', { defaultValue: 'Preparing Excel…' }) : t('apiBuilder.download.excel', { defaultValue: 'Download as Excel' })}
                    </button>
                  </div>
                </div>
              </div>

              {/* Response Preview */}
              <div className="bg-humdb-white rounded-2xl shadow-sm p-6">
                <h3 className="text-xl font-semibold text-humdb-navy mb-4">
                  {t('apiBuilder.response.title')}
                </h3>

                {isLoading && (
                  <div className="text-center py-8">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-humdb-red mx-auto mb-4"></div>
                    <p className="text-humdb-gray-600 text-sm">{t('apiBuilder.response.loading')}</p>
                  </div>
                )}

                {response && !isLoading && (
                  <div className="space-y-4">
                    <div className="flex items-center space-x-2">
                      <span className={`px-2 py-1 text-xs font-semibold rounded ${
                        response.status >= 400 ? 'bg-red-100 text-red-800' :
                        response.status >= 300 ? 'bg-yellow-100 text-yellow-800' :
                        'bg-green-100 text-green-800'
                      }`}>
                        {t('apiBuilder.response.status', { code: response.status })}
                      </span>
                    </div>

                    {response.error ? (
                      <div className="bg-red-50 border border-red-200 rounded-lg p-4">
                        <p className="text-red-800 text-sm mb-2">{response.error}</p>
                        {response.rawResponse && (
                          <details className="mt-2">
                            <summary className="text-red-600 text-xs cursor-pointer">{t('apiBuilder.response.showRaw', { defaultValue: 'Show raw response' })}</summary>
                            <pre className="text-xs text-red-700 mt-2 whitespace-pre-wrap bg-red-100 p-2 rounded">
                              {response.rawResponse}
                            </pre>
                          </details>
                        )}
                      </div>
                    ) : (
                      <div className="bg-humdb-gray-50 rounded-lg p-4 max-h-96 overflow-auto">
                        <pre className="text-xs text-humdb-gray-800 whitespace-pre-wrap">
                          {JSON.stringify(response.data, null, 2)}
                        </pre>
                      </div>
                    )}
                  </div>
                )}

                {!response && !isLoading && (
                  <div className="text-center py-8 text-humdb-gray-500">
                    <p className="text-sm">{t('apiBuilder.response.noData')}</p>
                  </div>
                )}
              </div>
            </motion.div>
          </div>
        </motion.div>
      </div>
    </>
  );
}
