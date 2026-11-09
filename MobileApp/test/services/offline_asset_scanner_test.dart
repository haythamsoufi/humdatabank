import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/services/offline/offline_asset_scanner.dart';

void main() {
  final page = Uri.parse('http://localhost:5000/forms/assignment/1');

  Set<String> refs(String html) =>
      OfflineAssetScanner.collectStaticRefsFromRawHtml(
        html,
        page,
      ).map((u) => u.path).toSet();

  test('finds root static files', () {
    expect(refs('<script>load("/static/js/app.js?v=1")</script>'), {
      '/static/js/app.js',
    });
  });

  test('finds upr files without treating them as /static/', () {
    expect(
      refs(
        '<link href="/upr/static/css/upr.css?v=2">'
        '<link href="/upr/fonts.css?v=9">'
        '<script src="/plugins/static/a/b.js"></script>',
      ),
      {'/upr/static/css/upr.css', '/upr/fonts.css', '/plugins/static/a/b.js'},
    );
  });

  test(
    'demotes /upr/ links so a file:// page does not request file:///upr',
    () {
      final html = OfflineAssetScanner.demoteHtmlRootStaticPaths(
        '<link href="/upr/fonts.css?v=9">'
        '<script src="/upr/static/js/upr-shared.js"></script>',
      );
      final stripped = OfflineAssetScanner.stripStaticUrlCacheQuery(html);
      expect(stripped, contains('href="upr/fonts.css"'));
      expect(stripped, contains('src="upr/static/js/upr-shared.js"'));
      expect(stripped, isNot(contains('"/upr/')));
    },
  );

  test('rewrites font urls inside upr/fonts.css relative to that file', () {
    final css = OfflineAssetScanner.rewriteCssRootStaticUrls(
      "@font-face { src: url('/static/fonts/OpenSans-Regular.ttf'); }",
      'upr/fonts.css',
    );
    expect(css, contains("url('../static/fonts/OpenSans-Regular.ttf')"));
  });

  test(
    'import map addresses stay document-relative inside scopes',
    () {
      const html = '''
<script type="importmap" nonce="abc">{"imports":{"http://localhost:5000/static/js/forms/main.js":"static/js/forms/main.js?v=1"},"scopes":{"http://localhost:5000/static/js/forms/":{"http://localhost:5000/static/js/forms/modules/ajax-save.js":"http://localhost:5000/static/js/forms/modules/ajax-save.js?v=2"},"http://localhost:5000/static/js/chatbot/":{"http://localhost:5000/static/js/lib/waf-json-body.js":"http://localhost:5000/static/js/lib/waf-json-body.js?v=3"}}}</script>
''';
      final out = OfflineAssetScanner.rewriteImportMapsForFileUrl(html);
      final start = out.indexOf('>') + 1;
      final body = out.substring(start, out.lastIndexOf('</script>'));
      final map = jsonDecode(body) as Map<String, dynamic>;
      final imports = map['imports'] as Map<String, dynamic>;
      expect(imports['./static/js/forms/main.js'], './static/js/forms/main.js');
      final scopes = map['scopes'] as Map<String, dynamic>;
      final forms = scopes['./static/js/forms/'] as Map<String, dynamic>;
      expect(
        forms['./static/js/forms/modules/ajax-save.js'],
        './static/js/forms/modules/ajax-save.js',
      );
      final chatbot = scopes['./static/js/chatbot/'] as Map<String, dynamic>;
      expect(
        chatbot['./static/js/lib/waf-json-body.js'],
        './static/js/lib/waf-json-body.js',
      );
      expect(out, isNot(contains('Bare')));
      expect(out, contains('nonce="abc"'));
    },
  );
}
