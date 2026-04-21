import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/admin/indicator_bank_admin_provider.dart';
import '../../models/shared/indicator.dart';
import '../../utils/theme_extensions.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/app_checkbox_list_tile.dart';
import '../../utils/constants.dart';
import '../../l10n/app_localizations.dart';
import '../../config/routes.dart';
import '../../utils/admin_screen_view_logging_mixin.dart';

class EditIndicatorScreen extends StatefulWidget {
  final int indicatorId;

  const EditIndicatorScreen({
    super.key,
    required this.indicatorId,
  });

  @override
  State<EditIndicatorScreen> createState() => _EditIndicatorScreenState();
}

class _EditIndicatorScreenState extends State<EditIndicatorScreen>
    with AdminScreenViewLoggingMixin {
  @override
  String get adminScreenViewRoutePath =>
      AppRoutes.editIndicator(widget.indicatorId);

  final _formKey = GlobalKey<FormState>();
  late TextEditingController _nameController;
  late TextEditingController _typeController;
  late TextEditingController _unitController;
  late TextEditingController _definitionController;
  late TextEditingController _sectorController;
  late TextEditingController _subSectorController;
  late TextEditingController _commentsController;
  late TextEditingController _relatedProgramsController;

  bool _emergency = false;
  bool _archived = false;
  bool _isLoading = false;
  Indicator? _indicator;

  final List<String> _typeOptions = [
    'Number',
    'Percentage',
    'Text',
    'YesNo',
    'Date',
  ];

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController();
    _typeController = TextEditingController();
    _unitController = TextEditingController();
    _definitionController = TextEditingController();
    _sectorController = TextEditingController();
    _subSectorController = TextEditingController();
    _commentsController = TextEditingController();
    _relatedProgramsController = TextEditingController();
    _loadIndicator();
  }

  @override
  void dispose() {
    _nameController.dispose();
    _typeController.dispose();
    _unitController.dispose();
    _definitionController.dispose();
    _sectorController.dispose();
    _subSectorController.dispose();
    _commentsController.dispose();
    _relatedProgramsController.dispose();
    super.dispose();
  }

  Future<void> _loadIndicator() async {
    setState(() {
      _isLoading = true;
    });

    final provider =
        Provider.of<IndicatorBankAdminProvider>(context, listen: false);
    final indicator = await provider.getIndicatorById(widget.indicatorId);

    if (mounted) {
      setState(() {
        _isLoading = false;
        if (indicator != null) {
          _indicator = indicator;
          _nameController.text = indicator.name ?? '';
          _typeController.text = indicator.type ?? '';
          _unitController.text = indicator.unit ?? '';
          _definitionController.text = indicator.description ?? '';
          _sectorController.text = indicator.sector ?? '';
          _subSectorController.text = indicator.subSector ?? '';
          _emergency = indicator.isEmergency;
          _archived = indicator.isArchived;
        }
      });
    }
  }

  Future<void> _saveIndicator() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }

    setState(() {
      _isLoading = true;
    });

    final provider =
        Provider.of<IndicatorBankAdminProvider>(context, listen: false);

    final data = <String, dynamic>{
      'name': _nameController.text.trim(),
      'type': _typeController.text.trim(),
      if (_unitController.text.trim().isNotEmpty)
        'unit': _unitController.text.trim(),
      if (_definitionController.text.trim().isNotEmpty)
        'definition': _definitionController.text.trim(),
      'emergency': _emergency,
      'archived': _archived,
      if (_commentsController.text.trim().isNotEmpty)
        'comments': _commentsController.text.trim(),
      if (_relatedProgramsController.text.trim().isNotEmpty)
        'related_programs': _relatedProgramsController.text.trim(),
    };

    final success = await provider.updateIndicator(widget.indicatorId, data);

    if (mounted) {
      setState(() {
        _isLoading = false;
      });

      final localizations = AppLocalizations.of(context)!;
      if (success) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(localizations.indicatorUpdatedSuccessfully),
            backgroundColor: Color(AppConstants.ifrcRed),
            duration: const Duration(seconds: 2),
          ),
        );
        Navigator.of(context).pop(true);
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(provider.error ?? localizations.error),
            backgroundColor: const Color(AppConstants.errorColor),
            duration: const Duration(seconds: 3),
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(
        title: localizations.editIndicator,
      ),
      body: _isLoading && _indicator == null
          ? const Center(
              child: CircularProgressIndicator(),
            )
          : _indicator == null
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        Icons.error_outline,
                        size: 48,
                        color: theme.colorScheme.error,
                      ),
                      const SizedBox(height: 16),
                      Text(
                        localizations.failedToLoadIndicator,
                        style: theme.textTheme.bodyLarge,
                      ),
                      const SizedBox(height: 24),
                      ElevatedButton(
                        onPressed: () {
                          Navigator.of(context).pop();
                        },
                        child: Text(localizations.goBack),
                      ),
                    ],
                  ),
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
                            labelText: localizations.indicatorEditNameLabel,
                            hintText: localizations.indicatorEditNameHint,
                            prefixIcon: const Icon(Icons.label_outline),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                            filled: true,
                            fillColor: context.lightSurfaceColor,
                          ),
                          validator: (value) {
                            if (value == null || value.trim().isEmpty) {
                              return localizations.indicatorEditNameRequired;
                            }
                            return null;
                          },
                        ),
                        const SizedBox(height: 16),

                        // Type Field (Dropdown)
                        DropdownButtonFormField<String>(
                          initialValue: _typeController.text.isEmpty
                              ? null
                              : _typeController.text,
                          decoration: InputDecoration(
                            labelText: localizations.indicatorEditTypeLabel,
                            prefixIcon: const Icon(Icons.category_outlined),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                            filled: true,
                            fillColor: context.lightSurfaceColor,
                          ),
                          items: _typeOptions.map((type) {
                            return DropdownMenuItem<String>(
                              value: type,
                              child: Text(type),
                            );
                          }).toList(),
                          onChanged: (value) {
                            if (value != null) {
                              setState(() {
                                _typeController.text = value;
                              });
                            }
                          },
                          validator: (value) {
                            if (value == null || value.isEmpty) {
                              return localizations.indicatorEditTypeRequired;
                            }
                            return null;
                          },
                        ),
                        const SizedBox(height: 16),

                        // Unit Field
                        TextFormField(
                          controller: _unitController,
                          decoration: InputDecoration(
                            labelText: localizations.indicatorDetailUnit,
                            hintText: localizations.indicatorEditUnitHint,
                            prefixIcon: const Icon(Icons.straighten_outlined),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                            filled: true,
                            fillColor: context.lightSurfaceColor,
                          ),
                        ),
                        const SizedBox(height: 16),

                        // Definition Field
                        TextFormField(
                          controller: _definitionController,
                          decoration: InputDecoration(
                            labelText: localizations.indicatorDetailDefinition,
                            hintText: localizations.indicatorEditDefinitionHint,
                            prefixIcon: const Icon(Icons.description_outlined),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                            filled: true,
                            fillColor: context.lightSurfaceColor,
                          ),
                          maxLines: 4,
                        ),
                        const SizedBox(height: 16),

                        // Sector Field
                        TextFormField(
                          controller: _sectorController,
                          decoration: InputDecoration(
                            labelText: localizations.indicatorDetailSector,
                            hintText: localizations.indicatorEditSectorHint,
                            prefixIcon: const Icon(Icons.business_outlined),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                            filled: true,
                            fillColor: context.lightSurfaceColor,
                          ),
                        ),
                        const SizedBox(height: 16),

                        // Sub-Sector Field
                        TextFormField(
                          controller: _subSectorController,
                          decoration: InputDecoration(
                            labelText: localizations.indicatorDetailSubsector,
                            hintText: localizations.indicatorEditSubsectorHint,
                            prefixIcon:
                                const Icon(Icons.business_center_outlined),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                            filled: true,
                            fillColor: context.lightSurfaceColor,
                          ),
                        ),
                        const SizedBox(height: 16),

                        // Related Programs Field
                        TextFormField(
                          controller: _relatedProgramsController,
                          decoration: InputDecoration(
                            labelText: localizations.indicatorDetailRelatedPrograms,
                            hintText:
                                localizations.indicatorEditRelatedProgramsHint,
                            prefixIcon: const Icon(Icons.list_outlined),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                            filled: true,
                            fillColor: context.lightSurfaceColor,
                          ),
                        ),
                        const SizedBox(height: 16),

                        // Comments Field
                        TextFormField(
                          controller: _commentsController,
                          decoration: InputDecoration(
                            labelText: localizations.indicatorEditCommentsLabel,
                            hintText: localizations.indicatorEditCommentsHint,
                            prefixIcon: const Icon(Icons.comment_outlined),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                            filled: true,
                            fillColor: context.lightSurfaceColor,
                          ),
                          maxLines: 3,
                        ),
                        const SizedBox(height: 24),

                        // Emergency Checkbox
                        AppCheckboxListTile(
                          title: localizations.indicatorEditEmergency,
                          value: _emergency,
                          onChanged: (value) {
                            setState(() {
                              _emergency = value ?? false;
                            });
                          },
                        ),

                        // Archived Checkbox
                        AppCheckboxListTile(
                          title: localizations.indicatorDetailArchived,
                          value: _archived,
                          onChanged: (value) {
                            setState(() {
                              _archived = value ?? false;
                            });
                          },
                        ),

                        const SizedBox(height: 32),

                        // Save Button
                        ElevatedButton(
                          onPressed: _isLoading ? null : _saveIndicator,
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
                                  localizations.indicatorEditSave,
                                  style: const TextStyle(
                                    fontSize: 16,
                                    fontWeight: FontWeight.w600,
                                  ),
                                ),
                        ),
                        const SizedBox(height: 16),

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
                            'Cancel',
                            style: TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w600,
                              color: Color(AppConstants.ifrcRed),
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
