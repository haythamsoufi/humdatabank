import 'dart:io';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import '../../config/app_config.dart';
import '../../config/routes.dart';
import '../../di/service_locator.dart';
import '../../l10n/app_localizations.dart';
import '../../models/shared/resource.dart';
import '../../services/api_service.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../widgets/app_bar.dart';
import '../../utils/admin_screen_view_logging_mixin.dart';

bool _bytesLookLikePdf(List<int> bytes) =>
    bytes.length >= 5 &&
    bytes[0] == 0x25 &&
    bytes[1] == 0x50 &&
    bytes[2] == 0x44 &&
    bytes[3] == 0x46 &&
    bytes[4] == 0x2d;

String _safeDownloadFileName(Resource resource) {
  final raw = resource.title ?? 'resource_${resource.id}';
  final cleaned = raw.replaceAll(RegExp(r'[<>:"/\\|?*\x00-\x1f]'), '_').trim();
  if (cleaned.isEmpty) return 'resource_${resource.id}';
  return cleaned;
}

Future<void> openResourcePreview(
  BuildContext context,
  Resource resource,
  String languageCode,
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
        '${AppConfig.mobileResourcesEndpoint}/${resource.id}/file';
    final response = await api.get(
      endpoint,
      queryParams: {'language': languageCode},
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
      await nav.pushNamed(
        AppRoutes.webview,
        arguments: '/admin/resources/edit/${resource.id}',
      );
      return;
    }

    final dir = await getTemporaryDirectory();
    final file = File(
      '${dir.path}/admin_resource_preview_${resource.id}_$languageCode.pdf',
    );
    await file.writeAsBytes(bytes, flush: true);

    if (!context.mounted) return;

    await nav.pushNamed(
      AppRoutes.pdfViewer,
      arguments: <String, String>{
        'filePath': file.path,
        'title': resource.title ?? loc.previewDocument,
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

Future<void> downloadResourceFile(
  BuildContext context,
  Resource resource,
  String languageCode,
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
        '${AppConfig.mobileResourcesEndpoint}/${resource.id}/file';
    final response = await api.get(
      endpoint,
      queryParams: {
        'language': languageCode,
        'attachment': '1',
      },
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
      '${dir.path}/admin_resource_download_${resource.id}_${languageCode}_${_safeDownloadFileName(resource)}',
    );
    await file.writeAsBytes(response.bodyBytes, flush: true);

    if (!context.mounted) return;

    final subject = resource.title ?? 'resource_${resource.id}';
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

/// Detail view for one admin resource: metadata and file preview/download
/// via the mobile API (no WebView for binary actions).
class ResourceDetailScreen extends StatefulWidget {
  const ResourceDetailScreen({
    super.key,
    required this.resource,
  });

  final Resource resource;

  @override
  State<ResourceDetailScreen> createState() => _ResourceDetailScreenState();
}

class _ResourceDetailScreenState extends State<ResourceDetailScreen>
    with AdminScreenViewLoggingMixin {
  @override
  String get adminScreenViewRoutePath =>
      AppRoutes.resourceDetail(widget.resource.id);

  late String _languageCode;

  Resource get _r => widget.resource;

  @override
  void initState() {
    super.initState();
    _languageCode = _initialLanguage(_r);
  }

  String _initialLanguage(Resource r) {
    if (r.language != null &&
        r.fileLanguages.any((c) => c.toLowerCase() == r.language!.toLowerCase())) {
      return r.language!.toLowerCase();
    }
    if (r.fileLanguages.isNotEmpty) {
      return r.fileLanguages.first.toLowerCase();
    }
    return 'en';
  }

  bool get _hasDownloadableFile => _r.fileLanguages.isNotEmpty;

  String? _formatDate(BuildContext context, DateTime? d) {
    if (d == null) return null;
    try {
      final locale = Localizations.localeOf(context).toLanguageTag();
      return DateFormat.yMMMd(locale).format(d);
    } catch (_) {
      return d.toIso8601String().split('T').first;
    }
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final bottomInset = MediaQuery.paddingOf(context).bottom;
    final title = _r.title ?? loc.genericUntitledResource;
    final pub = _formatDate(context, _r.publicationDate);

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
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: context.subtleSurfaceColor,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: context.borderColor),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _DetailLine(label: 'ID', value: '${_r.id}'),
                if (_r.resourceType != null) ...[
                  const SizedBox(height: 10),
                  _DetailLine(
                    label: loc.type,
                    value: _r.resourceType!,
                  ),
                ],
                if (pub != null) ...[
                  const SizedBox(height: 10),
                  _DetailLine(
                    label: 'Published',
                    value: pub,
                  ),
                ],
                if (_r.subcategory != null) ...[
                  const SizedBox(height: 10),
                  _DetailLine(
                    label: loc.category,
                    value: _r.subcategory!.name,
                  ),
                ],
                if (_r.description != null && _r.description!.trim().isNotEmpty) ...[
                  const SizedBox(height: 10),
                  Text(
                    'Description',
                    style: theme.textTheme.labelMedium?.copyWith(
                      color: context.textSecondaryColor,
                    ),
                  ),
                  const SizedBox(height: 4),
                  SelectableText(
                    _r.description!.trim(),
                    style: theme.textTheme.bodyMedium?.copyWith(
                      color: context.textColor,
                      height: 1.35,
                    ),
                  ),
                ],
                if (_r.fileLanguages.length <= 1) ...[
                  const SizedBox(height: 10),
                  _DetailLine(
                    label: loc.language,
                    value: _languageCode.toUpperCase(),
                  ),
                ],
                if (_r.fileLanguages.length > 1) ...[
                  const SizedBox(height: 12),
                  Text(
                    '${loc.language} (file)',
                    style: theme.textTheme.labelMedium?.copyWith(
                      color: context.textSecondaryColor,
                    ),
                  ),
                  const SizedBox(height: 6),
                  DropdownButton<String>(
                    value: _languageCode,
                    isExpanded: true,
                    items: _r.fileLanguages
                        .map(
                          (c) => DropdownMenuItem(
                            value: c.toLowerCase(),
                            child: Text(c.toUpperCase()),
                          ),
                        )
                        .toList(),
                    onChanged: (v) {
                      if (v != null) {
                        setState(() => _languageCode = v);
                      }
                    },
                  ),
                ],
                const SizedBox(height: 10),
                _DetailLine(
                  label: 'Public listing',
                  value: _r.isPublished ? 'Yes' : 'No',
                ),
              ],
            ),
          ),
          if (_hasDownloadableFile) ...[
            const SizedBox(height: 24),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: () =>
                    openResourcePreview(context, _r, _languageCode),
                icon: const Icon(Icons.preview_outlined),
                label: Text(loc.previewDocument),
                style: OutlinedButton.styleFrom(
                  foregroundColor: Color(AppConstants.ifrcRed),
                  side: BorderSide(color: Color(AppConstants.ifrcRed)),
                  padding: const EdgeInsets.symmetric(vertical: 14),
                ),
              ),
            ),
            const SizedBox(height: 10),
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: () =>
                    downloadResourceFile(context, _r, _languageCode),
                icon: const Icon(Icons.download_outlined),
                label: Text(loc.downloadDocument),
                style: OutlinedButton.styleFrom(
                  foregroundColor: Color(AppConstants.ifrcRed),
                  side: BorderSide(color: Color(AppConstants.ifrcRed)),
                  padding: const EdgeInsets.symmetric(vertical: 14),
                ),
              ),
            ),
          ] else ...[
            const SizedBox(height: 16),
            Text(
              'No file is available for this resource in the catalog.',
              style: theme.textTheme.bodyMedium?.copyWith(
                color: context.textSecondaryColor,
              ),
            ),
          ],
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
