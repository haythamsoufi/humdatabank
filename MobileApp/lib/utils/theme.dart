import 'package:flutter/material.dart';
import 'constants.dart';

class AppTheme {
  static ThemeData lightTheme({Locale? locale}) {
    final colorScheme = ColorScheme.fromSeed(
      seedColor: Color(AppConstants.ifrcNavy),
      primary: Color(AppConstants.ifrcNavy),
      secondary: Color(AppConstants.ifrcRed),
      error: const Color(AppConstants.errorColor),
      surface: const Color(AppConstants.backgroundColor),
      onPrimary: Colors.white,
      onSecondary: Colors.white,
      onSurface: const Color(AppConstants.textColor),
      brightness: Brightness.light,
    );

    // Use Tajawal font for Arabic, Montserrat for other languages
    final fontFamily = locale?.languageCode == 'ar' ? 'Tajawal' : 'Montserrat';

    // Helper function to get TextStyle with appropriate font
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

    return ThemeData(
      useMaterial3: true,
      visualDensity: VisualDensity.adaptivePlatformDensity,
      materialTapTargetSize: MaterialTapTargetSize.padded,
      colorScheme: colorScheme,
      scaffoldBackgroundColor:
          const Color(0xFFF2F2F7), // Light grey background (iPhone style)
      appBarTheme: AppBarTheme(
        backgroundColor: Colors.white,
        foregroundColor: Colors.black,
        elevation: 0,
        centerTitle: false,
        surfaceTintColor: Colors.transparent,
        titleTextStyle: getTextStyle(
          fontSize: 20,
          fontWeight: FontWeight.w600,
          color: Colors.black,
          letterSpacing: -0.5,
        ),
        iconTheme: const IconThemeData(color: Colors.black),
        shadowColor: Colors.black.withOpacity(0.1),
      ),
      textTheme: TextTheme(
        displayLarge: getTextStyle(
          fontSize: 32,
          fontWeight: FontWeight.bold,
          color: const Color(AppConstants.textColor),
          letterSpacing: -1,
        ),
        displayMedium: getTextStyle(
          fontSize: 28,
          fontWeight: FontWeight.bold,
          color: const Color(AppConstants.textColor),
          letterSpacing: -0.5,
        ),
        displaySmall: getTextStyle(
          fontSize: 24,
          fontWeight: FontWeight.w600,
          color: const Color(AppConstants.textColor),
          letterSpacing: -0.5,
        ),
        headlineMedium: getTextStyle(
          fontSize: 20,
          fontWeight: FontWeight.w600,
          color: const Color(AppConstants.textColor),
          letterSpacing: -0.3,
        ),
        titleLarge: getTextStyle(
          fontSize: 18,
          fontWeight: FontWeight.w600,
          color: const Color(AppConstants.textColor),
        ),
        titleMedium: getTextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w600,
          color: const Color(AppConstants.textColor),
        ),
        bodyLarge: getTextStyle(
          fontSize: 16,
          fontWeight: FontWeight.normal,
          color: const Color(AppConstants.textColor),
          height: 1.5,
        ),
        bodyMedium: getTextStyle(
          fontSize: 14,
          fontWeight: FontWeight.normal,
          color: const Color(AppConstants.textColor),
          height: 1.5,
        ),
        bodySmall: getTextStyle(
          fontSize: 12,
          fontWeight: FontWeight.normal,
          color: const Color(AppConstants.textSecondary),
          height: 1.4,
        ),
        labelLarge: getTextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w600,
          color: const Color(AppConstants.textColor),
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: Color(AppConstants.ifrcNavy),
          foregroundColor: Colors.white,
          elevation: 0,
          padding: const EdgeInsets.symmetric(
            horizontal: AppConstants.paddingLarge,
            vertical: AppConstants.paddingMedium + 2,
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
          elevation: MaterialStateProperty.resolveWith<double>(
            (Set<MaterialState> states) {
              if (states.contains(MaterialState.disabled)) return 0;
              if (states.contains(MaterialState.pressed)) return 2;
              return 1;
            },
          ),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: const Color(0xFF0095F6),
          foregroundColor: Colors.white,
          padding: const EdgeInsets.symmetric(
            horizontal: AppConstants.paddingLarge,
            vertical: AppConstants.paddingMedium + 2,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
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
          foregroundColor: Color(AppConstants.ifrcNavy),
          padding: const EdgeInsets.symmetric(
            horizontal: AppConstants.paddingLarge,
            vertical: AppConstants.paddingMedium + 2,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
          ),
          side: BorderSide(
            color: Color(AppConstants.ifrcNavy),
            width: 1.5,
          ),
          textStyle: getTextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
            color: Color(AppConstants.ifrcNavy),
            letterSpacing: 0.2,
          ),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: const Color(0xFFFAFAFA),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(4),
          borderSide: const BorderSide(
            color: Color(0xFFDBDBDB),
            width: 1,
          ),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(4),
          borderSide: const BorderSide(
            color: Color(0xFFDBDBDB),
            width: 1,
          ),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(4),
          borderSide: const BorderSide(
            color: Color(0xFF8E8E8E),
            width: 1,
          ),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(4),
          borderSide: const BorderSide(
            color: Color(AppConstants.errorColor),
            width: 1,
          ),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(4),
          borderSide: const BorderSide(
            color: Color(AppConstants.errorColor),
            width: 1,
          ),
        ),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 12,
          vertical: 12,
        ),
        labelStyle: getTextStyle(
          fontSize: 12,
          fontWeight: FontWeight.normal,
          color: const Color(0xFF8E8E8E),
        ),
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
        ),
        margin: EdgeInsets.zero,
        color: Colors.white,
        surfaceTintColor: Colors.transparent,
        shadowColor: Colors.transparent,
      ),
      dividerTheme: const DividerThemeData(
        color: Color(AppConstants.borderColor),
        thickness: 1,
        space: 1,
      ),
      chipTheme: ChipThemeData(
        backgroundColor: Colors.grey.shade100,
        selectedColor: Color(AppConstants.ifrcNavy).withOpacity(0.1),
        labelStyle: getTextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w500,
          color: const Color(AppConstants.textColor),
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
          horizontal: AppConstants.paddingMedium,
          vertical: AppConstants.paddingSmall,
        ),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppConstants.radiusMedium),
        ),
      ),
      floatingActionButtonTheme: FloatingActionButtonThemeData(
        backgroundColor: Color(AppConstants.ifrcRed),
        foregroundColor: Colors.white,
        elevation: 4,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
        ),
      ),
    );
  }

  static ThemeData darkTheme({Locale? locale}) {
    final colorScheme = ColorScheme.fromSeed(
      seedColor: Color(AppConstants.ifrcNavy),
      primary: Color(AppConstants.ifrcNavy),
      secondary: Color(AppConstants.ifrcRed),
      error: const Color(AppConstants.errorColor),
      surface: const Color(0xFF1E1E1E),
      onPrimary: Colors.white,
      onSecondary: Colors.white,
      onSurface: Colors.white,
      brightness: Brightness.dark,
    );

    // Use Tajawal font for Arabic, Montserrat for other languages
    final fontFamily = locale?.languageCode == 'ar' ? 'Tajawal' : 'Montserrat';

    // Helper function to get TextStyle with appropriate font
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

    return ThemeData(
      useMaterial3: true,
      visualDensity: VisualDensity.adaptivePlatformDensity,
      materialTapTargetSize: MaterialTapTargetSize.padded,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: const Color(0xFF121212),
      appBarTheme: AppBarTheme(
        backgroundColor: const Color(0xFF1E1E1E),
        foregroundColor: Colors.white,
        elevation: 0,
        centerTitle: false,
        surfaceTintColor: Colors.transparent,
        titleTextStyle: getTextStyle(
          fontSize: 20,
          fontWeight: FontWeight.w600,
          color: Colors.white,
          letterSpacing: -0.5,
        ),
        iconTheme: const IconThemeData(color: Colors.white),
        shadowColor: Colors.black.withOpacity(0.3),
      ),
      textTheme: TextTheme(
        displayLarge: getTextStyle(
          fontSize: 32,
          fontWeight: FontWeight.bold,
          color: Colors.white,
          letterSpacing: -1,
        ),
        displayMedium: getTextStyle(
          fontSize: 28,
          fontWeight: FontWeight.bold,
          color: Colors.white,
          letterSpacing: -0.5,
        ),
        displaySmall: getTextStyle(
          fontSize: 24,
          fontWeight: FontWeight.w600,
          color: Colors.white,
          letterSpacing: -0.5,
        ),
        headlineMedium: getTextStyle(
          fontSize: 20,
          fontWeight: FontWeight.w600,
          color: Colors.white,
          letterSpacing: -0.3,
        ),
        titleLarge: getTextStyle(
          fontSize: 18,
          fontWeight: FontWeight.w600,
          color: Colors.white,
        ),
        titleMedium: getTextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w600,
          color: Colors.white,
        ),
        bodyLarge: getTextStyle(
          fontSize: 16,
          fontWeight: FontWeight.normal,
          color: Colors.white,
          height: 1.5,
        ),
        bodyMedium: getTextStyle(
          fontSize: 14,
          fontWeight: FontWeight.normal,
          // Ensure good contrast (WCAG AA requires 4.5:1 for normal text)
          color: Colors.white.withOpacity(0.9),
          height: 1.5,
        ),
        bodySmall: getTextStyle(
          fontSize: 12,
          fontWeight: FontWeight.normal,
          // Slightly reduced opacity but still readable
          color: Colors.white.withOpacity(0.7),
          height: 1.4,
        ),
        labelLarge: getTextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w600,
          color: Colors.white,
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: Color(AppConstants.ifrcNavy),
          foregroundColor: Colors.white,
          elevation: 0,
          padding: const EdgeInsets.symmetric(
            horizontal: AppConstants.paddingLarge,
            vertical: AppConstants.paddingMedium + 2,
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
          elevation: MaterialStateProperty.resolveWith<double>(
            (Set<MaterialState> states) {
              if (states.contains(MaterialState.disabled)) return 0;
              if (states.contains(MaterialState.pressed)) return 2;
              return 1;
            },
          ),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: const Color(0xFF0095F6),
          foregroundColor: Colors.white,
          padding: const EdgeInsets.symmetric(
            horizontal: AppConstants.paddingLarge,
            vertical: AppConstants.paddingMedium + 2,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(8),
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
          // Use lighter color for dark theme for better visibility
          foregroundColor: Colors.white.withOpacity(0.9),
          padding: const EdgeInsets.symmetric(
            horizontal: AppConstants.paddingLarge,
            vertical: AppConstants.paddingMedium + 2,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
          ),
          side: BorderSide(
            // Use white with good opacity for dark theme visibility
            color: Colors.white.withOpacity(0.5),
            width: 1.5,
          ),
          textStyle: getTextStyle(
            fontSize: 16,
            fontWeight: FontWeight.w600,
            color: Colors.white.withOpacity(0.9),
            letterSpacing: 0.2,
          ),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: const Color(0xFF2C2C2C),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(4),
          borderSide: BorderSide(
            color: Colors.white.withOpacity(0.12),
            width: 1,
          ),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(4),
          borderSide: BorderSide(
            color: Colors.white.withOpacity(0.12),
            width: 1,
          ),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(4),
          borderSide: BorderSide(
            // Improved focus border visibility
            color: Colors.white.withOpacity(0.7),
            width: 1.5,
          ),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(4),
          borderSide: const BorderSide(
            color: Color(AppConstants.errorColor),
            width: 1,
          ),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(4),
          borderSide: const BorderSide(
            color: Color(AppConstants.errorColor),
            width: 1,
          ),
        ),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 12,
          vertical: 12,
        ),
        labelStyle: getTextStyle(
          fontSize: 12,
          fontWeight: FontWeight.normal,
          // Improved label visibility in dark theme
          color: Colors.white.withOpacity(0.7),
        ),
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
        ),
        margin: EdgeInsets.zero,
        color: const Color(0xFF1E1E1E),
        surfaceTintColor: Colors.transparent,
        shadowColor: Colors.black.withOpacity(0.3),
      ),
      dividerTheme: DividerThemeData(
        // Slightly more visible dividers in dark theme
        color: Colors.white.withOpacity(0.15),
        thickness: 1,
        space: 1,
      ),
      chipTheme: ChipThemeData(
        backgroundColor: const Color(0xFF2C2C2C),
        selectedColor: Color(AppConstants.ifrcNavy).withOpacity(0.3),
        labelStyle: getTextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w500,
          color: Colors.white,
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
          horizontal: AppConstants.paddingMedium,
          vertical: AppConstants.paddingSmall,
        ),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppConstants.radiusMedium),
        ),
      ),
      floatingActionButtonTheme: FloatingActionButtonThemeData(
        backgroundColor: Color(AppConstants.ifrcRed),
        foregroundColor: Colors.white,
        elevation: 4,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppConstants.radiusLarge),
        ),
      ),
    );
  }
}
