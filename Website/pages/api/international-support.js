// pages/api/international-support.js
//
// Temporary demo endpoint for International view support flows.
// IMPORTANT: This should eventually be fetched/proxied from Backoffice (Website shouldn't take flow data from env).
//
// This endpoint simulates a backend API response by serving data from:
// - Website/data/international_dummy.json
//
// Response shape (simulates backend API):
// {
//   supportMap: { [iso2: string]: string[] },
//   flows: { [year: string]: Array<{ from: string, to: string, value?: number }> },
//   indicators: {
//     [indicatorKey: string]: {
//       unit: string,  // e.g., "USD", "EUR", "People", "Services"
//       name?: string,
//       data: {
//         [year: string]: {
//           [iso2: string]: { value: number, name?: string }
//         }
//       }
//     }
//   }
// }

import internationalDummy from '../../data/international_dummy.json';

export default function handler(req, res) {
  const isDemo = process.env.NEXT_PUBLIC_DEMO_MODE === 'true';
  const isProd = process.env.NODE_ENV === 'production';

  // Only serve dummy data in demo/dev; avoid showing fake data in real prod deployments.
  if (isProd && !isDemo) {
    res.status(204).end();
    return;
  }

  res.setHeader('Cache-Control', 'public, max-age=60, s-maxage=300');
  res.status(200).json(internationalDummy);
}
