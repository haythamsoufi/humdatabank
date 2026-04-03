// components/global-initiative/GlobalRouteBasedMigrationSection.js
// Data for this section uses GLOBAL_INITIATIVE_TEMPLATE_IDS.GLOBAL_ROUTE_BASED_MIGRATION (lib/constants.js).

import { motion } from 'framer-motion';
import { GLOBAL_INITIATIVE_TEMPLATE_IDS } from '../../lib/constants';

const TEMPLATE_ID = GLOBAL_INITIATIVE_TEMPLATE_IDS.GLOBAL_ROUTE_BASED_MIGRATION;
const SECTION_KEY = 'GLOBAL_ROUTE_BASED_MIGRATION';

export default function GlobalRouteBasedMigrationSection({ animationDelay = 0 } = {}) {
  return (
    <motion.section
      className="mb-12 last:mb-0"
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: animationDelay }}
    >
      <div className="bg-white rounded-xl shadow-md border border-ngodb-gray-200 overflow-hidden">
        <div className="px-6 sm:px-8 py-5 border-b border-ngodb-gray-200 bg-ngodb-gray-50/80">
          <h2 className="text-xl sm:text-2xl font-bold text-ngodb-navy">
            Global Route-based Migration Programme
          </h2>
          {TEMPLATE_ID != null && (
            <p className="text-sm text-ngodb-gray-500 mt-1">
              Template ID: {TEMPLATE_ID}
            </p>
          )}
        </div>
        <div className="px-6 sm:px-8 py-6 text-ngodb-gray-700">
          <p className="mb-4">
            Data for the Global Route-based Migration Programme. Content will be populated from template data.
          </p>
          <div
            className="min-h-[120px] rounded-lg bg-ngodb-gray-100 border border-dashed border-ngodb-gray-300 flex items-center justify-center text-ngodb-gray-500 text-sm"
            data-template-id={TEMPLATE_ID}
            data-section-key={SECTION_KEY}
          >
            {TEMPLATE_ID == null
              ? 'Data will appear here once a template ID is set in lib/constants.js (GLOBAL_INITIATIVE_TEMPLATE_IDS.GLOBAL_ROUTE_BASED_MIGRATION).'
              : 'Data for this section will be loaded from the API using the configured template ID.'}
          </div>
        </div>
      </div>
    </motion.section>
  );
}
