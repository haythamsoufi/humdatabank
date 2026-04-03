import 'package:flutter/foundation.dart';
import 'dart:convert';
import '../../services/api_service.dart';

class OrganizationalStructureProvider with ChangeNotifier {
  final ApiService _api = ApiService();

  List<Map<String, dynamic>> _organizations = [];
  bool _isLoading = false;
  String? _error;

  List<Map<String, dynamic>> get organizations => _organizations;
  bool get isLoading => _isLoading;
  String? get error => _error;

  Future<void> loadOrganizations({
    String? search,
    String? levelFilter,
  }) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

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

      // Use HTML route
      final response = await _api.get(
        '/admin/organization',
        queryParams: queryParams.isNotEmpty ? queryParams : null,
      );

      if (response.statusCode == 200) {
        // Try to parse as JSON first
        try {
          final jsonData = jsonDecode(response.body) as Map<String, dynamic>;
          if (jsonData['success'] == true) {
            // Parse JSON response based on active tab
            final activeTab = jsonData['active_tab'] as String? ?? levelFilter ?? 'countries';
            _organizations = _parseOrganizationsFromJson(jsonData, activeTab);
          } else {
            // Fallback to HTML parsing
            _organizations = _parseOrganizationsFromHtml(response.body, levelFilter);
          }
        } catch (e) {
          // If JSON parsing fails, try HTML parsing as fallback
          print('[ORGS] JSON parse failed, trying HTML: $e');
          _organizations = _parseOrganizationsFromHtml(response.body, levelFilter);
        }

        print(
            '[ORGS] Parsed ${_organizations.length} organizations for filter: $levelFilter');

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
          print(
              '[ORGS] After search filter: ${_organizations.length} organizations');
        }

        _error = null;
      } else {
        _error = 'Failed to load organizations: ${response.statusCode}';
        _organizations = [];
      }
    } catch (e) {
      _error = 'Error loading organizations: $e';
      _organizations = [];
      print('[ORGANIZATIONS] Error: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
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
      // Parse branches
      if (jsonData['branches'] != null) {
        final branches = jsonData['branches'] as List<dynamic>;
        for (final branch in branches) {
          organizations.add({
            'id': branch['id'],
            'name': branch['name'] ?? '',
            'level': 'Branch',
            'country': branch['country_name'] ?? '',
            'country_id': branch['country_id'],
            'is_active': branch['is_active'] ?? true,
          });
        }
      }
      // Parse subbranches
      if (jsonData['subbranches'] != null) {
        final subbranches = jsonData['subbranches'] as List<dynamic>;
        for (final subbranch in subbranches) {
          organizations.add({
            'id': subbranch['id'],
            'name': subbranch['name'] ?? '',
            'level': 'Sub-branch',
            'country': subbranch['branch_name'] ?? '',
            'branch_id': subbranch['branch_id'],
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

  List<Map<String, dynamic>> _parseOrganizationsFromHtml(String html,
      [String? requestedEntityType]) {
    final organizations = <Map<String, dynamic>>[];

    // Determine which tab to parse based on requested entity type or active tab in HTML
    String? activeTab;
    String? secretariatSubTab;

    // If we have a requested entity type, use it to determine the tab
    if (requestedEntityType != null && requestedEntityType.isNotEmpty) {
      switch (requestedEntityType) {
        case 'countries':
          activeTab = 'countries';
          break;
        case 'nss':
          activeTab = 'nss';
          break;
        case 'ns_structure':
          activeTab = 'ns-structure';
          break;
        case 'secretariat':
        case 'divisions':
        case 'departments':
        case 'regions':
        case 'clusters':
          activeTab = 'secretariat';
          if (requestedEntityType != 'secretariat') {
            secretariatSubTab = requestedEntityType;
          }
          break;
      }
    }

    // If we couldn't determine from requested type, try to detect from HTML
    if (activeTab == null) {
      // Check for active tab by looking for tab-panel without "hidden" class
      final countriesPanelMatch = RegExp(
        r'id="countries-tab-panel"[^>]*class="[^"]*tab-panel[^"]*"',
        caseSensitive: false,
      ).firstMatch(html);
      if (countriesPanelMatch != null &&
          !countriesPanelMatch.group(0)!.contains('hidden')) {
        activeTab = 'countries';
      }

      final nssPanelMatch = RegExp(
        r'id="nss-tab-panel"[^>]*class="[^"]*tab-panel[^"]*"',
        caseSensitive: false,
      ).firstMatch(html);
      if (nssPanelMatch != null &&
          !nssPanelMatch.group(0)!.contains('hidden')) {
        activeTab = 'nss';
      }

      final nsStructurePanelMatch = RegExp(
        r'id="ns-structure-tab-panel"[^>]*class="[^"]*tab-panel[^"]*"',
        caseSensitive: false,
      ).firstMatch(html);
      if (nsStructurePanelMatch != null &&
          !nsStructurePanelMatch.group(0)!.contains('hidden')) {
        activeTab = 'ns-structure';
      }

      final secretariatPanelMatch = RegExp(
        r'id="secretariat-tab-panel"[^>]*class="[^"]*tab-panel[^"]*"',
        caseSensitive: false,
      ).firstMatch(html);
      if (secretariatPanelMatch != null &&
          !secretariatPanelMatch.group(0)!.contains('hidden')) {
        activeTab = 'secretariat';
      }
    }

    // Determine secretariat sub-tab if not already set
    if (activeTab == 'secretariat' && secretariatSubTab == null) {
      // Check which sub-tab div is visible (not hidden)
      final divisionsMatch = RegExp(
        r'id="divisions"[^>]*class="[^"]*tab-content[^"]*"[^>]*>',
        caseSensitive: false,
      ).firstMatch(html);
      if (divisionsMatch != null) {
        // Check if it's not hidden by looking at the full tag
        final divisionsFullMatch = RegExp(
          r'id="divisions"[^>]*>',
          caseSensitive: false,
          dotAll: true,
        ).firstMatch(html);
        if (divisionsFullMatch != null &&
            !divisionsFullMatch.group(0)!.contains('style="display: none;"')) {
          secretariatSubTab = 'divisions';
        }
      }

      final departmentsMatch = RegExp(
        r'id="departments"[^>]*class="[^"]*tab-content[^"]*"[^>]*>',
        caseSensitive: false,
      ).firstMatch(html);
      if (departmentsMatch != null) {
        final departmentsFullMatch = RegExp(
          r'id="departments"[^>]*>',
          caseSensitive: false,
          dotAll: true,
        ).firstMatch(html);
        if (departmentsFullMatch != null &&
            !departmentsFullMatch
                .group(0)!
                .contains('style="display: none;"')) {
          secretariatSubTab = 'departments';
        }
      }

      final regionsMatch = RegExp(
        r'id="regions"[^>]*class="[^"]*tab-content[^"]*"[^>]*>',
        caseSensitive: false,
      ).firstMatch(html);
      if (regionsMatch != null) {
        final regionsFullMatch = RegExp(
          r'id="regions"[^>]*>',
          caseSensitive: false,
          dotAll: true,
        ).firstMatch(html);
        if (regionsFullMatch != null &&
            !regionsFullMatch.group(0)!.contains('style="display: none;"')) {
          secretariatSubTab = 'regions';
        }
      }

      final clustersMatch = RegExp(
        r'id="clusters"[^>]*class="[^"]*tab-content[^"]*"[^>]*>',
        caseSensitive: false,
      ).firstMatch(html);
      if (clustersMatch != null) {
        final clustersFullMatch = RegExp(
          r'id="clusters"[^>]*>',
          caseSensitive: false,
          dotAll: true,
        ).firstMatch(html);
        if (clustersFullMatch != null &&
            !clustersFullMatch.group(0)!.contains('style="display: none;"')) {
          secretariatSubTab = 'clusters';
        }
      }
    }

    // Extract the relevant table HTML based on active tab
    String? tableHtml;
    if (activeTab == 'countries') {
      final match = RegExp(
        r'<table[^>]*id="countriesTable"[^>]*>([\s\S]*?)</table>',
        caseSensitive: false,
        dotAll: true,
      ).firstMatch(html);
      tableHtml = match?.group(0);
      print('[ORGS] Found countries table: ${tableHtml != null}');
    } else if (activeTab == 'nss') {
      final match = RegExp(
        r'<table[^>]*id="nssTable"[^>]*>([\s\S]*?)</table>',
        caseSensitive: false,
        dotAll: true,
      ).firstMatch(html);
      tableHtml = match?.group(0);
      print('[ORGS] Found nss table: ${tableHtml != null}');
    } else if (activeTab == 'ns-structure') {
      // NS Structure might have multiple tables or a different structure
      // Try to find tables within the ns-structure tab panel
      final panelMatch = RegExp(
        r'id="ns-structure-tab-panel"([\s\S]*?)</div>\s*</div>',
        caseSensitive: false,
        dotAll: true,
      ).firstMatch(html);
      if (panelMatch != null) {
        final panelHtml = panelMatch.group(1) ?? '';
        final match = RegExp(
          r'<table[^>]*>([\s\S]*?)</table>',
          caseSensitive: false,
          dotAll: true,
        ).firstMatch(panelHtml);
        tableHtml = match?.group(0);
      }
      print('[ORGS] Found ns-structure table: ${tableHtml != null}');
    } else if (activeTab == 'secretariat') {
      // Get the specific secretariat sub-tab table
      String? tableId;
      if (secretariatSubTab == 'divisions') {
        tableId = 'divisionsTable';
      } else if (secretariatSubTab == 'departments') {
        tableId = 'departmentsTable';
      } else if (secretariatSubTab == 'regions') {
        tableId = 'regionsTable';
      } else if (secretariatSubTab == 'clusters') {
        tableId = 'clustersTable';
      }

      if (tableId != null) {
        // Try multiple regex patterns to find the table
        RegExpMatch? match;

        // Pattern 1: Standard table with id attribute
        match = RegExp(
          r'<table[^>]*id="' + tableId + r'"[^>]*>([\s\S]*?)</table>',
          caseSensitive: false,
          dotAll: true,
        ).firstMatch(html);

        // Pattern 2: Table with id in quotes (different spacing)
        if (match == null) {
          match = RegExp(
            r'<table[^>]*\sid="' + tableId + r'"[^>]*>([\s\S]*?)</table>',
            caseSensitive: false,
            dotAll: true,
          ).firstMatch(html);
        }

        // Pattern 3: Find by table ID anywhere in attributes
        if (match == null) {
          final tableStart = html.indexOf('id="$tableId"');
          if (tableStart != -1) {
            // Find the opening <table> tag before this id
            final tableTagStart = html.lastIndexOf('<table', tableStart);
            if (tableTagStart != -1) {
              // Find the closing </table> tag
              final tableTagEnd = html.indexOf('</table>', tableStart);
              if (tableTagEnd != -1) {
                tableHtml = html.substring(tableTagStart, tableTagEnd + 8);
                match = RegExp(r'.*', dotAll: true).firstMatch(tableHtml);
              }
            }
          }
        }

        if (match != null) {
          tableHtml = match.group(0);
        }

        print(
            '[ORGS] Found $tableId table: ${tableHtml != null}, subTab: $secretariatSubTab, tableHtml length: ${tableHtml?.length ?? 0}');
      } else {
        print(
            '[ORGS] No tableId determined for secretariat, subTab: $secretariatSubTab');
      }
    }

    // If no specific table found, parse all tables (fallback)
    if (tableHtml == null) {
      print('[ORGS] No specific table found, parsing all HTML');
      tableHtml = html;
    } else {
      print('[ORGS] Parsing table with ${tableHtml.length} chars');
    }

    // Parse HTML table rows from the relevant table
    final rowPattern = RegExp(
      r'<tr[^>]*>([\s\S]*?)</tr>',
      caseSensitive: false,
    );

    final rows = rowPattern.allMatches(tableHtml);
    int index = 0;

    for (final row in rows) {
      final rowHtml = row.group(1) ?? '';

      // Skip header rows
      if (rowHtml.contains('<th') ||
          rowHtml.contains('thead') ||
          rowHtml.trim().isEmpty) {
        continue;
      }

      // Extract cells
      final cells = RegExp(
        r'<td[^>]*>([\s\S]*?)</td>',
        caseSensitive: false,
      ).allMatches(rowHtml).toList();

      if (cells.isNotEmpty) {
        // Try to extract organization ID from edit/delete/view links first
        final idMatch = RegExp(
          r'/admin/organization/(?:edit|delete|view)/(\d+)',
          caseSensitive: false,
        ).firstMatch(rowHtml);

        final id = idMatch != null
            ? int.tryParse(idMatch.group(1) ?? '0') ?? index
            : index;

        // Extract entity label/name - look for links or text in cells
        String name = '';

        // Try all cells to find the entity label (skip IDs)
        for (int i = 0; i < cells.length; i++) {
          final cellHtml = cells[i].group(1) ?? '';

          // Try to extract from link text first (usually the entity label)
          final linkMatch = RegExp(
            r'<a[^>]*>([\s\S]*?)</a>',
            caseSensitive: false,
          ).firstMatch(cellHtml);

          String candidateName;
          if (linkMatch != null) {
            candidateName = _extractText(linkMatch.group(1) ?? '');
          } else {
            candidateName = _extractText(cellHtml);
          }

          // Skip if it's empty, just a number (ID), or matches the ID
          if (candidateName.isNotEmpty &&
              candidateName != id.toString() &&
              !RegExp(r'^\d+$').hasMatch(candidateName) &&
              candidateName.length > 2) {
            name = candidateName;
            break; // Found a good name, stop searching
          }
        }

        // If still no name found, use a default
        if (name.isEmpty) {
          name = 'Organization #$id';
        }

        // Extract level/type from second or third cell (if exists)
        String? level;
        if (cells.length > 1) {
          final levelHtml = cells[1].group(1) ?? '';
          final levelText = _extractText(levelHtml);
          // Only use if it doesn't look like a name/label
          if (levelText.isNotEmpty &&
              !RegExp(r'^[A-Z][a-z]+').hasMatch(levelText)) {
            level = levelText;
          } else if (cells.length > 2) {
            final levelHtml2 = cells[2].group(1) ?? '';
            level = _extractText(levelHtml2);
          }
        }

        // Extract country from remaining cells
        String? country;
        for (int i = 2; i < cells.length; i++) {
          final countryHtml = cells[i].group(1) ?? '';
          final countryText = _extractText(countryHtml);
          if (countryText.isNotEmpty && countryText.length < 50) {
            country = countryText;
            break;
          }
        }

        if (name.isNotEmpty && name != id.toString()) {
          // Determine entity type based on context
          String? entityType;
          if (activeTab == 'countries') {
            entityType = 'countries';
          } else if (activeTab == 'nss') {
            entityType = 'nss';
          } else if (activeTab == 'ns-structure') {
            entityType = 'ns_structure';
          } else if (activeTab == 'secretariat') {
            entityType = secretariatSubTab ?? 'secretariat';
          }

          organizations.add({
            'id': id,
            'name': name,
            'level': level?.isNotEmpty == true ? level : null,
            'country': country?.isNotEmpty == true ? country : null,
            'entityType': entityType,
          });
          index++;
        }
      }
    }

    // If no table rows found, try to parse from other structures
    if (organizations.isEmpty) {
      // Try to find organization names in divs or other containers
      final orgPattern = RegExp(
        r'<div[^>]*class="[^"]*organization[^"]*"[^>]*>([\s\S]*?)</div>',
        caseSensitive: false,
      );

      final orgMatches = orgPattern.allMatches(html);
      for (final match in orgMatches) {
        final orgHtml = match.group(1) ?? '';
        final name = _extractText(orgHtml);
        if (name.isNotEmpty && name.length < 200) {
          // Filter out very long text
          organizations.add({
            'id': index++,
            'name': name,
          });
        }
      }
    }

    return organizations;
  }

  String _extractText(String html) {
    return html
        .replaceAll(RegExp(r'<[^>]+>'), '')
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
  }

  List<Map<String, dynamic>> _filterByEntityType(
    List<Map<String, dynamic>> organizations,
    String entityType,
  ) {
    // Filter based on entity type - use the entityType field if available, otherwise fall back to name/level matching
    return organizations.where((org) {
      final orgEntityType = org['entityType']?.toString();

      // If we have the entity type from parsing, use it directly
      if (orgEntityType != null) {
        if (entityType == 'secretariat') {
          // For general secretariat, include all secretariat sub-types
          return orgEntityType == 'divisions' ||
              orgEntityType == 'departments' ||
              orgEntityType == 'regions' ||
              orgEntityType == 'clusters' ||
              orgEntityType == 'secretariat';
        }
        return orgEntityType == entityType;
      }

      // Fallback to name/level matching if entityType not available
      final name = org['name']?.toString().toLowerCase() ?? '';
      final level = org['level']?.toString().toLowerCase() ?? '';

      switch (entityType) {
        case 'countries':
          return !name.contains('branch') &&
              !name.contains('subbranch') &&
              !name.contains('local unit') &&
              !name.contains('division') &&
              !name.contains('department') &&
              !name.contains('regional office') &&
              !name.contains('cluster office') &&
              !name.contains('red cross') &&
              !name.contains('red crescent');

        case 'nss':
          return name.contains('red cross') ||
              name.contains('red crescent') ||
              name.contains('national society');

        case 'ns_structure':
          return name.contains('branch') ||
              name.contains('subbranch') ||
              name.contains('local unit') ||
              level.contains('branch') ||
              level.contains('subbranch') ||
              level.contains('local unit');

        case 'secretariat':
          return name.contains('division') ||
              name.contains('department') ||
              name.contains('regional office') ||
              name.contains('cluster office') ||
              level.contains('division') ||
              level.contains('department') ||
              level.contains('regional') ||
              level.contains('cluster');

        case 'divisions':
          return name.contains('division') || level.contains('division');

        case 'departments':
          return name.contains('department') || level.contains('department');

        case 'regions':
          return name.contains('regional office') || level.contains('regional');

        case 'clusters':
          return name.contains('cluster office') || level.contains('cluster');

        default:
          return true;
      }
    }).toList();
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }
}
