import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/shared/auth_provider.dart';
import '../models/shared/user.dart';
import '../config/routes.dart';
import '../utils/constants.dart';
import 'modern_navigation_drawer.dart';

class AdminDrawer extends StatelessWidget {
  const AdminDrawer({super.key});

  bool _isAdmin(User? user) => user?.isAdmin ?? false;

  static final Color _brandRed = Color(AppConstants.ifrcRed);

  @override
  Widget build(BuildContext context) {
    return Consumer<AuthProvider>(
      builder: (context, authProvider, child) {
        final user = authProvider.user;

        if (!_isAdmin(user)) {
          return const SizedBox.shrink();
        }

        final theme = Theme.of(context);

        return Drawer(
          backgroundColor: theme.colorScheme.surface,
          elevation: 1,
          shadowColor: Colors.black.withValues(alpha: 0.1),
          surfaceTintColor: Colors.transparent,
          shape: modernDrawerShape(),
          child: SafeArea(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _AdminDrawerHeader(user: user),
                Expanded(
                  child: ListView(
                    padding: const EdgeInsets.only(top: 8, bottom: 16),
                    children: [
                      const ModernDrawerSectionTitle(label: 'General'),
                      ModernDrawerTile(
                        icon: Icons.home_rounded,
                        title: 'Dashboard',
                        iconColor: _brandRed,
                        onTap: () {
                          Navigator.pop(context);
                          Navigator.of(context).pushNamed(AppRoutes.dashboard);
                        },
                      ),
                      ModernDrawerTile(
                        icon: Icons.dashboard_rounded,
                        title: 'Admin Dashboard',
                        iconColor: _brandRed,
                        onTap: () {
                          Navigator.pop(context);
                          Navigator.of(context).pushNamed(
                            AppRoutes.webview,
                            arguments: '/admin/dashboard',
                          );
                        },
                      ),
                      ModernDrawerTile(
                        icon: Icons.description_rounded,
                        title: 'Document Management',
                        iconColor: _brandRed,
                        onTap: () {
                          Navigator.pop(context);
                          Navigator.of(context).pushNamed(
                            AppRoutes.webview,
                            arguments: '/admin/documents',
                          );
                        },
                      ),
                      ModernDrawerTile(
                        icon: Icons.translate_rounded,
                        title: 'Translation Management',
                        iconColor: _brandRed,
                        onTap: () {
                          Navigator.pop(context);
                          Navigator.of(context).pushNamed(
                            AppRoutes.webview,
                            arguments: '/admin/translations',
                          );
                        },
                      ),
                      if (user?.role == 'system_manager')
                        ModernDrawerTile(
                          icon: Icons.settings_rounded,
                          title: 'System Configuration',
                          iconColor: _brandRed,
                          onTap: () {
                            Navigator.pop(context);
                            Navigator.of(context).pushNamed(
                              AppRoutes.webview,
                              arguments: '/admin/settings',
                            );
                          },
                        ),
                      const SizedBox(height: 8),
                      const ModernDrawerSectionTitle(label: 'Form & data'),
                      ModernDrawerTile(
                        icon: Icons.article_rounded,
                        title: 'Manage Templates',
                        iconColor: _brandRed,
                        onTap: () {
                          Navigator.pop(context);
                          Navigator.of(context).pushNamed(AppRoutes.templates);
                        },
                      ),
                      ModernDrawerTile(
                        icon: Icons.assignment_rounded,
                        title: 'Manage Assignments',
                        iconColor: _brandRed,
                        onTap: () {
                          Navigator.pop(context);
                          Navigator.of(context).pushNamed(AppRoutes.assignments);
                        },
                      ),
                      const SizedBox(height: 8),
                      const ModernDrawerSectionTitle(label: 'Website'),
                      ModernDrawerTile(
                        icon: Icons.folder_open_rounded,
                        title: 'Manage Resources',
                        iconColor: _brandRed,
                        onTap: () {
                          Navigator.pop(context);
                          Navigator.of(context).pushNamed(
                            AppRoutes.webview,
                            arguments: '/admin/resources',
                          );
                        },
                      ),
                      const SizedBox(height: 8),
                      const ModernDrawerSectionTitle(label: 'Reference data'),
                      ModernDrawerTile(
                        icon: Icons.account_tree_rounded,
                        title: 'Organizational Structure',
                        iconColor: _brandRed,
                        onTap: () {
                          Navigator.pop(context);
                          Navigator.of(context).pushNamed(
                            AppRoutes.webview,
                            arguments: '/admin/organization',
                          );
                        },
                      ),
                      ModernDrawerTile(
                        icon: Icons.storage_rounded,
                        title: 'Indicator Bank',
                        iconColor: _brandRed,
                        onTap: () {
                          Navigator.pop(context);
                          Navigator.of(context).pushNamed(
                            AppRoutes.webview,
                            arguments: '/admin/indicator-bank',
                          );
                        },
                      ),
                      const SizedBox(height: 8),
                      const ModernDrawerSectionTitle(label: 'Analytics'),
                      ModernDrawerTile(
                        icon: Icons.bar_chart_rounded,
                        title: 'User Analytics',
                        iconColor: _brandRed,
                        onTap: () {
                          Navigator.pop(context);
                          Navigator.of(context).pushNamed(
                            AppRoutes.webview,
                            arguments: '/admin/analytics',
                          );
                        },
                      ),
                      ModernDrawerTile(
                        icon: Icons.history_rounded,
                        title: 'Audit Trail',
                        iconColor: _brandRed,
                        onTap: () {
                          Navigator.pop(context);
                          Navigator.of(context).pushNamed(
                            AppRoutes.webview,
                            arguments: '/admin/audit-trail',
                          );
                        },
                      ),
                      Padding(
                        padding: const EdgeInsets.fromLTRB(20, 20, 20, 8),
                        child: Text(
                          'Built by Haytham Alsoufi,\nvolunteer of Syrian Arab Red Crescent',
                          textAlign: TextAlign.center,
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                            height: 1.35,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _AdminDrawerHeader extends StatelessWidget {
  const _AdminDrawerHeader({required this.user});

  final User? user;

  @override
  Widget build(BuildContext context) {
    final red = Color(AppConstants.ifrcRed);
    return Material(
      color: Colors.transparent,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.fromLTRB(20, 20, 20, 20),
        decoration: BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [
              red,
              red.withValues(alpha: 0.88),
            ],
          ),
          borderRadius: const BorderRadius.only(
            bottomLeft: Radius.circular(20),
            bottomRight: Radius.circular(20),
          ),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: Colors.white.withValues(alpha: 0.22),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(
                    Icons.admin_panel_settings_rounded,
                    color: Colors.white,
                    size: 26,
                  ),
                ),
                const SizedBox(width: 14),
                const Expanded(
                  child: Text(
                    'Admin Panel',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 22,
                      fontWeight: FontWeight.w700,
                      letterSpacing: -0.3,
                    ),
                  ),
                ),
              ],
            ),
            if (user != null) ...[
              const SizedBox(height: 14),
              Text(
                user!.displayName,
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.92),
                  fontSize: 15,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
