import Head from 'next/head';
import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { useTranslation } from '../lib/useTranslation';

export default function DataHealthPage() {
  const { t } = useTranslation();
  const [dataStoreHealth, setDataStoreHealth] = useState(null);
  const [backendHealth, setBackendHealth] = useState(null);
  const [isLoading, setIsLoading] = useState(true);
  const [lastRefresh, setLastRefresh] = useState(null);

  const fetchHealth = async () => {
    setIsLoading(true);
    try {
      // Fetch data store health
      const dataStoreResponse = await fetch('/api/data/health');
      const dataStoreData = await dataStoreResponse.json();
      setDataStoreHealth(dataStoreData);

      // Fetch backend health
      const backendResponse = await fetch('/api/health');
      const backendData = await backendResponse.json();
      setBackendHealth(backendData);

      setLastRefresh(new Date());
    } catch (error) {
      console.error('Error fetching health data:', error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchHealth();
    // Auto-refresh every 30 seconds
    const interval = setInterval(fetchHealth, 30000);
    return () => clearInterval(interval);
  }, []);

  const formatBytes = (bytes) => {
    if (!bytes || bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  const formatTime = (minutes) => {
    if (!minutes && minutes !== 0) return t('dataHealth.time.unknown');
    if (minutes < 60) return t('dataHealth.time.minutesAgo', { minutes: Math.round(minutes) });
    const hours = Math.floor(minutes / 60);
    const days = Math.floor(hours / 24);
    if (days > 0) return t(days > 1 ? 'dataHealth.time.daysAgoPlural' : 'dataHealth.time.daysAgo', { days });
    return t(hours > 1 ? 'dataHealth.time.hoursAgoPlural' : 'dataHealth.time.hoursAgo', { hours });
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'healthy':
        return 'bg-green-500';
      case 'degraded':
        return 'bg-yellow-500';
      case 'unhealthy':
        return 'bg-red-500';
      default:
        return 'bg-gray-500';
    }
  };

  const getStatusBadge = (status) => {
    const colors = {
      healthy: 'bg-green-100 text-green-800 border-green-200',
      degraded: 'bg-yellow-100 text-yellow-800 border-yellow-200',
      unhealthy: 'bg-red-100 text-red-800 border-red-200',
    };
    return colors[status] || 'bg-gray-100 text-gray-800 border-gray-200';
  };

  return (
    <>
      <Head>
        <title>{t('dataHealth.metaTitle')}</title>
      </Head>

      <div className="min-h-screen bg-gray-50 py-8 px-4 sm:px-6 lg:px-8">
        <div className="max-w-7xl mx-auto">
          {/* Header */}
          <div className="mb-8">
            <div className="flex items-center justify-between">
              <div>
                <h1 className="text-3xl font-bold text-gray-900">{t('dataHealth.title')}</h1>
                <p className="mt-2 text-sm text-gray-600">
                  {t('dataHealth.description')}
                </p>
              </div>
              <div className="flex items-center gap-4">
                {lastRefresh && (
                  <span className="text-sm text-gray-500">
                    {t('dataHealth.lastUpdated')} {lastRefresh.toLocaleTimeString()}
                  </span>
                )}
                <button
                  onClick={fetchHealth}
                  disabled={isLoading}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {isLoading ? t('common.loading') : t('dataHealth.refresh')}
                </button>
              </div>
            </div>
          </div>

          {isLoading && !dataStoreHealth && !backendHealth ? (
            <div className="text-center py-12">
              <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
              <p className="mt-4 text-gray-600">{t('common.loading')}</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {/* Data Store Health */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                className="bg-white rounded-lg shadow-md p-6"
              >
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-xl font-semibold text-gray-900">{t('dataHealth.dataStore.title')}</h2>
                  {dataStoreHealth && (
                    <span
                      className={`px-3 py-1 rounded-full text-sm font-medium border ${getStatusBadge(
                        dataStoreHealth.status
                      )}`}
                    >
                      {dataStoreHealth.status?.toUpperCase() || t('dataHealth.dataStore.unknown')}
                    </span>
                  )}
                </div>

                {dataStoreHealth ? (
                  <div className="space-y-4">
                    {/* Status Indicator */}
                    <div className="flex items-center gap-2">
                      <div
                        className={`w-3 h-3 rounded-full ${getStatusColor(dataStoreHealth.status)}`}
                      ></div>
                      <span className="text-sm text-gray-600">
                        {t('dataHealth.dataStore.status')} <span className="font-medium">{dataStoreHealth.status}</span>
                      </span>
                    </div>

                    {/* Last Sync */}
                    {dataStoreHealth.lastSync && (
                      <div>
                        <p className="text-sm text-gray-600">{t('dataHealth.dataStore.lastSync')}</p>
                        <p className="text-lg font-semibold text-gray-900">
                          {new Date(dataStoreHealth.lastSync).toLocaleString()}
                        </p>
                        {dataStoreHealth.dataAge !== null && (
                          <p className="text-xs text-gray-500 mt-1">
                            {formatTime(dataStoreHealth.dataAge)}
                          </p>
                        )}
                      </div>
                    )}

                    {/* File Sizes */}
                    {dataStoreHealth.fileSizes && Object.keys(dataStoreHealth.fileSizes).length > 0 && (
                      <div>
                        <p className="text-sm font-medium text-gray-700 mb-2">{t('dataHealth.dataStore.fileSizes')}</p>
                        <div className="space-y-1">
                          {Object.entries(dataStoreHealth.fileSizes).map(([key, size]) => (
                            <div key={key} className="flex justify-between text-sm">
                              <span className="text-gray-600 capitalize">
                                {key.replace(/([A-Z])/g, ' $1').trim()}:
                              </span>
                              <span className="font-medium text-gray-900">{formatBytes(size)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Metadata */}
                    {dataStoreHealth.metadata && (
                      <div>
                        <p className="text-sm font-medium text-gray-700 mb-2">{t('dataHealth.dataStore.metadata')}</p>
                        <div className="bg-gray-50 rounded p-3 text-xs font-mono text-gray-600 overflow-x-auto">
                          <pre>{JSON.stringify(dataStoreHealth.metadata, null, 2)}</pre>
                        </div>
                      </div>
                    )}

                    {/* Issues */}
                    {dataStoreHealth.issues && dataStoreHealth.issues.length > 0 && (
                      <div>
                        <p className="text-sm font-medium text-red-700 mb-2">{t('dataHealth.dataStore.issues')}</p>
                        <ul className="list-disc list-inside space-y-1">
                          {dataStoreHealth.issues.map((issue, idx) => (
                            <li key={idx} className="text-sm text-red-600">
                              {issue}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {(!dataStoreHealth.issues || dataStoreHealth.issues.length === 0) && (
                      <div className="text-sm text-green-600">{t('dataHealth.dataStore.noIssues')}</div>
                    )}
                  </div>
                ) : (
                  <p className="text-gray-500">{t('dataHealth.dataStore.noData')}</p>
                )}
              </motion.div>

              {/* Backoffice Health */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 }}
                className="bg-white rounded-lg shadow-md p-6"
              >
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-xl font-semibold text-gray-900">{t('dataHealth.backoffice.title')}</h2>
                  {backendHealth && (
                    <span
                      className={`px-3 py-1 rounded-full text-sm font-medium border ${getStatusBadge(
                        backendHealth.status
                      )}`}
                    >
                      {backendHealth.status?.toUpperCase() || t('dataHealth.dataStore.unknown')}
                    </span>
                  )}
                </div>

                {backendHealth ? (
                  <div className="space-y-4">
                    {/* Status Indicator */}
                    <div className="flex items-center gap-2">
                      <div
                        className={`w-3 h-3 rounded-full ${getStatusColor(backendHealth.status)}`}
                      ></div>
                      <span className="text-sm text-gray-600">
                        {t('dataHealth.backoffice.status')} <span className="font-medium">{backendHealth.status}</span>
                      </span>
                    </div>

                    {/* Backoffice Connection */}
                    <div>
                      <p className="text-sm text-gray-600">{t('dataHealth.backoffice.connection')}</p>
                      <p className="text-lg font-semibold text-gray-900">
                        {backendHealth.backend || t('dataHealth.backoffice.unknown')}
                      </p>
                    </div>

                    {/* Timestamp */}
                    {backendHealth.timestamp && (
                      <div>
                        <p className="text-sm text-gray-600">{t('dataHealth.backoffice.lastCheck')}</p>
                        <p className="text-sm font-medium text-gray-900">
                          {new Date(backendHealth.timestamp).toLocaleString()}
                        </p>
                      </div>
                    )}

                    {/* Data Info */}
                    {backendHealth.data && (
                      <div>
                        <p className="text-sm font-medium text-gray-700 mb-2">{t('dataHealth.backoffice.responseData')}</p>
                        <div className="bg-gray-50 rounded p-3 text-xs">
                          {Object.entries(backendHealth.data).map(([key, value]) => (
                            <div key={key} className="flex justify-between mb-1">
                              <span className="text-gray-600 capitalize">
                                {key.replace(/_/g, ' ')}:
                              </span>
                              <span className="font-medium text-gray-900">{String(value)}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Error */}
                    {backendHealth.error && (
                      <div>
                        <p className="text-sm font-medium text-red-700 mb-2">{t('dataHealth.backoffice.error')}</p>
                        <p className="text-sm text-red-600">{backendHealth.error}</p>
                      </div>
                    )}

                    {!backendHealth.error && (
                      <div className="text-sm text-green-600">{t('dataHealth.backoffice.reachable')}</div>
                    )}
                  </div>
                ) : (
                  <p className="text-gray-500">{t('dataHealth.backoffice.noData')}</p>
                )}
              </motion.div>

              {/* Configuration Info */}
              <motion.div
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2 }}
                className="bg-white rounded-lg shadow-md p-6 lg:col-span-2"
              >
                <h2 className="text-xl font-semibold text-gray-900 mb-4">{t('dataHealth.configuration.title')}</h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <p className="text-sm text-gray-600">{t('dataHealth.configuration.localStore')}</p>
                    <p className="text-sm font-medium text-gray-900">
                      {typeof window !== 'undefined'
                        ? t('dataHealth.configuration.clientSide')
                        : t('dataHealth.configuration.serverSide')}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm text-gray-600">{t('dataHealth.configuration.environment')}</p>
                    <p className="text-sm font-medium text-gray-900">
                      {process.env.NODE_ENV || 'development'}
                    </p>
                  </div>
                </div>
              </motion.div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
