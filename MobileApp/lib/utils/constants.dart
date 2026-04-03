import '../services/organization_config_service.dart';

class AppConstants {
  // Organization Brand Colors (dynamic, loaded from config)
  // These are fallback values if config is not loaded
  static const int defaultNavy = 0xFF011E41;
  static const int defaultRed = 0xFFC8102E;
  static const int defaultDarkRed = 0xFFA50D25;

  // Legacy constants for backward compatibility
  // These now use dynamic values from organization config
  static int get ifrcNavy {
    try {
      if (OrganizationConfigService().isInitialized) {
        return OrganizationConfigService().config.branding.navyColorInt;
      }
    } catch (e) {
      // Fallback if config not loaded
    }
    return defaultNavy;
  }

  static int get ifrcRed {
    try {
      if (OrganizationConfigService().isInitialized) {
        return OrganizationConfigService().config.branding.redColorInt;
      }
    } catch (e) {
      // Fallback if config not loaded
    }
    return defaultRed;
  }

  static int get ifrcDarkRed {
    try {
      if (OrganizationConfigService().isInitialized) {
        return OrganizationConfigService().config.branding.darkRedColorInt;
      }
    } catch (e) {
      // Fallback if config not loaded
    }
    return defaultDarkRed;
  }

  // Organization-aware color getters (recommended for new code)
  static int get organizationNavy => ifrcNavy;
  static int get organizationRed => ifrcRed;
  static int get organizationDarkRed => ifrcDarkRed;

  // UI Colors
  static const int backgroundColor = 0xFFFFFFFF;
  static const int textColor = 0xFF111827;
  static const int textSecondary = 0xFF6B7280;
  static const int borderColor = 0xFFE5E7EB;
  static const int errorColor = 0xFFDC2626;
  static const int successColor = 0xFF16A34A;
  static const int warningColor = 0xFFF59E0B;

  // Spacing
  static const double paddingSmall = 8.0;
  static const double paddingMedium = 16.0;
  static const double paddingLarge = 24.0;
  static const double paddingXLarge = 32.0;

  // Border Radius
  static const double radiusSmall = 4.0;
  static const double radiusMedium = 8.0;
  static const double radiusLarge = 12.0;

  // Animation Durations
  static const Duration animationFast = Duration(milliseconds: 200);
  static const Duration animationMedium = Duration(milliseconds: 300);
  static const Duration animationSlow = Duration(milliseconds: 500);
}
