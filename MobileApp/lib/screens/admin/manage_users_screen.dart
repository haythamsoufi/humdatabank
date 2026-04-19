import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../l10n/app_localizations.dart';
import '../../models/admin/admin_user_list_item.dart';
import '../../models/shared/user.dart';
import '../../providers/admin/manage_users_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../utils/avatar_initials.dart';
import '../../widgets/admin_filter_panel.dart';
import '../../widgets/admin_filters_bottom_sheet.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/loading_indicator.dart';
import '../../widgets/error_state.dart';
import '../../widgets/profile_leading_avatar.dart';
import '../../config/routes.dart';
import '../../utils/admin_screen_view_logging_mixin.dart';
import 'access_requests_screen.dart';
import 'admin_user_detail_screen.dart';

enum _DirectoryStatusFilter { all, active, inactive }

enum _DirectoryRoleFilter { all, systemManager, admin, focalPoint }

/// Read-only user directory for admins. Editing remains on the web backoffice only.
class ManageUsersScreen extends StatefulWidget {
  const ManageUsersScreen({super.key});

  @override
  State<ManageUsersScreen> createState() => _ManageUsersScreenState();
}

class _ManageUsersScreenState extends State<ManageUsersScreen>
    with AdminScreenViewLoggingMixin {
  @override
  String get adminScreenViewRoutePath => AppRoutes.users;

  final _searchController = TextEditingController();
  String _query = '';
  _DirectoryStatusFilter _statusFilter = _DirectoryStatusFilter.all;
  _DirectoryRoleFilter _roleFilter = _DirectoryRoleFilter.all;
  int? _countryFilterId;

  bool _isAdmin(User? user) => user?.isAdmin ?? false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      if (_isAdmin(context.read<AuthProvider>().user)) {
        context.read<ManageUsersProvider>().loadUsers();
      }
    });
  }

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  Future<void> _onRefresh() async {
    await context.read<ManageUsersProvider>().loadUsers();
  }

  Future<void> _openDirectoryFiltersSheet() async {
    final localizations = AppLocalizations.of(context)!;
    final provider = context.read<ManageUsersProvider>();
    final countries = _sortedUniqueCountries(provider.users);
    await showAdminFiltersBottomSheet<void>(
      context: context,
      builder: (_, setModalState) {
        return AdminFilterPanel(
          title: localizations.filters,
          surfaceCard: false,
          child: _UserDirectoryFilters(
            localizations: localizations,
            statusFilter: _statusFilter,
            roleFilter: _roleFilter,
            countryFilterId: _countryFilterId,
            countries: countries,
            onStatusChanged: (v) {
              setState(() => _statusFilter = v);
              setModalState(() {});
            },
            onRoleChanged: (v) {
              setState(() => _roleFilter = v);
              setModalState(() {});
            },
            onCountryChanged: (id) {
              setState(() => _countryFilterId = id);
              setModalState(() {});
            },
          ),
        );
      },
    );
  }

  List<AdminUserListItem> _applyFilters(List<AdminUserListItem> users) {
    final q = _query.trim().toLowerCase();
    Iterable<AdminUserListItem> it = users;
    if (q.isNotEmpty) {
      it = it.where((u) {
        final name = u.displayName.toLowerCase();
        final email = u.email.toLowerCase();
        final roles = u.rolesLabel.toLowerCase();
        final countries = u.countries
            .map((c) => '${c.name ?? ''} ${c.code ?? ''}'.toLowerCase())
            .join(' ');
        return name.contains(q) ||
            email.contains(q) ||
            roles.contains(q) ||
            countries.contains(q);
      });
    }
    switch (_statusFilter) {
      case _DirectoryStatusFilter.active:
        it = it.where((u) => u.active);
        break;
      case _DirectoryStatusFilter.inactive:
        it = it.where((u) => !u.active);
        break;
      case _DirectoryStatusFilter.all:
        break;
    }
    if (_roleFilter != _DirectoryRoleFilter.all) {
      it = it.where((u) => _matchesDirectoryRole(u, _roleFilter));
    }
    if (_countryFilterId != null) {
      final cid = _countryFilterId!;
      it = it.where((u) => u.countries.any((c) => c.id == cid));
    }
    return it.toList();
  }

  bool _matchesDirectoryRole(AdminUserListItem u, _DirectoryRoleFilter f) {
    final system = u.isSystemManager;
    final admin = u.computedRoleType == 'admin';
    switch (f) {
      case _DirectoryRoleFilter.all:
        return true;
      case _DirectoryRoleFilter.systemManager:
        return system;
      case _DirectoryRoleFilter.admin:
        return !system && admin;
      case _DirectoryRoleFilter.focalPoint:
        return !system && !admin;
    }
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final auth = context.watch<AuthProvider>();
    final user = auth.user;

    if (!_isAdmin(user)) {
      return Scaffold(
        appBar: AppAppBar(title: localizations.manageUsers),
        body: Center(child: Text(localizations.accessDenied)),
        bottomNavigationBar: const AppBottomNavigationBar(currentIndex: -1),
      );
    }

    final provider = context.watch<ManageUsersProvider>();
    final countryIds = provider.users
        .expand((u) => u.countries)
        .map((c) => c.id)
        .toSet();
    if (_countryFilterId != null && !countryIds.contains(_countryFilterId)) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) setState(() => _countryFilterId = null);
      });
    }
    final filtered = _applyFilters(provider.users);
    final chatbot = user?.chatbotEnabled ?? false;

    return Scaffold(
      appBar: AppAppBar(
        title: localizations.manageUsers,
        actions: [
          IconButton(
            icon: const Icon(Icons.tune),
            tooltip: localizations.filters,
            onPressed: _openDirectoryFiltersSheet,
          ),
          IconButton(
            icon: const Icon(Icons.how_to_reg_outlined),
            tooltip: localizations.accessRequestsTitle,
            onPressed: () {
              Navigator.of(context).push(
                MaterialPageRoute<void>(
                  settings: const RouteSettings(name: '/admin/access-requests'),
                  builder: (context) => const AccessRequestsScreen(),
                ),
              );
            },
          ),
        ],
      ),
      backgroundColor: Theme.of(context).scaffoldBackgroundColor,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 16, 0),
            child: TextField(
              controller: _searchController,
              decoration: InputDecoration(
                hintText: localizations.searchUsers,
                prefixIcon: const Icon(Icons.search, size: 22),
                suffixIcon: _query.isNotEmpty
                    ? IconButton(
                        icon: const Icon(Icons.clear),
                        onPressed: () {
                          _searchController.clear();
                          setState(() => _query = '');
                        },
                      )
                    : null,
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(8),
                ),
                isDense: true,
              ),
              onChanged: (v) => setState(() => _query = v),
            ),
          ),
          const SizedBox(height: 8),
          Expanded(
            child: RefreshIndicator(
              onRefresh: _onRefresh,
              child: _buildBody(context, provider, filtered, localizations),
            ),
          ),
        ],
      ),
      bottomNavigationBar: AppBottomNavigationBar(
        currentIndex: AppBottomNavigationBar.adminTabNavIndex(
          chatbotEnabled: chatbot,
        ),
        chatbotEnabled: chatbot,
      ),
    );
  }

  Widget _buildBody(
    BuildContext context,
    ManageUsersProvider provider,
    List<AdminUserListItem> filtered,
    AppLocalizations localizations,
  ) {
    if (provider.isLoading && provider.users.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: [
          SizedBox(
            height: MediaQuery.of(context).size.height * 0.5,
            child: AppLoadingIndicator(message: localizations.loadingUsers),
          ),
        ],
      );
    }

    if (provider.error != null && provider.users.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: [
          SizedBox(
            height: MediaQuery.of(context).size.height * 0.5,
            child: AppErrorState(
              message: provider.error,
              onRetry: _onRefresh,
            ),
          ),
        ],
      );
    }

    if (filtered.isEmpty) {
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        children: [
          SizedBox(
            height: MediaQuery.of(context).size.height * 0.25,
          ),
          Center(
            child: Text(
              localizations.noUsersFound,
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ),
        ],
      );
    }

    return ListView.separated(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
      itemCount: filtered.length,
      separatorBuilder: (_, _) => const Divider(height: 1),
      itemBuilder: (context, i) {
        final u = filtered[i];
        return ListTile(
          contentPadding: const EdgeInsets.symmetric(vertical: 8),
          leading: ProfileLeadingAvatar(
            initials: avatarInitialsForProfile(name: u.name, email: u.email),
            profileColorHex: u.profileColor,
            opacity: u.active ? null : 0.72,
          ),
          onTap: () {
            Navigator.of(context).push(
              MaterialPageRoute<void>(
                settings: const RouteSettings(name: AppRoutes.adminUserDetail),
                builder: (ctx) => AdminUserDetailScreen(summary: u),
              ),
            );
          },
          title: u.active
              ? Text(
                  u.displayName,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                )
              : Row(
                  children: [
                    Icon(
                      Icons.cancel_outlined,
                      size: 20,
                      color: Theme.of(context).colorScheme.outline,
                    ),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        u.displayName,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
          subtitle: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: 2),
              Text(
                u.email,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: Theme.of(context).textTheme.bodySmall,
              ),
              if (u.title != null && u.title!.trim().isNotEmpty) ...[
                const SizedBox(height: 2),
                Text(
                  u.title!,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: Theme.of(context).colorScheme.onSurfaceVariant,
                      ),
                ),
              ],
              const SizedBox(height: 6),
              _UserDirectoryMainRoleBadge(
                user: u,
                localizations: localizations,
              ),
            ],
          ),
          trailing: Icon(
            Icons.chevron_right,
            color: Theme.of(context).colorScheme.outline,
          ),
        );
      },
    );
  }
}

List<AdminUserCountryRef> _sortedUniqueCountries(List<AdminUserListItem> users) {
  final byId = <int, AdminUserCountryRef>{};
  for (final u in users) {
    for (final c in u.countries) {
      byId[c.id] = c;
    }
  }
  final list = byId.values.toList()
    ..sort((a, b) {
      final na = '${a.name ?? ''} ${a.code ?? ''}'.trim().toLowerCase();
      final nb = '${b.name ?? ''} ${b.code ?? ''}'.trim().toLowerCase();
      return na.compareTo(nb);
    });
  return list;
}

class _UserDirectoryFilters extends StatelessWidget {
  const _UserDirectoryFilters({
    required this.localizations,
    required this.statusFilter,
    required this.roleFilter,
    required this.countryFilterId,
    required this.countries,
    required this.onStatusChanged,
    required this.onRoleChanged,
    required this.onCountryChanged,
  });

  final AppLocalizations localizations;
  final _DirectoryStatusFilter statusFilter;
  final _DirectoryRoleFilter roleFilter;
  final int? countryFilterId;
  final List<AdminUserCountryRef> countries;
  final ValueChanged<_DirectoryStatusFilter> onStatusChanged;
  final ValueChanged<_DirectoryRoleFilter> onRoleChanged;
  final ValueChanged<int?> onCountryChanged;

  static String _countryLabel(AdminUserCountryRef c) {
    final name = c.name?.trim();
    final code = c.code?.trim();
    if (name != null && name.isNotEmpty) return name;
    if (code != null && code.isNotEmpty) return code;
    return '#${c.id}';
  }

  InputDecoration _dropdownDecoration(String label) {
    return InputDecoration(labelText: label);
  }

  @override
  Widget build(BuildContext context) {
    final countryIds = countries.map((c) => c.id).toSet();
    final safeCountryValue =
        countryFilterId != null && countryIds.contains(countryFilterId)
            ? countryFilterId
            : null;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        DropdownButtonFormField<_DirectoryStatusFilter>(
            key: ValueKey<_DirectoryStatusFilter>(statusFilter),
            initialValue: statusFilter,
            isExpanded: true,
            decoration: _dropdownDecoration(localizations.status),
            items: [
              DropdownMenuItem(
                value: _DirectoryStatusFilter.all,
                child: Text(localizations.all),
              ),
              DropdownMenuItem(
                value: _DirectoryStatusFilter.active,
                child: Text(localizations.active),
              ),
              DropdownMenuItem(
                value: _DirectoryStatusFilter.inactive,
                child: Text(localizations.inactive),
              ),
            ],
            onChanged: (v) {
              if (v != null) onStatusChanged(v);
            },
          ),
          AdminFilterPanel.fieldGap,
          DropdownButtonFormField<_DirectoryRoleFilter>(
            key: ValueKey<_DirectoryRoleFilter>(roleFilter),
            initialValue: roleFilter,
            isExpanded: true,
            decoration: _dropdownDecoration(localizations.roleTypeLabel),
            items: [
              DropdownMenuItem(
                value: _DirectoryRoleFilter.all,
                child: Text(localizations.usersDirectoryRoleAll),
              ),
              DropdownMenuItem(
                value: _DirectoryRoleFilter.systemManager,
                child: Text(localizations.systemManagerRole),
              ),
              DropdownMenuItem(
                value: _DirectoryRoleFilter.admin,
                child: Text(localizations.adminRole),
              ),
              DropdownMenuItem(
                value: _DirectoryRoleFilter.focalPoint,
                child: Text(localizations.focalPointRole),
              ),
            ],
            onChanged: (v) {
              if (v != null) onRoleChanged(v);
            },
          ),
          if (countries.isNotEmpty) ...[
            AdminFilterPanel.fieldGap,
            DropdownButtonFormField<int?>(
              key: ValueKey<int?>(safeCountryValue),
              initialValue: safeCountryValue,
              isExpanded: true,
              menuMaxHeight: 320,
              decoration: _dropdownDecoration(localizations.countries),
              items: [
                DropdownMenuItem<int?>(
                  value: null,
                  child: Text(localizations.usersDirectoryCountryAll),
                ),
                ...countries.map(
                  (c) => DropdownMenuItem<int?>(
                    value: c.id,
                    child: Text(
                      _countryLabel(c),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ),
              ],
              onChanged: onCountryChanged,
            ),
          ],
      ],
    );
  }
}

/// Single primary directory role: system manager (if any), else admin vs focal point.
class _UserDirectoryMainRoleBadge extends StatelessWidget {
  const _UserDirectoryMainRoleBadge({
    required this.user,
    required this.localizations,
  });

  final AdminUserListItem user;
  final AppLocalizations localizations;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    if (user.rbacRoles.isEmpty) {
      return Text(
        '—',
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: scheme.onSurfaceVariant,
            ),
      );
    }

    final bool system = user.isSystemManager;
    final bool admin = user.computedRoleType == 'admin';
    final String label = system
        ? localizations.systemManagerRole
        : (admin ? localizations.adminRole : localizations.focalPointRole);

    late final Color bg;
    late final Color fg;
    if (system) {
      // Distinct black system manager chip.
      if (Theme.of(context).brightness == Brightness.dark) {
        fg = Colors.grey.shade100;
        bg = Color.alphaBlend(
          Colors.black.withValues(alpha: 0.52),
          scheme.surfaceContainerHighest,
        );
      } else {
        fg = Colors.white;
        bg = Colors.black87;
      }
    } else if (admin) {
      // Distinct orange admin chip (not primary/teal).
      if (Theme.of(context).brightness == Brightness.dark) {
        fg = Colors.orange.shade200;
        bg = Color.alphaBlend(
          Colors.orange.withValues(alpha: 0.32),
          scheme.surfaceContainerHighest,
        );
      } else {
        fg = Colors.orange.shade900;
        bg = Colors.orange.shade100;
      }
    } else {
      fg = scheme.onSecondaryContainer;
      bg = scheme.secondaryContainer;
    }

    late final IconData icon;
    if (system) {
      icon = Icons.verified_user_rounded;
    } else if (admin) {
      icon = Icons.admin_panel_settings_rounded;
    } else {
      icon = Icons.person_rounded;
    }

    return _RoleBadge(
      label: label,
      icon: icon,
      backgroundColor: bg,
      foregroundColor: fg,
    );
  }
}

class _RoleBadge extends StatelessWidget {
  const _RoleBadge({
    required this.label,
    required this.icon,
    required this.backgroundColor,
    required this.foregroundColor,
  });

  final String label;
  final IconData icon;
  final Color backgroundColor;
  final Color foregroundColor;

  static const double _radius = 20;

  @override
  Widget build(BuildContext context) {
    final borderColor = Color.alphaBlend(
      foregroundColor.withValues(alpha: 0.18),
      backgroundColor,
    );
    final shadowColor = Theme.of(context).shadowColor.withValues(alpha: 0.12);

    return LayoutBuilder(
      builder: (context, constraints) {
        final badge = DecoratedBox(
          decoration: BoxDecoration(
            color: backgroundColor,
            borderRadius: BorderRadius.circular(_radius),
            border: Border.all(color: borderColor, width: 1),
            boxShadow: [
              BoxShadow(
                color: shadowColor,
                blurRadius: 6,
                offset: const Offset(0, 2),
                spreadRadius: -1,
              ),
              BoxShadow(
                color: foregroundColor.withValues(alpha: 0.1),
                blurRadius: 0,
                offset: const Offset(0, 1),
              ),
            ],
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            child: ConstrainedBox(
              constraints: BoxConstraints(maxWidth: constraints.maxWidth),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  ExcludeSemantics(
                    child: Icon(
                      icon,
                      size: 14,
                      color: foregroundColor,
                    ),
                  ),
                  const SizedBox(width: 5),
                  Flexible(
                    child: Text(
                      label,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.labelSmall?.copyWith(
                            color: foregroundColor,
                            fontWeight: FontWeight.w600,
                            letterSpacing: 0.1,
                            height: 1.1,
                          ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );

        return Align(
          alignment: Alignment.centerLeft,
          child: badge,
        );
      },
    );
  }
}
