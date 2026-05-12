import 'package:flutter/foundation.dart';
import '../../services/api_service.dart';
import '../../services/error_handler.dart';
import '../../models/indicator_bank/indicator.dart';
import '../../models/indicator_bank/sector.dart';
import '../../config/app_config.dart';
import '../../utils/debug_logger.dart';
import '../../utils/mobile_api_json.dart';
import '../../utils/network_availability.dart';
import '../../di/service_locator.dart';
import '../../services/indicator_bank_snapshot_store.dart';

class RateLimitException implements Exception {
  final String message;
  final Duration? retryAfter;

  RateLimitException(this.message, {this.retryAfter});

  @override
  String toString() => message;
}

class IndicatorBankProvider with ChangeNotifier {
  final ApiService _api = sl<ApiService>();
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

    if (!forceRefresh) {
      if (_allIndicators.isEmpty && _sectors.isEmpty) {
        if (shouldDeferRemoteFetch) {
          await _restoreFromDiskSnapshotAnyAge(locale);
        } else {
          await _restoreFromDiskSnapshotIfFresh(locale);
        }
      }
      // If we already have fresh data for this locale and refresh is not forced, reuse it
      if (_hasFreshDataForLocale(locale)) {
        _error = null;
        _applyFilters();
        notifyListeners();
        return;
      }
    }

    // If the most recent load already failed, don't fire another identical
    // request.  Staggered callers that arrive after the failing load completes
    // (so _ongoingLoad is null again) would otherwise bypass the in-flight
    // dedup check below and each start their own load, producing cascading
    // identical errors (e.g. 3× "Session expired" when 3 screens call us).
    // A forceRefresh (user-triggered retry) or a successful login clears
    // _error via _performFullLoad, so explicit retries still work.
    if (!forceRefresh && _error != null) return;

    // Wait for any in-flight load to finish before deciding if we still need to fetch
    if (_ongoingLoad != null) {
      await _ongoingLoad;
      // If the concurrent load failed (e.g. auth error), don't fire another
      // identical request — the error state is already set and notified.
      // A manual forceRefresh can still override this to allow explicit retry.
      if (!forceRefresh && _error != null) return;
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

    if (shouldDeferRemoteFetch) {
      _isLoading = false;
      if (_allIndicators.isEmpty && _sectors.isEmpty) {
        await _restoreFromDiskSnapshotAnyAge(locale);
      }
      if (_allIndicators.isNotEmpty) {
        _error = null;
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
      await IndicatorBankSnapshotStore.save(
        IndicatorBankSnapshotPayload(
          version: 1,
          locale: locale,
          savedAt: _lastFullLoad!,
          sectors: _sectors,
          indicators: _allIndicators,
        ),
      );
      _clearRateLimitState();
    } on RateLimitException catch (e) {
      _error = e.message;
      DebugLogger.logWarn(
        'INDICATOR_BANK',
        'Rate limit while loading indicators: ${e.retryAfter ?? 'unknown retry window'}',
      );
      if (_allIndicators.isEmpty) {
        await _restoreFromDiskSnapshotAnyAge(locale);
        if (_allIndicators.isNotEmpty) {
          _error = null;
        }
      }
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
      if (_allIndicators.isEmpty) {
        await _restoreFromDiskSnapshotAnyAge(locale);
        if (_allIndicators.isNotEmpty) {
          _error = null;
        }
      }
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> _loadSectors(String locale) async {
    try {
      final response = await _api.get(
        AppConfig.mobileSectorsSubsectorsEndpoint,
        includeAuth: false,
      );

      if (response.statusCode == 200) {
        final body = decodeJsonObject(response.body);
        // Mobile API envelope: { success, data: { sectors: [...] }, meta } — each sector includes nested subsectors
        final payload = mobileDataMapLoose(body);
        final sectorsRaw = (payload['sectors'] as List<dynamic>?) ?? [];

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
    if (locale == 'en') return fallback;

    // multilingual_names dict uses ISO locale codes as keys (e.g. 'fr', 'es')
    if (field == 'multilingual_names' && obj is Map<String, dynamic>) {
      try {
        final multilingualNames = obj['multilingual_names'];
        if (multilingualNames is Map<String, dynamic>) {
          final localizedValue = multilingualNames[locale];
          if (localizedValue != null && localizedValue.toString().isNotEmpty) {
            return localizedValue.toString();
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

  Future<void> _restoreFromDiskSnapshotIfFresh(String locale) async {
    final snap = await IndicatorBankSnapshotStore.loadIfValid(
      locale: locale,
      maxAge: _cacheDuration,
    );
    if (snap == null) return;
    _applySnapshot(snap);
  }

  /// Last successful download, even if older than [_cacheDuration] (offline).
  Future<void> _restoreFromDiskSnapshotAnyAge(String locale) async {
    final snap = await IndicatorBankSnapshotStore.loadIfValid(
      locale: locale,
      maxAge: null,
    );
    if (snap == null) return;
    _applySnapshot(snap);
  }

  void _applySnapshot(IndicatorBankSnapshotPayload snap) {
    _sectors = snap.sectors;
    _allIndicators = snap.indicators;
    _filteredIndicators = List<Indicator>.from(snap.indicators);
    _lastFullLoad = snap.savedAt;
    _lastLoadedLocale = snap.locale;
    _error = null;
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
        'page': '1',
        'per_page': AppConfig.mobilePublicIndicatorBankPerPage.toString(),
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
        AppConfig.mobilePublicIndicatorBankEndpoint,
        queryParams: queryParams,
        includeAuth: false,
        timeout: const Duration(seconds: 30),
      );

      if (response.statusCode == 200) {
        final body = decodeJsonObject(response.body);
        // Mobile API envelope: { ok, data: [...items...], meta: { total, page, ... } }
        final indicatorsRaw = mobileDataListLoose(body);

        // Process indicators to extract localized names and definitions
        final indicatorsList = indicatorsRaw.map((indicatorJson) {
          final indicatorMap = indicatorJson as Map<String, dynamic>;
          final indicator = Indicator.fromJson(indicatorMap);

          // Extract localized name from name_translations dict (keys are ISO locale codes)
          String? localizedName;
          if (locale != 'en') {
            final nameTranslations =
                indicatorMap['name_translations'] as Map<String, dynamic>?;
            localizedName = nameTranslations?[locale] as String?;
          }

          // Extract localized definition from definition_translations (keys are ISO locale codes)
          String? localizedDefinition;
          final definitionTranslations =
              indicatorMap['definition_translations'];
          if (definitionTranslations is Map<String, dynamic>) {
            localizedDefinition = definitionTranslations[locale] as String?;
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
                  break;
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
    final previous = _selectedSector;
    _selectedSector = value;
    if (previous != value) {
      _selectedSubSector = '';
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

  String? _primaryEnglishSector(Indicator ind) {
    if (ind.sector == null) return null;
    if (ind.sector is String) return ind.sector as String;
    if (ind.sector is Map) {
      return (ind.sector as Map<String, dynamic>)['primary'] as String?;
    }
    return null;
  }

  String? _primaryEnglishSubSector(Indicator ind) {
    if (ind.subSector == null) return null;
    if (ind.subSector is String) return ind.subSector as String;
    if (ind.subSector is Map) {
      return (ind.subSector as Map<String, dynamic>)['primary'] as String?;
    }
    return null;
  }

  /// Re-applies type/sector/sub/emergency/archived on [allIndicators] when the
  /// network is unavailable (mirrors the usual server-side filter call).
  void _rebuildFilteredFromAllIndicatorsOffline() {
    var list = List<Indicator>.from(_allIndicators);
    if (_selectedType.isNotEmpty) {
      list = list
          .where((i) => (i.type ?? '').toLowerCase() == _selectedType.toLowerCase())
          .toList();
    }
    if (_selectedSector.isNotEmpty) {
      list = list
          .where((i) => _primaryEnglishSector(i) == _selectedSector)
          .toList();
    }
    if (_selectedSubSector.isNotEmpty) {
      list = list
          .where((i) => _primaryEnglishSubSector(i) == _selectedSubSector)
          .toList();
    }
    if (_selectedEmergency.isNotEmpty) {
      final q = _selectedEmergency.toLowerCase();
      list = list.where((i) {
        final e = i.emergency;
        if (e != null) {
          if (q == 'true' || q == '1' || q == 'yes') return e == true;
          if (q == 'false' || q == '0' || q == 'no') return e == false;
        }
        return (e?.toString() ?? '').toLowerCase().contains(q);
      }).toList();
    }
    if (!_archived) {
      list = list.where((i) => !i.archived).toList();
    }
    _filteredIndicators = list;
  }

  void _applyFilters() {
    // Client-side: search only. Sector/sub-sector filtering is server-side (any level).
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

    if (shouldDeferRemoteFetch) {
      if (_allIndicators.isEmpty) {
        _isLoading = false;
        notifyListeners();
        return;
      }
      _isLoading = true;
      _error = null;
      notifyListeners();
      try {
        _rebuildFilteredFromAllIndicatorsOffline();
        _applyFilters();
      } finally {
        _isLoading = false;
        notifyListeners();
      }
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

  /// Fetches a single indicator JSON map (for detail when not in cache). Returns `null` on failure or offline.
  Future<Map<String, dynamic>?> fetchIndicatorDetailMap(
    int indicatorId,
    String locale,
  ) async {
    if (shouldDeferRemoteFetch) {
      return null;
    }
    try {
      final response = await _api.get(
        '${AppConfig.mobilePublicIndicatorBankEndpoint}/$indicatorId',
        queryParams: {
          'locale': locale,
        },
        includeAuth: false,
      );
      if (response.statusCode != 200) {
        return null;
      }
      final root = decodeJsonObject(response.body);
      return resolveIndicatorDetailPayload(root);
    } catch (e, stackTrace) {
      DebugLogger.logWarn(
        'INDICATOR_BANK',
        'fetchIndicatorDetailMap failed: $e\n$stackTrace',
      );
      return null;
    }
  }

  Future<bool> proposeNewIndicator(Map<String, dynamic> proposalData) async {
    try {
      final response = await _api.post(
        AppConfig.mobileIndicatorSuggestionsEndpoint,
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
