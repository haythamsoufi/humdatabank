// pages/resources.js
import Head from 'next/head';
import { useState, useEffect } from 'react';
import { useRouter } from 'next/router';
import { getResources } from '../lib/apiService';
import ResourceCard from '../components/resources/ResourceCard';
import { useTranslation } from '../lib/useTranslation';
import { TranslationSafe } from '../components/ClientOnly';

export default function ResourcesPage() {
  const router = useRouter();
  const { t, isLoaded } = useTranslation();

  // State for publications data
  const [publications, setPublications] = useState([]);
  const [publicationsTotalPages, setPublicationsTotalPages] = useState(1);
  const [publicationsCurrentPage, setPublicationsCurrentPage] = useState(1);
  const [publicationsLoading, setPublicationsLoading] = useState(true);

  // State for other resources data
  const [otherResources, setOtherResources] = useState([]);
  const [otherResourcesTotalPages, setOtherResourcesTotalPages] = useState(1);
  const [otherResourcesCurrentPage, setOtherResourcesCurrentPage] = useState(1);
  const [otherResourcesLoading, setOtherResourcesLoading] = useState(true);

  // General state
  const [error, setError] = useState(null);

  // State for search and expandable cards
  const [searchTerm, setSearchTerm] = useState('');
  const [activeCardId, setActiveCardId] = useState(null);

  // State for section collapse/expand
  const [sectionsCollapsed, setSectionsCollapsed] = useState({
    publications: false,
    otherResources: false
  });

  const fetchPublications = async (page = 1, searchQuery = '') => {
    setPublicationsLoading(true);

    try {
      // Get current language from URL or default to 'en'
      const currentLanguage = router.locale || 'en';
      const data = await getResources(page, 12, searchQuery, 'publication', currentLanguage); // 12 items per page
      console.log('Publications API response:', data); // Debug logging

      if (data && typeof data === 'object') {
        const resourcesData = data.resources || [];
        console.log('Processed publications:', resourcesData); // Debug logging

        setPublications(resourcesData);
        setPublicationsTotalPages(data.total_pages || 1);
        setPublicationsCurrentPage(data.current_page || 1);

        // Set first publication as active if we have publications and no active card
        if (resourcesData.length > 0 && !activeCardId) {
          setActiveCardId(resourcesData[0].id);
        }
      } else {
        throw new Error('Invalid response format from API');
      }
    } catch (err) {
      console.error("Failed to fetch publications:", err);
      setError(t('resources.error.loadFailed'));
      setPublications([]);
      setPublicationsTotalPages(1);
      setPublicationsCurrentPage(1);
    } finally {
      setPublicationsLoading(false);
    }
  };

  const fetchOtherResources = async (page = 1, searchQuery = '') => {
    setOtherResourcesLoading(true);

    try {
      // Get current language from URL or default to 'en'
      const currentLanguage = router.locale || 'en';
      const data = await getResources(page, 12, searchQuery, 'other', currentLanguage); // 12 items per page
      console.log('Other resources API response:', data); // Debug logging

      if (data && typeof data === 'object') {
        const resourcesData = data.resources || [];
        console.log('Processed other resources:', resourcesData); // Debug logging

        setOtherResources(resourcesData);
        setOtherResourcesTotalPages(data.total_pages || 1);
        setOtherResourcesCurrentPage(data.current_page || 1);

        // Set first other resource as active if we have no publications and no active card
        if (resourcesData.length > 0 && publications.length === 0 && !activeCardId) {
          setActiveCardId(resourcesData[0].id);
        }
      } else {
        throw new Error('Invalid response format from API');
      }
    } catch (err) {
      console.error("Failed to fetch other resources:", err);
      setError(t('resources.error.loadFailed'));
      setOtherResources([]);
      setOtherResourcesTotalPages(1);
      setOtherResourcesCurrentPage(1);
    } finally {
      setOtherResourcesLoading(false);
    }
  };

  const fetchAllResources = async (page = 1, searchQuery = '') => {
    setError(null);
    const currentLanguage = router.locale || 'en';
    console.log('Fetching resources in language:', currentLanguage);
    await Promise.all([
      fetchPublications(page, searchQuery),
      fetchOtherResources(page, searchQuery)
    ]);
  };

  // Initialize state from URL query parameters and fetch data
  useEffect(() => {
    if (router.isReady) {
      const pageParam = router.query.page ? parseInt(router.query.page, 10) : 1;
      const page = isNaN(pageParam) ? 1 : Math.max(1, pageParam);
      const searchQuery = router.query.search || '';

      setPublicationsCurrentPage(page);
      setOtherResourcesCurrentPage(page);
      setSearchTerm(searchQuery);

      fetchAllResources(page, searchQuery);
    }
  }, [router.isReady, router.query]);

  // Prevent rendering until translations are loaded to avoid hydration mismatches
  if (!isLoaded) {
    return (
      <div className="w-full px-6 sm:px-8 lg:px-12 py-8">
        <Head>
          <title>Resources - NGO Databank</title>
        </Head>
        <div className="text-center py-20">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-ngodb-red mb-4"></div>
          <h1 className="text-3xl font-bold text-ngodb-navy mb-2">
            <TranslationSafe fallback="Loading Resources">
              {t('resources.loading.title')}
            </TranslationSafe>
          </h1>
          <p className="text-ngodb-gray-600">
            <TranslationSafe fallback="Please wait while we fetch the resources...">
              {t('resources.loading.description')}
            </TranslationSafe>
          </p>
        </div>
      </div>
    );
  }

  const handleSearch = (e) => {
    e.preventDefault();
    const encodedSearch = encodeURIComponent(searchTerm || '');
    router.push(`/resources?page=1&search=${encodedSearch}`);
  };

  const handlePublicationsPageChange = (newPage) => {
    if (newPage < 1 || newPage > publicationsTotalPages) {
      console.warn('Invalid page number:', newPage);
      return;
    }
    const encodedSearch = encodeURIComponent(searchTerm || '');
    router.push(`/resources?page=${newPage}&search=${encodedSearch}`);
  };

  const handleOtherResourcesPageChange = (newPage) => {
    if (newPage < 1 || newPage > otherResourcesTotalPages) {
      console.warn('Invalid page number:', newPage);
      return;
    }
    // For now, we'll keep both sections on the same page parameter
    // In the future, you might want separate page parameters for each section
    const encodedSearch = encodeURIComponent(searchTerm || '');
    router.push(`/resources?page=${newPage}&search=${encodedSearch}`);
  };

  const handleCardClick = (resource) => {
    console.log('Card clicked:', resource.title);
    // Toggle the card - if it's already active, deactivate it, otherwise activate it
    setActiveCardId(prevId => prevId === resource.id ? null : resource.id);
  };

  const handleCardExpand = (resourceId) => {
    // This can be used for additional expand logic if needed
    console.log('Card expanding:', resourceId);
  };

  const toggleSection = (sectionName) => {
    setSectionsCollapsed(prev => ({
      ...prev,
      [sectionName]: !prev[sectionName]
    }));
  };

  const isLoading = publicationsLoading || otherResourcesLoading;

  if (error) {
    return (
      <div className="w-full px-6 sm:px-8 lg:px-12 py-8 text-center">
        <Head>
          <title>{`${t('resources.error.title')} - NGO Databank`}</title>
        </Head>
        <h1 className="text-3xl font-bold text-ngodb-red mb-6">{t('resources.error.title')}</h1>
        <p className="text-red-600 bg-red-100 p-4 rounded-md">{error}</p>
        <button onClick={() => router.reload()} className="mt-4 text-ngodb-red hover:underline">
          {t('common.tryAgain')}
        </button>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="w-full px-6 sm:px-8 lg:px-12 py-8">
        <Head>
          <title>{`${t('resources.loading.title')} - NGO Databank`}</title>
        </Head>
        <div className="text-center py-20">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-ngodb-red mb-4"></div>
          <h1 className="text-3xl font-bold text-ngodb-navy mb-2">{t('resources.loading.title')}</h1>
          <p className="text-ngodb-gray-600">{t('resources.loading.description')}</p>
        </div>
      </div>
    );
  }

  return (
    <>
      <Head>
        <title>{`${t('resources.title')} - NGO Databank`}</title>
        <meta name="description" content={t('resources.meta.description')} />
      </Head>

      <div className="bg-ngodb-gray-100 min-h-screen">
        <div className="w-full h-full px-4 sm:px-6 lg:px-12 py-6 sm:py-8 lg:py-10">
          <div className="text-center mb-6 sm:mb-8">
            <h1 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-ngodb-navy mb-3 sm:mb-4">
              {t('resources.hero.title')}
            </h1>
            <p className="text-base sm:text-lg text-ngodb-gray-600 max-w-2xl mx-auto px-4">
              {t('resources.hero.description')}
            </p>
          </div>

                     {/* Search Bar */}
           <form onSubmit={handleSearch} className="mb-6 sm:mb-8 max-w-2xl mx-auto px-4">
             <label htmlFor="resource-search" className="sr-only">{t('resources.search.placeholder')}</label>
             <div className="relative border-2 border-ngodb-gray-300 rounded-lg overflow-hidden shadow-sm focus-within:ring-2 focus-within:ring-ngodb-red focus-within:border-ngodb-red">
               <input
                 id="resource-search"
                 type="text"
                 value={searchTerm}
                 onChange={(e) => setSearchTerm(e.target.value)}
                 placeholder={t('resources.search.placeholder')}
                 className="w-full px-4 sm:px-6 py-3 pr-20 sm:pr-24 text-ngodb-gray-700 focus:outline-none border-none text-base"
               />
               <button
                 type="submit"
                 className="absolute right-0 top-0 h-full bg-ngodb-red hover:bg-ngodb-red-dark text-white font-semibold px-4 sm:px-6 transition-colors duration-150 text-base flex items-center justify-center"
               >
                 {t('resources.search.button')}
               </button>
             </div>
           </form>

          {/* Publications Section */}
          <div className="mb-6 sm:mb-8">
                         <div className="flex items-center mb-4 sm:mb-6 px-4">
                               <h2 className="text-xl sm:text-2xl font-bold text-ngodb-navy mr-3 sm:mr-4">
                  {t('resources.sections.publications')}
                  <span className="ml-3 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs sm:text-sm font-medium bg-ngodb-red-light text-ngodb-red border border-ngodb-red/20">
                    {publicationsLoading ? '...' : publications.length}
                  </span>
                </h2>
               <div className="flex-1 h-px bg-ngodb-gray-300"></div>
               <button
                 onClick={() => toggleSection('publications')}
                 className="ml-4 p-2 text-ngodb-gray-600 hover:text-ngodb-red transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-ngodb-red focus:ring-offset-2 rounded-md"
                 aria-label={sectionsCollapsed.publications ? t('resources.sections.publications.expand') : t('resources.sections.publications.collapse')}
               >
                 {sectionsCollapsed.publications ? (
                   <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                     <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
                   </svg>
                 ) : (
                   <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                     <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 15l7-7 7 7" />
                   </svg>
                 )}
               </button>
             </div>

                         {!sectionsCollapsed.publications && (
              <>
                {publicationsLoading ? (
                  <div className="text-center py-6 sm:py-10 px-4">
                    <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-ngodb-red mb-2"></div>
                    <p className="text-ngodb-gray-600 text-sm sm:text-base">{t('common.loading')}</p>
                  </div>
                ) : publications.length === 0 ? (
                  <p className="text-center text-ngodb-gray-600 text-base sm:text-lg py-6 sm:py-10 px-4">
                    {searchTerm ? t('resources.sections.publications.noResults') : t('resources.sections.publications.none')}
                  </p>
                ) : (
                  <div className="resource-carousel-container">
                    <div className="resource-carousel-stage">
                      {publications.map((resource, index) => (
                        <ResourceCard
                          key={resource.id || `pub-${index}`}
                          resource={resource}
                          isActive={activeCardId === resource.id}
                          onClick={handleCardClick}
                          onExpand={handleCardExpand}
                        />
                      ))}
                    </div>

                    {/* Publications Pagination */}
                    {publicationsTotalPages > 1 && (
                      <nav className="mt-4 sm:mt-6 flex justify-center px-4" aria-label="Publications Pagination">
                        <ul className="inline-flex items-center -space-x-px shadow-sm rounded-md overflow-hidden">
                          {publicationsCurrentPage > 1 && (
                            <li>
                              <button
                                onClick={() => handlePublicationsPageChange(publicationsCurrentPage - 1)}
                                className="px-2 sm:px-3 py-2 text-xs sm:text-sm leading-tight text-ngodb-gray-600 bg-white border border-ngodb-gray-300 hover:bg-ngodb-gray-100 hover:text-ngodb-gray-700 transition-colors duration-150"
                              >
                                Previous
                              </button>
                            </li>
                          )}
                          {Array.from({ length: Math.max(1, publicationsTotalPages) }, (_, i) => i + 1).map((page) => (
                            <li key={page}>
                              <button
                                onClick={() => handlePublicationsPageChange(page)}
                                className={`px-2 sm:px-3 py-2 text-xs sm:text-sm leading-tight border border-ngodb-gray-300 transition-colors duration-150
                                  ${publicationsCurrentPage === page
                                    ? 'text-ngodb-red bg-ngodb-red-light border-ngodb-red hover:bg-ngodb-red-light font-semibold z-10'
                                    : 'text-ngodb-gray-600 bg-white hover:bg-ngodb-gray-100 hover:text-ngodb-gray-700'
                                  }`}
                              >
                                {page}
                              </button>
                            </li>
                          ))}
                          {publicationsCurrentPage < publicationsTotalPages && (
                            <li>
                              <button
                                onClick={() => handlePublicationsPageChange(publicationsCurrentPage + 1)}
                                className="px-2 sm:px-3 py-2 text-xs sm:text-sm leading-tight text-ngodb-gray-600 bg-white border border-ngodb-gray-300 hover:bg-ngodb-gray-100 hover:text-ngodb-gray-700 transition-colors duration-150"
                              >
                                {t('resources.pagination.next')}
                              </button>
                            </li>
                          )}
                        </ul>
                      </nav>
                    )}
                  </div>
                )}
              </>
            )}
          </div>

          {/* Other Resources Section */}
          <div className="mb-6 sm:mb-8">
                         <div className="flex items-center mb-4 sm:mb-6 px-4">
                               <h2 className="text-xl sm:text-2xl font-bold text-ngodb-navy mr-3 sm:mr-4">
                  {t('resources.sections.otherResources')}
                  <span className="ml-3 inline-flex items-center px-2.5 py-0.5 rounded-full text-xs sm:text-sm font-medium bg-ngodb-red-light text-ngodb-red border border-ngodb-red/20">
                    {otherResourcesLoading ? '...' : otherResources.length}
                  </span>
                </h2>
               <div className="flex-1 h-px bg-ngodb-gray-300"></div>
               <button
                 onClick={() => toggleSection('otherResources')}
                 className="ml-4 p-2 text-ngodb-gray-600 hover:text-ngodb-red transition-colors duration-150 focus:outline-none focus:ring-2 focus:ring-ngodb-red focus:ring-offset-2 rounded-md"
                 aria-label={sectionsCollapsed.otherResources ? t('resources.sections.otherResources.expand') : t('resources.sections.otherResources.collapse')}
               >
                 {sectionsCollapsed.otherResources ? (
                   <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                     <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
                   </svg>
                 ) : (
                   <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                     <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 15l7-7 7 7" />
                   </svg>
                 )}
               </button>
             </div>

                         {!sectionsCollapsed.otherResources && (
              <>
                {otherResourcesLoading ? (
                  <div className="text-center py-6 sm:py-10 px-4">
                    <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-ngodb-red mb-2"></div>
                    <p className="text-ngodb-gray-600 text-sm sm:text-base">{t('resources.sections.otherResources.loading')}</p>
                  </div>
                ) : otherResources.length === 0 ? (
                  <div className="bg-white rounded-lg border-2 border-dashed border-ngodb-gray-300 p-4 sm:p-8 text-center mx-4">
                    <svg className="w-8 h-8 sm:w-12 sm:h-12 text-ngodb-gray-400 mx-auto mb-3 sm:mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6" />
                    </svg>
                    <h3 className="text-base sm:text-lg font-medium text-ngodb-gray-600 mb-2">
                      {searchTerm ? t('resources.sections.otherResources.noResults') : t('resources.sections.otherResources.none')}
                    </h3>
                    <p className="text-ngodb-gray-500 text-sm sm:text-base">
                      {searchTerm ? t('resources.sections.otherResources.tryAdjusting') : t('resources.sections.otherResources.comingSoon')}
                    </p>
                  </div>
                ) : (
                  <div className="resource-carousel-container">
                    <div className="resource-carousel-stage">
                      {otherResources.map((resource, index) => (
                        <ResourceCard
                          key={resource.id || `other-${index}`}
                          resource={resource}
                          isActive={activeCardId === resource.id}
                          onClick={handleCardClick}
                          onExpand={handleCardExpand}
                        />
                      ))}
                    </div>

                    {/* Other Resources Pagination */}
                    {otherResourcesTotalPages > 1 && (
                      <nav className="mt-4 sm:mt-6 flex justify-center px-4" aria-label="Other Resources Pagination">
                        <ul className="inline-flex items-center -space-x-px shadow-sm rounded-md overflow-hidden">
                          {otherResourcesCurrentPage > 1 && (
                            <li>
                              <button
                                onClick={() => handleOtherResourcesPageChange(otherResourcesCurrentPage - 1)}
                                className="px-2 sm:px-3 py-2 text-xs sm:text-sm leading-tight text-ngodb-gray-600 bg-white border border-ngodb-gray-300 hover:bg-ngodb-gray-100 hover:text-ngodb-gray-700 transition-colors duration-150"
                              >
                                Previous
                              </button>
                            </li>
                          )}
                          {Array.from({ length: Math.max(1, otherResourcesTotalPages) }, (_, i) => i + 1).map((page) => (
                            <li key={page}>
                              <button
                                onClick={() => handleOtherResourcesPageChange(page)}
                                className={`px-2 sm:px-3 py-2 text-xs sm:text-sm leading-tight border border-ngodb-gray-300 transition-colors duration-150
                                  ${otherResourcesCurrentPage === page
                                    ? 'text-ngodb-red bg-ngodb-red-light border-ngodb-red hover:bg-ngodb-red-light font-semibold z-10'
                                    : 'text-ngodb-gray-600 bg-white hover:bg-ngodb-gray-100 hover:text-ngodb-gray-700'
                                  }`}
                              >
                                {page}
                              </button>
                            </li>
                          ))}
                          {otherResourcesCurrentPage < otherResourcesTotalPages && (
                            <li>
                              <button
                                onClick={() => handleOtherResourcesPageChange(otherResourcesCurrentPage + 1)}
                                className="px-2 sm:px-3 py-2 text-xs sm:text-sm leading-tight text-ngodb-gray-600 bg-white border border-ngodb-gray-300 hover:bg-ngodb-gray-100 hover:text-ngodb-gray-700 transition-colors duration-150"
                              >
                                {t('resources.pagination.next')}
                              </button>
                            </li>
                          )}
                        </ul>
                  </nav>
                )}
              </div>
            )}
          </>
        )}
          </div>


        </div>

        <style jsx>{`
          .resource-carousel-container {
            padding: 20px 0;
            overflow: visible; /* Changed from hidden to allow dropdowns */
            position: relative;
          }

          /* Smooth transitions for section collapse/expand */
          .section-content {
            transition: all 0.3s ease-in-out;
            overflow: hidden;
          }

          .resource-carousel-stage {
            margin: 15px 0;
            display: flex;
            overflow-x: auto;
            overflow-y: visible;
            padding: 20px 0 40px; /* Reduced bottom padding for dropdowns */
            scroll-behavior: smooth;
            -webkit-overflow-scrolling: touch;
            position: relative;
            z-index: 1; /* Base z-index for carousel */
          }

          /* Custom scrollbar */
          .resource-carousel-stage::-webkit-scrollbar {
            height: 8px;
          }

          .resource-carousel-stage::-webkit-scrollbar-track {
            background: #f1f1f1;
            border-radius: 4px;
          }

          .resource-carousel-stage::-webkit-scrollbar-thumb {
            background: #dc2626;
            border-radius: 4px;
          }

          .resource-carousel-stage::-webkit-scrollbar-thumb:hover {
            background: #991b1b;
          }

          /* Responsive adjustments */
          @media (min-width: 992px) and (max-width: 1199px) {
            .resource-carousel-container {
              padding: 20px 0;
            }
            .resource-carousel-stage {
              padding: 20px 0 30px; /* Reduced space for dropdowns */
            }
          }

          @media (min-width: 768px) and (max-width: 991px) {
            .resource-carousel-container {
              padding: 20px 0;
            }
            .resource-carousel-stage {
              padding: 20px 0 30px; /* Reduced space for dropdowns */
            }
          }

          @media (max-width: 767px) {
            .resource-carousel-container {
              padding: 20px 0;
            }
            .resource-carousel-stage {
              padding: 20px 0 30px; /* Reduced space for dropdowns */
            }
          }

                     /* Mobile-first responsive design */
           @media (max-width: 767px) {
             .resource-carousel-stage {
               flex-direction: column;
               overflow-x: visible;
               overflow-y: visible;
               padding: 20px 0 20px;
               gap: 20px;
             }

             .resource-carousel-container {
               padding: 20px 0;
             }

             /* Make cards take full width on mobile */
             .resource-carousel-stage > * {
               width: 100%;
               max-width: none;
               margin: 0;
             }
           }

          /* Tablet adjustments */
          @media (min-width: 768px) and (max-width: 1023px) {
            .resource-carousel-stage {
              flex-wrap: wrap;
              gap: 20px;
              justify-content: center;
              padding: 20px 0 30px;
            }
          }

                     /* Small mobile devices */
           @media (max-width: 480px) {
             .resource-carousel-stage {
               gap: 16px;
               padding: 16px 0 20px;
             }

             .resource-carousel-container {
               padding: 16px 0;
             }

             /* Ensure cards take full width on small mobile */
             .resource-carousel-stage > * {
               width: 100%;
               max-width: none;
               margin: 0;
             }
           }
        `}</style>
      </div>
    </>
  );
}

// Ensure SSR to avoid build-time prerender errors
export async function getServerSideProps() {
  return { props: {} };
}
