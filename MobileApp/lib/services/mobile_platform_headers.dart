import 'dart:io';

import 'package:device_info_plus/device_info_plus.dart';

/// Cached `X-Platform` / `X-OS-Version` for mobile API requests (shared by
/// [ApiService] and [DioClient]).
class MobilePlatformHeaders {
  MobilePlatformHeaders._();

  static Map<String, String> _headers = {};
  static bool _initialized = false;

  static Future<void> ensureInitialized() async {
    if (_initialized) return;
    try {
      final platform =
          Platform.isIOS ? 'ios' : (Platform.isAndroid ? 'android' : 'unknown');
      String osVersion = 'unknown';
      final deviceInfo = DeviceInfoPlugin();
      if (Platform.isIOS) {
        final info = await deviceInfo.iosInfo;
        osVersion = 'iOS ${info.systemVersion}';
      } else if (Platform.isAndroid) {
        final info = await deviceInfo.androidInfo;
        osVersion = 'Android ${info.version.release}';
      }
      _headers = {
        'X-Platform': platform,
        'X-OS-Version': osVersion,
      };
    } catch (_) {
      _headers = {
        'X-Platform':
            Platform.isIOS ? 'ios' : (Platform.isAndroid ? 'android' : 'unknown'),
      };
    }
    _initialized = true;
  }

  static Map<String, String> get map => Map<String, String>.from(_headers);
}
