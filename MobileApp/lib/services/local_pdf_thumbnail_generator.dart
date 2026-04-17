import 'dart:typed_data';

import 'package:pdfx/pdfx.dart';

import '../utils/debug_logger.dart';

/// Renders the first PDF page to JPEG using pdfx (native platforms).
///
/// Not used on web from callers that guard with `kIsWeb`; JPEG path may be
/// limited on web in pdfx. Default [maxWidth] keeps output within the unified
/// thumbnail cache byte cap.
Future<Uint8List?> localPdfThumbnailFromPdfBytes(
  Uint8List pdfBytes, {
  double maxWidth = 360,
}) async {
  if (pdfBytes.isEmpty) return null;
  PdfDocument? doc;
  PdfPage? page;
  try {
    doc = await PdfDocument.openData(pdfBytes);
    if (doc.pagesCount < 1) return null;
    page = await doc.getPage(1);
    final w = page.width;
    final h = page.height;
    if (w <= 0 || h <= 0) return null;
    final scale = maxWidth / w;
    final outW = maxWidth;
    final outH = h * scale;
    final img = await page.render(
      width: outW,
      height: outH,
      format: PdfPageImageFormat.jpeg,
      backgroundColor: '#FFFFFF',
      quality: 80,
    );
    final bytes = img?.bytes;
    if (bytes == null || bytes.isEmpty) return null;
    return bytes;
  } catch (e, st) {
    DebugLogger.logErrorWithTag('PDF_THUMB_LOCAL', '$e\n$st');
    return null;
  } finally {
    try {
      await page?.close();
    } catch (_) {}
    try {
      await doc?.close();
    } catch (_) {}
  }
}
