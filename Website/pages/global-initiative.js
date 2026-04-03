// pages/global-initiative.js
// Global Initiative: ECHO, Migration, Professional health services mapping.
// Each section lives in its own component under components/global-initiative/.

import Head from 'next/head';
import { motion } from 'framer-motion';
import EchoProgrammaticPartnershipSection from '../components/global-initiative/EchoProgrammaticPartnershipSection';
import GlobalRouteBasedMigrationSection from '../components/global-initiative/GlobalRouteBasedMigrationSection';
import ProfessionalHealthServicesMappingSection from '../components/global-initiative/ProfessionalHealthServicesMappingSection';

export default function GlobalInitiativePage() {
  return (
    <>
      <Head>
        <title>Global Initiatives - NGO Databank</title>
        <meta name="description" content="Global Initiatives: ECHO Programmatic Partnership, Global Route-based Migration Programme, Professional health services mapping." />
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
              Global Initiatives
            </motion.h1>
            <motion.p
              className="text-lg sm:text-xl text-white/90 max-w-2xl mx-auto"
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.4, delay: 0.1 }}
            >
              Programme and partnership data across ECHO Programmatic Partnership, Global Route-based Migration, and Professional health services mapping.
            </motion.p>
          </div>
        </section>

        {/* Sections (each in its own file) */}
        <div className="w-full px-4 sm:px-6 lg:px-12 py-10 lg:py-14 max-w-6xl mx-auto">
          <EchoProgrammaticPartnershipSection animationDelay={0} />
          <GlobalRouteBasedMigrationSection animationDelay={0.08} />
          <ProfessionalHealthServicesMappingSection animationDelay={0.16} />
        </div>
      </div>
    </>
  );
}
