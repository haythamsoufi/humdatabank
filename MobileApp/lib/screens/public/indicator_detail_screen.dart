import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/public/indicator_bank_provider.dart';
import '../../models/indicator_bank/indicator.dart';
import '../../models/indicator_bank/sector.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/app_bar.dart';
import '../../providers/shared/auth_provider.dart';
import '../../providers/shared/language_provider.dart';
import '../../l10n/app_localizations.dart';
import '../../utils/network_availability.dart';

class IndicatorDetailScreen extends StatefulWidget {
  final int indicatorId;

  const IndicatorDetailScreen({
    super.key,
    required this.indicatorId,
  });

  @override
  State<IndicatorDetailScreen> createState() => _IndicatorDetailScreenState();
}

class _IndicatorDetailScreenState extends State<IndicatorDetailScreen> {
  Indicator? _indicator;
  bool _isLoading = true;
  String? _error;
  String? _lastLanguage;

  @override
  void initState() {
    super.initState();
    _loadIndicatorDetails();
  }

  Future<void> _loadIndicatorDetails() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      final provider =
          Provider.of<IndicatorBankProvider>(context, listen: false);
      final languageProvider =
          Provider.of<LanguageProvider>(context, listen: false);
      await provider.loadData(
        locale: languageProvider.currentLanguage,
        forceRefresh: false,
      );
      if (!mounted) return;
      final indicators = provider.allIndicators;

      // Try to find indicator in cached list first
      final cachedIndicator = indicators.firstWhere(
        (ind) => ind.id == widget.indicatorId,
        orElse: () => Indicator(
          id: -1,
          name: '',
        ),
      );

      if (cachedIndicator.id == widget.indicatorId) {
        setState(() {
          _indicator = cachedIndicator;
          _isLoading = false;
          _lastLanguage = languageProvider.currentLanguage;
        });
      } else {
        // If not found in cache, fetch from API
        await _fetchIndicatorFromApi(languageProvider.currentLanguage);
      }
    } catch (e) {
      setState(() {
        _error = AppLocalizations.of(context)!.indicatorDetailError;
        _isLoading = false;
      });
    }
  }

  Future<void> _fetchIndicatorFromApi(String locale) async {
    if (shouldDeferRemoteFetch) {
      if (!mounted) return;
      setState(() {
        _isLoading = false;
        _error = AppLocalizations.of(context)!.offlineNoInternet;
      });
      return;
    }
    try {
      final provider =
          Provider.of<IndicatorBankProvider>(context, listen: false);
      final indicatorJson =
          await provider.fetchIndicatorDetailMap(widget.indicatorId, locale);

      if (indicatorJson != null) {
        final indicator = Indicator.fromJson(indicatorJson);

        // Get provider for sector lookups (captured before await above)

        // Process localized fields
        final processedIndicator =
            _processIndicatorWithLocale(indicatorJson, indicator, locale, provider);

        setState(() {
          _indicator = processedIndicator;
          _isLoading = false;
          _lastLanguage = locale;
        });
      } else {
        setState(() {
          _error = AppLocalizations.of(context)!.indicatorDetailNotFound;
          _isLoading = false;
        });
      }
    } catch (e) {
      setState(() {
        _error = AppLocalizations.of(context)!.indicatorDetailError;
        _isLoading = false;
      });
    }
  }

  String _localizeType(String type, String locale) {
    // Map of type translations
    final typeTranslations = {
      'number': {
        'en': 'Number',
        'fr': 'Nombre',
        'es': 'Número',
        'ar': 'رقم',
        'zh': '数字',
        'ru': 'Число',
        'hi': 'संख्या',
      },
      'percentage': {
        'en': 'Percentage',
        'fr': 'Pourcentage',
        'es': 'Porcentaje',
        'ar': 'نسبة مئوية',
        'zh': '百分比',
        'ru': 'Процент',
        'hi': 'प्रतिशत',
      },
      'text': {
        'en': 'Text',
        'fr': 'Texte',
        'es': 'Texto',
        'ar': 'نص',
        'zh': '文本',
        'ru': 'Текст',
        'hi': 'पाठ',
      },
      'yesno': {
        'en': 'Yes/No',
        'fr': 'Oui/Non',
        'es': 'Sí/No',
        'ar': 'نعم/لا',
        'zh': '是/否',
        'ru': 'Да/Нет',
        'hi': 'हाँ/नहीं',
      },
      'date': {
        'en': 'Date',
        'fr': 'Date',
        'es': 'Fecha',
        'ar': 'تاريخ',
        'zh': '日期',
        'ru': 'Дата',
        'hi': 'तारीख',
      },
      'boolean': {
        'en': 'Boolean',
        'fr': 'Booléen',
        'es': 'Booleano',
        'ar': 'منطقي',
        'zh': '布尔值',
        'ru': 'Логический',
        'hi': 'बूलियन',
      },
      'integer': {
        'en': 'Integer',
        'fr': 'Entier',
        'es': 'Entero',
        'ar': 'عدد صحيح',
        'zh': '整数',
        'ru': 'Целое число',
        'hi': 'पूर्णांक',
      },
      'decimal': {
        'en': 'Decimal',
        'fr': 'Décimal',
        'es': 'Decimal',
        'ar': 'عشري',
        'zh': '小数',
        'ru': 'Десятичный',
        'hi': 'दशमलव',
      },
    };

    final typeKey = type.toLowerCase();
    final translations = typeTranslations[typeKey];
    if (translations != null) {
      return translations[locale] ?? translations['en'] ?? type;
    }
    return type;
  }

  String _localizeUnit(String unit, String locale) {
    // Map of unit translations
    final unitTranslations = {
      'people': {
        'en': 'People',
        'fr': 'Personnes',
        'es': 'Personas',
        'ar': 'أشخاص',
        'zh': '人',
        'ru': 'Человек',
        'hi': 'लोग',
      },
      'households': {
        'en': 'Households',
        'fr': 'Ménages',
        'es': 'Hogares',
        'ar': 'أسر',
        'zh': '家庭',
        'ru': 'Домохозяйства',
        'hi': 'परिवार',
      },
      'percent': {
        'en': 'Percent',
        'fr': 'Pourcent',
        'es': 'Porcentaje',
        'ar': 'في المئة',
        'zh': '百分比',
        'ru': 'Процент',
        'hi': 'प्रतिशत',
      },
      '%': {
        'en': '%',
        'fr': '%',
        'es': '%',
        'ar': '%',
        'zh': '%',
        'ru': '%',
        'hi': '%',
      },
      'units': {
        'en': 'Units',
        'fr': 'Unités',
        'es': 'Unidades',
        'ar': 'وحدات',
        'zh': '单位',
        'ru': 'Единицы',
        'hi': 'इकाइयां',
      },
      'volunteers': {
        'en': 'Volunteers',
        'fr': 'Bénévoles',
        'es': 'Voluntarios',
        'ar': 'متطوعون',
        'zh': '志愿者',
        'ru': 'Волонтеры',
        'hi': 'स्वयंसेवक',
      },
      'beneficiaries': {
        'en': 'Beneficiaries',
        'fr': 'Bénéficiaires',
        'es': 'Beneficiarios',
        'ar': 'مستفيدون',
        'zh': '受益人',
        'ru': 'Бенефициары',
        'hi': 'लाभार्थी',
      },
      'staff': {
        'en': 'Staff',
        'fr': 'Personnel',
        'es': 'Personal',
        'ar': 'موظفون',
        'zh': '员工',
        'ru': 'Персонал',
        'hi': 'कर्मचारी',
      },
      'kg': {
        'en': 'kg',
        'fr': 'kg',
        'es': 'kg',
        'ar': 'كجم',
        'zh': '公斤',
        'ru': 'кг',
        'hi': 'किलो',
      },
      'liters': {
        'en': 'Liters',
        'fr': 'Litres',
        'es': 'Litros',
        'ar': 'لترات',
        'zh': '升',
        'ru': 'Литры',
        'hi': 'लीटर',
      },
    };

    final unitKey = unit.toLowerCase();
    final translations = unitTranslations[unitKey];
    if (translations != null) {
      return translations[locale] ?? translations['en'] ?? unit;
    }
    return unit;
  }

  Indicator _processIndicatorWithLocale(
    Map<String, dynamic> indicatorMap,
    Indicator indicator,
    String locale,
    IndicatorBankProvider provider,
  ) {
    // Extract localized name from name_translations dict (keys are ISO locale codes)
    String? localizedName;
    if (locale != 'en') {
      final nameTranslations =
          indicatorMap['name_translations'] as Map<String, dynamic>?;
      localizedName = nameTranslations?[locale] as String?;
    }

    // Extract localized definition from definition_translations (keys are ISO locale codes)
    String? localizedDefinition;
    final definitionTranslations = indicatorMap['definition_translations'];
    if (definitionTranslations is Map<String, dynamic>) {
      localizedDefinition = definitionTranslations[locale] as String?;
    }

    // Get sectors from provider to look up localized names
    final sectors = provider.sectors;

    // Map sector to include localized names
    dynamic localizedSector = indicator.sector;
    if (indicator.sector is Map) {
      final sectorMap = indicator.sector as Map<String, dynamic>;
      final primarySectorName = sectorMap['primary'] as String?;
      if (primarySectorName != null) {
        Sector? foundSector;
        try {
          foundSector = sectors.firstWhere(
            (s) => s.name == primarySectorName,
          );
        } catch (e) {
          // Sector not found, will use fallback
        }
        final displayName = foundSector?.displayName ?? primarySectorName;
        localizedSector = {
          'primary': primarySectorName,
          'secondary': sectorMap['secondary'],
          'tertiary': sectorMap['tertiary'],
          'localized_name': displayName,
          'name': primarySectorName,
        };
      }
    } else if (indicator.sector is String) {
      final sectorName = indicator.sector as String;
      Sector? foundSector;
      try {
        foundSector = sectors.firstWhere(
          (s) => s.name == sectorName,
        );
      } catch (e) {
        // Sector not found, will use fallback
      }
      final displayName = foundSector?.displayName ?? sectorName;
      localizedSector = {
        'primary': sectorName,
        'localized_name': displayName,
        'name': sectorName,
      };
    }

    // Map subsector to include localized names
    dynamic localizedSubSector = indicator.subSector;
    if (indicator.subSector is Map) {
      final subsectorMap = indicator.subSector as Map<String, dynamic>;
      final primarySubSectorName = subsectorMap['primary'] as String?;
      if (primarySubSectorName != null) {
        SubSector? foundSubSector;
        for (final sector in sectors) {
          try {
            foundSubSector = sector.subsectors.firstWhere(
              (s) => s.name == primarySubSectorName,
            );
            break;
                    } catch (e) {
            // Continue searching in next sector
          }
        }
        final displayName = foundSubSector?.displayName ?? primarySubSectorName;
        localizedSubSector = {
          'primary': primarySubSectorName,
          'secondary': subsectorMap['secondary'],
          'tertiary': subsectorMap['tertiary'],
          'localized_name': displayName,
          'name': primarySubSectorName,
        };
      }
    } else if (indicator.subSector is String) {
      final subSectorName = indicator.subSector as String;
      SubSector? foundSubSector;
      for (final sector in sectors) {
        try {
          foundSubSector = sector.subsectors.firstWhere(
            (s) => s.name == subSectorName,
          );
          break;
                } catch (e) {
          // Continue searching in next sector
        }
      }
      final displayName = foundSubSector?.displayName ?? subSectorName;
      localizedSubSector = {
        'primary': subSectorName,
        'localized_name': displayName,
        'name': subSectorName,
      };
    }

    // Extract localized type and unit from API response
    String? localizedType = indicatorMap['localized_type'] as String?;
    String? localizedUnit = indicatorMap['localized_unit'] as String?;

    // If API didn't provide localized values, use client-side localization
    if (localizedType == null && indicator.type != null) {
      localizedType = _localizeType(indicator.type!, locale);
    }
    if (localizedUnit == null && indicator.unit != null) {
      localizedUnit = _localizeUnit(indicator.unit!, locale);
    }

    return Indicator(
      id: indicator.id,
      name: indicator.name,
      localizedName: localizedName,
      definition: indicator.definition,
      localizedDefinition: localizedDefinition ?? indicator.localizedDefinition,
      type: indicator.type,
      localizedType: localizedType ?? indicator.localizedType,
      unit: indicator.unit,
      localizedUnit: localizedUnit ?? indicator.localizedUnit,
      sector: localizedSector,
      subSector: localizedSubSector,
      emergency: indicator.emergency,
      relatedPrograms: indicator.relatedPrograms,
      archived: indicator.archived,
    );
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;

    return Consumer2<AuthProvider, LanguageProvider>(
      builder: (context, authProvider, languageProvider, child) {
        // Reload indicator when language changes — always re-fetch from API
        // to avoid serving stale cached data in the old language.
        final currentLanguage = languageProvider.currentLanguage;
        if (_lastLanguage != null && _lastLanguage != currentLanguage) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            _fetchIndicatorFromApi(currentLanguage);
          });
        }
        final isAuthenticated = authProvider.isAuthenticated;
        // For non-authenticated users: Indicator Bank is at index 1
        // For authenticated users: Indicator Bank is not in the bottom nav
        final currentNavIndex = isAuthenticated ? -1 : 1;

        final theme = Theme.of(context);
        return Scaffold(
          backgroundColor: theme.scaffoldBackgroundColor,
          appBar: AppAppBar(
            title: localizations.indicatorDetailTitle,
          ),
          body: ColoredBox(
            color: theme.scaffoldBackgroundColor,
            child: _isLoading
                ? Center(
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
                          localizations.indicatorDetailLoading,
                          style: TextStyle(
                            fontSize: 14,
                            color: context.textSecondaryColor,
                          ),
                        ),
                      ],
                    ),
                  )
                : _error != null
                    ? Center(
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
                                localizations.indicatorDetailError,
                                style: TextStyle(
                                  fontSize: 18,
                                  fontWeight: FontWeight.w600,
                                  color: context.textColor,
                                ),
                              ),
                              const SizedBox(height: 8),
                              Text(
                                _error!,
                                textAlign: TextAlign.center,
                                style: TextStyle(
                                  fontSize: 14,
                                  color: context.textSecondaryColor,
                                ),
                              ),
                              const SizedBox(height: 24),
                              OutlinedButton.icon(
                                onPressed: () {
                                  Navigator.of(context).pop();
                                },
                                icon: const Icon(Icons.arrow_back, size: 18),
                                label:
                                    Text(localizations.indicatorDetailGoBack),
                                style: OutlinedButton.styleFrom(
                                  foregroundColor:
                                      Color(AppConstants.ifrcRed),
                                  side: BorderSide(
                                    color: Color(AppConstants.ifrcRed),
                                  ),
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 24,
                                    vertical: 12,
                                  ),
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(8),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      )
                    : _indicator == null
                        ? Center(
                            child: Text(
                              localizations.indicatorDetailNotFound,
                              style: TextStyle(
                                fontSize: 16,
                                color: context.textSecondaryColor,
                              ),
                            ),
                          )
                        : SingleChildScrollView(
                            padding: EdgeInsets.symmetric(
                              horizontal:
                                  MediaQuery.of(context).size.width > 600
                                      ? 32
                                      : 20,
                              vertical: 20,
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                // Indicator Name
                                Text(
                                  _indicator!.displayName,
                                  style: TextStyle(
                                    fontSize: 28,
                                    fontWeight: FontWeight.bold,
                                    color: context.navyTextColor,
                                    letterSpacing: -0.5,
                                    height: 1.2,
                                  ),
                                ),
                                const SizedBox(height: 24),
                                // Definition
                                if (_indicator!.displayDefinition.isNotEmpty)
                                  Card(
                                    elevation: 0,
                                    shape: RoundedRectangleBorder(
                                      borderRadius: BorderRadius.circular(
                                          AppConstants.radiusLarge),
                                    ),
                                    shadowColor: Theme.of(context).ambientShadow(
                                        lightOpacity: 0.05, darkOpacity: 0.3),
                                    child: Padding(
                                      padding: const EdgeInsets.all(20),
                                      child: Column(
                                        crossAxisAlignment:
                                            CrossAxisAlignment.start,
                                        children: [
                                          Row(
                                            children: [
                                              Container(
                                                padding:
                                                    const EdgeInsets.all(8),
                                                decoration: BoxDecoration(
                                                  color: context
                                                      .navyBackgroundColor(
                                                          opacity: 0.1),
                                                  borderRadius:
                                                      BorderRadius.circular(
                                                          AppConstants
                                                              .radiusMedium),
                                                ),
                                                child: Icon(
                                                  Icons.description_outlined,
                                                  size: 18,
                                                  color: context.navyIconColor,
                                                ),
                                              ),
                                              const SizedBox(width: 12),
                                              Text(
                                                localizations
                                                    .indicatorDetailDefinition,
                                                style: TextStyle(
                                                  fontSize: 16,
                                                  fontWeight: FontWeight.w600,
                                                  color: context.navyTextColor,
                                                ),
                                              ),
                                            ],
                                          ),
                                          const SizedBox(height: 16),
                                          Text(
                                            _indicator!.displayDefinition,
                                            style: TextStyle(
                                              fontSize: 14,
                                              color: context.textColor,
                                              height: 1.6,
                                            ),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ),
                                const SizedBox(height: 16),
                                // Details Grid
                                Card(
                                  elevation: 0,
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(
                                        AppConstants.radiusLarge),
                                  ),
                                  shadowColor: Theme.of(context).ambientShadow(
                                      lightOpacity: 0.05, darkOpacity: 0.3),
                                  child: Column(
                                    children: [
                                      Container(
                                        padding: const EdgeInsets.all(20),
                                        decoration: BoxDecoration(
                                          border: Border(
                                            bottom: BorderSide(
                                              color: context.borderColor,
                                              width: 0.5,
                                            ),
                                          ),
                                        ),
                                        child: Row(
                                          children: [
                                            Container(
                                              padding: const EdgeInsets.all(8),
                                              decoration: BoxDecoration(
                                                color:
                                                    context.navyBackgroundColor(
                                                        opacity: 0.1),
                                                borderRadius:
                                                    BorderRadius.circular(
                                                        AppConstants
                                                            .radiusMedium),
                                              ),
                                              child: Icon(
                                                Icons.info_outline,
                                                size: 18,
                                                color: context.navyIconColor,
                                              ),
                                            ),
                                            const SizedBox(width: 12),
                                            Text(
                                              localizations
                                                  .indicatorDetailDetails,
                                              style: TextStyle(
                                                fontSize: 16,
                                                fontWeight: FontWeight.w600,
                                                color: context.navyTextColor,
                                              ),
                                            ),
                                          ],
                                        ),
                                      ),
                                      Padding(
                                        padding: const EdgeInsets.all(20),
                                        child: Column(
                                          children: [
                                            _buildDetailRow(
                                              localizations.indicatorDetailType,
                                              _indicator!.displayType,
                                              isFirst: true,
                                            ),
                                            if (_indicator!
                                                .displayUnit.isNotEmpty)
                                              _buildDetailRow(
                                                localizations
                                                    .indicatorDetailUnit,
                                                _indicator!.displayUnit,
                                              ),
                                            if (_indicator!
                                                .displaySector.isNotEmpty)
                                              _buildDetailRow(
                                                localizations
                                                    .indicatorDetailSector,
                                                _indicator!.displaySector,
                                              ),
                                            if (_indicator!
                                                .displaySubSector.isNotEmpty)
                                              _buildDetailRow(
                                                localizations
                                                    .indicatorDetailSubsector,
                                                _indicator!.displaySubSector,
                                              ),
                                            if (_indicator!.emergency == true)
                                              _buildDetailRow(
                                                localizations
                                                    .indicatorDetailEmergencyContext,
                                                localizations
                                                    .indicatorDetailYes,
                                              ),
                                            if (_indicator!.relatedPrograms !=
                                                    null &&
                                                _indicator!.relatedPrograms!
                                                    .isNotEmpty)
                                              _buildDetailRow(
                                                localizations
                                                    .indicatorDetailRelatedPrograms,
                                                _indicator!.relatedPrograms!
                                                    .join(', '),
                                              ),
                                            if (_indicator!.archived)
                                              _buildDetailRow(
                                                localizations
                                                    .indicatorDetailStatus,
                                                localizations
                                                    .indicatorDetailArchived,
                                                isLast: true,
                                              ),
                                          ],
                                        ),
                                      ),
                                    ],
                                  ),
                                ),
                                const SizedBox(
                                    height: 100), // Space for bottom nav
                              ],
                            ),
                          ),
          ),
          bottomNavigationBar: AppBottomNavigationBar(
            currentIndex: currentNavIndex,
            // onTap is optional - if not provided, uses NavigationHelper.navigateToMainTab by default
          ),
        );
      },
    );
  }

  Widget _buildDetailRow(String label, String value,
      {bool isFirst = false, bool isLast = false}) {
    return Column(
      children: [
        if (!isFirst)
          Divider(
            height: 1,
            thickness: 0.5,
            color: context.borderColor,
          ),
        Padding(
          padding: const EdgeInsets.symmetric(vertical: 16),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(
                width: 140,
                child: Text(
                  label,
                  style: TextStyle(
                    fontWeight: FontWeight.w600,
                    color: context.textSecondaryColor,
                    fontSize: 14,
                  ),
                ),
              ),
              Expanded(
                child: Text(
                  value,
                  style: TextStyle(
                    fontSize: 14,
                    color: context.textColor,
                    height: 1.4,
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
