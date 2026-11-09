import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../../config/routes.dart';
import '../../l10n/app_localizations.dart';
import '../../models/shared/document.dart';
import '../../models/shared/entity.dart';
import '../../providers/shared/entity_document_repository_provider.dart';
import '../../utils/constants.dart';
import '../../utils/ios_constants.dart';
import '../../utils/theme_extensions.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/loading_indicator.dart';
import '../../widgets/mobile_screen_scaffold.dart';

class EntityDocumentRepositoryScreen extends StatefulWidget {
  final Entity entity;

  const EntityDocumentRepositoryScreen({super.key, required this.entity});

  @override
  State<EntityDocumentRepositoryScreen> createState() =>
      _EntityDocumentRepositoryScreenState();
}

class _EntityDocumentRepositoryScreenState
    extends State<EntityDocumentRepositoryScreen> {
  final TextEditingController _searchController = TextEditingController();
  String _searchQuery = '';

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  void _load() {
    final provider =
        Provider.of<EntityDocumentRepositoryProvider>(context, listen: false);
    provider.loadDocuments(
      entityType: widget.entity.entityType,
      entityId: widget.entity.entityId,
      search: _searchQuery.isNotEmpty ? _searchQuery : null,
    );
  }

  void _openDocumentDetail(Document document) {
    Navigator.of(context).pushNamed(
      AppRoutes.documentDetail(document.id),
      arguments: document,
    );
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final entityLabel = widget.entity.displayLabel;

    return MobileScreenScaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(
        title: loc.entityDocumentRepository,
      ),
      bottomNavigationBar: AppBottomNavigationBar.shellTabBar,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (entityLabel.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(20, 0, 20, 4),
              child: Text(
                entityLabel,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: context.textSecondaryColor,
                ),
              ),
            ),
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
            child: TextField(
              controller: _searchController,
              decoration: InputDecoration(
                hintText: loc.searchDocuments,
                prefixIcon: const Icon(Icons.search),
                suffixIcon: _searchQuery.isNotEmpty
                    ? IconButton(
                        icon: const Icon(Icons.clear),
                        onPressed: () {
                          setState(() {
                            _searchQuery = '';
                            _searchController.clear();
                          });
                          _load();
                        },
                      )
                    : null,
                filled: true,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(
                    IOSDimensions.borderRadiusLargeOf(context),
                  ),
                  borderSide: BorderSide.none,
                ),
              ),
              onSubmitted: (value) {
                setState(() => _searchQuery = value.trim());
                _load();
              },
            ),
          ),
          Expanded(
            child: Consumer<EntityDocumentRepositoryProvider>(
              builder: (context, provider, child) {
                if (provider.isLoading && provider.documents.isEmpty) {
                  return AppLoadingIndicator(
                    message: loc.loadingDocuments,
                    color: Color(AppConstants.ifrcRed),
                  );
                }

                if (provider.error != null && provider.documents.isEmpty) {
                  return Center(
                    child: Padding(
                      padding: const EdgeInsets.all(24),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const Icon(
                            Icons.error_outline,
                            size: 48,
                            color: Color(AppConstants.errorColor),
                          ),
                          const SizedBox(height: 16),
                          Text(
                            provider.error!,
                            style: TextStyle(
                              color: context.textSecondaryColor,
                              fontSize: 14,
                            ),
                            textAlign: TextAlign.center,
                          ),
                          const SizedBox(height: 24),
                          OutlinedButton.icon(
                            onPressed: () {
                              provider.clearError();
                              _load();
                            },
                            icon: const Icon(Icons.refresh, size: 18),
                            label: Text(loc.retry),
                          ),
                        ],
                      ),
                    ),
                  );
                }

                if (provider.documents.isEmpty) {
                  return Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(
                          Icons.folder_open_outlined,
                          size: 56,
                          color: context.textSecondaryColor,
                        ),
                        const SizedBox(height: 16),
                        Text(
                          loc.noDocumentsFound,
                          style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w600,
                            color: context.textColor,
                          ),
                        ),
                      ],
                    ),
                  );
                }

                return RefreshIndicator(
                  onRefresh: () async => _load(),
                  color: Color(AppConstants.ifrcRed),
                  child: ListView.separated(
                    padding: const EdgeInsets.only(bottom: 16),
                    itemCount: provider.documents.length,
                    separatorBuilder: (context, index) => Divider(
                      height: 1,
                      thickness: 1,
                      indent: 56,
                      color: theme.dividerColor.withValues(alpha: 0.6),
                    ),
                    itemBuilder: (context, index) {
                      final document = provider.documents[index];
                      return _EntityDocumentTile(
                        document: document,
                        onTap: () => _openDocumentDetail(document),
                      );
                    },
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _EntityDocumentTile extends StatelessWidget {
  final Document document;
  final VoidCallback onTap;

  const _EntityDocumentTile({
    required this.document,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final uploaded = document.uploadedAt != null
        ? DateFormat.yMMMd().format(document.uploadedAt!.toLocal())
        : null;
    final subtitle = [
      if (document.documentType != null && document.documentType!.isNotEmpty)
        document.documentType!,
      if (uploaded != null) uploaded,
    ].join(' · ');

    return ListTile(
      onTap: onTap,
      contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
      leading: _DocumentFileIcon(fileName: document.fileName),
      title: Text(
        document.fileName ?? 'Document #${document.id}',
        style: theme.textTheme.titleSmall?.copyWith(
          fontWeight: FontWeight.w600,
        ),
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
      ),
      subtitle: subtitle.isEmpty
          ? null
          : Text(
              subtitle,
              style: theme.textTheme.bodySmall?.copyWith(
                color: context.textSecondaryColor,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
      trailing: Icon(
        Icons.chevron_right,
        color: context.textSecondaryColor,
      ),
    );
  }
}

class _DocumentFileIcon extends StatelessWidget {
  final String? fileName;

  const _DocumentFileIcon({required this.fileName});

  @override
  Widget build(BuildContext context) {
    final style = _fileTypeStyle(fileName, context);
    return FaIcon(style.icon, size: 22, color: style.color);
  }
}

class _FileTypeStyle {
  final IconData icon;
  final Color color;

  const _FileTypeStyle(this.icon, this.color);
}

_FileTypeStyle _fileTypeStyle(String? fileName, BuildContext context) {
  switch (_fileExtension(fileName)) {
    case 'pdf':
      return _FileTypeStyle(
        FontAwesomeIcons.filePdf,
        Color(AppConstants.ifrcRed),
      );
    case 'doc':
    case 'docx':
    case 'docm':
    case 'odt':
    case 'rtf':
      return const _FileTypeStyle(FontAwesomeIcons.fileWord, Color(0xFF2B579A));
    case 'xls':
    case 'xlsx':
    case 'xlsm':
    case 'xlsb':
    case 'ods':
      return const _FileTypeStyle(
        FontAwesomeIcons.fileExcel,
        Color(0xFF217346),
      );
    case 'csv':
    case 'tsv':
      return const _FileTypeStyle(FontAwesomeIcons.fileCsv, Color(0xFF217346));
    case 'ppt':
    case 'pptx':
    case 'pptm':
    case 'odp':
      return const _FileTypeStyle(
        FontAwesomeIcons.filePowerpoint,
        Color(0xFFD24726),
      );
    case 'png':
    case 'jpg':
    case 'jpeg':
    case 'gif':
    case 'webp':
    case 'svg':
    case 'bmp':
    case 'tif':
    case 'tiff':
    case 'heic':
      return const _FileTypeStyle(FontAwesomeIcons.fileImage, Color(0xFF0F766E));
    case 'zip':
    case 'rar':
    case '7z':
    case 'gz':
    case 'tar':
      return const _FileTypeStyle(
        FontAwesomeIcons.fileZipper,
        Color(0xFFCA8A04),
      );
    case 'txt':
    case 'md':
      return _FileTypeStyle(FontAwesomeIcons.fileLines, context.textSecondaryColor);
    case 'mp4':
    case 'mov':
    case 'webm':
    case 'mkv':
      return const _FileTypeStyle(FontAwesomeIcons.fileVideo, Color(0xFF7C3AED));
    case 'mp3':
    case 'wav':
    case 'm4a':
    case 'aac':
      return const _FileTypeStyle(FontAwesomeIcons.fileAudio, Color(0xFF7C3AED));
    case 'json':
    case 'xml':
    case 'html':
    case 'htm':
    case 'js':
    case 'css':
    case 'py':
      return const _FileTypeStyle(FontAwesomeIcons.fileCode, Color(0xFF475569));
    default:
      return _FileTypeStyle(FontAwesomeIcons.file, context.textSecondaryColor);
  }
}

String? _fileExtension(String? fileName) {
  if (fileName == null) return null;
  final name = fileName.trim().split(RegExp(r'[\\/]')).last;
  final dot = name.lastIndexOf('.');
  if (dot <= 0 || dot == name.length - 1) return null;
  return name.substring(dot + 1).toLowerCase();
}
