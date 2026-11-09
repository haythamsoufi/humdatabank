import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:pdfrx/pdfrx.dart';
import 'package:share_plus/share_plus.dart';

import '../../config/app_config.dart';
import '../../services/jwt_token_service.dart';
import '../../services/local_pdf_thumbnail_generator.dart';
import '../../services/unified_planning_pdf_thumbnail_cache.dart';
import '../../utils/constants.dart';
import '../../utils/debug_logger.dart';
import '../../l10n/app_localizations.dart';
import '../../widgets/bottom_navigation_bar.dart';

class PdfViewerScreen extends StatefulWidget {
  /// Remote PDF URL (mutually exclusive with [localFilePath]).
  final String? url;

  /// Absolute path to a PDF already on disk (e.g. WebView session export).
  final String? localFilePath;

  /// When set with [url], first-page JPEG is generated after load and stored for
  /// [UnifiedPlanningPdfThumbnailCache] (e.g. same string as unified-planning document URL).
  final String? thumbnailCacheUrl;

  final String title;

  PdfViewerScreen({
    super.key,
    required this.title,
    this.url,
    this.localFilePath,
    this.thumbnailCacheUrl,
  }) : assert(
          (url != null && url.trim().isNotEmpty) ^
              (localFilePath != null && localFilePath.trim().isNotEmpty),
          'PdfViewerScreen: pass exactly one of url or localFilePath',
        );

  @override
  State<PdfViewerScreen> createState() => _PdfViewerScreenState();
}

class _PdfViewerScreenState extends State<PdfViewerScreen> {
  final PdfViewerController _pdfController = PdfViewerController();
  final TextEditingController _searchController = TextEditingController();
  final FocusNode _searchFocus = FocusNode();
  PdfTextSearcher? _textSearcher;
  Uint8List? _pdfBytes;
  bool _isDownloading = true;
  double _downloadProgress = 0;
  String? _error;
  int _currentPage = 1;
  int _totalPages = 0;
  bool _showControls = true;
  bool _isSharing = false;
  bool _searchOpen = false;

  @override
  void initState() {
    super.initState();
    _loadDocument();
  }

  @override
  void dispose() {
    _textSearcher?.removeListener(_onSearchChanged);
    _textSearcher?.dispose();
    _searchController.dispose();
    _searchFocus.dispose();
    super.dispose();
  }

  Future<void> _loadDocument() async {
    setState(() {
      _isDownloading = true;
      _downloadProgress = 0;
      _error = null;
    });

    try {
      if (widget.localFilePath != null && widget.localFilePath!.trim().isNotEmpty) {
        DebugLogger.logApi('PDF open: file ${widget.localFilePath}');
        final bytes = Uint8List.fromList(
          await File(widget.localFilePath!).readAsBytes(),
        );
        if (!mounted) return;
        _pdfBytes = bytes;
        setState(() {
          _isDownloading = false;
          _downloadProgress = 1.0;
        });
        return;
      }

      final client = http.Client();
      try {
        final sourceUrl = widget.url!;
        DebugLogger.logApi('PDF download: GET $sourceUrl');
        final request = http.Request('GET', Uri.parse(sourceUrl));
        // AI / authenticated document endpoints require the mobile JWT; public
        // resource URLs stay unauthenticated.
        final authHeaders = await _authHeadersForBackendUrl(sourceUrl);
        if (authHeaders.isNotEmpty) {
          request.headers.addAll(authHeaders);
        }
        final streamed = await client.send(request);

        DebugLogger.logApi('PDF response: HTTP ${streamed.statusCode}');
        if (streamed.statusCode != 200) {
          if (!mounted) return;
          throw Exception(
            AppLocalizations.of(context)!
                .pdfViewerDownloadFailedHttp(streamed.statusCode),
          );
        }

        final contentLength = streamed.contentLength ?? 0;
        final chunks = <int>[];

        await streamed.stream.listen((chunk) {
          chunks.addAll(chunk);
          if (contentLength > 0 && mounted) {
            setState(
                () => _downloadProgress = chunks.length / contentLength);
          }
        }).asFuture<void>();

        final bytes = Uint8List.fromList(chunks);
        if (!mounted) return;

        _pdfBytes = bytes;
        setState(() {
          _isDownloading = false;
          _downloadProgress = 1.0;
        });
        _scheduleUnifiedPlanningLocalThumbnail();
      } finally {
        client.close();
      }
    } catch (e) {
      DebugLogger.logErrorWithTag('PDF_VIEWER', 'Download error: $e');
      if (mounted) {
        setState(() {
          _isDownloading = false;
          _error = e.toString();
        });
      }
    }
  }

  /// Renders first page off-screen after the bytes are ready (separate [PdfDocument]).
  void _scheduleUnifiedPlanningLocalThumbnail() {
    if (kIsWeb) return;
    final key = widget.thumbnailCacheUrl?.trim();
    if (key == null || key.isEmpty) return;
    if (_pdfBytes == null) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      unawaited(_generateUnifiedPlanningThumbnail(key));
    });
  }

  Future<void> _generateUnifiedPlanningThumbnail(String cacheUrl) async {
    // Let the viewer finish opening the same bytes before a second document open.
    await Future<void>.delayed(const Duration(milliseconds: 400));
    final bytes = _pdfBytes;
    if (bytes == null || !mounted) return;
    try {
      final jpeg = await localPdfThumbnailFromPdfBytes(bytes);
      if (jpeg == null || !mounted) return;
      await UnifiedPlanningPdfThumbnailCache.instance.ingestLocalJpeg(cacheUrl, jpeg);
    } catch (e, st) {
      DebugLogger.logErrorWithTag(
        'PDF_VIEWER',
        'Local unified-planning thumbnail: $e\n$st',
      );
    }
  }

  /// Bearer token when [url] targets this app's backoffice host.
  Future<Map<String, String>> _authHeadersForBackendUrl(String url) async {
    try {
      final target = Uri.parse(url);
      final backend = Uri.parse(AppConfig.baseApiUrl);
      if (target.host.toLowerCase() != backend.host.toLowerCase()) {
        return const {};
      }
      final token = await JwtTokenService().getAccessToken();
      if (token == null || token.isEmpty) return const {};
      return {'Authorization': 'Bearer $token'};
    } catch (_) {
      return const {};
    }
  }

  Future<void> _shareDocument() async {
    if (_pdfBytes == null || _isSharing) return;
    final loc = AppLocalizations.of(context)!;
    setState(() => _isSharing = true);
    try {
      final dir = await getTemporaryDirectory();
      final safeName = widget.title
          .replaceAll(RegExp(r'[^\w\s\-]'), '')
          .trim()
          .replaceAll(RegExp(r'\s+'), '_');
      final file = File(
        '${dir.path}/${safeName.isEmpty ? loc.pdfViewerFilenameFallback : safeName}.pdf',
      );
      await file.writeAsBytes(_pdfBytes!);
      await Share.shareXFiles([XFile(file.path)], subject: widget.title);
    } catch (e) {
      DebugLogger.logWarn('PDF_VIEWER', 'Share failed: $e');
    } finally {
      if (mounted) setState(() => _isSharing = false);
    }
  }

  String get _pdfSourceName {
    final url = widget.url?.trim();
    if (url != null && url.isNotEmpty) return url;
    final path = widget.localFilePath?.trim();
    if (path != null && path.isNotEmpty) return path;
    return widget.title;
  }

  void _onSearchChanged() {
    if (mounted) setState(() {});
  }

  void _attachSearcher(PdfViewerController controller) {
    _textSearcher?.removeListener(_onSearchChanged);
    _textSearcher?.dispose();
    final searcher = PdfTextSearcher(controller)..addListener(_onSearchChanged);
    _textSearcher = searcher;
    final query = _searchController.text.trim();
    if (query.isNotEmpty) {
      searcher.startTextSearch(
        query,
        caseInsensitive: true,
        searchImmediately: true,
      );
    }
  }

  void _openSearch() {
    setState(() {
      _searchOpen = true;
      _showControls = true;
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _searchFocus.requestFocus();
    });
  }

  void _closeSearch() {
    _searchController.clear();
    _textSearcher?.resetTextSearch();
    _searchFocus.unfocus();
    setState(() => _searchOpen = false);
  }

  void _onSearchQueryChanged(String value) {
    final query = value.trim();
    final searcher = _textSearcher;
    if (searcher == null) return;
    if (query.isEmpty) {
      searcher.resetTextSearch();
      return;
    }
    searcher.startTextSearch(query, caseInsensitive: true);
  }

  Future<void> _goToMatch(int delta) async {
    final searcher = _textSearcher;
    if (searcher == null || searcher.matches.isEmpty) return;
    final count = searcher.matches.length;
    final current = searcher.currentIndex ?? (delta > 0 ? -1 : 0);
    final next = (current + delta) % count;
    final index = next < 0 ? next + count : next;
    await searcher.goToMatchOfIndex(index);
  }

  void _paintSearchMatches(Canvas canvas, Rect pageRect, PdfPage page) {
    _textSearcher?.pageTextMatchPaintCallback(canvas, pageRect, page);
  }

  void _onPdfPageChanged(int? pageNumber) {
    if (!mounted || pageNumber == null || pageNumber == _currentPage) return;
    setState(() => _currentPage = pageNumber);
  }

  void _onPdfViewerReady(PdfDocument document, PdfViewerController controller) {
    _attachSearcher(controller);
    if (!mounted) return;
    setState(() => _totalPages = document.pages.length);
  }

  bool _onPdfTap(
    BuildContext context,
    PdfViewerController controller,
    PdfViewerGeneralTapHandlerDetails details,
  ) {
    if (details.type == PdfViewerGeneralTapType.tap) {
      setState(() => _showControls = !_showControls);
    }
    return false;
  }

  // ── Build ──────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final ifrcRed = Color(AppConstants.ifrcRed);

    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        elevation: 0,
        scrolledUnderElevation: 0,
        iconTheme: const IconThemeData(color: Colors.white),
        actionsIconTheme: const IconThemeData(color: Colors.white),
        automaticallyImplyLeading: false,
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_rounded),
          tooltip: MaterialLocalizations.of(context).backButtonTooltip,
          color: Colors.white,
          onPressed: () {
            if (Navigator.of(context).canPop()) {
              Navigator.of(context).pop();
            }
          },
        ),
        leadingWidth: 56,
        title: Text(
          widget.title,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 16,
            fontWeight: FontWeight.w600,
          ),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        bottom: _searchOpen ? _buildSearchBar(loc) : null,
        actions: [
          if (!_isDownloading && _error == null && !_searchOpen)
            IconButton(
              icon: const Icon(Icons.search_rounded),
              tooltip: loc.pdfViewerSearch,
              onPressed: _openSearch,
            ),
          if (!_isDownloading && _error == null)
            _isSharing
                ? const Padding(
                    padding: EdgeInsets.all(14),
                    child: SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white54,
                      ),
                    ),
                  )
                : IconButton(
                    icon: const Icon(Icons.share_rounded),
                    tooltip: loc.actionShare,
                    onPressed: _shareDocument,
                  ),
        ],
      ),
      bottomNavigationBar: AppBottomNavigationBar(
        currentIndex: AppBottomNavigationBar.noTabSelected,
        backgroundColor: Colors.black.withValues(alpha: 0.52),
        lightForegroundOnBar: true,
      ),
      body: _isDownloading
          ? _buildDownloading(ifrcRed, theme, loc)
          : _error != null
              ? _buildError(ifrcRed, loc)
              : _buildPdf(ifrcRed),
    );
  }

  // ── Download progress ──────────────────────────────────────────────────────

  Widget _buildDownloading(Color accent, ThemeData theme, AppLocalizations loc) {
    final pct = (_downloadProgress * 100).toInt();
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          SizedBox(
            width: 72,
            height: 72,
            child: Stack(
              fit: StackFit.expand,
              children: [
                CircularProgressIndicator(
                  value: _downloadProgress > 0 ? _downloadProgress : null,
                  strokeWidth: 4,
                  backgroundColor: Colors.white12,
                  valueColor: AlwaysStoppedAnimation<Color>(accent),
                ),
                const Center(
                  child: Icon(
                    Icons.picture_as_pdf_rounded,
                    color: Colors.white54,
                    size: 30,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 20),
          Text(
            _downloadProgress > 0
                ? loc.pdfViewerDownloadingPercent(pct)
                : loc.pdfViewerConnecting,
            style: const TextStyle(
              color: Colors.white70,
              fontSize: 14,
            ),
          ),
        ],
      ),
    );
  }

  // ── Error state ────────────────────────────────────────────────────────────

  Widget _buildError(Color accent, AppLocalizations loc) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.broken_image_rounded,
                size: 64, color: Colors.white30),
            const SizedBox(height: 20),
            Text(
              loc.pdfViewerCouldNotLoad,
              style: const TextStyle(
                  color: Colors.white70,
                  fontSize: 16,
                  fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 8),
            Text(
              _error!,
              style: const TextStyle(color: Colors.white38, fontSize: 12),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 28),
            Wrap(
              alignment: WrapAlignment.center,
              spacing: 12,
              runSpacing: 10,
              children: [
                OutlinedButton.icon(
                  onPressed: _loadDocument,
                  icon: const Icon(Icons.refresh_rounded, size: 16),
                  label: Text(loc.retry),
                  style: OutlinedButton.styleFrom(
                    foregroundColor: accent,
                    side: BorderSide(color: accent),
                  ),
                ),
                if (_pdfBytes != null)
                  OutlinedButton.icon(
                    onPressed: _shareDocument,
                    icon: const Icon(Icons.share_rounded, size: 16),
                    label: Text(loc.actionShare),
                    style: OutlinedButton.styleFrom(
                      foregroundColor: Colors.white54,
                      side: const BorderSide(color: Colors.white24),
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  // ── PDF view ───────────────────────────────────────────────────────────────

  PreferredSizeWidget _buildSearchBar(AppLocalizations loc) {
    final searcher = _textSearcher;
    final canStep = searcher != null && searcher.matches.isNotEmpty;
    return PreferredSize(
      preferredSize: const Size.fromHeight(56),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 0, 4, 8),
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: _searchController,
                focusNode: _searchFocus,
                style: const TextStyle(color: Colors.white, fontSize: 15),
                cursorColor: Colors.white,
                textInputAction: TextInputAction.search,
                decoration: InputDecoration(
                  isDense: true,
                  hintText: loc.pdfViewerSearchHint,
                  hintStyle: const TextStyle(color: Colors.white38),
                  filled: true,
                  fillColor: Colors.white10,
                  contentPadding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(8),
                    borderSide: BorderSide.none,
                  ),
                ),
                onChanged: _onSearchQueryChanged,
                onSubmitted: (value) {
                  final query = value.trim();
                  if (query.isEmpty) return;
                  _textSearcher?.startTextSearch(
                    query,
                    caseInsensitive: true,
                    searchImmediately: true,
                  );
                },
              ),
            ),
            const SizedBox(width: 8),
            _searchStatus(loc),
            IconButton(
              tooltip: loc.pdfViewerSearchPrevious,
              onPressed: canStep ? () => _goToMatch(-1) : null,
              color: Colors.white,
              disabledColor: Colors.white24,
              icon: const Icon(Icons.keyboard_arrow_up_rounded),
            ),
            IconButton(
              tooltip: loc.pdfViewerSearchNext,
              onPressed: canStep ? () => _goToMatch(1) : null,
              color: Colors.white,
              disabledColor: Colors.white24,
              icon: const Icon(Icons.keyboard_arrow_down_rounded),
            ),
            IconButton(
              tooltip: loc.pdfViewerSearchClose,
              onPressed: _closeSearch,
              color: Colors.white,
              icon: const Icon(Icons.close_rounded),
            ),
          ],
        ),
      ),
    );
  }

  Widget _searchStatus(AppLocalizations loc) {
    final searcher = _textSearcher;
    final query = _searchController.text.trim();
    if (query.isEmpty || searcher == null) {
      return const SizedBox(width: 4);
    }
    if (searcher.matches.isEmpty) {
      if (searcher.isSearching) {
        return const SizedBox(
          width: 16,
          height: 16,
          child: CircularProgressIndicator(
            strokeWidth: 2,
            color: Colors.white54,
          ),
        );
      }
      return Text(
        loc.pdfViewerSearchNoMatches,
        style: const TextStyle(color: Colors.white54, fontSize: 12),
      );
    }
    final index = (searcher.currentIndex ?? 0) + 1;
    return Text(
      '$index/${searcher.matches.length}',
      style: const TextStyle(
        color: Colors.white70,
        fontSize: 12,
        fontWeight: FontWeight.w600,
      ),
    );
  }

  Widget _buildPdf(Color accent) {
    final bytes = _pdfBytes;
    if (bytes == null) return const SizedBox.shrink();
    return Stack(
      children: [
        PdfViewer.data(
          bytes,
          sourceName: _pdfSourceName,
          controller: _pdfController,
          params: PdfViewerParams(
            backgroundColor: Colors.black,
            margin: 8,
            pageDropShadow: null,
            matchTextColor: const Color(0x99FFEB3B),
            activeMatchTextColor: const Color(0xE6FF9800),
            pagePaintCallbacks: [_paintSearchMatches],
            onPageChanged: _onPdfPageChanged,
            onViewerReady: _onPdfViewerReady,
            onGeneralTap: _onPdfTap,
            loadingBannerBuilder: (_, _, _) => Center(
              child: CircularProgressIndicator(
                strokeWidth: 3,
                valueColor: AlwaysStoppedAnimation<Color>(accent),
              ),
            ),
            errorBannerBuilder: (_, error, _, _) => Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Text(
                  error.toString(),
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.white38, fontSize: 12),
                ),
              ),
            ),
          ),
        ),

        // Thin progress bar at top
        if (_totalPages > 0)
          Positioned(
            top: 0,
            left: 0,
            right: 0,
            child: LinearProgressIndicator(
              value: _totalPages > 0 ? _currentPage / _totalPages : 0,
              minHeight: 3,
              backgroundColor: Colors.white10,
              valueColor: AlwaysStoppedAnimation<Color>(accent),
            ),
          ),

        // Floating page pill at bottom
        if (_totalPages > 0)
          AnimatedPositioned(
            duration: const Duration(milliseconds: 250),
            curve: Curves.easeInOut,
            bottom: _showControls ? 24 : -48,
            left: 0,
            right: 0,
            child: Center(
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 8),
                decoration: BoxDecoration(
                  color: Colors.black.withValues(alpha: 0.60),
                  borderRadius: BorderRadius.circular(24),
                  border: Border.all(color: Colors.white12),
                ),
                child: Text(
                  '$_currentPage / $_totalPages',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    letterSpacing: 0.5,
                  ),
                ),
              ),
            ),
          ),
      ],
    );
  }
}

