import 'dart:convert';
import 'package:flutter/services.dart';
import '../utils/debug_logger.dart';

/// Organization configuration model
class OrganizationConfig {
  final OrganizationInfo organization;
  final BrandingInfo branding;
  final AppInfo app;
  final AzureInfo azure;
  final FeaturesInfo features;

  OrganizationConfig({
    required this.organization,
    required this.branding,
    required this.app,
    required this.azure,
    required this.features,
  });

  factory OrganizationConfig.fromJson(Map<String, dynamic> json) {
    return OrganizationConfig(
      organization: OrganizationInfo.fromJson(json['organization'] ?? {}),
      branding: BrandingInfo.fromJson(json['branding'] ?? {}),
      app: AppInfo.fromJson(json['app'] ?? {}),
      azure: AzureInfo.fromJson(json['azure'] ?? {}),
      features: FeaturesInfo.fromJson(json['features'] ?? {}),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'organization': organization.toJson(),
      'branding': branding.toJson(),
      'app': app.toJson(),
      'azure': azure.toJson(),
      'features': features.toJson(),
    };
  }
}

class OrganizationInfo {
  final String name;
  final String fullName;
  final String shortName;
  final String description;
  final String website;
  final String supportEmail;
  final String contactEmail;

  OrganizationInfo({
    required this.name,
    required this.fullName,
    required this.shortName,
    required this.description,
    required this.website,
    required this.supportEmail,
    required this.contactEmail,
  });

  factory OrganizationInfo.fromJson(Map<String, dynamic> json) {
    return OrganizationInfo(
      name: json['name'] ?? 'Humanitarian Databank',
      fullName: json['fullName'] ?? 'Humanitarian Databank',
      shortName: json['shortName'] ?? 'Humanitarian Databank',
      description: json['description'] ?? 'Humanitarian Databank Mobile Application',
      website: json['website'] ?? 'https://example.org',
      supportEmail: json['supportEmail'] ?? 'support@example.org',
      contactEmail: json['contactEmail'] ?? 'contact@example.org',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'name': name,
      'fullName': fullName,
      'shortName': shortName,
      'description': description,
      'website': website,
      'supportEmail': supportEmail,
      'contactEmail': contactEmail,
    };
  }
}

class BrandingInfo {
  final String primaryColor;
  final String secondaryColor;
  final String accentColor;
  final String navyColor;
  final String redColor;
  final String darkRedColor;
  final String logoPath;

  BrandingInfo({
    required this.primaryColor,
    required this.secondaryColor,
    required this.accentColor,
    required this.navyColor,
    required this.redColor,
    required this.darkRedColor,
    required this.logoPath,
  });

  factory BrandingInfo.fromJson(Map<String, dynamic> json) {
    return BrandingInfo(
      primaryColor: json['primaryColor'] ?? '#3B82F6',
      secondaryColor: json['secondaryColor'] ?? '#1E40AF',
      accentColor: json['accentColor'] ?? '#EF4444',
      navyColor: json['navyColor'] ?? '#011E41',
      redColor: json['redColor'] ?? '#C8102E',
      darkRedColor: json['darkRedColor'] ?? '#A50D25',
      logoPath: json['logoPath'] ?? 'assets/images/app_icon.png',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'primaryColor': primaryColor,
      'secondaryColor': secondaryColor,
      'accentColor': accentColor,
      'navyColor': navyColor,
      'redColor': redColor,
      'darkRedColor': darkRedColor,
      'logoPath': logoPath,
    };
  }

  /// Convert hex color string to int (for Flutter Color)
  int get primaryColorInt {
    return _hexToInt(primaryColor);
  }

  int get secondaryColorInt {
    return _hexToInt(secondaryColor);
  }

  int get accentColorInt {
    return _hexToInt(accentColor);
  }

  int get navyColorInt {
    return _hexToInt(navyColor);
  }

  int get redColorInt {
    return _hexToInt(redColor);
  }

  int get darkRedColorInt {
    return _hexToInt(darkRedColor);
  }

  int _hexToInt(String hex) {
    try {
      final cleanHex = hex.replaceFirst('#', '0xFF');
      return int.parse(cleanHex);
    } catch (e) {
      return 0xFF3B82F6; // Default blue
    }
  }
}

class AppInfo {
  final String name;
  final String packageName;
  final String displayName;
  final String description;

  AppInfo({
    required this.name,
    required this.packageName,
    required this.displayName,
    required this.description,
  });

  factory AppInfo.fromJson(Map<String, dynamic> json) {
    return AppInfo(
      name: json['name'] ?? 'Humanitarian Databank',
      packageName: json['packageName'] ?? 'com.hum.databank',
      displayName: json['displayName'] ?? 'Humanitarian Databank',
      description: json['description'] ?? 'Humanitarian Databank Mobile Application',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'name': name,
      'packageName': packageName,
      'displayName': displayName,
      'description': description,
    };
  }
}

class AzureInfo {
  final String b2cTenant;
  final String b2cPolicy;
  final String redirectScheme;

  AzureInfo({
    required this.b2cTenant,
    required this.b2cPolicy,
    required this.redirectScheme,
  });

  factory AzureInfo.fromJson(Map<String, dynamic> json) {
    return AzureInfo(
      b2cTenant: json['b2cTenant'] ?? '',
      b2cPolicy: json['b2cPolicy'] ?? '',
      redirectScheme: json['redirectScheme'] ?? 'humdatabank',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'b2cTenant': b2cTenant,
      'b2cPolicy': b2cPolicy,
      'redirectScheme': redirectScheme,
    };
  }
}

class FeaturesInfo {
  final bool showOrganizationName;
  final bool customBranding;

  FeaturesInfo({
    required this.showOrganizationName,
    required this.customBranding,
  });

  factory FeaturesInfo.fromJson(Map<String, dynamic> json) {
    return FeaturesInfo(
      showOrganizationName: json['showOrganizationName'] ?? true,
      customBranding: json['customBranding'] ?? false,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'showOrganizationName': showOrganizationName,
      'customBranding': customBranding,
    };
  }
}

/// Service to load and manage organization configuration
class OrganizationConfigService {
  static final OrganizationConfigService _instance =
      OrganizationConfigService._internal();
  factory OrganizationConfigService() => _instance;
  OrganizationConfigService._internal();

  OrganizationConfig? _config;
  bool _isInitialized = false;

  /// Get the current organization configuration
  OrganizationConfig get config {
    if (_config == null) {
      throw Exception(
          'OrganizationConfigService not initialized. Call loadConfig() first.');
    }
    return _config!;
  }

  /// Check if config is initialized
  bool get isInitialized => _isInitialized;

  /// Load organization configuration from JSON file
  ///
  /// Priority:
  /// 1. Check for organization-specific config (e.g., organization_config.ifrc.json)
  /// 2. Fall back to default organization_config.json
  ///
  /// Default organization profile is IFRC (`organization_config.ifrc.json`).
  /// Override with ORGANIZATION_CONFIG / `organization` parameter; empty string uses generic `organization_config.json`.
  Future<void> loadConfig({String? organization}) async {
    if (_isInitialized) {
      DebugLogger.logInfo('CONFIG', 'Config already loaded, skipping');
      return;
    }

    try {
      String configPath;

      // Determine which config file to load
      if (organization != null && organization.isNotEmpty) {
        configPath = 'assets/config/organization_config.$organization.json';
        DebugLogger.logInfo('CONFIG', 'Loading organization-specific config: $configPath');
      } else {
        // Try to get from environment variable (default: ifrc)
        const envOrg = String.fromEnvironment('ORGANIZATION_CONFIG', defaultValue: 'ifrc');
        if (envOrg.isNotEmpty) {
          configPath = 'assets/config/organization_config.$envOrg.json';
          DebugLogger.logInfo('CONFIG', 'Loading config from environment: $configPath');
        } else {
          // Explicit empty ORGANIZATION_CONFIG → generic Humanitarian Databank config
          configPath = 'assets/config/organization_config.json';
          DebugLogger.logInfo('CONFIG', 'Loading default config: $configPath');
        }
      }

      // Try to load the specified config file
      String jsonString;
      try {
        jsonString = await rootBundle.loadString(configPath);
      } catch (e) {
        // If organization-specific config not found, fall back to default
        if (configPath != 'assets/config/organization_config.json') {
          DebugLogger.logWarn('CONFIG',
              'Organization-specific config not found, falling back to default');
          configPath = 'assets/config/organization_config.json';
          jsonString = await rootBundle.loadString(configPath);
        } else {
          rethrow;
        }
      }

      final jsonData = json.decode(jsonString) as Map<String, dynamic>;
      _config = OrganizationConfig.fromJson(jsonData);
      _isInitialized = true;

      DebugLogger.logInfo('CONFIG',
          'Organization config loaded: ${_config!.organization.name}');
      DebugLogger.logInfo('CONFIG',
          'App name: ${_config!.app.name}');
    } catch (e, stackTrace) {
      DebugLogger.logError('Failed to load organization config: $e');
      DebugLogger.logError('Stack trace: $stackTrace');

      // Fall back to default hardcoded values
      _config = _getDefaultConfig();
      _isInitialized = true;
      DebugLogger.logWarn('CONFIG', 'Using default fallback configuration');
    }
  }

  /// Get default configuration (fallback)
  OrganizationConfig _getDefaultConfig() {
    return OrganizationConfig(
      organization: OrganizationInfo(
        name: 'Humanitarian Databank',
        fullName: 'Humanitarian Databank',
        shortName: 'Humanitarian Databank',
        description: 'Humanitarian Databank Mobile Application',
        website: 'https://example.org',
        supportEmail: 'support@example.org',
        contactEmail: 'contact@example.org',
      ),
      branding: BrandingInfo(
        primaryColor: '#3B82F6',
        secondaryColor: '#1E40AF',
        accentColor: '#EF4444',
        navyColor: '#011E41',
        redColor: '#C8102E',
        darkRedColor: '#A50D25',
        logoPath: 'assets/images/app_icon.png',
      ),
      app: AppInfo(
        name: 'Humanitarian Databank',
        packageName: 'com.hum.databank',
        displayName: 'Humanitarian Databank',
        description: 'Humanitarian Databank Mobile Application',
      ),
      azure: AzureInfo(
        b2cTenant: '',
        b2cPolicy: '',
        redirectScheme: 'humdatabank',
      ),
      features: FeaturesInfo(
        showOrganizationName: true,
        customBranding: false,
      ),
    );
  }

  /// Reload configuration (useful for testing or dynamic updates)
  Future<void> reloadConfig({String? organization}) async {
    _isInitialized = false;
    _config = null;
    await loadConfig(organization: organization);
  }
}
