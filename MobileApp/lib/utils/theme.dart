import 'package:flutter/material.dart';

import 'arabic_text_font.dart';
import '../theme/app_shell_tokens.dart';
import 'app_spacing.dart';
import 'constants.dart';

class AppTheme {
  static ThemeData lightTheme({
    Locale? locale,
    ArabicTextFontPreference arabicTextFont = ArabicTextFontPreference.tajawal,
  }) =>
      _buildTheme(Brightness.light, locale, arabicTextFont);

  static ThemeData darkTheme({
    Locale? locale,
    ArabicTextFontPreference arabicTextFont = ArabicTextFontPreference.tajawal,
  }) =>
      _buildTheme(Brightness.dark, locale, arabicTextFont);

  /// [ColorScheme.fromSeed] derives **chromatic** surface roles from the seed.
  /// With IFRC navy as seed, dark mode's `surfaceContainer*` and `primaryContainer`
  /// become blue-tinted grays across Material 3 widgets. We keep brand [primary] /
  /// [secondary] but replace those **surface** roles with a neutral ramp aligned to
  /// [AppConstants] dark shells (no blue cast).
  static ColorScheme _darkNeutralColorScheme(ColorScheme seeded) {
    const surfaceDark = Color(AppConstants.themeSurfaceDark);
    const elevated = Color(AppConstants.themeElevatedSurfaceDark);
    return seeded.copyWith(
      surfaceContainerLowest: const Color(AppConstants.themeSurfaceContainerLowestDark),
      surfaceContainerLow: const Color(AppConstants.themeSurfaceContainerLowDark),
      surfaceContainer: surfaceDark,
      surfaceContainerHigh: const Color(AppConstants.themeSurfaceContainerHighDark),
      surfaceContainerHighest: elevated,
      primaryContainer: const Color(AppConstants.themePrimaryContainerDark),
      onPrimaryContainer: const Color(AppConstants.themeOnContainerDark),
      tertiaryContainer: Color.alphaBlend(
        Colors.white.withValues(alpha: 0.12),
        elevated,
      ),
      onTertiaryContainer: const Color(AppConstants.themeOnContainerDark),
      outline: Colors.white.withValues(alpha: 0.22),
      outlineVariant: Colors.white.withValues(alpha: 0.14),
    );
  }

  static ThemeData _buildTheme(
    Brightness brightness,
    Locale? locale,
    ArabicTextFontPreference arabicTextFont,
  ) {
    final isDark = brightness == Brightness.dark;
    final String? fontFamily = _resolveFontFamily(locale, arabicTextFont);

    TextStyle getTextStyle({
      required double fontSize,
      required FontWeight fontWeight,
      required Color color,
      double? letterSpacing,
      double? height,
    }) {
      return TextStyle(
        fontFamily: fontFamily,
        fontSize: fontSize,
        fontWeight: fontWeight,
        color: color,
        letterSpacing: letterSpacing,
        height: height,
      );
    }

    final brandNavy = Color(AppConstants.ifrcNavy);
    // Dark mode: brand navy is nearly black — unusable as Material primary on greys.
    final primary = isDark
        ? Color.lerp(
            brandNavy,
            const Color(AppConstants.themeDarkPrimaryBlend),
            0.58,
          )!
        : brandNavy;
    final secondary = Color(AppConstants.ifrcRed);
    final colorSchemeBase = ColorScheme.fromSeed(
      seedColor: primary,
      primary: primary,
      secondary: secondary,
      error: const Color(AppConstants.errorColor),
      surface: isDark
          ? const Color(AppConstants.themeSurfaceDark)
          : const Color(AppConstants.backgroundColor),
      onPrimary: Colors.white,
      onSecondary: Colors.white,
      onSurface: isDark
          ? Colors.white
          : const Color(AppConstants.textColor),
      brightness: brightness,
    );
    final colorScheme =
        isDark ? _darkNeutralColorScheme(colorSchemeBase) : colorSchemeBase;

    final textPrimary =
        isDark ? Colors.white : const Color(AppConstants.textColor);
    final bodySmallColor = isDark
        ? Colors.white.withValues(alpha: 0.7)
        : const Color(AppConstants.textSecondary);
    final bodyMediumColor =
        isDark ? Colors.white.withValues(alpha: 0.9) : textPrimary;

    final inputRadius = BorderRadius.circular(AppConstants.radiusMedium);

    final shellTokens = AppShellTokens.fromBridge(
      isDark: isDark,
      colorScheme: colorScheme,
      navy: Color(AppConstants.ifrcNavy),
    );

    return ThemeData(
      useMaterial3: true,
      extensions: <ThemeExtension<dynamic>>[shellTokens],
      visualDensity: VisualDensity.adaptivePlatformDensity,
      materialTapTargetSize: MaterialTapTargetSize.padded,
      // Subtle page motion (keeps iOS cupertino-style push; others get a soft fade-up).
      pageTransitionsTheme: const PageTransitionsTheme(
        builders: <TargetPlatform, PageTransitionsBuilder>{
          TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
          TargetPlatform.macOS: CupertinoPageTransitionsBuilder(),
          TargetPlatform.android: FadeUpwardsPageTransitionsBuilder(),
          TargetPlatform.fuchsia: FadeUpwardsPageTransitionsBuilder(),
          TargetPlatform.linux: FadeUpwardsPageTransitionsBuilder(),
          TargetPlatform.windows: FadeUpwardsPageTransitionsBuilder(),
        },
      ),
      splashFactory: InkSparkle.splashFactory,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: isDark
          ? const Color(AppConstants.themeScaffoldDark)
          : const Color(AppConstants.themeScaffoldLight),
      appBarTheme: AppBarTheme(
        backgroundColor: isDark
            ? const Color(AppConstants.themeSurfaceDark)
            : Colors.white,
        foregroundColor: isDark ? Colors.white : Colors.black,
        elevation: 0,
        centerTitle: false,
        surfaceTintColor: Colors.transparent,
        titleTextStyle: getTextStyle(
          fontSize: 20,
          fontWeight: FontWeight.w600,
          color: isDark ? Colors.white : Colors.black,
          letterSpacing: -0.5,
        ),
        iconTheme: IconThemeData(color: isDark ? Colors.white : Colors.black),
        shadowColor: Colors.black.withValues(alpha: isDark ? 0.3 : 0.1),
        scrolledUnderElevation: 1,
      ),
      // Full Material 3 text roles; [main.dart] applies [LayoutScale] via fontSizeFactor.
      // [IOSTextStyle] delegates here so Montserrat / Tajawal / system Arabic and scaling stay single-pipeline.
      textTheme: TextTheme(
        displayLarge: getTextStyle(
          fontSize: 32,
          fontWeight: FontWeight.bold,
          color: textPrimary,
          letterSpacing: -1,
        ),
        displayMedium: getTextStyle(
          fontSize: 28,
          fontWeight: FontWeight.bold,
          color: textPrimary,
          letterSpacing: -0.5,
        ),
        displaySmall: getTextStyle(
          fontSize: 24,
          fontWeight: FontWeight.w600,
          color: textPrimary,
          letterSpacing: -0.5,
        ),
        headlineLarge: getTextStyle(
          fontSize: 32,
          fontWeight: FontWeight.w400,
          color: textPrimary,
          letterSpacing: -0.5,
        ),
        headlineMedium: getTextStyle(
          fontSize: 20,
          fontWeight: FontWeight.w600,
          color: textPrimary,
          letterSpacing: -0.3,
        ),
        headlineSmall: getTextStyle(
          fontSize: 22,
          fontWeight: FontWeight.w600,
          color: textPrimary,
          letterSpacing: -0.35,
        ),
        titleLarge: getTextStyle(
          fontSize: 18,
          fontWeight: FontWeight.w600,
          color: textPrimary,
        ),
        titleMedium: getTextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w600,
          color: textPrimary,
        ),
        titleSmall: getTextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w600,
          color: textPrimary,
        ),
        bodyLarge: getTextStyle(
          fontSize: 16,
          fontWeight: FontWeight.normal,
          color: textPrimary,
          height: 1.5,
        ),
        bodyMedium: getTextStyle(
          fontSize: 14,
          fontWeight: FontWeight.normal,
          color: bodyMediumColor,
          height: 1.5,
        ),
        bodySmall: getTextStyle(
          fontSize: 12,
          fontWeight: FontWeight.normal,
          color: bodySmallColor,
          height: 1.4,
        ),
        labelLarge: getTextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w600,
          color: textPrimary,
        ),
        labelMedium: getTextStyle(
          fontSize: 13,
          fontWeight: FontWeight.w500,
          color: bodyMediumColor,
        ),
        labelSmall: getTextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w500,
          color: bodySmallColor,
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: primary,
          foregroundColor: Colors.white,
          elevation: 0,
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.xl,
            vertical: AppSpacing.md + 2,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
          ),
          textStyle: getTextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
            color: Colors.white,
            letterSpacing: 0.2,
          ),
        ).copyWith(
          elevation: WidgetStateProperty.resolveWith<double>(
            (Set<WidgetState> states) {
              if (states.contains(WidgetState.disabled)) return 0;
              if (states.contains(WidgetState.pressed)) return 2;
              return 1;
            },
          ),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: primary,
          foregroundColor: colorScheme.onPrimary,
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.xl,
            vertical: AppSpacing.md + 2,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppConstants.radiusMedium),
          ),
          elevation: 0,
          textStyle: getTextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w600,
            color: Colors.white,
            letterSpacing: 0.2,
          ),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: isDark
              ? Colors.white.withValues(alpha: 0.9)
              : primary,
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.xl,
            vertical: AppSpacing.md + 2,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
          ),
          side: BorderSide(
            color: isDark ? Colors.white.withValues(alpha: 0.5) : primary,
            width: 1.5,
          ),
          textStyle: getTextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
            color: isDark ? Colors.white.withValues(alpha: 0.9) : primary,
            letterSpacing: 0.2,
          ),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: isDark
            ? const Color(AppConstants.themeElevatedSurfaceDark)
            : const Color(AppConstants.themeInputFillLight),
        border: OutlineInputBorder(
          borderRadius: inputRadius,
          borderSide: BorderSide(
            color: isDark
                ? Colors.white.withValues(alpha: 0.12)
                : const Color(AppConstants.themeInputBorderLight),
            width: 1,
          ),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: inputRadius,
          borderSide: BorderSide(
            color: isDark
                ? Colors.white.withValues(alpha: 0.12)
                : const Color(AppConstants.themeInputBorderLight),
            width: 1,
          ),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: inputRadius,
          borderSide: BorderSide(
            color: isDark
                ? Colors.white.withValues(alpha: 0.7)
                : const Color(AppConstants.themeInputBorderFocusedLight),
            width: isDark ? 1.5 : 2,
          ),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: inputRadius,
          borderSide: const BorderSide(
            color: Color(AppConstants.errorColor),
            width: 1,
          ),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: inputRadius,
          borderSide: const BorderSide(
            color: Color(AppConstants.errorColor),
            width: 1.5,
          ),
        ),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 12,
          vertical: 12,
        ),
        labelStyle: getTextStyle(
          fontSize: 12,
          fontWeight: FontWeight.normal,
          color: isDark
              ? Colors.white.withValues(alpha: 0.7)
              : const Color(AppConstants.themeInputLabelLight),
        ),
      ),
      cardTheme: CardThemeData(
        elevation: isDark ? 0 : 1,
        shadowColor: isDark
            ? Colors.black.withValues(alpha: 0.35)
            : Colors.black.withValues(alpha: 0.06),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
        ),
        margin: EdgeInsets.zero,
        color: isDark
            ? const Color(AppConstants.themeSurfaceDark)
            : Colors.white,
        surfaceTintColor: Colors.transparent,
      ),
      dividerTheme: DividerThemeData(
        color: isDark
            ? Colors.white.withValues(alpha: 0.15)
            : const Color(AppConstants.borderColor),
        thickness: 1,
        space: 1,
      ),
      chipTheme: ChipThemeData(
        backgroundColor: isDark
            ? const Color(AppConstants.themeElevatedSurfaceDark)
            : colorScheme.surfaceContainerLow,
        selectedColor: primary.withValues(alpha: isDark ? 0.3 : 0.1),
        labelStyle: getTextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w500,
          color: textPrimary,
        ),
        padding: const EdgeInsets.symmetric(
          horizontal: 12,
          vertical: 8,
        ),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
        ),
      ),
      listTileTheme: ListTileThemeData(
        contentPadding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.sm,
        ),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppConstants.radiusMedium),
        ),
      ),
      // [ColorScheme.primary] stays brand navy in dark mode; default Material icons
      // would inherit that and disappear on dark surfaces. Align with [AppShellTokens.navyIcon].
      iconTheme: IconThemeData(
        color: shellTokens.navyIcon,
        size: 24,
      ),
      progressIndicatorTheme: ProgressIndicatorThemeData(
        color: shellTokens.navyIcon,
      ),
      floatingActionButtonTheme: FloatingActionButtonThemeData(
        backgroundColor: secondary,
        foregroundColor: colorScheme.onSecondary,
        elevation: 4,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
        ),
      ),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        elevation: 2,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
        ),
        backgroundColor: isDark
            ? const Color(AppConstants.themeElevatedSurfaceDark)
            : const Color(0xFF1F2937),
        contentTextStyle: getTextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w500,
          color: Colors.white,
        ),
      ),
      bottomSheetTheme: BottomSheetThemeData(
        showDragHandle: true,
        dragHandleColor: isDark
            ? Colors.white.withValues(alpha: 0.35)
            : Colors.black.withValues(alpha: 0.25),
        backgroundColor: isDark
            ? const Color(AppConstants.themeSurfaceDark)
            : Colors.white,
        surfaceTintColor: Colors.transparent,
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(
            top: Radius.circular(AppConstants.radiusXLarge),
          ),
        ),
      ),
      dialogTheme: DialogThemeData(
        elevation: 3,
        backgroundColor: isDark
            ? const Color(AppConstants.themeSurfaceDark)
            : Colors.white,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppConstants.radiusXLarge),
        ),
      ),
      popupMenuTheme: PopupMenuThemeData(
        elevation: 3,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppConstants.radiusMedium),
        ),
      ),
    );
  }

  /// Montserrat for Latin script; Tajawal or platform default when Arabic is active.
  static String? _resolveFontFamily(
    Locale? locale,
    ArabicTextFontPreference arabicTextFont,
  ) {
    if (locale?.languageCode != 'ar') {
      return 'Montserrat';
    }
    return arabicTextFont == ArabicTextFontPreference.system ? null : 'Tajawal';
  }
}
