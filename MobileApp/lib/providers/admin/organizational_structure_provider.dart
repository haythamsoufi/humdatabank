import 'package:flutter/foundation.dart';
import '../../config/app_config.dart';
import '../../services/api_service.dart';
import '../../utils/debug_logger.dart';
import '../../utils/mobile_api_json.dart';
import '../../utils/network_availability.dart';
import '../../di/service_locator.dart';
import '../shared/async_operation_mixin.dart';

class OrganizationalStructureProvider with ChangeNotifier, AsyncOperationMixin {
  final ApiService _api = sl<ApiService>();

  List<Map<String, dynamic>> _organizations = [];

  List<Map<String, dynamic>> get organizations => _organizations;
  bool get isLoading => opLoading;
  String? get error => opError;

  Future<void> loadOrganizations({
    String? search,
    String? levelFilter,
  }) async {
    if (shouldDeferRemoteFetch) {
      notifyListeners();
      return;
    }

    await runAsyncOperation(() async {
    try {
      final queryParams = <String, String>{};
      if (search != null && search.isNotEmpty) {
        queryParams['search'] = search;
      }
      // Use tab parameter to get the right entity type
      if (levelFilter != null && levelFilter.isNotEmpty) {
        // Map entity type filter to tab parameter
        String? tab;
        switch (levelFilter) {
          case 'countries':
            tab = 'countries';
            break;
          case 'nss':
            tab = 'nss';
            break;
          case 'ns_structure':
            tab = 'ns-structure';
            break;
          case 'secretariat':
          case 'divisions':
          case 'departments':
          case 'regions':
          case 'clusters':
            tab = 'secretariat';
            if (levelFilter != 'secretariat') {
              queryParams['secretariat_tab'] = levelFilter;
            }
            break;
        }
        if (tab != null) {
          queryParams['tab'] = tab;
        }
      }

      // Mobile org structure JSON API (/api/mobile/v1/admin/org/structure)
      final response = await _api.get(
        AppConfig.mobileOrgStructureEndpoint,
        queryParams: queryParams.isNotEmpty ? queryParams : null,
      );

      if (response.statusCode == 200) {
        try {
          final jsonData = decodeJsonObject(response.body);
          if (mobileResponseIsSuccess(jsonData)) {
            final rawData = jsonData['data'] is Map<String, dynamic>
                ? jsonData['data'] as Map<String, dynamic>
                : jsonData;
            // Server always returns all entity lists; pick the slice from the UI filter.
            final effectiveTab = _effectiveTabFromFilter(levelFilter);
            _organizations = _parseOrganizationsFromJson(rawData, effectiveTab);
          } else {
            _organizations = [];
            throw Exception('Failed to load organizations: invalid API response');
          }
        } catch (e) {
          DebugLogger.logErrorWithTag('ORGS', 'JSON parse failed: $e');
          _organizations = [];
          rethrow;
        }

        DebugLogger.logInfo('ORGS',
            'Parsed ${_organizations.length} organizations for filter: $levelFilter');

        // Apply search filter if provided (only if we have organizations)
        if (search != null && search.isNotEmpty && _organizations.isNotEmpty) {
          final searchLower = search.toLowerCase();
          _organizations = _organizations.where((org) {
            final name = org['name']?.toString().toLowerCase() ?? '';
            final level = org['level']?.toString().toLowerCase() ?? '';
            final country = org['country']?.toString().toLowerCase() ?? '';
            return name.contains(searchLower) ||
                level.contains(searchLower) ||
                country.contains(searchLower);
          }).toList();
          DebugLogger.logInfo('ORGS',
              'After search filter: ${_organizations.length} organizations');
        }

        // success — opError cleared by runAsyncOperation
      } else {
        _organizations = [];
        throw Exception('Failed to load organizations: ${response.statusCode}');
      }
    } catch (e) {
      _organizations = [];
      DebugLogger.logErrorWithTag('ORGANIZATIONS', 'Error: $e');
      rethrow;
    }
    }); // end runAsyncOperation
  }

  /// Maps UI entity filter to the JSON slice returned by the mobile org API.
  String _effectiveTabFromFilter(String? levelFilter) {
    if (levelFilter == null || levelFilter.isEmpty || levelFilter == 'countries') {
      return 'countries';
    }
    if (levelFilter == 'nss') return 'nss';
    if (levelFilter == 'ns_structure') return 'ns-structure';
    if (levelFilter == 'secretariat' ||
        levelFilter == 'divisions' ||
        levelFilter == 'departments' ||
        levelFilter == 'regions' ||
        levelFilter == 'clusters') {
      return 'secretariat';
    }
    return 'countries';
  }

  List<Map<String, dynamic>> _parseOrganizationsFromJson(
      Map<String, dynamic> jsonData, String activeTab) {
    final organizations = <Map<String, dynamic>>[];

    if (activeTab == 'countries' || activeTab == 'nss') {
      // Parse countries
      if (jsonData['countries'] != null) {
        final countries = jsonData['countries'] as List<dynamic>;
        for (final country in countries) {
          organizations.add({
            'id': country['id'],
            'name': country['name'] ?? '',
            'level': 'Country',
            'country': country['name'] ?? '',
            'code': country['code'],
          });
        }
      }
      // Parse national societies
      if (jsonData['national_societies'] != null) {
        final nss = jsonData['national_societies'] as List<dynamic>;
        for (final ns in nss) {
          organizations.add({
            'id': ns['id'],
            'name': ns['name'] ?? '',
            'level': 'National Society',
            'country': ns['country_name'] ?? '',
            'country_id': ns['country_id'],
          });
        }
      }
    } else if (activeTab == 'ns-structure') {
      final branches = jsonData['branches'] is List<dynamic>
          ? jsonData['branches'] as List<dynamic>
          : const <dynamic>[];
      final branchNames = <int, String>{};
      final branchCountries = <int, String>{};
      for (final branch in branches) {
        if (branch is! Map<String, dynamic>) continue;
        final id = branch['id'];
        if (id is int) {
          branchNames[id] = branch['name']?.toString() ?? '';
          branchCountries[id] = branch['country_name']?.toString() ?? '';
        }
      }

      // Parse branches
      for (final branch in branches) {
        if (branch is! Map<String, dynamic>) continue;
        organizations.add({
          'id': branch['id'],
          'name': branch['name'] ?? '',
          'level': 'Branch',
          'country': branch['country_name'] ?? '',
          'country_id': branch['country_id'],
          'is_active': branch['is_active'] ?? true,
        });
      }
      // Parse subbranches
      if (jsonData['subbranches'] != null) {
        final subbranches = jsonData['subbranches'] as List<dynamic>;
        for (final subbranch in subbranches) {
          if (subbranch is! Map<String, dynamic>) continue;
          final branchId = subbranch['branch_id'];
          organizations.add({
            'id': subbranch['id'],
            'name': subbranch['name'] ?? '',
            'level': 'Sub-branch',
            'country': subbranch['branch_name'] ??
                (branchId is int ? branchCountries[branchId] : null) ??
                '',
            'branch_id': branchId,
            'is_active': subbranch['is_active'] ?? true,
          });
        }
      }
      // Parse local units
      if (jsonData['local_units'] != null) {
        final localUnits = jsonData['local_units'] as List<dynamic>;
        for (final unit in localUnits) {
          organizations.add({
            'id': unit['id'],
            'name': unit['name'] ?? '',
            'level': 'Local Unit',
            'country': unit['branch_name'] ?? '',
            'branch_id': unit['branch_id'],
            'is_active': unit['is_active'] ?? true,
          });
        }
      }
    } else if (activeTab == 'secretariat') {
      // Parse divisions
      if (jsonData['divisions'] != null) {
        final divisions = jsonData['divisions'] as List<dynamic>;
        for (final division in divisions) {
          organizations.add({
            'id': division['id'],
            'name': division['name'] ?? '',
            'level': 'Division',
            'display_order': division['display_order'],
          });
        }
      }
      // Parse departments
      if (jsonData['departments'] != null) {
        final departments = jsonData['departments'] as List<dynamic>;
        for (final dept in departments) {
          organizations.add({
            'id': dept['id'],
            'name': dept['name'] ?? '',
            'level': 'Department',
            'country': dept['division_name'] ?? '',
            'division_id': dept['division_id'],
            'is_active': dept['is_active'] ?? true,
          });
        }
      }
      // Parse regions
      if (jsonData['regions'] != null) {
        final regions = jsonData['regions'] as List<dynamic>;
        for (final region in regions) {
          organizations.add({
            'id': region['id'],
            'name': region['name'] ?? '',
            'level': 'Regional Office',
            'display_order': region['display_order'],
          });
        }
      }
      // Parse clusters
      if (jsonData['clusters'] != null) {
        final clusters = jsonData['clusters'] as List<dynamic>;
        for (final cluster in clusters) {
          organizations.add({
            'id': cluster['id'],
            'name': cluster['name'] ?? '',
            'level': 'Cluster Office',
            'country': cluster['regional_office_name'] ?? '',
            'regional_office_id': cluster['regional_office_id'],
          });
        }
      }
    }

    return organizations;
  }

  void clearError() => clearOpError();
}
