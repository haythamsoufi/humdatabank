import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/admin/indicator_bank_admin_provider.dart';
import '../../models/shared/indicator.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../l10n/app_localizations.dart';

class IndicatorBankAdminScreen extends StatefulWidget {
  const IndicatorBankAdminScreen({super.key});

  @override
  State<IndicatorBankAdminScreen> createState() =>
      _IndicatorBankAdminScreenState();
}

class _IndicatorBankAdminScreenState extends State<IndicatorBankAdminScreen> {
  final TextEditingController _searchController = TextEditingController();
  String _searchQuery = '';
  String? _selectedCategoryFilter;
  String? _selectedSectorFilter;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadIndicators();
    });
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  void _loadIndicators() {
    final provider =
        Provider.of<IndicatorBankAdminProvider>(context, listen: false);
    provider.loadIndicators(
      search: _searchQuery.isNotEmpty ? _searchQuery : null,
      categoryFilter: _selectedCategoryFilter,
      sectorFilter: _selectedSectorFilter,
    );
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;

    final theme = Theme.of(context);
    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(
        title: localizations.indicatorBankTitle,
      ),
      body: Container(
        color: theme.scaffoldBackgroundColor,
        child: Column(
          children: [
            // Search and Filters
            Container(
              padding: const EdgeInsets.all(16),
              color: theme.scaffoldBackgroundColor,
              child: Column(
                children: [
                  TextField(
                    controller: _searchController,
                    decoration: InputDecoration(
                      hintText: localizations.searchIndicators,
                      prefixIcon: const Icon(Icons.search),
                      suffixIcon: _searchQuery.isNotEmpty
                          ? IconButton(
                              icon: const Icon(Icons.clear),
                              onPressed: () {
                                setState(() {
                                  _searchQuery = '';
                                  _searchController.clear();
                                });
                              },
                            )
                          : null,
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                      contentPadding: const EdgeInsets.symmetric(
                        horizontal: 16,
                        vertical: 12,
                      ),
                    ),
                    onChanged: (value) {
                      setState(() {
                        _searchQuery = value;
                      });
                      _loadIndicators();
                    },
                  ),
                  const SizedBox(height: 12),
                  // Filters
                  LayoutBuilder(
                    builder: (context, constraints) {
                      if (constraints.maxWidth > 400) {
                        // Wide screen: show filters side by side
                        return Row(
                          children: [
                            Expanded(
                              child: DropdownButtonFormField<String>(
                                value: _selectedCategoryFilter,
                                decoration: InputDecoration(
                                  labelText: localizations.category,
                                  border: OutlineInputBorder(
                                    borderRadius: BorderRadius.circular(8),
                                  ),
                                  contentPadding: const EdgeInsets.symmetric(
                                    horizontal: 12,
                                    vertical: 12,
                                  ),
                                  isDense: true,
                                ),
                                items: [
                                  DropdownMenuItem<String>(
                                    value: null,
                                    child: Text(localizations.allCategories),
                                  ),
                                  DropdownMenuItem<String>(
                                    value: 'output',
                                    child: Text(localizations.output),
                                  ),
                                  DropdownMenuItem<String>(
                                    value: 'outcome',
                                    child: Text(localizations.outcome),
                                  ),
                                  DropdownMenuItem<String>(
                                    value: 'impact',
                                    child: Text(localizations.impact),
                                  ),
                                ],
                                onChanged: (value) {
                                  setState(() {
                                    _selectedCategoryFilter = value;
                                  });
                                  _loadIndicators();
                                },
                              ),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: DropdownButtonFormField<String>(
                                value: _selectedSectorFilter,
                                decoration: InputDecoration(
                                  labelText: localizations.sector,
                                  border: OutlineInputBorder(
                                    borderRadius: BorderRadius.circular(8),
                                  ),
                                  contentPadding: const EdgeInsets.symmetric(
                                    horizontal: 12,
                                    vertical: 12,
                                  ),
                                  isDense: true,
                                ),
                                items: [
                                  DropdownMenuItem<String>(
                                    value: null,
                                    child: Text(localizations.allSectors),
                                  ),
                                  DropdownMenuItem<String>(
                                    value: 'health',
                                    child: Text(localizations.health),
                                  ),
                                  DropdownMenuItem<String>(
                                    value: 'wash',
                                    child: Text(localizations.wash),
                                  ),
                                  DropdownMenuItem<String>(
                                    value: 'shelter',
                                    child: Text(localizations.shelter),
                                  ),
                                  DropdownMenuItem<String>(
                                    value: 'education',
                                    child: Text(localizations.education),
                                  ),
                                ],
                                onChanged: (value) {
                                  setState(() {
                                    _selectedSectorFilter = value;
                                  });
                                  _loadIndicators();
                                },
                              ),
                            ),
                          ],
                        );
                      } else {
                        // Narrow screen: show filters stacked
                        return Column(
                          children: [
                            DropdownButtonFormField<String>(
                              value: _selectedCategoryFilter,
                              decoration: InputDecoration(
                                labelText: localizations.category,
                                border: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                contentPadding: const EdgeInsets.symmetric(
                                  horizontal: 12,
                                  vertical: 12,
                                ),
                                isDense: true,
                              ),
                              items: [
                                DropdownMenuItem<String>(
                                  value: null,
                                  child: Text(localizations.allCategories),
                                ),
                                DropdownMenuItem<String>(
                                  value: 'output',
                                  child: Text(localizations.output),
                                ),
                                DropdownMenuItem<String>(
                                  value: 'outcome',
                                  child: Text(localizations.outcome),
                                ),
                                DropdownMenuItem<String>(
                                  value: 'impact',
                                  child: Text(localizations.impact),
                                ),
                              ],
                              onChanged: (value) {
                                setState(() {
                                  _selectedCategoryFilter = value;
                                });
                                _loadIndicators();
                              },
                            ),
                            const SizedBox(height: 12),
                            DropdownButtonFormField<String>(
                              value: _selectedSectorFilter,
                              decoration: InputDecoration(
                                labelText: localizations.sector,
                                border: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                contentPadding: const EdgeInsets.symmetric(
                                  horizontal: 12,
                                  vertical: 12,
                                ),
                                isDense: true,
                              ),
                              items: [
                                DropdownMenuItem<String>(
                                  value: null,
                                  child: Text(localizations.allSectors),
                                ),
                                DropdownMenuItem<String>(
                                  value: 'health',
                                  child: Text(localizations.health),
                                ),
                                DropdownMenuItem<String>(
                                  value: 'wash',
                                  child: Text(localizations.wash),
                                ),
                                DropdownMenuItem<String>(
                                  value: 'shelter',
                                  child: Text(localizations.shelter),
                                ),
                                DropdownMenuItem<String>(
                                  value: 'education',
                                  child: Text(localizations.education),
                                ),
                              ],
                              onChanged: (value) {
                                setState(() {
                                  _selectedSectorFilter = value;
                                });
                                _loadIndicators();
                              },
                            ),
                          ],
                        );
                      }
                    },
                  ),
                ],
              ),
            ),
            // Indicators List
            Expanded(
              child: Consumer<IndicatorBankAdminProvider>(
                builder: (context, provider, child) {
                  if (provider.isLoading && provider.indicators.isEmpty) {
                    return Center(
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
                            AppLocalizations.of(context)!.loadingIndicators,
                            style: TextStyle(
                              color: Theme.of(context)
                                  .colorScheme
                                  .onSurface
                                  .withOpacity(0.6),
                              fontSize: 14,
                            ),
                          ),
                        ],
                      ),
                    );
                  }

                  if (provider.error != null && provider.indicators.isEmpty) {
                    return Center(
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
                              provider.error!,
                              style: TextStyle(
                                color: Theme.of(context)
                                    .colorScheme
                                    .onSurface
                                    .withOpacity(0.6),
                                fontSize: 14,
                              ),
                              textAlign: TextAlign.center,
                            ),
                            const SizedBox(height: 24),
                            OutlinedButton.icon(
                              onPressed: () {
                                provider.clearError();
                                _loadIndicators();
                              },
                              icon: const Icon(Icons.refresh, size: 18),
                              label: const Text('Retry'),
                              style: OutlinedButton.styleFrom(
                                foregroundColor:
                                    Color(AppConstants.ifrcRed),
                                side: BorderSide(
                                  color: Color(AppConstants.ifrcRed),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    );
                  }

                  if (provider.indicators.isEmpty) {
                    return Center(
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(
                            Icons.storage_outlined,
                            size: 56,
                            color: Theme.of(context)
                                .colorScheme
                                .onSurface
                                .withOpacity(0.5),
                          ),
                          const SizedBox(height: 16),
                          Text(
                            localizations.noIndicatorsFound,
                            style: TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.w600,
                              color: Theme.of(context).colorScheme.onSurface,
                            ),
                          ),
                        ],
                      ),
                    );
                  }

                  return RefreshIndicator(
                    onRefresh: () async {
                      _loadIndicators();
                    },
                    color: Color(AppConstants.ifrcRed),
                    child: ListView.builder(
                      padding: const EdgeInsets.all(16),
                      itemCount: provider.indicators.length,
                      itemBuilder: (context, index) {
                        final indicator = provider.indicators[index];
                        return Card(
                          margin: const EdgeInsets.only(bottom: 12),
                          elevation: 0,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(8),
                            side: BorderSide(
                              color: Theme.of(context).dividerColor,
                              width: 1,
                            ),
                          ),
                          child: InkWell(
                            onTap: () {
                              Navigator.of(context).pushNamed(
                                AppRoutes.editIndicator(indicator.id),
                              );
                            },
                            borderRadius: BorderRadius.circular(8),
                            child: Padding(
                              padding: const EdgeInsets.all(16),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    children: [
                                      Expanded(
                                        child: Text(
                                          indicator.name ?? 'Unnamed Indicator',
                                          style: TextStyle(
                                            fontSize: 16,
                                            fontWeight: FontWeight.w600,
                                            color: Theme.of(context)
                                                .colorScheme
                                                .onSurface,
                                          ),
                                        ),
                                      ),
                                      Icon(
                                        Icons.chevron_right,
                                        color: Theme.of(context)
                                            .colorScheme
                                            .onSurface
                                            .withOpacity(0.6),
                                        size: 20,
                                      ),
                                    ],
                                  ),
                                  if (indicator.type != null) ...[
                                    const SizedBox(height: 8),
                                    Text(
                                      'Type: ${indicator.type}',
                                      style: TextStyle(
                                        fontSize: 14,
                                        color: Theme.of(context)
                                            .colorScheme
                                            .onSurface
                                            .withOpacity(0.6),
                                      ),
                                    ),
                                  ],
                                  if (indicator.sector != null) ...[
                                    const SizedBox(height: 4),
                                    Text(
                                      'Sector: ${indicator.sector}',
                                      style: TextStyle(
                                        fontSize: 14,
                                        color: Theme.of(context)
                                            .colorScheme
                                            .onSurface
                                            .withOpacity(0.6),
                                      ),
                                    ),
                                  ],
                                  if (indicator.subSector != null) ...[
                                    const SizedBox(height: 4),
                                    Text(
                                      'Sub-Sector: ${indicator.subSector}',
                                      style: TextStyle(
                                        fontSize: 14,
                                        color: Theme.of(context)
                                            .colorScheme
                                            .onSurface
                                            .withOpacity(0.6),
                                      ),
                                    ),
                                  ],
                                  if (indicator.description != null &&
                                      indicator.description!.isNotEmpty) ...[
                                    const SizedBox(height: 8),
                                    Text(
                                      indicator.description!,
                                      style: TextStyle(
                                        fontSize: 13,
                                        color: Theme.of(context)
                                            .colorScheme
                                            .onSurface
                                            .withOpacity(0.6),
                                      ),
                                      maxLines: 2,
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  ],
                                ],
                              ),
                            ),
                          ),
                        );
                      },
                    ),
                  );
                },
              ),
            ),
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton.extended(
        heroTag: 'indicator_bank_add_button',
        onPressed: () {
          Navigator.of(context).pushNamed(
            AppRoutes.webview,
            arguments: '/admin/indicator_bank/new',
          );
        },
        backgroundColor: Color(AppConstants.ifrcRed),
        icon: const Icon(Icons.add),
        label: Text(localizations.newIndicator),
      ),
      bottomNavigationBar: AppBottomNavigationBar(
        currentIndex: -1,
        onTap: (index) {
          Navigator.of(context).popUntil((route) {
            return route.isFirst || route.settings.name == AppRoutes.dashboard;
          });
        },
      ),
    );
  }
}
