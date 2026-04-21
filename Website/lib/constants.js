/**
 * Centralized template IDs for form templates.
 * FDRS = Federation-wide Data Reporting System (default template for Website data).
 */
export const FDRS_TEMPLATE_ID = 21;

/**
 * Global Initiative section template IDs (set when backend templates are available).
 * - ECHO Programmatic Partnership
 * - Global Route-based Migration Programme
 * - Professional health services mapping project
 */
export const GLOBAL_INITIATIVE_TEMPLATE_IDS = {
  ECHO_PROGRAMMATIC_PARTNERSHIP: null,
  GLOBAL_ROUTE_BASED_MIGRATION: null,
  PROFESSIONAL_HEALTH_SERVICES_MAPPING: null
};

/**
 * Unified Planning and Reporting (UPR) template ID (set when backend template is available).
 */
export const UPR_TEMPLATE_ID = null;

/**
 * Indicator bank IDs for the global overview map (FDRS template).
 * Keys match frontend indicator keys; ids must match Backoffice indicator bank.
 * To verify/update: Backoffice Admin → System Admin → Indicator Bank, or GET /api/v1/indicator-bank (with API key).
 */
export const KEY_INDICATOR_BANK_IDS = {
  volunteers: 724,
  staff: 727,
  branches: 1117,
  'local-units': 723,
  'blood-donors': 626,
  'first-aid': 625,
  'people-reached': 729,
  income: 733,
  expenditure: 734
};

/** Display units for key indicators (used with KEY_INDICATOR_BANK_IDS). */
export const KEY_INDICATOR_UNITS = {
  volunteers: 'Volunteers',
  staff: 'Staff',
  branches: 'Branches',
  'local-units': 'Units',
  'blood-donors': 'People',
  'first-aid': 'People',
  'people-reached': 'People',
  income: 'CHF',
  expenditure: 'CHF'
};
