import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../services/api_service.dart';
import '../../providers/shared/language_provider.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../l10n/app_localizations.dart';
import '../../utils/debug_logger.dart';
import '../../utils/network_availability.dart';
import 'dart:convert';
import '../../di/service_locator.dart';

class NSStructureScreen extends StatefulWidget {
  final int? countryId;

  const NSStructureScreen({super.key, this.countryId});

  @override
  State<NSStructureScreen> createState() => _NSStructureScreenState();
}

class _NSStructureScreenState extends State<NSStructureScreen> {
  final ApiService _apiService = sl<ApiService>();
  List<Map<String, dynamic>> _branches = [];
  List<Map<String, dynamic>> _subbranches = [];
  bool _isLoading = true;
  String? _error;
  String? _searchQuery = '';
  String? _subbranchSearchQuery = '';
  int? _selectedBranchId;

  @override
  void initState() {
    super.initState();
    if (widget.countryId != null) {
      _loadNSStructure();
    } else {
      setState(() {
        _isLoading = false;
        _error = 'Country ID is required';
      });
    }
  }

  Future<void> _loadNSStructure() async {
    if (widget.countryId == null) return;

    if (shouldDeferRemoteFetch) {
      if (!mounted) return;
      setState(() {
        _isLoading = false;
      });
      return;
    }

    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      final languageProvider = Provider.of<LanguageProvider>(context, listen: false);
      final language = languageProvider.currentLanguage;

      // Fetch branches and sub-branches from backend endpoints
      // Similar to Website's /api/ns-structure route
      final branchesResponse = await _apiService.get(
        '/admin/organization/api/public/branches/${widget.countryId}',
        queryParams: {
          'locale': language,
        },
        includeAuth: false,
      );

      List<Map<String, dynamic>> branches = [];
      List<Map<String, dynamic>> subbranches = [];

      if (branchesResponse.statusCode == 200) {
        final branchesData = jsonDecode(branchesResponse.body);
        final branchesList = (branchesData is List
            ? branchesData
            : (branchesData is Map && branchesData['branches'] != null
                ? branchesData['branches']
                : [])) as List<dynamic>;
        branches = branchesList
            .map((item) => item as Map<String, dynamic>)
            .toList();
      }

      // Fetch all sub-branches for the country
      try {
        final subbranchesResponse = await _apiService.get(
          '/admin/organization/api/public/subbranches/by-country/${widget.countryId}',
          queryParams: {
            'locale': language,
          },
          includeAuth: false,
        );

        if (subbranchesResponse.statusCode == 200) {
          final subbranchesData = jsonDecode(subbranchesResponse.body);
          final subbranchesList = (subbranchesData is List
              ? subbranchesData
              : (subbranchesData is Map && subbranchesData['subbranches'] != null
                  ? subbranchesData['subbranches']
                  : [])) as List<dynamic>;
          subbranches = subbranchesList
              .map((item) => item as Map<String, dynamic>)
              .toList();
        }
      } catch (e) {
        // Continue without sub-branches if fetch fails
        DebugLogger.logError('Error fetching sub-branches: $e');
      }

      setState(() {
        _branches = branches;
        _subbranches = subbranches;
        _selectedBranchId = null;
        _isLoading = false;
      });
    } catch (e) {
      setState(() {
        _error = AppLocalizations.of(context)!.oopsSomethingWentWrong;
        _isLoading = false;
      });
    }
  }

  // Filter branches based on search query
  List<Map<String, dynamic>> _getFilteredBranches() {
    if (_searchQuery == null || _searchQuery!.trim().isEmpty) {
      return _branches;
    }

    final query = _searchQuery!.toLowerCase();
    return _branches.where((branch) {
      final name = (branch['name'] as String? ?? '').toLowerCase();
      return name.contains(query);
    }).toList();
  }

  // Filter sub-branches based on selected branch and search query
  List<Map<String, dynamic>> _getFilteredSubbranches() {
    List<Map<String, dynamic>> filtered = _subbranches;

    // Filter by selected branch
    if (_selectedBranchId != null) {
      filtered = filtered.where((sb) {
        return sb['branch_id'] == _selectedBranchId;
      }).toList();
    }

    // Filter by search query
    if (_subbranchSearchQuery != null && _subbranchSearchQuery!.trim().isNotEmpty) {
      final query = _subbranchSearchQuery!.toLowerCase();
      filtered = filtered.where((sb) {
        final name = (sb['name'] as String? ?? '').toLowerCase();
        return name.contains(query);
      }).toList();
    }

    return filtered;
  }

  // Count sub-branches for each branch
  Map<int, int> _getBranchSubbranchCounts() {
    final Map<int, int> counts = {};
    for (final subbranch in _subbranches) {
      final branchId = subbranch['branch_id'] as int?;
      if (branchId != null) {
        counts[branchId] = (counts[branchId] ?? 0) + 1;
      }
    }
    return counts;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final localizations = AppLocalizations.of(context)!;

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        title: Text(localizations.nsStructure),
        backgroundColor: Color(AppConstants.ifrcNavy),
        foregroundColor: theme.colorScheme.onPrimary,
        elevation: 0,
      ),
      body: _isLoading
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
                    'Loading organizational structure...',
                    style: TextStyle(
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                      fontSize: 14,
                    ),
                  ),
                ],
              ),
            )
          : _error != null
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        Icons.error_outline,
                        size: 64,
                        color: theme.colorScheme.error,
                      ),
                      const SizedBox(height: 16),
                      Text(
                        _error!,
                        style: TextStyle(
                          color: theme.colorScheme.error,
                          fontSize: 14,
                        ),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 16),
                      ElevatedButton(
                        onPressed: _loadNSStructure,
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Color(AppConstants.ifrcRed),
                        ),
                        child: Text(localizations.retry),
                      ),
                    ],
                  ),
                )
              : LayoutBuilder(
                  builder: (context, constraints) {
                    final isMobile = constraints.maxWidth < 768;

                    if (isMobile) {
                      // Mobile layout: Column with branches at top
                      return Column(
                        children: [
                          // Branches header
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
                                  'Branches',
                                  style: theme.textTheme.titleSmall?.copyWith(
                                    fontWeight: FontWeight.bold,
                                    color: theme.colorScheme.onSurface,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          // Branches section with search
                          SizedBox(
                            height: 200,
                            child: Column(
                              children: [
                                // Search
                                Padding(
                                  padding: const EdgeInsets.all(8.0),
                                  child: TextField(
                                    decoration: InputDecoration(
                                      hintText: 'Search branches...',
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
                                ),
                                // Branches list
                                Expanded(
                                  child: _buildBranchesList(context, theme, true),
                                ),
                              ],
                            ),
                          ),
                          const Divider(height: 1),
                          // Sub-branches section (full width)
                          Expanded(
                            child: _buildSubbranchesList(context, theme, true),
                          ),
                        ],
                      );
                    } else {
                      // Desktop layout: Row with branches on left, sub-branches on right
                      return Row(
                        children: [
                          // Branches List - Left Side (1/3 width)
                          Container(
                            width: MediaQuery.of(context).size.width * 0.33,
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
                                // Branches header
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
                                      'Branches',
                                      style: theme.textTheme.titleSmall?.copyWith(
                                        fontWeight: FontWeight.bold,
                                        color: theme.colorScheme.onSurface,
                                      ),
                                    ),
                                  ),
                                ),
                                // Search
                                Padding(
                                  padding: const EdgeInsets.all(8.0),
                                  child: TextField(
                                    decoration: InputDecoration(
                                      hintText: 'Search branches...',
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
                                ),
                                // Branches list
                                Expanded(
                                  child: _buildBranchesList(context, theme, false),
                                ),
                              ],
                            ),
                          ),
                          // Sub-branches List - Right Side (2/3 width)
                          Expanded(
                            child: _buildSubbranchesList(context, theme, false),
                          ),
                        ],
                      );
                    }
                  },
                ),
    );
  }

  Widget _buildBranchesList(BuildContext context, ThemeData theme, bool isMobile) {
    final filteredBranches = _getFilteredBranches();
    final branchCounts = _getBranchSubbranchCounts();

    if (filteredBranches.isEmpty) {
      return Center(
        child: Text(
          'No branches found',
          style: TextStyle(
            color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
            fontSize: 14,
          ),
        ),
      );
    }

    return ListView.builder(
      itemCount: filteredBranches.length,
      itemBuilder: (context, index) {
        final branch = filteredBranches[index];
        final branchId = branch['id'] as int?;
        final isSelected = _selectedBranchId == branchId;
        final count = branchCounts[branchId] ?? 0;

        return InkWell(
          onTap: () {
            setState(() {
              _selectedBranchId = isSelected ? null : branchId;
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
            child: Row(
              children: [
                Expanded(
                  child: Text(
                    branch['name'] as String? ??
                        AppLocalizations.of(context)!.unknown,
                    style: TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 14,
                      color: isSelected
                          ? theme.colorScheme.onSecondary
                          : theme.colorScheme.onSurface,
                    ),
                  ),
                ),
                if (count > 0)
                  Text(
                    '($count)',
                    style: TextStyle(
                      fontSize: 12,
                      color: isSelected
                          ? theme.colorScheme.onSecondary.withValues(alpha: 0.9)
                          : theme.colorScheme.onSurface.withValues(alpha: 0.6),
                    ),
                  ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildSubbranchesList(BuildContext context, ThemeData theme, bool isMobile) {
    return Column(
      children: [
        // Header with search
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
              Text(
                'Sub-branches',
                style: theme.textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.bold,
                  color: theme.colorScheme.onSurface,
                ),
              ),
              const SizedBox(height: 8),
              TextField(
                decoration: InputDecoration(
                  hintText: 'Search sub-branches...',
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
                    _subbranchSearchQuery = value;
                  });
                },
              ),
            ],
          ),
        ),
        // Sub-branches list
        Expanded(
          child: Builder(
            builder: (context) {
              final filteredSubbranches = _getFilteredSubbranches();

              if (filteredSubbranches.isEmpty) {
                return Center(
                  child: Text(
                    _selectedBranchId == null
                        ? AppLocalizations.of(context)!.nsSelectBranchPrompt
                        : 'No sub-branches found',
                    style: TextStyle(
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                      fontSize: 14,
                    ),
                  ),
                );
              }

              // Grid layout with 2-3 columns depending on screen size
              return GridView.builder(
                padding: const EdgeInsets.all(12),
                gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: isMobile ? 2 : 3,
                  childAspectRatio: 4,
                  crossAxisSpacing: 8,
                  mainAxisSpacing: 8,
                ),
                itemCount: filteredSubbranches.length,
                itemBuilder: (context, index) {
                  final subbranch = filteredSubbranches[index];
                  final name = subbranch['name'] as String? ??
                      AppLocalizations.of(context)!.unknown;

                  return Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 12,
                      vertical: 10,
                    ),
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
