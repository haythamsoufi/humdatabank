import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import '../../widgets/app_bar.dart';

/// In-app preview for non-PDF bytes (text, images) fetched via the mobile API.
class SubmittedDocumentPreviewScreen extends StatelessWidget {
  const SubmittedDocumentPreviewScreen({
    super.key,
    required this.title,
    required this.bytes,
    required this.isImage,
    this.fileName,
  });

  final String title;
  final Uint8List bytes;
  final bool isImage;

  /// Optional hint for decoding (e.g. `.txt` when bytes lack a clear UTF-8 shape).
  final String? fileName;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppAppBar(title: title),
      body: isImage
          ? Center(
              child: InteractiveViewer(
                minScale: 0.5,
                maxScale: 4,
                child: Image.memory(
                  bytes,
                  fit: BoxFit.contain,
                  errorBuilder: (_, _, _) => Padding(
                    padding: const EdgeInsets.all(24),
                    child: Text(
                      'Could not display this image.',
                      style: theme.textTheme.bodyLarge,
                      textAlign: TextAlign.center,
                    ),
                  ),
                ),
              ),
            )
          : SelectableRegion(
              selectionControls: MaterialTextSelectionControls(),
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(16),
                child: SelectableText(
                  _decodePlainText(bytes, fileName: fileName),
                  style: theme.textTheme.bodyMedium?.copyWith(height: 1.45),
                ),
              ),
            ),
    );
  }

  static String _decodeUtf16Units(Uint8List bytes, Endian endian) {
    if (bytes.isEmpty) return '';
    if (bytes.length.isOdd) {
      return utf8.decode(bytes, allowMalformed: true);
    }
    final bd = ByteData.sublistView(bytes);
    final units = <int>[];
    for (var i = 0; i + 1 < bytes.length; i += 2) {
      units.add(bd.getUint16(i, endian));
    }
    return String.fromCharCodes(units);
  }

  /// UTF-8 / UTF-16 (with BOM) and best-effort UTF-8 for plain-text preview.
  static String _decodePlainText(Uint8List bytes, {String? fileName}) {
    if (bytes.isEmpty) return '';
    // UTF-8 BOM
    if (bytes.length >= 3 &&
        bytes[0] == 0xEF &&
        bytes[1] == 0xBB &&
        bytes[2] == 0xBF) {
      return utf8.decode(bytes.sublist(3), allowMalformed: true);
    }
    // UTF-16 LE BOM
    if (bytes.length >= 2 && bytes[0] == 0xFF && bytes[1] == 0xFE) {
      return _decodeUtf16Units(bytes.sublist(2), Endian.little);
    }
    // UTF-16 BE BOM
    if (bytes.length >= 2 && bytes[0] == 0xFE && bytes[1] == 0xFF) {
      return _decodeUtf16Units(bytes.sublist(2), Endian.big);
    }
    // UTF-16 LE without BOM (common for Windows "Unicode" .txt): (ASCII, 0) pairs.
    if (_fileNameLooksLikePlainText(fileName) &&
        _looksLikeUtf16LeWithoutBom(bytes)) {
      return _decodeUtf16Units(bytes, Endian.little);
    }
    try {
      return utf8.decode(bytes, allowMalformed: true);
    } catch (_) {
      return String.fromCharCodes(bytes);
    }
  }

  /// JPEG / PNG / GIF / WebP magic bytes.
  static bool bytesLookLikeImage(Uint8List bytes) {
    if (bytes.length < 12) return false;
    if (bytes[0] == 0xFF && bytes[1] == 0xD8 && bytes[2] == 0xFF) return true;
    if (bytes.length >= 8 &&
        bytes[0] == 0x89 &&
        bytes[1] == 0x50 &&
        bytes[2] == 0x4E &&
        bytes[3] == 0x47) {
      return true;
    }
    if (bytes.length >= 6 &&
        bytes[0] == 0x47 &&
        bytes[1] == 0x49 &&
        bytes[2] == 0x46 &&
        bytes[3] == 0x38) {
      return true;
    }
    if (bytes.length >= 12 &&
        bytes[0] == 0x52 &&
        bytes[1] == 0x49 &&
        bytes[2] == 0x46 &&
        bytes[3] == 0x46) {
      return true;
    }
    return false;
  }

  static bool bytesLookLikeText(Uint8List bytes, {int sample = 4096}) {
    // Empty file: still show an in-app text preview (WebView admin URL needs cookies).
    if (bytes.isEmpty) return true;
    // UTF-16 (with BOM) is not "single-byte text" but we must preview in-app, not WebView.
    if (bytes.length >= 2 && bytes[0] == 0xFF && bytes[1] == 0xFE) return true;
    if (bytes.length >= 2 && bytes[0] == 0xFE && bytes[1] == 0xFF) return true;
    final n = bytes.length < sample ? bytes.length : sample;
    var binaryLike = 0;
    for (var i = 0; i < n; i++) {
      final b = bytes[i];
      if (b == 0) return false;
      if (b < 0x09 || (b > 0x0D && b < 0x20 && b != 0x1B)) {
        binaryLike++;
      }
    }
    // `binaryLike < n ~/ 32` is wrong for n < 32 (threshold becomes 0). Use ratio.
    return binaryLike * 32 < n;
  }

  static bool _looksLikeUtf16LeWithoutBom(Uint8List bytes) {
    if (bytes.length < 4 || bytes.length.isOdd) return false;
    final limit = bytes.length < 400 ? bytes.length : 400;
    var asciiPairs = 0;
    var pairs = 0;
    for (var i = 0; i + 1 < limit; i += 2) {
      pairs++;
      final lo = bytes[i];
      final hi = bytes[i + 1];
      if (hi == 0 && lo < 0x80) asciiPairs++;
    }
    return pairs > 0 && asciiPairs * 2 >= pairs;
  }

  static bool _fileNameLooksLikePlainText(String? fileName) {
    if (fileName == null || fileName.isEmpty) return false;
    final dot = fileName.lastIndexOf('.');
    if (dot < 0 || dot == fileName.length - 1) return false;
    final ext = fileName.substring(dot + 1).toLowerCase();
    const plain = <String>{
      'txt',
      'text',
      'md',
      'csv',
      'tsv',
      'log',
      'json',
      'xml',
      'yaml',
      'yml',
      'ini',
      'cfg',
      'conf',
    };
    return plain.contains(ext);
  }

  static bool shouldUseNativePreview(Uint8List bytes, {String? fileName}) =>
      bytesLookLikeImage(bytes) ||
      bytesLookLikeText(bytes) ||
      _fileNameLooksLikePlainText(fileName);
}
