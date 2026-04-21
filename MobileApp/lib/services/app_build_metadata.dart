import 'package:package_info_plus/package_info_plus.dart';

/// Package version from [PackageInfo], loaded once for headers (e.g. `X-App-Version`).
class AppBuildMetadata {
  AppBuildMetadata._();

  static PackageInfo? _info;
  static bool _initialized = false;

  /// Loads [PackageInfo.fromPlatform] once. Safe to call multiple times.
  static Future<void> ensureInitialized() async {
    if (_initialized) return;
    _initialized = true;
    try {
      _info = await PackageInfo.fromPlatform();
    } catch (_) {
      _info = null;
    }
  }

  /// Semver from pubspec (e.g. `1.2.3`), or `0.0.0` if unavailable.
  static String get appVersionSemver => _info?.version ?? '0.0.0';

  static String? get buildNumber => _info?.buildNumber;
}
