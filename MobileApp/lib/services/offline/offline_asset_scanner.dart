import 'dart:convert';
import 'dart:io';

import 'package:html/dom.dart' show Document;
import 'package:path/path.dart' as p;

import '../offline_form_scripts.dart';

/// Pure helpers that decide which files an entry form needs and rewrite saved
/// markup, styles and scripts so they resolve from `file://`.
///
/// Nothing here touches the disk or the network, so the functions are cheap to
/// unit test and safe to run in a background isolate.
class OfflineAssetScanner {
  OfflineAssetScanner._();

  /// POSIX paths only (URLs in HTML/CSS use forward slashes).
  static final p.Context _posix = p.Context(style: p.Style.posix);

  static const Set<String> externalMirrorExtensions = {
    '.js',
    '.mjs',
    '.css',
    '.woff',
    '.woff2',
    '.ttf',
    '.otf',
    '.eot',
    '.svg',
    '.png',
    '.jpg',
    '.jpeg',
    '.gif',
    '.webp',
    '.ico',
  };

  static const List<String> externalSkipHosts = [
    'google-analytics.com',
    'googletagmanager.com',
    'doubleclick.net',
    'sentry.io',
    'hotjar.com',
    'clarity.ms',
  ];

  static const String externalDirName = 'static/ext';

  static bool isSameOrigin(Uri asset, Uri pageUri) =>
      asset.host == pageUri.host && asset.port == pageUri.port;

  /// Third-party styles, scripts and fonts the form needs (CDN libraries, web
  /// fonts). Pages and API endpoints are never mirrored.
  static bool isMirrorableExternal(Uri asset) {
    final host = asset.host.toLowerCase();
    if (host.isEmpty) return false;
    for (final skip in externalSkipHosts) {
      if (host == skip || host.endsWith('.$skip')) return false;
    }
    if (host == 'www.gstatic.com' && asset.path.startsWith('/charts/')) {
      return false;
    }
    if (host == 'fonts.googleapis.com' && asset.path.startsWith('/css')) {
      return true;
    }
    final ext = p.extension(asset.path).toLowerCase();
    return externalMirrorExtensions.contains(ext);
  }

  static bool shouldMirror(Uri asset, Uri pageUri) {
    if (!asset.hasScheme ||
        (asset.scheme != 'http' && asset.scheme != 'https')) {
      return false;
    }
    if (!isSameOrigin(asset, pageUri)) {
      return isMirrorableExternal(asset);
    }
    return isBundledPath(asset.path);
  }

  static bool isBundledPath(String path) =>
      path.startsWith('/static/') || path.startsWith('/plugins/static/');

  /// Stable on-disk path for a third-party file, kept under its host so relative
  /// references inside CDN stylesheets keep resolving.
  static String externalRelativePath(Uri absolute) {
    final host = absolute.hasPort
        ? '${absolute.host}_${absolute.port}'
        : absolute.host;
    var path = absolute.path;
    if (path.isEmpty || path.endsWith('/')) path = '${path}index';
    var ext = p.extension(path);
    if (ext.isEmpty && absolute.host == 'fonts.googleapis.com') ext = '.css';
    final base = p.extension(path).isEmpty
        ? path
        : path.substring(0, path.length - p.extension(path).length);
    var queryTag = '';
    if (absolute.hasQuery) {
      var h = 5381;
      for (final c in absolute.query.codeUnits) {
        h = ((h * 33) ^ c) & 0xFFFFFFFF;
      }
      queryTag = '.${h.toRadixString(36)}';
    }
    final safe = '$base$queryTag$ext'.replaceAll(
      RegExp(r'[^a-zA-Z0-9._/@-]'),
      '_',
    );
    return '$externalDirName/$host${safe.startsWith('/') ? safe : '/$safe'}';
  }

  static String relativePathForUrl(
    Uri absolute,
    Uri pageUri, {
    bool foldCacheQueryIntoFileName = true,
  }) {
    var path = absolute.path;
    if (path.startsWith('/')) path = path.substring(1);
    if (path.isEmpty) path = 'asset.bin';
    if (foldCacheQueryIntoFileName && absolute.hasQuery) {
      final ext = p.extension(path);
      final baseName = ext.isNotEmpty
          ? path.substring(0, path.length - ext.length)
          : path;
      final safeQ = absolute.query.replaceAll(RegExp(r'[^a-zA-Z0-9._-]'), '_');
      final short = safeQ.length > 40 ? safeQ.substring(0, 40) : safeQ;
      path = ext.isNotEmpty ? '$baseName.$short$ext' : '${baseName}_$short';
    }
    return path;
  }

  /// Strip `?v=…` cache busters from `static/…` URLs so `file://` requests match on-disk names.
  static String stripStaticUrlCacheQuery(String html) {
    return html.replaceAllMapped(
      RegExp(
        r'(static/[\w./-]+\.(?:css|js|mjs|svg|woff2?|map))\?[^">\s\x27\)]*',
        caseSensitive: false,
      ),
      (m) => m[1]!,
    );
  }

  static Set<Uri> collectAssetRefs(Document doc, Uri pageUri) {
    final out = <Uri>{};
    void addRaw(String? raw) {
      if (raw == null) return;
      final t = raw.trim();
      if (t.isEmpty) return;
      if (t.startsWith('data:') ||
          t.startsWith('javascript:') ||
          t.startsWith('mailto:') ||
          t == '#') {
        return;
      }
      try {
        if (t.startsWith('//')) {
          out.add(Uri.parse('${pageUri.scheme}:$t'));
        } else {
          out.add(pageUri.resolve(t));
        }
      } catch (_) {}
    }

    for (final n in doc.querySelectorAll('script[src]')) {
      addRaw(n.attributes['src']);
    }
    for (final n in doc.querySelectorAll('link[href]')) {
      addRaw(n.attributes['href']);
    }
    for (final n in doc.querySelectorAll('img[src]')) {
      addRaw(n.attributes['src']);
    }
    for (final n in doc.querySelectorAll('source[src]')) {
      addRaw(n.attributes['src']);
    }
    return out;
  }

  /// Picks up `/static/...` URLs embedded in inline scripts (e.g. `static_url(...)` output),
  /// which are not present on `script[src]` / `link[href]` nodes.
  static Set<Uri> collectStaticRefsFromRawHtml(String html, Uri pageUri) {
    final out = <Uri>{};
    final origin =
        '${pageUri.scheme}://${pageUri.host}'
        '${pageUri.hasPort ? ':${pageUri.port}' : ''}';
    final ext =
        r'(?:js|mjs|css|svg|woff2?|ttf|eot|otf|map|json|ico|wasm|webp|png|jpg|jpeg|gif)';
    final tail = r'/static/[\w./-]+\.' + ext + r'(?:\?[^\s\x22\x27<>]*)?';

    try {
      final absRe = RegExp(RegExp.escape(origin) + tail, caseSensitive: false);
      for (final m in absRe.allMatches(html)) {
        out.add(Uri.parse(m.group(0)!));
      }
    } catch (_) {}

    try {
      final relRe = RegExp(r'(?<!/plugins)' + tail, caseSensitive: false);
      for (final m in relRe.allMatches(html)) {
        out.add(pageUri.resolve(m.group(0)!));
      }
    } catch (_) {}

    // Plugin field modules/styles (/plugins/static/…) are named in the page's
    // data-entry-form-config JSON and are imported at runtime.
    try {
      final pluginRe = RegExp(
        r'/plugins/static/[\w./-]+\.' + ext,
        caseSensitive: false,
      );
      for (final m in pluginRe.allMatches(html)) {
        out.add(pageUri.resolve(m.group(0)!));
      }
    } catch (_) {}

    return out;
  }

  /// Resolves `url(...)` / `@import` references from CSS text (webfonts, nested CSS).
  static Set<Uri> urlsFromCss(String css, Uri cssLocation) {
    final out = <Uri>{};
    void addRaw(String? raw) {
      if (raw == null) return;
      var t = raw.trim();
      if (t.isEmpty ||
          t.startsWith('data:') ||
          t.startsWith('javascript:') ||
          t == '#') {
        return;
      }
      final hash = t.indexOf('#');
      if (hash != -1) t = t.substring(0, hash);
      try {
        if (t.startsWith('//')) {
          out.add(Uri.parse('${cssLocation.scheme}:$t'));
        } else {
          out.add(cssLocation.resolve(t));
        }
      } catch (_) {}
    }

    for (final m in RegExp(
      r'url\(\s*([\x22\x27])([^\x22\x27]+)\1\s*\)',
      caseSensitive: false,
    ).allMatches(css)) {
      addRaw(m.group(2));
    }
    for (final m in RegExp(
      r'url\(\s*((?:\.\./|\./|/|https?:)[^)\s\x22\x27]+)\s*\)',
      caseSensitive: false,
    ).allMatches(css)) {
      addRaw(m.group(1));
    }
    for (final m in RegExp(
      r'@import\s+([\x22\x27])([^\x22\x27]+)\1',
      caseSensitive: false,
    ).allMatches(css)) {
      addRaw(m.group(2));
    }
    return out;
  }

  static final RegExp jsStaticLiteral = RegExp(
    r'''(["'`])(/(?:plugins/)?static/[\w./@-]*)\1''',
  );

  /// `'/static/…'` / `'/plugins/static/…'` string literals in plugin scripts
  /// (e.g. vendor libraries added with `script.src = …` at runtime).
  static Set<Uri> staticLiteralsFromJavaScript(String js, Uri jsLocation) {
    final out = <Uri>{};
    for (final m in jsStaticLiteral.allMatches(js)) {
      final path = m.group(2)!;
      if (!RegExp(r'\.[A-Za-z0-9]{2,5}$').hasMatch(path)) continue;
      try {
        out.add(jsLocation.resolve(path));
      } catch (_) {}
    }
    return out;
  }

  /// `file://` has no site root, so root-absolute asset paths inside saved
  /// scripts must be made relative: module specifiers (which resolve against the
  /// importing file) and, for plugin scripts, other string literals (which
  /// resolve against the page).
  static String rewriteRootStaticInJs(String js, String fileRelPosix) {
    final fromDir = _posix.dirname(fileRelPosix);
    final isPlugin = fileRelPosix.startsWith('plugins/static/');

    String fileRelative(String rootPath) {
      var q = rootPath.indexOf('?');
      final hash = rootPath.indexOf('#');
      if (hash != -1 && (q == -1 || hash < q)) q = hash;
      final pathOnly = q == -1 ? rootPath : rootPath.substring(0, q);
      final suffix = q == -1 ? '' : rootPath.substring(q);
      var rel = _posix.relative(pathOnly.substring(1), from: fromDir);
      if (!rel.startsWith('.')) rel = './$rel';
      return '$rel$suffix';
    }

    var out = js.replaceAllMapped(
      RegExp(
        r'''(\bfrom\s*|\bimport\s*\(\s*|\bimport\s+)(["'])(/(?:plugins/)?static/[^"'\s]+)\2''',
      ),
      (m) => '${m[1]}${m[2]}${fileRelative(m[3]!)}${m[2]}',
    );
    if (isPlugin) {
      out = out.replaceAllMapped(
        jsStaticLiteral,
        (m) => '${m[1]}${m[2]!.substring(1)}${m[1]}',
      );
    }
    return out;
  }

  /// Static `import` / `export … from` specifiers in JS modules (not visible in HTML).
  static Set<Uri> urlsFromJavaScript(String js, Uri jsLocation) {
    final out = <Uri>{};
    void addSpec(String? spec) {
      if (spec == null) return;
      var s = spec.trim();
      if (s.isEmpty || s.startsWith('data:')) return;
      if (!s.startsWith('./') &&
          !s.startsWith('../') &&
          !s.startsWith('/static/') &&
          !s.startsWith('/plugins/static/')) {
        return;
      }
      final hash = s.indexOf('#');
      if (hash != -1) s = s.substring(0, hash);
      final q = s.indexOf('?');
      if (q != -1) s = s.substring(0, q);
      try {
        if (s.startsWith('//')) {
          out.add(Uri.parse('${jsLocation.scheme}:$s'));
        } else {
          out.add(jsLocation.resolve(s));
        }
      } catch (_) {}
    }

    // import … from "…" / '…'
    for (final m in RegExp(
      r'from\s+"(\./[^"]+|\.\./[^"]+|/(?:plugins/)?static/[^"]+)"',
      caseSensitive: false,
    ).allMatches(js)) {
      addSpec(m.group(1));
    }
    for (final m in RegExp(
      r"from\s+'(\./[^']+|\.\./[^']+|/(?:plugins/)?static/[^']+)'",
      caseSensitive: false,
    ).allMatches(js)) {
      addSpec(m.group(1));
    }
    // import "…" / '…' (side-effect)
    for (final m in RegExp(
      r'import\s+"(\./[^"]+|\.\./[^"]+|/(?:plugins/)?static/[^"]+)"',
      caseSensitive: false,
    ).allMatches(js)) {
      addSpec(m.group(1));
    }
    for (final m in RegExp(
      r"import\s+'(\./[^']+|\.\./[^']+|/(?:plugins/)?static/[^']+)'",
      caseSensitive: false,
    ).allMatches(js)) {
      addSpec(m.group(1));
    }
    // import("…") / import('…')
    for (final m in RegExp(
      r'import\s*\(\s*"(\./[^"]+|\.\./[^"]+|/(?:plugins/)?static/[^"]+)"\s*\)',
      caseSensitive: false,
    ).allMatches(js)) {
      addSpec(m.group(1));
    }
    for (final m in RegExp(
      r"import\s*\(\s*'(\./[^']+|\.\./[^']+|/(?:plugins/)?static/[^']+)'\s*\)",
      caseSensitive: false,
    ).allMatches(js)) {
      addSpec(m.group(1));
    }
    return out;
  }

  /// Extra URL strings to rewrite to the on-disk path (query folded into filename).
  static void registerMirrorRewriteKeys(
    Uri absolute,
    String relPosix,
    Map<String, String> map,
  ) {
    if (!absolute.path.startsWith('/static/')) return;
    final rel = relPosix;
    final pathWithQuery = absolute.hasQuery
        ? '${absolute.path}?${absolute.query}'
        : absolute.path;
    map[pathWithQuery] = rel;

    final tail = absolute.path.startsWith('/static/')
        ? absolute.path.substring('/static/'.length)
        : absolute.path.substring(1);
    final demoted = 'static/$tail';
    if (absolute.hasQuery) {
      map['$demoted?${absolute.query}'] = rel;
    }
    map[demoted] = rel;
  }

  /// Root-relative `/static/` resolves to `file:///static/...` in Android WebView
  /// with a `file://` base URL. Demote to bundle-relative `static/...`.
  static String demoteHtmlRootStaticPaths(String html) {
    var s = html;
    s = s.replaceAllMapped(
      RegExp(
        r'\b(href|src|data-src|data-href|poster)\s*=\s*([\x22\x27])/static/',
        caseSensitive: true,
      ),
      (m) => '${m[1]}=${m[2]}static/',
    );
    s = s.replaceAllMapped(
      RegExp(
        r'\b(href|src)\s*=\s*([\x22\x27])/plugins/static/',
        caseSensitive: true,
      ),
      (m) => '${m[1]}=${m[2]}plugins/static/',
    );
    s = s.replaceAllMapped(
      RegExp(
        r'(<script\b[^>]*\btype\s*=\s*[\x22\x27]module[\x22\x27][^>]*>)([\s\S]*?)(</script>)',
        caseSensitive: false,
      ),
      (m) =>
          '${m[1]}${m[2]!.replaceAll('"/plugins/static/', '"./plugins/static/').replaceAll("'/plugins/static/", "'./plugins/static/")}${m[3]}',
    );
    s = s.replaceAll('url(/static/', 'url(static/');
    s = s.replaceAll('url("/static/', 'url("static/');
    s = s.replaceAll("url('/static/", "url('static/");
    s = s.replaceAll('@import "/static/', '@import "static/');
    s = s.replaceAll("@import '/static/", "@import 'static/");
    // Inline scripts often build URLs with quoted root-relative paths.
    s = s.replaceAll('"/static/', '"static/');
    s = s.replaceAll("'/static/", "'static/");
    s = s.replaceAll('`/static/', '`static/');
    return s;
  }

  /// Rewrites `url(/static/...)` / quoted variants / `@import` to paths relative
  /// to the CSS file (POSIX), so `file://` offline bundles resolve assets correctly.
  static String rewriteCssRootStaticUrls(String css, String fileRelPosix) {
    final relNorm = fileRelPosix.replaceAll(r'\', '/');
    final fromDir = relNorm == '.' || relNorm.isEmpty
        ? '.'
        : _posix.dirname(relNorm);

    String resolveTargetToUrl(String absStaticPath) {
      final target = absStaticPath.startsWith('/')
          ? absStaticPath.substring(1)
          : absStaticPath;
      if (!target.startsWith('static/')) {
        return absStaticPath;
      }
      var cut = target.length;
      final q = target.indexOf('?');
      final h = target.indexOf('#');
      if (q != -1) cut = q;
      if (h != -1 && h < cut) cut = h;
      final pathOnly = target.substring(0, cut);
      final suffix = cut < target.length ? target.substring(cut) : '';
      try {
        var relUrl = fromDir == '.' || fromDir.isEmpty
            ? pathOnly
            : _posix.relative(pathOnly, from: fromDir);
        relUrl = relUrl.replaceAll(r'\', '/');
        return '$relUrl$suffix';
      } catch (_) {
        return absStaticPath;
      }
    }

    var out = css.replaceAllMapped(
      RegExp(
        r'url\(\s*([\x22\x27])(/static/[^\x22\x27]+)\1\s*\)',
        caseSensitive: false,
      ),
      (m) {
        final quote = m[1]!;
        final path = m[2]!;
        final rel = resolveTargetToUrl(path);
        return 'url($quote$rel$quote)';
      },
    );

    out = out.replaceAllMapped(
      RegExp(r'url\(\s*(/static/[^)\s]+)\s*\)', caseSensitive: false),
      (m) {
        final path = m[1]!;
        final rel = resolveTargetToUrl(path);
        return 'url($rel)';
      },
    );

    out = out.replaceAllMapped(
      RegExp(
        r'@import\s+([\x22\x27])(/static/[^\x22\x27]+)\1',
        caseSensitive: false,
      ),
      (m) {
        final quote = m[1]!;
        final path = m[2]!;
        final rel = resolveTargetToUrl(path);
        return '@import $quote$rel$quote';
      },
    );

    return out;
  }

  /// Rewrites occurrences of mirrored absolute URLs to relative paths.
  static String rewriteHtmlAssetRefs(
    String html,
    Map<String, String> savedRelByAbsolute,
  ) {
    var s = html;
    final keys = savedRelByAbsolute.keys.toList()
      ..sort((a, b) => b.length.compareTo(a.length));
    for (final abs in keys) {
      final rel = savedRelByAbsolute[abs]!;
      final uri = Uri.parse(abs);
      final withoutQuery = Uri(
        scheme: uri.scheme,
        userInfo: uri.userInfo,
        host: uri.host,
        port: uri.port,
        path: uri.path,
      ).toString();
      final candidates = <String>{abs};
      if (!uri.hasQuery || uri.path.startsWith('/static/')) {
        candidates.add(withoutQuery);
      }
      for (final c in List<String>.of(candidates)) {
        final i = c.indexOf('//');
        if (i != -1) candidates.add(c.substring(i));
      }
      for (final candidate in candidates) {
        s = s.split(candidate).join(rel);
        for (final esc in <String>{
          const HtmlEscape().convert(candidate),
          const HtmlEscape(HtmlEscapeMode.attribute).convert(candidate),
        }) {
          if (esc != candidate) s = s.split(esc).join(rel);
        }
      }
    }
    return s;
  }

  /// Adds the offline runtime (API replay, online-only actions, static URL stub).
  static String injectOfflineHead(String html, String submitBlockedMessage) {
    final patch = buildOfflineHeadPatch(
      submitBlockedMessage: submitBlockedMessage,
    );
    final lower = html.toLowerCase();
    final idx = lower.indexOf('</head>');
    final withHead = idx != -1
        ? html.substring(0, idx) + patch + html.substring(idx)
        : patch + html;
    final bodyEnd = withHead.toLowerCase().lastIndexOf('</body>');
    if (bodyEnd == -1) return withHead + kOfflinePluginPathsScript;
    return withHead.substring(0, bodyEnd) +
        kOfflinePluginPathsScript +
        withHead.substring(bodyEnd);
  }

  static bool pathLooksLikeCss(String path) {
    final lower = path.toLowerCase();
    return lower.endsWith('.css') ||
        lower.contains('output.css') ||
        lower.contains('.css?');
  }

  /// Font Awesome (and similar) reference optional files that are often absent on disk.
  static bool mirrorSkipIsBenign404(Uri u, int statusCode) {
    if (statusCode != 404) return false;
    final lower = u.path.toLowerCase();
    if (lower.contains('fa-v4compatibility')) return true;
    return false;
  }
}

/// Input for [rewriteSavedFilesSync].
class OfflineRewriteJob {
  const OfflineRewriteJob({
    required this.dirPath,
    required this.relPaths,
    this.mirroredExternal = const {},
  });

  /// Package directory the files live in.
  final String dirPath;

  /// Package-relative POSIX paths of the files to rewrite.
  final List<String> relPaths;

  /// Absolute third-party URL -> package-relative path of its saved copy.
  final Map<String, String> mirroredExternal;
}

/// Makes freshly saved stylesheets and scripts work from `file://` (root
/// absolute `/static/` paths, third-party URLs). Synchronous and self-contained
/// so it can run in a background isolate. Returns the number of files changed.
int rewriteSavedFilesSync(OfflineRewriteJob job) {
  final posix = p.Context(style: p.Style.posix);
  final externalKeys = job.mirroredExternal.keys.toList()
    ..sort((a, b) => b.length.compareTo(a.length));
  var changed = 0;

  for (final rel in job.relPaths) {
    final lower = rel.toLowerCase();
    final isCss = lower.endsWith('.css');
    final isJs = lower.endsWith('.js') || lower.endsWith('.mjs');
    if (!isCss && !isJs) continue;
    if (isJs && rel.startsWith('${OfflineAssetScanner.externalDirName}/')) {
      continue;
    }
    final file = File(p.join(job.dirPath, rel));
    final String raw;
    try {
      raw = file.readAsStringSync(encoding: utf8);
    } catch (_) {
      continue;
    }

    var next = raw;
    if (isCss) {
      next = OfflineAssetScanner.rewriteCssRootStaticUrls(next, rel);
      next = OfflineAssetScanner.stripStaticUrlCacheQuery(next);
      final fromDir = posix.dirname(rel);
      for (final abs in externalKeys) {
        final schemeless = abs.substring(abs.indexOf('//'));
        if (!next.contains(abs) && !next.contains(schemeless)) continue;
        final target = posix.relative(
          job.mirroredExternal[abs]!,
          from: fromDir,
        );
        next = next.split(abs).join(target).split(schemeless).join(target);
      }
    } else if (raw.contains('/static/')) {
      next = OfflineAssetScanner.rewriteRootStaticInJs(next, rel);
    }

    if (next != raw) {
      file.writeAsStringSync(next);
      changed++;
    }
  }
  return changed;
}
