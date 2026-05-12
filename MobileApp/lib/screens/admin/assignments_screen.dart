import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/admin/assignments_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../utils/theme_extensions.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/app_fade_in_up.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/async/async_body.dart';
import '../../widgets/empty_state.dart';
import '../../widgets/error_state.dart';
import '../../widgets/shimmer_list_placeholder.dart';
import '../../l10n/app_localizations.dart';
import '../../utils/admin_screen_view_logging_mixin.dart';

class AssignmentsScreen extends StatefulWidget {
  const AssignmentsScreen({super.key});

  @override
  State<AssignmentsScreen> createState() => _AssignmentsScreenState();
}

class _AssignmentsScreenState extends State<AssignmentsScreen>
    with AdminScreenViewLoggingMixin {
  @override
  String get adminScreenViewRoutePath => AppRoutes.assignments;

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

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final chatbot = context.watch<AuthProvider>().user?.chatbotEnabled ?? false;

    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(
        title: localizations.manageAssignments,
        actions: const [
        ],
      ),
      body: Consumer<AssignmentsProvider>(
        builder: (context, provider, child) {
          return AsyncBody(
            whenLoading: provider.isLoading,
            whenError: provider.error != null,
            loading: const ShimmerListPlaceholder(itemCount: 6),
            error: AppErrorState(
              message: provider.error,
              onRetry: () => provider.loadAssignments(),
            ),
            child: provider.assignments.isEmpty
                ? AppEmptyState(
                    icon: Icons.assignment_outlined,
                    title: localizations.noAssignmentsFound,
                    subtitle: localizations.getStartedByCreating,
                  )
                : RefreshIndicator(
                    onRefresh: () async => _loadAssignments(),
                    color: Color(AppConstants.ifrcRed),
                    child: ListView.builder(
                      padding: const EdgeInsets.all(16),
                      itemCount: provider.assignments.length,
                      itemBuilder: (context, index) {
                        final assignment = provider.assignments[index];
                        return AppFadeInUp(
                          staggerIndex: index,
                          child: Card(
                          margin: const EdgeInsets.only(bottom: 12),
                          elevation: 0,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(8),
                            side: BorderSide(
                              color: context.borderColor,
                              width: 1,
                            ),
                          ),
                          child: InkWell(
                            borderRadius: BorderRadius.circular(8),
                            onTap: () {
                              Navigator.of(context).pushNamed(
                                AppRoutes.assignmentDetail(assignment.id),
                                arguments: assignment,
                              );
                            },
                            child: Padding(
                              padding: const EdgeInsets.all(16),
                              child: Row(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment:
                                          CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          assignment.periodName,
                                          style: theme.textTheme.titleMedium
                                              ?.copyWith(
                                            fontWeight: FontWeight.w600,
                                            color:
                                                theme.colorScheme.onSurface,
                                          ),
                                        ),
                                        const SizedBox(height: 4),
                                        Text(
                                          assignment.templateName ??
                                              localizations.templateMissing,
                                          style: theme.textTheme.bodyMedium
                                              ?.copyWith(
                                            color: theme
                                                .colorScheme.onSurfaceVariant,
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                  Icon(
                                    Icons.chevron_right,
                                    color: context.textSecondaryColor,
                                  ),
                                ],
                              ),
                            ),
                          ),
                          ),
                        );
                      },
                    ),
                  ),
          );
        },
      ),
      bottomNavigationBar: AppBottomNavigationBar(
        currentIndex: AppBottomNavigationBar.adminTabNavIndex(
          chatbotEnabled: chatbot,
        ),
        chatbotEnabled: chatbot,
        onTap: (index) {
          Navigator.of(context).popUntil((route) {
            return route.isFirst || route.settings.name == AppRoutes.dashboard;
          });
        },
      ),
    );
  }
}
