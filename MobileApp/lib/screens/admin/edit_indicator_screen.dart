import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/admin/indicator_bank_admin_provider.dart';
import '../../models/shared/indicator.dart';
import '../../utils/theme_extensions.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/app_checkbox_list_tile.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../l10n/app_localizations.dart';

class EditIndicatorScreen extends StatefulWidget {
  final int indicatorId;

  const EditIndicatorScreen({
    super.key,
    required this.indicatorId,
  });

  @override
  State<EditIndicatorScreen> createState() => _EditIndicatorScreenState();
}

class _EditIndicatorScreenState extends State<EditIndicatorScreen> {
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
          _unitController.text = '';
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
        title: localizations.editIndicator ?? 'Edit Indicator',
      ),
      body: _isLoading && _indicator == null
          ? Center(
              child: CircularProgressIndicator(
                valueColor: AlwaysStoppedAnimation<Color>(
                  theme.colorScheme.primary,
                ),
              ),
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
                            labelText: 'Indicator Name *',
                            hintText: 'Enter indicator name',
                            prefixIcon: const Icon(Icons.label_outline),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                            filled: true,
                            fillColor: context.lightSurfaceColor,
                          ),
                          validator: (value) {
                            if (value == null || value.trim().isEmpty) {
                              return 'Indicator name is required';
                            }
                            return null;
                          },
                        ),
                        const SizedBox(height: 16),

                        // Type Field (Dropdown)
                        DropdownButtonFormField<String>(
                          value: _typeController.text.isEmpty
                              ? null
                              : _typeController.text,
                          decoration: InputDecoration(
                            labelText: 'Type *',
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
                              return 'Type is required';
                            }
                            return null;
                          },
                        ),
                        const SizedBox(height: 16),

                        // Unit Field
                        TextFormField(
                          controller: _unitController,
                          decoration: InputDecoration(
                            labelText: 'Unit',
                            hintText: 'e.g., People, %, Items',
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
                            labelText: 'Definition',
                            hintText: 'Detailed definition of this indicator',
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
                            labelText: 'Sector',
                            hintText: 'Enter sector',
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
                            labelText: 'Sub-Sector',
                            hintText: 'Enter sub-sector',
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
                            labelText: 'Related Programs',
                            hintText:
                                'Comma-separated list of related programs',
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
                            labelText: 'Comments',
                            hintText: 'Internal comments about this indicator',
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
                          title: 'Emergency Indicator',
                          value: _emergency,
                          onChanged: (value) {
                            setState(() {
                              _emergency = value ?? false;
                            });
                          },
                        ),

                        // Archived Checkbox
                        AppCheckboxListTile(
                          title: 'Archived',
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
                              : const Text(
                                  'Save Indicator',
                                  style: TextStyle(
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
