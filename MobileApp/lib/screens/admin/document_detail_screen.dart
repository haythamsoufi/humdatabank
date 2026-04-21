import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import '../../config/app_config.dart';
import '../../config/routes.dart';
import '../../di/service_locator.dart';
import '../../l10n/app_localizations.dart';
import '../../models/shared/document.dart';
import '../../services/api_service.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../utils/admin_screen_view_logging_mixin.dart';
import '../../widgets/app_bar.dart';
import 'submitted_document_preview_screen.dart';

bool _bytesLookLikePdf(List<int> bytes) =>
    bytes.length >= 5 &&
    bytes[0] == 0x25 &&
    bytes[1] == 0x50 &&
    bytes[2] == 0x44 &&
    bytes[3] == 0x46 &&
    bytes[4] == 0x2d;

String _safePreviewFileName(Document document) {
  final raw = document.fileName ?? 'document_${document.id}.pdf';
  final cleaned = raw.replaceAll(RegExp(r'[<>:"/\\|?*\x00-\x1f]'), '_').trim();
  if (cleaned.isEmpty) return 'document_${document.id}.pdf';
  return cleaned;
}

Future<void> openSubmittedDocumentPreview(
  BuildContext context,
  Document document,
) async {
  final loc = AppLocalizations.of(context)!;
  final messenger = ScaffoldMessenger.maybeOf(context);
  final nav = Navigator.of(context);

  var dialogShown = false;
  void closeDialog() {
    if (!dialogShown) return;
    dialogShown = false;
    if (context.mounted) {
      final rootNav = Navigator.of(context, rootNavigator: true);
      if (rootNav.canPop()) {
        rootNav.pop();
      }
    }
  }

  showDialog<void>(
    context: context,
    useRootNavigator: true,
    barrierDismissible: false,
    builder: (ctx) => PopScope(
      canPop: false,
      child: AlertDialog(
        content: Row(
          children: [
            CircularProgressIndicator(
              color: Color(AppConstants.ifrcRed),
            ),
            const SizedBox(width: 20),
            Expanded(child: Text(loc.pdfViewerConnecting)),
          ],
        ),
      ),
    ),
  );
  dialogShown = true;

  try {
    final api = sl<ApiService>();
    final endpoint =
        '${AppConfig.mobileDocumentsEndpoint}/${document.id}/file';
    final response = await api.get(
      endpoint,
      useCache: false,
      additionalHeaders: const {'Accept': '*/*'},
    );

    closeDialog();

    if (!context.mounted) return;

    if (response.statusCode != 200) {
      messenger?.showSnackBar(
        SnackBar(content: Text(loc.pdfViewerDownloadFailedHttp(response.statusCode))),
      );
      return;
    }

    final bytes = response.bodyBytes;
    if (!_bytesLookLikePdf(bytes)) {
      final u8 = Uint8List.fromList(bytes);
      if (SubmittedDocumentPreviewScreen.shouldUseNativePreview(
            u8,
            fileName: document.fileName,
          )) {
        if (!context.mounted) return;
        await nav.push<void>(
          MaterialPageRoute<void>(
            settings: RouteSettings(
              name: '${AppRoutes.documentDetail(document.id)}/preview-native',
            ),
            builder: (ctx) => SubmittedDocumentPreviewScreen(
              title: document.fileName ?? loc.previewDocument,
              bytes: u8,
              isImage: SubmittedDocumentPreviewScreen.bytesLookLikeImage(u8),
              fileName: document.fileName,
            ),
          ),
        );
        return;
      }
      await nav.pushNamed(
        AppRoutes.webview,
        arguments: '/admin/documents/serve/${document.id}',
      );
      return;
    }

    final dir = await getTemporaryDirectory();
    final file = File(
      '${dir.path}/admin_doc_preview_${document.id}_${_safePreviewFileName(document)}',
    );
    await file.writeAsBytes(bytes, flush: true);

    if (!context.mounted) return;

    await nav.pushNamed(
      AppRoutes.pdfViewer,
      arguments: <String, String>{
        'filePath': file.path,
        'title': document.fileName ?? loc.previewDocument,
      },
    );
  } on AuthenticationException catch (e) {
    closeDialog();
    if (context.mounted) {
      messenger?.showSnackBar(SnackBar(content: Text(e.message)));
    }
  } catch (e) {
    closeDialog();
    if (context.mounted) {
      messenger?.showSnackBar(
        SnackBar(content: Text(loc.pdfViewerCouldNotLoad)),
      );
    }
  }
}

Future<void> downloadSubmittedDocument(
  BuildContext context,
  Document document,
) async {
  final loc = AppLocalizations.of(context)!;
  final messenger = ScaffoldMessenger.maybeOf(context);

  var dialogShown = false;
  void closeDialog() {
    if (!dialogShown) return;
    dialogShown = false;
    if (context.mounted) {
      final rootNav = Navigator.of(context, rootNavigator: true);
      if (rootNav.canPop()) {
        rootNav.pop();
      }
    }
  }

  showDialog<void>(
    context: context,
    useRootNavigator: true,
    barrierDismissible: false,
    builder: (ctx) => PopScope(
      canPop: false,
      child: AlertDialog(
        content: Row(
          children: [
            CircularProgressIndicator(
              color: Color(AppConstants.ifrcRed),
            ),
            const SizedBox(width: 20),
            Expanded(
              child: Text('${loc.downloadDocument}…'),
            ),
          ],
        ),
      ),
    ),
  );
  dialogShown = true;

  try {
    final api = sl<ApiService>();
    final endpoint =
        '${AppConfig.mobileDocumentsEndpoint}/${document.id}/file';
    final response = await api.get(
      endpoint,
      queryParams: const {'attachment': '1'},
      useCache: false,
      additionalHeaders: const {'Accept': '*/*'},
    );

    closeDialog();

    if (!context.mounted) return;

    if (response.statusCode != 200) {
      messenger?.showSnackBar(
        SnackBar(content: Text(loc.pdfViewerDownloadFailedHttp(response.statusCode))),
      );
      return;
    }

    final dir = await getTemporaryDirectory();
    final file = File(
      '${dir.path}/admin_doc_download_${document.id}_${_safePreviewFileName(document)}',
    );
    await file.writeAsBytes(response.bodyBytes, flush: true);

    if (!context.mounted) return;

    final subject = document.fileName ?? 'document_${document.id}';
    await Share.shareXFiles(
      [XFile(file.path)],
      subject: subject,
    );

    if (context.mounted) {
      messenger?.showSnackBar(SnackBar(content: Text(loc.downloadStarted)));
    }
  } on AuthenticationException catch (e) {
    closeDialog();
    if (context.mounted) {
      messenger?.showSnackBar(SnackBar(content: Text(e.message)));
    }
  } catch (e) {
    closeDialog();
    if (context.mounted) {
      messenger?.showSnackBar(
        SnackBar(content: Text(loc.couldNotStartDownload)),
      );
    }
  }
}

Color _documentDetailStatusColor(String status, BuildContext context) {
  switch (status.toLowerCase()) {
    case 'approved':
      return Colors.green;
    case 'pending':
      return Colors.orange;
    case 'rejected':
      return Colors.red;
    default:
      return context.textSecondaryColor;
  }
}

String? _formatDocumentUploadedAt(BuildContext context, DateTime? at) {
  if (at == null) return null;
  try {
    final locale = Localizations.localeOf(context).toLanguageTag();
    return DateFormat.yMMMd(locale).add_jm().format(at.toLocal());
  } catch (_) {
    return at.toIso8601String();
  }
}

/// Full-screen summary for one document from the admin list.
/// Download fetches the file via the mobile API and opens the system share
/// sheet. Preview loads PDFs in [PdfViewerScreen]; other common types use
/// [SubmittedDocumentPreviewScreen], with WebView as a last resort.
class DocumentDetailScreen extends StatefulWidget {
  const DocumentDetailScreen({
    super.key,
    required this.document,
  });

  final Document document;

  @override
  State<DocumentDetailScreen> createState() => _DocumentDetailScreenState();
}

class _DocumentDetailScreenState extends State<DocumentDetailScreen>
    with AdminScreenViewLoggingMixin {
  @override
  String get adminScreenViewRoutePath =>
      AppRoutes.documentDetail(widget.document.id);

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final bottomInset = MediaQuery.paddingOf(context).bottom;
    final document = widget.document;
    final title = document.fileName ?? loc.genericUntitledDocument;
    final uploadedAtLabel = _formatDocumentUploadedAt(context, document.uploadedAt);
    final accent = Color(AppConstants.ifrcRed);
    final onAccent = theme.colorScheme.onPrimary;

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(
        title: title,
      ),
      body: ListView(
        padding: EdgeInsets.fromLTRB(16, 12, 16, 24 + bottomInset),
        children: [
          Text(
            loc.indicatorDetailDetails,
            style: theme.textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w600,
              color: context.textColor,
            ),
          ),
          const SizedBox(height: 12),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: context.subtleSurfaceColor,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: theme.colorScheme.outlineVariant.withValues(alpha: 0.45),
              ),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _DetailLine(
                  label: 'ID',
                  value: '${document.id}',
                ),
                if (document.status != null) ...[
                  const SizedBox(height: 10),
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      SizedBox(
                        width: 110,
                        child: Text(
                          loc.status,
                          style: theme.textTheme.labelMedium?.copyWith(
                            color: context.textSecondaryColor,
                          ),
                        ),
                      ),
                      Expanded(
                        child: Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 10,
                            vertical: 5,
                          ),
                          decoration: BoxDecoration(
                            color: _documentDetailStatusColor(
                                    document.status!, context)
                                .withValues(alpha: 0.12),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Text(
                            document.status!,
                            style: TextStyle(
                              fontWeight: FontWeight.w600,
                              color: _documentDetailStatusColor(
                                document.status!,
                                context,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
                if (document.countryName != null) ...[
                  const SizedBox(height: 10),
                  _DetailLine(
                    label: loc.accessRequestsCountry,
                    value: document.countryName!,
                  ),
                ],
                if (document.documentType != null) ...[
                  const SizedBox(height: 10),
                  _DetailLine(
                    label: loc.type,
                    value: document.documentType!,
                  ),
                ],
                if (document.language != null) ...[
                  const SizedBox(height: 10),
                  _DetailLine(
                    label: loc.language,
                    value: document.language!,
                  ),
                ],
                if (document.year != null) ...[
                  const SizedBox(height: 10),
                  _DetailLine(
                    label: 'Year',
                    value: '${document.year}',
                  ),
                ],
                if (document.uploadedByName != null) ...[
                  const SizedBox(height: 10),
                  _DetailLine(
                    label: 'Uploaded by',
                    value: document.uploadedByName!,
                  ),
                ],
                if (uploadedAtLabel != null) ...[
                  const SizedBox(height: 10),
                  _DetailLine(
                    label: 'Uploaded',
                    value: uploadedAtLabel,
                  ),
                ],
                if (document.assignmentPeriod != null) ...[
                  const SizedBox(height: 10),
                  _DetailLine(
                    label: 'Period',
                    value: document.assignmentPeriod!,
                  ),
                ],
                const SizedBox(height: 10),
                _DetailLine(
                  label: 'Visibility',
                  value: document.isPublic ? 'Public' : 'Internal',
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: () => openSubmittedDocumentPreview(context, document),
              icon: const Icon(Icons.preview_outlined),
              label: Text(loc.previewDocument),
              style: FilledButton.styleFrom(
                backgroundColor: accent,
                foregroundColor: onAccent,
                padding: const EdgeInsets.symmetric(vertical: 14),
              ),
            ),
          ),
          const SizedBox(height: 10),
          SizedBox(
            width: double.infinity,
            child: OutlinedButton.icon(
              onPressed: () => downloadSubmittedDocument(context, document),
              icon: const Icon(Icons.download_outlined),
              label: Text(loc.downloadDocument),
              style: OutlinedButton.styleFrom(
                foregroundColor: accent,
                side: BorderSide(color: accent),
                padding: const EdgeInsets.symmetric(vertical: 14),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _DetailLine extends StatelessWidget {
  const _DetailLine({
    required this.label,
    required this.value,
  });

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 110,
          child: Text(
            label,
            style: theme.textTheme.labelMedium?.copyWith(
              color: context.textSecondaryColor,
            ),
          ),
        ),
        Expanded(
          child: SelectableText(
            value,
            style: theme.textTheme.bodyMedium?.copyWith(
              color: context.textColor,
              height: 1.35,
            ),
          ),
        ),
      ],
    );
  }
}
