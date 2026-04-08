import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import '../../l10n/app_localizations.dart';
import '../../models/admin/country_access_request_item.dart';
import '../../models/shared/user.dart';
import '../../providers/admin/access_requests_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/shared/elevated_list_card.dart';

ButtonStyle _compactFilledButtonStyle() => FilledButton.styleFrom(
      visualDensity: VisualDensity.compact,
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
      minimumSize: const Size(0, 34),
      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
    );

ButtonStyle _compactTextButtonStyle() => TextButton.styleFrom(
      visualDensity: VisualDensity.compact,
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      minimumSize: const Size(0, 32),
      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
    );

/// Shared label typography for Approve / Reject on request cards (same size & weight).
TextStyle _accessRequestActionLabelStyle(ThemeData theme) {
  return TextStyle(
    fontSize: 14,
    fontWeight: FontWeight.w600,
    letterSpacing: 0.15,
    height: 1.2,
    fontFamily: theme.textTheme.labelLarge?.fontFamily,
  );
}

ButtonStyle _accessRequestApproveStyle(ThemeData theme) {
  final cs = theme.colorScheme;
  return FilledButton.styleFrom(
    visualDensity: VisualDensity.compact,
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
    minimumSize: const Size(0, 38),
    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
    foregroundColor: cs.onPrimary,
    backgroundColor: cs.primary,
    textStyle: _accessRequestActionLabelStyle(theme).copyWith(color: cs.onPrimary),
    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
  );
}

ButtonStyle _accessRequestRejectStyle(ThemeData theme) {
  final cs = theme.colorScheme;
  return OutlinedButton.styleFrom(
    visualDensity: VisualDensity.compact,
    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
    minimumSize: const Size(0, 38),
    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
    foregroundColor: cs.primary,
    textStyle: _accessRequestActionLabelStyle(theme).copyWith(color: cs.primary),
    side: BorderSide(color: cs.primary, width: 1),
    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
  );
}

({Color background, Color foreground}) _statusChipColors(
  ThemeData theme,
  String status,
) {
  final cs = theme.colorScheme;
  switch (status) {
    case 'approved':
      return (
        background: cs.tertiaryContainer.withValues(alpha: 0.85),
        foreground: cs.onTertiaryContainer,
      );
    case 'rejected':
      return (
        background: cs.errorContainer.withValues(alpha: 0.9),
        foreground: cs.onErrorContainer,
      );
    default:
      return (
        background: cs.surfaceContainerHigh,
        foreground: cs.onSurfaceVariant,
      );
  }
}

/// Country access requests (aligned with web `/admin/access-requests`).
class AccessRequestsScreen extends StatefulWidget {
  const AccessRequestsScreen({super.key});

  @override
  State<AccessRequestsScreen> createState() => _AccessRequestsScreenState();
}

class _AccessRequestsScreenState extends State<AccessRequestsScreen> {
  bool _isAdmin(User? user) => user?.isAdmin ?? false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      if (_isAdmin(context.read<AuthProvider>().user)) {
        context.read<AccessRequestsProvider>().load();
      }
    });
  }

  String _formatWhen(BuildContext context, String? iso) {
    if (iso == null || iso.isEmpty) return '—';
    final normalized = iso.endsWith('Z') ? iso : '${iso}Z';
    final dt = DateTime.tryParse(normalized) ?? DateTime.tryParse(iso);
    if (dt == null) return iso;
    final locale = Localizations.localeOf(context).toString();
    return DateFormat.yMMMd(locale).add_jm().format(dt.toLocal());
  }

  String _statusLabel(AppLocalizations loc, String status) {
    switch (status) {
      case 'pending':
        return loc.accessRequestsStatusPending;
      case 'approved':
        return loc.accessRequestsStatusApproved;
      case 'rejected':
        return loc.accessRequestsStatusRejected;
      default:
        return status;
    }
  }

  Future<void> _confirmReject(
    BuildContext context,
    AccessRequestsProvider provider,
    CountryAccessRequestItem item,
    AppLocalizations loc,
  ) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: Text(loc.accessRequestsReject),
        content: Text(loc.accessRequestsRejectConfirm),
        actions: [
          TextButton(
            style: _compactTextButtonStyle(),
            onPressed: () => Navigator.of(ctx).pop(false),
            child: Text(loc.cancel),
          ),
          FilledButton(
            style: _compactFilledButtonStyle(),
            onPressed: () => Navigator.of(ctx).pop(true),
            child: Text(loc.accessRequestsReject),
          ),
        ],
      ),
    );
    if (ok != true || !context.mounted) return;
    final success = await provider.reject(item.id);
    if (!context.mounted) return;
    if (!success && provider.error != null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(provider.error!)),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    final auth = context.watch<AuthProvider>();
    final user = auth.user;

    if (!_isAdmin(user)) {
      final t = Theme.of(context);
      return Scaffold(
        backgroundColor: t.colorScheme.surfaceContainerLow,
        appBar: AppAppBar(title: loc.accessRequestsTitle),
        body: Center(
          child: Padding(
            padding: const EdgeInsets.all(32),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  Icons.lock_outline_rounded,
                  size: 48,
                  color: t.colorScheme.outline,
                ),
                const SizedBox(height: 16),
                Text(
                  loc.accessDenied,
                  textAlign: TextAlign.center,
                  style: t.textTheme.bodyLarge?.copyWith(
                    color: t.colorScheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ),
        ),
        bottomNavigationBar: const AppBottomNavigationBar(currentIndex: -1),
      );
    }

    final provider = context.watch<AccessRequestsProvider>();
    final theme = Theme.of(context);
    final chatbot = user?.chatbotEnabled ?? false;

    return Scaffold(
      backgroundColor: theme.colorScheme.surfaceContainerLow,
      appBar: AppAppBar(
        title: loc.accessRequestsTitle,
      ),
      bottomNavigationBar: AppBottomNavigationBar(
        currentIndex: AppBottomNavigationBar.adminTabNavIndex(
          chatbotEnabled: chatbot,
        ),
        chatbotEnabled: chatbot,
      ),
      body: RefreshIndicator(
        onRefresh: () => context.read<AccessRequestsProvider>().load(),
        child: provider.isLoading && provider.pending.isEmpty
            ? ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                padding: const EdgeInsets.symmetric(vertical: 48),
                children: [
                  Center(
                    child: SizedBox(
                      width: 36,
                      height: 36,
                      child: CircularProgressIndicator(
                        strokeWidth: 3,
                        color: theme.colorScheme.primary,
                      ),
                    ),
                  ),
                ],
              )
            : _buildBody(context, provider, loc, theme),
      ),
    );
  }

  Widget _buildBody(
    BuildContext context,
    AccessRequestsProvider provider,
    AppLocalizations loc,
    ThemeData theme,
  ) {
    if (provider.error != null &&
        provider.pending.isEmpty &&
        provider.processed.isEmpty) {
      final cs = theme.colorScheme;
      return ListView(
        physics: const AlwaysScrollableScrollPhysics(),
        padding: const EdgeInsets.all(24),
        children: [
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              color: cs.errorContainer.withValues(alpha: 0.4),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: cs.error.withValues(alpha: 0.28),
              ),
            ),
            child: Column(
              children: [
                Icon(Icons.cloud_off_outlined, size: 40, color: cs.error),
                const SizedBox(height: 12),
                Text(
                  provider.error!,
                  textAlign: TextAlign.center,
                  style: theme.textTheme.bodyLarge?.copyWith(
                    color: cs.onSurface,
                  ),
                ),
                const SizedBox(height: 20),
                FilledButton(
                  style: _compactFilledButtonStyle(),
                  onPressed: () => provider.load(),
                  child: Text(loc.retry),
                ),
              ],
            ),
          ),
        ],
      );
    }

    // ListView + AlwaysScrollableScrollPhysics (not CustomScrollView) ensures
    // RefreshIndicator reliably sizes and paints the scrollable on all devices.
    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 32),
      children: [
        _SectionHeader(
          icon: Icons.pending_actions_rounded,
          title: loc.accessRequestsPending,
          count: provider.pending.length,
          theme: theme,
        ),
        if (provider.pending.isEmpty)
          _EmptySectionHint(theme: theme, message: loc.accessRequestsEmpty)
        else
          ...provider.pending.map(
            (item) => _RequestCard(
              item: item,
              isPending: true,
              statusLabel: _statusLabel(loc, item.status),
              whenLabel: _formatWhen(context, item.createdAt),
              onApprove: provider.actionInFlight
                  ? null
                  : () async {
                      final ok = await provider.approve(item.id);
                      if (!context.mounted) return;
                      if (!ok && provider.error != null) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(content: Text(provider.error!)),
                        );
                      }
                    },
              onReject: provider.actionInFlight
                  ? null
                  : () => _confirmReject(context, provider, item, loc),
              loc: loc,
              theme: theme,
            ),
          ),
        const SizedBox(height: 16),
        _SectionHeader(
          icon: Icons.fact_check_outlined,
          title: loc.accessRequestsProcessed,
          count: provider.processed.length,
          theme: theme,
        ),
        if (provider.processed.isEmpty)
          _EmptySectionHint(theme: theme, message: loc.accessRequestsEmpty)
        else
          ...provider.processed.map(
            (item) => _RequestCard(
              item: item,
              isPending: false,
              statusLabel: _statusLabel(loc, item.status),
              whenLabel: _formatWhen(context, item.processedAt ?? item.createdAt),
              onApprove: null,
              onReject: null,
              loc: loc,
              theme: theme,
            ),
          ),
      ],
    );
  }
}

class _SectionHeader extends StatelessWidget {
  final IconData icon;
  final String title;
  final int count;
  final ThemeData theme;

  const _SectionHeader({
    required this.icon,
    required this.title,
    required this.count,
    required this.theme,
  });

  @override
  Widget build(BuildContext context) {
    final cs = theme.colorScheme;
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          Icon(icon, size: 22, color: cs.primary),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              title,
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w600,
                letterSpacing: -0.2,
              ),
            ),
          ),
          if (count > 0)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: cs.primaryContainer.withValues(alpha: 0.55),
                borderRadius: BorderRadius.circular(20),
              ),
              child: Text(
                '$count',
                style: theme.textTheme.labelMedium?.copyWith(
                  fontWeight: FontWeight.w700,
                  color: cs.onPrimaryContainer,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _EmptySectionHint extends StatelessWidget {
  final ThemeData theme;
  final String message;

  const _EmptySectionHint({
    required this.theme,
    required this.message,
  });

  @override
  Widget build(BuildContext context) {
    final cs = theme.colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 18),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(
            Icons.inbox_outlined,
            size: 22,
            color: cs.outline,
          ),
          const SizedBox(width: 10),
          Flexible(
            child: Text(
              message,
              textAlign: TextAlign.center,
              style: theme.textTheme.bodyMedium?.copyWith(
                color: cs.onSurfaceVariant,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _RequestCard extends StatelessWidget {
  final CountryAccessRequestItem item;
  final bool isPending;
  final String statusLabel;
  final String whenLabel;
  final VoidCallback? onApprove;
  final VoidCallback? onReject;
  final AppLocalizations loc;
  final ThemeData theme;

  const _RequestCard({
    required this.item,
    required this.isPending,
    required this.statusLabel,
    required this.whenLabel,
    required this.onApprove,
    required this.onReject,
    required this.loc,
    required this.theme,
  });

  @override
  Widget build(BuildContext context) {
    final cs = theme.colorScheme;
    final countryLine = item.country.name != null && item.country.name!.isNotEmpty
        ? item.country.name!
        : (item.country.iso2 ?? '—');
    final chipColors = _statusChipColors(theme, item.status);

    return ElevatedListCard(
      marginBottom: 12,
      padding: const EdgeInsets.fromLTRB(16, 14, 16, 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.only(top: 2),
                  child: Icon(
                    Icons.person_outline_rounded,
                    size: 20,
                    color: cs.primary,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        item.user.email ?? item.user.name ?? '—',
                        style: theme.textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w600,
                          height: 1.25,
                          color: cs.onSurface,
                        ),
                      ),
                      if (item.user.name != null &&
                          item.user.name!.isNotEmpty &&
                          item.user.email != null &&
                          item.user.email!.isNotEmpty &&
                          item.user.name != item.user.email) ...[
                        const SizedBox(height: 2),
                        Text(
                          item.user.name!,
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: cs.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                if (!isPending)
                  Container(
                    padding: const EdgeInsets.symmetric(
                      horizontal: 8,
                      vertical: 4,
                    ),
                    decoration: BoxDecoration(
                      color: chipColors.background,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(
                      statusLabel,
                      style: theme.textTheme.labelSmall?.copyWith(
                        color: chipColors.foreground,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 12),
            _MetaRow(
              icon: Icons.public_outlined,
              text: '${loc.accessRequestsCountry}: $countryLine',
              theme: theme,
            ),
            if (item.requestMessage != null &&
                item.requestMessage!.trim().isNotEmpty) ...[
              const SizedBox(height: 10),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.fromLTRB(10, 8, 10, 8),
                decoration: BoxDecoration(
                  color: cs.surfaceContainerHigh.withValues(alpha: 0.9),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      loc.accessRequestsMessage,
                      style: theme.textTheme.labelSmall?.copyWith(
                        color: cs.onSurfaceVariant,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      item.requestMessage!.trim(),
                      style: theme.textTheme.bodySmall?.copyWith(
                        height: 1.35,
                      ),
                    ),
                  ],
                ),
              ),
            ],
            const SizedBox(height: 10),
            _MetaRow(
              icon: Icons.schedule_outlined,
              text:
                  '${isPending ? loc.accessRequestsRequestedAt : loc.accessRequestsProcessedAt}: $whenLabel',
              theme: theme,
              dense: true,
            ),
            if (!isPending &&
                item.processedBy != null &&
                (item.processedBy!.email != null ||
                    item.processedBy!.name != null)) ...[
              const SizedBox(height: 6),
              _MetaRow(
                icon: Icons.manage_accounts_outlined,
                text:
                    '${loc.accessRequestsBy} ${item.processedBy!.name ?? item.processedBy!.email}',
                theme: theme,
                dense: true,
              ),
            ],
            // Row + Expanded: side-by-side, bounded height (avoid Wrap/Column stretch issues).
            if (isPending && (onApprove != null || onReject != null)) ...[
              const SizedBox(height: 14),
              Divider(
                height: 1,
                color: cs.outlineVariant.withValues(alpha: 0.5),
              ),
              const SizedBox(height: 12),
              Row(
                crossAxisAlignment: CrossAxisAlignment.center,
                children: [
                  if (onApprove != null)
                    Expanded(
                      child: FilledButton(
                        style: _accessRequestApproveStyle(theme),
                        onPressed: onApprove,
                        child: Text(loc.accessRequestsApprove),
                      ),
                    ),
                  if (onApprove != null && onReject != null)
                    const SizedBox(width: 10),
                  if (onReject != null)
                    Expanded(
                      child: OutlinedButton(
                        style: _accessRequestRejectStyle(theme),
                        onPressed: onReject,
                        child: Text(loc.accessRequestsReject),
                      ),
                    ),
                ],
              ),
            ],
        ],
      ),
    );
  }
}

class _MetaRow extends StatelessWidget {
  final IconData icon;
  final String text;
  final ThemeData theme;
  final bool dense;

  const _MetaRow({
    required this.icon,
    required this.text,
    required this.theme,
    this.dense = false,
  });

  @override
  Widget build(BuildContext context) {
    final cs = theme.colorScheme;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(
          icon,
          size: dense ? 16 : 18,
          color: cs.outline,
        ),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            text,
            style: (dense ? theme.textTheme.bodySmall : theme.textTheme.bodyMedium)
                ?.copyWith(
              color: dense ? cs.onSurfaceVariant : cs.onSurface,
              height: 1.35,
            ),
          ),
        ),
      ],
    );
  }
}
