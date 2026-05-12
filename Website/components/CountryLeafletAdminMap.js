import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from '../lib/useTranslation';

// Leaflet fallback for country admin boundaries (ADM0-ADM3) using geoBoundaries.
// Used when Mapbox GL can't render (e.g., WebGL not available).

function computeBboxFromFeatureCollection(fc) {
  if (!fc?.features?.length) return null;
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

  for (const f of fc.features) {
    const coords = f?.geometry?.coordinates;
    if (coords) walk(coords);
  }

  if (!Number.isFinite(minX) || !Number.isFinite(minY) || !Number.isFinite(maxX) || !Number.isFinite(maxY)) return null;
  return [[minY, minX], [maxY, maxX]]; // Leaflet: [lat, lng]
}

function getAdminNameFromProps(p) {
  if (!p) return null;
  return (
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

function isFastConnectionForAdm3() {
  // Conservative: only prefetch ADM3 when we can confidently detect a fast connection.
  try {
    if (typeof navigator === 'undefined') return false;
    const c = navigator.connection || navigator.mozConnection || navigator.webkitConnection;
    if (!c) return false;
    if (c.saveData) return false;

    const effectiveType = String(c.effectiveType || '').toLowerCase();
    const downlink = Number(c.downlink);
    const rtt = Number(c.rtt);
    const deviceMemory = Number(navigator.deviceMemory);

    const looksFastType = effectiveType === '4g' || effectiveType === '5g';
    const looksFastDownlink = Number.isFinite(downlink) ? downlink >= 5 : false;
    const looksOkRtt = Number.isFinite(rtt) ? rtt <= 150 : true;
    const looksOkMemory = Number.isFinite(deviceMemory) ? deviceMemory >= 4 : true;

    return (looksFastType || looksFastDownlink) && looksOkRtt && looksOkMemory;
  } catch (_e) {
    return false;
  }
}

async function loadGeoBoundaries(iso3, adm) {
  if (!iso3) return null;

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

export default function CountryLeafletAdminMap({
  countryIso3,
  activeAdmLevel = 'ADM1',
  value = 0,
  visualizationType = 'choropleth', // 'choropleth' | 'bubble'
  indicatorData = null, // optional: map keyed by shapeID|shapeISO|shapeName -> number | { value, name }
  maxValue = null, // optional max for normalization
  onHover,
  onLeave,
  onClick,
}) {
  const { t } = useTranslation();
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const layersRef = useRef([]);
  const adminLayersRef = useRef({}); // { ADM1, ADM2, ADM3 }
  const groupingLayersRef = useRef({}); // { ADM1, ADM2 } - grouping outline layers
  const bubbleLayerRef = useRef(null);
  const [error, setError] = useState(null);

  const onHoverRef = useRef(onHover);
  const onLeaveRef = useRef(onLeave);
  const onClickRef = useRef(onClick);
  useEffect(() => { onHoverRef.current = onHover; }, [onHover]);
  useEffect(() => { onLeaveRef.current = onLeave; }, [onLeave]);
  useEffect(() => { onClickRef.current = onClick; }, [onClick]);

  const iso3 = useMemo(() => (countryIso3 ? String(countryIso3).toUpperCase() : null), [countryIso3]);

  const normalizeKey = (v) => {
    if (v == null) return '';
    return String(v).trim().toLowerCase().replace(/[\s\W_]+/g, '');
  };

  const getIndicatorMaxValue = () => {
    const explicit = Number(maxValue);
    if (Number.isFinite(explicit) && explicit > 0) return explicit;
    let m = 0;
    if (indicatorData && typeof indicatorData === 'object') {
      for (const v of Object.values(indicatorData)) {
        const n = typeof v === 'object' && v ? Number(v.value) : Number(v);
        if (Number.isFinite(n) && n > m) m = n;
      }
    }
    const fallback = Number(value || 0);
    if (m <= 0 && Number.isFinite(fallback) && fallback > 0) m = fallback;
    return m > 0 ? m : 1;
  };

  const buildIndicatorLookup = () => {
    const lookup = new Map(); // normalized -> { value, name }
    if (!indicatorData || typeof indicatorData !== 'object') return lookup;
    for (const [rawKey, rawVal] of Object.entries(indicatorData)) {
      const v = typeof rawVal === 'object' && rawVal ? Number(rawVal.value) : Number(rawVal);
      const name = typeof rawVal === 'object' && rawVal ? rawVal.name : null;
      if (!Number.isFinite(v)) continue;
      const add = (k) => {
        const nk = normalizeKey(k);
        if (!nk) return;
        if (!lookup.has(nk)) lookup.set(nk, { value: v, name });
      };
      add(rawKey);
      add(String(rawKey).toUpperCase());
      add(String(rawKey).toLowerCase());
      if (name) add(name);
    }
    return lookup;
  };

  const getColor = (v, m) => {
    if (!v || v === 0) return '#f8fafc';
    const intensity = Math.min(v / m, 1);
    if (intensity < 0.2) return '#e3f2fd';
    if (intensity < 0.4) return '#90caf9';
    if (intensity < 0.6) return '#42a5f5';
    if (intensity < 0.8) return '#1976d2';
    return '#0d47a1';
  };

  const getBubbleSize = (v, m) => {
    if (!v || v === 0) return 0;
    const minSize = 3;
    const maxSize = 30;
    const intensity = Math.min(v / m, 1);
    return minSize + (intensity * (maxSize - minSize));
  };

  useEffect(() => {
    let destroyed = false;

    const init = async () => {
      if (!containerRef.current) return;
      if (!iso3) {
        setError('Missing ISO3 for admin boundaries.');
        return;
      }

      // Clean up previous map
      if (mapRef.current) {
        try {
          layersRef.current.forEach((l) => mapRef.current.removeLayer(l));
        } catch (_e) {}
        layersRef.current = [];
        try {
          mapRef.current.remove();
        } catch (_e) {}
        mapRef.current = null;
      }

      let L;
      try {
        L = (await import('leaflet')).default;
        if (!document.querySelector('link[href*="leaflet.css"]')) {
          await import('leaflet/dist/leaflet.css');
        }
      } catch (e) {
        setError(`Failed to load Leaflet: ${e?.message || String(e)}`);
        return;
      }

      if (destroyed) return;

      const map = L.map(containerRef.current, {
        center: [20, 0],
        zoom: 2,
        zoomControl: true,
        attributionControl: false,
      });

      // Field-only mode: simple background (no underlying basemap)
      containerRef.current.style.background = '#f8fafc';

      mapRef.current = map;

      try {
        // Load only what we need for fast initial render.
        // ADM2/ADM3 can be huge; only fetch if the selected level requires it.
        const desired = String(activeAdmLevel || 'ADM1').toUpperCase();
        const needAdm2 = desired === 'ADM2' || desired === 'ADM3';
        const needAdm3 = desired === 'ADM3';

        const [adm0, adm1, adm2, adm3] = await Promise.all([
          loadGeoBoundaries(iso3, 'ADM0'),
          loadGeoBoundaries(iso3, 'ADM1'),
          needAdm2 ? loadGeoBoundaries(iso3, 'ADM2') : null,
          needAdm3 ? loadGeoBoundaries(iso3, 'ADM3') : null,
        ]);

        if (destroyed) return;

        if (!adm0) throw new Error('No ADM0 boundary available.');

        const bounds = computeBboxFromFeatureCollection(adm0);
        if (bounds) {
          map.fitBounds(bounds, { padding: [30, 30] });
        }

        const maxVal = getIndicatorMaxValue();
        const lookup = buildIndicatorLookup();

        const decorate = (fc) => {
          if (!fc?.features?.length) return { fc, anyMatched: false };
          let anyMatched = false;
          for (const f of fc.features) {
            const p = f.properties || (f.properties = {});
            const candidates = [p.shapeID, p.shapeISO, p.shapeName, p.name, p.NAME].filter(Boolean);
            let matched = null;
            for (const cand of candidates) {
              const hit = lookup.get(normalizeKey(cand));
              if (hit) { matched = hit; break; }
            }
            const v = matched ? matched.value : Number(value || 0);
            const safeV = Number.isFinite(v) ? v : 0;
            p.__humdbValue = safeV;
            p.__humdbIntensity = maxVal > 0 ? Math.min(safeV / maxVal, 1) : 0;
            if (matched?.name) p.__humdbName = matched.name;
            if (matched) anyMatched = true;
          }
          return { fc, anyMatched };
        };

        const d0 = decorate(adm0);
        const d1 = decorate(adm1);
        const d2 = decorate(adm2);
        const d3 = decorate(adm3);
        const anyMatched = !!(d0.anyMatched || d1.anyMatched || d2.anyMatched || d3.anyMatched);

        const addAdminLayer = (fc, color, weight, dashArray, baseFillOpacity) => {
          if (!fc?.features?.length) return null;
          const viz = String(visualizationType || 'choropleth').toLowerCase();
          const isBubble = viz === 'bubble';
          const layer = L.geoJSON(fc, {
            style: (feature) => {
              const p = feature?.properties || {};
              const v = Number(p.__humdbValue || 0);
              return {
                color: '#d1d5db',
                weight: 1,
                dashArray: dashArray || null,
                opacity: 1,
                fillColor: isBubble ? '#f8fafc' : getColor(v, maxVal),
                fillOpacity: isBubble ? 0.3 : (v > 0 ? 0.85 : 0.3),
              };
            },
            onEachFeature: (feature, layer) => {
              layer.on('mouseover', () => {
                const props = feature?.properties || {};
                const name = getAdminNameFromProps(props) || iso3;
                const v = Number(props.__humdbValue != null ? props.__humdbValue : (value || 0));
                try {
                  layer.setStyle({
                    fillOpacity: 0.95,
                    color: '#ef4444',
                    weight: 2,
                    fillColor: '#ef4444',
                  });
                } catch (_e) {}
                if (onHoverRef.current) onHoverRef.current(name, v, iso3);
              });
              layer.on('mouseout', () => {
                try {
                  const p = feature?.properties || {};
                  const v = Number(p.__humdbValue || 0);
                  const viz = String(visualizationType || 'choropleth').toLowerCase();
                  const isBubble = viz === 'bubble';
                  layer.setStyle({
                    color: '#d1d5db',
                    weight: 1,
                    opacity: 1,
                    fillColor: isBubble ? '#f8fafc' : getColor(v, maxVal),
                    fillOpacity: isBubble ? 0.3 : (v > 0 ? 0.85 : 0.3),
                  });
                } catch (_e) {}
                if (onLeaveRef.current) onLeaveRef.current();
              });
              layer.on('click', () => {
                const name = getAdminNameFromProps(feature?.properties) || iso3;
                if (onClickRef.current) onClickRef.current(iso3, name);
              });
            },
          });
          layer.addTo(map);
          return layer;
        };

        const hasAdm1 = !!adm1?.features?.length;

        // Option B: do NOT render ADM0 when ADM1+ exists (avoid misalignment).
        // Keep ADM0 only as fallback when ADM1 is missing.
        if (!hasAdm1) {
          const adm0Layer = L.geoJSON(adm0, {
            style: { color: '#dc2626', weight: 2, fillColor: '#ef4444', fillOpacity: 0.12, opacity: 1 },
          }).addTo(map);
          layersRef.current.push(adm0Layer);
        }

        const adm1Layer = addAdminLayer(d1.fc, '#374151', 2.2, null, 0.03);
        const adm2Layer = addAdminLayer(d2.fc, '#6b7280', 1.8, '2 2', 0.02);
        const adm3Layer = addAdminLayer(d3.fc, '#9ca3af', 1.2, '1 1', 0.01);

        // Create grouping outline layers (thicker parent admin level lines for context)
        const addGroupingLayer = (fc, color, weight) => {
          if (!fc?.features?.length) return null;
          const layer = L.geoJSON(fc, {
            style: {
              color,
              weight,
              fill: false,
              opacity: 0.9,
            },
          });
          return layer;
        };

        const adm1GroupingLayer = addGroupingLayer(adm1, '#374151', 3.5);
        const adm2GroupingLayer = addGroupingLayer(adm2, '#6b7280', 2.8);

        adminLayersRef.current = { ADM1: adm1Layer, ADM2: adm2Layer, ADM3: adm3Layer };
        groupingLayersRef.current = { ADM1: adm1GroupingLayer, ADM2: adm2GroupingLayer };

        // Show active admin layer + parent grouping outlines
        const applyVisibility = () => {
          const lvl = String(activeAdmLevel || 'ADM1').toUpperCase();

          // Show/hide main admin layers
          ['ADM1', 'ADM2', 'ADM3'].forEach((k) => {
            const layer = adminLayersRef.current[k];
            if (!layer) return;
            const shouldShow = lvl === k;
            if (shouldShow) {
              try { layer.addTo(map); } catch (_e) {}
            } else {
              try { map.removeLayer(layer); } catch (_e) {}
            }
          });

          // Show parent grouping outlines when viewing child levels
          // When viewing ADM2: show ADM1 grouping (thicker outline)
          // When viewing ADM3: show both ADM1 and ADM2 grouping (ADM1 thicker, ADM2 medium)
          const adm1Grouping = groupingLayersRef.current.ADM1;
          const adm2Grouping = groupingLayersRef.current.ADM2;
          if (lvl === 'ADM2' && adm1Grouping) {
            try { adm1Grouping.addTo(map); } catch (_e) {}
            if (adm2Grouping) {
              try { map.removeLayer(adm2Grouping); } catch (_e) {}
            }
          } else if (lvl === 'ADM3') {
            if (adm1Grouping) {
              try { adm1Grouping.addTo(map); } catch (_e) {}
            }
            if (adm2Grouping) {
              try { adm2Grouping.addTo(map); } catch (_e) {}
            }
          } else {
            if (adm1Grouping) {
              try { map.removeLayer(adm1Grouping); } catch (_e) {}
            }
            if (adm2Grouping) {
              try { map.removeLayer(adm2Grouping); } catch (_e) {}
            }
          }
        };
        applyVisibility();

        // Bubble overlay (only in bubble mode)
        const applyBubbles = () => {
          const viz = String(visualizationType || 'choropleth').toLowerCase();
          if (bubbleLayerRef.current) {
            try { map.removeLayer(bubbleLayerRef.current); } catch (_e) {}
            bubbleLayerRef.current = null;
          }
          if (viz !== 'bubble') return;

          const lvl = String(activeAdmLevel || 'ADM1').toUpperCase();
          const activeLayer = adminLayersRef.current[lvl] || adminLayersRef.current.ADM1 || null;
          const bubbleMarkers = [];

          if (!anyMatched && d0.fc?.features?.length) {
            // Avoid thousands of identical bubbles when we only have a single country-level value.
            const center = bounds ? L.latLngBounds(bounds).getCenter() : map.getCenter();
            const r = getBubbleSize(Number(value || 0), maxVal);
            const bubble = L.circleMarker(center, {
              radius: r,
              fillColor: '#ef4444',
              color: '#dc2626',
              weight: 2,
              opacity: 0.8,
              fillOpacity: 0.7,
            });
            bubble.on('mouseover', () => {
              try { bubble.setStyle({ fillOpacity: 0.9, opacity: 1, weight: 3 }); } catch (_e) {}
              if (onHoverRef.current) onHoverRef.current(iso3, Number(value || 0), iso3);
            });
            bubble.on('mouseout', () => {
              try { bubble.setStyle({ fillOpacity: 0.7, opacity: 0.8, weight: 2 }); } catch (_e) {}
              if (onLeaveRef.current) onLeaveRef.current();
            });
            bubble.on('click', () => {
              if (onClickRef.current) onClickRef.current(iso3, iso3);
            });
            bubbleMarkers.push(bubble);
          } else if (activeLayer && typeof activeLayer.eachLayer === 'function') {
            activeLayer.eachLayer((featLayer) => {
              const f = featLayer?.feature;
              if (!f) return;
              const p = f.properties || {};
              const v = Number(p.__humdbValue || 0);
              if (!v || v <= 0) return;
              let center = null;
              try {
                if (typeof featLayer.getBounds === 'function') center = featLayer.getBounds().getCenter();
              } catch (_e) {}
              if (!center) return;

              const r = getBubbleSize(v, maxVal);
              const bubble = L.circleMarker(center, {
                radius: r,
                fillColor: '#ef4444',
                color: '#dc2626',
                weight: 2,
                opacity: 0.8,
                fillOpacity: 0.7,
              });

              const name = getAdminNameFromProps(p) || iso3;
              bubble.on('mouseover', () => {
                try { bubble.setStyle({ fillOpacity: 0.9, opacity: 1, weight: 3 }); } catch (_e) {}
                if (onHoverRef.current) onHoverRef.current(name, v, iso3);
              });
              bubble.on('mouseout', () => {
                try { bubble.setStyle({ fillOpacity: 0.7, opacity: 0.8, weight: 2 }); } catch (_e) {}
                if (onLeaveRef.current) onLeaveRef.current();
              });
              bubble.on('click', () => {
                if (onClickRef.current) onClickRef.current(iso3, name);
              });
              bubbleMarkers.push(bubble);
            });
          }

          if (bubbleMarkers.length) {
            bubbleLayerRef.current = L.layerGroup(bubbleMarkers).addTo(map);
            layersRef.current.push(bubbleLayerRef.current);
          }
        };
        applyBubbles();

        // Progressive background prefetch:
        // Once ADM0/ADM1 are on-screen, fetch ADM2 then ADM3 sequentially in the background.
        // This warms cache and makes switching smoother without blocking initial render.
        (async () => {
          try {
            await new Promise((r) => setTimeout(r, 250));
            if (destroyed) return;

            // ADM2
            const hasAdm2 = await checkGeoBoundariesAvailable(iso3, 'ADM2');
            if (destroyed) return;
            if (hasAdm2 && !adminLayersRef.current.ADM2) {
              const fc2 = await loadGeoBoundaries(iso3, 'ADM2');
              if (destroyed) return;
              const dd2 = decorate(fc2);
              const newAdm2 = addAdminLayer(dd2.fc, '#6b7280', 1.8, '2 2', 0.02);
              adminLayersRef.current = { ...adminLayersRef.current, ADM2: newAdm2 };
              const newAdm2Grouping = addGroupingLayer(fc2, '#6b7280', 2.8);
              groupingLayersRef.current = { ...groupingLayersRef.current, ADM2: newAdm2Grouping };
              applyVisibility();
              applyBubbles();
            }

            // ADM3
            if (isFastConnectionForAdm3()) {
              const hasAdm3 = await checkGeoBoundariesAvailable(iso3, 'ADM3');
              if (destroyed) return;
              if (hasAdm3 && !adminLayersRef.current.ADM3) {
                const fc3 = await loadGeoBoundaries(iso3, 'ADM3');
                if (destroyed) return;
                const dd3 = decorate(fc3);
                const newAdm3 = addAdminLayer(dd3.fc, '#9ca3af', 1.2, '1 1', 0.01);
                adminLayersRef.current = { ...adminLayersRef.current, ADM3: newAdm3 };
                applyVisibility();
                applyBubbles();
              }
            }
          } catch (_e) {
            // ignore
          }
        })();

        // Track layers for cleanup
        [adm1Layer, adm2Layer, adm3Layer, adm1GroupingLayer, adm2GroupingLayer].filter(Boolean).forEach((l) => layersRef.current.push(l));

        setError(null);
      } catch (e) {
        setError(e?.message || String(e));
      }
    };

    init();

    return () => {
      destroyed = true;
      if (mapRef.current) {
        try {
          layersRef.current.forEach((l) => mapRef.current.removeLayer(l));
        } catch (_e) {}
        layersRef.current = [];
        try {
          mapRef.current.remove();
        } catch (_e) {}
        mapRef.current = null;
      }
    };
  }, [iso3, value, activeAdmLevel, visualizationType, indicatorData, maxValue]);

  if (!iso3) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-gray-50">
        <div className="text-sm text-humdb-gray-600">{t('common.loading')}</div>
      </div>
    );
  }

  return (
    <div className="w-full h-full relative">
      <div ref={containerRef} className="w-full h-full" />
      {error && (
        <div className="absolute inset-0 flex items-center justify-center bg-white/70 backdrop-blur-sm">
          <div className="max-w-md w-full mx-6 bg-white border border-gray-200 rounded-xl shadow-lg p-4">
            <div className="text-sm font-semibold text-humdb-gray-800 mb-1">Leaflet fallback failed</div>
            <div className="text-xs text-humdb-gray-600">{String(error)}</div>
          </div>
        </div>
      )}
    </div>
  );
}
