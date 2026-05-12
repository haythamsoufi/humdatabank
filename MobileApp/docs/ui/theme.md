# Theme Usage Guide

This guide explains how to ensure proper text visibility and theme adaptation in the IFRC Databank app.

## Dark Theme System

The app supports both light and dark themes. All screens should use theme-aware colors to ensure proper visibility in both modes.

## UI surfaces (where colors come from)

The app mixes a few deliberate layers; pick tokens from the right one:

1. **Material shell** — Default app chrome: `AppTheme` (`lib/utils/theme.dart`), `ColorScheme`, `Theme.of(context).textTheme`, and `ThemeColors` / **`AppShellTokens`** (`Theme.of(context).extension<AppShellTokens>()`). Primary actions use org navy (`ColorScheme.primary`); **[FilledButton](https://api.flutter.dev/flutter/material/FilledButton-class.html)** follows the same primary fill as elevated actions unless a screen overrides for semantics (e.g. IFRC red for SSO).

2. **iOS-style chrome** — Settings-style components: `lib/utils/ios_constants.dart` (`IOSColors`, `IOSSpacing`, `IOSTextStyle`). Uses Apple-like system blues/grays for native feel; not fully merged with Material brand colors by design.

3. **Immersive AI chat** — Dark mode uses a dedicated neutral palette (`lib/theme/chat_immersive_palette.dart`) so links and text stay readable on near-black surfaces; this is **not** the same hex stack as global `AppTheme` dark scaffold.

**Cross-product note:** The Backoffice web UI uses a different shape language (e.g. sharp corners on buttons). Mobile stays Material/iOS rounded unless product aligns them later.

## Responsive scale

Width-based scaling is unified in **`LayoutScale.screenScaleFactor`** (`lib/utils/layout_scale.dart`). It feeds:

- Global Material `textTheme` scaling via `ResponsiveTypography.screenTextScaleFactor` in `main.dart`
- `IOSSpacing` (padding, insets) and `IOSIconSize`
- `IOSTextStyle` font sizes

OS **accessibility text scaling** is still applied by Flutter on top of these styles.

## Best Practices

### ✅ DO: Use Theme-Aware Colors

#### 1. Use Theme Extensions (Recommended)

Shell semantics are registered as **`AppShellTokens`** on `ThemeData.extensions` (see `lib/theme/app_shell_tokens.dart`). Prefer the stable **`ThemeColors`** API on `BuildContext` (it delegates to `AppShellTokens` when present).

```dart
// Import the extension
import '../utils/theme_extensions.dart';

// In your widget
Widget build(BuildContext context) {
  return Container(
    color: context.surfaceColor,  // Adapts to theme
    child: Text(
      'Hello',
      style: TextStyle(
        color: context.textColor,  // Adapts to theme
      ),
    ),
  );
}
```

#### 2. Use Theme.of(context)

```dart
Widget build(BuildContext context) {
  final theme = Theme.of(context);
  final isDark = theme.brightness == Brightness.dark;
  
  return Container(
    color: theme.colorScheme.surface,
    child: Text(
      'Hello',
      style: theme.textTheme.bodyLarge,  // Uses theme text styles
    ),
  );
}
```

#### 3. Use ColorScheme Colors

```dart
Widget build(BuildContext context) {
  final colorScheme = Theme.of(context).colorScheme;
  
  return Container(
    color: colorScheme.surface,
    child: Text(
      'Hello',
      style: TextStyle(
        color: colorScheme.onSurface,  // Proper contrast color
      ),
    ),
  );
}
```

### ❌ DON'T: Use Hardcoded Colors

```dart
// ❌ BAD - Won't adapt to dark theme
Container(
  color: Colors.white,
  child: Text(
    'Hello',
    style: TextStyle(
      color: Colors.black,  // Hard to see in dark theme
    ),
  ),
)

// ✅ GOOD - Adapts to theme
Container(
  color: context.surfaceColor,
  child: Text(
    'Hello',
    style: TextStyle(
      color: context.textColor,
    ),
  ),
)
```

## Common Color Patterns

### Text Colors

| Purpose | Light Theme | Dark Theme | How to Use |
|---------|-------------|------------|------------|
| Primary text | Dark gray (#111827) | White | `context.textColor` or `Theme.of(context).colorScheme.onSurface` |
| Secondary text | Medium gray (#6B7280) | White 60% | `context.textSecondaryColor` or `Theme.of(context).textTheme.bodySmall?.color` |
| Disabled text | Black 38% | White 38% | `context.disabledTextColor` |

### Background Colors

| Purpose | Light Theme | Dark Theme | How to Use |
|---------|-------------|------------|------------|
| Scaffold | White | Dark gray (#121212) | `context.scaffoldBackgroundColor` or `Theme.of(context).scaffoldBackgroundColor` |
| Surface/Card | White | Dark gray (#1E1E1E) | `context.surfaceColor` or `Theme.of(context).cardColor` |
| Input field | Light gray (#FAFAFA) | Dark gray (#2C2C2C) | `context.lightSurfaceColor` |
| Subtle background | Very light gray | Medium gray | `context.subtleSurfaceColor` |

### Border Colors

| Purpose | Light Theme | Dark Theme | How to Use |
|---------|-------------|------------|------------|
| Default border | Light gray (#E5E7EB) | White 12% | `context.borderColor` |
| Focus border | Medium gray | White 70% | Uses `InputDecorationTheme` |

## Available Theme Extensions

The `ThemeColors` extension provides easy access to theme-aware colors:

- `context.textColor` - Primary text color
- `context.textSecondaryColor` - Secondary text color
- `context.surfaceColor` - Surface/background color
- `context.cardColor` - Card background color
- `context.borderColor` - Border color
- `context.scaffoldBackgroundColor` - Scaffold background
- `context.dividerColor` - Divider color
- `context.lightSurfaceColor` - Light surface (inputs, chips)
- `context.subtleSurfaceColor` - Subtle background
- `context.iconColor` - Icon color
- `context.disabledTextColor` - Disabled text color

## Migration Checklist

When updating a screen to be theme-aware:

1. ✅ Replace `Colors.white` with `context.surfaceColor` or `Theme.of(context).cardColor`
2. ✅ Replace `Colors.black` with `context.textColor` or `Theme.of(context).colorScheme.onSurface`
3. ✅ Replace `Color(AppConstants.textColor)` with `context.textColor`
4. ✅ Replace `Color(AppConstants.borderColor)` with `context.borderColor`
5. ✅ Replace `Colors.grey.shade300` with `context.borderColor` or `context.dividerColor`
6. ✅ Replace `Colors.grey.shade50` with `context.subtleSurfaceColor`
7. ✅ Use `Theme.of(context).textTheme` styles instead of hardcoded text styles
8. ✅ For conditional styling, check `Theme.of(context).brightness == Brightness.dark`

## Text Visibility Standards

Design targets **WCAG AA** contrast for normal UI (4.5:1 for body text, 3:1 for large text). Contrast is achieved by **choosing tokens** (`ColorScheme`, `ThemeColors`, chat palette) — the app does **not** run automatic contrast correction at runtime. When adding new surfaces or custom colors, verify contrast manually or with design tools.

## Examples

### Example 1: Basic Container with Text

```dart
// ❌ BAD
Container(
  color: Colors.white,
  child: Text(
    'Hello',
    style: TextStyle(color: Colors.black),
  ),
)

// ✅ GOOD
Container(
  color: context.surfaceColor,
  child: Text(
    'Hello',
    style: TextStyle(color: context.textColor),
  ),
)
```

### Example 2: Card with Title and Subtitle

```dart
// ❌ BAD
Card(
  color: Colors.white,
  child: Column(
    children: [
      Text(
        'Title',
        style: TextStyle(
          color: Color(AppConstants.textColor),
          fontSize: 18,
        ),
      ),
      Text(
        'Subtitle',
        style: TextStyle(
          color: Color(AppConstants.textSecondary),
          fontSize: 14,
        ),
      ),
    ],
  ),
)

// ✅ GOOD
Card(
  child: Column(
    children: [
      Text(
        'Title',
        style: Theme.of(context).textTheme.titleLarge,
      ),
      Text(
        'Subtitle',
        style: Theme.of(context).textTheme.bodySmall,
      ),
    ],
  ),
)
```

### Example 3: Input Field

```dart
// ❌ BAD
TextField(
  decoration: InputDecoration(
    filled: true,
    fillColor: Colors.grey.shade50,
    border: OutlineInputBorder(
      borderSide: BorderSide(color: Color(AppConstants.borderColor)),
    ),
  ),
)

// ✅ GOOD - Uses InputDecorationTheme automatically
TextField(
  decoration: InputDecoration(
    hintText: 'Enter text',
    // Theme colors applied automatically via InputDecorationTheme
  ),
)
```

## Testing Dark Theme

To test dark theme visibility:

1. Enable dark theme in Settings
2. Check all screens for:
   - Text readability
   - Proper contrast
   - Border visibility
   - Input field visibility
   - Button visibility

## Questions?

Refer to:
- `lib/utils/theme.dart` - Theme configuration
- `lib/theme/app_shell_tokens.dart` - `AppShellTokens` ThemeExtension
- `lib/theme/chat_immersive_palette.dart` - Immersive chat-only colors
- `lib/utils/theme_extensions.dart` - `ThemeColors` and other helpers
- `lib/utils/layout_scale.dart` - Unified width-based scale
- `lib/utils/constants.dart` - App constants (use with caution, prefer theme colors)

### Optional: theme drift check (CI)

`scripts/check_theme_drift.py` can fail the build when **new** `Colors.white` / `Colors.black` appear on added lines under `lib/screens/` or `lib/widgets/` (compares working tree to `HEAD`). Run from repo root:

`python MobileApp/scripts/check_theme_drift.py --git-diff`

Use `--base <ref>` to compare against another branch (e.g. `origin/main`). Without `--git-diff`, the script exits 0 (no-op).
