import 'package:flutter/material.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/app_checkbox_list_tile.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../l10n/app_localizations.dart';
import '../../utils/admin_screen_view_logging_mixin.dart';

class EditEntityScreen extends StatefulWidget {
  final int entityId;
  final String? entityType;
  final String? entityName;

  const EditEntityScreen({
    super.key,
    required this.entityId,
    this.entityType,
    this.entityName,
  });

  @override
  State<EditEntityScreen> createState() => _EditEntityScreenState();
}

class _EditEntityScreenState extends State<EditEntityScreen>
    with AdminScreenViewLoggingMixin {
  @override
  String get adminScreenViewRoutePath =>
      AppRoutes.editEntity(widget.entityId, widget.entityType);

  final _formKey = GlobalKey<FormState>();
  late TextEditingController _nameController;
  late TextEditingController _codeController;
  late TextEditingController _descriptionController;

  bool _isActive = true;
  int _displayOrder = 0;
  bool _isLoading = false;

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController(text: widget.entityName ?? '');
    _codeController = TextEditingController();
    _descriptionController = TextEditingController();
    _loadEntity();
  }

  @override
  void dispose() {
    _nameController.dispose();
    _codeController.dispose();
    _descriptionController.dispose();
    super.dispose();
  }

  Future<void> _loadEntity() async {
    // For now, we'll load from the existing data structure
    // In the future, this can be enhanced to fetch from API
    setState(() {
      _isLoading = true;
    });

    // Simulate loading - in real implementation, fetch from API
    await Future.delayed(const Duration(milliseconds: 500));

    if (mounted) {
      setState(() {
        _isLoading = false;
      });
    }
  }

  Future<void> _saveEntity() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }

    setState(() {
      _isLoading = true;
    });

    // For now, navigate back with success indicator
    // In the future, this can be enhanced to save via API
    await Future.delayed(const Duration(milliseconds: 500));

    if (mounted) {
      setState(() {
        _isLoading = false;
      });

      // Since we don't have direct API access yet, show message and redirect to webview
      final localizations = AppLocalizations.of(context)!;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content:
              Text(localizations.pleaseUseWebInterface),
          backgroundColor: Color(AppConstants.ifrcRed),
          duration: const Duration(seconds: 3),
          action: SnackBarAction(
            label: localizations.openInWebBrowser,
            textColor: Theme.of(context).colorScheme.onPrimary,
            onPressed: () {
              // Navigate to webview for editing
              final editUrl = widget.entityType != null
                  ? '/admin/organization/edit/${widget.entityType}/${widget.entityId}'
                  : '/admin/organization/edit/${widget.entityId}';
              Navigator.of(context).pushNamed(
                AppRoutes.webview,
                arguments: editUrl,
              );
            },
          ),
        ),
      );

      // Close the screen after a delay
      Future.delayed(const Duration(seconds: 2), () {
        if (mounted) {
          Navigator.of(context).pop();
        }
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final entityKey = widget.entityType ?? '';

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(
        title: localizations.entityEditTitle(entityKey),
      ),
      body: _isLoading && _nameController.text.isEmpty
          ? const Center(
              child: CircularProgressIndicator(),
            )
          : ColoredBox(
              color: theme.scaffoldBackgroundColor,
              child: Form(
                key: _formKey,
                child: ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    // Name Field
                    TextFormField(
                      controller: _nameController,
                      decoration: InputDecoration(
                        labelText: localizations.entityNameLabel(entityKey),
                        hintText: localizations.entityNameHint(entityKey),
                        prefixIcon: const Icon(Icons.business_outlined),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(8),
                        ),
                        filled: true,
                        fillColor:
                            theme.cardTheme.color ?? theme.colorScheme.surface,
                      ),
                      style: TextStyle(
                        color: theme.colorScheme.onSurface,
                      ),
                      validator: (value) {
                        if (value == null || value.trim().isEmpty) {
                          return '${localizations.entityNameLabel(entityKey)} is required';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 16),

                    // Code Field
                    TextFormField(
                      controller: _codeController,
                      decoration: InputDecoration(
                        labelText: localizations.fieldCode,
                        hintText: localizations.fieldCodeHint,
                        prefixIcon: const Icon(Icons.tag_outlined),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(8),
                        ),
                        filled: true,
                        fillColor:
                            theme.cardTheme.color ?? theme.colorScheme.surface,
                      ),
                      style: TextStyle(
                        color: theme.colorScheme.onSurface,
                      ),
                    ),
                    const SizedBox(height: 16),

                    // Description Field
                    TextFormField(
                      controller: _descriptionController,
                      decoration: InputDecoration(
                        labelText: localizations.fieldDescription,
                        hintText: localizations.fieldDescriptionHint,
                        prefixIcon: const Icon(Icons.description_outlined),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(8),
                        ),
                        filled: true,
                        fillColor:
                            theme.cardTheme.color ?? theme.colorScheme.surface,
                      ),
                      style: TextStyle(
                        color: theme.colorScheme.onSurface,
                      ),
                      maxLines: 4,
                    ),
                    const SizedBox(height: 16),

                    // Active Checkbox
                    AppCheckboxListTile(
                      title: localizations.fieldActive,
                      value: _isActive,
                      onChanged: (value) {
                        setState(() {
                          _isActive = value ?? true;
                        });
                      },
                    ),

                    // Display Order Field (if applicable)
                    if (widget.entityType == 'divisions' ||
                        widget.entityType == 'departments' ||
                        widget.entityType == 'regions' ||
                        widget.entityType == 'clusters')
                      TextFormField(
                        initialValue: _displayOrder.toString(),
                        decoration: InputDecoration(
                          labelText: localizations.fieldDisplayOrder,
                          hintText: localizations.fieldDisplayOrderHint,
                          prefixIcon: const Icon(Icons.sort_outlined),
                          border: OutlineInputBorder(
                            borderRadius: BorderRadius.circular(8),
                          ),
                          filled: true,
                          fillColor: theme.cardTheme.color ??
                              theme.colorScheme.surface,
                        ),
                        style: TextStyle(
                          color: theme.colorScheme.onSurface,
                        ),
                        keyboardType: TextInputType.number,
                        onChanged: (value) {
                          _displayOrder = int.tryParse(value) ?? 0;
                        },
                      ),
                    const SizedBox(height: 24),

                    // Save Button
                    ElevatedButton(
                      onPressed: _isLoading ? null : _saveEntity,
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Color(AppConstants.ifrcRed),
                        foregroundColor:
                            Theme.of(context).colorScheme.onPrimary,
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8),
                        ),
                      ),
                      child: _isLoading
                          ? SizedBox(
                              height: 20,
                              width: 20,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                valueColor: AlwaysStoppedAnimation<Color>(
                                  Theme.of(context).colorScheme.onPrimary,
                                ),
                              ),
                            )
                          : Text(
                              localizations.save,
                              style: const TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                    ),
                    const SizedBox(height: 12),

                    // Cancel Button
                    OutlinedButton(
                      onPressed: _isLoading
                          ? null
                          : () {
                              Navigator.of(context).pop();
                            },
                      style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        side: BorderSide(
                          color: Color(AppConstants.ifrcRed),
                        ),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8),
                        ),
                      ),
                      child: Text(
                        localizations.cancel,
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w600,
                          color: context.navyForegroundColor,
                        ),
                      ),
                    ),
                    const SizedBox(height: 16),

                    // Open in Web Button
                    OutlinedButton.icon(
                      onPressed: () {
                        final editUrl = widget.entityType != null
                            ? '/admin/organization/edit/${widget.entityType}/${widget.entityId}'
                            : '/admin/organization/edit/${widget.entityId}';
                        Navigator.of(context).pushReplacementNamed(
                          AppRoutes.webview,
                          arguments: editUrl,
                        );
                      },
                      icon: const Icon(Icons.open_in_browser),
                      label: Text(localizations.openInWebBrowser),
                      style: OutlinedButton.styleFrom(
                        padding: const EdgeInsets.symmetric(vertical: 16),
                        side: BorderSide(
                          color: theme.dividerColor,
                        ),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
    );
  }
}
