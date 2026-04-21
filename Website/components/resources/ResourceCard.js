// Website/components/resources/ResourceCard.js
import { useState, useEffect, useRef } from 'react';

export default function ResourceCard({ resource, isActive, onClick, onExpand }) {
  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageError, setImageError] = useState(false);
  const [selectedDownloadLanguage, setSelectedDownloadLanguage] = useState(resource.language || 'en');
  const [isLanguageDropdownOpen, setIsLanguageDropdownOpen] = useState(false);
  const dropdownButtonRef = useRef(null);

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    try {
      return new Date(dateString).toLocaleDateString('en-GB', {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
      });
    } catch (e) {
      return dateString;
    }
  };

  const handleCardClick = () => {
    onClick(resource);
    if (onExpand) {
      onExpand(resource.id);
    }
  };

  const handleDownload = (e) => {
    e.stopPropagation(); // Prevent card expansion when download is clicked
    if (resource.download_url) {
      // Modify the download URL to include the selected language
      // This assumes the backend can handle language parameters
      const downloadUrl = new URL(resource.download_url, window.location.origin);
      if (selectedDownloadLanguage !== resource.language) {
        downloadUrl.searchParams.set('lang', selectedDownloadLanguage);
      }
      window.open(downloadUrl.toString(), '_blank', 'noopener noreferrer');
    }
  };

  const handleLanguageSelect = (language) => {
    setSelectedDownloadLanguage(language);
    setIsLanguageDropdownOpen(false);
  };

  const toggleLanguageDropdown = (e) => {
    e.stopPropagation();
    setIsLanguageDropdownOpen(!isLanguageDropdownOpen);
  };

  // Calculate dropdown position for fixed positioning
  const getDropdownStyle = () => {
    if (!isLanguageDropdownOpen || !dropdownButtonRef.current) {
      return { display: 'none' };
    }

    const rect = dropdownButtonRef.current.getBoundingClientRect();
    return {
      position: 'fixed',
      top: rect.bottom + 4,
      right: window.innerWidth - rect.right, // Align to right edge of button
      zIndex: 99999,
      display: 'block',
      minWidth: '80px'
    };
  };

  // Debug logging
  useEffect(() => {
    if (typeof window !== 'undefined') {
      console.log('ResourceCard render:', {
        id: resource.id,
        title: resource.title,
        language: resource.language,
        available_languages: resource.available_languages,
        has_thumbnail: resource.has_thumbnail,
        has_download: !!resource.download_url,
        thumbnail_url: resource.thumbnail_url,
        isActive
      });
    }
  }, [resource, isActive]);

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (isLanguageDropdownOpen && !event.target.closest('.language-selector')) {
        setIsLanguageDropdownOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isLanguageDropdownOpen]);

  // Reset selected language when resource changes
  useEffect(() => {
    setSelectedDownloadLanguage(resource.language || 'en');
  }, [resource.language]);

  return (
    <>
      <div
        className={`resource-card-item ${isActive ? 'active' : ''}`}
        onClick={handleCardClick}
        style={{
          backgroundImage: resource.has_thumbnail && !imageError
            ? `url(${resource.thumbnail_url})`
            : 'none'
        }}
      >
        {/* Fallback content when no image or image fails */}
        {(!resource.thumbnail_url || imageError) && (
          <div className="fallback-background">
            <svg className="w-16 h-16 text-white opacity-30" fill="currentColor" viewBox="0 0 24 24">
              <path d="M16 4h-2V2h-4v2H8c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zm0 12H8V6h8v10zM4 22h16V8h2v14c0 1.1-.9 2-2 2H2c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2h2v16z"></path>
            </svg>
          </div>
        )}

        {/* Hidden image for loading detection */}
        {resource.has_thumbnail && (
          <img
            src={resource.thumbnail_url}
            alt=""
            style={{ display: 'none' }}
            onLoad={() => {
              setImageLoaded(true);
              setImageError(false);
            }}
            onError={() => {
              setImageError(true);
              setImageLoaded(false);
            }}
          />
        )}

        <div className="item-desc">
          <h3>{resource.title || resource.default_title || 'Untitled Resource'}</h3>
          <div className="resource-meta">
            {resource.publication_date && (
              <p className="publication-date">
                Published: {formatDate(resource.publication_date)}
              </p>
            )}
            {(resource.description || resource.default_description) && (
              <p className="description">
                {resource.description || resource.default_description}
              </p>
            )}



            {/* Download section - button and language dropdown */}
            {isActive && resource.download_url && (
              <div className="download-section">
                <button
                  onClick={handleDownload}
                  className="download-btn"
                >
                  <svg className="w-4 h-4 mr-2" fill="currentColor" viewBox="0 0 20 20">
                    <path fillRule="evenodd" d="M3 17a1 1 0 011-1h12a1 1 0 110 2H4a1 1 0 01-1-1zm3.293-7.707a1 1 0 011.414 0L9 10.586V3a1 1 0 112 0v7.586l1.293-1.293a1 1 0 111.414 1.414l-3 3a1 1 0 01-1.414 0l-3-3a1 1 0 010-1.414z" clipRule="evenodd"></path>
                  </svg>
                  Download in {selectedDownloadLanguage?.toUpperCase() || 'EN'}
                </button>

                {/* Language selector dropdown */}
                {resource.available_languages && resource.available_languages.length > 1 && (
                  <div className="language-selector">
                    <button
                      ref={dropdownButtonRef}
                      onClick={toggleLanguageDropdown}
                      className="language-dropdown-btn"
                      title="Select download language"
                    >
                      <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M10 18a8 8 0 100-16 8 8 0 000 16zM4.332 8.027a6.012 6.012 0 011.912-2.706C6.512 5.73 6.974 6 7.5 6A1.5 1.5 0 019 7.5V8a2 2 0 004 0 2 2 0 011.523-1.943A5.977 5.977 0 0116 10c0 .34-.028.675-.083 1H15a2 2 0 00-2 2v2.197A5.973 5.973 0 0110 16v-2a2 2 0 00-2-2 2 2 0 01-2-2 2 2 0 00-1.668-1.973z" clipRule="evenodd"></path>
                      </svg>
                      <svg className="w-3 h-3 ml-1" fill="currentColor" viewBox="0 0 20 20">
                        <path fillRule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clipRule="evenodd"></path>
                      </svg>
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>

        <style jsx global>{`
          .resource-card-item {
            margin: 0 15px 60px;
            width: 320px;
            height: 400px;
            display: flex;
            align-items: flex-end;
            background: #343434 no-repeat center center / cover;
            border-radius: 16px;
            overflow: hidden;
            position: relative;
            transition: all 0.4s ease-in-out;
            cursor: pointer;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
          }

          .resource-card-item:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(0, 0, 0, 0.15);
          }

          .resource-card-item.active {
            width: 500px;
            box-shadow: 12px 40px 40px rgba(0, 0, 0, 0.25);
            overflow: visible; /* Allow dropdown to show outside */
            z-index: 100; /* Ensure the active card is above others */
          }

          .resource-card-item:after {
            content: "";
            display: block;
            position: absolute;
            height: 100%;
            width: 100%;
            left: 0;
            top: 0;
            background-image: linear-gradient(rgba(0, 0, 0, 0), rgba(0, 0, 0, 0.8));
          }

          .fallback-background {
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: linear-gradient(135deg, #dc2626 0%, #991b1b 100%);
            display: flex;
            align-items: center;
            justify-content: center;
          }

                            .item-desc {
             padding: 0 24px 12px;
             color: #fff;
             position: relative;
             z-index: 1;
             overflow: hidden;
             transform: translateY(calc(100% - 120px));
             transition: all 0.4s ease-in-out;
             width: 100%;
           }

           .resource-card-item.active .item-desc {
             transform: none;
           }

                   .item-desc h3 {
             margin: 0 0 10px;
             font-size: 1.75rem;
             line-height: 1.4;
             font-weight: 700;
             color: #fff;
             text-shadow: 0 2px 8px rgba(0, 0, 0, 0.8), 0 1px 3px rgba(0, 0, 0, 0.9); /* Dark glow for readability */
           }

          .resource-meta {
            opacity: 0;
            transform: translateY(32px);
            transition: all 0.4s ease-in-out 0.2s;
          }

          .resource-card-item.active .resource-meta {
            opacity: 1;
            transform: translateY(0);
          }

          .publication-date {
            font-size: 0.875rem;
            color: #e5e7eb;
            margin-bottom: 8px;
          }

                   .description {
             font-size: 0.875rem;
             line-height: 1.5;
             color: #f3f4f6;
             margin-bottom: 16px;
             max-height: 100px;
             overflow-y: auto;
           }

           .resource-card-item:not(.active) .description {
             display: -webkit-box;
             -webkit-line-clamp: 2;
             -webkit-box-orient: vertical;
             overflow: hidden;
             max-height: 2.6em;
           }

          .download-btn {
            display: inline-flex;
            align-items: center;
            background: #dc2626;
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 0.875rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease-in-out;
            margin-right: 8px;
          }

          .download-btn:hover {
            background: #991b1b;
            transform: translateY(-1px);
            box-shadow: 0 4px 12px rgba(220, 38, 38, 0.4);
          }

          .download-section {
            display: flex;
            align-items: center;
            margin-top: 8px;
            position: relative;
            z-index: 200; /* Higher z-index for download section */
          }

          .language-selector {
            position: relative;
            z-index: 300; /* Even higher z-index for the selector */
          }

          .language-dropdown-btn {
            display: inline-flex;
            align-items: center;
            background: rgba(255, 255, 255, 0.1);
            color: white;
            border: 1px solid rgba(255, 255, 255, 0.2);
            padding: 8px 10px;
            border-radius: 6px;
            font-size: 0.875rem;
            cursor: pointer;
            transition: all 0.2s ease-in-out;
            backdrop-filter: blur(10px);
            position: relative;
            z-index: 300;
          }

          .language-dropdown-btn:hover {
            background: rgba(255, 255, 255, 0.15);
            border-color: rgba(255, 255, 255, 0.3);
          }


          /* Responsive Design */
          @media (min-width: 992px) and (max-width: 1199px) {
            .resource-card-item {
              margin: 0 12px 60px;
              width: 260px;
              height: 360px;
            }
            .resource-card-item.active {
              width: 400px;
            }
                       .item-desc {
                 transform: translateY(calc(100% - 110px));
               }
              .item-desc h3 {
                font-size: 1.5rem;
                line-height: 1.4;
              }
            }

            @media (min-width: 768px) and (max-width: 991px) {
              .resource-card-item {
                margin: 0 12px 60px;
                width: 240px;
                height: 330px;
              }
              .resource-card-item.active {
                width: 360px;
              }
                       .item-desc {
                 transform: translateY(calc(100% - 100px));
               }
              .item-desc h3 {
                font-size: 1.5rem;
                line-height: 1.4;
              }
            }

            @media (max-width: 767px) {
              .resource-card-item {
                margin: 0 10px 40px;
                width: 200px;
                height: 280px;
              }
              .resource-card-item.active {
                width: 270px;
                box-shadow: 6px 10px 10px rgba(0, 0, 0, 0.25);
              }
                       .item-desc {
                 padding: 0 14px 5px;
                 transform: translateY(calc(100% - 90px));
               }
              .item-desc h3 {
                font-size: 1.25rem;
                line-height: 1.4;
              }
            }

          .global-language-dropdown {
            background: rgba(0, 0, 0, 0.95) !important;
            backdrop-filter: blur(20px);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 6px;
            padding: 4px 0;
            min-width: 80px;
            box-shadow: 0 10px 25px rgba(0, 0, 0, 0.5);
            pointer-events: auto;
          }
        `}</style>
      </div>

      {/* Render dropdown outside styled-jsx scope with fixed positioning */}
      {isLanguageDropdownOpen && resource.available_languages && resource.available_languages.length > 1 && (
        <div
          style={getDropdownStyle()}
          className="global-language-dropdown"
        >
          {resource.available_languages.map((lang) => (
            <button
              key={lang}
              onClick={() => handleLanguageSelect(lang)}
              className={`language-option ${selectedDownloadLanguage === lang ? 'selected' : ''}`}
              style={{
                display: 'block',
                width: '100%',
                background: 'none',
                border: 'none',
                color: 'white',
                padding: '8px 12px',
                fontSize: '0.875rem',
                cursor: 'pointer',
                transition: 'all 0.2s ease-in-out',
                textAlign: 'left',
                backgroundColor: selectedDownloadLanguage === lang ? 'rgba(220, 38, 38, 0.5)' : 'transparent',
                fontWeight: selectedDownloadLanguage === lang ? '600' : 'normal'
              }}
              onMouseEnter={(e) => {
                if (selectedDownloadLanguage !== lang) {
                  e.target.style.backgroundColor = 'rgba(220, 38, 38, 0.3)';
                }
              }}
              onMouseLeave={(e) => {
                if (selectedDownloadLanguage !== lang) {
                  e.target.style.backgroundColor = 'transparent';
                }
              }}
            >
              {lang.toUpperCase()}
            </button>
          ))}
        </div>
      )}


    </>
  );
}
