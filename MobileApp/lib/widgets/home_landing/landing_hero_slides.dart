/// Bundled landing hero slideshow assets (`assets/images/hero/`).
///
/// Replace files or paths to customize; keep [assetPaths] non-empty for a photo
/// background, or set to `[]` to use gradient-only fallback in [LandingHeroSliver].
abstract final class LandingHeroSlides {
  LandingHeroSlides._();

  static const List<String> assetPaths = [
    'assets/images/hero/slide_01.jpg',
    'assets/images/hero/slide_02.jpg',
    'assets/images/hero/slide_03.jpg',
  ];

  static const Duration defaultInterval = Duration(seconds: 5);
}
