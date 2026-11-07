import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/widgets/network_logo_image.dart';

void main() {
  group('isSvgLogoUrl', () {
    test('detects svg with cache-busting query', () {
      expect(
        isSvgLogoUrl('https://cdn.example/static/system/sectors/health.svg?v=123'),
        isTrue,
      );
    });

    test('is case-insensitive', () {
      expect(isSvgLogoUrl('https://host/api/v1/uploads/sectors/WASH.SVG'), isTrue);
    });

    test('treats raster logos as non-svg', () {
      expect(isSvgLogoUrl('https://host/api/v1/uploads/sectors/health.png'), isFalse);
      expect(isSvgLogoUrl('https://host/a.png?file=x.svg'), isFalse);
    });
  });
}
