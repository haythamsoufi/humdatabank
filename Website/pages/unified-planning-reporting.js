// pages/unified-planning-reporting.js
// Unified Planning and Reporting (UPR). Data will be populated from UPR template ID (see lib/constants.js).

import Head from 'next/head';
import { useTranslation } from '../lib/useTranslation';
import { UPR_TEMPLATE_ID } from '../lib/constants';
import { motion } from 'framer-motion';

export default function UnifiedPlanningReportingPage() {
  const { t } = useTranslation();

  return (
    <>
      <Head>
        <title>Unified Planning and Reporting - NGO Databank</title>
        <meta name="description" content="Unified Planning and Reporting (UPR) data and dashboards." />
      </Head>

      <div className="min-h-screen bg-ngodb-gray-50">
        {/* Hero */}
        <section className="bg-gradient-to-br from-ngodb-navy to-ngodb-navy/90 text-white py-12 sm:py-16 px-4 sm:px-6 lg:px-12">
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
              Planning and reporting data in one place. Content will be populated from the UPR template.
            </motion.p>
          </div>
        </section>

        {/* Main content */}
        <div className="w-full px-4 sm:px-6 lg:px-12 py-10 lg:py-14 max-w-6xl mx-auto">
          <motion.section
            className="mb-12"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35 }}
          >
            <div className="bg-white rounded-xl shadow-md border border-ngodb-gray-200 overflow-hidden">
              <div className="px-6 sm:px-8 py-5 border-b border-ngodb-gray-200 bg-ngodb-gray-50/80">
                <h2 className="text-xl sm:text-2xl font-bold text-ngodb-navy">
                  UPR Data
                </h2>
                {UPR_TEMPLATE_ID != null && (
                  <p className="text-sm text-ngodb-gray-500 mt-1">
                    Template ID: {UPR_TEMPLATE_ID}
                  </p>
                )}
              </div>
              <div className="px-6 sm:px-8 py-6 text-ngodb-gray-700">
                <p className="mb-4">
                  Unified Planning and Reporting brings planning and reporting data into a single view. This section will display data from the UPR form template once the template ID is configured.
                </p>
                <div
                  className="min-h-[200px] rounded-lg bg-ngodb-gray-100 border border-dashed border-ngodb-gray-300 flex items-center justify-center text-ngodb-gray-500 text-sm"
                  data-template-id={UPR_TEMPLATE_ID}
                  data-section="upr"
                >
                  {UPR_TEMPLATE_ID == null
                    ? 'Data will appear here once UPR_TEMPLATE_ID is set in lib/constants.js.'
                    : 'Data for UPR will be loaded from the API using the configured template ID.'}
                </div>
              </div>
            </div>
          </motion.section>
        </div>
      </div>
    </>
  );
}
