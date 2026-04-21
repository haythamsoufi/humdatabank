import 'package:flutter/foundation.dart';
import '../../services/storage_service.dart';
import '../../utils/arabic_text_font.dart';

class LanguageProvider with ChangeNotifier {
  final StorageService _storage = StorageService();

  static const String _languageKey = 'selected_language';
  static const String _defaultLanguage = 'en';
  static const String _arabicTextFontKey = 'arabic_text_font';

  String _currentLanguage = _defaultLanguage;
  ArabicTextFontPreference _arabicTextFont = ArabicTextFontPreference.tajawal;
  bool _isLoading = false;

  String get currentLanguage => _currentLanguage;
  bool get isLoading => _isLoading;

  /// Arabic script font when UI language is Arabic (Tajawal or platform UI font).
  /// Ignored for non-Arabic locales.
  ArabicTextFontPreference get arabicTextFontPreference => _arabicTextFont;

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

      final savedArabicFont = await _storage.getString(_arabicTextFontKey);
      if (savedArabicFont == 'system') {
        _arabicTextFont = ArabicTextFontPreference.system;
      } else {
        _arabicTextFont = ArabicTextFontPreference.tajawal;
      }
    } catch (e) {
      // On error, use default language
      _currentLanguage = _defaultLanguage;
      _arabicTextFont = ArabicTextFontPreference.tajawal;
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

  Future<void> setArabicTextFontPreference(ArabicTextFontPreference value) async {
    if (_arabicTextFont == value) {
      return;
    }
    try {
      await _storage.setString(
        _arabicTextFontKey,
        value == ArabicTextFontPreference.system ? 'system' : 'tajawal',
      );
      _arabicTextFont = value;
      notifyListeners();
    } catch (e) {
      debugPrint('Error saving Arabic text font preference: $e');
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
