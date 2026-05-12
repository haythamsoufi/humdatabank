import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../config/app_config.dart';

class StorageService {
  static final StorageService _instance = StorageService._internal();
  factory StorageService() => _instance;

  late final FlutterSecureStorage _secureStorage;

  StorageService._internal() {
    // Use an environment-scoped Keychain service name (kSecAttrService on iOS,
    // SharedPreferences file name on Android) so that prod, staging, and dev
    // installs on the same device never read or overwrite each other's tokens.
    //
    // flutter_secure_storage defaults kSecAttrService to the fixed string
    // 'flutter_secure_storage_service' for all Flutter apps, meaning two apps
    // that share the same key names (and the same Keychain access scope) will
    // silently overwrite each other — causing one app to log out the other.
    // Setting a distinct accountName per environment prevents this entirely.
    final String keychainService = AppConfig.isStaging
        ? 'flutter_secure_storage_service.staging'
        : AppConfig.isDemo
            ? 'flutter_secure_storage_service.demo'
            : AppConfig.isDevelopment
                ? 'flutter_secure_storage_service.dev'
                : 'flutter_secure_storage_service';

    _secureStorage = FlutterSecureStorage(
      iOptions: IOSOptions(accountName: keychainService),
      aOptions: AndroidOptions(
        sharedPreferencesName: keychainService,
      ),
    );
  }
  SharedPreferences? _prefs;

  Future<void> init() async {
    _prefs ??= await SharedPreferences.getInstance();
  }

  // Secure Storage Methods
  Future<void> setSecure(String key, String value) async {
    await _secureStorage.write(key: key, value: value);
  }

  Future<String?> getSecure(String key) async {
    return await _secureStorage.read(key: key);
  }

  Future<void> deleteSecure(String key) async {
    await _secureStorage.delete(key: key);
  }

  Future<void> clearSecure() async {
    await _secureStorage.deleteAll();
  }

  // SharedPreferences Methods
  Future<void> setString(String key, String value) async {
    await init();
    await _prefs!.setString(key, value);
  }

  Future<String?> getString(String key) async {
    await init();
    return _prefs!.getString(key);
  }

  Future<void> setBool(String key, bool value) async {
    await init();
    await _prefs!.setBool(key, value);
  }

  Future<bool?> getBool(String key) async {
    await init();
    return _prefs!.getBool(key);
  }

  Future<void> setInt(String key, int value) async {
    await init();
    await _prefs!.setInt(key, value);
  }

  Future<int?> getInt(String key) async {
    await init();
    return _prefs!.getInt(key);
  }

  Future<void> remove(String key) async {
    await init();
    await _prefs!.remove(key);
  }

  Future<void> clear() async {
    await init();
    await _prefs!.clear();
  }

  /// Clear every SharedPreferences entry **except** [keepKeys].
  ///
  /// Used by [AuthService.logout] so that user-level UI/UX preferences
  /// (theme, language, etc.) survive a logout while everything else
  /// (cached profiles, session metadata, per-account caches) is wiped.
  /// Plain [clear] is dangerous on logout: it deletes the user's theme,
  /// language, and any new pref ever added in the future.
  Future<void> clearPrefsExcept(Iterable<String> keepKeys) async {
    await init();
    final keepSet = keepKeys.toSet();

    // Snapshot survivors before deleting.
    final preserved = <String, Object?>{};
    for (final key in keepSet) {
      if (!_prefs!.containsKey(key)) continue;
      preserved[key] = _prefs!.get(key);
    }

    await _prefs!.clear();

    for (final entry in preserved.entries) {
      final value = entry.value;
      if (value is String) {
        await _prefs!.setString(entry.key, value);
      } else if (value is bool) {
        await _prefs!.setBool(entry.key, value);
      } else if (value is int) {
        await _prefs!.setInt(entry.key, value);
      } else if (value is double) {
        await _prefs!.setDouble(entry.key, value);
      } else if (value is List) {
        // SharedPreferences only persists List<String>; cast defensively.
        await _prefs!.setStringList(
          entry.key,
          value.map((e) => e?.toString() ?? '').toList(),
        );
      }
    }
  }

  /// Clear every secure-storage entry **except** [keepKeys].
  ///
  /// Used by [AuthService.logout] to keep the persistent device-install ID
  /// (and any other long-lived non-auth secret) without the brittle
  /// "read → clear → write" dance that previously dropped the device ID
  /// whenever the Keychain read transiently failed.
  Future<void> clearSecureExcept(Iterable<String> keepKeys) async {
    final keepSet = keepKeys.toSet();

    // Snapshot the survivors first. If any individual read fails (e.g.
    // transient Keychain unavailability right after device unlock) we
    // log and continue — losing one survivor is far better than losing
    // every secret.
    final preserved = <String, String>{};
    for (final key in keepSet) {
      try {
        final value = await _secureStorage.read(key: key);
        if (value != null) preserved[key] = value;
      } catch (_) {
        // Best-effort: skip this survivor.
      }
    }

    try {
      await _secureStorage.deleteAll();
    } catch (_) {
      // If deleteAll fails the best we can do is fall back to deleting
      // each non-preserved key we currently know about.  Callers should
      // verify auth state is gone before re-issuing tokens.
      try {
        final all = await _secureStorage.readAll();
        for (final key in all.keys) {
          if (keepSet.contains(key)) continue;
          try {
            await _secureStorage.delete(key: key);
          } catch (_) {}
        }
      } catch (_) {}
    }

    for (final entry in preserved.entries) {
      try {
        await _secureStorage.write(key: entry.key, value: entry.value);
      } catch (_) {
        // If we fail to restore a survivor we have to live with it; the
        // alternative — refusing to log the user out — is worse.
      }
    }
  }
}
