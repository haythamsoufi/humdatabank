# Organization Configuration

This directory contains organization-specific configuration files that allow the mobile app to be customized for different organizations.

For the consolidated MobileApp documentation index, see [`MobileApp/docs/README.md`](../../docs/README.md).

## Default Configuration

**`organization_config.json`** - Default generic "Humanitarian Databank" configuration used when no organization-specific config is specified.

## Organization-Specific Configurations

To use an organization-specific configuration, create a file named:
```
organization_config.{organization}.json
```

For example:
- `organization_config.ifrc.json` - example organization profile (sample; replace with your org’s file)
- `organization_config.oxfam.json` - Oxfam-specific configuration
- `organization_config.unicef.json` - UNICEF-specific configuration

## Configuration Structure

Each configuration file should follow this structure:

```json
{
  "organization": {
    "name": "Organization Name",
    "fullName": "Full Organization Name",
    "shortName": "Short Name",
    "description": "Organization description",
    "website": "https://example.org",
    "supportEmail": "support@example.org",
    "contactEmail": "contact@example.org"
  },
  "branding": {
    "primaryColor": "#3B82F6",
    "secondaryColor": "#1E40AF",
    "accentColor": "#EF4444",
    "navyColor": "#011E41",
    "redColor": "#C8102E",
    "darkRedColor": "#A50D25",
    "logoPath": "assets/images/app_icon.png"
  },
  "app": {
    "name": "App Display Name",
    "packageName": "com.organization.app",
    "displayName": "App Display Name",
    "description": "App description"
  },
  "azure": {
    "b2cTenant": "tenant.onmicrosoft.com",
    "b2cPolicy": "B2C_1A_POLICY_NAME",
    "redirectScheme": "appscheme"
  },
  "features": {
    "showOrganizationName": true,
    "customBranding": true
  }
}
```

## How to Use

### Method 1: Environment Variable (Recommended for Builds)

When building the app, specify the organization using the `ORGANIZATION_CONFIG` environment variable:

```bash
# Example named profile (ifrc)
flutter build appbundle --release --dart-define=ORGANIZATION_CONFIG=ifrc --dart-define=PRODUCTION=true

# For generic Humanitarian Databank (default)
flutter build appbundle --release --dart-define=PRODUCTION=true
```

### Method 2: Code-Level Configuration

The organization config is automatically loaded at app startup. If you need to specify it programmatically:

```dart
await OrganizationConfigService().loadConfig(organization: 'ifrc');
```

### Method 3: Runtime Configuration (Future Enhancement)

Currently, the config is loaded at startup. Future versions may support runtime configuration changes.

## Color Format

All colors should be specified in hex format with or without the `#` prefix:
- `#3B82F6` (with #)
- `3B82F6` (without #)

Both formats are supported.

## Example profile

See `organization_config.ifrc.json` for a sample organization-specific configuration you can copy and adapt.

## Fallback Behavior

If an organization-specific config file is not found, the app will:
1. Try to load the specified organization config
2. Fall back to `organization_config.json` (default Humanitarian Databank)
3. If that fails, use hardcoded default values

## Updating Configuration

After modifying a configuration file:
1. Rebuild the app: `flutter clean && flutter pub get`
2. Rebuild the bundle: `flutter build appbundle --release --dart-define=ORGANIZATION_CONFIG=your_profile`

## Notes

- Configuration files are bundled with the app at build time
- Changes to config files require a rebuild
- The app name, colors, and branding are all configurable
- Azure B2C settings can be left empty if not using Azure authentication
- Package name should match your Android/iOS bundle identifier
