import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/services/offline/offline_asset_scanner.dart';

void main() {
  final page = Uri.parse('http://localhost:5000/forms/assignment/1');

  Set<String> refs(String html) => OfflineAssetScanner.collectStaticRefsFromRawHtml(
    html,
    page,
  ).map((u) => u.path).toSet();

  test('finds root static files', () {
    expect(
      refs('<script>load("/static/js/app.js?v=1")</script>'),
      {'/static/js/app.js'},
    );
  });

  test('does not invent /static/ files from plugin static URLs', () {
    expect(
      refs(
        '<link href="/upr/static/css/upr.css?v=2">'
        '<script src="/plugins/static/a/b.js"></script>',
      ),
      {'/plugins/static/a/b.js'},
    );
  });
}
