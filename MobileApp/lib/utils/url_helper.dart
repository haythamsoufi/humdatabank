import '../config/app_config.dart';
import '../providers/shared/language_provider.dart';

class UrlHelper {
  /// Builds a frontend URL with the specified language locale
  /// Next.js i18n routing uses locale in the path: /en/, /es/, etc.
  static String buildFrontendUrlWithLanguage(String path, String language) {
    final baseUrl = AppConfig.frontendUrl;
    final uri = Uri.parse(baseUrl);
    final pathSegments = List<String>.from(uri.pathSegments);

    // Parse the path to extract its segments
    final pathUri =
        Uri.parse(path.startsWith('http') ? path : '${baseUrl}$path');
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
    final newPath = '/' + finalSegments.join('/');
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
