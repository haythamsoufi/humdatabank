// pages/unified-planning-reporting.js
// Public UPR coverage. Figures stay in Backoffice; this page shows how many
// countries have a public value on the plan (template 24) and country reporting
// (template 33) templates.

import Head from 'next/head';
import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { getBackofficeApiUrl } from '../lib/apiService';
import { UPR_PLAN_TEMPLATE_ID, UPR_REPORT_TEMPLATE_ID } from '../lib/constants';

const PROGRAMMES = [
  {
    id: UPR_PLAN_TEMPLATE_ID,
    title: 'Unified Country Plan',
    description: 'Planning-country data (P* rounds).',
  },
  {
    id: UPR_REPORT_TEMPLATE_ID,
    title: 'Country reporting',
    description: 'National Society indicators, funding, and support (AR* and MYR* rounds).',
  },
];

async function loadCoverage(templateId) {
  const url = getBackofficeApiUrl('public/submissions/coverage', {
    template_id: String(templateId),
  });
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Coverage request failed (${response.status})`);
  }
  return response.json();
}

function CoverageCard({ programme, coverage, error, loading }) {
  const periods = Array.isArray(coverage?.by_period) ? coverage.by_period : [];
  return (
    <div className="bg-white rounded-xl shadow-md border border-humdb-gray-200 overflow-hidden">
      <div className="px-6 sm:px-8 py-5 border-b border-humdb-gray-200 bg-humdb-gray-50/80">
        <h2 className="text-xl sm:text-2xl font-bold text-humdb-navy">{programme.title}</h2>
        <p className="text-sm text-humdb-gray-500 mt-1">
          {programme.description} Template {programme.id}.
        </p>
      </div>
      <div className="px-6 sm:px-8 py-6 text-humdb-gray-700">
        {loading && <p className="text-sm text-humdb-gray-500">Loading public coverage…</p>}
        {error && (
          <p className="text-sm text-humdb-gray-600">
            Public coverage is not available right now. {error}
          </p>
        )}
        {!loading && !error && (
          <>
            <p className="text-3xl font-bold text-humdb-navy">
              {coverage?.countries_submitted_total ?? 0}
            </p>
            <p className="text-sm text-humdb-gray-500 mb-4">
              Countries with at least one public value
              {coverage?.truncated ? ' (count may be incomplete)' : ''}.
            </p>
            {periods.length === 0 ? (
              <p className="text-sm text-humdb-gray-500">No public reporting periods yet.</p>
            ) : (
              <ul className="divide-y divide-humdb-gray-100 border border-humdb-gray-200 rounded-lg">
                {periods.map((period) => (
                  <li
                    key={period.period_name}
                    className="flex items-center justify-between px-4 py-3 text-sm"
                  >
                    <span className="font-medium text-humdb-navy">{period.period_name}</span>
                    <span className="text-humdb-gray-600">
                      {period.countries_submitted} countries
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default function UnifiedPlanningReportingPage() {
  const [coverageByTemplate, setCoverageByTemplate] = useState({});
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const nextCoverage = {};
      const nextErrors = {};
      await Promise.all(PROGRAMMES.map(async (programme) => {
        try {
          nextCoverage[programme.id] = await loadCoverage(programme.id);
        } catch (error) {
          nextErrors[programme.id] = error.message || 'Request failed';
        }
      }));
      if (!cancelled) {
        setCoverageByTemplate(nextCoverage);
        setErrors(nextErrors);
        setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <>
      <Head>
        <title>Unified Planning and Reporting - Humanitarian Databank</title>
        <meta
          name="description"
          content="Public coverage of Unified Planning and Reporting plan and country-reporting templates."
        />
      </Head>

      <div className="min-h-screen bg-humdb-gray-50">
        <section className="bg-gradient-to-br from-humdb-navy to-humdb-navy/90 text-white py-12 sm:py-16 px-4 sm:px-6 lg:px-12">
          <div className="max-w-4xl mx-auto text-center">
            <motion.h1
              className="text-3xl sm:text-4xl lg:text-5xl font-bold mb-4"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4 }}
            >
              Unified Planning and Reporting
            </motion.h1>
            <motion.p
              className="text-lg sm:text-xl text-white/90 max-w-2xl mx-auto"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.1 }}
            >
              How many countries have published a public value on the current UPR plan and reporting templates.
            </motion.p>
          </div>
        </section>

        <div className="w-full px-4 sm:px-6 lg:px-12 py-10 lg:py-14 max-w-6xl mx-auto">
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            {PROGRAMMES.map((programme) => (
              <CoverageCard
                key={programme.id}
                programme={programme}
                coverage={coverageByTemplate[programme.id]}
                error={errors[programme.id]}
                loading={loading}
              />
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
