import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/admin/organizational_structure_provider.dart';
import '../../utils/theme_extensions.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/app_checkbox_list_tile.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../l10n/app_localizations.dart';

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

class _EditEntityScreenState extends State<EditEntityScreen> {
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

  String _getEntityTypeLabel() {
    switch (widget.entityType) {
      case 'countries':
        return 'Country';
      case 'nss':
        return 'National Society';
      case 'divisions':
        return 'Division';
      case 'departments':
        return 'Department';
      case 'regions':
        return 'Regional Office';
      case 'clusters':
        return 'Cluster Office';
      case 'ns_structure':
        return 'NS Structure';
      default:
        return 'Entity';
    }
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(
        title: 'Edit ${_getEntityTypeLabel()}',
      ),
      body: _isLoading && _nameController.text.isEmpty
          ? Center(
              child: CircularProgressIndicator(
                valueColor: AlwaysStoppedAnimation<Color>(
                  theme.colorScheme.primary,
                ),
              ),
            )
          : Container(
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
                        labelText: '${_getEntityTypeLabel()} Name *',
                        hintText:
                            'Enter ${_getEntityTypeLabel().toLowerCase()} name',
                        prefixIcon: Icon(Icons.business_outlined),
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
                          return '${_getEntityTypeLabel()} name is required';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 16),

                    // Code Field
                    TextFormField(
                      controller: _codeController,
                      decoration: InputDecoration(
                        labelText: 'Code',
                        hintText: 'Enter code (optional)',
                        prefixIcon: Icon(Icons.tag_outlined),
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
                        labelText: 'Description',
                        hintText: 'Enter description (optional)',
                        prefixIcon: Icon(Icons.description_outlined),
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
                      title: 'Active',
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
                          labelText: 'Display Order',
                          hintText: 'Enter display order',
                          prefixIcon: Icon(Icons.sort_outlined),
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
                          : const Text(
                              'Save',
                              style: TextStyle(
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
                        localizations.cancel ?? 'Cancel',
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w600,
                          color: theme.colorScheme.primary,
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
