import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../l10n/app_localizations.dart';
import '../../models/admin/admin_user_detail.dart';
import '../../models/admin/admin_user_list_item.dart';
import '../../providers/admin/manage_users_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../utils/avatar_initials.dart';
import '../../widgets/profile_leading_avatar.dart';
import '../../utils/constants.dart';
import '../../utils/network_availability.dart';
import '../../utils/ios_constants.dart';
import '../../utils/theme_extensions.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/profile_color_picker_dialog.dart';
import '../../config/routes.dart';
import '../../utils/admin_screen_view_logging_mixin.dart';

/// Profile and (with permission) granular admin View/Manage matrix + Data Explorer; entity grants read-only.
class AdminUserDetailScreen extends StatefulWidget {
  const AdminUserDetailScreen({super.key, required this.summary});

  final AdminUserListItem summary;

  @override
  State<AdminUserDetailScreen> createState() => _AdminUserDetailScreenState();
}

class _AdminUserDetailScreenState extends State<AdminUserDetailScreen>
    with AdminScreenViewLoggingMixin {
  @override
  String get adminScreenViewRoutePath => AppRoutes.adminUserDetail;

  AdminUserDetail? _detail;
  bool _loading = true;
  String? _error;
  bool _saving = false;
  bool _syncingFields = false;

  late final TextEditingController _nameController;
  late final TextEditingController _titleController;
  late final TextEditingController _profileColorController;
  bool _draftActive = true;
  bool _draftChatbot = true;

  /// RBAC matrix + Data Explorer (when [admin.users.roles.assign] and catalog load succeeds).
  Map<String, int>? _roleCodeToId;
  bool _canAssignRoles = false;
  Map<String, _ModuleAccess>? _matrixDraft;
  Map<String, _ModuleAccess>? _matrixInitial;
  bool _matrixLocked = false;
  bool _deDraftTable = false;
  bool _deDraftAnalysis = false;
  bool _deDraftCompliance = false;
  bool _deInitialTable = false;
  bool _deInitialAnalysis = false;
  bool _deInitialCompliance = false;

  @override
  void initState() {
    super.initState();
    _nameController = TextEditingController();
    _titleController = TextEditingController();
    _profileColorController = TextEditingController();
    void onFieldChanged() {
      if (_syncingFields) return;
      setState(() {});
    }

    _nameController.addListener(onFieldChanged);
    _titleController.addListener(onFieldChanged);
    _profileColorController.addListener(onFieldChanged);
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  @override
  void dispose() {
    _nameController.dispose();
    _titleController.dispose();
    _profileColorController.dispose();
    super.dispose();
  }

  void _syncControllersFromDetail(AdminUserDetail d) {
    _syncingFields = true;
    _nameController.text = d.name ?? '';
    _titleController.text = d.title ?? '';
    _profileColorController.text = (d.profileColor != null && d.profileColor!.trim().isNotEmpty)
        ? d.profileColor!.trim()
        : '#3B82F6';
    _draftActive = d.active;
    _draftChatbot = d.chatbotEnabled;
    _syncingFields = false;
  }

  Map<String, _ModuleAccess> _cloneModuleMap(Map<String, _ModuleAccess> m) {
    final out = <String, _ModuleAccess>{};
    for (final e in m.entries) {
      final a = _ModuleAccess();
      a.view = e.value.view;
      a.manage = e.value.manage;
      out[e.key] = a;
    }
    return out;
  }

  bool _moduleMapsEqual(Map<String, _ModuleAccess> a, Map<String, _ModuleAccess> b) {
    final keys = {...a.keys, ...b.keys};
    for (final k in keys) {
      final av = a[k] ?? _ModuleAccess();
      final bv = b[k] ?? _ModuleAccess();
      if (av.view != bv.view || av.manage != bv.manage) return false;
    }
    return true;
  }

  /// Aligns with [user_form.html]: Manage implies View for each admin feature row.
  void _normalizeManageImpliesViewInMap(Map<String, _ModuleAccess> map) {
    for (final m in map.values) {
      if (m.manage) m.view = true;
    }
  }

  void _syncRoleDraftFromDetail(AdminUserDetail d) {
    final adminSys =
        d.rbacRoles.where((r) => r.code == 'system_manager' || r.code.startsWith('admin_')).toList();
    final model = _parseAdminAccess(adminSys);
    // `admin_core` is a bundle but often coexists with granular admin_*_viewer/manager roles.
    // Keep the matrix editable so those granular cells can be changed; only lock for full bundle or system manager.
    _matrixLocked = model.hasAdminFull || model.systemManager;
    _matrixInitial = _cloneModuleMap(model.modules);
    _matrixDraft = _cloneModuleMap(model.modules);
    _normalizeManageImpliesViewInMap(_matrixInitial!);
    _normalizeManageImpliesViewInMap(_matrixDraft!);
    _deInitialTable = model.deTable;
    _deInitialAnalysis = model.deAnalysis;
    _deInitialCompliance = model.deCompliance;
    _deDraftTable = model.deTable;
    _deDraftAnalysis = model.deAnalysis;
    _deDraftCompliance = model.deCompliance;
  }

  bool _isProfileDirty(AdminUserDetail d) {
    if (_nameController.text.trim() != (d.name ?? '').trim()) return true;
    if (_titleController.text.trim() != (d.title ?? '').trim()) return true;
    final pc = _profileColorController.text.trim();
    final serverPc = (d.profileColor != null && d.profileColor!.trim().isNotEmpty)
        ? d.profileColor!.trim()
        : '#3B82F6';
    if (pc.toUpperCase() != serverPc.toUpperCase()) return true;
    if (_draftActive != d.active) return true;
    if (_draftChatbot != d.chatbotEnabled) return true;
    return false;
  }

  bool _isRolesDirty() {
    if (_matrixDraft == null || _matrixInitial == null) return false;
    if (!_canAssignRoles || _matrixLocked) return false;
    if (!_moduleMapsEqual(_matrixDraft!, _matrixInitial!)) return true;
    if (_deDraftTable != _deInitialTable) return true;
    if (_deDraftAnalysis != _deInitialAnalysis) return true;
    if (_deDraftCompliance != _deInitialCompliance) return true;
    return false;
  }

  bool _isDirty(AdminUserDetail d) => _isProfileDirty(d) || _isRolesDirty();

  bool _preserveRoleCodeForRebuild(String code) {
    if (code.startsWith('assignment_')) return true;
    if (code == 'system_manager' || code == 'admin_full' || code == 'admin_core') return true;
    if (RegExp(r'^admin_.+_viewer$').hasMatch(code)) return false;
    if (RegExp(r'^admin_.+_manager$').hasMatch(code)) return false;
    if (code == 'admin_security_responder' || code == 'admin_security_viewer') return false;
    if (code.startsWith('admin_data_explorer')) return false;
    return true;
  }

  List<int>? _computeFinalRoleIds(AdminUserDetail d) {
    final cat = _roleCodeToId;
    if (cat == null || _matrixDraft == null) return null;
    final ids = <int>{};
    for (final r in d.rbacRoles) {
      if (_preserveRoleCodeForRebuild(r.code)) {
        ids.add(r.id);
      }
    }
    for (final e in _matrixDraft!.entries) {
      final key = e.key;
      final acc = e.value;
      if (key == 'security') {
        if (acc.view) {
          final id = cat['admin_security_viewer'];
          if (id != null) ids.add(id);
        }
        if (acc.manage) {
          final id = cat['admin_security_responder'];
          if (id != null) ids.add(id);
        }
      } else {
        if (acc.view) {
          final id = cat['admin_${key}_viewer'];
          if (id != null) ids.add(id);
        }
        if (acc.manage) {
          final id = cat['admin_${key}_manager'];
          if (id != null) ids.add(id);
        }
      }
    }
    if (_deDraftTable) {
      final id = cat['admin_data_explorer_data_table'];
      if (id != null) ids.add(id);
    }
    if (_deDraftAnalysis) {
      final id = cat['admin_data_explorer_analysis'];
      if (id != null) ids.add(id);
    }
    if (_deDraftCompliance) {
      final id = cat['admin_data_explorer_compliance'];
      if (id != null) ids.add(id);
    }
    if (ids.isEmpty) return null;
    return ids.toList();
  }

  void _setMatrixCell(String moduleKey, {bool? view, bool? manage}) {
    if (_matrixDraft == null) return;
    setState(() {
      final m = _matrixDraft!.putIfAbsent(moduleKey, () => _ModuleAccess());
      if (manage != null) {
        m.manage = manage;
        if (manage) {
          m.view = true;
        }
      }
      if (view != null && !m.manage) {
        m.view = view;
      }
    });
  }

  List<MapEntry<String, _ModuleAccess>> _matrixRowsForDisplay() {
    if (_matrixDraft == null || _matrixInitial == null) return [];
    final keys = {..._matrixInitial!.keys, ..._matrixDraft!.keys};
    for (final k in keys) {
      _matrixDraft!.putIfAbsent(k, () => _ModuleAccess());
    }
    final sorted = keys.toList()
      ..sort(
        (a, b) => _adminModuleTitle(a).toLowerCase().compareTo(
              _adminModuleTitle(b).toLowerCase(),
            ),
      );
    return sorted.map((k) => MapEntry(k, _matrixDraft![k]!)).toList();
  }

  String? _normalizeProfileColorHex(String raw) {
    var s = raw.trim();
    if (s.isEmpty) return null;
    if (!s.startsWith('#')) s = '#$s';
    if (!RegExp(r'^#[0-9A-Fa-f]{6}$').hasMatch(s)) return null;
    return s;
  }

  Future<void> _openProfileColorPicker(BuildContext context) async {
    final current = _normalizeProfileColorHex(_profileColorController.text) ?? '#3B82F6';
    final picked = await showProfileColorPickerDialog(context, current);
    if (picked != null && mounted) {
      setState(() {
        _profileColorController.text = picked;
      });
    }
  }

  Future<void> _load() async {
    if (shouldDeferRemoteFetch) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = AppLocalizations.of(context)!.offlineNoInternet;
      });
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    final provider = context.read<ManageUsersProvider>();
    final detail = await provider.fetchUserDetail(widget.summary.id);
    final catalog = detail != null ? await provider.fetchRbacRoleCatalog() : null;
    if (!mounted) return;
    setState(() {
      _loading = false;
      if (detail == null) {
        _error = AppLocalizations.of(context)!.failedLoadUserProfile;
      } else {
        _detail = detail;
        _syncControllersFromDetail(detail);
        _roleCodeToId = catalog;
        _canAssignRoles = catalog != null;
        _syncRoleDraftFromDetail(detail);
      }
    });
  }

  Future<void> _confirmSave(BuildContext context, AppLocalizations loc, AdminUserDetail d) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(loc.adminUserDetailConfirmSaveTitle),
        content: Text(loc.adminUserDetailConfirmSaveMessage),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: Text(loc.cancel),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            child: Text(loc.save),
          ),
        ],
      ),
    );
    if (ok == true && mounted) {
      await _save(loc, d);
    }
  }

  Future<void> _save(AppLocalizations loc, AdminUserDetail d) async {
    final profileDirty = _isProfileDirty(d);
    final rolesDirty = _isRolesDirty();

    String? hex;
    if (profileDirty) {
      hex = _normalizeProfileColorHex(_profileColorController.text);
      if (hex == null) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(loc.adminUserDetailInvalidProfileColor)),
        );
        return;
      }
    }

    List<int>? roleIds;
    if (rolesDirty) {
      roleIds = _computeFinalRoleIds(d);
      if (roleIds == null || roleIds.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(loc.adminUserDetailRbacIncomplete)),
        );
        return;
      }
    }

    setState(() => _saving = true);
    final String? err;
    if (profileDirty && rolesDirty) {
      err = await context.read<ManageUsersProvider>().updateUserProfile(
            d.id,
            name: _nameController.text.trim(),
            title: _titleController.text.trim().isEmpty ? null : _titleController.text.trim(),
            active: _draftActive,
            chatbotEnabled: _draftChatbot,
            profileColor: hex,
            rbacRoleIds: roleIds,
          );
    } else if (profileDirty) {
      err = await context.read<ManageUsersProvider>().updateUserProfile(
            d.id,
            name: _nameController.text.trim(),
            title: _titleController.text.trim().isEmpty ? null : _titleController.text.trim(),
            active: _draftActive,
            chatbotEnabled: _draftChatbot,
            profileColor: hex,
          );
    } else if (rolesDirty) {
      err = await context.read<ManageUsersProvider>().updateUserProfile(
            d.id,
            rbacRoleIds: roleIds,
          );
    } else {
      err = null;
    }

    if (!mounted) return;
    setState(() => _saving = false);
    if (err != null) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(err)));
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(loc.adminUserDetailChangesSaved)),
    );
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final detail = _detail;
    final title = detail?.displayName ?? widget.summary.displayName;
    final dirty = detail != null && _isDirty(detail);
    final authId = context.watch<AuthProvider>().user?.id;
    final isSelf = authId != null && authId == widget.summary.id;

    return Scaffold(
      appBar: AppAppBar(title: title),
      bottomNavigationBar: detail != null && dirty
          ? SafeArea(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                child: FilledButton.icon(
                  onPressed: _saving ? null : () => _confirmSave(context, loc, detail),
                  icon: _saving
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.save_outlined),
                  label: Text(loc.adminUserDetailSaveChanges),
                ),
              ),
            )
          : null,
      body: _loading && detail == null
          ? Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const CircularProgressIndicator(),
                  const SizedBox(height: 16),
                  Text(loc.loadingUserProfile),
                ],
              ),
            )
          : _error != null && detail == null
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(Icons.error_outline, size: 48, color: Theme.of(context).colorScheme.error),
                        const SizedBox(height: 16),
                        Text(_error!, textAlign: TextAlign.center),
                        const SizedBox(height: 24),
                        FilledButton.icon(
                          onPressed: _load,
                          icon: const Icon(Icons.refresh),
                          label: Text(loc.retry),
                        ),
                      ],
                    ),
                  ),
                )
              : RefreshIndicator(
                  onRefresh: _load,
                  child: ListView(
                    padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
                    children: [
                      if (detail != null) ...[
                        _accountCard(context, loc, detail, isSelf: isSelf),
                        const SizedBox(height: 16),
                        _sectionTitle(context, loc.assignedRolesTitle),
                        const SizedBox(height: 8),
                        _rolesOverview(context, loc, detail),
                        const SizedBox(height: 20),
                        _sectionTitle(context, loc.entityPermissionsTitle),
                        const SizedBox(height: 8),
                        _entityListGrouped(context, loc, detail.entityPermissions),
                        const SizedBox(height: 24),
                        Text(
                          loc.manageUsersDetailFooter,
                          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                                color: Theme.of(context).colorScheme.onSurfaceVariant,
                              ),
                        ),
                      ],
                    ],
                  ),
                ),
    );
  }

  Widget _sectionTitle(BuildContext context, String text) {
    return Text(
      text,
      style: Theme.of(context).textTheme.titleSmall?.copyWith(
            fontWeight: FontWeight.w600,
          ),
    );
  }

  /// Same parsing as [SettingsScreen] profile header (`#RRGGBB` → accent, else default blue).
  Color _profileAccentColor(String? colorString) {
    if (colorString == null || colorString.isEmpty) {
      return const Color(AppConstants.semanticDefaultProfileAccent);
    }
    try {
      final clean = colorString.replaceFirst('#', '0xFF');
      return Color(int.parse(clean));
    } catch (_) {
      return const Color(AppConstants.semanticDefaultProfileAccent);
    }
  }

  Widget _accountCard(
    BuildContext context,
    AppLocalizations loc,
    AdminUserDetail d, {
    required bool isSelf,
  }) {
    final profileHex = _normalizeProfileColorHex(_profileColorController.text) ??
        d.profileColor ??
        '#3B82F6';
    final profileColor = _profileAccentColor(profileHex);
    final nameTrim = _nameController.text.trim();
    final initials = avatarInitialsForProfile(
      name: nameTrim.isEmpty ? null : nameTrim,
      email: d.email,
    );
    final theme = Theme.of(context);

    InputDecoration fieldDeco(String label, {String? hint, bool compact = false}) {
      final outline = theme.colorScheme.outlineVariant.withValues(alpha: 0.45);
      return InputDecoration(
        labelText: label,
        hintText: hint,
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: outline),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide(color: theme.colorScheme.secondary, width: 2),
        ),
        filled: true,
        fillColor: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.35),
        isDense: true,
        contentPadding: compact
            ? const EdgeInsets.symmetric(horizontal: 12, vertical: 8)
            : const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
      );
    }

    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: context.subtleSurfaceColor,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: theme.colorScheme.outlineVariant.withValues(alpha: 0.45),
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 14, 14, 16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                ProfileLeadingAvatar(
                  initials: initials,
                  backgroundColor: profileColor,
                  size: 40,
                  useGradient: true,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      TextField(
                        controller: _nameController,
                        textCapitalization: TextCapitalization.words,
                        decoration: fieldDeco(loc.name, compact: true),
                        maxLines: 1,
                        minLines: 1,
                        style: theme.textTheme.bodyLarge,
                        maxLength: 100,
                        buildCounter: (
                          context, {
                          required currentLength,
                          required isFocused,
                          maxLength,
                        }) =>
                            null,
                      ),
                      const SizedBox(height: 6),
                      Text.rich(
                        TextSpan(
                          children: [
                            TextSpan(
                              text: '${loc.email} ',
                              style: theme.textTheme.labelSmall?.copyWith(
                                color: theme.colorScheme.onSurfaceVariant,
                              ),
                            ),
                            TextSpan(
                              text: d.email,
                              style: theme.textTheme.bodySmall,
                            ),
                          ],
                        ),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 6),
                      Wrap(
                        spacing: 6,
                        runSpacing: 4,
                        crossAxisAlignment: WrapCrossAlignment.center,
                        children: [
                          _statusChip(context, loc, _draftActive),
                          _primaryDirectoryRoleChip(context, loc, d),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 10),
              child: Divider(height: 1, color: theme.dividerColor),
            ),
            TextField(
              controller: _titleController,
              decoration: fieldDeco(loc.title, compact: true),
              maxLines: 1,
              minLines: 1,
              style: theme.textTheme.bodyLarge,
              maxLength: 100,
              buildCounter: (
                context, {
                required currentLength,
                required isFocused,
                maxLength,
              }) =>
                  null,
            ),
            const SizedBox(height: 8),
            Material(
              color: Colors.transparent,
              child: InkWell(
                onTap: () => _openProfileColorPicker(context),
                borderRadius: BorderRadius.circular(8),
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      Expanded(
                        child: Text(
                          loc.adminUserDetailProfileColorLabel,
                          style: theme.textTheme.bodySmall?.copyWith(
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ),
                      Container(
                        width: 22,
                        height: 22,
                        decoration: BoxDecoration(
                          color: profileColor,
                          shape: BoxShape.circle,
                          border: Border.all(
                            color: theme.dividerColor,
                            width: 1,
                          ),
                        ),
                      ),
                      const SizedBox(width: 4),
                      Icon(
                        Icons.chevron_right,
                        size: 18,
                        color: theme.colorScheme.onSurface.withValues(alpha: 0.45),
                      ),
                    ],
                  ),
                ),
              ),
            ),
            const SizedBox(height: 4),
            _compactSwitchRow(
              context,
              label: loc.activeStatus,
              value: _draftActive,
              onChanged: isSelf
                  ? (v) {
                      if (!v) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(content: Text(loc.adminUserDetailCannotDeactivateSelf)),
                        );
                        return;
                      }
                      setState(() => _draftActive = v);
                    }
                  : (v) => setState(() => _draftActive = v),
            ),
            _compactSwitchRow(
              context,
              label: loc.chatbot,
              value: _draftChatbot,
              onChanged: (v) => setState(() => _draftChatbot = v),
            ),
          ],
        ),
      ),
    );
  }

  /// Tighter than [SwitchListTile] (no list min heights / subtitle gap).
  Widget _compactSwitchRow(
    BuildContext context, {
    required String label,
    required bool value,
    required ValueChanged<bool>? onChanged,
  }) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(top: 2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Expanded(
            child: Text(
              label,
              style: theme.textTheme.bodySmall?.copyWith(fontWeight: FontWeight.w500),
            ),
          ),
          Transform.scale(
            scale: 0.88,
            alignment: Alignment.centerRight,
            child: Switch(
              value: value,
              onChanged: onChanged,
              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
          ),
        ],
      ),
    );
  }

  Widget _statusChip(BuildContext context, AppLocalizations loc, bool active) {
    return Chip(
      visualDensity: VisualDensity.compact,
      label: Text(active ? loc.activeStatus : loc.inactiveStatus),
      avatar: Icon(
        active ? Icons.check_circle_outline : Icons.cancel_outlined,
        size: 18,
        color: active ? IOSColors.systemGreen : Theme.of(context).colorScheme.outline,
      ),
    );
  }

  /// System manager shown alone; API still sets `computed_role_type` to admin for SM users.
  Widget _primaryDirectoryRoleChip(BuildContext context, AppLocalizations loc, AdminUserDetail d) {
    if (d.rbacRoles.isEmpty) {
      return Chip(
        visualDensity: VisualDensity.compact,
        label: Text(loc.emptyEmDash),
      );
    }
    final scheme = Theme.of(context).colorScheme;
    final system = d.isSystemManager;
    final admin = d.computedRoleType == 'admin';
    final label =
        system ? loc.systemManagerRole : (admin ? loc.adminRole : loc.focalPointRole);
    final Color bg;
    final Color? labelColor;
    if (system) {
      if (Theme.of(context).brightness == Brightness.dark) {
        bg = Color.alphaBlend(
          Colors.black.withValues(alpha: 0.52),
          scheme.surfaceContainerHighest,
        );
        labelColor = Colors.grey.shade100;
      } else {
        bg = Colors.black87;
        labelColor = Colors.white;
      }
    } else if (admin) {
      if (Theme.of(context).brightness == Brightness.dark) {
        bg = Color.alphaBlend(
          Colors.orange.withValues(alpha: 0.32),
          scheme.surfaceContainerHighest,
        );
        labelColor = Colors.orange.shade200;
      } else {
        bg = Colors.orange.shade100;
        labelColor = Colors.orange.shade900;
      }
    } else {
      bg = scheme.secondaryContainer.withValues(alpha: 0.45);
      labelColor = null;
    }
    return Chip(
      visualDensity: VisualDensity.compact,
      label: Text(label),
      backgroundColor: bg,
      labelStyle: labelColor != null
          ? Theme.of(context).textTheme.labelLarge?.copyWith(color: labelColor)
          : null,
    );
  }

  Widget _rolesOverview(BuildContext context, AppLocalizations loc, AdminUserDetail d) {
    final assignment = d.rbacRoles.where((r) => r.code.startsWith('assignment_')).toList();
    final adminSys = d.rbacRoles
        .where((r) => r.code == 'system_manager' || r.code.startsWith('admin_'))
        .toList();
    final other = d.rbacRoles
        .where(
          (r) =>
              r.code != 'system_manager' &&
              !r.code.startsWith('admin_') &&
              !r.code.startsWith('assignment_'),
        )
        .toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (assignment.isNotEmpty) ...[
          const SizedBox(height: 12),
          Text(
            loc.userDirAssignmentRoles,
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: assignment.map((r) => _roleNameChip(context, r.name, r.code)).toList(),
          ),
        ],
        if (adminSys.isNotEmpty) ...[
          const SizedBox(height: 12),
          Text(
            loc.userDirAdminRoles,
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
          ),
          const SizedBox(height: 6),
          _adminSystemRolesGrouped(context, loc, adminSys),
        ],
        if (other.isNotEmpty) ...[
          const SizedBox(height: 12),
          Text(
            loc.userDirOtherRoles,
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: other.map((r) => _roleNameChip(context, r.name, r.code)).toList(),
          ),
        ],
        if (assignment.isEmpty && adminSys.isEmpty && other.isEmpty)
          Text(
            loc.noRolesAssigned,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
          ),
      ],
    );
  }

  /// Admin/system roles: bundle notes, then a View/Manage matrix by area, Data Explorer tabs, leftover chips.
  Widget _adminSystemRolesGrouped(
    BuildContext context,
    AppLocalizations loc,
    List<AdminRbacRoleDetail> adminSys,
  ) {
    final model = _parseAdminAccess(adminSys);
    final scheme = Theme.of(context).colorScheme;
    final matrixLocked = _matrixLocked;
    final editable = _canAssignRoles && !matrixLocked && _roleCodeToId != null;

    final List<MapEntry<String, _ModuleAccess>> rows;
    if (matrixLocked) {
      rows = model.modules.entries.where((e) => e.value.view || e.value.manage).toList()
        ..sort(
          (a, b) => _adminModuleTitle(a.key).toLowerCase().compareTo(
                _adminModuleTitle(b.key).toLowerCase(),
              ),
        );
    } else if (editable) {
      rows = _matrixRowsForDisplay();
    } else {
      rows = model.modules.entries.where((e) => e.value.view || e.value.manage).toList()
        ..sort(
          (a, b) => _adminModuleTitle(a.key).toLowerCase().compareTo(
                _adminModuleTitle(b.key).toLowerCase(),
              ),
        );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (model.hasAdminFull) ...[
          ListTile(
            contentPadding: EdgeInsets.zero,
            dense: true,
            leading: Icon(Icons.layers_outlined, color: context.navyIconColor, size: 24),
            title: Text(loc.adminRoleNoteAdminFull),
          ),
        ],
        if (model.hasAdminCore) ...[
          ListTile(
            contentPadding: EdgeInsets.zero,
            dense: true,
            leading: Icon(Icons.widgets_outlined, color: scheme.secondary, size: 24),
            title: Text(loc.adminRoleNoteAdminCore),
          ),
        ],
        if (matrixLocked && (model.hasAdminFull || model.systemManager)) ...[
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Text(
              loc.adminUserDetailMatrixReadOnlyBundled,
              style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: scheme.onSurfaceVariant,
                  ),
            ),
          ),
        ],
        if (rows.isNotEmpty) ...[
          const SizedBox(height: 8),
          _adminAccessMatrixCard(
            context,
            loc,
            rows,
            editable: editable,
          ),
        ],
        if (matrixLocked && model.hasAnyDataExplorer) ...[
          const SizedBox(height: 12),
          _dataExplorerAccessCard(
            context,
            loc,
            dataTable: model.deTable,
            analysis: model.deAnalysis,
            compliance: model.deCompliance,
            editable: false,
          ),
        ],
        if (!matrixLocked && editable) ...[
          const SizedBox(height: 12),
          _dataExplorerAccessCard(
            context,
            loc,
            dataTable: _deDraftTable,
            analysis: _deDraftAnalysis,
            compliance: _deDraftCompliance,
            editable: true,
            onDataTable: (v) => setState(() => _deDraftTable = v),
            onAnalysis: (v) => setState(() => _deDraftAnalysis = v),
            onCompliance: (v) => setState(() => _deDraftCompliance = v),
          ),
        ],
        if (!matrixLocked && !editable && model.hasAnyDataExplorer) ...[
          const SizedBox(height: 12),
          _dataExplorerAccessCard(
            context,
            loc,
            dataTable: model.deTable,
            analysis: model.deAnalysis,
            compliance: model.deCompliance,
            editable: false,
          ),
        ],
        if (model.leftover.isNotEmpty) ...[
          const SizedBox(height: 12),
          Text(
            loc.adminRoleOtherAdminRoles,
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: scheme.onSurfaceVariant,
                ),
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: _sortAdminRolesByName(model.leftover)
                .map((r) => _roleNameChip(context, r.name, r.code))
                .toList(),
          ),
        ],
      ],
    );
  }

  _AdminAccessModel _parseAdminAccess(List<AdminRbacRoleDetail> adminSys) {
    final model = _AdminAccessModel();
    final consumed = <String>{};
    final viewerRe = RegExp(r'^admin_(.+)_viewer$');
    final managerRe = RegExp(r'^admin_(.+)_manager$');

    for (final r in adminSys) {
      final c = r.code;
      if (c == 'system_manager') {
        model.systemManager = true;
        consumed.add(c);
        continue;
      }
      if (c == 'admin_full') {
        model.hasAdminFull = true;
        consumed.add(c);
        continue;
      }
      if (c == 'admin_core') {
        model.hasAdminCore = true;
        consumed.add(c);
        continue;
      }
      if (c == 'admin_data_explorer') {
        model.deTable = true;
        model.deAnalysis = true;
        model.deCompliance = true;
        consumed.add(c);
        continue;
      }
      if (c == 'admin_data_explorer_data_table') {
        model.deTable = true;
        consumed.add(c);
        continue;
      }
      if (c == 'admin_data_explorer_analysis') {
        model.deAnalysis = true;
        consumed.add(c);
        continue;
      }
      if (c == 'admin_data_explorer_compliance') {
        model.deCompliance = true;
        consumed.add(c);
        continue;
      }
      final vm = viewerRe.firstMatch(c);
      if (vm != null) {
        final key = vm.group(1)!;
        model.modules.putIfAbsent(key, () => _ModuleAccess()).view = true;
        consumed.add(c);
        continue;
      }
      final mm = managerRe.firstMatch(c);
      if (mm != null) {
        final key = mm.group(1)!;
        model.modules.putIfAbsent(key, () => _ModuleAccess()).manage = true;
        consumed.add(c);
        continue;
      }
      if (c == 'admin_security_responder') {
        model.modules.putIfAbsent('security', () => _ModuleAccess()).manage = true;
        consumed.add(c);
        continue;
      }
    }

    for (final r in adminSys) {
      if (!consumed.contains(r.code)) {
        model.leftover.add(r);
      }
    }

    return model;
  }

  Widget _adminAccessMatrixCard(
    BuildContext context,
    AppLocalizations loc,
    List<MapEntry<String, _ModuleAccess>> rows, {
    required bool editable,
  }) {
    final scheme = Theme.of(context).colorScheme;
    final borderColor = scheme.outlineVariant.withValues(alpha: 0.55);

    return Card(
      margin: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
      child: Table(
        columnWidths: const {
          0: FlexColumnWidth(2.4),
          1: FlexColumnWidth(0.85),
          2: FlexColumnWidth(0.85),
        },
        border: TableBorder(
          top: BorderSide(color: borderColor),
          bottom: BorderSide(color: borderColor),
          horizontalInside: BorderSide(color: borderColor),
        ),
        children: [
          TableRow(
            decoration: BoxDecoration(
              color: scheme.surfaceContainerHighest.withValues(alpha: 0.4),
            ),
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(12, 10, 8, 10),
                child: Text(
                  loc.adminRoleAccessArea,
                  style: Theme.of(context).textTheme.labelLarge?.copyWith(
                        fontWeight: FontWeight.w600,
                      ),
                ),
              ),
              _accessMatrixHeaderCell(context, Icons.visibility_outlined, loc.adminRoleAccessView),
              _accessMatrixHeaderCell(context, Icons.tune_outlined, loc.adminRoleAccessManage),
            ],
          ),
          for (final e in rows)
            TableRow(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(12, 10, 8, 10),
                  child: Text(
                    _adminModuleTitle(e.key),
                    style: Theme.of(context).textTheme.bodyMedium,
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Center(
                    child: editable
                        ? _accessGrantedIconTappable(
                            context,
                            e.value.view,
                            interactive: !e.value.manage,
                            lockedVisual: e.value.manage,
                            onTap: e.value.manage
                                ? null
                                : () => _setMatrixCell(e.key, view: !e.value.view),
                          )
                        : _accessGrantedIcon(
                            context,
                            e.value.view,
                            locked: e.value.manage,
                          ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Center(
                    child: editable
                        ? _accessGrantedIconTappable(
                            context,
                            e.value.manage,
                            interactive: true,
                            onTap: () => _setMatrixCell(e.key, manage: !e.value.manage),
                          )
                        : _accessGrantedIcon(context, e.value.manage),
                  ),
                ),
              ],
            ),
        ],
      ),
    );
  }

  Widget _accessMatrixHeaderCell(
    BuildContext context,
    IconData icon,
    String label,
  ) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 4),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 18, color: context.navyIconColor),
          const SizedBox(height: 4),
          Text(
            label,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
          ),
        ],
      ),
    );
  }

  /// [locked]: View implied by Manage — show tick as non-interactive / disabled (muted).
  Widget _accessGrantedIcon(
    BuildContext context,
    bool granted, {
    bool locked = false,
  }) {
    final scheme = Theme.of(context).colorScheme;
    late final Widget icon;
    if (granted) {
      icon = const Icon(Icons.check_circle, size: 22, color: IOSColors.systemGreen);
    } else {
      icon = Icon(
        Icons.radio_button_unchecked,
        size: 20,
        color: scheme.outline.withValues(alpha: 0.35),
      );
    }
    if (locked) {
      return Opacity(
        opacity: 0.42,
        child: icon,
      );
    }
    return icon;
  }

  /// Same green tick / grey circle as read-only, with optional tap (no Material [Checkbox]).
  Widget _accessGrantedIconTappable(
    BuildContext context,
    bool granted, {
    required bool interactive,
    VoidCallback? onTap,
    bool lockedVisual = false,
  }) {
    final icon = _accessGrantedIcon(context, granted, locked: lockedVisual);
    if (!interactive || onTap == null) {
      return Padding(
        padding: const EdgeInsets.all(4),
        child: icon,
      );
    }
    return Material(
      type: MaterialType.transparency,
      child: InkWell(
        onTap: onTap,
        customBorder: const CircleBorder(),
        child: Padding(
          padding: const EdgeInsets.all(4),
          child: icon,
        ),
      ),
    );
  }

  Widget _dataExplorerAccessCard(
    BuildContext context,
    AppLocalizations loc, {
    required bool dataTable,
    required bool analysis,
    required bool compliance,
    required bool editable,
    ValueChanged<bool>? onDataTable,
    ValueChanged<bool>? onAnalysis,
    ValueChanged<bool>? onCompliance,
  }) {
    return Card(
      margin: EdgeInsets.zero,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 12, 12, 14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.explore_outlined, size: 20, color: context.navyIconColor),
                const SizedBox(width: 8),
                Text(
                  loc.adminRoleDeHeading,
                  style: Theme.of(context).textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.w600,
                      ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: _dataExplorerTabCell(
                    context,
                    loc.adminRoleDeTable,
                    dataTable,
                    editable: editable,
                    onChanged: onDataTable,
                  ),
                ),
                Expanded(
                  child: _dataExplorerTabCell(
                    context,
                    loc.adminRoleDeAnalysis,
                    analysis,
                    editable: editable,
                    onChanged: onAnalysis,
                  ),
                ),
                Expanded(
                  child: _dataExplorerTabCell(
                    context,
                    loc.adminRoleDeCompliance,
                    compliance,
                    editable: editable,
                    onChanged: onCompliance,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _dataExplorerTabCell(
    BuildContext context,
    String label,
    bool granted, {
    required bool editable,
    ValueChanged<bool>? onChanged,
  }) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        editable && onChanged != null
            ? _accessGrantedIconTappable(
                context,
                granted,
                interactive: true,
                onTap: () => onChanged(!granted),
              )
            : _accessGrantedIcon(context, granted),
        const SizedBox(height: 6),
        Text(
          label,
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.labelSmall,
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
        ),
      ],
    );
  }

  /// Matches backoffice RBAC module names where possible.
  String _adminModuleTitle(String key) {
    const titles = <String, String>{
      'users': 'Users',
      'templates': 'Templates',
      'assignments': 'Assignments',
      'countries': 'Countries & organization',
      'indicator_bank': 'Indicator bank',
      'docs': 'Documentation',
      'analytics': 'Analytics',
      'audit': 'Audit trail',
      'security': 'Security',
      'governance': 'Governance',
      'content': 'Content',
      'documents': 'Documents',
      'settings': 'Settings',
      'api': 'API',
      'plugins': 'Plugins',
      'notifications': 'Notifications',
      'translations': 'Translations',
      'ai': 'AI',
    };
    if (titles.containsKey(key)) return titles[key]!;
    return key
        .split('_')
        .map(
          (w) => w.isEmpty ? w : '${w[0].toUpperCase()}${w.length > 1 ? w.substring(1) : ''}',
        )
        .join(' ');
  }

  List<AdminRbacRoleDetail> _sortAdminRolesByName(List<AdminRbacRoleDetail> roles) {
    final copy = List<AdminRbacRoleDetail>.from(roles);
    copy.sort((a, b) {
      final an = (a.name.trim().isNotEmpty ? a.name : a.code).toLowerCase();
      final bn = (b.name.trim().isNotEmpty ? b.name : b.code).toLowerCase();
      return an.compareTo(bn);
    });
    return copy;
  }

  Widget _roleNameChip(BuildContext context, String name, String code) {
    final label = name.trim().isNotEmpty ? name : code;
    final isSys = code == 'system_manager';
    final isAssignment = code.startsWith('assignment_');
    Color? bg;
    Color? labelColor;
    final scheme = Theme.of(context).colorScheme;
    if (isSys) {
      if (Theme.of(context).brightness == Brightness.dark) {
        bg = Color.alphaBlend(
          Colors.black.withValues(alpha: 0.52),
          scheme.surfaceContainerHighest,
        );
        labelColor = Colors.grey.shade100;
      } else {
        bg = Colors.black87;
        labelColor = Colors.white;
      }
    } else if (isAssignment) {
      bg = IOSColors.systemGreen.withValues(alpha: 0.18);
    } else if (code.startsWith('admin_')) {
      if (Theme.of(context).brightness == Brightness.dark) {
        bg = Color.alphaBlend(
          Colors.orange.withValues(alpha: 0.32),
          scheme.surfaceContainerHighest,
        );
        labelColor = Colors.orange.shade200;
      } else {
        bg = Colors.orange.shade100;
        labelColor = Colors.orange.shade900;
      }
    }
    return Chip(
      label: Text(label, maxLines: 2, overflow: TextOverflow.ellipsis),
      visualDensity: VisualDensity.compact,
      backgroundColor: bg,
      labelStyle: labelColor != null
          ? Theme.of(context).textTheme.labelLarge?.copyWith(color: labelColor)
          : null,
    );
  }

  Widget _entityNameChip(
    BuildContext context,
    AppLocalizations loc,
    AdminEntityPermissionRow e,
  ) {
    final scheme = Theme.of(context).colorScheme;
    final raw = e.entityName?.trim();
    final label = raw != null && raw.isNotEmpty ? raw : loc.entityPermissionUnnamed;
    return Chip(
      visualDensity: VisualDensity.compact,
      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 0),
      labelPadding: EdgeInsets.zero,
      side: BorderSide(color: scheme.outlineVariant.withValues(alpha: 0.45)),
      backgroundColor: scheme.surfaceContainerHighest.withValues(alpha: 0.4),
      label: Text(
        label,
        style: Theme.of(context).textTheme.labelMedium,
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
      ),
    );
  }

  Widget _entityListGrouped(
    BuildContext context,
    AppLocalizations loc,
    List<AdminEntityPermissionRow> rows,
  ) {
    if (rows.isEmpty) {
      return Text(
        loc.noEntitiesAssigned,
        style: Theme.of(context).textTheme.bodyMedium?.copyWith(
              color: Theme.of(context).colorScheme.onSurfaceVariant,
            ),
      );
    }

    final byType = <String, List<AdminEntityPermissionRow>>{};
    for (final e in rows) {
      final k = e.entityType.trim().toLowerCase();
      byType.putIfAbsent(k, () => []).add(e);
    }
    final types = byType.keys.toList()..sort();

    return Card(
      margin: EdgeInsets.zero,
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (var i = 0; i < types.length; i++) ...[
            if (i > 0)
              Divider(
                height: 1,
                thickness: 1,
                color: Theme.of(context).dividerColor,
              ),
            ExpansionTile(
              key: PageStorageKey<String>('admin_user_entity_${types[i]}'),
              tilePadding: const EdgeInsets.symmetric(horizontal: 12),
              visualDensity: VisualDensity.compact,
              initiallyExpanded: false,
              title: Text(
                '${_entityTypeSectionTitle(types[i])} (${byType[types[i]]!.length})',
                style: Theme.of(context).textTheme.titleSmall?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
              ),
              childrenPadding: const EdgeInsets.fromLTRB(10, 0, 10, 10),
              children: [
                _entityTypeBody(context, loc, types[i], byType[types[i]]!),
              ],
            ),
          ],
        ],
      ),
    );
  }

  /// Renders chips for one entity type; countries are sub-grouped by [AdminEntityPermissionRow.entityRegion].
  Widget _entityTypeBody(
    BuildContext context,
    AppLocalizations loc,
    String typeKey,
    List<AdminEntityPermissionRow> rows,
  ) {
    if (typeKey.trim().toLowerCase() == 'country') {
      return _countryEntitiesByRegion(context, loc, rows);
    }
    return Align(
      alignment: Alignment.centerLeft,
      child: Wrap(
        spacing: 6,
        runSpacing: 4,
        children: _sortedEntityRows(rows)
            .map((e) => _entityNameChip(context, loc, e))
            .toList(),
      ),
    );
  }

  Widget _countryEntitiesByRegion(
    BuildContext context,
    AppLocalizations loc,
    List<AdminEntityPermissionRow> rows,
  ) {
    final scheme = Theme.of(context).colorScheme;
    final byRegion = <String, List<AdminEntityPermissionRow>>{};
    for (final e in rows) {
      var r = e.entityRegion?.trim();
      if (r == null || r.isEmpty) {
        r = loc.entityRegionOther;
      }
      byRegion.putIfAbsent(r, () => []).add(e);
    }
    final regionKeys = byRegion.keys.toList()
      ..sort((a, b) {
        final other = loc.entityRegionOther;
        if (a == other && b != other) return 1;
        if (b == other && a != other) return -1;
        return a.toLowerCase().compareTo(b.toLowerCase());
      });

    final sectionChildren = <Widget>[];
    var firstRegion = true;
    for (final rk in regionKeys) {
      if (!firstRegion) {
        sectionChildren.add(const SizedBox(height: 12));
      }
      firstRegion = false;
      sectionChildren.add(
        Text(
          '$rk (${byRegion[rk]!.length})',
          style: Theme.of(context).textTheme.labelLarge?.copyWith(
                fontWeight: FontWeight.w700,
                color: scheme.onSurface,
              ),
        ),
      );
      sectionChildren.add(const SizedBox(height: 6));
      sectionChildren.add(
        Align(
          alignment: Alignment.centerLeft,
          child: Wrap(
            spacing: 6,
            runSpacing: 4,
            children: _sortedEntityRows(byRegion[rk]!)
                .map((e) => _entityNameChip(context, loc, e))
                .toList(),
          ),
        ),
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: sectionChildren,
    );
  }

  List<AdminEntityPermissionRow> _sortedEntityRows(List<AdminEntityPermissionRow> rows) {
    final copy = List<AdminEntityPermissionRow>.from(rows);
    copy.sort((a, b) {
      final an = (a.entityName ?? '').toLowerCase();
      final bn = (b.entityName ?? '').toLowerCase();
      final c = an.compareTo(bn);
      if (c != 0) return c;
      return a.entityId.compareTo(b.entityId);
    });
    return copy;
  }

  String _entityTypeSectionTitle(String raw) {
    if (raw.isEmpty) return raw;
    return raw
        .split('_')
        .map(
          (part) => part.isEmpty
              ? part
              : '${part[0].toUpperCase()}${part.length > 1 ? part.substring(1) : ''}',
        )
        .join(' ');
  }
}

class _ModuleAccess {
  bool view = false;
  bool manage = false;
}

class _AdminAccessModel {
  bool systemManager = false;
  bool hasAdminFull = false;
  bool hasAdminCore = false;
  bool deTable = false;
  bool deAnalysis = false;
  bool deCompliance = false;
  final Map<String, _ModuleAccess> modules = {};
  final List<AdminRbacRoleDetail> leftover = [];

  bool get hasAnyDataExplorer => deTable || deAnalysis || deCompliance;
}
