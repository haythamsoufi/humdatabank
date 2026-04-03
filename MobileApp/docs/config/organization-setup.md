# Organization Setup Guide

This guide explains how to configure the mobile app for a specific organization.

## Quick Start

1. **Create your organization config file:**
   ```
   assets/config/organization_config.{yourorg}.json
   ```

2. **Build with your organization:**
   ```bash
   flutter build appbundle --release --dart-define=ORGANIZATION_CONFIG=yourorg --dart-define=PRODUCTION=true
   ```

## Step-by-Step Setup

### 1. Copy the Default Config

Copy `assets/config/organization_config.json` to create your organization-specific config:

```bash
cp assets/config/organization_config.json assets/config/organization_config.yourorg.json
```

### 2. Edit Your Config

Open `assets/config/organization_config.yourorg.json` and update:

#### Organization Information
```json
{
  "organization": {
    "name": "Your Organization",
    "fullName": "Full Name of Your Organization",
    "shortName": "Short Name",
    "description": "Your organization's databank mobile app",
    "website": "https://yourwebsite.org",
    "supportEmail": "support@yourwebsite.org",
    "contactEmail": "contact@yourwebsite.org"
  }
}
```

#### Branding Colors
```json
{
  "branding": {
    "primaryColor": "#YOUR_PRIMARY_COLOR",
    "secondaryColor": "#YOUR_SECONDARY_COLOR",
    "accentColor": "#YOUR_ACCENT_COLOR",
    "navyColor": "#YOUR_NAVY_COLOR",
    "redColor": "#YOUR_RED_COLOR",
    "darkRedColor": "#YOUR_DARK_RED_COLOR",
    "logoPath": "assets/images/app_icon.png"
  }
}
```

**Color Format:** Use hex colors with or without `#` (e.g., `#3B82F6` or `3B82F6`)

#### App Information
```json
{
  "app": {
    "name": "Your Organization Databank",
    "packageName": "com.yourorg.databank",
    "displayName": "Your Organization Databank",
    "description": "Your organization's databank mobile application"
  }
}
```

**Important:** The `packageName` should match your Android package name and iOS bundle identifier.

#### Azure B2C (Optional)
If you're using Azure AD B2C for authentication:

```json
{
  "azure": {
    "b2cTenant": "yourtenant.onmicrosoft.com",
    "b2cPolicy": "B2C_1A_YOUR_POLICY",
    "redirectScheme": "yourorgdatabank"
  }
}
```

If not using Azure, leave these empty:
```json
{
  "azure": {
    "b2cTenant": "",
    "b2cPolicy": "",
    "redirectScheme": "yourorgdatabank"
  }
}
```

### 3. Update Android Package Name

If you changed the `packageName` in the config, update:

**Android:** `android/app/build.gradle`
```gradle
defaultConfig {
    applicationId "com.yourorg.databank"  // Match your config
    // ...
}
```

**Android Manifest:** `android/app/src/main/AndroidManifest.xml`
```xml
<manifest package="com.yourorg.databank">
```

### 4. Update iOS Bundle Identifier

**iOS:** Open `ios/Runner.xcodeproj` in Xcode and update:
- Bundle Identifier: `com.yourorg.databank` (match your config)

### 5. Build Your App

```bash
# Clean previous builds
flutter clean
flutter pub get

# Build with your organization config
flutter build appbundle --release --dart-define=ORGANIZATION_CONFIG=yourorg --dart-define=PRODUCTION=true
```

## Example: IFRC Setup

See `assets/config/organization_config.ifrc.json` for a complete example.

To build for IFRC:
```bash
flutter build appbundle --release --dart-define=ORGANIZATION_CONFIG=ifrc --dart-define=PRODUCTION=true
```

## Testing

### Test with Default Config
```bash
flutter run --dart-define=PRODUCTION=true
```

### Test with Organization Config
```bash
flutter run --dart-define=ORGANIZATION_CONFIG=yourorg --dart-define=PRODUCTION=true
```

## Verification

After building, verify the app shows your organization's:
- ✅ App name in the app launcher
- ✅ Organization name in the app
- ✅ Brand colors throughout the UI
- ✅ Correct contact information

## Troubleshooting

### Config Not Loading
- Ensure the config file is in `assets/config/`
- Check that `pubspec.yaml` includes `assets/config/` in assets
- Run `flutter clean && flutter pub get`

### Colors Not Applied
- Verify color format is correct (hex with or without `#`)
- Check that colors are valid hex values
- Ensure config is loaded before accessing colors

### App Name Not Changed
- Verify `app.name` in config matches expected name
- Check that config is loaded at startup
- Rebuild the app after config changes

## Multiple Organizations

You can maintain multiple organization configs:
- `organization_config.json` - Default (NGO Databank)
- `organization_config.ifrc.json` - IFRC
- `organization_config.oxfam.json` - Oxfam
- `organization_config.unicef.json` - UNICEF
- etc.

Build for each by changing the `ORGANIZATION_CONFIG` value.

## Best Practices

1. **Version Control:** Keep all organization configs in version control
2. **Documentation:** Document organization-specific requirements
3. **Testing:** Test each organization config before deployment
4. **Naming:** Use clear, consistent naming for organization identifiers
5. **Backup:** Keep backups of working configurations

## Support

For questions or issues with organization configuration, refer to:
- `assets/config/README.md` - Detailed configuration reference
- `MobileApp/README.md` - General app documentation
