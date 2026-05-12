import 'package:flutter/material.dart';
import '../../config/app_config.dart';
import '../../services/storage_service.dart';

class ThemeProvider with ChangeNotifier {
  ThemeProvider({String? initialMode}) {
    if (initialMode != null && _isValidSavedMode(initialMode)) {
      _currentThemeMode = initialMode;
      _isLoading = false;
    } else {
      _loadThemeMode();
    }
  }

  final StorageService _storage = StorageService();
  static const String _defaultThemeMode =
      'system'; // 'light', 'dark', or 'system'

  String _currentThemeMode = _defaultThemeMode;
  bool _isLoading = false;

  static bool _isValidSavedMode(String? value) =>
      value == 'light' || value == 'dark' || value == 'system';

  /// Read saved theme from [StorageService] after [StorageService.init] and
  /// [migrateLegacySharedPreferencesKeys] so the first [MaterialApp] frame
  /// matches the user preference (avoids a one-frame flash of [ThemeMode.system]).
  static Future<String> loadInitialModeFromStorage(StorageService storage) async {
    try {
      final saved = await storage.getString(AppConfig.themeModeKey);
      if (_isValidSavedMode(saved)) return saved!;
    } catch (_) {}
    return _defaultThemeMode;
  }

  String get currentThemeMode => _currentThemeMode;
  bool get isLoading => _isLoading;

  /// User chose **Dark** in settings (not whether the UI is dark — use
  /// `Theme.of(context).brightness` or `context.isDarkTheme` for that).
  bool get isExplicitDarkMode => _currentThemeMode == 'dark';

  /// User chose **Light** in settings.
  bool get isExplicitLightMode => _currentThemeMode == 'light';

  /// User chose **System** default.
  bool get followsSystemTheme => _currentThemeMode == 'system';

  /// Deprecated: use [isExplicitDarkMode]. Same meaning as before (saved
  /// preference is dark, not whether the UI is currently dark).
  @Deprecated('Use isExplicitDarkMode')
  bool get isDarkMode => isExplicitDarkMode;

  Future<void> _loadThemeMode() async {
    _isLoading = true;
    notifyListeners();

    try {
      final savedThemeMode = await _storage.getString(AppConfig.themeModeKey);
      if (_isValidSavedMode(savedThemeMode)) {
        _currentThemeMode = savedThemeMode!;
      } else {
        _currentThemeMode = _defaultThemeMode;
      }
    } catch (e) {
      // On error, use default theme mode
      _currentThemeMode = _defaultThemeMode;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> setThemeMode(String themeMode) async {
    // Validate theme mode
    if (themeMode != 'light' && themeMode != 'dark' && themeMode != 'system') {
      return;
    }

    if (_currentThemeMode == themeMode) {
      return; // No change needed
    }

    try {
      await _storage.setString(AppConfig.themeModeKey, themeMode);
      _currentThemeMode = themeMode;
      notifyListeners();
    } catch (e) {
      // Handle error silently or log it
      debugPrint('Error saving theme mode preference: $e');
    }
  }

  /// Cycles **Light → Dark → System → Light** so system preference is not ignored.
  Future<void> toggleThemeMode() async {
    final next = switch (_currentThemeMode) {
      'light' => 'dark',
      'dark' => 'system',
      'system' => 'light',
      _ => 'light',
    };
    await setThemeMode(next);
  }

  // Helper to get ThemeMode enum value for MaterialApp
  ThemeMode get themeMode {
    switch (_currentThemeMode) {
      case 'dark':
        return ThemeMode.dark;
      case 'light':
        return ThemeMode.light;
      case 'system':
      default:
        return ThemeMode.system;
    }
  }
}
