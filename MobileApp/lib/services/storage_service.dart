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
}
