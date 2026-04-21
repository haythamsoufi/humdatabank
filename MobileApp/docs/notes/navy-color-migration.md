# Navy Color Dark Theme Migration Guide

This guide shows how to migrate hardcoded `ifrcNavy` colors to use centralized theme-aware helpers for proper dark theme support.

## Available Helpers

All helpers are available via the `ThemeColors` extension on `BuildContext`:

```dart
import '../../utils/theme_extensions.dart';

// In your widget
context.navyTextColor      // For text that should be navy in light theme
context.navyIconColor      // For icons that should be navy in light theme
context.navyForegroundColor // For button text/foreground
context.navyBackgroundColor(opacity: 0.1) // For backgrounds with opacity
```

## Migration Patterns

### 1. Text Colors

**Before:**
```dart
Text(
  'Sector Name',
  style: TextStyle(
    color: const Color(AppConstants.ifrcNavy),
  ),
)
```

**After:**
```dart
Text(
  'Sector Name',
  style: TextStyle(
    color: context.navyTextColor,
  ),
)
```

### 2. Icon Colors

**Before:**
```dart
Icon(
  Icons.filter_list,
  color: const Color(AppConstants.ifrcNavy),
)
```

**After:**
```dart
Icon(
  Icons.filter_list,
  color: context.navyIconColor,
)
```

### 3. Button Foreground Colors

**Before:**
```dart
OutlinedButton.styleFrom(
  foregroundColor: const Color(AppConstants.ifrcNavy),
)
```

**After:**
```dart
OutlinedButton.styleFrom(
  foregroundColor: context.navyForegroundColor,
)
```

### 4. Background Colors with Opacity

**Before:**
```dart
Container(
  decoration: BoxDecoration(
    color: const Color(AppConstants.ifrcNavy).withOpacity(0.1),
  ),
)
```

**After:**
```dart
Container(
  decoration: BoxDecoration(
    color: context.navyBackgroundColor(opacity: 0.1),
  ),
)
```

### 5. Conditional Logic (Old Pattern)

**Before:**
```dart
color: Theme.of(context).brightness == Brightness.dark
    ? context.textColor
    : const Color(AppConstants.ifrcNavy),
```

**After:**
```dart
color: context.navyTextColor,  // Much cleaner!
```

## Files That Need Migration

Based on the codebase scan, these files contain `ifrcNavy` colors that may need migration:

- `screens/public/indicator_detail_screen.dart`
- `screens/shared/dashboard_screen.dart`
- `screens/admin/templates_screen.dart`
- `screens/admin/audit_trail_screen.dart`
- `screens/admin/system_configuration_screen.dart`
- `widgets/assignment_card.dart`

**Note:** Some uses of `ifrcNavy` are appropriate (like solid background colors for headers), but text and icon colors should use the helpers.

## What Gets Adapted

- **Light Theme:** Uses `ifrcNavy` (0xFF011E41) as before
- **Dark Theme:** 
  - Text/Icons: Uses `textColor` or `iconColor` (white/light colors)
  - Backgrounds: Uses white with opacity for subtle backgrounds

This ensures proper contrast and readability in both themes.
