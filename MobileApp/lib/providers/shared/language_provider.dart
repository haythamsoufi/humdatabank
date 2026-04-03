import 'package:flutter/foundation.dart';
import '../../services/storage_service.dart';

class LanguageProvider with ChangeNotifier {
  final StorageService _storage = StorageService();

  static const String _languageKey = 'selected_language';
  static const String _defaultLanguage = 'en';

  String _currentLanguage = _defaultLanguage;
  bool _isLoading = false;

  String get currentLanguage => _currentLanguage;
  bool get isLoading => _isLoading;

  // Available languages matching the frontend LanguageSwitcher
  static const List<Map<String, String>> availableLanguages = [
    {'code': 'en', 'name': 'English', 'display': 'EN'},
    {'code': 'es', 'name': 'Español', 'display': 'ES'},
    {'code': 'fr', 'name': 'Français', 'display': 'FR'},
    {'code': 'ar', 'name': 'العربية', 'display': 'AR'},
    {'code': 'hi', 'name': 'हिन्दी', 'display': 'HI'},
    {'code': 'ru', 'name': 'Русский', 'display': 'RU'},
    {'code': 'zh', 'name': '中文', 'display': 'ZH'},
  ];

  LanguageProvider() {
    _loadLanguage();
  }

  Future<void> _loadLanguage() async {
    _isLoading = true;
    notifyListeners();

    try {
      final savedLanguage = await _storage.getString(_languageKey);
      if (savedLanguage != null && savedLanguage.isNotEmpty) {
        // Validate that the saved language is in our available languages
        final isValid =
            availableLanguages.any((lang) => lang['code'] == savedLanguage);
        if (isValid) {
          _currentLanguage = savedLanguage;
        } else {
          _currentLanguage = _defaultLanguage;
        }
      } else {
        _currentLanguage = _defaultLanguage;
      }
    } catch (e) {
      // On error, use default language
      _currentLanguage = _defaultLanguage;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> setLanguage(String languageCode) async {
    // Validate language code
    final isValid =
        availableLanguages.any((lang) => lang['code'] == languageCode);
    if (!isValid) {
      return;
    }

    if (_currentLanguage == languageCode) {
      return; // No change needed
    }

    try {
      await _storage.setString(_languageKey, languageCode);
      _currentLanguage = languageCode;
      notifyListeners();
    } catch (e) {
      // Handle error silently or log it
      debugPrint('Error saving language preference: $e');
    }
  }

  String getLanguageName(String code) {
    final language = availableLanguages.firstWhere(
      (lang) => lang['code'] == code,
      orElse: () => availableLanguages[0],
    );
    return language['name'] ?? 'English';
  }

  String getLanguageDisplay(String code) {
    final language = availableLanguages.firstWhere(
      (lang) => lang['code'] == code,
      orElse: () => availableLanguages[0],
    );
    return language['display'] ?? 'EN';
  }
}
