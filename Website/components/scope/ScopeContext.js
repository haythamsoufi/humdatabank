// components/scope/ScopeContext.js
import React, { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { DEMO_MODE, getAllowedScopeTypes, getEffectiveScope, getScopeLabel } from '../../lib/scopeConfig';
import { getCountriesList } from '../../lib/apiService';

const STORAGE_KEY = 'ifrc_databank_scope_v2';

const ScopeContext = createContext({
  scope: { type: 'global', countryIso2: null },
  setScope: () => {},
  isDemoMode: false,
  allowedScopeTypes: ['global'],
  countryIso2: null,
  countryIso3: null,
  label: 'Global',
});

export function ScopeProvider({ children }) {
  const allowedScopeTypes = useMemo(() => getAllowedScopeTypes(), []);

  // Start from the effective (env) scope; if DEMO_MODE, we'll upgrade from localStorage after hydration.
  const [scope, setScopeState] = useState(() => getEffectiveScope(null));
  const [countryName, setCountryName] = useState(null);
  const [nationalSocietyName, setNationalSocietyName] = useState(null);
  const [countryIso3, setCountryIso3] = useState(null);

  useEffect(() => {
    if (!DEMO_MODE) return;
    try {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored) {
        // stored is either "global" or ISO2 like "SY"
        const next = getEffectiveScope(stored);
        setScopeState(next);
      }
    } catch (_e) {
      // ignore
    }
  }, []);

  // For non-demo deployments (no banner), resolve ISO3/name for the configured country scope.
  useEffect(() => {
    const effective = getEffectiveScope(scope);
    if (effective.type !== 'country' || !effective.countryIso2) return;
    if (countryIso3 && countryName) return;

    let mounted = true;
    const resolve = async () => {
      try {
        const list = await getCountriesList();
        if (!mounted) return;
        const match = (list || []).find((c) => String(c?.iso2 || '').toUpperCase() === String(effective.countryIso2).toUpperCase());
        if (match) {
          setCountryIso3(match.iso3 ? String(match.iso3).toUpperCase() : null);
          if (!countryName) setCountryName(match.name || null);
          if (!nationalSocietyName) setNationalSocietyName(match.national_society_name || null);
        }
      } catch (_e) {
        // ignore
      }
    };
    resolve();
    return () => {
      mounted = false;
    };
  }, [scope, countryIso3, countryName, nationalSocietyName]);

  const setScope = (next) => {
    if (!DEMO_MODE) return; // locked in non-demo deployments
    const normalized = getEffectiveScope(next);
    setScopeState(normalized);
    try {
      window.localStorage.setItem(STORAGE_KEY, normalized.type === 'country' ? normalized.countryIso2 : 'global');
    } catch (_e) {
      // ignore
    }
  };

  const value = useMemo(() => {
    const effective = getEffectiveScope(scope);
    return {
      scope: effective,
      setScope,
      isDemoMode: DEMO_MODE,
      allowedScopeTypes,
      countryIso2: effective.type === 'country' ? effective.countryIso2 : null,
      countryIso3,
      countryName,
      nationalSocietyName,
      setCountryName,
      setNationalSocietyName,
      setCountryIso3,
      label: getScopeLabel(effective, countryName, nationalSocietyName),
    };
  }, [scope, allowedScopeTypes, countryIso3, countryName, nationalSocietyName]);

  return <ScopeContext.Provider value={value}>{children}</ScopeContext.Provider>;
}

export function useScope() {
  return useContext(ScopeContext);
}
