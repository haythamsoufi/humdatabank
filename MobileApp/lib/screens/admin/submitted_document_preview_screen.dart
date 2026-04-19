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
  });

  final String title;
  final Uint8List bytes;
  final bool isImage;

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
                  _decodeAsUtf8(bytes),
                  style: theme.textTheme.bodyMedium?.copyWith(height: 1.45),
                ),
              ),
            ),
    );
  }

  static String _decodeAsUtf8(Uint8List bytes) {
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
    if (bytes.isEmpty) return false;
    final n = bytes.length < sample ? bytes.length : sample;
    var binaryLike = 0;
    for (var i = 0; i < n; i++) {
      final b = bytes[i];
      if (b == 0) return false;
      if (b < 0x09 || (b > 0x0D && b < 0x20 && b != 0x1B)) {
        binaryLike++;
      }
    }
    return binaryLike < n ~/ 32;
  }

  static bool shouldUseNativePreview(Uint8List bytes) =>
      bytesLookLikeImage(bytes) || bytesLookLikeText(bytes);
}
