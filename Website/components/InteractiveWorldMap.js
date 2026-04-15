import React, { useEffect, useMemo, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import { MapSafe } from './ClientOnly';
import CountryMapboxMap from './CountryMapboxMap';
import { useTranslation } from '../lib/useTranslation';
import { getCountriesList } from '../lib/apiService';

// Dynamically import Leaflet to avoid SSR issues
const InteractiveWorldMap = ({
  selectedIndicator,
  indicatorName,
  indicatorData,
  flowLines = [],
  internationalIndicatorType = 'total-funding',
  internationalIndicatorUnit = 'USD',
  visualizationType = 'choropleth',
  onCountryClick,
  globalTotal,
  isLoadingData,
  onCountryHover,
  onCountryLeave,
  hoveredCountry,
  hoveredValue,
  onVisualizationTypeChange,
  yearTimeline = null,
  regionName = null,
  availableYears = [],
  selectedYear = null,
  onYearChange = null,
  selectedRegion = 'global',
  scopeType = 'global',
  scopeCountryIso2 = null,
  scopeCountryIso3 = null
}) => {
  const hashIndicatorData = (data) => {
    // Stable hash to prevent unnecessary chart rebuilds when `indicatorData` object identity changes.
    // Note: keys are sorted for determinism.
    if (!data || typeof data !== 'object') return '0:0';
    const keys = Object.keys(data).sort();
    let h = 2166136261; // FNV-1a 32-bit offset basis
    const fnv1a = (str) => {
      for (let i = 0; i < str.length; i++) {
        h ^= str.charCodeAt(i);
        // h *= 16777619 (with overflow)
        h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
      }
    };
    for (const k of keys) {
      const v = data[k];
      const num = typeof v === 'object' && v ? Number(v.value) : Number(v);
      fnv1a(String(k));
      fnv1a(':');
      fnv1a(String(Number.isFinite(num) ? num : 'NaN'));
      fnv1a(';');
    }
    return `${keys.length}:${h.toString(16)}`;
  };

  // Local-first geoBoundaries loader:
  // - Prefer pre-downloaded files served from Next.js `public/` at `/geoboundaries/{ISO3}/{ADM}.geojson`
  // - Fallback to `/api/geoboundaries` for countries/levels not bundled
  const fetchGeoBoundaries = async (iso3, adm) => {
    const ISO3 = iso3 ? String(iso3).toUpperCase() : '';
    const ADM = adm ? String(adm).toUpperCase() : '';
    if (!ISO3 || !ADM) return null;

    try {
      const localPath = `/geoboundaries/${encodeURIComponent(ISO3)}/${encodeURIComponent(ADM)}.geojson`;
      let resp = await fetch(localPath);
      if (!resp.ok) {
        resp = await fetch(`/api/geoboundaries?iso3=${encodeURIComponent(ISO3)}&adm=${encodeURIComponent(ADM)}`);
        if (!resp.ok) return null;
      }
      const gj = await resp.json();
      return gj && Array.isArray(gj?.features) ? gj : null;
    } catch (_e) {
      return null;
    }
  };

  // Fast availability check:
  // - Try HEAD against static file first (instant for bundled countries)
  // - Fall back to API "check" mode (metadata only; no huge GeoJSON download)
  const checkGeoBoundariesAvailable = async (iso3, adm) => {
    const ISO3 = iso3 ? String(iso3).toUpperCase() : '';
    const ADM = adm ? String(adm).toUpperCase() : '';
    if (!ISO3 || !ADM) return false;

    try {
      const localPath = `/geoboundaries/${encodeURIComponent(ISO3)}/${encodeURIComponent(ADM)}.geojson`;
      const localResp = await fetch(localPath, { method: 'HEAD' });
      if (localResp.ok) return true;
    } catch (_e) {
      // ignore and try API
    }

    try {
      const resp = await fetch(`/api/geoboundaries?iso3=${encodeURIComponent(ISO3)}&adm=${encodeURIComponent(ADM)}&check=1`);
      return !!resp.ok;
    } catch (_e) {
      return false;
    }
  };

  // Helper function to format numbers with K, M, B units
  const formatNumber = (num, showFull = false) => {
    if (showFull) {
      return num.toLocaleString();
    }
    // Round to avoid floating point precision issues
    const rounded = Math.round(num * 100) / 100;
    if (rounded >= 1000000000) {
      return (rounded / 1000000000).toFixed(1) + 'B';
    } else if (rounded >= 1000000) {
      return (rounded / 1000000).toFixed(1) + 'M';
    } else if (rounded >= 1000) {
      return (rounded / 1000).toFixed(1) + 'K';
    }
    // For numbers less than 1000, show up to 1 decimal place if needed, otherwise integer
    if (rounded % 1 === 0) {
      return rounded.toString();
    }
    return rounded.toFixed(1);
  };

  // Get currency symbol from unit code
  const getCurrencySymbol = (unit) => {
    const currencyMap = {
      'USD': '$',
      'EUR': '€',
      'GBP': '£',
      'JPY': '¥',
      'CNY': '¥',
      'CHF': 'CHF ',
      'CAD': 'C$',
      'AUD': 'A$',
      'INR': '₹',
      'BRL': 'R$',
      'MXN': 'MX$',
      'ZAR': 'R',
      'KRW': '₩',
      'SGD': 'S$',
      'HKD': 'HK$',
      'NZD': 'NZ$',
      'SEK': 'kr',
      'NOK': 'kr',
      'DKK': 'kr',
      'PLN': 'zł',
      'TRY': '₺',
      'RUB': '₽',
      'AED': 'د.إ',
      'SAR': '﷼',
      'QAR': '﷼',
    };
    return currencyMap[unit?.toUpperCase()] || (unit ? `${unit} ` : '');
  };

  // Format flow value based on indicator type and unit
  const formatFlowValue = (value, indicatorType, unit = null) => {
    const num = Number(value) || 0;
    if (indicatorType === 'total-funding') {
      const currencySymbol = getCurrencySymbol(unit || internationalIndicatorUnit);
      return `${currencySymbol}${formatNumber(num)}`;
    } else if (indicatorType === 'people-reached') {
      return `${formatNumber(num)} People reached`;
    } else if (indicatorType === 'services') {
      return `${formatNumber(num)} Services`;
    }
    return formatNumber(num);
  };

  // Define region bounds for zooming
  const regionBounds = {
    'global': {
      center: [20, 0],
      zoom: 2
    },
    'africa': {
      bounds: [[-35, -20], [35, 55]] // Southwest and Northeast corners
    },
    'americas': {
      bounds: [[-60, -180], [75, -30]]
    },
    'asia-pacific': {
      bounds: [[-10, 60], [45, 150]]
    },
    'europe-and-central-asia': {
      bounds: [[35, 10], [70, 80]]
    },
    'mena': {
      bounds: [[5, -15], [45, 65]]
    }
  };

  // Function to zoom to a specific region
  const zoomToRegion = (region) => {
    if (!mapInstanceRef.current || !regionBounds[region]) return;

    const regionConfig = regionBounds[region];

    if (region === 'global') {
      // For global view, use setView with center and zoom
      mapInstanceRef.current.setView(regionConfig.center, regionConfig.zoom, {
        animate: true,
        duration: 1.5
      });
    } else {
      // For specific regions, use fitBounds
      const bounds = L.latLngBounds(regionConfig.bounds);
      mapInstanceRef.current.fitBounds(bounds, {
        animate: true,
        duration: 1.5,
        padding: [20, 20] // Add some padding around the region
      });
    }
  };

  const mapRef = useRef(null);
  const mapInstanceRef = useRef(null);
  const geojsonLayerRef = useRef(null);
  const bubbleLayerRef = useRef(null);
  const flowLayerRef = useRef(null);
  const leafletLibRef = useRef(null);
  const legendRef = useRef(null);
  const isInitializingRef = useRef(false);
  const retryTimeoutRef = useRef(null);
  const retryCountRef = useRef(0);
  // Prevent repeatedly auto-fitting bounds on re-renders
  const lastFlowAutoFitKeyRef = useRef(null);
  const [showFullValues, setShowFullValues] = useState(false);
  const [isTooltipVisible, setIsTooltipVisible] = useState(false);
  const [geojsonReadyTick, setGeojsonReadyTick] = useState(0);
  const indicatorDataRef = useRef(indicatorData);
  const indicatorDataSignature = useMemo(() => hashIndicatorData(indicatorData), [indicatorData]);
  const [isMobile, setIsMobile] = useState(false);
  // Country-scope admin level (shared across map + bar chart)
  const [countryAdmLevel, setCountryAdmLevel] = useState('ADM1');
  const [countryAvailableAdmLevels, setCountryAvailableAdmLevels] = useState(['ADM1']);

  const { t, locale } = useTranslation();

  // State for localized country names from backend
  const [localizedCountries, setLocalizedCountries] = useState([]);
  const [isLoadingCountries, setIsLoadingCountries] = useState(false);

  // Animation state
  const [isAnimating, setIsAnimating] = useState(false);
  const [currentAnimationYear, setCurrentAnimationYear] = useState(null);
  const animationIntervalRef = useRef(null);

  // Performance optimization: Memoize maxValue calculation
  const maxValueRef = useRef(0);
  const lastIndicatorDataRef = useRef(null);
  const updateTimeoutRef = useRef(null);

  const getConnectedMapContainer = () => {
    const container = mapRef.current;
    if (!container || typeof document === 'undefined') return null;
    if (!container.isConnected || !document.body.contains(container)) return null;
    return container;
  };

  const getFeatureIso2 = (props) => {
    if (!props) return null;
    const iso2 =
      props['ISO3166-1-Alpha-2'] ||
      props.ISO_A2 ||
      props.ISO2 ||
      props.iso_a2;
    return iso2 ? String(iso2).toUpperCase() : null;
  };

  const getFeatureIso3 = (props) => {
    if (!props) return null;
    const iso3 =
      props['ISO3166-1-Alpha-3'] ||
      props.ISO_A3 ||
      props.ISO3 ||
      props.iso_a3;
    return iso3 ? String(iso3).toUpperCase() : null;
  };

  // Debug logging for component props
  console.log('InteractiveWorldMap received props:', {
    selectedIndicator,
    indicatorData,
    visualizationType,
    globalTotal,
    isLoadingData,
    regionName,
    selectedRegion,
    indicatorDataKeys: Object.keys(indicatorData || {}),
    indicatorDataType: typeof indicatorData,
    availableYears,
    selectedYear
  });

  // Animation control functions
  const startAnimation = () => {
    if (isAnimating || availableYears.length === 0) return;

    setIsAnimating(true);
    const sortedYears = [...availableYears].sort((a, b) => parseInt(a) - parseInt(b));
    setCurrentAnimationYear(sortedYears[0]);

    // Start the animation loop with smoother timing
    let currentIndex = 0;
    animationIntervalRef.current = setInterval(() => {
      if (currentIndex < sortedYears.length) {
        const year = sortedYears[currentIndex];
        setCurrentAnimationYear(year);
        if (onYearChange) {
          onYearChange(year);
        }
        currentIndex++;
      } else {
        // Animation complete
        stopAnimation();
      }
    }, 1500); // 1.5 seconds per year for smoother transitions
  };

  const stopAnimation = () => {
    setIsAnimating(false);
    setCurrentAnimationYear(null);
    if (animationIntervalRef.current) {
      clearInterval(animationIntervalRef.current);
      animationIntervalRef.current = null;
    }
  };

  // Function to smoothly animate bubble radius
  const animateRadius = (bubble, startRadius, endRadius, duration) => {
    const startTime = performance.now();
    const radiusDiff = endRadius - startRadius;

    const animate = (currentTime) => {
      const elapsed = currentTime - startTime;
      const progress = Math.min(elapsed / duration, 1);

      // Ease-out function for smooth deceleration
      const easeOut = 1 - Math.pow(1 - progress, 3);
      const currentRadius = startRadius + (radiusDiff * easeOut);

      bubble.setRadius(currentRadius);

      if (progress < 1) {
        requestAnimationFrame(animate);
      }
    };

    requestAnimationFrame(animate);
  };

  // Fetch localized country names from backend
  useEffect(() => {
    let mounted = true;
    const loadCountries = async () => {
      try {
        setIsLoadingCountries(true);
        const countries = await getCountriesList(locale || 'en');
        if (!mounted) return;
        setLocalizedCountries(Array.isArray(countries) ? countries : []);
      } catch (error) {
        console.error('Failed to load localized countries:', error);
        if (!mounted) return;
        setLocalizedCountries([]);
      } finally {
        if (!mounted) return;
        setIsLoadingCountries(false);
      }
    };
    loadCountries();
    return () => {
      mounted = false;
    };
  }, [locale]);

  // Detect mobile viewport
  useEffect(() => {
    const checkIsMobile = () => {
      const mobile = typeof window !== 'undefined' && window.innerWidth < 768;
      setIsMobile(mobile);

      // Remove legend from map when switching to mobile
      if (mobile && legendRef.current && mapInstanceRef.current) {
        mapInstanceRef.current.removeControl(legendRef.current);
        legendRef.current = null;
      }
    };
    checkIsMobile();
    window.addEventListener('resize', checkIsMobile);
    return () => window.removeEventListener('resize', checkIsMobile);
  }, []);

  // Update country name mapping when localized countries load
  useEffect(() => {
    if (!localizedCountries || localizedCountries.length === 0) return;

    // Update the global countryCodeToName mapping with localized names
    const countryCodeToName = window.countryCodeToName || {};

    localizedCountries.forEach(country => {
      const iso2 = String(country.iso2 || country.code || '').toUpperCase();
      const iso3 = String(country.iso3 || '').toUpperCase();
      const countryName = country.name || '';
      const nsName = country.national_society_name || countryName;

      // Prefer National Society name if available, otherwise country name
      const displayName = nsName || countryName;

      if (iso2 && displayName) {
        countryCodeToName[iso2] = displayName;
      }
      if (iso3 && displayName) {
        countryCodeToName[iso3] = displayName;
      }
    });

    window.countryCodeToName = countryCodeToName;

    // If map is already initialized, update the style to reflect new names
    if (geojsonLayerRef.current && mapInstanceRef.current) {
      // Trigger a style update to refresh any displayed names
      geojsonLayerRef.current.setStyle(style);
    }
  }, [localizedCountries]);

  // Determine available ADM levels for country scope (ADM0-ADM3)
  useEffect(() => {
    let cancelled = false;
    const iso3 = scopeCountryIso3 ? String(scopeCountryIso3).toUpperCase() : null;
    if (scopeType !== 'country' || !iso3) return;

    const check = async () => {
      try {
        const adms = ['ADM0', 'ADM1', 'ADM2', 'ADM3'];
        const results = await Promise.all(
          adms.map(async (adm) => {
            try {
              const ok = await checkGeoBoundariesAvailable(iso3, adm);
              return { adm, ok };
            } catch (_e) {
              return { adm, ok: false };
            }
          })
        );
        if (cancelled) return;
        const available = results.filter(r => r.ok).map(r => r.adm);
        const normalized = available.filter(a => a !== 'ADM0');
        const finalAvailable = normalized.length ? normalized : (available.includes('ADM0') ? ['ADM0'] : ['ADM1']);
        setCountryAvailableAdmLevels(finalAvailable);
        setCountryAdmLevel((prev) => {
          const p = String(prev || '').toUpperCase();
          if (finalAvailable.includes(p)) return p;
          // prefer finest available
          if (finalAvailable.includes('ADM3')) return 'ADM3';
          if (finalAvailable.includes('ADM2')) return 'ADM2';
          if (finalAvailable.includes('ADM1')) return 'ADM1';
          return finalAvailable[0] || 'ADM1';
        });
      } catch (_e) {
        // ignore
      }
    };
    check();

    return () => { cancelled = true; };
  }, [scopeType, scopeCountryIso3]);

  // Cleanup animation on unmount
  useEffect(() => {
    return () => {
      if (animationIntervalRef.current) {
        clearInterval(animationIntervalRef.current);
      }
      if (updateTimeoutRef.current) {
        clearTimeout(updateTimeoutRef.current);
      }
    };
  }, []);

  // Modern color scale for data visualization - Optimized for performance
  const getColor = (value, maxValue) => {
    if (!value || value === 0) return '#f8fafc';

    // Create a more sophisticated color gradient
    const intensity = Math.min(value / maxValue, 1);

    // Use a blue to red gradient for better data visualization
    // Optimized with early returns for better performance
    if (intensity < 0.2) return '#e3f2fd'; // Very light blue
    if (intensity < 0.4) return '#90caf9'; // Light blue
    if (intensity < 0.6) return '#42a5f5'; // Medium blue
    if (intensity < 0.8) return '#1976d2'; // Dark blue
    return '#0d47a1'; // Very dark blue
  };

  // Bubble size calculation for bubble map
  const getBubbleSize = (value, maxValue) => {
    if (!value || value === 0) return 0;

    // Calculate bubble size based on value
    const minSize = 3;
    const maxSize = 30;
    const intensity = Math.min(value / maxValue, 1);

    return minSize + (intensity * (maxSize - minSize));
  };

  // Function to add bubble layer
  const addBubbleLayer = () => {
    if (!mapInstanceRef.current || !indicatorData || Object.keys(indicatorData).length === 0) return;

    // Remove existing bubble layer
    if (bubbleLayerRef.current) {
      mapInstanceRef.current.removeLayer(bubbleLayerRef.current);
    }

    // Use memoized maxValue for better performance
    const maxValue = maxValueRef.current;

    if (maxValue <= 0) return;

    // Create bubble markers for countries with data
    const bubbleMarkers = [];
    Object.entries(indicatorData).forEach(([countryCode, countryData]) => {
      const value = typeof countryData === 'object' ? countryData.value : countryData;
      if (value > 0) {
        // Find the country in the GeoJSON to get its center coordinates
        if (geojsonLayerRef.current) {
          geojsonLayerRef.current.eachLayer((layer) => {
            const props = layer.feature.properties;
            const geoJsonCountryCode = props['ISO3166-1-Alpha-2'] || props.ISO_A2 || props.ISO2 || props.iso_a2;
            const geoJsonCountryISO3 = props['ISO3166-1-Alpha-3'] || props.ISO_A3 || props.ISO3 || props.iso_a3;

            // Check if this is the country we're looking for
            let isTargetCountry = false;
            if (countryCode === geoJsonCountryCode) {
              isTargetCountry = true;
            } else if (window.countryCodeMapping && window.countryCodeMapping[geoJsonCountryCode] === countryCode) {
              isTargetCountry = true;
            } else if (geoJsonCountryISO3 && countryCode === geoJsonCountryISO3) {
              isTargetCountry = true;
            }

            if (isTargetCountry) {
              const bounds = layer.getBounds();
              const center = bounds.getCenter();
              const size = getBubbleSize(value, maxValue);

              const bubble = L.circleMarker(center, {
                radius: size,
                fillColor: '#ef4444',
                color: '#dc2626',
                weight: 2,
                opacity: 0.8,
                fillOpacity: 0.7,
                className: 'bubble-marker'
              });

              // Store country code on bubble for updates
              bubble.countryCode = countryCode;

              // Add popup with country info
              let countryName = null;

              // First, try to get name from countryData if it exists and is a proper name (not a code)
              if (typeof countryData === 'object' && countryData.name) {
                const dataName = countryData.name;
                // Check if it's a code (2-3 uppercase letters)
                if (!/^[A-Z]{2,3}$/.test(dataName)) {
                  countryName = dataName; // It's a proper name, use it
                }
              }

              // If not found or is a code, try to map it using countryCode
              if (!countryName || /^[A-Z]{2,3}$/.test(countryName)) {
                const codeToLookup = (countryCode || countryName || '').toUpperCase();
                if (window.countryCodeToName && window.countryCodeToName[codeToLookup]) {
                  countryName = window.countryCodeToName[codeToLookup];
                } else if (!countryName) {
                  countryName = countryCode; // Fallback to code if no mapping found
                }
              }
              bubble.bindPopup(`
                <div class="text-center">
                  <h3 class="font-bold text-lg mb-2">${countryName}</h3>
                  <p class="text-2xl font-bold text-humdb-red">${formatNumber(value, showFullValues)}</p>
                  <p class="text-sm text-gray-600">${selectedIndicator.replace('-', ' ')}</p>
                </div>
              `);

              // Add hover effects
              bubble.on('mouseover', function() {
                this.setStyle({
                  fillOpacity: 0.9,
                  opacity: 1,
                  weight: 3
                });
                if (onCountryHover) {
                  onCountryHover(countryName, value, countryCode);
                }
              });

              bubble.on('mouseout', function() {
                this.setStyle({
                  fillOpacity: 0.7,
                  opacity: 0.8,
                  weight: 2
                });
                if (onCountryLeave) {
                  onCountryLeave();
                }
              });

              bubble.on('click', () => {
                if (onCountryClick) {
                  onCountryClick(countryCode, countryName);
                }
              });

              bubbleMarkers.push(bubble);
            }
          });
        }
      }
    });

    // Create layer group and add to map
    if (bubbleMarkers.length > 0) {
      bubbleLayerRef.current = L.layerGroup(bubbleMarkers);
      bubbleLayerRef.current.addTo(mapInstanceRef.current);
    }
  };

  // Render international flow lines (Leaflet only, global scope).
  useEffect(() => {
    // Country scope uses Mapbox map, and bar chart has no Leaflet map.
    if (scopeType === 'country' || visualizationType === 'barchart') {
      // If we previously rendered flow lines, clear them.
      try {
        if (flowLayerRef.current) {
          flowLayerRef.current.clearLayers();
        }
      } catch (_e) {}
      return;
    }

    const map = mapInstanceRef.current;
    const geoLayer = geojsonLayerRef.current;
    const flows = Array.isArray(flowLines) ? flowLines : [];
    if (!map || !geoLayer) return;

    let cancelled = false;

    const draw = async () => {
      // Lazy-load Leaflet lib (needed for layerGroup/polyline)
      let L = leafletLibRef.current;
      if (!L) {
        try {
          L = (await import('leaflet')).default;
          leafletLibRef.current = L;
        } catch (_e) {
          return;
        }
      }
      if (cancelled) return;

        // Ensure a dedicated pane so flows always render above countries.
        try {
          if (!map.getPane('ifrcFlowPane')) {
            map.createPane('ifrcFlowPane');
            const pane = map.getPane('ifrcFlowPane');
            if (pane) {
              pane.style.zIndex = '650';
              // Allow pointer events for interactive flow lines
              pane.style.pointerEvents = 'auto';
            }
          }
        } catch (_e) {
          // ignore
        }

      // Ensure a layer group exists on the map
      if (!flowLayerRef.current) {
        try {
            flowLayerRef.current = L.layerGroup([], { pane: 'ifrcFlowPane' }).addTo(map);
        } catch (_e) {
          return;
        }
      }

      // Clear previous flow lines
      try {
        flowLayerRef.current.clearLayers();
      } catch (_e) {}

      if (!flows.length) return;

      // Build a centroid lookup from the GeoJSON layer (ISO2 + ISO3 -> LatLng)
      const centers = new Map();
      try {
        // Compute proper centroid from GeoJSON geometry (handles antimeridian crossing).
        // For MultiPolygon, uses the LARGEST polygon (e.g. continental US, not Alaska/Hawaii).
        const getLayerCentroid = (layer) => {
          try {
            const feature = layer?.feature;
            if (!feature || !feature.geometry) return null;

            const geom = feature.geometry;
            const coords = geom.coordinates;

            if (geom.type === 'Point') {
              return { lat: coords[1], lng: coords[0] };
            }

            // Helper to compute polygon area (using shoelace formula approximation)
            const polygonArea = (ring) => {
              if (!ring || ring.length < 3) return 0;
              let area = 0;
              for (let i = 0; i < ring.length; i++) {
                const j = (i + 1) % ring.length;
                const [lng1, lat1] = ring[i];
                const [lng2, lat2] = ring[j];
                area += Number(lng1) * Number(lat2);
                area -= Number(lng2) * Number(lat1);
              }
              return Math.abs(area / 2);
            };

            // Helper to compute centroid from a ring
            const ringCentroid = (ring) => {
              if (!ring || ring.length === 0) return null;
              let refLng = Number(ring[0][0]);
              if (!Number.isFinite(refLng)) return null;

              let sumLat = 0;
              let sumLng = 0;
              let n = 0;

              for (const [lng, lat] of ring) {
                const numLat = Number(lat);
                let numLng = Number(lng);
                if (!Number.isFinite(numLat) || !Number.isFinite(numLng)) continue;

                // Normalize longitude to be near refLng (handle wrapping)
                while (numLng - refLng > 180) numLng -= 360;
                while (numLng - refLng < -180) numLng += 360;

                refLng = (refLng * 0.95) + (numLng * 0.05);

                sumLat += numLat;
                sumLng += numLng;
                n += 1;
              }

              if (!n) return null;
              const avgLat = sumLat / n;
              let avgLng = sumLng / n;
              avgLng = ((avgLng + 540) % 360) - 180;
              return { lat: avgLat, lng: avgLng };
            };

            if (geom.type === 'Polygon') {
              // Single polygon: use exterior ring
              return ringCentroid(coords[0]);
            } else if (geom.type === 'MultiPolygon') {
              // MultiPolygon: find the LARGEST polygon and use its centroid
              let largestArea = -1;
              let largestRing = null;

              for (const poly of coords) {
                if (poly[0] && poly[0].length >= 3) {
                  const area = polygonArea(poly[0]);
                  if (area > largestArea) {
                    largestArea = area;
                    largestRing = poly[0];
                  }
                }
              }

              if (largestRing) {
                return ringCentroid(largestRing);
              }
            } else if (geom.type === 'LineString') {
              return ringCentroid(coords);
            } else if (geom.type === 'MultiLineString') {
              // For MultiLineString, use the longest line
              let longest = null;
              let maxLen = -1;
              for (const line of coords) {
                if (line.length > maxLen) {
                  maxLen = line.length;
                  longest = line;
                }
              }
              if (longest) return ringCentroid(longest);
            }

            return null;
          } catch (_e) {
            return null;
          }
        };

        geoLayer.eachLayer((layer) => {
          const props = layer?.feature?.properties;
          const iso2 = getFeatureIso2(props);
          const iso3 = getFeatureIso3(props);
          const center = getLayerCentroid(layer) || layer?.getBounds?.()?.getCenter?.();
          if (!center) return;
          if (iso2) centers.set(iso2, center);
          if (iso3) centers.set(iso3, center);
        });
      } catch (_e) {
        // ignore
      }

      const normalizeCode = (code) => {
        const c = String(code || '').trim();
        if (!c) return null;
        const up = c.toUpperCase();
        // If someone passes ISO3, allow it (we also store ISO3 in centers).
        if (up.length === 2 || up.length === 3) return up;
        // Try mapping from name/other to ISO2 if available
        if (window.countryCodeMapping) {
          const mapped = window.countryCodeMapping[up] || window.countryCodeMapping[up.toLowerCase()];
          if (mapped) return String(mapped).toUpperCase();
        }
        return null;
      };

      // Helper to get country name from ISO2
      const getCountryNameFromIso2 = (iso2) => {
        if (!iso2) return iso2 || 'Unknown';
        const data = indicatorData?.[iso2];
        if (data && typeof data === 'object' && data.name) {
          return data.name;
        }
        if (window.countryCodeToName && window.countryCodeToName[iso2]) {
          return window.countryCodeToName[iso2];
        }
        return iso2;
      };

      // Auto-fit the map to the active flows when a specific country is selected (e.g. Qatar).
      // We only do this for country-scoped international view, not for global scope.
      const shouldAutoFitFlows = !!scopeCountryIso2;
      const autoFitPoints = [];
      const autoFitEdgeKeys = [];
      const clamp = (n, min, max) => Math.max(min, Math.min(max, Number.isFinite(n) ? n : min));
      const lerp = (a, b, t) => a + ((b - a) * clamp(t, 0, 1));
      const getFlowTierProfile = (tier, normalizedStrength) => {
        if (tier === 'strong') {
          return { color: '#dc2626', opacity: 0.9, strength: clamp(normalizedStrength, 0.75, 1) };
        }
        if (tier === 'subtle') {
          return { color: '#fb7185', opacity: 0.62, strength: clamp(normalizedStrength, 0, 0.35) };
        }
        return { color: '#ef4444', opacity: 0.76, strength: clamp(normalizedStrength, 0.25, 0.85) };
      };
      const getBaseWeightFromFlow = (flow) => {
        const visualWeight = Number(flow?.visualWeight);
        if (Number.isFinite(visualWeight) && visualWeight >= 0) {
          const normalized = clamp(visualWeight / 100, 0, 1);
          return {
            baseWeight: lerp(1.6, 5.8, normalized),
            normalizedStrength: normalized,
          };
        }
        const fallbackValue = Number(flow?.value ?? 1);
        const normalized = clamp(Math.log10(Math.max(1, fallbackValue) + 1) / 3.2, 0, 1);
        return {
          baseWeight: lerp(1.8, 5.2, normalized),
          normalizedStrength: normalized,
        };
      };
      const getZoomLineScale = (zoomLevel) => clamp(Math.pow(1.5, zoomLevel - 2), 0.4, 2.7);
      const getZoomArrowScale = (zoomLevel) => clamp(Math.pow(1.45, zoomLevel - 2), 0.35, 2.3);

      // Draw each flow
      // Note: we attach mouse handlers to a thick "hover line" so the tooltip is easy to trigger.
      // The visible line is non-interactive (to avoid global Leaflet interactive CSS affecting styling).
      for (const f of flows) {
        const fromCode = normalizeCode(f?.from);
        const toCode = normalizeCode(f?.to);
        if (!fromCode || !toCode || fromCode === toCode) continue;

        const fromCenter = centers.get(fromCode) || centers.get(window.countryCodeMapping?.[fromCode] || '');
        const toCenter = centers.get(toCode) || centers.get(window.countryCodeMapping?.[toCode] || '');
        if (!fromCenter || !toCenter) continue;

        if (shouldAutoFitFlows) {
          autoFitPoints.push(fromCenter, toCenter);
          autoFitEdgeKeys.push(`${fromCode}->${toCode}`);
        }

        const styleValue = Number(f?.visualWeight ?? f?.value ?? 1);
        const displayValue = Number(f?.rawValue ?? f?.value ?? styleValue ?? 1);
        const { baseWeight, normalizedStrength } = getBaseWeightFromFlow(f);
        const tierProfile = getFlowTierProfile(String(f?.styleTier || 'medium'), normalizedStrength);

        const buildArcPoints = (a, b, curvature = 0.22, segments = 28) => {
          // Quadratic Bezier curve in lat/lng space:
          // p(t) = (1-t)^2 * a + 2(1-t)t * c + t^2 * b
          // Control point c is offset perpendicular to the AB vector.
          const ax = Number(a.lng), ay = Number(a.lat);
          const bx = Number(b.lng), by = Number(b.lat);
          if (![ax, ay, bx, by].every(Number.isFinite)) return [a, b];

          const dx = bx - ax;
          const dy = by - ay;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;

          // Perpendicular unit vector
          const px = -dy / dist;
          const py = dx / dist;

          // Midpoint + perpendicular offset
          const mx = (ax + bx) / 2;
          const my = (ay + by) / 2;
          const offset = dist * curvature;
          const cx = mx + px * offset;
          const cy = my + py * offset;

          const pts = [];
          const n = Math.max(8, Math.min(80, Number(segments) || 28));
          for (let i = 0; i <= n; i++) {
            const t = i / n;
            const omt = 1 - t;
            const x = omt * omt * ax + 2 * omt * t * cx + t * t * bx;
            const y = omt * omt * ay + 2 * omt * t * cy + t * t * by;
            pts.push([y, x]); // [lat, lng]
          }
          return pts;
        };

        try {
          const pts = buildArcPoints(fromCenter, toCenter);
          const last = pts[pts.length - 1];
          const prev = pts[Math.max(0, pts.length - 2)];
          const midPoint = pts[Math.floor(pts.length / 2)];

          // Get country names
          const fromName = getCountryNameFromIso2(fromCode);
          const toName = getCountryNameFromIso2(toCode);
          const formattedValue = formatFlowValue(displayValue, internationalIndicatorType, internationalIndicatorUnit);

          // Popup/tooltip (positioned at midpoint of curve)
          const midLatLng = L.latLng(midPoint[0], midPoint[1]);
          const popupContent = `
            <div style="text-align: center; min-width: 180px;">
              <div style="font-weight: 700; margin-bottom: 6px; color: #1e3a8a;">${fromName} → ${toName}</div>
              <div style="font-size: 18px; font-weight: 800; color: #ef4444; margin-bottom: 4px;">${formattedValue}</div>
            </div>
          `;

          // Visible flow line (non-interactive; hover handled by hoverLine)
          const line = L.polyline(pts, {
            pane: 'ifrcFlowPane',
            color: tierProfile.color,
            weight: baseWeight,
            opacity: tierProfile.opacity,
            lineCap: 'round',
            lineJoin: 'round',
            smoothFactor: 1,
            interactive: false, // Not interactive, hover handled by hoverLine
            className: 'humdb-flow-line',
          });
          line.__ifrcBaseWeight = baseWeight;
          line.__ifrcBaseOpacity = tierProfile.opacity;
          line.__ifrcBaseColor = tierProfile.color;
          line.__ifrcIsFlowLine = true;
          line.__ifrcIsHovered = false;

          // Thick hover target line (nearly invisible, but still hoverable)
          const hoverLine = L.polyline(pts, {
            pane: 'ifrcFlowPane',
            color: tierProfile.color,
            weight: Math.max(8, baseWeight + 10),
            opacity: 0.001, // keep >0 so SVG pointer-events can hit it
            lineCap: 'round',
            lineJoin: 'round',
            smoothFactor: 1,
            interactive: true,
            className: 'humdb-flow-hover',
          });
          hoverLine.__ifrcBaseWeight = baseWeight;
          hoverLine.__ifrcIsFlowHover = true;
          hoverLine.__ifrcPopupLatLng = midLatLng;
          hoverLine.__ifrcVisibleLine = line;
          line.__ifrcHoverLine = hoverLine;
          hoverLine.__ifrcFlowMeta = {
            from: fromName,
            to: toName,
            fromCode,
            toCode,
            value: displayValue,
            styleValue,
            styleTier: String(f?.styleTier || 'medium'),
            formattedValue,
          };
          hoverLine.bindPopup(popupContent, {
            className: 'humdb-flow-tooltip',
            closeButton: false,
            offset: [0, -10],
            autoPan: false,
          });

          hoverLine.on('mouseover', function(e) {
            try { map.getContainer().style.cursor = 'pointer'; } catch (_e2) {}
            const visible = this.__ifrcVisibleLine;
            if (visible) visible.__ifrcIsHovered = true;
            // Open popup at midpoint for stability
            const ll = this.__ifrcPopupLatLng || e?.latlng;
            if (ll) this.openPopup(ll);
            // Re-apply zoom styling so hover width is consistent
            try { map.fire('ifrc:flowstyle'); } catch (_e2) {}
          });
          hoverLine.on('mouseout', function() {
            try { map.getContainer().style.cursor = ''; } catch (_e2) {}
            const visible = this.__ifrcVisibleLine;
            if (visible) visible.__ifrcIsHovered = false;
            this.closePopup();
            try { map.fire('ifrc:flowstyle'); } catch (_e2) {}
          });

          // Add both layers (hover first so visible line is on top)
          hoverLine.addTo(flowLayerRef.current);
          line.addTo(flowLayerRef.current);

          // Arrow tip (direction) at the end of the arc.
          // Use a stroked chevron instead of a filled triangle for a cleaner, modern look.
          try {
            const endLatLng = L.latLng(last[0], last[1]);
            // Use a farther-back point to stabilize tangent direction at the tip.
            const dirIdx = Math.max(0, pts.length - 6);
            const dirPoint = pts[dirIdx] || prev;
            const dirLatLng = L.latLng(dirPoint[0], dirPoint[1]);

            const arrow = L.polyline(
              [
                [endLatLng.lat, endLatLng.lng],
                [endLatLng.lat, endLatLng.lng],
                [endLatLng.lat, endLatLng.lng],
              ],
              {
              pane: 'ifrcFlowPane',
              color: tierProfile.color,
              weight: Math.max(1.05, baseWeight * 0.62),
              opacity: Math.min(0.92, tierProfile.opacity + 0.06),
              lineCap: 'butt',
              lineJoin: 'miter',
              interactive: false,
              className: 'humdb-flow-arrow',
              }
            );
            arrow.__ifrcArrowMeta = {
              endLatLng,
              dirLatLng,
              baseWeight,
              color: tierProfile.color,
              opacity: tierProfile.opacity,
              visibleLine: line,
            };
            arrow.addTo(flowLayerRef.current);
          } catch (_e) {
            // ignore arrow failures
          }
        } catch (_e) {
          // ignore individual flow failures
        }
      }

      // Auto-zoom to the active flow area (country selection only).
      try {
        if (shouldAutoFitFlows && autoFitPoints.length >= 2) {
          const key = `${String(scopeCountryIso2 || '').toUpperCase()}|${autoFitEdgeKeys.sort().join('|')}`;
          if (lastFlowAutoFitKeyRef.current !== key) {
            lastFlowAutoFitKeyRef.current = key;
            const b = L.latLngBounds(autoFitPoints);
            if (b && b.isValid && b.isValid()) {
              map.fitBounds(b, {
                padding: [40, 40],
                maxZoom: 5,
                animate: true,
                duration: 1.2,
              });
            }
          }
        }
      } catch (_e) {
        // ignore auto-fit failures
      }

      // Scale stroke widths based on current Leaflet zoom level.
      const applyZoomStyling = () => {
        try {
          const z = Number(map.getZoom?.() ?? 2);
          const lineScale = getZoomLineScale(z);
          const arrowScale = getZoomArrowScale(z);

          flowLayerRef.current?.eachLayer?.((layer) => {
            // Hover target lines (make them thick, nearly invisible, but hoverable)
            if (layer && typeof layer.setStyle === 'function' && layer.__ifrcIsFlowHover && layer.__ifrcBaseWeight) {
              const linkedLine = layer.__ifrcVisibleLine;
              const visibleBase = Number(linkedLine?.__ifrcBaseWeight ?? layer.__ifrcBaseWeight) || 2;
              const visibleWidth = clamp(visibleBase * lineScale, 0.9, 13);
              const w = clamp(visibleWidth + 10, 8, 24);
              layer.setStyle({
                color: linkedLine?.__ifrcBaseColor || '#ef4444',
                weight: w,
                opacity: 0.001,
              });
              return;
            }

            // Visible flow lines (thickness scales with zoom; highlight on hover)
            if (layer && typeof layer.setStyle === 'function' && layer.__ifrcIsFlowLine && layer.__ifrcBaseWeight) {
              const bw = Number(layer.__ifrcBaseWeight) || 2;
              const baseOpacity = Number(layer.__ifrcBaseOpacity);
              const color = layer.__ifrcBaseColor || '#ef4444';
              const w = clamp(bw * lineScale, 0.9, 13);
              const isHovered = !!layer.__ifrcIsHovered;
              layer.setStyle({
                color,
                weight: isHovered ? clamp(w * 1.16, 1.1, 14) : w,
                opacity: isHovered ? clamp((Number.isFinite(baseOpacity) ? baseOpacity : 0.78) + 0.18, 0.45, 1) : (Number.isFinite(baseOpacity) ? baseOpacity : 0.78),
              });
              return;
            }

            // Arrow chevrons: recompute points in pixel space with adaptive geometry.
            if (layer && typeof layer.setLatLngs === 'function' && layer.__ifrcArrowMeta) {
              const meta = layer.__ifrcArrowMeta;
              const endLatLng = meta?.endLatLng;
              const dirLatLng = meta?.dirLatLng;
              const baseWeight = Number(meta?.baseWeight) || 2;
              const baseColor = meta?.color || '#ef4444';
              const baseOpacity = Number(meta?.opacity);
              const linkedLine = meta?.visibleLine;
              if (!endLatLng || !dirLatLng) return;

              const pEnd = map.latLngToLayerPoint(endLatLng);
              const pDir = map.latLngToLayerPoint(dirLatLng);
              const dx = pEnd.x - pDir.x;
              const dy = pEnd.y - pDir.y;
              const len = Math.sqrt(dx * dx + dy * dy) || 1;
              if (len < 2) {
                layer.setStyle({ opacity: 0 });
                return;
              }
              const ux = dx / len;
              const uy = dy / len;
              const px = -uy;
              const py = ux;

              const renderedLineWidth = clamp(baseWeight * lineScale, 0.9, 13);
              // Keep arrow tips visually small and crisp at low zoom.
              const arrowLenPx = clamp((3.8 + renderedLineWidth * 1.6) * arrowScale, 3.6, 13);
              const arrowWidthPx = clamp((1.6 + renderedLineWidth * 1.0) * arrowScale, 1.8, 7.5);
              const tipBackoffPx = clamp((2.1 + renderedLineWidth * 0.65) * arrowScale, 1.8, 9);
              const tip = { x: pEnd.x - ux * tipBackoffPx, y: pEnd.y - uy * tipBackoffPx };
              const wingAnchor = { x: tip.x - ux * arrowLenPx, y: tip.y - uy * arrowLenPx };
              const left = { x: wingAnchor.x + px * (arrowWidthPx / 2), y: wingAnchor.y + py * (arrowWidthPx / 2) };
              const right = { x: wingAnchor.x - px * (arrowWidthPx / 2), y: wingAnchor.y - py * (arrowWidthPx / 2) };

              const llLeft = map.layerPointToLatLng(left);
              const llTip = map.layerPointToLatLng(tip);
              const llRight = map.layerPointToLatLng(right);

              layer.setLatLngs([llLeft, llTip, llRight]);
              layer.setStyle({
                color: linkedLine?.__ifrcBaseColor || baseColor,
                weight: clamp(renderedLineWidth * 0.52, 0.95, 3.5),
                opacity: clamp((Number.isFinite(baseOpacity) ? baseOpacity : 0.78) + 0.1, 0.52, 0.96),
                lineCap: 'butt',
                lineJoin: 'miter',
              });
            }
          });
        } catch (_e) {
          // ignore
        }
      };

      // Apply once now, and keep it smooth on interactive zoom.
      let pendingStyleFrame = null;
      const scheduleFlowStyling = () => {
        try {
          if (pendingStyleFrame != null) {
            cancelAnimationFrame(pendingStyleFrame);
          }
          pendingStyleFrame = requestAnimationFrame(() => {
            pendingStyleFrame = null;
            applyZoomStyling();
          });
        } catch (_e) {
          applyZoomStyling();
        }
      };
      applyZoomStyling();
      try {
        map.off('zoom', scheduleFlowStyling);
        map.on('zoom', scheduleFlowStyling);
        map.off('zoomend', scheduleFlowStyling);
        map.on('zoomend', scheduleFlowStyling);
        map.off('ifrc:flowstyle', scheduleFlowStyling);
        map.on('ifrc:flowstyle', scheduleFlowStyling);
        // Keep a handle for cleanup
        flowLayerRef.current.__ifrcZoomHandler = scheduleFlowStyling;
        flowLayerRef.current.__ifrcStyleFrameCleanup = () => {
          if (pendingStyleFrame != null) {
            cancelAnimationFrame(pendingStyleFrame);
            pendingStyleFrame = null;
          }
        };
      } catch (_e) {
        // ignore
      }
    };

    draw();

    return () => {
      cancelled = true;
      // Detach zoom handler if present
      try {
        const h = flowLayerRef.current?.__ifrcZoomHandler;
        if (h) {
          map.off('zoom', h);
          map.off('zoomend', h);
          map.off('ifrc:flowstyle', h);
        }
        flowLayerRef.current?.__ifrcStyleFrameCleanup?.();
      } catch (_e) {}
    };
  }, [flowLines, scopeType, scopeCountryIso2, visualizationType, indicatorDataSignature, geojsonReadyTick]);

  // Function to update legend content
  const updateLegend = () => {
    // Update Leaflet legend (desktop only)
    if (!isMobile && legendRef.current && mapInstanceRef.current) {
      const legendContainer = legendRef.current.getContainer();
      if (!legendContainer) return;

      // Use memoized maxValue for better performance
      const maxValue = maxValueRef.current;

      if (maxValue <= 0) {
        legendContainer.innerHTML = `
          <h4 class="font-bold text-humdb-navy mb-3 text-base">${t('globalOverview.map.dataRange')}</h4>
          <div class="text-sm text-humdb-gray-600">${t('data.noDataAvailable')}</div>
        `;
        return;
      }

      if (visualizationType === 'bubble') {
        // Bubble map legend
        const grades = [0, maxValue * 0.2, maxValue * 0.4, maxValue * 0.6, maxValue * 0.8, maxValue];

        legendContainer.innerHTML = `
          <h4 class="font-bold text-humdb-navy mb-3 text-base">${t('globalOverview.map.bubbleSize')}</h4>
          <div class="space-y-2">
        `;

        for (let i = 0; i < grades.length - 1; i++) {
          const size = getBubbleSize(grades[i + 1], maxValue);
          legendContainer.innerHTML += `
            <div class="flex items-center space-x-3">
              <div style="width: ${size}px; height: ${size}px; background: #ef4444; border-radius: 50%; border: 2px solid #dc2626;"></div>
              <span class="text-sm text-humdb-gray-700">
                ${formatNumber(grades[i], showFullValues)}${grades[i + 1] ? ' - ' + formatNumber(grades[i + 1], showFullValues) : '+'}
              </span>
            </div>
          `;
        }

        legendContainer.innerHTML += `
          </div>
          <div class="mt-3 pt-3 border-t border-gray-200">
            <div class="flex items-center space-x-2">
              <div style="width: 3px; height: 3px; background: #f8fafc; border-radius: 50%; border: 1px solid #e5e7eb;"></div>
              <span class="text-sm text-humdb-gray-600">${t('data.noData')}</span>
            </div>
          </div>
        `;
      } else {
        // Choropleth legend
        // Round grades to avoid floating point precision issues
        const rawGrades = [0, maxValue * 0.2, maxValue * 0.4, maxValue * 0.6, maxValue * 0.8, maxValue];
        const grades = rawGrades.map(g => Math.round(g * 100) / 100);

        legendContainer.innerHTML = `
          <h4 class="font-bold text-humdb-navy mb-3 text-base">${t('globalOverview.map.dataRange')}</h4>
          <div class="space-y-2">
        `;

        for (let i = 0; i < grades.length - 1; i++) {
          legendContainer.innerHTML += `
            <div class="flex items-center space-x-3">
              <div style="background: ${getColor(grades[i + 1], maxValue)}; width: 20px; height: 20px; border-radius: 4px; border: 1px solid #e5e7eb;"></div>
              <span class="text-sm text-humdb-gray-700">
                ${formatNumber(grades[i], showFullValues)}${grades[i + 1] ? ' - ' + formatNumber(grades[i + 1], showFullValues) : '+'}
              </span>
            </div>
          `;
        }

        legendContainer.innerHTML += `
          </div>
          <div class="mt-3 pt-3 border-t border-gray-200">
            <div class="flex items-center space-x-2">
              <div style="background: #f8fafc; width: 20px; height: 20px; border-radius: 4px; border: 1px solid #e5e7eb;"></div>
              <span class="text-sm text-humdb-gray-600">${t('data.noData')}</span>
            </div>
          </div>
        `;
      }
    }
  };

  // Function to render mobile legend HTML
  const renderMobileLegend = () => {
    // Calculate maxValue directly from indicatorData for mobile legend
    let maxValue = 0;
    if (indicatorData && Object.keys(indicatorData).length > 0) {
      maxValue = Math.max(...Object.values(indicatorData).map(data =>
        typeof data === 'object' ? data.value : data
      ).filter(v => v > 0));
    }

    if (maxValue <= 0) {
      return (
        <div className="text-xs text-humdb-gray-600">{t('data.noDataAvailable')}</div>
      );
    }

    if (visualizationType === 'bubble') {
      // Round grades to avoid floating point precision issues
      const rawGrades = [0, maxValue * 0.2, maxValue * 0.4, maxValue * 0.6, maxValue * 0.8, maxValue];
      const grades = rawGrades.map(g => Math.round(g * 100) / 100);
      return (
        <div className="space-y-1.5">
          <h4 className="font-semibold text-humdb-navy mb-2 text-xs">{t('globalOverview.map.bubbleSize')}</h4>
          {grades.slice(0, -1).map((grade, i) => {
            const size = getBubbleSize(grades[i + 1], maxValue);
            return (
              <div key={i} className="flex items-center space-x-2">
                <div
                  className="rounded-full border-2 border-red-600"
                  style={{
                    width: `${size}px`,
                    height: `${size}px`,
                    backgroundColor: '#ef4444'
                  }}
                />
                <span className="text-xs text-humdb-gray-700">
                  {formatNumber(grade, showFullValues)}{grades[i + 1] ? ' - ' + formatNumber(grades[i + 1], showFullValues) : '+'}
                </span>
              </div>
            );
          })}
        </div>
      );
    } else {
      // Round grades to avoid floating point precision issues
      const rawGrades = [0, maxValue * 0.2, maxValue * 0.4, maxValue * 0.6, maxValue * 0.8, maxValue];
      const grades = rawGrades.map(g => Math.round(g * 100) / 100);
      return (
        <div className="space-y-1.5">
          <h4 className="font-semibold text-humdb-navy mb-2 text-xs">{t('globalOverview.map.dataRange')}</h4>
          {grades.slice(0, -1).map((grade, i) => (
            <div key={i} className="flex items-center space-x-2">
              <div
                className="rounded border"
                style={{
                  width: '16px',
                  height: '16px',
                  backgroundColor: getColor(grades[i + 1], maxValue),
                  borderColor: '#e5e7eb'
                }}
              />
              <span className="text-xs text-humdb-gray-700">
                {formatNumber(grade, showFullValues)}{grades[i + 1] ? ' - ' + formatNumber(grades[i + 1], showFullValues) : '+'}
              </span>
            </div>
          ))}
        </div>
      );
    }
  };

  // Enhanced style function for countries - Optimized for performance
  const style = (feature) => {
    const geoJsonCountryCode = feature.properties['ISO3166-1-Alpha-2'] || feature.properties.ISO_A2 || feature.properties.ISO2 || feature.properties.iso_a2;
    const geoJsonCountryName = feature.properties.name || feature.properties.ADMIN || feature.properties.NAME;
    const geoJsonCountryISO3 = feature.properties['ISO3166-1-Alpha-3'] || feature.properties.ISO_A3 || feature.properties.ISO3 || feature.properties.iso_a3;

    // Use the country code mapping to find the correct key
    let countryCode = geoJsonCountryCode;
    let countryData = null;

    // Try direct match first
    if (indicatorData && indicatorData[geoJsonCountryCode]) {
      countryCode = geoJsonCountryCode;
      countryData = indicatorData[geoJsonCountryCode];
    } else if (window.countryCodeMapping && window.countryCodeMapping[geoJsonCountryCode] && indicatorData) {
      // Try mapping
      const mappedCode = window.countryCodeMapping[geoJsonCountryCode];
      if (indicatorData[mappedCode]) {
        countryCode = mappedCode;
        countryData = indicatorData[mappedCode];
      }
    } else if (geoJsonCountryISO3 && indicatorData && indicatorData[geoJsonCountryISO3]) {
      // Try ISO3 match
      countryCode = geoJsonCountryISO3;
      countryData = indicatorData[geoJsonCountryISO3];
    } else if (geoJsonCountryName && window.countryCodeMapping && window.countryCodeMapping[geoJsonCountryName.toLowerCase()] && indicatorData) {
      // Try name match
      const mappedCode = window.countryCodeMapping[geoJsonCountryName.toLowerCase()];
      if (indicatorData[mappedCode]) {
        countryCode = mappedCode;
        countryData = indicatorData[mappedCode];
      }
    }

    const value = countryData ? (typeof countryData === 'object' ? countryData.value : countryData) : 0;

    // Use memoized maxValue for better performance
    let maxValue = maxValueRef.current;
    if (lastIndicatorDataRef.current !== indicatorData) {
      if (indicatorData && Object.keys(indicatorData).length > 0) {
        maxValue = Math.max(...Object.values(indicatorData).map(data =>
          typeof data === 'object' ? data.value : data
        ).filter(v => v > 0));
        maxValueRef.current = maxValue;
        lastIndicatorDataRef.current = indicatorData;
      } else {
        // If no data, set maxValue to 1 to avoid division by zero
        maxValue = 1;
        maxValueRef.current = maxValue;
        lastIndicatorDataRef.current = indicatorData;
      }
    }

    // Debug logging for Afghanistan specifically
    if (geoJsonCountryCode === 'AF' || geoJsonCountryName?.toLowerCase().includes('afghan')) {
      console.log(`Afghanistan styling:`, {
        geoJsonCountryCode,
        geoJsonCountryName,
        geoJsonCountryISO3,
        countryCode,
        countryData,
        value,
        indicatorDataKeys: Object.keys(indicatorData || {}),
        mapping: window.countryCodeMapping ? window.countryCodeMapping['AF'] : 'No mapping'
      });
    }

    // Different styling based on visualization type
    if (visualizationType === 'bubble') {
      return {
        fillColor: '#f8fafc', // Light background for bubble map
        weight: 1,
        opacity: 1,
        color: '#d1d5db',
        fillOpacity: 0.3,
        className: 'country-polygon'
      };
    } else {
      const fillColor = getColor(value, maxValue);
      return {
        fillColor: fillColor,
        weight: 1,
        opacity: 1,
        color: '#d1d5db', // Lighter grey borders
        fillOpacity: value > 0 ? 0.85 : 0.3,
        className: 'country-polygon'
        // Removed CSS transition to eliminate delay
      };
    }
  };

  // Enhanced highlight function
  const highlightFeature = (e) => {
    const layer = e.target;
    const props = layer.feature.properties;

    layer.setStyle({
      weight: 2,
      color: '#ef4444',
      fillOpacity: 0.95,
      fillColor: '#ef4444'
    });
    layer.bringToFront();

    // Call the hover callback with country data
    if (onCountryHover) {
      const iso2 = props['ISO3166-1-Alpha-2'] || props.ISO_A2 || props.ISO2 || props.iso_a2;
      const iso3 = props['ISO3166-1-Alpha-3'] || props.ISO_A3 || props.ISO3 || props.iso_a3;
      const name = props.name || props.ADMIN || props.NAME;

      // Build an ordered list of candidate codes to try against indicatorData
      const candidates = [];
      if (iso2) candidates.push(iso2);
      if (window.countryCodeMapping && iso2 && window.countryCodeMapping[iso2]) {
        candidates.push(window.countryCodeMapping[iso2]);
      }
      if (iso3) {
        candidates.push(iso3);
        if (window.countryCodeMapping && window.countryCodeMapping[iso3]) {
          candidates.push(window.countryCodeMapping[iso3]);
        }
      }
      if (name && window.countryCodeMapping && window.countryCodeMapping[String(name).toLowerCase()]) {
        candidates.push(window.countryCodeMapping[String(name).toLowerCase()]);
      }

      // Resolve the first candidate that exists in indicatorData
      let resolvedCode = null;
      let countryData = null;
      const tryResolve = (code) => {
        const currentData = indicatorDataRef.current;
        if (!code || !currentData || typeof currentData !== 'object') return false;
        const raw = String(code);
        const upper = raw.toUpperCase();
        if (Object.prototype.hasOwnProperty.call(currentData, raw)) {
          resolvedCode = raw;
          countryData = currentData[raw];
          return true;
        }
        if (Object.prototype.hasOwnProperty.call(currentData, upper)) {
          resolvedCode = upper;
          countryData = currentData[upper];
          return true;
        }
        return false;
      };
      for (const code of candidates) {
        if (tryResolve(code)) break;
      }

      const value = countryData ? (typeof countryData === 'object' ? countryData.value : countryData) : 0;

      // Determine display name with proper fallback logic
      // Prefer localized names from backend when available
      let displayName = null;

      // First, try to get localized name using the resolved code
      const codeToLookup = (resolvedCode || iso2 || iso3 || '').toUpperCase();
      if (codeToLookup && window.countryCodeToName && window.countryCodeToName[codeToLookup]) {
        displayName = window.countryCodeToName[codeToLookup];
      }

      // If not found, try to get name from countryData if it exists and is a proper name (not a code)
      if (!displayName && countryData && typeof countryData === 'object' && countryData.name) {
        const dataName = countryData.name;
        // Check if it's a code (2-3 uppercase letters)
        if (!/^[A-Z]{2,3}$/.test(dataName)) {
          displayName = dataName; // It's a proper name, use it
        }
      }

      // If still not found, try GeoJSON properties
      if (!displayName) {
        displayName = name || props.NAME || props.NAME_LONG || props.ADMIN;
      }

      // If displayName looks like a code or is still not found, try to map it
      if (!displayName || /^[A-Z]{2,3}$/.test(displayName)) {
        // Use the resolved code or ISO2 code to look up the name
        if (codeToLookup && window.countryCodeToName && window.countryCodeToName[codeToLookup]) {
          displayName = window.countryCodeToName[codeToLookup];
        } else if (!displayName) {
          displayName = t('fallbacks.unknownCountry');
        }
      }

      onCountryHover(displayName, value, resolvedCode || iso2 || iso3 || name);
    }
  };

  // Reset highlight function
  const resetHighlight = (e) => {
    geojsonLayerRef.current.resetStyle(e.target);

    // Call the leave callback to reset to global total
    if (onCountryLeave) {
      onCountryLeave();
    }
  };

  // Handle country click
  const onEachFeature = (feature, layer) => {
    layer.on({
      mouseover: highlightFeature,
      mouseout: resetHighlight,
      click: (e) => {
        const geoJsonCountryCode = feature.properties.ISO_A2 || feature.properties.ISO2 || feature.properties.iso_a2;
        const geoJsonCountryName = feature.properties.ADMIN || feature.properties.NAME || feature.properties.name;
        const geoJsonCountryISO3 = feature.properties.ISO_A3 || feature.properties.ISO3 || feature.properties.iso_a3;

        // Use the same mapping logic to find the correct country code
        let countryCode = geoJsonCountryCode;
        let countryData = null;

        // Try direct match first
        const currentData = indicatorDataRef.current || {};
        if (currentData[geoJsonCountryCode]) {
          countryCode = geoJsonCountryCode;
          countryData = currentData[geoJsonCountryCode];
        } else if (window.countryCodeMapping && window.countryCodeMapping[geoJsonCountryCode]) {
          // Try mapping
          const mappedCode = window.countryCodeMapping[geoJsonCountryCode];
          if (currentData[mappedCode]) {
            countryCode = mappedCode;
            countryData = currentData[mappedCode];
          }
        } else if (geoJsonCountryISO3 && currentData[geoJsonCountryISO3]) {
          // Try ISO3 match
          countryCode = geoJsonCountryISO3;
          countryData = currentData[geoJsonCountryISO3];
        } else if (geoJsonCountryName && window.countryCodeMapping && window.countryCodeMapping[geoJsonCountryName.toLowerCase()]) {
          // Try name match
          const mappedCode = window.countryCodeMapping[geoJsonCountryName.toLowerCase()];
          if (currentData[mappedCode]) {
            countryCode = mappedCode;
            countryData = currentData[mappedCode];
          }
        }

        // Get country name with fallback - prefer localized names
        let countryName = null;

        // First, try to get localized name using the country code
        const codeKey = (countryCode || geoJsonCountryCode || geoJsonCountryISO3 || '').toUpperCase();
        if (codeKey && window.countryCodeToName && window.countryCodeToName[codeKey]) {
          countryName = window.countryCodeToName[codeKey];
        }

        // If not found, try to get name from countryData
        if (!countryName && countryData && typeof countryData === 'object' && countryData.name) {
          const dataName = countryData.name;
          // Only use if it's not a code
          if (!/^[A-Z]{2,3}$/.test(dataName)) {
            countryName = dataName;
          }
        }

        // If still not found, use GeoJSON name
        if (!countryName) {
          countryName = geoJsonCountryName;
        }

        // Final fallback: if it looks like a code, try to map it
        if ((!countryName || /^[A-Z]{2,3}$/.test(countryName)) && window.countryCodeToName && codeKey) {
          if (window.countryCodeToName[codeKey]) {
            countryName = window.countryCodeToName[codeKey];
          }
        }

        onCountryClick(countryCode, countryName);
      }
    });
  };

  // Initialize map when component mounts and ref is ready
  useEffect(() => {
    // In country scope we render the Mapbox map and do NOT mount a Leaflet container,
    // so skip Leaflet initialization entirely.
    if (scopeType === 'country') {
      // Cancel any pending retries
      if (retryTimeoutRef.current) {
        clearTimeout(retryTimeoutRef.current);
        retryTimeoutRef.current = null;
      }
      retryCountRef.current = 0;
      // If we are switching from global -> country, ensure Leaflet is torn down.
      if (mapInstanceRef.current) {
        try {
          if (bubbleLayerRef.current) {
            mapInstanceRef.current.removeLayer(bubbleLayerRef.current);
            bubbleLayerRef.current = null;
          }
          mapInstanceRef.current.remove();
        } catch (_e) {
          console.warn('Error removing map instance:', _e);
        }
        mapInstanceRef.current = null;
        geojsonLayerRef.current = null;
        legendRef.current = null;
      }
      // Clear Leaflet references from DOM element if they exist
      if (mapRef.current) {
        if (mapRef.current._leaflet_id) {
          delete mapRef.current._leaflet_id;
        }
        if (mapRef.current._leaflet) {
          delete mapRef.current._leaflet;
        }
      }
      return;
    }

    const MAX_RETRIES = 25; // Maximum 25 retries (5 seconds total)
    const RETRY_DELAY = 200; // 200ms between retries

    const initMap = async () => {
      try {
        // Check if we're still in the correct scope (not country)
        if (scopeType === 'country') {
          retryCountRef.current = 0;
          if (retryTimeoutRef.current) {
            clearTimeout(retryTimeoutRef.current);
            retryTimeoutRef.current = null;
          }
          return;
        }

        // Wait for map ref to be ready
        if (!mapRef.current) {
          retryCountRef.current += 1;
          if (retryCountRef.current > MAX_RETRIES) {
            console.error('Map ref not ready after maximum retries, aborting initialization');
            retryCountRef.current = 0;
            if (retryTimeoutRef.current) {
              clearTimeout(retryTimeoutRef.current);
              retryTimeoutRef.current = null;
            }
            return;
          }
          console.log(`Map ref not ready, retrying in ${RETRY_DELAY}ms (attempt ${retryCountRef.current}/${MAX_RETRIES})`);
          // Clear any existing timeout before scheduling a new one
          if (retryTimeoutRef.current) {
            clearTimeout(retryTimeoutRef.current);
          }
          retryTimeoutRef.current = setTimeout(initMap, RETRY_DELAY);
          return;
        }

        // Reset retry count on success
        retryCountRef.current = 0;

        // Prevent concurrent initializations
        if (isInitializingRef.current) {
          console.log('Map initialization already in progress, skipping');
          return;
        }

        // Check if map is already initialized
        if (mapInstanceRef.current) {
          return;
        }

        // Mark as initializing
        isInitializingRef.current = true;

      // Check if Leaflet has already initialized a map on this container
      if (mapRef.current && mapRef.current._leaflet_id) {
        console.log('Container already has a Leaflet map instance, cleaning up first');
        // Try to get the existing map instance and remove it properly
        try {
          const existingMap = mapRef.current._leaflet;
          if (existingMap && existingMap.remove) {
            existingMap.remove();
          }
        } catch (e) {
          console.warn('Error removing existing map:', e);
        }
        // Clear the Leaflet reference from the DOM element
        delete mapRef.current._leaflet_id;
        // Clear any remaining Leaflet data
        if (mapRef.current._leaflet) {
          delete mapRef.current._leaflet;
        }
        // Wait a tick to ensure cleanup completes
        await new Promise(resolve => setTimeout(resolve, 0));
      }

      // Double-check after cleanup
      if (mapRef.current && mapRef.current._leaflet_id) {
        console.warn('Container still has Leaflet reference after cleanup, aborting initialization');
        isInitializingRef.current = false;
        return;
      }

      try {
        // Import Leaflet with better error handling
        let L;
        try {
          L = (await import('leaflet')).default;
          // Import CSS only once
          if (!document.querySelector('link[href*="leaflet.css"]')) {
            await import('leaflet/dist/leaflet.css');
          }
        } catch (importError) {
          console.error('Failed to import Leaflet:', importError);
          isInitializingRef.current = false;
          return;
        }

        // Fix for default markers in Leaflet
        if (L && L.Icon && L.Icon.Default) {
          delete L.Icon.Default.prototype._getIconUrl;
          L.Icon.Default.mergeOptions({
            iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
            iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
            shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
          });
        }

        // Final check before initialization
        const mapContainer = getConnectedMapContainer();
        if (!mapContainer) {
          console.warn('Map container is not connected; skipping initialization');
          isInitializingRef.current = false;
          return;
        }
        if (mapInstanceRef.current || mapContainer._leaflet_id) {
          console.warn('Map container is already initialized, aborting');
          isInitializingRef.current = false;
          return;
        }

      // Initialize map with better styling
      if (!mapInstanceRef.current) {
        try {
          mapInstanceRef.current = L.map(mapContainer, {
            center: [20, 0],
            zoom: 2,
            zoomControl: false, // Disable default zoom control
            scrollWheelZoom: true,
            dragging: true,
            touchZoom: true,
            doubleClickZoom: true,
            boxZoom: true,
            keyboard: true,
            tap: true,
            attributionControl: false // We'll add custom attribution
          });
        } catch (error) {
          console.error('Error initializing map:', error);
          isInitializingRef.current = false;
          return;
        }

        // Add very simple tile layer (no labels, no terrain)
        L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', {
          attribution: '', // Remove attribution
          subdomains: 'abcd',
          maxZoom: 19,
          minZoom: 2
        }).addTo(mapInstanceRef.current);

        // Remove zoom control - we'll add custom controls later
        // const zoomControl = L.control.zoom({ position: 'bottomleft' });
        // zoomControl.addTo(mapInstanceRef.current);

        // Add enhanced legend (only on desktop)
        const isMobileWidth = typeof window !== 'undefined' && window.innerWidth < 768;
        if (!isMobileWidth) {
          legendRef.current = L.control({ position: 'bottomright' });
          legendRef.current.onAdd = function() {
            const div = L.DomUtil.create('div', 'legend-control');
            div.style.backgroundColor = 'rgba(255, 255, 255, 0.95)';
            div.style.padding = '16px';
            div.style.borderRadius = '12px';
            div.style.boxShadow = '0 4px 20px rgba(0,0,0,0.15)';
            div.style.border = '1px solid rgba(0,0,0,0.1)';
            div.style.backdropFilter = 'blur(10px)';
            div.style.minWidth = '200px';

            // Initial legend content will be set by updateLegend function
            div.innerHTML = `
              <h4 class="font-bold text-humdb-navy mb-3 text-base">${t('globalOverview.map.dataRange')}</h4>
              <div class="text-sm text-humdb-gray-600">${t('common.loading')}</div>
            `;

            return div;
          };
          legendRef.current.addTo(mapInstanceRef.current);
        }
      }
    } catch (error) {
      console.error('Failed to initialize map:', error);
      return;
    }

    // Load enhanced GeoJSON data for world countries with fallback
      const loadGeoJSON = async (url) => {
        try {
          const response = await fetch(url);
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          return await response.json();
        } catch (error) {
          console.error(`Failed to load GeoJSON from ${url}:`, error);
          return null;
        }
      };

      // Try multiple GeoJSON sources
      const geoJsonSources = [
        'https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson',
        'https://raw.githubusercontent.com/holtzy/D3-graph-gallery/master/DATA/world.geojson',
        'https://raw.githubusercontent.com/PublicaMundi/MappingAPI/master/data/geojson/countries.json'
      ];

      let data = null;
      for (const source of geoJsonSources) {
        console.log(`Trying GeoJSON source: ${source}`);
        data = await loadGeoJSON(source);
        if (data && data.features && data.features.length > 0) {
          console.log(`Successfully loaded GeoJSON from: ${source}`);
          break;
        }
      }

      if (!data || !data.features || data.features.length === 0) {
        console.error('All GeoJSON sources failed, using fallback');
        // Fallback: create a simple world outline
        const worldOutline = L.rectangle([[-90, -180], [90, 180]], {
          color: '#374151',
          weight: 1,
          fillColor: '#f8fafc',
          fillOpacity: 0.3
        }).addTo(mapInstanceRef.current);
        return;
      }

      if (geojsonLayerRef.current) {
        mapInstanceRef.current.removeLayer(geojsonLayerRef.current);
      }

      // Debug: Check what countries are in the GeoJSON
      const countriesInGeoJson = data.features.map(f => ({
        code: f.properties['ISO3166-1-Alpha-2'] || f.properties.ISO_A2 || f.properties.ISO2 || f.properties.iso_a2,
        name: f.properties.name || f.properties.ADMIN || f.properties.NAME,
        iso3: f.properties['ISO3166-1-Alpha-3'] || f.properties.ISO_A3 || f.properties.ISO3 || f.properties.iso_a3
      }));
      console.log('Total countries in GeoJSON:', countriesInGeoJson.length);
      console.log('Countries in GeoJSON:', countriesInGeoJson.slice(0, 10)); // First 10
      console.log('Afghanistan in GeoJSON:', countriesInGeoJson.find(c => c.code === 'AF'));

      // Look for Afghanistan with different possible codes
      const afghanistanVariants = countriesInGeoJson.filter(c =>
        c.name && c.name.toLowerCase().includes('afghan')
      );
      console.log('Afghanistan variants found:', afghanistanVariants);

      // Check what properties are available in the first feature
      if (data.features.length > 0) {
        console.log('First feature properties:', data.features[0].properties);
        console.log('Available property keys:', Object.keys(data.features[0].properties));
      }

      // Create a comprehensive country code mapping
      const countryCodeMapping = {};
      const countryCodeToName = {};

      // First, populate from localized countries (backend) if available
      if (localizedCountries && localizedCountries.length > 0) {
        localizedCountries.forEach(country => {
          const iso2 = String(country.iso2 || country.code || '').toUpperCase();
          const iso3 = String(country.iso3 || '').toUpperCase();
          const countryName = country.name || '';
          const nsName = country.national_society_name || countryName;

          if (iso2) {
            countryCodeMapping[iso2] = iso2;
            // Prefer National Society name if available, otherwise country name
            countryCodeToName[iso2] = nsName || countryName;
          }
          if (iso3) {
            countryCodeMapping[iso3] = iso2; // ISO3 to ISO2 mapping
            countryCodeToName[iso3] = nsName || countryName;
          }
          if (countryName) {
            countryCodeMapping[countryName.toLowerCase()] = iso2; // Name to ISO2
          }
        });
      }

      // Fallback to GeoJSON names for countries not in backend data
      countriesInGeoJson.forEach(country => {
        const iso2 = String(country.code || '').toUpperCase();
        const iso3 = String(country.iso3 || '').toUpperCase();

        if (iso2 && !countryCodeToName[iso2]) {
          countryCodeMapping[iso2] = iso2;
          countryCodeToName[iso2] = country.name;
        }
        if (iso3 && !countryCodeToName[iso3]) {
          countryCodeMapping[iso3] = iso2; // ISO3 to ISO2 (fallback)
          countryCodeToName[iso3] = country.name;
        }
        if (country.name && !countryCodeMapping[country.name.toLowerCase()]) {
          countryCodeMapping[country.name.toLowerCase()] = iso2; // Name to ISO2
        }
      });

      // Add manual mappings for common variations
      const manualMappings = {
        'afghanistan': 'AF',
        'af': 'AF',
        'afg': 'AF',
        'usa': 'US',
        'united states': 'US',
        'united states of america': 'US',
        'uk': 'GB',
        'united kingdom': 'GB',
        'great britain': 'GB',
        'russia': 'RU',
        'russian federation': 'RU',
        'china': 'CN',
        'peoples republic of china': 'CN',
        'india': 'IN',
        'brazil': 'BR',
        'france': 'FR',
        'germany': 'DE',
        'japan': 'JP',
        'canada': 'CA',
        'australia': 'AU'
      };

      Object.assign(countryCodeMapping, manualMappings);

      // Store the mapping for use in style function
      window.countryCodeMapping = countryCodeMapping;
      window.countryCodeToName = countryCodeToName;

      console.log('Country code mapping created:', Object.keys(countryCodeMapping).length, 'entries');
      console.log('Sample mappings:', Object.entries(countryCodeMapping).slice(0, 10));

      geojsonLayerRef.current = L.geoJSON(data, {
        style: style,
        onEachFeature: onEachFeature
      }).addTo(mapInstanceRef.current);
      // Signal that the GeoJSON layer is ready (used by flow-line overlay).
      setGeojsonReadyTick((x) => x + 1);

      // Add bubble layer for bubble map visualization
      if (visualizationType === 'bubble') {
        addBubbleLayer();
      }

      // Update legend with initial data
      updateLegend();
    } catch (error) {
      console.error('Error in map initialization:', error);
    } finally {
      // Always reset the initialization flag
      isInitializingRef.current = false;
      // Clear any pending retry timeouts
      if (retryTimeoutRef.current) {
        clearTimeout(retryTimeoutRef.current);
        retryTimeoutRef.current = null;
      }
      retryCountRef.current = 0;
    }
    };

    initMap();

    return () => {
      if (mapInstanceRef.current) {
        // Clean up bubble layer
        if (bubbleLayerRef.current) {
          try {
            mapInstanceRef.current.removeLayer(bubbleLayerRef.current);
          } catch (e) {
            console.warn('Error removing bubble layer:', e);
          }
          bubbleLayerRef.current = null;
        }

        // Clean up flow layer
        if (flowLayerRef.current) {
          try {
            mapInstanceRef.current.removeLayer(flowLayerRef.current);
          } catch (e) {
            console.warn('Error removing flow layer:', e);
          }
          flowLayerRef.current = null;
        }

        try {
          mapInstanceRef.current.remove();
        } catch (e) {
          console.warn('Error removing map instance:', e);
        }
        mapInstanceRef.current = null;
      }

      // Clear Leaflet reference from DOM element
      if (mapRef.current) {
        if (mapRef.current._leaflet_id) {
          delete mapRef.current._leaflet_id;
        }
        if (mapRef.current._leaflet) {
          delete mapRef.current._leaflet;
        }
      }

      geojsonLayerRef.current = null;
      legendRef.current = null;

      // Clear any pending retry timeouts
      if (retryTimeoutRef.current) {
        clearTimeout(retryTimeoutRef.current);
        retryTimeoutRef.current = null;
      }
      retryCountRef.current = 0;
    };
  }, [scopeType, localizedCountries]); // Re-run when switching between global/country scopes or when localized countries load

  // Separate effect to handle visualization type changes
  useEffect(() => {
    // In country scope we render Mapbox; avoid any Leaflet reinit logic (no container exists).
    if (scopeType === 'country') {
      return;
    }

    if (visualizationType === 'barchart') {
      // When switching to bar chart, hide the map container
      console.log('Switching to bar chart, hiding map container');
      if (mapRef.current) {
        mapRef.current.style.display = 'none';
      }
    } else {
      // When switching to any map view (choropleth or bubble)
      console.log('Switching to map view, showing map container');
      if (mapRef.current) {
        mapRef.current.style.display = 'block';
      }

      // If map instance doesn't exist or GeoJSON layer is missing, reinitialize completely
      if (!mapInstanceRef.current || !geojsonLayerRef.current) {
        console.log('Reinitializing map for visualization type:', visualizationType);

        // Clean up existing map if it exists
        if (mapInstanceRef.current) {
          try {
            mapInstanceRef.current.remove();
          } catch (e) {
            console.warn('Error removing map instance:', e);
          }
          mapInstanceRef.current = null;
          geojsonLayerRef.current = null;
          bubbleLayerRef.current = null;
          legendRef.current = null;
        }

        // Clear Leaflet reference from DOM element
        if (mapRef.current) {
          if (mapRef.current._leaflet_id) {
            delete mapRef.current._leaflet_id;
          }
          if (mapRef.current._leaflet) {
            delete mapRef.current._leaflet;
          }
        }

        const initMap = async () => {
          try {
            if (!mapRef.current) {
              console.warn('Leaflet map container not available; skipping Leaflet init.');
              return;
            }

            // Prevent concurrent initializations
            if (isInitializingRef.current) {
              console.log('Map initialization already in progress, skipping');
              return;
            }

            // Check if map is already initialized on this container
            if (mapInstanceRef.current) {
              console.log('Map already initialized, skipping reinitialization');
              return;
            }

            // Mark as initializing
            isInitializingRef.current = true;

            // Check if Leaflet has already initialized a map on this container
            if (mapRef.current && mapRef.current._leaflet_id) {
              console.log('Container already has a Leaflet map instance, cleaning up first');
              // Try to get the existing map instance and remove it properly
              try {
                const existingMap = mapRef.current._leaflet;
                if (existingMap && existingMap.remove) {
                  existingMap.remove();
                }
              } catch (e) {
                console.warn('Error removing existing map:', e);
              }
              // Clear the Leaflet reference from the DOM element
              delete mapRef.current._leaflet_id;
              // Clear any remaining Leaflet data
              if (mapRef.current._leaflet) {
                delete mapRef.current._leaflet;
              }
              // Wait a tick to ensure cleanup completes
              await new Promise(resolve => setTimeout(resolve, 0));
            }

            // Double-check after cleanup
            if (mapRef.current && mapRef.current._leaflet_id) {
              console.warn('Container still has Leaflet reference after cleanup, aborting initialization');
              isInitializingRef.current = false;
              return;
            }

            // Import Leaflet
            let L;
            try {
              L = (await import('leaflet')).default;
              if (!document.querySelector('link[href*="leaflet.css"]')) {
                await import('leaflet/dist/leaflet.css');
              }
            } catch (importError) {
              console.error('Failed to import Leaflet:', importError);
              isInitializingRef.current = false;
              return;
            }

            // Fix for default markers in Leaflet
            if (L && L.Icon && L.Icon.Default) {
              delete L.Icon.Default.prototype._getIconUrl;
              L.Icon.Default.mergeOptions({
                iconRetinaUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon-2x.png',
                iconUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-icon.png',
                shadowUrl: 'https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.7.1/images/marker-shadow.png',
              });
            }

            // Final check before initialization
            const mapContainer = getConnectedMapContainer();
            if (!mapContainer) {
              console.warn('Map container is not connected; skipping Leaflet init.');
              isInitializingRef.current = false;
              return;
            }
            if (mapInstanceRef.current || mapContainer._leaflet_id) {
              console.warn('Map container is already initialized, aborting');
              isInitializingRef.current = false;
              return;
            }

            // Initialize map
            mapInstanceRef.current = L.map(mapContainer, {
              center: [20, 0],
              zoom: 2,
              zoomControl: false,
              scrollWheelZoom: true,
              dragging: true,
              touchZoom: true,
              doubleClickZoom: true,
              boxZoom: true,
              keyboard: true,
              tap: true,
              attributionControl: false
            });

            // Add tile layer
            L.tileLayer('https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png', {
              attribution: '',
              subdomains: 'abcd',
              maxZoom: 19,
              minZoom: 2
            }).addTo(mapInstanceRef.current);

            // Add legend (only on desktop)
            const isMobileWidth = typeof window !== 'undefined' && window.innerWidth < 768;
            if (!isMobileWidth) {
              legendRef.current = L.control({ position: 'bottomright' });
              legendRef.current.onAdd = function() {
                const div = L.DomUtil.create('div', 'legend-control');
                div.style.backgroundColor = 'rgba(255, 255, 255, 0.95)';
                div.style.padding = '16px';
                div.style.borderRadius = '12px';
                div.style.boxShadow = '0 4px 20px rgba(0,0,0,0.15)';
                div.style.border = '1px solid rgba(0,0,0,0.1)';
                div.style.backdropFilter = 'blur(10px)';
                div.style.minWidth = '200px';

                div.innerHTML = `
                  <h4 class="font-bold text-humdb-navy mb-3 text-base">${t('globalOverview.map.dataRange')}</h4>
                  <div class="text-sm text-humdb-gray-600">${t('common.loading')}</div>
                `;

                return div;
              };
              legendRef.current.addTo(mapInstanceRef.current);
            }

            // Load GeoJSON and create map layer
            const loadGeoJSON = async (url) => {
              try {
                const response = await fetch(url);
                if (!response.ok) throw new Error(`HTTP ${response.status}`);
                return await response.json();
              } catch (error) {
                console.error(`Failed to load GeoJSON from ${url}:`, error);
                return null;
              }
            };

            const geoJsonSources = [
              'https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson',
              'https://raw.githubusercontent.com/holtzy/D3-graph-gallery/master/DATA/world.geojson',
              'https://raw.githubusercontent.com/PublicaMundi/MappingAPI/master/data/geojson/countries.json'
            ];

            let data = null;
            for (const source of geoJsonSources) {
              data = await loadGeoJSON(source);
              if (data && data.features && data.features.length > 0) {
                break;
              }
            }

            if (data && data.features && data.features.length > 0) {
              // Create country code mapping
              const countriesInGeoJson = data.features.map(f => ({
                code: f.properties['ISO3166-1-Alpha-2'] || f.properties.ISO_A2 || f.properties.ISO2 || f.properties.iso_a2,
                name: f.properties.name || f.properties.ADMIN || f.properties.NAME,
                iso3: f.properties['ISO3166-1-Alpha-3'] || f.properties.ISO_A3 || f.properties.ISO3 || f.properties.iso_a3
              }));

              const countryCodeMapping = {};
              const countryCodeToName = {};

              // First, populate from localized countries (backend) if available
              if (localizedCountries && localizedCountries.length > 0) {
                localizedCountries.forEach(country => {
                  const iso2 = String(country.iso2 || country.code || '').toUpperCase();
                  const iso3 = String(country.iso3 || '').toUpperCase();
                  const countryName = country.name || '';
                  const nsName = country.national_society_name || countryName;

                  if (iso2) {
                    countryCodeMapping[iso2] = iso2;
                    countryCodeToName[iso2] = nsName || countryName;
                  }
                  if (iso3) {
                    countryCodeMapping[iso3] = iso2;
                    countryCodeToName[iso3] = nsName || countryName;
                  }
                  if (countryName) {
                    countryCodeMapping[countryName.toLowerCase()] = iso2;
                  }
                });
              }

              // Fallback to GeoJSON names for countries not in backend data
              countriesInGeoJson.forEach(country => {
                const iso2 = String(country.code || '').toUpperCase();
                const iso3 = String(country.iso3 || '').toUpperCase();

                if (iso2 && !countryCodeToName[iso2]) {
                  countryCodeMapping[iso2] = iso2;
                  countryCodeToName[iso2] = country.name;
                }
                if (iso3 && !countryCodeToName[iso3]) {
                  countryCodeMapping[iso3] = iso2;
                  countryCodeToName[iso3] = country.name;
                }
                if (country.name && !countryCodeMapping[country.name.toLowerCase()]) {
                  countryCodeMapping[country.name.toLowerCase()] = iso2;
                }
              });

              window.countryCodeToName = countryCodeToName;

              const manualMappings = {
                'afghanistan': 'AF',
                'af': 'AF',
                'afg': 'AF',
                'usa': 'US',
                'united states': 'US',
                'united states of america': 'US',
                'uk': 'GB',
                'united kingdom': 'GB',
                'great britain': 'GB',
                'russia': 'RU',
                'russian federation': 'RU',
                'china': 'CN',
                'peoples republic of china': 'CN',
                'india': 'IN',
                'brazil': 'BR',
                'france': 'FR',
                'germany': 'DE',
                'japan': 'JP',
                'canada': 'CA',
                'australia': 'AU'
              };

              Object.assign(countryCodeMapping, manualMappings);
              window.countryCodeMapping = countryCodeMapping;

              // Guard against races: async GeoJSON loading can finish after map teardown.
              const currentMap = mapInstanceRef.current;
              if (!currentMap) {
                console.warn('Map instance unavailable while attaching GeoJSON; skipping layer add.');
                return;
              }

              geojsonLayerRef.current = L.geoJSON(data, {
                style: style,
                onEachFeature: onEachFeature
              }).addTo(currentMap);
              // Signal that the GeoJSON layer is ready (used by flow-line overlay).
              setGeojsonReadyTick((x) => x + 1);

              // Add bubble layer if needed
              if (visualizationType === 'bubble') {
                addBubbleLayer();
              }

              // Update legend
              updateLegend();

              // Apply current data if available
              if (indicatorData && Object.keys(indicatorData).length > 0) {
                console.log('Applying current data to newly initialized map');
                geojsonLayerRef.current.setStyle(style);
              }

              // Trigger map resize to ensure proper rendering
              setTimeout(() => {
                if (mapInstanceRef.current) {
                  mapInstanceRef.current.invalidateSize();
                }
              }, 100);
            }
          } catch (error) {
            console.error('Failed to initialize map:', error);
          } finally {
            // Always reset the initialization flag
            isInitializingRef.current = false;
          }
        };

        // Defer so ref is attached (refs are set after commit; effect runs in same tick)
        let rafAttempts = 0;
        const maxRafAttempts = 20;
        const runInit = () => {
          if (mapRef.current) {
            initMap();
            return;
          }
          if (rafAttempts < maxRafAttempts) {
            rafAttempts += 1;
            requestAnimationFrame(runInit);
          } else {
            console.warn('Leaflet map container not available after defer; skipping Leaflet init.');
          }
        };
        requestAnimationFrame(runInit);
      } else {
        // Map instance and GeoJSON layer exist, just update visualization type
        console.log('Updating existing map for visualization type:', visualizationType);

        if (visualizationType === 'bubble') {
          addBubbleLayer();
        } else if (bubbleLayerRef.current) {
          mapInstanceRef.current.removeLayer(bubbleLayerRef.current);
          bubbleLayerRef.current = null;
        }

        updateLegend();

        // Trigger map resize to ensure proper rendering
        setTimeout(() => {
          if (mapInstanceRef.current) {
            mapInstanceRef.current.invalidateSize();
          }
        }, 100);
      }
    }
  }, [visualizationType, scopeType]);

  // Update legend when component first mounts with data
  useEffect(() => {
    if (!isMobile && legendRef.current && mapInstanceRef.current && indicatorData && Object.keys(indicatorData).length > 0) {
      updateLegend();
    }
  }, [indicatorData, showFullValues, isMobile]);
  // Keep latest indicatorData in a ref so event handlers don't capture stale values
  useEffect(() => {
    indicatorDataRef.current = indicatorData;
  }, [indicatorDataSignature]);

  // Update map when data changes - Optimized for performance with debouncing
  useEffect(() => {
    console.log('Map component received new indicatorData:', {
      indicatorData,
      type: typeof indicatorData,
      isArray: Array.isArray(indicatorData),
      keys: Object.keys(indicatorData || {}),
      selectedIndicator,
      hasData: indicatorData && Object.keys(indicatorData).length > 0
    });

    // Clear any pending update
    if (updateTimeoutRef.current) {
      clearTimeout(updateTimeoutRef.current);
    }

    // Debounce the update to prevent excessive re-renders
    updateTimeoutRef.current = setTimeout(() => {
      if (geojsonLayerRef.current && mapInstanceRef.current) {
        console.log('Updating map style with new data');

        // Use requestAnimationFrame for smoother updates
        requestAnimationFrame(() => {
          geojsonLayerRef.current.setStyle(style);

          // Handle bubble layer - recreate when data changes to handle region filtering
          if (visualizationType === 'bubble') {
            // Remove existing bubble layer if it exists
            if (bubbleLayerRef.current) {
              mapInstanceRef.current.removeLayer(bubbleLayerRef.current);
              bubbleLayerRef.current = null;
            }
            // Create new bubble layer with filtered data
            addBubbleLayer();
          } else if (bubbleLayerRef.current) {
            // Remove bubble layer for other visualization types
            mapInstanceRef.current.removeLayer(bubbleLayerRef.current);
            bubbleLayerRef.current = null;
          }

          // Update legend with new data
          updateLegend();
        });
      } else if (mapInstanceRef.current && !geojsonLayerRef.current && visualizationType !== 'barchart') {
        console.log('Map instance exists but GeoJSON layer missing, triggering layer recreation');
        // Trigger the visualization type change effect to recreate layers
        // This will be handled by the visualization type change effect
      } else {
        console.log('Map not ready for update:', {
          hasGeoJsonLayer: !!geojsonLayerRef.current,
          hasMapInstance: !!mapInstanceRef.current,
          visualizationType: visualizationType
        });
      }
    }, 50); // 50ms debounce delay

    // Cleanup timeout on unmount
    return () => {
      if (updateTimeoutRef.current) {
        clearTimeout(updateTimeoutRef.current);
      }
    };
  }, [indicatorData, selectedIndicator, visualizationType]);

  // Force map update when data becomes available (fix for initial render issue)
  useEffect(() => {
    if (indicatorData && Object.keys(indicatorData).length > 0 && geojsonLayerRef.current && mapInstanceRef.current) {
      console.log('Force updating map with newly available data');
      // Small delay to ensure map is fully rendered
      setTimeout(() => {
        if (geojsonLayerRef.current && mapInstanceRef.current) {
          geojsonLayerRef.current.setStyle(style);
          updateLegend();
        }
      }, 100);
    }
  }, [indicatorData]);

  // Zoom to region when selectedRegion changes
  useEffect(() => {
    if (mapInstanceRef.current && selectedRegion) {
      // Small delay to ensure map is fully loaded
      setTimeout(() => {
        zoomToRegion(selectedRegion);
      }, 100);
    }
  }, [selectedRegion]);

  // Bar Chart Component
  const BarChart = () => {
    const chartRef = useRef(null);
    const animationFunctionRef = useRef(null);
    const boundaryCacheRef = useRef(new Map()); // `${ISO3}:${ADM}` -> geojson

    useEffect(() => {
      if (visualizationType !== 'barchart') return;

      const renderChart = () => {
        const chartContainer = chartRef.current;
        if (!chartContainer) return;

        // Clear previous content
        chartContainer.innerHTML = '';

        const currentIndicatorData = indicatorDataRef.current || {};

        const normalizeKey = (v) => {
          if (v == null) return '';
          return String(v).trim().toLowerCase().replace(/[\s\W_]+/g, '');
        };

        const buildLookup = (dataMap) => {
          const lookup = new Map();
          if (!dataMap || typeof dataMap !== 'object') return lookup;
          for (const [k, v] of Object.entries(dataMap)) {
            const val = typeof v === 'object' && v ? Number(v.value) : Number(v);
            const name = typeof v === 'object' && v ? v.name : null;
            if (!Number.isFinite(val)) continue;
            const add = (key) => {
              const nk = normalizeKey(key);
              if (!nk) return;
              if (!lookup.has(nk)) lookup.set(nk, { value: val, name });
            };
            add(k);
            add(String(k).toUpperCase());
            add(String(k).toLowerCase());
            if (name) add(name);
          }
          return lookup;
        };

        const isCountryScope = scopeType === 'country' && scopeCountryIso3;
        let chartDataMap = currentIndicatorData;
        let countLabel = t('globalOverview.map.countries');

        if (isCountryScope) {
          const iso3 = String(scopeCountryIso3).toUpperCase();
          const adm = String(countryAdmLevel || 'ADM1').toUpperCase();
          countLabel = t('globalOverview.map.areas');

          const cacheKey = `${iso3}:${adm}`;
          const cached = boundaryCacheRef.current.get(cacheKey);

          const proceedWithGeo = (geojson) => {
            if (!geojson?.features?.length) return null;
            const lookup = buildLookup(currentIndicatorData);
            const adminMap = {};
            let anyMatched = false;

            for (const f of geojson.features) {
              const p = f.properties || {};
              const name = p.shapeName || p.name || p.NAME || null;
              const keys = [p.shapeID, p.shapeISO, p.shapeName, p.name, p.NAME].filter(Boolean);
              let matched = null;
              for (const cand of keys) {
                const hit = lookup.get(normalizeKey(cand));
                if (hit) { matched = hit; break; }
              }
              if (matched) anyMatched = true;
              const v = matched ? matched.value : 0;
              const id = p.shapeID || p.shapeISO || name || String(Math.random());
              adminMap[id] = { value: Number(v) || 0, name: matched?.name || name || String(id) };
            }

            // If no admin-level values exist, still render ADM bars so the chart corresponds to the selected admin level.
            // We distribute the country total uniformly as a fallback (better UX than a single bar).
            if (!anyMatched) {
              const iso2 = scopeCountryIso2 ? String(scopeCountryIso2).toUpperCase() : null;
              const iso3 = scopeCountryIso3 ? String(scopeCountryIso3).toUpperCase() : null;
              const countryValue = iso2 && currentIndicatorData && currentIndicatorData[iso2] ? (currentIndicatorData[iso2].value || 0) : 0;

              // Get localized country name
              let countryName = null;
              if (iso2 && window.countryCodeToName && window.countryCodeToName[iso2]) {
                countryName = window.countryCodeToName[iso2];
              } else if (iso3 && window.countryCodeToName && window.countryCodeToName[iso3]) {
                countryName = window.countryCodeToName[iso3];
              } else if (iso2 && currentIndicatorData && currentIndicatorData[iso2] && currentIndicatorData[iso2].name) {
                // Fallback to indicatorData name if localized name not available
                const dataName = currentIndicatorData[iso2].name;
                // Only use if it's not a code
                if (!/^[A-Z]{2,3}$/.test(dataName)) {
                  countryName = dataName;
                }
              }

              // Final fallbacks
              if (!countryName) {
                countryName = regionName || iso2 || iso3 || t('globalOverview.map.selectedCountry');
              }
              const n = geojson.features.length || 1;
              const uniform = (Number(countryValue) || 0) / n;
              // Overwrite values uniformly while keeping ADM names
              for (const key of Object.keys(adminMap)) {
                adminMap[key] = { ...adminMap[key], value: uniform };
              }
              countLabel = t('globalOverview.map.areasEstimated');
              return adminMap;
            }

            return adminMap;
          };

          if (cached) {
            const mapped = proceedWithGeo(cached);
            if (mapped) chartDataMap = mapped;
          } else {
            // Best-effort fetch; if it fails we'll just show current (country) data
            fetchGeoBoundaries(iso3, adm)
              .then(gj => {
                if (!gj) return;
                boundaryCacheRef.current.set(cacheKey, gj);
                // Re-render after async fetch
                try { renderChart(); } catch (_e) {}
              })
              .catch(() => {});
            // fall through with current chartDataMap until fetch completes
          }
        }

        // Sort entities by value
        const sortedData = Object.entries(chartDataMap || {})
          .map(([code, data]) => ({
            code,
            name: typeof data === 'object' ? data.name : code,
            value: typeof data === 'object' ? data.value : data
          }))
          .filter(item => item.value > 0)
          .sort((a, b) => b.value - a.value);

        if (sortedData.length === 0) {
          chartContainer.innerHTML = `
            <div class="flex items-center justify-center h-full">
              <div class="text-center">
                <p class="text-gray-500 text-lg">${t('data.noDataAvailable')}</p>
              </div>
            </div>
          `;
          return;
        }

        const maxValue = Math.max(...sortedData.map(item => item.value));
        const barHeight = 20;
        const barSpacing = 8;
        const totalHeight = sortedData.length * (barHeight + barSpacing);

        // Calculate available height: full container height minus padding
        const containerHeight = 600; // Full container height (md:h-[600px])
        const padding = 48; // Top and bottom padding (p-6 = 24px each)
        const availableHeight = containerHeight - padding;

        // Create scrollable container
        const scrollContainer = document.createElement('div');
        scrollContainer.style.cssText = `
          width: 100%;
          height: ${availableHeight}px;
          overflow-y: auto;
          overflow-x: hidden;
          padding-right: 8px;
          scrollbar-width: thin;
          scrollbar-color: #ef4444 #f3f4f6;
          position: relative;
        `;

        // Add custom scrollbar styles for webkit browsers
        const styleId = 'humdb-barchart-scrollbar-style';
        if (!document.getElementById(styleId)) {
          const style = document.createElement('style');
          style.id = styleId;
          style.textContent = `
            .custom-scrollbar::-webkit-scrollbar {
              width: 8px;
            }
            .custom-scrollbar::-webkit-scrollbar-track {
              background: #f3f4f6;
              border-radius: 4px;
            }
            .custom-scrollbar::-webkit-scrollbar-thumb {
              background: #ef4444;
              border-radius: 4px;
            }
            .custom-scrollbar::-webkit-scrollbar-thumb:hover {
              background: #dc2626;
            }
          `;
          document.head.appendChild(style);
        }
        scrollContainer.classList.add('custom-scrollbar');

        // Create SVG with full height for all bars
        const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
        svg.setAttribute('width', '100%');
        svg.setAttribute('height', `${totalHeight}px`);
        svg.setAttribute('viewBox', `0 0 800 ${totalHeight}`);

        // Create bar chart race animation
        const createBarChartRace = () => {
          // Clear previous content
          svg.innerHTML = '';

          // Create groups for each bar (bar + name + value)
          sortedData.forEach((item, index) => {
            const targetY = index * (barHeight + barSpacing);
            const barWidth = (item.value / maxValue) * 600;

            // Create group for this bar
            const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
            group.setAttribute('data-country', item.code);

            // Bar
            const bar = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
            bar.setAttribute('x', 150);
            bar.setAttribute('y', targetY);
            bar.setAttribute('width', barWidth);
            bar.setAttribute('height', barHeight);
            bar.setAttribute('fill', '#ef4444');
            bar.setAttribute('rx', '4');

            // Country name
            const nameText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            nameText.setAttribute('x', 140);
            nameText.setAttribute('y', targetY + barHeight / 2 + 4);
            nameText.setAttribute('text-anchor', 'end');
            nameText.setAttribute('font-size', '12');
            nameText.setAttribute('fill', '#374151');
            nameText.textContent = item.name.length > 12 ? item.name.substring(0, 12) + '...' : item.name;

            // Value
            const valueText = document.createElementNS('http://www.w3.org/2000/svg', 'text');
            valueText.setAttribute('x', 160 + barWidth);
            valueText.setAttribute('y', targetY + barHeight / 2 + 4);
            valueText.setAttribute('font-size', '12');
            valueText.setAttribute('fill', '#374151');
            valueText.setAttribute('font-weight', 'bold');
            valueText.textContent = formatNumber(item.value, showFullValues);

            group.appendChild(bar);
            group.appendChild(nameText);
            group.appendChild(valueText);
            svg.appendChild(group);
          });
        };

        // Initial render
        createBarChartRace();

        // Function to animate bar chart race
        const animateBarChartRace = (newData) => {
          if (!newData || Object.keys(newData).length === 0) return;

          // Sort new data
          const newSortedData = Object.entries(newData)
            .map(([code, data]) => ({
              code,
              name: typeof data === 'object' ? data.name : code,
              value: typeof data === 'object' ? data.value : data
            }))
            .filter(item => item.value > 0)
            .sort((a, b) => b.value - a.value);

          const newMaxValue = Math.max(...newSortedData.map(item => item.value));

          // Get current positions and create a map of current groups
          const currentGroups = Array.from(svg.querySelectorAll('g[data-country]'));
          const currentPositions = {};
          const groupMap = {};

          currentGroups.forEach((group, index) => {
            const country = group.getAttribute('data-country');
            const currentY = index * (barHeight + barSpacing);
            currentPositions[country] = currentY;
            groupMap[country] = group;
          });

          // Calculate new positions
          const newPositions = {};
          newSortedData.forEach((item, index) => {
            const targetY = index * (barHeight + barSpacing);
            newPositions[item.code] = targetY;
          });

          // Animate each bar to its new position
          newSortedData.forEach((newItem, newIndex) => {
            const country = newItem.code;
            const group = groupMap[country];

            if (group) {
              const currentY = currentPositions[country];
              const newY = newPositions[country];
              const newBarWidth = (newItem.value / newMaxValue) * 600;

              // Get elements
              const bar = group.querySelector('rect');
              const nameText = group.querySelector('text:first-of-type');
              const valueText = group.querySelector('text:last-of-type');

              // Animate Y position with smooth movement
              const animatePosition = () => {
                const startTime = performance.now();
                const duration = 1200; // 1.2 seconds for smooth movement
                const yDiff = newY - currentY;

                const animate = (currentTime) => {
                  const elapsed = currentTime - startTime;
                  const progress = Math.min(elapsed / duration, 1);

                  // Ease-out function for smooth deceleration
                  const easeOut = 1 - Math.pow(1 - progress, 3);
                  const currentYPos = currentY + (yDiff * easeOut);

                  // Update positions smoothly
                  group.setAttribute('transform', `translate(0, ${currentYPos - newY})`);

                  if (progress < 1) {
                    requestAnimationFrame(animate);
                  } else {
                    // Final position - remove transform and set actual position
                    group.removeAttribute('transform');
                    bar.setAttribute('y', newY);
                    nameText.setAttribute('y', newY + barHeight / 2 + 4);
                    valueText.setAttribute('y', newY + barHeight / 2 + 4);
                  }
                };

                requestAnimationFrame(animate);
              };

              // Animate bar width
              const animateWidth = () => {
                const startTime = performance.now();
                const duration = 1200; // 1.2 seconds
                const currentWidth = parseFloat(bar.getAttribute('width'));
                const widthDiff = newBarWidth - currentWidth;

                const animate = (currentTime) => {
                  const elapsed = currentTime - startTime;
                  const progress = Math.min(elapsed / duration, 1);

                  // Ease-out function
                  const easeOut = 1 - Math.pow(1 - progress, 3);
                  const currentWidth = parseFloat(bar.getAttribute('width')) + (widthDiff * easeOut);

                  bar.setAttribute('width', currentWidth);
                  valueText.setAttribute('x', 160 + currentWidth);
                  valueText.textContent = formatNumber(newItem.value, showFullValues);

                  if (progress < 1) {
                    requestAnimationFrame(animate);
                  }
                };

                requestAnimationFrame(animate);
              };

              // Start both animations with slight delay for staggered effect
              setTimeout(() => {
                animatePosition();
                animateWidth();
              }, newIndex * 50); // Stagger animations by 50ms
            }
          });
        };

        scrollContainer.appendChild(svg);
        chartContainer.appendChild(scrollContainer);

        // Store animation function in ref for external access
        animationFunctionRef.current = animateBarChartRace;

        // Add data count indicator
        const countIndicator = document.createElement('div');
        countIndicator.style.cssText = `
          position: absolute;
          bottom: 20px;
          right: 60px;
          background: rgba(255, 255, 255, 0.9);
          padding: 4px 8px;
          border-radius: 12px;
          font-size: 12px;
          color: #6b7280;
          font-weight: 500;
          backdrop-filter: blur(4px);
          border: 1px solid rgba(0, 0, 0, 0.1);
          z-index: 50;
        `;
        countIndicator.textContent = `${sortedData.length} ${countLabel}`;
        // Add scroll to top button
        const scrollToTopBtn = document.createElement('button');
        scrollToTopBtn.innerHTML = '↑';
        scrollToTopBtn.style.cssText = `
          position: absolute;
          bottom: 16px;
          right: 16px;
          width: 40px;
          height: 40px;
          background: #ef4444;
          color: white;
          border: none;
          border-radius: 50%;
          font-size: 18px;
          font-weight: bold;
          cursor: pointer;
          opacity: 0;
          transition: opacity 0.3s ease;
          box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
          z-index: 10;
          pointer-events: auto;
        `;
        scrollToTopBtn.title = t('globalOverview.map.scrollToTop');

        scrollToTopBtn.addEventListener('click', () => {
          if (scrollContainer && scrollContainer.isConnected) {
            scrollContainer.scrollTo({ top: 0, behavior: 'smooth' });
          }
        });

        // Show/hide scroll to top button based on scroll position
        scrollContainer.addEventListener('scroll', () => {
          if (!scrollContainer || !scrollContainer.isConnected) return;
          if (scrollContainer.scrollTop > 100) {
            scrollToTopBtn.style.opacity = '1';
          } else {
            scrollToTopBtn.style.opacity = '0';
          }
        });

        chartContainer.appendChild(scrollToTopBtn);

        // Add data count indicator to main container
        const mainContainer = chartRef.current.parentElement;
        if (mainContainer) {
          mainContainer.appendChild(countIndicator);
        }
      };

      renderChart();

      // If this is a data update (not initial render), trigger bar chart race animation
      if (chartRef.current && indicatorData && Object.keys(indicatorData).length > 0 && animationFunctionRef.current) {
        // Small delay to ensure the chart is rendered
        setTimeout(() => {
          if (animationFunctionRef.current) {
            animationFunctionRef.current(indicatorData);
          }
        }, 200);
      }
    }, [indicatorDataSignature, selectedIndicator, visualizationType, showFullValues, scopeType, scopeCountryIso2, scopeCountryIso3, countryAdmLevel, regionName]);

    return (
      <div className="relative">
        {/* Mobile: Total Box Above Chart */}
        {isMobile && (
          <div className="mb-3">
            <div className="bg-white rounded-lg shadow-md p-3 border border-gray-200">
              <div className="text-center">
                <h3 className="text-xs font-semibold text-humdb-gray-600 mb-1">
                  {hoveredCountry ? hoveredCountry : (regionName || t('globalOverview.map.globalTotal'))}
                </h3>
                {isLoadingData ? (
                  <div className="text-base font-bold text-humdb-navy animate-pulse">
                    {t('common.loading')}
                  </div>
                ) : (
                  <>
                    <div className="text-xl font-bold text-humdb-red mb-1">
                      {hoveredCountry ? formatNumber(hoveredValue, showFullValues) : formatNumber(globalTotal, showFullValues)}
                    </div>
                    <div className="text-xs text-humdb-gray-500 break-words leading-relaxed">
                      {indicatorName || selectedIndicator.replace('-', ' ')}
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Desktop: Total Box Inside Chart - Positioned to avoid toggle buttons */}
        {!isMobile && (
          <div className={`absolute left-6 top-8 z-30 bg-white rounded-xl shadow-xl p-6 w-[220px] border border-gray-200 backdrop-blur-sm transition-opacity duration-200 ${isTooltipVisible ? 'opacity-0 pointer-events-none' : 'opacity-100'}`}>
            <div className="text-center">
              <h3 className="text-sm font-semibold text-humdb-gray-600 mb-2">
                {hoveredCountry ? hoveredCountry : (regionName || t('globalOverview.map.globalTotal'))}
              </h3>
              {isLoadingData ? (
                <div className="text-lg font-bold text-humdb-navy animate-pulse">
                  {t('common.loading')}
                </div>
              ) : (
                <>
                  <div className="text-3xl font-bold text-humdb-red mb-2">
                    {hoveredCountry ? formatNumber(hoveredValue, showFullValues) : formatNumber(globalTotal, showFullValues)}
                  </div>
                  <div className="text-xs text-humdb-gray-500 break-words leading-relaxed">
                    {indicatorName || selectedIndicator.replace('-', ' ')}
                  </div>
                </>
              )}
            </div>
          </div>
        )}
        <div className="w-full h-96 md:h-[600px] rounded-xl overflow-hidden shadow-lg relative z-10">
          {/* Admin level toggle (country scope only) */}
          {scopeType === 'country' && (
            <div className="absolute bottom-4 right-4 z-[1000] bg-white/95 rounded-lg shadow-lg p-2 border border-gray-200">
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-semibold text-gray-600 uppercase tracking-wide">{t('globalOverview.map.admin')}</span>
                <div className="flex gap-1">
                  {countryAvailableAdmLevels.map((lvl) => {
                    const active = String(countryAdmLevel || '').toUpperCase() === String(lvl || '').toUpperCase();
                    return (
                      <button
                        key={lvl}
                        onClick={() => setCountryAdmLevel(String(lvl || '').toUpperCase())}
                        className={`px-2 py-1 rounded-md text-[11px] font-semibold transition-all ${
                          active ? 'bg-humdb-red text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                        }`}
                        title={t('globalOverview.map.showAdmin', { level: lvl })}
                      >
                        {lvl}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
          {/* Visualization Type Toggle - On Top of Chart */}
          <div className="absolute top-4 right-4 z-[1000] bg-white rounded-lg shadow-lg p-2 border border-gray-200">
            <div className="flex gap-1">
              <button
                onClick={() => onVisualizationTypeChange('choropleth')}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-all duration-200 flex items-center justify-center ${
                  visualizationType === 'choropleth'
                    ? 'bg-humdb-red text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
                title={t('globalOverview.map.choroplethMap')}
              >
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="w-4 h-4">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 6.75V15m6-6v8.25m.503 3.498 4.875-2.437c.381-.19.622-.58.622-1.006V4.82c0-.836-.88-1.38-1.628-1.006l-3.869 1.934c-.317.159-.69.159-1.006 0L9.503 3.252a1.125 1.125 0 0 0-1.006 0L3.622 5.689C3.24 5.88 3 6.27 3 6.695V19.18c0 .836.88 1.38 1.628 1.006l3.869-1.934c.317-.159.69-.159 1.006 0l4.994 2.497c.317.158.69.158 1.006 0Z" />
                </svg>
              </button>
              <button
                onClick={() => onVisualizationTypeChange('bubble')}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-all duration-200 flex items-center justify-center ${
                  visualizationType === 'bubble'
                    ? 'bg-humdb-red text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
                title={t('globalOverview.map.bubbleMap')}
              >
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="w-4 h-4">
                  <circle cx="8" cy="8" r="3" />
                  <circle cx="16" cy="8" r="2" />
                  <circle cx="12" cy="16" r="4" />
                </svg>
              </button>
              <button
                onClick={() => onVisualizationTypeChange('barchart')}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-all duration-200 flex items-center justify-center ${
                  visualizationType === 'barchart'
                    ? 'bg-humdb-red text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
                title={t('globalOverview.map.barChart')}
              >
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="w-4 h-4">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 0 1 3 19.875v-6.75ZM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V8.625ZM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V4.125Z" />
                </svg>
              </button>
              <div className="border-l border-gray-300 mx-1"></div>
              <button
                onClick={() => setShowFullValues(!showFullValues)}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-all duration-200 ${
                  showFullValues
                    ? 'bg-blue-500 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
                title={showFullValues ? t('globalOverview.map.showAbbreviated') : t('globalOverview.map.showFull')}
              >
                {showFullValues ? '1.2K' : '1,234'}
              </button>
            </div>
          </div>

          {/* Animation Controls - Only show for bar chart */}
          {availableYears.length > 1 && (
            <div className="absolute bottom-8 left-8 z-[1000]" style={{ left: '120px' }}>
              <button
                onClick={isAnimating ? stopAnimation : startAnimation}
                className={`w-10 h-10 rounded-full bg-red-500 text-white transition-all duration-300 ease-in-out flex items-center justify-center shadow-lg ${
                  isAnimating
                    ? 'opacity-100 scale-110'
                    : 'opacity-50 hover:opacity-100 hover:bg-red-600 hover:scale-105'
                }`}
                title={isAnimating ? t('globalOverview.map.stopAnimation') : t('globalOverview.map.startBarChartRace')}
              >
                {isAnimating ? (
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                    <rect x="6" y="4" width="4" height="16" rx="1"/>
                    <rect x="14" y="4" width="4" height="16" rx="1"/>
                  </svg>
                ) : (
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M8 5v14l11-7z"/>
                  </svg>
                )}
              </button>
            </div>
          )}

          {/* Year Timeline Overlay - Bottom Left */}
          {yearTimeline && (
            <div className="absolute bottom-8 left-8 z-[1000]">
              {yearTimeline}
            </div>
          )}

          {/* Chart Container */}
          <div
            ref={chartRef}
            className="absolute inset-0 rounded-xl overflow-hidden shadow-lg bg-white p-6"
          >
          </div>
        </div>

        {/* Mobile: Legend Below Chart */}
        {isMobile && (
          <div className="mt-3">
            <div className="bg-white rounded-lg shadow-md p-3 border border-gray-200">
              {renderMobileLegend()}
            </div>
          </div>
        )}
      </div>
    );
  };

  // Create loading component for server-side rendering
  const loadingComponent = (
    <div className="relative">
      <div className="absolute left-4 top-4 z-30 bg-white rounded-xl shadow-xl p-6 min-w-[220px] border border-gray-200 backdrop-blur-sm">
        <div className="text-center">
          <h3 className="text-sm font-semibold text-humdb-gray-600 mb-2">
            {hoveredCountry ? hoveredCountry : (regionName || t('globalOverview.map.globalTotal'))}
          </h3>
          <div className="text-lg font-bold text-humdb-navy animate-pulse">
            Loading...
          </div>
        </div>
      </div>
      <div className="w-full h-96 md:h-[600px] rounded-xl overflow-hidden bg-gradient-to-br from-gray-50 to-gray-100 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-16 w-16 border-4 border-humdb-red border-t-transparent mx-auto mb-6"></div>
          <p className="text-humdb-gray-600 text-lg font-medium">{t('common.loading')}</p>
        </div>
      </div>
      {/* Year Timeline Overlay - Bottom Left */}
      {yearTimeline && (
        <div className="absolute bottom-8 left-8 z-30">
          {yearTimeline}
        </div>
      )}
    </div>
  );

  const isBarChart = visualizationType === 'barchart';

  // In country scope, bar chart doesn't depend on Leaflet/Mapbox lifecycle.
  if (scopeType === 'country' && isBarChart) {
    return (
      <MapSafe loadingComponent={loadingComponent} className="relative">
        <BarChart />
      </MapSafe>
    );
  }

  // In country scope, use Mapbox for the map views.
  if (scopeType === 'country') {
    const iso2 = scopeCountryIso2 ? String(scopeCountryIso2).toUpperCase() : null;
    const iso3 = scopeCountryIso3 ? String(scopeCountryIso3).toUpperCase() : null;
    const countryValue = iso2 && indicatorData && indicatorData[iso2] ? (indicatorData[iso2].value || 0) : 0;

    // Get localized country name
    let countryName = null;
    if (iso2 && window.countryCodeToName && window.countryCodeToName[iso2]) {
      countryName = window.countryCodeToName[iso2];
    } else if (iso3 && window.countryCodeToName && window.countryCodeToName[iso3]) {
      countryName = window.countryCodeToName[iso3];
    } else if (iso2 && indicatorData && indicatorData[iso2] && indicatorData[iso2].name) {
      // Fallback to indicatorData name if localized name not available
      const dataName = indicatorData[iso2].name;
      // Only use if it's not a code
      if (!/^[A-Z]{2,3}$/.test(dataName)) {
        countryName = dataName;
      }
    }

    // Final fallbacks
    if (!countryName) {
      countryName = regionName || iso2 || t('globalOverview.map.selectedCountry');
    }

    return (
      <MapSafe loadingComponent={loadingComponent} className="relative">
        {/* Mobile: Total Box Above Map */}
        {isMobile && (
          <div className="mb-3">
            <div className="bg-white rounded-lg shadow-md p-3 border border-gray-200">
              <div className="text-center">
                <h3 className="text-xs font-semibold text-humdb-gray-600 mb-1">
                  {hoveredCountry ? hoveredCountry : (countryName || t('globalOverview.map.selectedCountry'))}
                </h3>
                {isLoadingData ? (
                  <div className="text-base font-bold text-humdb-navy animate-pulse">Loading...</div>
                ) : (
                  <>
                    <div className="text-xl font-bold text-humdb-red mb-1">
                      {hoveredCountry ? formatNumber(hoveredValue, showFullValues) : formatNumber(globalTotal, showFullValues)}
                    </div>
                    <div className="text-xs text-humdb-gray-500 break-words leading-relaxed">
                      {indicatorName || selectedIndicator.replace('-', ' ')}
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Desktop: Total Box */}
        {!isMobile && (
          <div className={`absolute left-6 top-8 z-30 bg-white rounded-xl shadow-xl p-6 w-[220px] border border-gray-200 backdrop-blur-sm transition-opacity duration-200 ${isTooltipVisible ? 'opacity-0 pointer-events-none' : 'opacity-100'}`}>
            <div className="text-center">
              <h3 className="text-sm font-semibold text-humdb-gray-600 mb-2">
                {hoveredCountry ? hoveredCountry : (countryName || t('globalOverview.map.selectedCountry'))}
              </h3>
              {isLoadingData ? (
                <div className="text-lg font-bold text-humdb-navy animate-pulse">Loading...</div>
              ) : (
                <>
                  <div className="text-3xl font-bold text-humdb-red mb-2">
                    {hoveredCountry ? formatNumber(hoveredValue, showFullValues) : formatNumber(globalTotal, showFullValues)}
                  </div>
                  <div className="text-xs text-humdb-gray-500 break-words leading-relaxed">
                    {indicatorName || selectedIndicator.replace('-', ' ')}
                  </div>
                </>
              )}
            </div>
          </div>
        )}

        <div className="w-full h-96 md:h-[600px] rounded-xl overflow-hidden shadow-lg relative z-10">
          {/* Visualization Type Toggle - On Top of Map */}
          <div className="absolute top-4 right-4 z-[1000] bg-white rounded-lg shadow-lg p-2 border border-gray-200">
            <div className="flex gap-1">
              <button
                onClick={() => onVisualizationTypeChange('choropleth')}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-all duration-200 flex items-center justify-center ${
                  visualizationType === 'choropleth'
                    ? 'bg-humdb-red text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
                title={t('globalOverview.map.choroplethMap')}
              >
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="w-4 h-4">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 6.75V15m6-6v8.25m.503 3.498 4.875-2.437c.381-.19.622-.58.622-1.006V4.82c0-.836-.88-1.38-1.628-1.006l-3.869 1.934c-.317.159-.69.159-1.006 0L9.503 3.252a1.125 1.125 0 0 0-1.006 0L3.622 5.689C3.24 5.88 3 6.27 3 6.695V19.18c0 .836.88 1.38 1.628 1.006l3.869-1.934c.317-.159.69-.159 1.006 0l4.994 2.497c.317.158.69.158 1.006 0Z" />
                </svg>
              </button>
              <button
                onClick={() => onVisualizationTypeChange('bubble')}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-all duration-200 flex items-center justify-center ${
                  visualizationType === 'bubble'
                    ? 'bg-humdb-red text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
                title={t('globalOverview.map.bubbleMap')}
              >
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="w-4 h-4">
                  <circle cx="8" cy="8" r="3" />
                  <circle cx="16" cy="8" r="2" />
                  <circle cx="12" cy="16" r="4" />
                </svg>
              </button>
              <button
                onClick={() => onVisualizationTypeChange('barchart')}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-all duration-200 flex items-center justify-center ${
                  visualizationType === 'barchart'
                    ? 'bg-humdb-red text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
                title={t('globalOverview.map.barChart')}
              >
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="w-4 h-4">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 0 1 3 19.875v-6.75ZM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V8.625ZM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V4.125Z" />
                </svg>
              </button>
              <div className="border-l border-gray-300 mx-1"></div>
              <button
                onClick={() => setShowFullValues(!showFullValues)}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-all duration-200 ${
                  showFullValues
                    ? 'bg-blue-500 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
                title={showFullValues ? t('globalOverview.map.showAbbreviated') : t('globalOverview.map.showFull')}
              >
                {showFullValues ? '1.2K' : '1,234'}
              </button>
            </div>
          </div>

          {/* Year Timeline Overlay - Bottom Left */}
          {yearTimeline && (
            <div className="absolute bottom-8 left-8 z-[1000]">
              {yearTimeline}
            </div>
          )}

          <CountryMapboxMap
            countryIso2={iso2}
            countryIso3={scopeCountryIso3}
            value={countryValue}
            indicatorLabel={indicatorName || selectedIndicator.replace('-', ' ')}
            showFullValues={showFullValues}
            visualizationType={visualizationType}
            indicatorData={indicatorData}
            maxValue={maxValueRef.current}
            activeAdmLevel={countryAdmLevel}
            onActiveAdmLevelChange={setCountryAdmLevel}
            onHover={onCountryHover}
            onLeave={onCountryLeave}
            onClick={onCountryClick}
            onTooltipShow={() => setIsTooltipVisible(true)}
            onTooltipHide={() => setIsTooltipVisible(false)}
          />
        </div>

        {/* Mobile: Legend Below Map */}
        {isMobile && (
          <div className="mt-3">
            <div className="bg-white rounded-lg shadow-md p-3 border border-gray-200">
              {renderMobileLegend()}
            </div>
          </div>
        )}
      </MapSafe>
    );
  }

  // Default choropleth map
  return (
    <MapSafe
      loadingComponent={loadingComponent}
      className="relative"
    >
      <div style={{ display: isBarChart ? 'none' : 'block' }}>
        {/* Mobile: Total Box Above Map */}
        {isMobile && (
          <div className="mb-3">
            <div className="bg-white rounded-lg shadow-md p-3 border border-gray-200">
              <div className="text-center">
                <h3 className="text-xs font-semibold text-humdb-gray-600 mb-1">
                  {hoveredCountry ? hoveredCountry : (regionName || t('globalOverview.map.globalTotal'))}
                </h3>
                {isLoadingData ? (
                  <div className="text-base font-bold text-humdb-navy animate-pulse">
                    {t('common.loading')}
                  </div>
                ) : (
                  <>
                    <div className="text-xl font-bold text-humdb-red mb-1">
                      {hoveredCountry ? formatNumber(hoveredValue, showFullValues) : formatNumber(globalTotal, showFullValues)}
                    </div>
                    <div className="text-xs text-humdb-gray-500 break-words leading-relaxed">
                      {indicatorName || selectedIndicator.replace('-', ' ')}
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Desktop: Enhanced Global Total Card - Positioned to avoid toggle buttons */}
        {!isMobile && (
          <div className={`absolute left-6 top-8 z-30 bg-white rounded-xl shadow-xl p-6 w-[220px] border border-gray-200 backdrop-blur-sm transition-opacity duration-200 ${isTooltipVisible ? 'opacity-0 pointer-events-none' : 'opacity-100'}`}>
            <div className="text-center">
              <h3 className="text-sm font-semibold text-humdb-gray-600 mb-2">
                {hoveredCountry ? hoveredCountry : (regionName || t('globalOverview.map.globalTotal'))}
              </h3>
              {isLoadingData ? (
                <div className="text-lg font-bold text-humdb-navy animate-pulse">
                  Loading...
                </div>
              ) : (
                <>
                  <div className="text-3xl font-bold text-humdb-red mb-2">
                    {hoveredCountry ? formatNumber(hoveredValue, showFullValues) : formatNumber(globalTotal, showFullValues)}
                  </div>
                  <div className="text-xs text-humdb-gray-500 break-words leading-relaxed">
                    {indicatorName || selectedIndicator.replace('-', ' ')}
                  </div>
                </>
              )}
            </div>
          </div>
        )}

        {/* Map Container */}
        <div
          ref={mapRef}
          className="w-full h-96 md:h-[600px] rounded-xl overflow-hidden shadow-lg relative z-10"
        >
          {/* Visualization Type Toggle - On Top of Map */}
          <div className="absolute top-4 right-4 z-[1000] bg-white rounded-lg shadow-lg p-2 border border-gray-200">
            <div className="flex gap-1">
              <button
                onClick={() => onVisualizationTypeChange('choropleth')}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-all duration-200 flex items-center justify-center ${
                  visualizationType === 'choropleth'
                    ? 'bg-humdb-red text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
                title={t('globalOverview.map.choroplethMap')}
              >
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="w-4 h-4">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 6.75V15m6-6v8.25m.503 3.498 4.875-2.437c.381-.19.622-.58.622-1.006V4.82c0-.836-.88-1.38-1.628-1.006l-3.869 1.934c-.317.159-.69.159-1.006 0L9.503 3.252a1.125 1.125 0 0 0-1.006 0L3.622 5.689C3.24 5.88 3 6.27 3 6.695V19.18c0 .836.88 1.38 1.628 1.006l3.869-1.934c.317-.159.69.159 1.006 0l4.994 2.497c.317.158.69.158 1.006 0Z" />
                </svg>
              </button>
              <button
                onClick={() => onVisualizationTypeChange('bubble')}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-all duration-200 flex items-center justify-center ${
                  visualizationType === 'bubble'
                    ? 'bg-humdb-red text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
                title="Bubble Map"
              >
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="w-4 h-4">
                  <circle cx="8" cy="8" r="3" />
                  <circle cx="16" cy="8" r="2" />
                  <circle cx="12" cy="16" r="4" />
                </svg>
              </button>
              <button
                onClick={() => onVisualizationTypeChange('barchart')}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-all duration-200 flex items-center justify-center ${
                  visualizationType === 'barchart'
                    ? 'bg-humdb-red text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
                title={t('globalOverview.map.barChart')}
              >
                <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="w-4 h-4">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 0 1 3 19.875v-6.75ZM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V8.625ZM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V4.125Z" />
                </svg>
              </button>
              <div className="border-l border-gray-300 mx-1"></div>
              <button
                onClick={() => setShowFullValues(!showFullValues)}
                className={`px-3 py-1 rounded-md text-xs font-medium transition-all duration-200 ${
                  showFullValues
                    ? 'bg-blue-500 text-white'
                    : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                }`}
                title={showFullValues ? t('globalOverview.map.showAbbreviated') : t('globalOverview.map.showFull')}
              >
                {showFullValues ? '1.2K' : '1,234'}
              </button>
            </div>
          </div>

          {/* Animation Controls - Only show when multiple years available */}
          {availableYears.length > 1 && (
            <div className="absolute bottom-8 left-8 z-[1000]" style={{ left: '120px' }}>
              <button
                onClick={isAnimating ? stopAnimation : startAnimation}
                className={`w-10 h-10 rounded-full bg-red-500 text-white transition-all duration-300 ease-in-out flex items-center justify-center shadow-lg ${
                  isAnimating
                    ? 'opacity-100 scale-110'
                    : 'opacity-50 hover:opacity-100 hover:bg-red-600 hover:scale-105'
                }`}
                title={isAnimating ? t('globalOverview.map.stopAnimation') : t('globalOverview.map.startTimeAnimation')}
              >
                {isAnimating ? (
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                    <rect x="6" y="4" width="4" height="16" rx="1"/>
                    <rect x="14" y="4" width="4" height="16" rx="1"/>
                  </svg>
                ) : (
                  <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M8 5v14l11-7z"/>
                  </svg>
                )}
              </button>
            </div>
          )}

          {/* Year Timeline Overlay - Bottom Left */}
          {yearTimeline && (
            <div className="absolute bottom-8 left-8 z-[1000]">
              {yearTimeline}
            </div>
          )}
        </div>

        {/* Mobile: Legend Below Map */}
        {isMobile && (
          <div className="mt-3">
            <div className="bg-white rounded-lg shadow-md p-3 border border-gray-200">
              {renderMobileLegend()}
            </div>
          </div>
        )}
      </div>

      {isBarChart && <BarChart />}
    </MapSafe>
  );
};

export default InteractiveWorldMap;
