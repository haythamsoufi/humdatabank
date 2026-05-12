// pages/global-initiative.js
// Global Initiatives: renders Power BI embeds managed from the backoffice.
// Falls back to static placeholder sections when no embeds are available.

import { useState, useEffect } from 'react';
import Head from 'next/head';
import { motion } from 'framer-motion';
import EmbedSection from '../components/global-initiative/EmbedSection';
import EchoProgrammaticPartnershipSection from '../components/global-initiative/EchoProgrammaticPartnershipSection';
import GlobalRouteBasedMigrationSection from '../components/global-initiative/GlobalRouteBasedMigrationSection';
import ProfessionalHealthServicesMappingSection from '../components/global-initiative/ProfessionalHealthServicesMappingSection';

const PAGE_SLOTS = [
  { slot: 'echo_partnership', Fallback: EchoProgrammaticPartnershipSection },
  { slot: 'grbm', Fallback: GlobalRouteBasedMigrationSection },
  { slot: 'phsm', Fallback: ProfessionalHealthServicesMappingSection },
];

export default function GlobalInitiativePage({ initialEmbeds }) {
  const [embeds, setEmbeds] = useState(initialEmbeds || []);

  useEffect(() => {
    let cancelled = false;
    async function refresh() {
      try {
        const res = await fetch('/api/embed-content?category=global_initiative');
        if (res.ok) {
          const data = await res.json();
          if (!cancelled && data.embeds?.length) {
            setEmbeds(data.embeds);
          }
        }
      } catch (_e) {
        // keep existing data
      }
    }
    refresh();
    return () => { cancelled = true; };
  }, []);

  const slotMap = {};
  const extras = [];
  for (const embed of embeds) {
    if (embed.page_slot && PAGE_SLOTS.some((s) => s.slot === embed.page_slot)) {
      slotMap[embed.page_slot] = embed;
    } else {
      extras.push(embed);
    }
  }

  return (
    <>
      <Head>
        <title>Global Initiatives - Humanitarian Databank</title>
        <meta name="description" content="Global Initiatives: ECHO Programmatic Partnership, Global Route-based Migration Programme, Professional health services mapping." />
      </Head>

      <div className="min-h-screen bg-humdb-gray-50">
        {/* Hero */}
        <section className="bg-gradient-to-br from-humdb-navy to-humdb-navy/90 text-white py-12 sm:py-16 px-4 sm:px-6 lg:px-12">
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

        {/* Embed Sections — fixed slot order */}
        <div className="w-full px-4 sm:px-6 lg:px-12 py-10 lg:py-14 max-w-6xl mx-auto">
          {PAGE_SLOTS.map(({ slot, Fallback }, idx) => {
            const embed = slotMap[slot];
            return embed ? (
              <EmbedSection key={embed.id} embed={embed} animationDelay={idx * 0.08} />
            ) : (
              <Fallback key={slot} animationDelay={idx * 0.08} />
            );
          })}

          {extras.map((embed, idx) => (
            <EmbedSection
              key={embed.id}
              embed={embed}
              animationDelay={(PAGE_SLOTS.length + idx) * 0.08}
            />
          ))}
        </div>
      </div>
    </>
  );
}

export async function getServerSideProps() {
  let initialEmbeds = [];
  try {
    const backofficeUrl = (
      process.env.NEXT_INTERNAL_API_URL ||
      process.env.INTERNAL_API_URL ||
      process.env.NEXT_PUBLIC_API_URL ||
      'http://localhost:5000'
    ).replace(/\/$/, '');
    const apiKey = (process.env.NEXT_PUBLIC_API_KEY || 'databank2026')
      .replace(/^Bearer\s+/i, '')
      .trim();

    const res = await fetch(
      `${backofficeUrl}/api/v1/embed-content?category=global_initiative`,
      {
        headers: {
          Accept: 'application/json',
          ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}),
        },
        signal: AbortSignal.timeout(10000),
      }
    );
    if (res.ok) {
      const data = await res.json();
      initialEmbeds = data?.embeds || [];
    }
  } catch (e) {
    console.warn('[global-initiative] SSR fetch failed, will rely on client cache:', e?.message);
  }
  return { props: { initialEmbeds } };
}
