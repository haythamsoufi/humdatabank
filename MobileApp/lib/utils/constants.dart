import '../services/organization_config_service.dart';
import 'app_spacing.dart';

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
  static const int semanticSuccessOnDarkSoft = 0xFF86EFAC;
  static const int semanticSuccessOnLightStrong = 0xFF15803D;
  static const int warningColor = 0xFFF59E0B;

  /// Blended with organization [ifrcNavy] for dark theme [ColorScheme.primary].
  /// Raw navy (~#011E41) on charcoal fails contrast; this light blue anchor keeps
  /// buttons, focus rings, and switches readable while staying hue-aligned.
  static const int themeDarkPrimaryBlend = 0xFFB8D4FF;

  /// Shared Material theme tokens (light/dark shells, inputs, accents).
  /// Keep in sync with `AppTheme` (`theme.dart`), `AppShellTokens`, and `ThemeColors`.
  static const int themeScaffoldLight = 0xFFF2F2F7;
  static const int themeScaffoldDark = 0xFF121212;
  static const int themeSurfaceDark = 0xFF1E1E1E;
  static const int themeElevatedSurfaceDark = 0xFF2C2C2C;
  static const int themeSurfaceContainerLowestDark = 0xFF0D0D0D;
  static const int themeSurfaceContainerLowDark = 0xFF141414;
  static const int themeSurfaceContainerHighDark = 0xFF252525;
  static const int themePrimaryContainerDark = 0xFF363636;
  static const int themeOnContainerDark = 0xFFE8E8E8;
  static const int themeInputFillLight = 0xFFFAFAFA;
  static const int themeInputBorderLight = 0xFFDBDBDB;
  static const int themeInputBorderFocusedLight = 0xFF8E8E8E;
  static const int themeInputLabelLight = 0xFF8E8E8E;
  static const int themeSwitchCheckboxActiveDark = 0xFF4A90E2;

  /// Centralized feature accents (avoid scattering raw hex in screens/widgets).
  static const int semanticAdminHubBlue = 0xFF3B82F6;
  static const int semanticAdminHubPurple = 0xFF8B5CF6;
  static const int semanticAdminHubAmber = 0xFFF59E0B;
  static const int semanticAdminHubRed = 0xFFEF4444;
  static const int semanticAdminHubCyan = 0xFF06B6D4;

  /// Subtle muted text on cards (slate-500); paired with [textSecondary].
  static const int semanticSubtleText = 0xFF64748B;

  /// Leaderboard podium / medal colours (universal).
  static const int semanticPodiumGold = 0xFFFFD700;
  static const int semanticPodiumSilver = 0xFFC0C0C0;
  static const int semanticPodiumBronze = 0xFFCD7F32;

  /// Avatar / ranking accent palette used in leaderboard and profile chips.
  static const List<int> semanticAvatarPalette = [
    0xFF6366F1,
    0xFF8B5CF6,
    0xFF06B6D4,
    0xFF10B981,
    0xFFF59E0B,
    0xFFEF4444,
    0xFFEC4899,
    0xFF3B82F6,
    0xFF14B8A6,
    0xFFF97316,
  ];

  /// Resource / planning category gradient stops (start, end pairs).
  static const int semanticCategoryBlueStart = 0xFF0D47A1;
  static const int semanticCategoryBlueEnd = 0xFF1976D2;
  static const int semanticCategoryGreenStart = 0xFF1B5E20;
  static const int semanticCategoryGreenEnd = 0xFF388E3C;
  static const int semanticCategoryOrangeStart = 0xFFE65100;
  static const int semanticCategoryOrangeEnd = 0xFFFF6D00;
  static const int semanticCategoryPurpleStart = 0xFF4A148C;
  static const int semanticCategoryPurpleEnd = 0xFF7B1FA2;
  static const int semanticCategoryOrangeFallbackText = 0xFFBF360C;

  /// Shimmer / skeleton placeholder colours (light + dark).
  static const int semanticShimmerBaseLight = 0xFFE5E5EA;
  static const int semanticShimmerHighlightLight = 0xFFF2F2F7;
  static const int semanticShimmerBaseDark = 0xFF2C2C2E;
  static const int semanticShimmerHighlightDark = 0xFF3A3A3C;

  /// Snackbar background on light theme (slate-800).
  static const int themeSnackBarLight = 0xFF1F2937;
  static const int semanticNotificationOrange = 0xFFFF6B35;
  static const int semanticNotificationOrangeDarkUnread = 0xFFFFB366;
  static const int semanticNotificationOrangeDarkRead = 0xFFFFCC80;
  static const int semanticNotificationOrangeTextStrongLight = 0xFFC2410C;
  static const int semanticNotificationOrangeTextMutedLight = 0xFFEA580C;
  static const int semanticNotificationSky = 0xFF0369A1;
  static const int semanticNotificationSkyLight = 0xFF7DD3FC;
  static const int semanticNotificationUnreadRoseWash = 0xFFFFF5F5;
  static const int semanticNotificationUnreadBlueWash = 0xFFF0F8FF;
  static const int semanticEntityChipLightWash = 0xFFF0F9FF;
  static const int semanticDefaultProfileAccent = 0xFF3B82F6;

  /// Public source repo (matches Backoffice admin sidebar “Powered by” link).
  static const String humdatabankGithubRepoUrl =
      'https://github.com/haythamsoufi/humdatabank';

  // Spacing — aliases to [AppSpacing]. Prefer [AppSpacing] or [IOSSpacing] directly.
  @Deprecated('Use AppSpacing.sm or IOSSpacing.sm instead')
  static const double paddingSmall = AppSpacing.sm;
  @Deprecated('Use AppSpacing.md or IOSSpacing.md instead')
  static const double paddingMedium = AppSpacing.md;
  @Deprecated('Use AppSpacing.xl or IOSSpacing.xl instead')
  static const double paddingLarge = AppSpacing.xl;
  @Deprecated('Use AppSpacing.xxl or IOSSpacing.xxl instead')
  static const double paddingXLarge = AppSpacing.xxl;

  // Border Radius — prefer [IOSDimensions] for new widgets.
  static const double radiusSmall = 4.0;
  static const double radiusMedium = 8.0;
  static const double radiusLarge = 12.0;
  static const double radiusXLarge = 20.0;

  // Animation Durations
  static const Duration animationFast = Duration(milliseconds: 200);
  static const Duration animationMedium = Duration(milliseconds: 300);
  static const Duration animationSlow = Duration(milliseconds: 500);
}
