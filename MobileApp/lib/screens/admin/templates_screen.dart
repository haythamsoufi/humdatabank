import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/admin/templates_provider.dart';
import '../../models/shared/template.dart';
import '../../utils/theme_extensions.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/app_bar.dart';
import 'package:flutter/services.dart';
import '../../l10n/app_localizations.dart';

class TemplatesScreen extends StatefulWidget {
  const TemplatesScreen({super.key});

  @override
  State<TemplatesScreen> createState() => _TemplatesScreenState();
}

class _TemplatesScreenState extends State<TemplatesScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadTemplates();
    });
  }

  void _loadTemplates() {
    Provider.of<TemplatesProvider>(context, listen: false).loadTemplates();
  }

  Future<void> _handleDelete(Template template) async {
    final localizations = AppLocalizations.of(context)!;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(localizations.deleteTemplate),
        content: Text(
          template.dataCount != null && template.dataCount! > 0
              ? 'This template has ${template.dataCount} saved data entries that will be permanently deleted. Continue?'
              : 'Are you sure you want to delete this template?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: Text(localizations.cancel),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            style: TextButton.styleFrom(
              foregroundColor: Colors.red,
            ),
            child: Text(localizations.delete),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      final provider = Provider.of<TemplatesProvider>(context, listen: false);
      final success = await provider.deleteTemplate(template.id);

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(success
                ? localizations.templateDeletedSuccessfully
                : localizations.failedToDeleteTemplate),
            backgroundColor: success ? Colors.green : Colors.red,
          ),
        );

        if (success) {
          _loadTemplates();
        }
      }
    }
  }

  Future<void> _handleDuplicate(Template template) async {
    final provider = Provider.of<TemplatesProvider>(context, listen: false);
    final success = await provider.duplicateTemplate(template.id);

    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(success
              ? 'Template duplicated successfully'
              : 'Failed to duplicate template'),
          backgroundColor: success ? Colors.green : Colors.red,
        ),
      );

      if (success) {
        _loadTemplates();
      }
    }
  }

  void _copyToClipboard(String text, String message) {
    Clipboard.setData(ClipboardData(text: text));
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        duration: const Duration(seconds: 2),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(
        title: localizations.manageTemplates,
      ),
      body: Consumer<TemplatesProvider>(
        builder: (context, provider, child) {
          if (provider.isLoading) {
            return Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  CircularProgressIndicator(
                    valueColor: AlwaysStoppedAnimation<Color>(
                      Color(AppConstants.ifrcRed),
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    AppLocalizations.of(context)!.loadingTemplates,
                    style: const TextStyle(
                      color: Color(AppConstants.textSecondary),
                      fontSize: 14,
                    ),
                  ),
                ],
              ),
            );
          }

          if (provider.error != null) {
            return Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(
                    Icons.error_outline,
                    size: 64,
                    color: Color(AppConstants.textSecondary),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    provider.error!,
                    style: const TextStyle(
                      color: Color(AppConstants.textSecondary),
                      fontSize: 14,
                    ),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 16),
                  ElevatedButton(
                    onPressed: _loadTemplates,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Color(AppConstants.ifrcRed),
                      foregroundColor: Theme.of(context).colorScheme.onPrimary,
                    ),
                    child: Text(localizations.retry),
                  ),
                ],
              ),
            );
          }

          if (provider.templates.isEmpty) {
            return Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(
                    Icons.description_outlined,
                    size: 64,
                    color: Color(AppConstants.textSecondary),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    localizations.noTemplatesFound,
                    style: const TextStyle(
                      color: Color(AppConstants.textSecondary),
                      fontSize: 16,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ],
              ),
            );
          }

          return RefreshIndicator(
            onRefresh: () async => _loadTemplates(),
            color: Color(AppConstants.ifrcRed),
            child: ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: provider.templates.length,
              itemBuilder: (context, index) {
                final template = provider.templates[index];
                return Card(
                  margin: const EdgeInsets.only(bottom: 12),
                  elevation: 0,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8),
                    side: BorderSide(
                      color: context.borderColor,
                      width: 1,
                    ),
                  ),
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    template.displayName,
                                    style: const TextStyle(
                                      fontSize: 16,
                                      fontWeight: FontWeight.w600,
                                      color: Color(AppConstants.textColor),
                                    ),
                                  ),
                                  const SizedBox(height: 8),
                                  Row(
                                    children: [
                                      if (template.addToSelfReport)
                                        Container(
                                          padding: const EdgeInsets.symmetric(
                                            horizontal: 8,
                                            vertical: 4,
                                          ),
                                          decoration: BoxDecoration(
                                            color:
                                                Colors.green.withOpacity(0.1),
                                            borderRadius:
                                                BorderRadius.circular(8),
                                          ),
                                          child: Row(
                                            mainAxisSize: MainAxisSize.min,
                                            children: [
                                              Icon(
                                                Icons.check_circle,
                                                size: 14,
                                                color: Colors.green.shade700,
                                              ),
                                              const SizedBox(width: 4),
                                              Text(
                                                'Self-Report',
                                                style: TextStyle(
                                                  fontSize: 12,
                                                  color: Colors.green.shade700,
                                                  fontWeight: FontWeight.w500,
                                                ),
                                              ),
                                            ],
                                          ),
                                        ),
                                    ],
                                  ),
                                ],
                              ),
                            ),
                            PopupMenuButton<String>(
                              icon: const Icon(Icons.more_vert),
                              onSelected: (value) {
                                switch (value) {
                                  case 'edit':
                                    Navigator.of(context).pushNamed(
                                      AppRoutes.webview,
                                      arguments:
                                          '/admin/form-builder/edit-template/${template.id}',
                                    );
                                    break;
                                  case 'duplicate':
                                    _handleDuplicate(template);
                                    break;
                                  case 'preview':
                                    Navigator.of(context).pushNamed(
                                      AppRoutes.webview,
                                      arguments:
                                          '/forms/preview-template/${template.id}',
                                    );
                                    break;
                                  case 'delete':
                                    _handleDelete(template);
                                    break;
                                }
                              },
                              itemBuilder: (context) {
                                final localizations = AppLocalizations.of(context)!;
                                return [
                                  PopupMenuItem(
                                    value: 'edit',
                                    child: Row(
                                      children: [
                                        Icon(Icons.edit,
                                            size: 20, color: Colors.blue),
                                        SizedBox(width: 8),
                                        Text(localizations.edit),
                                      ],
                                    ),
                                  ),
                                  PopupMenuItem(
                                    value: 'duplicate',
                                    child: Row(
                                      children: [
                                        Icon(Icons.copy,
                                            size: 20, color: context.iconColor),
                                        const SizedBox(width: 8),
                                        Text(localizations.duplicate),
                                      ],
                                    ),
                                  ),
                                  PopupMenuItem(
                                    value: 'preview',
                                    child: Row(
                                      children: [
                                        Icon(Icons.visibility,
                                            size: 20, color: Colors.green),
                                        const SizedBox(width: 8),
                                        Text(localizations.preview),
                                      ],
                                    ),
                                  ),
                                  PopupMenuItem(
                                    value: 'delete',
                                    child: Row(
                                      children: [
                                        const Icon(Icons.delete,
                                            size: 20, color: Colors.red),
                                        const SizedBox(width: 8),
                                        Text(localizations.delete),
                                      ],
                                    ),
                                  ),
                                ];
                              },
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                        Row(
                          children: [
                            Icon(
                              Icons.calendar_today,
                              size: 14,
                              color: context.textSecondaryColor,
                            ),
                            const SizedBox(width: 4),
                            Text(
                              'Created: ${_formatDate(template.createdAt)}',
                              style: const TextStyle(
                                fontSize: 12,
                                color: Color(AppConstants.textSecondary),
                              ),
                            ),
                            if (template.dataCount != null) ...[
                              const SizedBox(width: 16),
                              Icon(
                                Icons.data_object,
                                size: 14,
                                color: context.textSecondaryColor,
                              ),
                              const SizedBox(width: 4),
                              Text(
                                '${template.dataCount} entries',
                                style: const TextStyle(
                                  fontSize: 12,
                                  color: Color(AppConstants.textSecondary),
                                ),
                              ),
                            ],
                          ],
                        ),
                      ],
                    ),
                  ),
                );
              },
            ),
          );
        },
      ),
      floatingActionButton: FloatingActionButton.extended(
        heroTag: 'templates_add_button',
        onPressed: () {
          Navigator.of(context).pushNamed(
            AppRoutes.webview,
            arguments: '/admin/form-builder/new-template',
          );
        },
        backgroundColor: Color(AppConstants.ifrcRed),
        icon: const Icon(Icons.add),
        label: Text(localizations.createTemplate),
      ),
      bottomNavigationBar: AppBottomNavigationBar(
        currentIndex:
            -1, // -1 means no tab is active (Templates screen is on top)
        onTap: (index) {
          // Navigate back to main navigation screen
          // The MainNavigationScreen will handle tab switching
          Navigator.of(context).popUntil((route) {
            // Pop until we reach the main navigation screen
            return route.isFirst || route.settings.name == AppRoutes.dashboard;
          });
        },
      ),
    );
  }

  String _formatDate(DateTime date) {
    return '${date.year}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')} ${date.hour.toString().padLeft(2, '0')}:${date.minute.toString().padLeft(2, '0')}';
  }
}
