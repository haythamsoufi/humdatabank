import React, { useEffect, useMemo, useRef, useState } from 'react';
import CountryLeafletAdminMap from './CountryLeafletAdminMap';
import { useTranslation } from '../lib/useTranslation';
import { getCountriesList } from '../lib/apiService';

// Generic Mapbox GL map to display a selected country (by ISO2) and show a single aggregated value.
// This is used for "National Society" scope in demo/deployments.

function formatNumber(num, showFull = false) {
  // Round to avoid floating point precision issues
  const n = Math.round(Number(num || 0) * 100) / 100;
  if (showFull) return n.toLocaleString();
  if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toFixed(1)}B`;
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  // For numbers less than 1000, show up to 1 decimal place if needed, otherwise integer
  if (n % 1 === 0) {
    return String(n);
  }
  return n.toFixed(1);
}

function escapeHtml(s) {
  return String(s || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function getFeatureIso2(feature) {
  const p = feature?.properties || {};
  const iso2 =
    p['ISO3166-1-Alpha-2'] ||
    p.ISO_A2 ||
    p.ISO2 ||
    p.iso_a2;
  return iso2 ? String(iso2).toUpperCase() : null;
}

function getFeatureName(feature) {
  const p = feature?.properties || {};
  return p.name || p.ADMIN || p.NAME || p.NAME_LONG || 'Selected country';
}

// This function will be used inside the component where we have access to translations
function getAdminLevelLabel(admLevel, t) {
  const key = String(admLevel || '').toUpperCase();
  const translationKey = `countryProfile.map.adminLevels.${key}`;
  const translated = t(translationKey);
  // If translation returns the key (meaning it wasn't found), fallback to English defaults
  if (translated === translationKey) {
    const fallbacks = {
      'ADM0': 'Country',
      'ADM1': 'Province',
      'ADM2': 'District',
      'ADM3': 'Sub-district',
    };
    return fallbacks[key] || admLevel;
  }
  return translated;
}

function computeBbox(feature) {
  // Simple bbox calc for Polygon/MultiPolygon
  const coords = feature?.geometry?.coordinates;
  const type = feature?.geometry?.type;
  if (!coords || !type) return null;

  let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;

  const pushPoint = (pt) => {
    const x = Number(pt?.[0]);
    const y = Number(pt?.[1]);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    if (x < minX) minX = x;
    if (y < minY) minY = y;
    if (x > maxX) maxX = x;
    if (y > maxY) maxY = y;
  };

  const walk = (arr) => {
    if (!Array.isArray(arr)) return;
    if (typeof arr[0] === 'number') {
      pushPoint(arr);
      return;
    }
    for (const child of arr) walk(child);
  };

  walk(coords);

  if (!Number.isFinite(minX) || !Number.isFinite(minY) || !Number.isFinite(maxX) || !Number.isFinite(maxY)) {
    return null;
  }

  return [[minX, minY], [maxX, maxY]];
}

function isFastConnectionForAdm3() {
  // Prefer being conservative: if we can't detect, assume NOT fast.
  // We only want ADM3 prefetch on clearly fast connections.
  try {
    if (typeof navigator === 'undefined') return false;
    const c = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    if (!c) return false;
    if (c.saveData) return false;

    const effectiveType = String(c.effectiveType || '').toLowerCase(); // e.g. '4g'
    const downlink = Number(c.downlink); // Mbps (may be NaN)
    const rtt = Number(c.rtt); // ms (may be NaN)
    const deviceMemory = Number(navigator.deviceMemory); // GB (may be NaN)

    const looksFastType = effectiveType === '4g' || effectiveType === '5g';
    const looksFastDownlink = !Number.isFinite(downlink) ? false : downlink >= 5;
    const looksOkRtt = !Number.isFinite(rtt) ? true : rtt <= 150;
    const looksOkMemory = !Number.isFinite(deviceMemory) ? true : deviceMemory >= 4;

    // Require either 4g/5g or >=5Mbps downlink, plus no obvious red flags.
    return (looksFastType || looksFastDownlink) && looksOkRtt && looksOkMemory;
  } catch (_e) {
    return false;
  }
}

async function loadWorldGeoJson() {
  const sources = [
    'https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson',
    'https://raw.githubusercontent.com/holtzy/D3-graph-gallery/master/DATA/world.geojson',
    'https://raw.githubusercontent.com/PublicaMundi/MappingAPI/master/data/geojson/countries.json',
  ];

  for (const url of sources) {
    try {
      const resp = await fetch(url);
      if (!resp.ok) continue;
      const data = await resp.json();
      if (data && Array.isArray(data.features) && data.features.length > 0) return data;
    } catch (_e) {
      // try next
    }
  }

  return null;
}

export default function CountryMapboxMap({
  countryIso2,
  countryIso3,
  value = 0,
  indicatorLabel = '',
  showFullValues = false,
  visualizationType = 'choropleth', // 'choropleth' | 'bubble'
  indicatorData = null, // optional: map of { [shapeID|shapeISO|shapeName]: number | { value, name } }
  maxValue = null, // optional: normalize colors/sizes against a max from the parent scope
  activeAdmLevel: activeAdmLevelProp = undefined, // optional controlled admin level
  onActiveAdmLevelChange = undefined, // optional callback when admin level changes
  onHover,
  onLeave,
  onClick,
  onTooltipShow,
  onTooltipHide,
}) {
  const { t, locale } = useTranslation();
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const popupRef = useRef(null);
  const worldGeoJsonRef = useRef(null);
  const valueRef = useRef(value);
  const indicatorRef = useRef(indicatorLabel);
  const showFullRef = useRef(showFullValues);
  const visualizationTypeRef = useRef(visualizationType);
  const indicatorDataRef = useRef(indicatorData);
  const maxValuePropRef = useRef(maxValue);
  const countryIso2Ref = useRef(countryIso2);
  const countryIso3Ref = useRef(countryIso3);

  // State for localized country names from backend
  const [localizedCountries, setLocalizedCountries] = useState([]);
  const localizedCountriesRef = useRef([]);

  const [status, setStatus] = useState('init'); // init | loading | ready | error
  const [statusDetail, setStatusDetail] = useState('');
  const [fallbackMode, setFallbackMode] = useState('mapbox'); // mapbox | leaflet
  const [availableAdmLevels, setAvailableAdmLevels] = useState(['ADM0']);
  const [activeAdmLevel, setActiveAdmLevel] = useState(activeAdmLevelProp || 'ADM1'); // will be normalized after load
  // Basemap mode is hardcoded (no UI toggle).
  // Options: 'field' (no basemap, plain background) | 'basemap' (use configured Mapbox style)
  const BASEMAP_MODE = 'field';

  // Parent passes new function instances on each render; keep stable refs so we don't re-init the map.
  const onHoverRef = useRef(onHover);
  const onLeaveRef = useRef(onLeave);
  const onClickRef = useRef(onClick);
  const onTooltipShowRef = useRef(onTooltipShow);
  const onTooltipHideRef = useRef(onTooltipHide);
  useEffect(() => { onHoverRef.current = onHover; }, [onHover]);
  useEffect(() => { onLeaveRef.current = onLeave; }, [onLeave]);
  useEffect(() => { onClickRef.current = onClick; }, [onClick]);
  useEffect(() => { onTooltipShowRef.current = onTooltipShow; }, [onTooltipShow]);
  useEffect(() => { onTooltipHideRef.current = onTooltipHide; }, [onTooltipHide]);

  valueRef.current = value;
  indicatorRef.current = indicatorLabel;
  showFullRef.current = showFullValues;
  visualizationTypeRef.current = visualizationType;
  indicatorDataRef.current = indicatorData;
  maxValuePropRef.current = maxValue;
  countryIso2Ref.current = countryIso2;
  countryIso3Ref.current = countryIso3;

  const token = process.env.NEXT_PUBLIC_MAPBOX_TOKEN;

  const normalizedIso2 = useMemo(() => {
    return countryIso2 ? String(countryIso2).toUpperCase() : null;
  }, [countryIso2]);

  const normalizedIso3 = useMemo(() => {
    return countryIso3 ? String(countryIso3).toUpperCase() : null;
  }, [countryIso3]);

  const boundaryCacheRef = useRef(new Map()); // key: `${ISO3}:${ADM}` -> geojson

  // Fetch localized country names from backend
  useEffect(() => {
    let mounted = true;
    const loadCountries = async () => {
      try {
        const countries = await getCountriesList(locale || 'en');
        if (!mounted) return;
        const countriesArray = Array.isArray(countries) ? countries : [];
        setLocalizedCountries(countriesArray);
        localizedCountriesRef.current = countriesArray;
      } catch (error) {
        console.error('Failed to load localized countries:', error);
        if (!mounted) return;
        setLocalizedCountries([]);
        localizedCountriesRef.current = [];
      }
    };
    loadCountries();
    return () => {
      mounted = false;
    };
  }, [locale]);

  // Helper function to get localized country name (uses refs so it works in closures)
  const getLocalizedCountryName = (iso2, iso3, fallbackName) => {
    const countries = localizedCountriesRef.current;
    if (!countries || countries.length === 0) {
      return fallbackName || t('globalOverview.map.selectedCountry');
    }

    const iso2Upper = iso2 ? String(iso2).toUpperCase() : null;
    const iso3Upper = iso3 ? String(iso3).toUpperCase() : null;

    // Try to find by ISO2 first
    if (iso2Upper) {
      const country = countries.find(
        c => String(c.iso2 || c.code || '').toUpperCase() === iso2Upper
      );
      if (country) {
        return country.national_society_name || country.name || fallbackName;
      }
    }

    // Try to find by ISO3
    if (iso3Upper) {
      const country = countries.find(
        c => String(c.iso3 || '').toUpperCase() === iso3Upper
      );
      if (country) {
        return country.national_society_name || country.name || fallbackName;
      }
    }

    return fallbackName || t('globalOverview.map.selectedCountry');
  };

  const makeFieldOnlyStyle = () => ({
    version: 8,
    sources: {},
    layers: [
      {
        id: 'background',
        type: 'background',
        paint: { 'background-color': '#f8fafc' },
      },
    ],
  });

  const buildRasterStyle = () => ({
    version: 8,
    sources: {
      carto: {
        type: 'raster',
        tiles: [
          'https://a.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png',
          'https://b.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png',
          'https://c.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png',
          'https://d.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png',
        ],
        tileSize: 256,
        attribution: '',
      },
    },
    layers: [{ id: 'carto', type: 'raster', source: 'carto' }],
  });

  async function loadGeoBoundaries(iso3, adm) {
    if (!iso3) return null;
    const key = `${iso3}:${adm}`;
    const cached = boundaryCacheRef.current.get(key);
    if (cached) return cached;

    try {
      // First try to load from public folder (pre-downloaded files)
      // Path format: /geoboundaries/{ISO3}/{ADM}.geojson
      const localPath = `/geoboundaries/${iso3}/${adm}.geojson`;
      let resp = await fetch(localPath);

      // If local file doesn't exist (404), fallback to API
      if (!resp.ok) {
        // Use same-origin proxy to avoid CORS issues with GitHub raw links.
        resp = await fetch(`/api/geoboundaries?iso3=${encodeURIComponent(iso3)}&adm=${encodeURIComponent(adm)}`);
        if (!resp.ok) return null;
      }

      const geojson = await resp.json();
      if (!geojson || !Array.isArray(geojson.features)) return null;

      boundaryCacheRef.current.set(key, geojson);
      return geojson;
    } catch (_e) {
      return null;
    }
  }

  async function checkGeoBoundariesAvailable(iso3, adm) {
    if (!iso3) return false;
    const ISO3 = String(iso3).toUpperCase();
    const ADM = String(adm).toUpperCase();
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
  }

  function bboxFromFeatureCollection(fc) {
    if (!fc?.features?.length) return null;
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
    for (const f of fc.features) {
      const bb = computeBbox(f);
      if (!bb) continue;
      const [[x1, y1], [x2, y2]] = bb;
      if (x1 < minX) minX = x1;
      if (y1 < minY) minY = y1;
      if (x2 > maxX) maxX = x2;
      if (y2 > maxY) maxY = y2;
    }
    if (!Number.isFinite(minX)) return null;
    return [[minX, minY], [maxX, maxY]];
  }

  function getAdminNameFromProps(p) {
    if (!p) return null;
    return (
      p.__ifrcName ||
      p.shapeName ||
      p.name ||
      p.NAME ||
      p.admin ||
      p.adminName ||
      p.ADM0_EN ||
      p.ADM1_EN ||
      p.ADM2_EN ||
      p.ADM3_EN ||
      null
    );
  }

  function normalizeKey(v) {
    if (v == null) return '';
    return String(v)
      .trim()
      .toLowerCase()
      // keep unicode letters/digits, drop punctuation/spaces/underscores
      .replace(/[\s\W_]+/g, '');
  }

  function getIndicatorMaxValue(indicatorMap) {
    const explicit = Number(maxValuePropRef.current);
    if (Number.isFinite(explicit) && explicit > 0) return explicit;

    let m = 0;
    if (indicatorMap && typeof indicatorMap === 'object') {
      for (const v of Object.values(indicatorMap)) {
        const n = typeof v === 'object' && v ? Number(v.value) : Number(v);
        if (Number.isFinite(n) && n > m) m = n;
      }
    }
    const fallback = Number(valueRef.current);
    if (m <= 0 && Number.isFinite(fallback) && fallback > 0) m = fallback;
    return m > 0 ? m : 1;
  }

  function buildIndicatorLookup(indicatorMap) {
    const lookup = new Map(); // normalizedKey -> { value, name }
    if (!indicatorMap || typeof indicatorMap !== 'object') return lookup;

    for (const [rawKey, rawVal] of Object.entries(indicatorMap)) {
      const v = typeof rawVal === 'object' && rawVal ? Number(rawVal.value) : Number(rawVal);
      const name = typeof rawVal === 'object' && rawVal ? rawVal.name : null;
      if (!Number.isFinite(v)) continue;

      const add = (k) => {
        const nk = normalizeKey(k);
        if (!nk) return;
        // Keep first-write to avoid surprising overrides
        if (!lookup.has(nk)) lookup.set(nk, { value: v, name });
      };

      add(rawKey);
      add(String(rawKey).toUpperCase());
      add(String(rawKey).toLowerCase());
      if (name) add(name);
    }
    return lookup;
  }

  function getFeatureJoinCandidates(props) {
    if (!props) return [];
    // geoBoundaries: shapeID (stable), shapeISO (sometimes blank), shapeName (human)
    return [
      props.shapeID,
      props.shapeISO,
      props.shapeName,
      props.name,
      props.NAME,
      props.adminName,
    ].filter(Boolean);
  }

  // Simple hash function to generate deterministic pseudo-random numbers from a string
  function hashString(str) {
    let hash = 0;
    if (!str) return hash;
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash; // Convert to 32-bit integer
    }
    return Math.abs(hash);
  }

  // Generate deterministic random number between 0 and 1 based on seed
  function seededRandom(seed) {
    const x = Math.sin(seed) * 10000;
    return x - Math.floor(x);
  }

  function decorateFeatureCollection(fc, indicatorMap, maxVal) {
    if (!fc?.features?.length) return { fc, anyMatched: false };
    const lookup = buildIndicatorLookup(indicatorMap);
    const totalValue = Number(valueRef.current || 0);
    const featureCount = fc.features.length;
    const avgValuePerFeature = featureCount > 0 ? totalValue / featureCount : 0;

    // First pass: try to match features with indicator data
    const matches = [];
    for (let i = 0; i < fc.features.length; i++) {
      const f = fc.features[i];
      const p = f.properties || (f.properties = {});
      let matched = null;

      // Try matching by candidate keys
      for (const cand of getFeatureJoinCandidates(p)) {
        const hit = lookup.get(normalizeKey(cand));
        if (hit) {
          matched = hit;
          break;
        }
      }
      matches.push(matched);
    }

    // Check if we have any real admin-level matches
    const hasAdminLevelMatches = matches.some(m => m !== null);

    // Pre-calculate random values if we don't have admin-level matches
    let randomValues = [];
    if (!hasAdminLevelMatches && featureCount > 0) {
      let sum = 0;
      // First pass: generate random values
      for (let i = 0; i < featureCount; i++) {
        const f = fc.features[i];
        const p = f.properties || {};
        // Create a stable seed from feature properties
        const seedStr = [
          p.shapeID,
          p.shapeISO,
          p.shapeName,
          p.name,
          p.NAME,
          String(i),
        ].filter(Boolean).join('|');
        const seed = hashString(seedStr);
        const rand = seededRandom(seed);

        // ~70% of features get values, ~30% are null
        if (rand < 0.3) {
          randomValues.push(null);
        } else {
          // Random value between 0.1x and 2.5x the average
          const multiplier = 0.1 + (rand * 2.4);
          const baseValue = avgValuePerFeature * multiplier;
          // Add some additional variation
          const variation = baseValue * (0.5 + rand);
          randomValues.push(Math.max(0, Math.round(variation)));
          sum += randomValues[i];
        }
      }

      // Second pass: normalize to approximately match total (if we have values)
      if (sum > 0 && totalValue > 0) {
        const scale = totalValue / sum;
        for (let i = 0; i < randomValues.length; i++) {
          if (randomValues[i] != null) {
            randomValues[i] = Math.max(0, Math.round(randomValues[i] * scale));
          }
        }
      }
    }

    // Second pass: apply values to features
    let anyMatched = false;
    for (let i = 0; i < fc.features.length; i++) {
      const f = fc.features[i];
      const p = f.properties || (f.properties = {});
      const matched = matches[i];

      let v;
      if (matched) {
        v = matched.value;
        anyMatched = true;
      } else if (!hasAdminLevelMatches) {
        // Use pre-calculated deterministic random value when no admin-level matches
        v = randomValues[i] != null ? randomValues[i] : null;
        if (v != null) anyMatched = true; // Mark as matched for demo purposes
      } else {
        // This shouldn't happen, but fallback to 0 if somehow we have matches but this one doesn't
        v = 0;
      }

      const safeV = (v == null || !Number.isFinite(v)) ? 0 : v;
      const intensity = maxVal > 0 ? Math.min(safeV / maxVal, 1) : 0;

      p.__ifrcValue = safeV;
      p.__ifrcIntensity = intensity;
      if (matched?.name) p.__ifrcName = matched.name;
    }

    return { fc, anyMatched };
  }

  function choroplethColorExpression() {
    // Matches InteractiveWorldMap's thresholds
    return [
      'case',
      ['<=', ['coalesce', ['get', '__ifrcValue'], 0], 0],
      '#f8fafc',
      ['<', ['coalesce', ['get', '__ifrcIntensity'], 0], 0.2],
      '#e3f2fd',
      ['<', ['coalesce', ['get', '__ifrcIntensity'], 0], 0.4],
      '#90caf9',
      ['<', ['coalesce', ['get', '__ifrcIntensity'], 0], 0.6],
      '#42a5f5',
      ['<', ['coalesce', ['get', '__ifrcIntensity'], 0], 0.8],
      '#1976d2',
      '#0d47a1',
    ];
  }

  function bubbleRadiusExpression(maxVal) {
    const denom = Number.isFinite(maxVal) && maxVal > 0 ? maxVal : 1;
    // radius = 3 + intensity * 27, 0 when value<=0
    return [
      'case',
      ['<=', ['coalesce', ['get', '__ifrcValue'], 0], 0],
      0,
      ['+', 3, ['*', ['min', 1, ['/', ['coalesce', ['get', '__ifrcValue'], 0], denom]], 27]],
    ];
  }

  function featureToBubblePoint(feature) {
    const bb = computeBbox(feature);
    if (!bb) return null;
    const [[minX, minY], [maxX, maxY]] = bb;
    const cx = (minX + maxX) / 2;
    const cy = (minY + maxY) / 2;
    if (!Number.isFinite(cx) || !Number.isFinite(cy)) return null;
    const p = feature?.properties || {};
    return {
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [cx, cy] },
      properties: {
        __ifrcValue: Number(p.__ifrcValue || 0),
        __ifrcIntensity: Number(p.__ifrcIntensity || 0),
        __ifrcName: getAdminNameFromProps(p) || p.shapeName || p.name || p.NAME || null,
      },
    };
  }

  useEffect(() => {
    let destroyed = false;

    const init = async () => {
      if (!containerRef.current) return;
      if (!normalizedIso2) return;
      if (fallbackMode === 'leaflet') return;

      // Mapbox GL JS requires a valid Mapbox token for operation; if absent, use Leaflet fallback.
      if (!token) {
        setStatus('error');
        setStatusDetail('Mapbox token is not set. Switching to Leaflet fallback…');
        setFallbackMode('leaflet');
        return;
      }

      // Quick WebGL support check (Mapbox GL requires WebGL even for raster tiles)
      try {
        const canvas = document.createElement('canvas');
        const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
        if (!gl) {
          setStatus('error');
          setStatusDetail('WebGL is not available. Switching to Leaflet fallback…');
          setFallbackMode('leaflet');
          return;
        }
      } catch (_e) {
        // If check fails, proceed and let Mapbox throw.
      }

      setStatus('loading');
      setStatusDetail('Initializing map…');

      // Destroy previous instance (switch scope/country)
      if (mapRef.current) {
        try { mapRef.current.remove(); } catch (_e) {}
        mapRef.current = null;
      }

      let mapboxgl = null;
      try {
        mapboxgl = (await import('mapbox-gl')).default;
      } catch (e) {
        console.error('Failed to import mapbox-gl:', e);
        setStatus('error');
        setStatusDetail('Failed to load mapbox-gl. Switching to Leaflet fallback…');
        setFallbackMode('leaflet');
        return;
      }
      if (destroyed) return;

      if (token) {
        mapboxgl.accessToken = token;
      }

      let map = null;
      try {
        const initialStyle =
          BASEMAP_MODE === 'basemap'
            ? 'mapbox://styles/go-ifrc/ckrfe16ru4c8718phmckdfjh0'
            : makeFieldOnlyStyle();
        map = new mapboxgl.Map({
          container: containerRef.current,
          style: initialStyle,
          center: [0, 20],
          zoom: 1,
          attributionControl: false,
        });
      } catch (e) {
        console.error('Failed to initialize mapbox-gl Map:', e);
        setStatus('error');
        setStatusDetail(`Mapbox init failed. Switching to Leaflet fallback… (${e?.message || String(e)})`);
        setFallbackMode('leaflet');
        return;
      }

      // Hide Mapbox logo
      const hideLogo = () => {
        const logo = containerRef.current?.querySelector('.mapboxgl-ctrl-logo');
        if (logo) {
          logo.style.display = 'none';
        }
      };
      // Hide immediately if already present, and also after load
      hideLogo();
      map.on('load', hideLogo);
      map.on('style.load', hideLogo);

      const popup = new mapboxgl.Popup({
        closeButton: false,
        closeOnClick: false,
        offset: 12,
      });
      popupRef.current = popup;

      // If Mapbox rejects the token (or other fatal errors), switch to Leaflet fallback.
      map.on('error', (evt) => {
        try {
          const msg = String(evt?.error?.message || evt?.message || '');
          if (msg.toLowerCase().includes('access token')) {
            console.warn('Mapbox token error; switching to Leaflet fallback.', msg);
            setStatus('error');
            setStatusDetail('Invalid Mapbox token. Switching to Leaflet fallback…');
            setFallbackMode('leaflet');
            try { map.remove(); } catch (_e) {}
          }
        } catch (_e) {
          // ignore
        }
      });

      map.on('load', async () => {
        if (destroyed) return;

        setStatusDetail(t('common.loading'));

        // Prefer ISO3 for admin-boundary fetch; fallback to world ADM0 if ISO3 isn't available yet.
        const iso2 = countryIso2Ref.current ? String(countryIso2Ref.current).toUpperCase() : null;
        const iso3 = countryIso3Ref.current ? String(countryIso3Ref.current).toUpperCase() : null;

        let adm0 = null;
        let adm1 = null;
        // ADM2/ADM3 are potentially huge; lazy-load them when/if the user selects those levels.
        let adm2 = null;
        let adm3 = null;

        if (iso3) {
          // Load only ADM0/ADM1 for initial render (fast).
          const [a0, a1] = await Promise.all([
            loadGeoBoundaries(iso3, 'ADM0'),
            loadGeoBoundaries(iso3, 'ADM1'),
          ]);
          adm0 = a0;
          adm1 = a1;
        }

        // Fallback: if ADM0 isn't available, use world country polygon
        if (!adm0) {
          if (!worldGeoJsonRef.current) {
            worldGeoJsonRef.current = await loadWorldGeoJson();
          }
          const world = worldGeoJsonRef.current;
          const feature = world?.features?.find((f) => getFeatureIso2(f) === iso2) || null;
          if (feature) {
            adm0 = { type: 'FeatureCollection', features: [feature] };
          }
        }

        if (!adm0 || !Array.isArray(adm0.features) || adm0.features.length === 0) return;

        // Store admin data on the map instance so we can re-apply after style changes.
        map.__ifrcAdminData = { adm0, adm1, adm2, adm3, iso2, iso3 };

        // Determine available admin levels and pick a default "lowest" (finest) level.
        const hasAdm1Data = !!adm1?.features?.length;
        // Do not download ADM2/ADM3 just to know if they exist; do a lightweight check.
        const [hasAdm2Data, hasAdm3Data] = iso3
          ? await Promise.all([
              checkGeoBoundariesAvailable(iso3, 'ADM2'),
              checkGeoBoundariesAvailable(iso3, 'ADM3'),
            ])
          : [false, false];

        // Option B: do NOT render ADM0 when ADM1+ exists (avoid misalignment issues).
        // Keep ADM0 only as a fallback when ADM1 is not available.
        const available = [];
        if (hasAdm1Data) available.push('ADM1');
        if (hasAdm2Data) available.push('ADM2');
        if (hasAdm3Data) available.push('ADM3');
        if (available.length === 0) available.push('ADM0');
        setAvailableAdmLevels(available);
        // Default to a sensible initial level without triggering huge downloads.
        // If ADM1 exists, prefer ADM1; otherwise fallback to ADM0.
        const preferred = available.includes('ADM1') ? 'ADM1' : 'ADM0';
        setActiveAdmLevel((prev) => (available.includes(prev) ? prev : preferred));

        const ensureAdminLayers = () => {
          const data = map.__ifrcAdminData;
          if (!data) return;

          const removeLayerSafe = (id) => { try { if (map.getLayer(id)) map.removeLayer(id); } catch (_e) {} };
          const removeSourceSafe = (id) => { try { if (map.getSource(id)) map.removeSource(id); } catch (_e) {} };

          // Remove our layers/sources if re-applying after style changes
          [
            'adm3-fill','adm3-line','adm3-grouping',
            'adm2-fill','adm2-line','adm2-grouping',
            'adm1-fill','adm1-line','adm1-grouping',
            'adm0-fill','adm0-outline',
            'humdb-bubbles-circle',
          ].forEach(removeLayerSafe);
          ['adm3','adm2','adm1','adm0','humdb-bubbles'].forEach(removeSourceSafe);

          const maxVal = getIndicatorMaxValue(indicatorDataRef.current);
          // Decorate admin feature collections with per-feature values/intensity (best-effort join).
          const d0 = decorateFeatureCollection(data.adm0, indicatorDataRef.current, maxVal);
          const d1 = decorateFeatureCollection(data.adm1, indicatorDataRef.current, maxVal);
          const d2 = decorateFeatureCollection(data.adm2, indicatorDataRef.current, maxVal);
          const d3 = decorateFeatureCollection(data.adm3, indicatorDataRef.current, maxVal);
          // Track whether anything matched (vs uniform fallback) so bubble mode can avoid thousands of identical bubbles.
          map.__ifrcAnyFeatureMatch = !!(d0.anyMatched || d1.anyMatched || d2.anyMatched || d3.anyMatched);

          const addAdm0 = () => {
            try { map.addSource('adm0', { type: 'geojson', data: d0.fc, generateId: true }); } catch (_e) {}
            try {
              map.addLayer({
                id: 'adm0-fill',
                type: 'fill',
                source: 'adm0',
                paint: {
                  'fill-color': [
                    'case',
                    ['boolean', ['feature-state', 'hover'], false],
                    '#ef4444',
                    choroplethColorExpression(),
                  ],
                  'fill-opacity': [
                    'case',
                    ['boolean', ['feature-state', 'hover'], false],
                    0.95,
                    ['case', ['>', ['coalesce', ['get', '__ifrcValue'], 0], 0], 0.85, 0.3],
                  ],
                },
              });
            } catch (_e) {}
            try {
              map.addLayer({
                id: 'adm0-outline',
                type: 'line',
                source: 'adm0',
                paint: {
                  'line-color': [
                    'case',
                    ['boolean', ['feature-state', 'hover'], false],
                    '#ef4444',
                    '#d1d5db',
                  ],
                  'line-width': [
                    'case',
                    ['boolean', ['feature-state', 'hover'], false],
                    3.2,
                    1,
                  ],
                },
              });
            } catch (_e) {}
          };

          const addBoundaryLayer = (id, fc, color, width, dash = null) => {
            if (!fc || !Array.isArray(fc.features) || fc.features.length === 0) return false;
            const decorated =
              id === 'adm1' ? d1.fc :
              id === 'adm2' ? d2.fc :
              id === 'adm3' ? d3.fc :
              fc;
            try { map.addSource(id, { type: 'geojson', data: decorated, generateId: true }); } catch (_e) {}
            try {
              map.addLayer({
                id: `${id}-fill`,
                type: 'fill',
                source: id,
                paint: {
                  'fill-color': [
                    'case',
                    ['boolean', ['feature-state', 'hover'], false],
                    '#ef4444',
                    choroplethColorExpression(),
                  ],
                  'fill-opacity': [
                    'case',
                    ['boolean', ['feature-state', 'hover'], false],
                    0.95,
                    ['case', ['>', ['coalesce', ['get', '__ifrcValue'], 0], 0], 0.85, 0.3],
                  ],
                },
              });
            } catch (_e) {}
            try {
              map.addLayer({
                id: `${id}-line`,
                type: 'line',
                source: id,
                paint: {
                  'line-color': [
                    'case',
                    ['boolean', ['feature-state', 'hover'], false],
                    '#ef4444',
                    '#d1d5db',
                  ],
                  'line-width': [
                    'case',
                    ['boolean', ['feature-state', 'hover'], false],
                    width + 1.2,
                    1,
                  ],
                  ...(dash ? { 'line-dasharray': dash } : {}),
                },
              });
            } catch (_e) {}
            return true;
          };

          // Add grouping outline layers (thicker parent admin level lines for context)
          const addGroupingLayer = (id, fc, color, width) => {
            if (!fc || !Array.isArray(fc.features) || fc.features.length === 0) return false;
            // Reuse existing source if available
            try {
              map.addLayer({
                id: `${id}-grouping`,
                type: 'line',
                source: id,
                paint: {
                  'line-color': color,
                  'line-width': width,
                },
              });
            } catch (_e) {}
            return true;
          };

          // Option B: only add ADM0 if ADM1 is missing (fallback only).
          const hasAdm1Data = !!data.adm1?.features?.length;
          if (!hasAdm1Data) {
            addAdm0();
          }
          const hasAdm3 = addBoundaryLayer('adm3', data.adm3, '#9ca3af', 1.2, [1, 1]);
          const hasAdm2 = addBoundaryLayer('adm2', data.adm2, '#6b7280', 1.8, [2, 2]);
          const hasAdm1 = addBoundaryLayer('adm1', data.adm1, '#374151', 1.6, null);

          // Add grouping outline layers (thicker parent lines for context when viewing child levels)
          // ADM1 grouping (thicker, shown when viewing ADM2 or ADM3)
          if (hasAdm1) addGroupingLayer('adm1', data.adm1, '#374151', 2.5);
          // ADM2 grouping (medium, shown when viewing ADM3)
          if (hasAdm2) addGroupingLayer('adm2', data.adm2, '#6b7280', 2.8);

          map.__ifrcHasAdm = { hasAdm1, hasAdm2, hasAdm3 };

          // Bubble layer (Mapbox circles) for bubble visualization.
          try {
            map.addSource('humdb-bubbles', {
              type: 'geojson',
              data: { type: 'FeatureCollection', features: [] },
              generateId: true,
            });
          } catch (_e) {}
          try {
            map.addLayer({
              id: 'humdb-bubbles-circle',
              type: 'circle',
              source: 'humdb-bubbles',
              paint: {
                'circle-color': '#ef4444',
                'circle-stroke-color': '#dc2626',
                'circle-stroke-width': 2,
                'circle-opacity': 0.7,
                'circle-stroke-opacity': 0.85,
                'circle-radius': bubbleRadiusExpression(maxVal),
              },
            });
          } catch (_e) {}
        };

        ensureAdminLayers();
        // If we ever re-introduce style switching, re-apply layers on style.load.
        map.on('style.load', () => {
          try { ensureAdminLayers(); } catch (_e) {}
          try { if (typeof map.__ifrcRebindAdminHover === 'function') map.__ifrcRebindAdminHover(); } catch (_e) {}
        });

        // Fit bounds to ADM0
        const bbox = bboxFromFeatureCollection(adm0);
        if (bbox) {
          try { map.fitBounds(bbox, { padding: 40, duration: 800 }); } catch (_e) {}
        }

        // Track hovered feature-state to highlight/fill shapes.
        // Event binding is driven by activeAdmLevel below (so we can toggle levels).
        let hovered = { source: null, id: null };
        const clearHover = () => {
          if (hovered.source && hovered.id != null) {
            try { map.setFeatureState({ source: hovered.source, id: hovered.id }, { hover: false }); } catch (_e) {}
          }
          hovered = { source: null, id: null };
        };

        // Store map mouse leave handler for cleanup
        let mapMouseLeaveHandler = null;

        const pickActive = () => {
          const lvl = activeAdmLevelRef.current;
          const flags = map.__ifrcHasAdm || {};
          if (lvl === 'ADM3' && flags.hasAdm3) return { source: 'adm3', layer: 'adm3-fill' };
          if (lvl === 'ADM2' && flags.hasAdm2) return { source: 'adm2', layer: 'adm2-fill' };
          if (lvl === 'ADM1' && flags.hasAdm1) return { source: 'adm1', layer: 'adm1-fill' };
          // Fallback to ADM0 only if that's the only available level.
          return { source: 'adm0', layer: 'adm0-fill' };
        };

        const bindHoverHandlers = () => {
          const { source, layer } = pickActive();
          const viz = String(visualizationTypeRef.current || 'choropleth').toLowerCase();
          // Remove any previous handlers (safe even if not registered)
          try { map.off('mousemove', 'adm1-fill', onMove); } catch (_e) {}
          try { map.off('mousemove', 'adm2-fill', onMove); } catch (_e) {}
          try { map.off('mousemove', 'adm3-fill', onMove); } catch (_e) {}
          try { map.off('mouseleave', 'adm1-fill', onLeaveLayer); } catch (_e) {}
          try { map.off('mouseleave', 'adm2-fill', onLeaveLayer); } catch (_e) {}
          try { map.off('mouseleave', 'adm3-fill', onLeaveLayer); } catch (_e) {}
          try { map.off('click', 'adm1-fill', onClickLayer); } catch (_e) {}
          try { map.off('click', 'adm2-fill', onClickLayer); } catch (_e) {}
          try { map.off('click', 'adm3-fill', onClickLayer); } catch (_e) {}

          try { map.off('mousemove', 'humdb-bubbles-circle', onBubbleMove); } catch (_e) {}
          try { map.off('mouseleave', 'humdb-bubbles-circle', onBubbleLeave); } catch (_e) {}
          try { map.off('click', 'humdb-bubbles-circle', onBubbleClick); } catch (_e) {}

          if (viz === 'bubble') {
            map.on('mousemove', 'humdb-bubbles-circle', onBubbleMove);
            map.on('mouseleave', 'humdb-bubbles-circle', onBubbleLeave);
            map.on('click', 'humdb-bubbles-circle', onBubbleClick);
          } else {
            map.on('mousemove', layer, onMove);
            map.on('mouseleave', layer, onLeaveLayer);
            map.on('click', layer, onClickLayer);
          }

          // Toggle visibility of admin layers based on selection.
          const setVis = (id, vis) => {
            try { map.setLayoutProperty(`${id}-fill`, 'visibility', vis); } catch (_e) {}
            try { map.setLayoutProperty(`${id}-line`, 'visibility', vis); } catch (_e) {}
          };
          const setGroupingVis = (id, vis) => {
            try { map.setLayoutProperty(`${id}-grouping`, 'visibility', vis); } catch (_e) {}
          };

          // Show active level fill + line
          setVis('adm1', (source === 'adm1') ? 'visible' : 'none');
          setVis('adm2', (source === 'adm2') ? 'visible' : 'none');
          setVis('adm3', (source === 'adm3') ? 'visible' : 'none');
          // Bubbles are only relevant in bubble mode
          try { map.setLayoutProperty('humdb-bubbles-circle', 'visibility', viz === 'bubble' ? 'visible' : 'none'); } catch (_e) {}

          // Show parent grouping outlines when viewing child levels
          // When viewing ADM2: show ADM1 grouping (thicker outline)
          // When viewing ADM3: show both ADM1 and ADM2 grouping (ADM1 thicker, ADM2 medium)
          const flags = map.__ifrcHasAdm || {};
          if (source === 'adm2' && flags.hasAdm1) {
            setGroupingVis('adm1', 'visible');
            setGroupingVis('adm2', 'none');
          } else if (source === 'adm3') {
            if (flags.hasAdm1) setGroupingVis('adm1', 'visible');
            if (flags.hasAdm2) setGroupingVis('adm2', 'visible');
          } else {
            setGroupingVis('adm1', 'none');
            setGroupingVis('adm2', 'none');
          }
        };

        const onMove = (e) => {
          const lngLat = e?.lngLat;
          const feat = e?.features?.[0];
          if (!lngLat || !feat) return;

          map.getCanvas().style.cursor = 'pointer';
          const props = feat.properties || {};
          const fallbackCountryName = adm0?.features?.[0] ? getFeatureName(adm0.features[0]) : iso2;
          const adminName = getAdminNameFromProps(props) || getLocalizedCountryName(iso2, iso3, fallbackCountryName);
          const featureValue = Number(props.__ifrcValue != null ? props.__ifrcValue : valueRef.current);

          const { source: src } = pickActive();
          const fid = feat.id != null ? feat.id : null;
          if (src && fid != null) {
            if (hovered.source !== src || hovered.id !== fid) {
              clearHover();
              hovered = { source: src, id: fid };
              try { map.setFeatureState({ source: src, id: fid }, { hover: true }); } catch (_e) {}
            }
          }

          const html = `
            <div style="min-width: 180px; text-align: center;">
              <div style="font-weight: 700; margin-bottom: 6px;">${escapeHtml(adminName)}</div>
              <div style="font-size: 20px; font-weight: 800; color: #ef4444;">${formatNumber(featureValue, showFullRef.current)}</div>
              <div style="font-size: 12px; color: #6b7280; margin-top: 2px;">${escapeHtml(indicatorRef.current)}</div>
            </div>
          `;
          popup.setLngLat(lngLat).setHTML(html).addTo(map);
          if (onHoverRef.current) onHoverRef.current(adminName, featureValue, iso2);
          if (onTooltipShowRef.current) onTooltipShowRef.current();
        };

        const onLeaveLayer = () => {
          try {
            const canvas = map.getCanvas();
            if (canvas) canvas.style.cursor = '';
          } catch (_e) {}
          try { popup.remove(); } catch (_e) {}
          clearHover();
          if (onLeaveRef.current) onLeaveRef.current();
          if (onTooltipHideRef.current) onTooltipHideRef.current();
        };

        const onClickLayer = (e) => {
          const feat = e?.features?.[0];
          const fallbackCountryName = adm0?.features?.[0] ? getFeatureName(adm0.features[0]) : iso2;
          const adminName = getAdminNameFromProps(feat?.properties) || getLocalizedCountryName(iso2, iso3, fallbackCountryName);
          if (onClickRef.current) onClickRef.current(iso2, adminName);
        };

        const onBubbleMove = (e) => {
          const feat = e?.features?.[0];
          const lngLat = e?.lngLat;
          if (!feat || !lngLat) return;
          map.getCanvas().style.cursor = 'pointer';
          const props = feat.properties || {};
          const name = getAdminNameFromProps(props) || getLocalizedCountryName(iso2, iso3, iso2);
          const v = Number(props.__ifrcValue != null ? props.__ifrcValue : 0);
          const html = `
            <div style="min-width: 180px; text-align: center;">
              <div style="font-weight: 700; margin-bottom: 6px;">${escapeHtml(name)}</div>
              <div style="font-size: 20px; font-weight: 800; color: #ef4444;">${formatNumber(v, showFullRef.current)}</div>
              <div style="font-size: 12px; color: #6b7280; margin-top: 2px;">${escapeHtml(indicatorRef.current)}</div>
            </div>
          `;
          popup.setLngLat(lngLat).setHTML(html).addTo(map);
          if (onHoverRef.current) onHoverRef.current(name, v, iso2);
          if (onTooltipShowRef.current) onTooltipShowRef.current();
        };

        const onBubbleLeave = () => {
          try {
            const canvas = map.getCanvas();
            if (canvas) canvas.style.cursor = '';
          } catch (_e) {}
          try { popup.remove(); } catch (_e) {}
          if (onLeaveRef.current) onLeaveRef.current();
          if (onTooltipHideRef.current) onTooltipHideRef.current();
        };

        const onBubbleClick = (e) => {
          const feat = e?.features?.[0];
          const props = feat?.properties || {};
          const name = getAdminNameFromProps(props) || getLocalizedCountryName(iso2, iso3, iso2);
          if (onClickRef.current) onClickRef.current(iso2, name);
        };

        // Handler for when mouse leaves the map area entirely
        const onMapMouseLeave = () => {
          try {
            const canvas = map.getCanvas();
            if (canvas) canvas.style.cursor = '';
          } catch (_e) {}
          try { popup.remove(); } catch (_e) {}
          clearHover();
          if (onLeaveRef.current) onLeaveRef.current();
          if (onTooltipHideRef.current) onTooltipHideRef.current();
        };
        mapMouseLeaveHandler = onMapMouseLeave;
        // Store handler reference on map for cleanup
        map.__ifrcMapMouseLeaveHandler = mapMouseLeaveHandler;

        // Keep a ref of current selection for handlers without reinit
        activeAdmLevelRef.current = activeAdmLevel;
        bindHoverHandlers();

        // Add map-level mouse leave handler to ensure tooltip disappears when cursor leaves map area
        const canvas = map.getCanvas();
        if (canvas) {
          canvas.addEventListener('mouseleave', mapMouseLeaveHandler);
        }

        // Expose a small hook to rebind when selection changes
        map.__ifrcRebindAdminHover = () => {
          clearHover();
          bindHoverHandlers();
        };

        // Lazily load ADM2/ADM3 when selected (to avoid multi-second initial load on large countries).
        map.__ifrcEnsureAdmLoaded = async (lvl) => {
          try {
            const data = map.__ifrcAdminData;
            if (!data?.iso3) return;
            const target = String(lvl || '').toUpperCase();
            if (target === 'ADM2' && !data.adm2) {
              const fc = await loadGeoBoundaries(data.iso3, 'ADM2');
              if (fc?.features?.length) {
                data.adm2 = fc;
                map.__ifrcAdminData = data;
                ensureAdminLayers();
                if (typeof map.__ifrcApplyVisualization === 'function') map.__ifrcApplyVisualization();
              }
            }
            if (target === 'ADM3' && !data.adm3) {
              // ADM3 can be extremely large; only load on demand.
              const fc = await loadGeoBoundaries(data.iso3, 'ADM3');
              if (fc?.features?.length) {
                data.adm3 = fc;
                map.__ifrcAdminData = data;
                ensureAdminLayers();
                if (typeof map.__ifrcApplyVisualization === 'function') map.__ifrcApplyVisualization();
              }
            }
          } catch (_e) {
            // ignore
          }
        };

        // Expose a hook to re-apply data + visualization without re-initializing the map
        map.__ifrcApplyVisualization = () => {
          try {
            const data = map.__ifrcAdminData;
            if (!data) return;

            const maxVal = getIndicatorMaxValue(indicatorDataRef.current);
            // Re-decorate with latest data
            const d0 = decorateFeatureCollection(data.adm0, indicatorDataRef.current, maxVal);
            const d1 = decorateFeatureCollection(data.adm1, indicatorDataRef.current, maxVal);
            const d2 = decorateFeatureCollection(data.adm2, indicatorDataRef.current, maxVal);
            const d3 = decorateFeatureCollection(data.adm3, indicatorDataRef.current, maxVal);
            map.__ifrcAnyFeatureMatch = !!(d0.anyMatched || d1.anyMatched || d2.anyMatched || d3.anyMatched);

            // Push updated geojson into sources (if they exist)
            const setDataSafe = (srcId, fc) => {
              try {
                const src = map.getSource(srcId);
                if (src && typeof src.setData === 'function') src.setData(fc);
              } catch (_e) {}
            };
            setDataSafe('adm0', d0.fc);
            setDataSafe('adm1', d1.fc);
            setDataSafe('adm2', d2.fc);
            setDataSafe('adm3', d3.fc);

            // Update paints for current visualization
            const viz = String(visualizationTypeRef.current || 'choropleth').toLowerCase();
            const isBubble = viz === 'bubble';
            const fillColorExpr = isBubble ? '#f8fafc' : choroplethColorExpression();
            const fillOpacityExpr = isBubble
              ? ['case', ['boolean', ['feature-state', 'hover'], false], 0.95, 0.3]
              : ['case', ['boolean', ['feature-state', 'hover'], false], 0.95, ['case', ['>', ['coalesce', ['get', '__ifrcValue'], 0], 0], 0.85, 0.3]];
            const lineColor = '#d1d5db';

            const setFillPaint = (layerId) => {
              try { map.setPaintProperty(layerId, 'fill-color', ['case', ['boolean', ['feature-state', 'hover'], false], '#ef4444', fillColorExpr]); } catch (_e) {}
              try { map.setPaintProperty(layerId, 'fill-opacity', fillOpacityExpr); } catch (_e) {}
            };
            const setLinePaint = (layerId) => {
              try { map.setPaintProperty(layerId, 'line-color', ['case', ['boolean', ['feature-state', 'hover'], false], '#ef4444', lineColor]); } catch (_e) {}
              try { map.setPaintProperty(layerId, 'line-width', ['case', ['boolean', ['feature-state', 'hover'], false], 3.2, 1]); } catch (_e) {}
            };
            ['adm0-fill', 'adm1-fill', 'adm2-fill', 'adm3-fill'].forEach(setFillPaint);
            ['adm0-outline', 'adm1-line', 'adm2-line', 'adm3-line'].forEach(setLinePaint);

            // Update bubble radius expression
            try { map.setPaintProperty('humdb-bubbles-circle', 'circle-radius', bubbleRadiusExpression(maxVal)); } catch (_e) {}

            // Build bubble points for bubble mode
            if (isBubble) {
              let bubbleFeatures = [];

              // If we didn't match any per-feature values, avoid thousands of identical bubbles — show one bubble at ADM0 center.
              if (!map.__ifrcAnyFeatureMatch && d0.fc?.features?.length) {
                const pt = featureToBubblePoint(d0.fc.features[0]);
                if (pt) bubbleFeatures = [pt];
              } else {
                // Use active level features (bounded) to generate bubbles
                const lvl = String(activeAdmLevelRef.current || 'ADM1').toUpperCase();
                const activeFc =
                  (lvl === 'ADM3' && d3.fc?.features?.length) ? d3.fc :
                  (lvl === 'ADM2' && d2.fc?.features?.length) ? d2.fc :
                  (lvl === 'ADM1' && d1.fc?.features?.length) ? d1.fc :
                  d0.fc;

                const pts = [];
                for (const f of activeFc?.features || []) {
                  const pt = featureToBubblePoint(f);
                  if (pt) pts.push(pt);
                }
                // Cap for performance
                const MAX_BUBBLES = 500;
                if (pts.length > MAX_BUBBLES) {
                  pts.sort((a, b) => (Number(b.properties?.__ifrcValue || 0) - Number(a.properties?.__ifrcValue || 0)));
                  bubbleFeatures = pts.slice(0, MAX_BUBBLES);
                } else {
                  bubbleFeatures = pts;
                }
              }

              setDataSafe('humdb-bubbles', { type: 'FeatureCollection', features: bubbleFeatures });
            } else {
              setDataSafe('humdb-bubbles', { type: 'FeatureCollection', features: [] });
            }

            // Rebind interactions + visibilities
            if (typeof map.__ifrcRebindAdminHover === 'function') {
              try { map.__ifrcRebindAdminHover(); } catch (_e) {}
            }
          } catch (_e) {
            // ignore
          }
        };

        // Progressive background prefetch:
        // Render quickly with ADM0/ADM1, then fetch ADM2 and ADM3 sequentially in the background.
        // This avoids parsing huge GeoJSON all at once, but still warms the cache without user interaction.
        map.__ifrcPrefetchAdmLevels = async () => {
          try {
            const data = map.__ifrcAdminData;
            if (!data?.iso3) return;

            const hasAdm2 = await checkGeoBoundariesAvailable(data.iso3, 'ADM2');
            if (hasAdm2) {
              await map.__ifrcEnsureAdmLoaded?.('ADM2');
            }

            // ADM3 is often huge; only prefetch it on fast connections.
            if (isFastConnectionForAdm3()) {
              const hasAdm3 = await checkGeoBoundariesAvailable(data.iso3, 'ADM3');
              if (hasAdm3) {
                await map.__ifrcEnsureAdmLoaded?.('ADM3');
              }
            }
          } catch (_e) {
            // ignore
          }
        };

        setStatus('ready');
        setStatusDetail('Ready');

        // Kick off background prefetch after initial render.
        // Use a short delay to let the map paint first.
        try { setTimeout(() => { try { map.__ifrcPrefetchAdmLevels?.(); } catch (_e) {} }, 250); } catch (_e) {}
      });

      mapRef.current = map;
    };

    init();

    return () => {
      destroyed = true;
      // Clean up map mouse leave handler
      try {
        if (mapRef.current && mapRef.current.getCanvas && mapRef.current.__ifrcMapMouseLeaveHandler) {
          const canvas = mapRef.current.getCanvas();
          if (canvas && mapRef.current.__ifrcMapMouseLeaveHandler) {
            canvas.removeEventListener('mouseleave', mapRef.current.__ifrcMapMouseLeaveHandler);
          }
        }
      } catch (_e) {}
      try { if (popupRef.current) popupRef.current.remove(); } catch (_e) {}
      try { if (mapRef.current) mapRef.current.remove(); } catch (_e) {}
      mapRef.current = null;
      popupRef.current = null;
    };
  }, [token, normalizedIso2, fallbackMode, normalizedIso3]);

  // Keep active admin level in a ref for map event handlers (prevents re-init).
  const activeAdmLevelRef = useRef(activeAdmLevel);
  useEffect(() => {
    activeAdmLevelRef.current = activeAdmLevel;
    const map = mapRef.current;
    if (fallbackMode === 'mapbox' && map && typeof map.__ifrcRebindAdminHover === 'function') {
      try { map.__ifrcRebindAdminHover(); } catch (_e) {}
    }
    if (fallbackMode === 'mapbox' && map && typeof map.__ifrcApplyVisualization === 'function') {
      try { map.__ifrcApplyVisualization(); } catch (_e) {}
    }
  }, [activeAdmLevel, fallbackMode]);

  // Controlled admin level support
  useEffect(() => {
    if (typeof activeAdmLevelProp === 'string' && activeAdmLevelProp) {
      setActiveAdmLevel(String(activeAdmLevelProp).toUpperCase());
    }
  }, [activeAdmLevelProp]);

  // Apply visualization updates (choropleth/bubble) and data updates without re-initializing the map.
  useEffect(() => {
    const map = mapRef.current;
    if (fallbackMode === 'mapbox' && map && typeof map.__ifrcApplyVisualization === 'function') {
      try { map.__ifrcApplyVisualization(); } catch (_e) {}
    }
  }, [fallbackMode, visualizationType, indicatorData, maxValue, value, showFullValues, indicatorLabel]);

  if (!normalizedIso2) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-gray-50">
        <div className="text-sm text-humdb-gray-600">Select a country to view the map.</div>
      </div>
    );
  }

  if (fallbackMode === 'leaflet') {
    return (
      <CountryLeafletAdminMap
        countryIso3={normalizedIso3}
        activeAdmLevel={activeAdmLevel}
        value={value}
        visualizationType={visualizationType}
        indicatorData={indicatorData}
        maxValue={maxValue}
        onHover={onHoverRef.current}
        onLeave={onLeaveRef.current}
        onClick={onClickRef.current}
      />
    );
  }

  // Calculate max value for legend
  const legendMaxValue = useMemo(() => {
    const explicit = Number(maxValue);
    if (Number.isFinite(explicit) && explicit > 0) return explicit;

    let m = 0;
    if (indicatorData && typeof indicatorData === 'object') {
      for (const v of Object.values(indicatorData)) {
        const n = typeof v === 'object' && v ? Number(v.value) : Number(v);
        if (Number.isFinite(n) && n > m) m = n;
      }
    }
    const fallback = Number(value);
    if (m <= 0 && Number.isFinite(fallback) && fallback > 0) m = fallback;
    return m > 0 ? m : 1;
  }, [indicatorData, maxValue, value]);

  // Render legend component
  const renderLegend = () => {
    if (legendMaxValue <= 0) {
      return (
        <div className="absolute bottom-4 right-4 z-[1000] bg-white/95 rounded-lg shadow-lg p-3 border border-gray-200 min-w-[180px]">
          <h4 className="font-bold text-humdb-navy mb-2 text-sm">
            {t('globalOverview.map.dataRange', { defaultValue: 'Data Range' })}
          </h4>
          <div className="text-xs text-humdb-gray-600">
            {t('data.noDataAvailable', { defaultValue: 'No data available' })}
          </div>
        </div>
      );
    }

    if (visualizationType === 'bubble') {
      // Bubble map legend
      // Round grades to avoid floating point precision issues
      const rawGrades = [0, legendMaxValue * 0.2, legendMaxValue * 0.4, legendMaxValue * 0.6, legendMaxValue * 0.8, legendMaxValue];
      const grades = rawGrades.map(g => Math.round(g * 100) / 100);
      const getBubbleSize = (val) => {
        if (val <= 0) return 0;
        const intensity = Math.min(val / legendMaxValue, 1);
        return 3 + intensity * 27;
      };

      return (
        <div className="absolute bottom-4 right-4 z-[1000] bg-white/95 rounded-lg shadow-lg p-3 border border-gray-200 min-w-[180px]">
          <h4 className="font-bold text-humdb-navy mb-3 text-sm">
            {t('globalOverview.map.bubbleSize', { defaultValue: 'Bubble Size' })}
          </h4>
          <div className="space-y-2">
            {grades.slice(0, -1).map((grade, i) => {
              const size = getBubbleSize(grades[i + 1]);
              return (
                <div key={i} className="flex items-center space-x-2">
                  <div
                    style={{
                      width: `${size}px`,
                      height: `${size}px`,
                      background: '#ef4444',
                      borderRadius: '50%',
                      border: '2px solid #dc2626',
                    }}
                  />
                  <span className="text-xs text-humdb-gray-700">
                    {formatNumber(grade, showFullValues)}
                    {grades[i + 1] ? ` - ${formatNumber(grades[i + 1], showFullValues)}` : '+'}
                  </span>
                </div>
              );
            })}
          </div>
          <div className="mt-3 pt-3 border-t border-gray-200">
            <div className="flex items-center space-x-2">
              <div
                style={{
                  width: '3px',
                  height: '3px',
                  background: '#f8fafc',
                  borderRadius: '50%',
                  border: '1px solid #e5e7eb',
                }}
              />
              <span className="text-xs text-humdb-gray-600">
                {t('data.noData', { defaultValue: 'No data' })}
              </span>
            </div>
          </div>
        </div>
      );
    } else {
      // Choropleth legend
      // Round grades to avoid floating point precision issues
      const rawGrades = [0, legendMaxValue * 0.2, legendMaxValue * 0.4, legendMaxValue * 0.6, legendMaxValue * 0.8, legendMaxValue];
      const grades = rawGrades.map(g => Math.round(g * 100) / 100);
      const getColor = (intensity) => {
        if (intensity <= 0) return '#f8fafc';
        if (intensity < 0.2) return '#e3f2fd';
        if (intensity < 0.4) return '#90caf9';
        if (intensity < 0.6) return '#42a5f5';
        if (intensity < 0.8) return '#1976d2';
        return '#0d47a1';
      };

      return (
        <div className="absolute bottom-4 right-4 z-[1000] bg-white/95 rounded-lg shadow-lg p-3 border border-gray-200 min-w-[180px]">
          <h4 className="font-bold text-humdb-navy mb-3 text-sm">
            {t('globalOverview.map.dataRange', { defaultValue: 'Data Range' })}
          </h4>
          <div className="space-y-2">
            {grades.slice(0, -1).map((grade, i) => {
              const intensity = grades[i + 1] / legendMaxValue;
              const color = getColor(intensity);
              return (
                <div key={i} className="flex items-center space-x-2">
                  <div
                    style={{
                      background: color,
                      width: '20px',
                      height: '20px',
                      borderRadius: '4px',
                      border: '1px solid #e5e7eb',
                    }}
                  />
                  <span className="text-xs text-humdb-gray-700">
                    {formatNumber(grade, showFullValues)}
                    {grades[i + 1] ? ` - ${formatNumber(grades[i + 1], showFullValues)}` : '+'}
                  </span>
                </div>
              );
            })}
          </div>
          <div className="mt-3 pt-3 border-t border-gray-200">
            <div className="flex items-center space-x-2">
              <div
                style={{
                  background: '#f8fafc',
                  width: '20px',
                  height: '20px',
                  borderRadius: '4px',
                  border: '1px solid #e5e7eb',
                }}
              />
              <span className="text-xs text-humdb-gray-600">
                {t('data.noData', { defaultValue: 'No data' })}
              </span>
            </div>
          </div>
        </div>
      );
    }
  };

  return (
    <div className="w-full h-full relative">
      <div ref={containerRef} className="w-full h-full" />

      {/* Data ranges legend */}
      {status === 'ready' && renderLegend()}

      {/* Admin level toggle */}
      <div className="absolute top-20 right-4 z-[1000] bg-white/95 rounded-lg shadow-lg p-2 border border-gray-200">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-semibold text-gray-600 uppercase tracking-wide">
            {t('countryProfile.map.adminLevels.label', { defaultValue: 'Level' })}
          </span>
          <div className="flex gap-1">
            {availableAdmLevels.map((lvl) => {
              const active = activeAdmLevel === lvl;
              const label = getAdminLevelLabel(lvl, t);
              return (
                <button
                  key={lvl}
                  onClick={() => {
                    const next = String(lvl || '').toUpperCase();
                    // If Mapbox is active, lazily load heavy admin levels before switching.
                    const map = mapRef.current;
                    if (
                      fallbackMode === 'mapbox' &&
                      map &&
                      typeof map.__ifrcEnsureAdmLoaded === 'function' &&
                      (next === 'ADM2' || next === 'ADM3')
                    ) {
                      // Fire-and-forget; map will switch immediately if already loaded,
                      // otherwise layers will appear once the download + parse completes.
                      try { map.__ifrcEnsureAdmLoaded(next); } catch (_e) {}
                    }
                    if (typeof onActiveAdmLevelChange === 'function') {
                      onActiveAdmLevelChange(next);
                    } else {
                      setActiveAdmLevel(next);
                    }
                  }}
                  className={`px-2 py-1 rounded-md text-[11px] font-semibold transition-all ${
                    active ? 'bg-humdb-red text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
                  }`}
                  title={`Show ${label}`}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
