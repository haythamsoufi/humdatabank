import 'package:flutter/foundation.dart';
import 'dart:convert';
import '../../services/api_service.dart';
import '../../services/error_handler.dart';
import '../../models/indicator_bank/indicator.dart';
import '../../models/indicator_bank/sector.dart';
import '../../config/app_config.dart';
import '../../utils/debug_logger.dart';

class RateLimitException implements Exception {
  final String message;
  final Duration? retryAfter;

  RateLimitException(this.message, {this.retryAfter});

  @override
  String toString() => message;
}

class IndicatorBankProvider with ChangeNotifier {
  final ApiService _api = ApiService();
  final ErrorHandler _errorHandler = ErrorHandler();
  static const Duration _cacheDuration = Duration(minutes: 20);

  List<Indicator> _allIndicators = [];
  List<Indicator> _filteredIndicators = [];
  List<Sector> _sectors = [];
  bool _isLoading = false;
  String? _error;
  String _currentLocale = 'en';
  DateTime? _lastFullLoad;
  String _lastLoadedLocale = 'en';
  Future<void>? _ongoingLoad;
  DateTime? _rateLimitResetAt;
  String? _rateLimitMessage;

  // Filter state
  String _searchTerm = '';
  String _selectedType = '';
  String _selectedSector = '';
  String _selectedSubSector = '';
  String _selectedEmergency = '';
  bool _archived = false;

  // View mode: 'grid' or 'table'
  String _viewMode = 'grid';

  // Getters
  List<Indicator> get allIndicators => _allIndicators;
  List<Indicator> get filteredIndicators => _filteredIndicators;
  List<Sector> get sectors => _sectors;
  bool get isLoading => _isLoading;
  String? get error => _error;
  String get searchTerm => _searchTerm;
  String get selectedType => _selectedType;
  String get selectedSector => _selectedSector;
  String get selectedSubSector => _selectedSubSector;
  String get selectedEmergency => _selectedEmergency;
  bool get archived => _archived;
  String get viewMode => _viewMode;

  // Get unique types for filter dropdown
  List<String> get types {
    final typeSet = <String>{};
    for (final indicator in _allIndicators) {
      if (indicator.type != null && indicator.type!.isNotEmpty) {
        typeSet.add(indicator.type!);
      }
    }
    return typeSet.toList()..sort();
  }

  // Get sectors with indicator counts
  List<Sector> get sectorsWithCounts {
    final sectorCounts = <String, int>{};
    final subsectorCounts = <String, int>{};

    // Count indicators per sector and subsector
    for (final indicator in _allIndicators) {
      final sectorName = indicator.displaySector;
      if (sectorName.isNotEmpty) {
        sectorCounts[sectorName] = (sectorCounts[sectorName] ?? 0) + 1;
      }

      final subsectorName = indicator.displaySubSector;
      if (subsectorName.isNotEmpty) {
        subsectorCounts[subsectorName] =
            (subsectorCounts[subsectorName] ?? 0) + 1;
      }
    }

    // Return sectors as-is (counts are calculated in the UI)
    return _sectors;
  }

  // Get indicator count for a sector
  // sectorName should be the English name (s.name), not the localized name
  int getSectorIndicatorCount(String sectorName) {
    return _allIndicators.where((ind) {
      // Compare using the English sector name, not the localized display name
      if (ind.sector == null) return false;
      if (ind.sector is String) {
        return (ind.sector as String) == sectorName;
      }
      if (ind.sector is Map) {
        final sectorMap = ind.sector as Map<String, dynamic>;
        final primarySectorName = sectorMap['primary'] as String?;
        return primarySectorName == sectorName;
      }
      return false;
    }).length;
  }

  Future<void> loadData(
      {String locale = 'en', bool forceRefresh = false}) async {
    _currentLocale = locale;

    // If we already have fresh data for this locale and refresh is not forced, reuse it
    if (!forceRefresh && _hasFreshDataForLocale(locale)) {
      _error = null;
      _applyFilters();
      notifyListeners();
      return;
    }

    // Wait for any in-flight load to finish before deciding if we still need to fetch
    if (_ongoingLoad != null) {
      await _ongoingLoad;
      if (!forceRefresh && _hasFreshDataForLocale(locale)) {
        _error = null;
        _applyFilters();
        notifyListeners();
        return;
      }
    }

    // Respect server-side rate limit window
    if (_isRateLimited()) {
      _error = _rateLimitMessage ??
          'Indicator Bank is temporarily unavailable. Please try again soon.';
      if (_allIndicators.isNotEmpty) {
        _applyFilters();
      }
      notifyListeners();
      return;
    }

    final loadFuture = _performFullLoad(locale);
    _ongoingLoad = loadFuture;
    try {
      await loadFuture;
    } finally {
      _ongoingLoad = null;
    }
  }

  Future<void> _performFullLoad(String locale) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      await _loadSectors(locale);
      await _loadIndicators(
        search: '',
        type: '',
        sector: '',
        subSector: '',
        emergency: '',
        archived: false,
        locale: locale,
      );

      _applyFilters();
      _lastFullLoad = DateTime.now();
      _lastLoadedLocale = locale;
      _clearRateLimitState();
    } on RateLimitException catch (e) {
      _error = e.message;
      DebugLogger.logWarn(
        'INDICATOR_BANK',
        'Rate limit while loading indicators: ${e.retryAfter ?? 'unknown retry window'}',
      );
      if (_allIndicators.isNotEmpty) {
        _applyFilters();
      }
    } catch (e, stackTrace) {
      final error = _errorHandler.parseError(
        error: e,
        stackTrace: stackTrace,
        context: 'Load Indicator Bank Data',
      );
      _error = error.getUserMessage();
      _errorHandler.logError(error);
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> _loadSectors(String locale) async {
    try {
      final response = await _api.get(
        '/api/v1/sectors-subsectors',
        includeAuth: false,
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        final sectorsRaw = (data['sectors'] as List<dynamic>?) ?? [];

        // Process localized names based on locale from raw JSON
        _sectors = sectorsRaw.map((sectorJson) {
          final sectorMap = sectorJson as Map<String, dynamic>;
          final sector = Sector.fromJson(sectorMap);

          // Extract localized name from multilingual_names
          final localizedName = _getLocalizedField(
            sectorMap,
            'multilingual_names',
            locale,
            sector.name,
          );

          final subsectorsRaw =
              (sectorMap['subsectors'] as List<dynamic>?) ?? [];
          final subsectors = subsectorsRaw.map((subsectorJson) {
            final subsectorMap = subsectorJson as Map<String, dynamic>;
            final subsector = SubSector.fromJson(subsectorMap);

            // Extract localized name from multilingual_names
            final subLocalizedName = _getLocalizedField(
              subsectorMap,
              'multilingual_names',
              locale,
              subsector.name,
            );

            return SubSector(
              id: subsector.id,
              name: subsector.name,
              localizedName: subLocalizedName,
              description: subsector.description,
              localizedDescription: subsector.localizedDescription,
              logoUrl: subsector.logoUrl,
              displayOrder: subsector.displayOrder,
              sectorId: subsector.sectorId,
            );
          }).toList();

          return Sector(
            id: sector.id,
            name: sector.name,
            localizedName: localizedName,
            description: sector.description,
            localizedDescription: sector.localizedDescription,
            logoUrl: sector.logoUrl,
            displayOrder: sector.displayOrder,
            subsectors: subsectors,
          );
        }).toList();

        // Sort by display order
        _sectors.sort((a, b) {
          if (a.displayOrder != b.displayOrder) {
            return a.displayOrder.compareTo(b.displayOrder);
          }
          return a.displayName.compareTo(b.displayName);
        });
      } else {
        final error = _errorHandler.parseError(
          error: Exception('HTTP ${response.statusCode}'),
          response: response,
          context: 'Load Sectors',
        );
        _errorHandler.logError(error);
        throw Exception(error.getUserMessage());
      }
    } catch (e, stackTrace) {
      final error = _errorHandler.parseError(
        error: e,
        stackTrace: stackTrace,
        context: 'Load Sectors',
      );
      _errorHandler.logError(error);
      rethrow;
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

  String _getLocalizedField(
    dynamic obj,
    String field,
    String locale,
    String fallback,
  ) {
    if (obj == null) return fallback;

    // Map Flutter locale codes to backend language names
    final localeMap = {
      'en': null, // English is the default
      'fr': 'french',
      'es': 'spanish',
      'ar': 'arabic',
      'zh': 'chinese',
      'ru': 'russian',
      'hi': 'hindi',
    };

    final backendLocale = localeMap[locale];

    // For English, return the default name
    if (locale == 'en' || backendLocale == null) {
      return fallback;
    }

    // Try to get from multilingual_names field
    if (field == 'multilingual_names') {
      try {
        if (obj is Map<String, dynamic>) {
          final multilingualNames = obj['multilingual_names'];
          if (multilingualNames is Map<String, dynamic>) {
            final localizedValue = multilingualNames[backendLocale];
            if (localizedValue != null &&
                localizedValue.toString().isNotEmpty) {
              return localizedValue.toString();
            }
          }
        }
      } catch (e) {
        DebugLogger.logWarn(
            'INDICATOR_BANK', 'Error extracting multilingual_names: $e');
      }
    }

    return fallback;
  }

  bool _hasFreshDataForLocale(String locale) {
    if (_allIndicators.isEmpty) return false;
    if (_lastFullLoad == null) return false;
    if (_lastLoadedLocale != locale) return false;
    return DateTime.now().difference(_lastFullLoad!) < _cacheDuration;
  }

  bool _isRateLimited() {
    if (_rateLimitResetAt == null) return false;
    return DateTime.now().isBefore(_rateLimitResetAt!);
  }

  Duration? _parseRetryAfter(String? rawHeader) {
    if (rawHeader == null) return null;
    final trimmed = rawHeader.trim();

    final seconds = int.tryParse(trimmed);
    if (seconds != null) {
      return Duration(seconds: seconds);
    }

    final retryDate = DateTime.tryParse(trimmed);
    if (retryDate != null) {
      final diff = retryDate.toUtc().difference(DateTime.now().toUtc());
      if (diff.isNegative) {
        return Duration.zero;
      }
      return diff;
    }

    return null;
  }

  void _updateRateLimitState(Duration? retryAfter) {
    final waitDuration = retryAfter ?? const Duration(hours: 1);
    _rateLimitResetAt = DateTime.now().add(waitDuration);
    final readable = _formatDuration(waitDuration);
    _rateLimitMessage =
        'Indicator Bank is temporarily unavailable due to high traffic. Please try again in $readable.';
    DebugLogger.logWarn(
      'INDICATOR_BANK',
      'Rate limit triggered. Retry after $readable',
    );
  }

  void _clearRateLimitState() {
    _rateLimitResetAt = null;
    _rateLimitMessage = null;
  }

  String _formatDuration(Duration duration) {
    if (duration.inHours >= 1) {
      final hours = duration.inHours;
      final minutes = duration.inMinutes.remainder(60);
      if (minutes == 0) {
        return '$hours ${hours == 1 ? 'hour' : 'hours'}';
      }
      return '$hours ${hours == 1 ? 'hour' : 'hours'} '
          '$minutes ${minutes == 1 ? 'minute' : 'minutes'}';
    }

    if (duration.inMinutes >= 1) {
      final minutes = duration.inMinutes;
      return '$minutes ${minutes == 1 ? 'minute' : 'minutes'}';
    }

    final seconds = duration.inSeconds <= 0 ? 1 : duration.inSeconds;
    return '$seconds ${seconds == 1 ? 'second' : 'seconds'}';
  }

  Future<void> _loadIndicators({
    required String search,
    required String type,
    required String sector,
    required String subSector,
    required String emergency,
    required bool archived,
    String locale = 'en',
  }) async {
    try {
      final queryParams = <String, String>{
        'api_key': AppConfig.apiKey,
        'archived': archived.toString(),
        'locale': locale, // Pass locale for localized type and unit
      };

      if (search.isNotEmpty) {
        queryParams['search'] = search;
      }
      if (type.isNotEmpty) {
        queryParams['type'] = type;
      }
      if (sector.isNotEmpty) {
        queryParams['sector'] = sector;
      }
      if (subSector.isNotEmpty) {
        queryParams['sub_sector'] = subSector;
      }
      if (emergency.isNotEmpty) {
        queryParams['emergency'] = emergency;
      }

      final response = await _api.get(
        '/api/v1/indicator-bank',
        queryParams: queryParams,
        includeAuth: false,
        timeout: const Duration(seconds: 30), // Increased timeout for large indicator datasets
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body) as Map<String, dynamic>;
        final indicatorsRaw = (data['indicators'] as List<dynamic>?) ?? [];

        // Process indicators to extract localized names and definitions
        final indicatorsList = indicatorsRaw.map((indicatorJson) {
          final indicatorMap = indicatorJson as Map<String, dynamic>;
          final indicator = Indicator.fromJson(indicatorMap);

          // Extract localized name from name_* fields
          String? localizedName;
          if (locale != 'en') {
            final localeMap = {
              'fr': 'name_french',
              'es': 'name_spanish',
              'ar': 'name_arabic',
              'zh': 'name_chinese',
              'ru': 'name_russian',
              'hi': 'name_hindi',
            };
            final nameField = localeMap[locale];
            if (nameField != null) {
              localizedName = indicatorMap[nameField] as String?;
            }
          }

          // Extract localized definition from definition_translations
          String? localizedDefinition;
          final definitionTranslations =
              indicatorMap['definition_translations'];
          if (definitionTranslations is Map<String, dynamic>) {
            if (locale == 'en') {
              // For English, try 'en' first, then 'english'
              localizedDefinition = definitionTranslations['en'] as String? ??
                  definitionTranslations['english'] as String?;
            } else {
              final localeMap = {
                'fr': 'french',
                'es': 'spanish',
                'ar': 'arabic',
                'zh': 'chinese',
                'ru': 'russian',
                'hi': 'hindi',
              };
              final translationKey = localeMap[locale];
              if (translationKey != null) {
                localizedDefinition =
                    definitionTranslations[translationKey] as String?;
              }
            }
          }

          // Map sector and subsector to include localized names
          dynamic localizedSector = indicator.sector;
          if (indicator.sector is Map) {
            final sectorMap = indicator.sector as Map<String, dynamic>;
            final primarySectorName = sectorMap['primary'] as String?;
            if (primarySectorName != null) {
              // Find the sector in our loaded sectors list
              Sector? foundSector;
              try {
                foundSector = _sectors.firstWhere(
                  (s) => s.name == primarySectorName,
                );
              } catch (e) {
                // Sector not found, will use fallback
              }
              // Use found sector or fallback to English name
              final displayName = foundSector?.displayName ?? primarySectorName;
              // Create a new map with localized name
              localizedSector = {
                'primary': primarySectorName,
                'secondary': sectorMap['secondary'],
                'tertiary': sectorMap['tertiary'],
                'localized_name': displayName,
                'name': primarySectorName,
              };
            }
          } else if (indicator.sector is String) {
            // If sector is just a string, look it up
            final sectorName = indicator.sector as String;
            Sector? foundSector;
            try {
              foundSector = _sectors.firstWhere(
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
              // Find the subsector in our loaded sectors' subsectors
              SubSector? foundSubSector;
              for (final sector in _sectors) {
                try {
                  foundSubSector = sector.subsectors.firstWhere(
                    (s) => s.name == primarySubSectorName,
                  );
                  if (foundSubSector != null) {
                    break;
                  }
                } catch (e) {
                  // Continue searching in next sector
                }
              }
              // Use found subsector or create a fallback
              final displayName =
                  foundSubSector?.displayName ?? primarySubSectorName;
              // Create a new map with localized name
              localizedSubSector = {
                'primary': primarySubSectorName,
                'secondary': subsectorMap['secondary'],
                'tertiary': subsectorMap['tertiary'],
                'localized_name': displayName,
                'name': primarySubSectorName,
              };
            }
          } else if (indicator.subSector is String) {
            // If subsector is just a string, look it up
            SubSector? foundSubSector;
            final subSectorName = indicator.subSector as String;
            for (final sector in _sectors) {
              try {
                foundSubSector = sector.subsectors.firstWhere(
                  (s) => s.name == subSectorName,
                );
                if (foundSubSector != null) {
                  break;
                }
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

          // Extract localized type and unit from API response or localize them
          String? localizedType = indicatorMap['localized_type'] as String?;
          String? localizedUnit = indicatorMap['localized_unit'] as String?;

          // If API didn't provide localized values, use client-side localization
          if (localizedType == null && indicator.type != null) {
            localizedType = _localizeType(indicator.type!, locale);
          }
          if (localizedUnit == null && indicator.unit != null) {
            localizedUnit = _localizeUnit(indicator.unit!, locale);
          }

          // Create a new indicator with localized fields
          return Indicator(
            id: indicator.id,
            name: indicator.name,
            localizedName: localizedName,
            definition: indicator.definition,
            localizedDefinition:
                localizedDefinition ?? indicator.localizedDefinition,
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
        }).toList();

        if (search.isEmpty &&
            type.isEmpty &&
            sector.isEmpty &&
            subSector.isEmpty &&
            emergency.isEmpty &&
            !archived) {
          // This is the "all indicators" load
          _allIndicators = indicatorsList;
        }

        _filteredIndicators = indicatorsList;
      } else if (response.statusCode == 429) {
        final retryAfterHeader =
            response.headers['retry-after'] ?? response.headers['Retry-After'];
        final retryAfter = _parseRetryAfter(retryAfterHeader);
        _updateRateLimitState(retryAfter);
        throw RateLimitException(
          _rateLimitMessage ??
              'Too many Indicator Bank requests. Please try again later.',
          retryAfter: retryAfter,
        );
      } else {
        final error = _errorHandler.parseError(
          error: Exception('HTTP ${response.statusCode}'),
          response: response,
          context: 'Load Indicators',
        );
        _errorHandler.logError(error);
        throw Exception(error.getUserMessage());
      }
    } catch (e, stackTrace) {
      final error = _errorHandler.parseError(
        error: e,
        stackTrace: stackTrace,
        context: 'Load Indicators',
      );
      _errorHandler.logError(error);
      rethrow;
    }
  }

  void setSearchTerm(String value) {
    _searchTerm = value;
    _applyFilters();
    notifyListeners();
  }

  void setSelectedType(String value) {
    _selectedType = value;
    _applyFilters();
    notifyListeners();
  }

  void setSelectedSector(String value) {
    _selectedSector = value;
    if (value != _selectedSector) {
      _selectedSubSector = ''; // Clear subsector when sector changes
    }
    _applyFilters();
    notifyListeners();
  }

  void setSelectedSubSector(String value) {
    _selectedSubSector = value;
    _applyFilters();
    notifyListeners();
  }

  void setSelectedEmergency(String value) {
    _selectedEmergency = value;
    _applyFilters();
    notifyListeners();
  }

  void setArchived(bool value) {
    _archived = value;
    _applyFilters();
    notifyListeners();
  }

  void setViewMode(String mode) {
    _viewMode = mode;
    notifyListeners();
  }

  void clearFilters() {
    _searchTerm = '';
    _selectedType = '';
    _selectedSector = '';
    _selectedSubSector = '';
    _selectedEmergency = '';
    _archived = false;
    _applyFilters();
    notifyListeners();
  }

  void _applyFilters() {
    // Apply client-side filtering for search term
    var filtered = _filteredIndicators;

    if (_searchTerm.isNotEmpty) {
      final searchLower = _searchTerm.toLowerCase();
      filtered = filtered.where((indicator) {
        return indicator.displayName.toLowerCase().contains(searchLower) ||
            (indicator.localizedDefinition ?? indicator.definition ?? '')
                .toLowerCase()
                .contains(searchLower);
      }).toList();
    }

    _filteredIndicators = filtered;
  }

  Future<void> applyFilters() async {
    if (_isRateLimited()) {
      _error = _rateLimitMessage ??
          'Indicator Bank is temporarily unavailable. Please try again soon.';
      notifyListeners();
      return;
    }

    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      await _loadIndicators(
        search: _searchTerm,
        type: _selectedType,
        sector: _selectedSector,
        subSector: _selectedSubSector,
        emergency: _selectedEmergency,
        archived: _archived,
        locale: _currentLocale,
      );
      _applyFilters();
    } on RateLimitException catch (e) {
      _error = e.message;
      DebugLogger.logWarn(
        'INDICATOR_BANK',
        'Rate limit while applying filters: ${e.retryAfter ?? 'unknown retry window'}',
      );
    } catch (e, stackTrace) {
      final error = _errorHandler.parseError(
        error: e,
        stackTrace: stackTrace,
        context: 'Apply Filters',
      );
      _error = error.getUserMessage();
      _errorHandler.logError(error);
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> proposeNewIndicator(Map<String, dynamic> proposalData) async {
    try {
      // Add API key to query string manually since POST doesn't support queryParams in our API service
      final endpoint = '/api/v1/indicator-suggestions?api_key=${AppConfig.apiKey}';
      final response = await _api.post(
        endpoint,
        body: {
          ...proposalData,
        },
        includeAuth: false,
      );

      return response.statusCode == 200 || response.statusCode == 201;
    } catch (e) {
      DebugLogger.logError('Error proposing indicator: $e');
      return false;
    }
  }
}
