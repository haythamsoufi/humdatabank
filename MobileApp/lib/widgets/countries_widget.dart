import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../services/api_service.dart';
import '../providers/shared/language_provider.dart';
import '../utils/constants.dart';
import '../utils/theme_extensions.dart';
import '../utils/url_helper.dart';
import '../config/app_config.dart';
import '../config/routes.dart';
import 'dart:convert';
import '../di/service_locator.dart';

class CountriesWidget extends StatefulWidget {
  const CountriesWidget({super.key});

  @override
  State<CountriesWidget> createState() => _CountriesWidgetState();
}

class _CountriesWidgetState extends State<CountriesWidget> {
  final ApiService _apiService = sl<ApiService>();
  List<Map<String, dynamic>> _countries = [];
  bool _isLoading = true;
  String? _error;
  String? _searchQuery = '';
  String? _selectedRegion;
  Map<String, List<Map<String, dynamic>>> _countriesByRegion = {};

  @override
  void initState() {
    super.initState();
    _loadCountries();
  }

  Future<void> _loadCountries() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      final languageProvider = Provider.of<LanguageProvider>(context, listen: false);
      final language = languageProvider.currentLanguage;

      final response = await _apiService.get(
        AppConfig.mobileCountryMapEndpoint,
        queryParams: {
          'locale': language,
        },
        includeAuth: false,
      );

      if (response.statusCode == 200) {
        final decoded = jsonDecode(response.body);
        final List<dynamic> data;
        if (decoded is List) {
          data = decoded;
        } else if (decoded is Map<String, dynamic> && decoded['data'] is Map) {
          data = (decoded['data'] as Map)['countries'] as List<dynamic>? ?? [];
        } else if (decoded is Map<String, dynamic> && decoded['data'] is List) {
          data = decoded['data'] as List<dynamic>;
        } else {
          data = [];
        }
        final List<Map<String, dynamic>> countries = data
            .map((item) => item as Map<String, dynamic>)
            .toList();

        // Group countries by region
        final Map<String, List<Map<String, dynamic>>> grouped = {};
        for (final country in countries) {
          final region = country['region_localized'] as String? ??
              country['region'] as String? ??
              'Other';
          if (!grouped.containsKey(region)) {
            grouped[region] = [];
          }
          grouped[region]!.add(country);
        }

        // Sort regions alphabetically
        final sortedRegions = grouped.keys.toList()..sort();
        final sortedGrouped = Map<String, List<Map<String, dynamic>>>.fromEntries(
          sortedRegions.map((region) => MapEntry(region, grouped[region]!))
        );

        // Sort countries within each region alphabetically
        for (final region in sortedGrouped.keys) {
          sortedGrouped[region]!.sort((a, b) {
            final nameA = (a['name'] as String? ?? '').toLowerCase();
            final nameB = (b['name'] as String? ?? '').toLowerCase();
            return nameA.compareTo(nameB);
          });
        }

        setState(() {
          _countries = countries;
          _countriesByRegion = sortedGrouped;
          _selectedRegion = sortedRegions.isNotEmpty ? sortedRegions.first : null;
          _isLoading = false;
        });
      } else {
        setState(() {
          _error = 'Failed to load countries (${response.statusCode})';
          _isLoading = false;
        });
      }
    } catch (e) {
      setState(() {
        _error = 'Error loading countries: $e';
        _isLoading = false;
      });
    }
  }

  List<Map<String, dynamic>> _getFilteredCountries() {
    if (_searchQuery == null || _searchQuery!.trim().isEmpty) {
      // No search query - show countries from selected region only
      if (_selectedRegion == null) return [];
      return _countriesByRegion[_selectedRegion] ?? [];
    }

    // Search query exists - search across all countries
    final query = _searchQuery!.toLowerCase();
    return _countries.where((country) {
      final name = (country['name'] as String? ?? '').toLowerCase();
      final nationalSocietyName =
          (country['national_society_name'] as String? ?? '').toLowerCase();
      return name.contains(query) || nationalSocietyName.contains(query);
    }).toList();
  }

  void _navigateToCountry(String iso3) {
    final languageProvider = Provider.of<LanguageProvider>(context, listen: false);
    final language = languageProvider.currentLanguage;
    final fullUrl = UrlHelper.buildFrontendUrlWithLanguage('/countries/$iso3', language);
    Navigator.of(context).pushNamed(
      AppRoutes.webview,
      arguments: fullUrl,
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    if (_isLoading) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(
              valueColor: AlwaysStoppedAnimation<Color>(
                Color(AppConstants.ifrcRed),
              ),
            ),
            const SizedBox(height: 16),
            Text(
              'Loading countries...',
              style: TextStyle(
                color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                fontSize: 14,
              ),
            ),
          ],
        ),
      );
    }

    if (_error != null) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.error_outline,
              size: 64,
              color: theme.colorScheme.error,
            ),
            const SizedBox(height: 16),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 24),
              child: Text(
                _error!,
                style: TextStyle(
                  color: theme.colorScheme.error,
                  fontSize: 14,
                ),
                textAlign: TextAlign.center,
              ),
            ),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: _loadCountries,
              style: ElevatedButton.styleFrom(
                backgroundColor: Color(AppConstants.ifrcRed),
              ),
              child: const Text('Retry'),
            ),
          ],
        ),
      );
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        final isMobile = constraints.maxWidth < 768;

        if (isMobile) {
          // Mobile layout: Column with regions at top
          return Column(
            children: [
              // Regions header
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 12,
                ),
                decoration: BoxDecoration(
                  color: theme.scaffoldBackgroundColor,
                  border: Border(
                    bottom: BorderSide(
                      color: context.dividerColor,
                      width: 1,
                    ),
                  ),
                ),
                child: Row(
                  children: [
                    Text(
                      'Regions',
                      style: theme.textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: theme.colorScheme.onSurface,
                      ),
                    ),
                  ],
                ),
              ),
              // Horizontal scrollable region chips
              SizedBox(
                height: 60,
                child: ListView(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(
                    horizontal: 16,
                    vertical: 8,
                  ),
                  children: _countriesByRegion.keys.map((region) {
                    final isSelected = _selectedRegion == region;
                    final count =
                        _countriesByRegion[region]?.length ?? 0;
                    return Padding(
                      padding: const EdgeInsets.only(right: 8),
                      child: FilterChip(
                        label: Text('$region ($count)'),
                        selected: isSelected,
                        onSelected: (selected) {
                          setState(() {
                            _selectedRegion = region;
                            _searchQuery = '';
                          });
                        },
                        selectedColor:
                            Color(AppConstants.ifrcRed),
                        labelStyle: TextStyle(
                          color: isSelected
                              ? theme.colorScheme.onSecondary
                              : theme.colorScheme.onSurface,
                          fontSize: 12,
                        ),
                      ),
                    );
                  }).toList(),
                ),
              ),
              const Divider(height: 1),
              // Countries section (full width)
              Expanded(
                child: _buildCountriesList(context, theme),
              ),
            ],
          );
        } else {
          // Desktop layout: Row with regions on left, countries on right
          return Row(
            children: [
              // Regions List - Left Side (1/4 width)
              Container(
                width: MediaQuery.of(context).size.width * 0.25,
                decoration: BoxDecoration(
                  color: theme.scaffoldBackgroundColor,
                  border: Border(
                    right: BorderSide(
                      color: context.dividerColor,
                      width: 1,
                    ),
                  ),
                ),
                child: Column(
                  children: [
                    // Regions header
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        border: Border(
                          bottom: BorderSide(
                            color: context.dividerColor,
                            width: 1,
                          ),
                        ),
                      ),
                      child: Align(
                        alignment: Alignment.centerLeft,
                        child: Text(
                          'Regions',
                          style: theme.textTheme.titleSmall?.copyWith(
                            fontWeight: FontWeight.bold,
                            color: theme.colorScheme.onSurface,
                          ),
                        ),
                      ),
                    ),
                    // Regions list
                    Expanded(
                      child: ListView.builder(
                        itemCount: _countriesByRegion.keys.length,
                        itemBuilder: (context, index) {
                          final region = _countriesByRegion.keys
                              .elementAt(index);
                          final isSelected = _selectedRegion == region;
                          final count =
                              _countriesByRegion[region]?.length ?? 0;
                          return InkWell(
                            onTap: () {
                              setState(() {
                                _selectedRegion = region;
                                _searchQuery = '';
                              });
                            },
                            child: Container(
                              color: isSelected
                                  ? Color(AppConstants.ifrcRed)
                                  : Colors.transparent,
                              padding: const EdgeInsets.symmetric(
                                horizontal: 12,
                                vertical: 12,
                              ),
                              child: Column(
                                crossAxisAlignment:
                                    CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    region,
                                    style: TextStyle(
                                      fontWeight: FontWeight.w600,
                                      fontSize: 14,
                                      color: isSelected
                                          ? theme.colorScheme.onSecondary
                                          : theme
                                              .colorScheme.onSurface,
                                    ),
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    '$count countries',
                                    style: TextStyle(
                                      fontSize: 12,
                                      color: isSelected
                                          ? theme.colorScheme.onSecondary
                                              .withValues(alpha: 0.9)
                                          : theme.colorScheme.onSurface
                                              .withValues(alpha: 0.6),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                  ],
                ),
              ),
              // Countries List - Right Side (3/4 width)
              Expanded(
                child: _buildCountriesList(context, theme),
              ),
            ],
          );
        }
      },
    );
  }

  Widget _buildCountriesList(BuildContext context, ThemeData theme) {
    return Column(
      children: [
        // Header with region info and search
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            border: Border(
              bottom: BorderSide(
                color: context.dividerColor,
                width: 1,
              ),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (_selectedRegion != null)
                GestureDetector(
                  onTap: () {
                    final languageProvider =
                        Provider.of<LanguageProvider>(
                      context,
                      listen: false,
                    );
                    final language =
                        languageProvider.currentLanguage;
                    // Navigate to region overview
                    final regionSlug = _selectedRegion!
                        .toLowerCase()
                        .replaceAll(' ', '-');
                    final fullUrl = UrlHelper
                        .buildFrontendUrlWithLanguage(
                      '/regions/$regionSlug',
                      language,
                    );
                    Navigator.of(context).pushNamed(
                      AppRoutes.webview,
                      arguments: fullUrl,
                    );
                  },
                  child: Text(
                    'See $_selectedRegion Region Overview',
                    style: TextStyle(
                      color: Color(AppConstants.ifrcRed),
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                      decoration: TextDecoration.underline,
                    ),
                  ),
                ),
              const SizedBox(height: 8),
              TextField(
                decoration: InputDecoration(
                  hintText: 'Search countries...',
                  prefixIcon: const Icon(Icons.search),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(8),
                    borderSide: BorderSide(
                      color: context.dividerColor,
                    ),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(8),
                    borderSide: BorderSide(
                      color: Color(AppConstants.ifrcRed),
                      width: 2,
                    ),
                  ),
                  filled: true,
                  fillColor: theme.scaffoldBackgroundColor,
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 12,
                  ),
                ),
                onChanged: (value) {
                  setState(() {
                    _searchQuery = value;
                  });
                },
              ),
            ],
          ),
        ),
        // Countries list
        Expanded(
          child: Builder(
            builder: (context) {
              final filteredCountries = _getFilteredCountries();
              if (filteredCountries.isEmpty) {
                return Center(
                  child: Text(
                    _searchQuery != null &&
                            _searchQuery!.trim().isNotEmpty
                        ? 'No countries found'
                        : 'No countries available',
                    style: TextStyle(
                      color: theme.colorScheme.onSurface
                          .withValues(alpha: 0.6),
                      fontSize: 14,
                    ),
                  ),
                );
              }

              // Grid layout with 2 columns
              return GridView.builder(
                padding: const EdgeInsets.all(12),
                gridDelegate:
                    const SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: 2,
                  childAspectRatio: 4,
                  crossAxisSpacing: 6,
                  mainAxisSpacing: 6,
                ),
                itemCount: filteredCountries.length,
                itemBuilder: (context, index) {
                  final country = filteredCountries[index];
                  final name =
                      country['name'] as String? ?? 'Unknown';
                  final iso3 = country['iso3'] as String?;

                  return InkWell(
                    onTap: iso3 != null
                        ? () => _navigateToCountry(iso3)
                        : null,
                    borderRadius: BorderRadius.circular(4),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                      decoration: BoxDecoration(
                        borderRadius: BorderRadius.circular(4),
                        border: Border.all(
                          color: context.dividerColor.withValues(alpha: 0.3),
                          width: 0.5,
                        ),
                      ),
                      child: Center(
                        child: Text(
                          name,
                          style: TextStyle(
                            fontWeight: FontWeight.w500,
                            fontSize: 14,
                            color: theme.colorScheme.onSurface,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          textAlign: TextAlign.center,
                        ),
                      ),
                    ),
                  );
                },
              );
            },
          ),
        ),
      ],
    );
  }
}
