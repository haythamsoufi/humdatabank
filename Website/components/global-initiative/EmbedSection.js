// components/global-initiative/EmbedSection.js
// Power BI, Tableau Public, or allowlisted iframe embeds (from Backoffice).

import { motion } from 'framer-motion';

const POWERBI_HOSTS = ['app.powerbi.com', 'app.powerbigov.us', 'msit.powerbi.com'];
const TABLEAU_HOSTS = ['public.tableau.com'];

function hostMatches(host, suffixes) {
  const h = (host || '').toLowerCase();
  return suffixes.some((d) => h === d || h.endsWith(`.${d}`));
}

function isAllowedForType(url, embedType) {
  try {
    const parsed = new URL(url);
    if (parsed.protocol !== 'https:') return false;
    const t = (embedType || 'powerbi').toLowerCase();
    if (t === 'powerbi') return hostMatches(parsed.hostname, POWERBI_HOSTS);
    if (t === 'tableau') return hostMatches(parsed.hostname, TABLEAU_HOSTS);
    if (t === 'iframe') {
      return hostMatches(parsed.hostname, POWERBI_HOSTS) || hostMatches(parsed.hostname, TABLEAU_HOSTS);
    }
    return false;
  } catch {
    return false;
  }
}

/** Tableau Public: append standard embed query (iframe-friendly). */
export function buildTableauEmbedSrc(viewUrl) {
  const s = (viewUrl || '').trim();
  if (!s) return s;
  if (/[?&:]embed\s*=\s*y/i.test(s) || /:embed=y/.test(s)) return s;
  return `${s}${s.includes('?') ? '&' : '?'}:embed=y&:showVizHome=no`;
}

/**
 * Power BI "Publish to web" embeds: append params to hide the page-navigation
 * pane and action bar where supported. The bottom status bar (branding, zoom)
 * cannot be hidden for free "Publish to web" links -- that requires the
 * Power BI JavaScript SDK with embed tokens.
 */
export function buildPowerBiEmbedSrc(viewUrl) {
  const s = (viewUrl || '').trim();
  if (!s) return s;
  try {
    const u = new URL(s);
    if (u.protocol !== 'https:') return s;
    if (!hostMatches(u.hostname, POWERBI_HOSTS)) return s;
    u.searchParams.set('navContentPaneEnabled', 'false');
    u.searchParams.set('actionBarEnabled', 'false');
    return u.toString();
  } catch {
    return s;
  }
}

/** Parse "W:H" string into a padding-bottom percentage, clamped to sane bounds. */
function ratioToPadding(ratio) {
  if (!ratio || typeof ratio !== 'string') return null;
  const parts = ratio.split(':');
  if (parts.length !== 2) return null;
  const w = parseFloat(parts[0]);
  const h = parseFloat(parts[1]);
  if (!w || !h || w <= 0 || h <= 0) return null;
  const pct = (h / w) * 100;
  if (pct < 20 || pct > 200) return null;
  return pct;
}

const PBI_BOTTOM_BAR_PX = 36;

function isPowerBi(embedType) {
  const t = (embedType || '').toLowerCase();
  return t === 'powerbi' || t === 'iframe';
}

export default function EmbedSection({ embed, animationDelay = 0 }) {
  if (!embed) return null;

  const embedType = (embed.embed_type || 'powerbi').toLowerCase();
  let iframeSrc = embed.embed_url;
  if (embedType === 'tableau') {
    iframeSrc = buildTableauEmbedSrc(embed.embed_url);
  } else if (isPowerBi(embedType)) {
    iframeSrc = buildPowerBiEmbedSrc(embed.embed_url);
  }
  const urlSafe = isAllowedForType(iframeSrc, embedType);
  const ratioPct = ratioToPadding(embed.aspect_ratio);
  const clipPx = isPowerBi(embedType) ? PBI_BOTTOM_BAR_PX : 0;

  return (
    <motion.section
      className="mb-12 last:mb-0"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: animationDelay }}
    >
      <div className="bg-white rounded-xl shadow-md border border-humdb-gray-200 overflow-hidden">
        <div className="px-6 sm:px-8 py-5 border-b border-humdb-gray-200 bg-humdb-gray-50/80">
          <h2 className="text-xl sm:text-2xl font-bold text-humdb-navy">
            {embed.title}
          </h2>
          {embed.description && (
            <p className="text-sm text-humdb-gray-500 mt-1">{embed.description}</p>
          )}
        </div>
        <div className="w-full overflow-hidden">
          {urlSafe ? (
            ratioPct ? (
              <div
                className="relative w-full overflow-hidden"
                style={{ paddingBottom: `${ratioPct}%`, maxHeight: '85vh' }}
              >
                <iframe
                  src={iframeSrc}
                  title={embed.title}
                  className="absolute inset-0 w-full border-0"
                  style={{ height: `calc(100% + ${clipPx}px)` }}
                  referrerPolicy="no-referrer"
                  loading="lazy"
                  allowFullScreen
                />
              </div>
            ) : (
              <div
                className="relative w-full overflow-hidden"
                style={{ minHeight: '600px', height: '75vh' }}
              >
                <iframe
                  src={iframeSrc}
                  title={embed.title}
                  className="absolute inset-0 w-full border-0"
                  style={{ height: `calc(100% + ${clipPx}px)` }}
                  referrerPolicy="no-referrer"
                  loading="lazy"
                  allowFullScreen
                />
              </div>
            )
          ) : (
            <div className="px-6 sm:px-8 py-12 text-center text-humdb-gray-500">
              <p>This embed source is not available.</p>
            </div>
          )}
        </div>
      </div>
    </motion.section>
  );
}
