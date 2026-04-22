import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../config/app_config.dart';
import '../../config/routes.dart';
import '../../di/service_locator.dart';
import '../../l10n/app_localizations.dart';
import '../../models/shared/indicator.dart';
import '../../models/shared/indicator_level_ids.dart';
import '../../providers/admin/indicator_bank_admin_provider.dart';
import '../../services/api_service.dart';
import '../../utils/admin_screen_view_logging_mixin.dart';
import '../../utils/constants.dart';
import '../../utils/mobile_api_json.dart';
import '../../utils/theme_extensions.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/app_checkbox_list_tile.dart';

class EditIndicatorScreen extends StatefulWidget {
  final int indicatorId;

  const EditIndicatorScreen({
    super.key,
    required this.indicatorId,
  });

  @override
  State<EditIndicatorScreen> createState() => _EditIndicatorScreenState();
}

class _SubsectorRow {
  _SubsectorRow({
    required this.id,
    required this.name,
    required this.sectorId,
  });

  final int id;
  final String name;
  final int sectorId;
}

class _SectorRow {
  _SectorRow({required this.id, required this.name});

  final int id;
  final String name;
}

class _EditIndicatorScreenState extends State<EditIndicatorScreen>
    with AdminScreenViewLoggingMixin {
  @override
  String get adminScreenViewRoutePath =>
      AppRoutes.editIndicator(widget.indicatorId);

  final _formKey = GlobalKey<FormState>();
  final _nameController = TextEditingController();
  final _typeController = TextEditingController();
  final _unitController = TextEditingController();
  final _fdrsController = TextEditingController();
  final _definitionController = TextEditingController();
  final _commentsController = TextEditingController();
  final _relatedProgramsController = TextEditingController();

  final Map<String, TextEditingController> _nameI18nControllers = {};

  bool _emergency = false;
  bool _archived = false;
  bool _canArchive = true;
  bool _isLoading = false;
  bool _isLoadingSectors = false;
  bool _detailReady = false;
  Indicator? _indicator;

  List<String> _translatableLangs = [];

  int? _sectorP;
  int? _sectorS;
  int? _sectorT;
  int? _subP;
  int? _subS;
  int? _subT;

  List<_SectorRow> _sectors = [];
  List<_SubsectorRow> _subsectors = [];

  static const _rtlLangs = {'ar', 'fa', 'he', 'ur'};

  final List<String> _typeOptions = const [
    'Number',
    'Percentage',
    'Text',
    'YesNo',
    'Date',
  ];

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _nameController.dispose();
    _typeController.dispose();
    _unitController.dispose();
    _fdrsController.dispose();
    _definitionController.dispose();
    _commentsController.dispose();
    _relatedProgramsController.dispose();
    for (final c in _nameI18nControllers.values) {
      c.dispose();
    }
    _nameI18nControllers.clear();
    super.dispose();
  }

  void _disposeI18nControllers() {
    for (final c in _nameI18nControllers.values) {
      c.dispose();
    }
    _nameI18nControllers.clear();
  }

  void _applyIndicatorToForm(Indicator ind) {
    _disposeI18nControllers();
    _nameController.text = ind.name ?? '';
    _typeController.text = ind.type ?? '';
    _unitController.text = ind.unit ?? '';
    _fdrsController.text = ind.fdrsKpiCode ?? '';
    _definitionController.text = ind.description ?? '';
    _commentsController.text = ind.comments ?? '';
    _relatedProgramsController.text = ind.relatedPrograms ?? '';
    _emergency = ind.isEmergency;
    _archived = ind.isArchived;
    _canArchive = ind.canArchive;

    _translatableLangs = List<String>.from(ind.translatableLanguages);
    for (final code in _translatableLangs) {
      final lc = code.toLowerCase();
      if (lc == 'en') {
        continue;
      }
      _nameI18nControllers[lc] = TextEditingController(
        text: ind.nameTranslations[lc] ?? '',
      );
    }

    final sl = ind.sectorLevels;
    if (sl != null) {
      _sectorP = sl.primary;
      _sectorS = sl.secondary;
      _sectorT = sl.tertiary;
    } else {
      _sectorP = _sectorS = _sectorT = null;
    }

    final sub = ind.subSectorLevels;
    if (sub != null) {
      _subP = sub.primary;
      _subS = sub.secondary;
      _subT = sub.tertiary;
    } else {
      _subP = _subS = _subT = null;
    }
  }

  Future<void> _load() async {
    setState(() {
      _isLoading = true;
    });

    final provider =
        Provider.of<IndicatorBankAdminProvider>(context, listen: false);
    final indicator = await provider.getIndicatorById(widget.indicatorId);
    if (!mounted) {
      return;
    }

    if (indicator != null) {
      _applyIndicatorToForm(indicator);
      setState(() {
        _indicator = indicator;
        _detailReady = true;
        _isLoading = false;
      });
      await _loadSectors();
    } else {
      setState(() {
        _indicator = null;
        _detailReady = true;
        _isLoading = false;
      });
    }
  }

  Future<void> _loadSectors() async {
    setState(() {
      _isLoadingSectors = true;
    });
    final api = sl<ApiService>();
    try {
      final res = await api.get(AppConfig.mobileSectorsSubsectorsEndpoint);
      if (!mounted) return;
      if (res.statusCode != 200) {
        setState(() => _isLoadingSectors = false);
        return;
      }
      final root = decodeJsonObject(res.body);
      if (!mobileResponseIsSuccess(root)) {
        setState(() => _isLoadingSectors = false);
        return;
      }
      final data = root['data'];
      if (data is! Map<String, dynamic>) {
        setState(() => _isLoadingSectors = false);
        return;
      }
      final list = data['sectors'];
      if (list is! List) {
        setState(() => _isLoadingSectors = false);
        return;
      }
      final sectors = <_SectorRow>[];
      final subsectors = <_SubsectorRow>[];
      for (final raw in list) {
        if (raw is! Map) continue;
        final m = Map<String, dynamic>.from(raw);
        final sid = m['id'];
        final sectorId = sid is int ? sid : int.tryParse('$sid');
        final name = m['name'] as String? ?? '';
        if (sectorId == null) continue;
        sectors.add(_SectorRow(id: sectorId, name: name));
        final subs = m['subsectors'];
        if (subs is! List) continue;
        for (final sraw in subs) {
          if (sraw is! Map) continue;
          final sm = Map<String, dynamic>.from(sraw);
          final suid = sm['id'];
          final subId = suid is int ? suid : int.tryParse('$suid');
          if (subId == null) continue;
          subsectors.add(
            _SubsectorRow(
              id: subId,
              name: sm['name'] as String? ?? '',
              sectorId: sectorId,
            ),
          );
        }
      }
      if (!mounted) return;
      setState(() {
        _sectors = sectors;
        _subsectors = subsectors;
        _isLoadingSectors = false;
        _normalizeLevelSelections();
      });
    } catch (_) {
      if (mounted) {
        setState(() => _isLoadingSectors = false);
      }
    }
  }

  void _normalizeLevelSelections() {
    bool hasSector(int? id) =>
        id != null && _sectors.any((s) => s.id == id);
    bool hasSub(int? id) =>
        id != null && _subsectors.any((s) => s.id == id);
    if (!hasSector(_sectorP)) {
      _sectorP = null;
    }
    if (!hasSector(_sectorS)) {
      _sectorS = null;
    }
    if (!hasSector(_sectorT)) {
      _sectorT = null;
    }
    if (!hasSub(_subP)) {
      _subP = null;
    }
    if (!hasSub(_subS)) {
      _subS = null;
    }
    if (!hasSub(_subT)) {
      _subT = null;
    }
  }

  Map<String, String> _buildNameTranslationsPayload() {
    final nt = <String, String>{};
    for (final code in _translatableLangs) {
      final lc = code.toLowerCase();
      if (lc == 'en') {
        nt['en'] = _nameController.text.trim();
      } else {
        final c = _nameI18nControllers[lc];
        if (c != null) {
          nt[lc] = c.text;
        }
      }
    }
    return nt;
  }

  Map<String, dynamic> _buildSavePayload() {
    final sl = IndicatorLevelIds(
      primary: _sectorP,
      secondary: _sectorS,
      tertiary: _sectorT,
    );
    final subL = IndicatorLevelIds(
      primary: _subP,
      secondary: _subS,
      tertiary: _subT,
    );

    return {
      'name': _nameController.text.trim(),
      'type': _typeController.text.trim(),
      'unit': _unitController.text.trim().isEmpty
          ? null
          : _unitController.text.trim(),
      'fdrs_kpi_code': _fdrsController.text.trim().isEmpty
          ? null
          : _fdrsController.text.trim(),
      'definition': _definitionController.text.trim().isEmpty
          ? null
          : _definitionController.text.trim(),
      'emergency': _emergency,
      'archived': _archived,
      'comments': _commentsController.text.trim().isEmpty
          ? null
          : _commentsController.text.trim(),
      'related_programs': _relatedProgramsController.text.trim().isEmpty
          ? null
          : _relatedProgramsController.text.trim(),
      'name_translations': _buildNameTranslationsPayload(),
      'sector': sl.isEmpty ? <String, dynamic>{} : sl.toJson(),
      'sub_sector': subL.isEmpty ? <String, dynamic>{} : subL.toJson(),
    };
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
    final data = _buildSavePayload();
    final success = await provider.updateIndicator(widget.indicatorId, data);

    if (!mounted) {
      return;
    }

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

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(
        title: localizations.editIndicator,
      ),
      body: _isLoading && !_detailReady
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
                        DropdownButtonFormField<String>(
                          // ignore: deprecated_member_use
                          value: _typeController.text.isEmpty
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
                        TextFormField(
                          controller: _fdrsController,
                          decoration: InputDecoration(
                            labelText:
                                localizations.indicatorEditFdrsKpiLabel,
                            hintText:
                                localizations.indicatorEditFdrsKpiHint,
                            prefixIcon: const Icon(Icons.tag_outlined),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                            filled: true,
                            fillColor: context.lightSurfaceColor,
                          ),
                        ),
                        const SizedBox(height: 16),
                        TextFormField(
                          controller: _definitionController,
                          decoration: InputDecoration(
                            labelText:
                                localizations.indicatorDetailDefinition,
                            hintText:
                                localizations.indicatorEditDefinitionHint,
                            prefixIcon: const Icon(Icons.description_outlined),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                            filled: true,
                            fillColor: context.lightSurfaceColor,
                          ),
                          maxLines: 4,
                        ),
                        if (_translatableLangs.isNotEmpty) ...[
                          const SizedBox(height: 24),
                          Align(
                            alignment: Alignment.centerLeft,
                            child: Text(
                              localizations.indicatorEditMultilingualSection,
                              style: theme.textTheme.titleSmall?.copyWith(
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                          const SizedBox(height: 12),
                          for (final code in _translatableLangs) ...[
                            if (code.toLowerCase() != 'en') ...[
                              TextFormField(
                                controller: _nameI18nControllers[code
                                    .toLowerCase()],
                                textDirection: _rtlLangs.contains(
                                        code.toLowerCase())
                                    ? TextDirection.rtl
                                    : TextDirection.ltr,
                                decoration: InputDecoration(
                                  labelText: localizations
                                      .indicatorEditNameForLanguage(
                                    code.toUpperCase(),
                                  ),
                                  border: OutlineInputBorder(
                                    borderRadius: BorderRadius.circular(8),
                                  ),
                                  filled: true,
                                  fillColor: context.lightSurfaceColor,
                                ),
                              ),
                              const SizedBox(height: 12),
                            ],
                          ],
                        ],
                        const SizedBox(height: 12),
                        if (_isLoadingSectors)
                          const Padding(
                            padding: EdgeInsets.symmetric(vertical: 8),
                            child: LinearProgressIndicator(),
                          ),
                        _sectorDropdownGroup(localizations, theme),
                        const SizedBox(height: 8),
                        _subsectorDropdownGroup(localizations, theme),
                        const SizedBox(height: 16),
                        TextFormField(
                          controller: _relatedProgramsController,
                          decoration: InputDecoration(
                            labelText: localizations
                                .indicatorDetailRelatedPrograms,
                            hintText: localizations
                                .indicatorEditRelatedProgramsHint,
                            prefixIcon: const Icon(Icons.list_outlined),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(8),
                            ),
                            filled: true,
                            fillColor: context.lightSurfaceColor,
                          ),
                        ),
                        const SizedBox(height: 16),
                        TextFormField(
                          controller: _commentsController,
                          decoration: InputDecoration(
                            labelText:
                                localizations.indicatorEditCommentsLabel,
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
                        AppCheckboxListTile(
                          title: localizations.indicatorEditEmergency,
                          value: _emergency,
                          onChanged: (value) {
                            setState(() {
                              _emergency = value ?? false;
                            });
                          },
                        ),
                        AppCheckboxListTile(
                          title: localizations.indicatorDetailArchived,
                          value: _archived,
                          enabled: _canArchive,
                          onChanged: (value) {
                            setState(() {
                              _archived = value ?? false;
                            });
                          },
                        ),
                        const SizedBox(height: 32),
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

  Widget _sectorDropdownGroup(
    AppLocalizations loc,
    ThemeData theme,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          loc.indicatorEditSectorGroup,
          style: theme.textTheme.titleSmall?.copyWith(
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 8),
        _levelDropdown(
          loc,
          loc.indicatorEditSectorLevelPrimary,
          _sectorP,
          (v) => setState(() => _sectorP = v),
          _sectors,
        ),
        const SizedBox(height: 8),
        _levelDropdown(
          loc,
          loc.indicatorEditSectorLevelSecondary,
          _sectorS,
          (v) => setState(() => _sectorS = v),
          _sectors,
        ),
        const SizedBox(height: 8),
        _levelDropdown(
          loc,
          loc.indicatorEditSectorLevelTertiary,
          _sectorT,
          (v) => setState(() => _sectorT = v),
          _sectors,
        ),
      ],
    );
  }

  Widget _subsectorDropdownGroup(
    AppLocalizations loc,
    ThemeData theme,
  ) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          loc.indicatorEditSubsectorGroup,
          style: theme.textTheme.titleSmall?.copyWith(
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: 8),
        _levelDropdown(
          loc,
          loc.indicatorEditSectorLevelPrimary,
          _subP,
          (v) => setState(() => _subP = v),
          null,
        ),
        const SizedBox(height: 8),
        _levelDropdown(
          loc,
          loc.indicatorEditSectorLevelSecondary,
          _subS,
          (v) => setState(() => _subS = v),
          null,
        ),
        const SizedBox(height: 8),
        _levelDropdown(
          loc,
          loc.indicatorEditSectorLevelTertiary,
          _subT,
          (v) => setState(() => _subT = v),
          null,
        ),
      ],
    );
  }

  Widget _levelDropdown(
    AppLocalizations loc,
    String levelLabel,
    int? value,
    void Function(int?) onChanged,
    List<_SectorRow>? sectorOrNull,
  ) {
    final items = <DropdownMenuItem<int?>>[
      DropdownMenuItem<int?>(
        value: null,
        child: Text(loc.indicatorEditSelectNone),
      ),
    ];
    if (sectorOrNull != null) {
      for (final s in sectorOrNull) {
        items.add(
          DropdownMenuItem<int?>(
            value: s.id,
            child: Text(
              s.name,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        );
      }
    } else {
      for (final s in _subsectors) {
        items.add(
          DropdownMenuItem<int?>(
            value: s.id,
            child: Text(
              s.name,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        );
      }
    }

    return DropdownButtonFormField<int?>(
      // ignore: deprecated_member_use
      value: value,
      decoration: InputDecoration(
        labelText: levelLabel,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(8),
        ),
        filled: true,
        fillColor: context.lightSurfaceColor,
      ),
      isExpanded: true,
      items: items,
      onChanged: onChanged,
    );
  }
}
