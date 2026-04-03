# iOS Style Guide for IFRC Network Databank Mobile App

This document outlines the iOS-native design system and patterns used throughout the app to ensure a consistent, native iOS experience.

## Design Principles

1. **Native iOS Look & Feel**: All UI components should follow iOS Human Interface Guidelines
2. **Consistency**: Use standardized components and constants throughout
3. **Accessibility**: All interactive elements must have proper semantic labels
4. **Dark Theme Support**: All components must work in both light and dark themes

## Typography

### Always Use IOSTextStyle

**❌ DON'T:**
```dart
Text(
  'Hello',
  style: TextStyle(
    fontSize: 17,
    fontWeight: FontWeight.w400,
  ),
)
```

**✅ DO:**
```dart
Text(
  'Hello',
  style: IOSTextStyle.body(context),
)
```

### Available Text Styles

- `IOSTextStyle.largeTitle(context)` - 34pt, bold (main titles)
- `IOSTextStyle.title1(context)` - 28pt, bold (section titles)
- `IOSTextStyle.title2(context)` - 22pt, bold (subsection titles)
- `IOSTextStyle.title3(context)` - 20pt, semibold (card titles)
- `IOSTextStyle.headline(context)` - 17pt, semibold (app bar titles)
- `IOSTextStyle.body(context)` - 17pt, regular (body text)
- `IOSTextStyle.callout(context)` - 16pt, regular (callouts)
- `IOSTextStyle.subheadline(context)` - 15pt, regular (subtitles)
- `IOSTextStyle.footnote(context)` - 13pt, regular (footnotes)
- `IOSTextStyle.caption1(context)` - 12pt, regular (captions)
- `IOSTextStyle.caption2(context)` - 11pt, regular (small captions)

### Customizing Text Styles

```dart
// ✅ Good - extend existing style
IOSTextStyle.body(context).copyWith(
  fontWeight: FontWeight.w600,
  color: Colors.red,
)

// ❌ Bad - create new TextStyle
TextStyle(
  fontSize: 17,
  fontWeight: FontWeight.w600,
)
```

## Spacing

### Always Use IOSSpacing

**❌ DON'T:**
```dart
SizedBox(height: 16)
EdgeInsets.all(24)
padding: EdgeInsets.symmetric(horizontal: 20, vertical: 12)
```

**✅ DO:**
```dart
SizedBox(height: IOSSpacing.md)
EdgeInsets.all(IOSSpacing.xl)
padding: EdgeInsets.symmetric(
  horizontal: IOSSpacing.lg,
  vertical: IOSSpacing.md,
)
```

### Available Spacing Constants

- `IOSSpacing.xs` - 4.0
- `IOSSpacing.sm` - 8.0
- `IOSSpacing.md` - 16.0
- `IOSSpacing.lg` - 20.0
- `IOSSpacing.xl` - 24.0
- `IOSSpacing.xxl` - 32.0

## Colors

### Always Use Theme-Aware Colors

**❌ DON'T:**
```dart
Color(0xFF111827)  // Hardcoded color
Colors.black       // Doesn't adapt to dark theme
```

**✅ DO:**
```dart
theme.colorScheme.onSurface           // Primary text color
context.textColor                     // Theme-aware text
IOSColors.getSystemBlue(context)      // iOS system blue
IOSColors.getGroupedBackground(context) // Grouped table background
```

### Available Color Helpers

- `IOSColors.getSystemBlue(context)` - iOS system blue (adapts to theme)
- `IOSColors.getGroupedBackground(context)` - Grouped table background
- `context.textColor` - Primary text color
- `context.textSecondaryColor` - Secondary text color
- `context.surfaceColor` - Surface color
- `context.cardColor` - Card color
- `context.borderColor` - Border color
- `context.dividerColor` - Divider color

## Components

### Buttons

**Always use iOS-style buttons:**

```dart
// Filled button
IOSFilledButton(
  onPressed: () {},
  semanticLabel: 'Save',
  child: Text('Save'),
)

// Outlined button
IOSOutlinedButton(
  onPressed: () {},
  semanticLabel: 'Cancel',
  child: Text('Cancel'),
)

// Icon button
IOSIconButton(
  icon: Icons.close,
  onPressed: () {},
  tooltip: 'Close',
  semanticLabel: 'Close',
)
```

### Cards

**Use iOSCard for consistent card styling:**

```dart
IOSCard(
  padding: EdgeInsets.all(IOSSpacing.md),
  child: Column(
    children: [...],
  ),
)
```

### Error States

**Use AppErrorState for consistent error displays:**

```dart
AppErrorState(
  message: errorMessage,
  onRetry: () => retry(),
  retryLabel: localizations.retry,
)
```

### Loading Indicators

**Use AppLoadingIndicator:**

```dart
AppLoadingIndicator(
  message: localizations.loading,
  color: const Color(AppConstants.ifrcRed),
)
```

## Lists

### iOS-Style List Tiles

```dart
ListTile(
  contentPadding: EdgeInsets.symmetric(
    horizontal: IOSSpacing.md,
    vertical: IOSSpacing.xs,
  ),
  dense: true,
  leading: Icon(Icons.home),
  title: Text(
    'Home',
    style: IOSTextStyle.body(context),
  ),
  trailing: Icon(
    Icons.chevron_right,
    size: 16,
    color: theme.colorScheme.onSurface.withOpacity(0.3),
  ),
)
```

## Navigation

### App Bars

**Use AppAppBar:**

```dart
AppAppBar(
  title: localizations.home,
)
```

### Bottom Navigation

**Use AppBottomNavigationBar:**

```dart
AppBottomNavigationBar(
  currentIndex: currentIndex,
  onTap: (index) => navigateToTab(index),
)
```

## Accessibility

### Always Add Semantic Labels

```dart
Semantics(
  label: 'Save button',
  hint: 'Tap to save changes',
  button: true,
  child: IOSFilledButton(...),
)
```

### Icon Buttons Must Have Tooltips

```dart
IOSIconButton(
  icon: Icons.close,
  tooltip: localizations.close,
  semanticLabel: localizations.close,
  onPressed: () {},
)
```

## Common Patterns

### Section Headers

```dart
Padding(
  padding: EdgeInsets.only(
    left: IOSSpacing.xl,
    right: IOSSpacing.xl,
    bottom: IOSSpacing.sm,
  ),
  child: Text(
    'Section Title',
    style: IOSTextStyle.footnote(context).copyWith(
      fontWeight: FontWeight.w600,
      color: theme.colorScheme.onSurface.withOpacity(0.6),
    ),
  ),
)
```

### Grouped Sections

```dart
IOSGroupedSection(
  header: 'Section Header',
  footer: 'Section Footer',
  children: [
    ListTile(...),
    ListTile(...),
  ],
)
```

## Checklist for New Screens

- [ ] All text uses `IOSTextStyle` (no hardcoded font sizes)
- [ ] All spacing uses `IOSSpacing` (no hardcoded values)
- [ ] All colors are theme-aware (no hardcoded colors)
- [ ] All buttons use iOS-style components (`IOSFilledButton`, `IOSOutlinedButton`, `IOSIconButton`)
- [ ] All interactive elements have semantic labels
- [ ] All icon buttons have tooltips
- [ ] Error states use `AppErrorState`
- [ ] Loading states use `AppLoadingIndicator`
- [ ] Cards use `IOSCard` or iOS-style containers
- [ ] Dark theme is tested and working

## Examples

See the following files for reference implementations:
- `screens/shared/dashboard_screen.dart` - Complex screen with stats cards
- `screens/admin/admin_dashboard_screen.dart` - Admin dashboard
- `screens/shared/settings_screen.dart` - Settings screen
- `widgets/ios_button.dart` - Button components
- `widgets/ios_card.dart` - Card components
- `widgets/error_state.dart` - Error state component
