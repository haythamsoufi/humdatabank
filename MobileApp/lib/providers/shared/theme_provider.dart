import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import '../../services/storage_service.dart';

class ThemeProvider with ChangeNotifier {
  final StorageService _storage = StorageService();

  static const String _themeModeKey = 'theme_mode';
  static const String _defaultThemeMode =
      'system'; // 'light', 'dark', or 'system'

  String _currentThemeMode = _defaultThemeMode;
  bool _isLoading = false;

  String get currentThemeMode => _currentThemeMode;
  bool get isLoading => _isLoading;
  bool get isDarkMode => _currentThemeMode == 'dark';

  ThemeProvider() {
    _loadThemeMode();
  }

  Future<void> _loadThemeMode() async {
    _isLoading = true;
    notifyListeners();

    try {
      final savedThemeMode = await _storage.getString(_themeModeKey);
      if (savedThemeMode != null &&
          (savedThemeMode == 'light' ||
              savedThemeMode == 'dark' ||
              savedThemeMode == 'system')) {
        _currentThemeMode = savedThemeMode;
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
      await _storage.setString(_themeModeKey, themeMode);
      _currentThemeMode = themeMode;
      notifyListeners();
    } catch (e) {
      // Handle error silently or log it
      debugPrint('Error saving theme mode preference: $e');
    }
  }

  Future<void> toggleThemeMode() async {
    final newMode = _currentThemeMode == 'light' ? 'dark' : 'light';
    await setThemeMode(newMode);
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
