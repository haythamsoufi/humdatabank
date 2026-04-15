# Design System

## Overview

The Humanitarian Databank mobile app uses a layered design system:

1. **Design Tokens** — Colors, spacing, typography defined in `lib/theme/`
2. **Core Widgets** — Reusable components in `lib/widgets/`
3. **iOS-Style Components** — Platform-aligned widgets for native feel
4. **Screen Layouts** — Consistent page structure patterns

## Running the Widgetbook

```bash
cd MobileApp
flutter run -t widgetbook/main.dart
```

Or with a specific device:
```bash
flutter run -t widgetbook/main.dart -d chrome
```

## Design Tokens

### Colors
- **Primary**: IFRC Navy (`#011E41`)
- **Accent**: IFRC Red (`#C8102E`)
- **Surface**: Adaptive light/dark

### Typography
- **Primary font**: Montserrat (Latin)
- **Arabic font**: Tajawal (RTL)
- **Scale**: Responsive via `LayoutScale`

### Spacing
See `lib/utils/app_spacing.dart` for standard spacing tokens.

## Component Catalog

### Foundation
- `AppLoadingIndicator` — iOS/Material spinner with optional message
- `AppFullScreenLoading` — Full-page loading state
- `AppErrorState` — Error display with retry action

### Navigation
- `AppAppBar` — Themed app bar with optional large title
- `AppBottomNavigationBar` — Bottom tab bar
- `AppNavigationDrawer` — Side navigation drawer

### iOS Components
- `IOSFilledButton` — iOS-styled filled action button
- `IOSOutlinedButton` — iOS-styled outlined button
- `IOSIconButton` — iOS-styled icon button with haptic feedback
- `IOSCard` — Rounded card with iOS styling
- `IOSListTile` — iOS Settings-style list item
- `IOSListSwitchTile` — Settings row with CupertinoSwitch
- `IOSGroupedList` — iOS grouped list section (like iOS Settings)

### Form Controls
- `AppCheckboxListTile` — Themed checkbox
- `AppSwitchListTile` — Themed toggle
- `EntitySelector` — Country/entity picker

## Adding New Components

1. Create the widget in `lib/widgets/`
2. Add a use case in `widgetbook/main.dart`
3. Follow existing patterns for constructors (named params, const where possible)
4. Support both light and dark themes
5. Add Semantics labels for accessibility
