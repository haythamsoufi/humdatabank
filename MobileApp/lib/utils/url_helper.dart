import '../config/app_config.dart';
import '../providers/shared/language_provider.dart';

class UrlHelper {
  /// True for Flask/backoffice routes (not Next.js public pages).
  static bool isBackendPath(String path) {
    final normalized = path.startsWith('/') ? path : '/$path';
    final withoutLocale = stripLeadingLocaleSegment(normalized);
    return withoutLocale.startsWith('/forms/') ||
        withoutLocale.startsWith('/api/') ||
        withoutLocale.startsWith('/admin') ||
        withoutLocale.startsWith('/login') ||
        withoutLocale.startsWith('/logout');
  }

  /// Removes a leading 2-letter locale segment when it matches [LanguageProvider] codes.
  static String stripLeadingLocaleSegment(String path) {
    final segments = path.split('/').where((s) => s.isNotEmpty).toList();
    if (segments.isEmpty) {
      return path.startsWith('/') ? path : '/$path';
    }
    final codes =
        LanguageProvider.availableLanguages.map((l) => l['code']!).toList();
    if (segments[0].length == 2 && codes.contains(segments[0])) {
      return '/${segments.sublist(1).join('/')}';
    }
    return path.startsWith('/') ? path : '/$path';
  }

  static bool _matchesFrontendHost(Uri uri) {
    final frontend = Uri.parse(AppConfig.frontendUrl);
    if (uri.host == frontend.host && uri.port == frontend.port) return true;
    if (uri.host == 'localhost' && uri.port == 3000) return true;
    if (uri.host == '10.0.2.2' && uri.port == 3000) return true;
    if (uri.host == 'website-databank.fly.dev') return true;
    return false;
  }

  /// Resolves the URL to load in [WebViewScreen]: backoffice routes always use
  /// [AppConfig.backendUrl] (no `/en/` locale); Next.js pages get locale wrapping.
  static String resolveWebViewInitialUrl(String initial, String language) {
    final trimmed = initial.trim();
    if (trimmed.isEmpty) {
      return buildBackendUrl('/');
    }

    if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
      final uri = Uri.parse(trimmed);
      final pathOnly = uri.path;
      final withoutLocale = stripLeadingLocaleSegment(pathOnly);
      if (isBackendPath(withoutLocale)) {
        var pathWithQuery = withoutLocale;
        if (uri.hasQuery) {
          pathWithQuery = '$pathWithQuery?${uri.query}';
        }
        if (uri.hasFragment) {
          pathWithQuery = '$pathWithQuery#${uri.fragment}';
        }
        return buildBackendUrl(pathWithQuery);
      }
      if (_matchesFrontendHost(uri)) {
        return buildFrontendUrlWithLanguage(trimmed, language);
      }
      return trimmed;
    }

    if (trimmed.startsWith('/') && isBackendPath(trimmed)) {
      return buildBackendUrl(trimmed);
    }
    if (trimmed.startsWith('/')) {
      return buildFrontendUrlWithLanguage(trimmed, language);
    }
    return buildBackendUrl(trimmed);
  }

  /// Builds a frontend URL with the specified language locale
  /// Next.js i18n routing uses locale in the path: /en/, /es/, etc.
  static String buildFrontendUrlWithLanguage(String path, String language) {
    final baseUrl = AppConfig.frontendUrl;
    final uri = Uri.parse(baseUrl);

    // Parse the path to extract its segments
    final pathUri =
        Uri.parse(path.startsWith('http') ? path : '$baseUrl$path');
    final pathSegmentsFromPath = pathUri.pathSegments;

    // Remove empty segments
    final cleanPathSegments =
        pathSegmentsFromPath.where((s) => s.isNotEmpty).toList();

    // Check if first segment is a locale (2-letter code matching available languages)
    final availableCodes =
        LanguageProvider.availableLanguages.map((l) => l['code']!).toList();

    List<String> finalSegments;
    if (cleanPathSegments.isNotEmpty &&
        cleanPathSegments[0].length == 2 &&
        availableCodes.contains(cleanPathSegments[0])) {
      // Replace existing locale
      finalSegments = [language, ...cleanPathSegments.sublist(1)];
    } else {
      // Add locale at the beginning
      finalSegments = [language, ...cleanPathSegments];
    }

    // Ensure trailing slash for Next.js routing
    final newPath = '/${finalSegments.join('/')}';
    final finalPath = newPath.endsWith('/') ? newPath : '$newPath/';

    return uri.replace(path: finalPath).toString();
  }

  /// Builds a backend URL (doesn't need language, but kept for consistency)
  static String buildBackendUrl(String path) {
    if (path.startsWith('http://') || path.startsWith('https://')) {
      return path;
    }
    return '${AppConfig.backendUrl}$path';
  }
}
