import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:pdfx/pdfx.dart';
import 'package:share_plus/share_plus.dart';

import '../../services/local_pdf_thumbnail_generator.dart';
import '../../services/unified_planning_pdf_thumbnail_cache.dart';
import '../../utils/constants.dart';
import '../../utils/debug_logger.dart';
import '../../l10n/app_localizations.dart';
import '../../utils/navigation_helper.dart';
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
  PdfController? _controller;
  Uint8List? _pdfBytes;
  bool _isDownloading = true;
  double _downloadProgress = 0;
  String? _error;
  int _currentPage = 1;
  int _totalPages = 0;
  bool _showControls = true;
  bool _isSharing = false;

  @override
  void initState() {
    super.initState();
    _loadDocument();
  }

  @override
  void dispose() {
    _controller?.dispose();
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
        _controller = PdfController(
          document: PdfDocument.openData(bytes),
        );
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
        _controller = PdfController(
          document: PdfDocument.openData(bytes),
        );
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

  /// Renders first page off-screen after the viewer’s document is ready (separate [PdfDocument]).
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
    // Let [PdfController] / platform renderer initialize before a second openData.
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
        actions: [
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
        onTap: (index) =>
            NavigationHelper.popToMainThenOpenAiIfNeeded(context, index),
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

  Widget _buildPdf(Color accent) {
    return Stack(
      children: [
        // Main PDF viewer
        GestureDetector(
          onTap: () => setState(() => _showControls = !_showControls),
          child: PdfView(
            controller: _controller!,
            scrollDirection: Axis.vertical,
            onDocumentLoaded: (doc) {
              setState(() => _totalPages = doc.pagesCount);
            },
            onPageChanged: (page) {
              setState(() => _currentPage = page);
            },
            builders: PdfViewBuilders<DefaultBuilderOptions>(
              options: const DefaultBuilderOptions(),
              documentLoaderBuilder: (_) => Center(
                child: CircularProgressIndicator(
                  strokeWidth: 3,
                  valueColor: AlwaysStoppedAnimation<Color>(accent),
                ),
              ),
              pageLoaderBuilder: (_) => Center(
                child: CircularProgressIndicator(
                  strokeWidth: 2,
                  valueColor:
                      AlwaysStoppedAnimation<Color>(accent.withValues(alpha: 0.6)),
                ),
              ),
              errorBuilder: (_, err) => Center(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.warning_rounded,
                        color: Colors.white38, size: 40),
                    const SizedBox(height: 8),
                    Text(err.toString(),
                        style: const TextStyle(
                            color: Colors.white38, fontSize: 12)),
                  ],
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

