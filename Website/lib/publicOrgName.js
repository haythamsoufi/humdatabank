/**
 * Public-site organization name.
 *
 * Set NEXT_PUBLIC_ORGANIZATION_NAME in .env.local to match Backoffice
 * Settings → Organization branding (deploy-time sync). When unset, callers
 * should pass the i18n default (e.g. navigation.siteTitle).
 */
export function getPublicOrganizationName(i18nFallback = 'NGO Databank') {
  if (typeof process === 'undefined' || !process.env) {
    return i18nFallback;
  }
  const fromEnv = (process.env.NEXT_PUBLIC_ORGANIZATION_NAME || '').trim();
  return fromEnv || i18nFallback;
}
