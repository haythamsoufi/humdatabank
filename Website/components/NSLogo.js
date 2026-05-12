// components/NSLogo.js
import React from 'react';
import { useScope } from './scope/ScopeContext';

/**
 * National Society Logo Component
 * Displays a generic Red Cross/Crescent emblem when a country is selected in demo mode.
 * Falls back to the default organization logo when in global scope or non-demo mode.
 */
export default function NSLogo({ className = '', alt = '', size = 'default' }) {
  const { scope, countryIso2, isDemoMode, nationalSocietyName } = useScope();
  const isNationalScope = scope?.type === 'country' && !!countryIso2;

  // Show NS logo only in demo mode with country scope
  const showNSLogo = isDemoMode && isNationalScope && nationalSocietyName;

  // Size classes
  const sizeClasses = {
    small: 'h-8 w-8',
    default: 'h-10 w-10',
    medium: 'h-12 w-12',
    large: 'h-16 w-16'
  };

  const heightClass = sizeClasses[size] || sizeClasses.default;

  if (!showNSLogo) {
    // Fallback to default org logo asset
    return (
      <img
        src="/ifrc_logo_white.svg"
        alt={alt || "Organization logo"}
        className={`${heightClass} w-auto flex-shrink-0 ${className}`}
        onError={(e) => e.target.style.display='none'}
      />
    );
  }

  // Render National Society logo - simple placeholder design
  return (
    <img
      src="/ns_logo_placeholder.svg"
      alt={alt || `${nationalSocietyName} Logo`}
      className={`${heightClass} w-auto flex-shrink-0 ${className}`}
      onError={(e) => e.target.style.display='none'}
    />
  );
}
