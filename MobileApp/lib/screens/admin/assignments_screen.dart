import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/admin/assignments_provider.dart';
import '../../models/admin/admin_assignment.dart';
import '../../utils/theme_extensions.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../l10n/app_localizations.dart';

class AssignmentsScreen extends StatefulWidget {
  const AssignmentsScreen({super.key});

  @override
  State<AssignmentsScreen> createState() => _AssignmentsScreenState();
}

class _AssignmentsScreenState extends State<AssignmentsScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadAssignments();
    });
  }

  Future<void> _loadAssignments() async {
    await Provider.of<AssignmentsProvider>(context, listen: false)
        .loadAssignments();
  }

  Future<void> _handleDelete(AdminAssignment assignment) async {
    final localizations = AppLocalizations.of(context)!;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(localizations.deleteAssignment),
        content: const Text(
          'Are you sure you want to delete this assignment and all its associated country statuses and data?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: Text(localizations.cancel),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            style: TextButton.styleFrom(
              foregroundColor: Colors.red,
            ),
            child: Text(localizations.delete),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      final provider = Provider.of<AssignmentsProvider>(context, listen: false);
      final success = await provider.deleteAssignment(assignment.id);

      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(success
                ? localizations.assignmentDeletedSuccessfully
                : localizations.failedToDeleteAssignment),
            backgroundColor: success ? Colors.green : Colors.red,
          ),
        );

        if (success) {
          _loadAssignments();
        }
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
        title: localizations.manageAssignments,
        actions: [
        ],
      ),
      body: Consumer<AssignmentsProvider>(
        builder: (context, provider, child) {
          if (provider.isLoading) {
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
                    AppLocalizations.of(context)!.loadingAssignments,
                    style: const TextStyle(
                      color: Color(AppConstants.textSecondary),
                      fontSize: 14,
                    ),
                  ),
                ],
              ),
            );
          }

          if (provider.error != null) {
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
                    const Text(
                      'Something went wrong',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w600,
                        color: Color(AppConstants.textColor),
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      provider.error!,
                      style: const TextStyle(
                        color: Color(AppConstants.textSecondary),
                        fontSize: 14,
                      ),
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 24),
                    OutlinedButton.icon(
                      onPressed: _loadAssignments,
                      icon: const Icon(Icons.refresh, size: 18),
                      label: Text(localizations.retry),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: Color(AppConstants.ifrcRed),
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

          if (provider.assignments.isEmpty) {
            return Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(
                    Icons.assignment_outlined,
                    size: 56,
                    color: Color(AppConstants.textSecondary),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    localizations.noAssignmentsFound,
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                      color: Color(AppConstants.textColor),
                    ),
                  ),
                  const SizedBox(height: 4),
                  const Text(
                    'Create a new assignment to get started',
                    style: TextStyle(
                      fontSize: 14,
                      color: Color(AppConstants.textSecondary),
                    ),
                  ),
                ],
              ),
            );
          }

          return RefreshIndicator(
            onRefresh: () async => _loadAssignments(),
            color: Color(AppConstants.ifrcRed),
            child: ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: provider.assignments.length,
              itemBuilder: (context, index) {
                final assignment = provider.assignments[index];
                return Card(
                  margin: const EdgeInsets.only(bottom: 12),
                  elevation: 0,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8),
                    side: BorderSide(
                      color: context.borderColor,
                      width: 1,
                    ),
                  ),
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    assignment.periodName,
                                    style: const TextStyle(
                                      fontSize: 16,
                                      fontWeight: FontWeight.w600,
                                      color: Color(AppConstants.textColor),
                                    ),
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    assignment.templateName ??
                                        'Template Missing',
                                    style: const TextStyle(
                                      fontSize: 14,
                                      color: Color(AppConstants.textSecondary),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                IconButton(
                                  icon: const Icon(Icons.delete, size: 20),
                                  color: Colors.red,
                                  onPressed: () => _handleDelete(assignment),
                                  tooltip: localizations.delete,
                                ),
                              ],
                            ),
                          ],
                        ),
                        const SizedBox(height: 12),
                      ],
                    ),
                  ),
                );
              },
            ),
          );
        },
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
