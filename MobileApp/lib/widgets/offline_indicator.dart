import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../l10n/app_localizations.dart';
import '../providers/shared/backend_reachability_notifier.dart';
import '../providers/shared/offline_banner_dismissal_provider.dart';
import '../providers/shared/offline_provider.dart';
import '../utils/theme_extensions.dart';

/// Widget to display offline status indicator
class OfflineIndicator extends StatelessWidget {
  final bool showSyncButton;

  const OfflineIndicator({
    super.key,
    this.showSyncButton = true,
  });

  @override
  Widget build(BuildContext context) {
    return Consumer<OfflineProvider>(
      builder: (context, offlineProvider, child) {
        final l10n = AppLocalizations.of(context);
        if (offlineProvider.isOnline) {
          // Show online status if there are queued requests
          if (offlineProvider.queuedRequestsCount > 0) {
            return Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              color: context.offlineQueuedBackground,
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.sync,
                      size: 16, color: context.offlineQueuedForeground),
                  const SizedBox(width: 8),
                  Text(
                    l10n?.offlinePendingCount(offlineProvider.queuedRequestsCount) ??
                        '${offlineProvider.queuedRequestsCount} pending',
                    style: TextStyle(
                      fontSize: 12,
                      color: context.offlineQueuedForeground,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  if (showSyncButton && !offlineProvider.isSyncing) ...[
                    const SizedBox(width: 8),
                    InkWell(
                      onTap: () => offlineProvider.manualSync(),
                      child: Text(
                        l10n?.offlineSync ?? 'Sync',
                        style: TextStyle(
                          fontSize: 12,
                          color: context.offlineQueuedForeground,
                          fontWeight: FontWeight.bold,
                          decoration: TextDecoration.underline,
                        ),
                      ),
                    ),
                  ],
                  if (offlineProvider.isSyncing) ...[
                    const SizedBox(width: 8),
                    SizedBox(
                      width: 12,
                      height: 12,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        valueColor: AlwaysStoppedAnimation<Color>(
                          context.offlineQueuedForeground,
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            );
          }

          // Show last synced time if available
          if (offlineProvider.lastSyncedFormatted != null) {
            return Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              color: context.offlineSyncedBackground,
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.check_circle,
                      size: 16, color: context.offlineSyncedForeground),
                  const SizedBox(width: 8),
                  Text(
                    l10n?.offlineSyncedTime(offlineProvider.lastSyncedFormatted!) ??
                        'Synced ${offlineProvider.lastSyncedFormatted}',
                    style: TextStyle(
                      fontSize: 12,
                      color: context.offlineSyncedForeground,
                    ),
                  ),
                ],
              ),
            );
          }

          return const SizedBox.shrink();
        } else {
          // Show offline status
          return Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            color: context.offlineDisconnectedInlineBackground,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.offline_bolt,
                    size: 16, color: context.offlineDisconnectedInlineForeground),
                const SizedBox(width: 8),
                Text(
                  l10n?.offlineStatus ?? 'Offline',
                  style: TextStyle(
                    fontSize: 12,
                    color: context.offlineDisconnectedInlineForeground,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                if (offlineProvider.queuedRequestsCount > 0) ...[
                  const SizedBox(width: 8),
                  Text(
                    l10n?.offlineQueuedCount(offlineProvider.queuedRequestsCount) ??
                        '(${offlineProvider.queuedRequestsCount} queued)',
                    style: TextStyle(
                      fontSize: 12,
                      color: context.offlineDisconnectedInlineForeground,
                    ),
                  ),
                ],
              ],
            ),
          );
        }
      },
    );
  }
}

/// Banner widget to display offline / server status above the bottom nav.
///
/// When [floatOverContent] is true (tab shell and login), the host should anchor
/// this widget to the bottom of a [Stack] body so it sits above [Scaffold.bottomNavigationBar].
class OfflineBanner extends StatelessWidget {
  /// If true, pad for safe areas and draw as a compact chip above the bottom bar.
  final bool floatOverContent;

  const OfflineBanner({super.key, this.floatOverContent = true});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Consumer3<OfflineProvider, BackendReachabilityNotifier,
        OfflineBannerDismissalProvider>(
      builder: (context, offlineProvider, reachNotifier, dismissal, _) {
        if (dismissal.isDismissedForSession) {
          return const SizedBox.shrink();
        }

        final showOffline = !offlineProvider.isOnline;
        final showServer = reachNotifier.showServerUnreachableBanner;
        if (!showOffline && !showServer) {
          return const SizedBox.shrink();
        }

        final l10n = AppLocalizations.of(context);
        final closeTooltip = l10n?.close ?? 'Close';
        void onDismiss() => dismissal.dismissForSession();

        final strips = <Widget>[];
        if (showOffline) {
          strips.add(
            _OfflineBannerStrip(
              floatOverContent: floatOverContent,
              background: context.offlineDisconnectedInlineBackground,
              foreground: context.offlineDisconnectedInlineForeground,
              icon: Icons.wifi_off_rounded,
              title: l10n?.offlineNoInternet ?? 'No Internet Connection',
              subtitle: null,
              onDismiss: floatOverContent ? onDismiss : null,
              dismissTooltip: closeTooltip,
            ),
          );
        }
        if (showServer) {
          strips.add(
            _OfflineBannerStrip(
              floatOverContent: floatOverContent,
              background: scheme.secondaryContainer,
              foreground: scheme.onSecondaryContainer,
              icon: Icons.cloud_off_rounded,
              title: l10n?.backendUnreachableTitle ?? 'Cannot reach server',
              subtitle: floatOverContent
                  ? null
                  : (l10n?.backendUnreachableSubtitle ??
                      'Showing saved data where available. '
                          'Actions may not sync until the server is available again.'),
              onDismiss: floatOverContent && !showOffline ? onDismiss : null,
              dismissTooltip: closeTooltip,
            ),
          );
        }

        final column = Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            for (var i = 0; i < strips.length; i++) ...[
              if (i > 0 && floatOverContent) const SizedBox(height: 6),
              strips[i],
            ],
          ],
        );

        if (!floatOverContent) {
          return column;
        }

        return SafeArea(
          top: false,
          bottom: true,
          left: false,
          right: false,
          minimum: EdgeInsets.zero,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 6),
            child: column,
          ),
        );
      },
    );
  }
}

class _OfflineBannerStrip extends StatelessWidget {
  final bool floatOverContent;
  final Color background;
  final Color foreground;
  final IconData icon;
  final String title;
  final String? subtitle;
  final VoidCallback? onDismiss;
  final String dismissTooltip;

  const _OfflineBannerStrip({
    required this.floatOverContent,
    required this.background,
    required this.foreground,
    required this.icon,
    required this.title,
    this.subtitle,
    this.onDismiss,
    this.dismissTooltip = 'Close',
  });

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final horizontal = floatOverContent ? 12.0 : 16.0;
    final vertical = floatOverContent ? 8.0 : 10.0;

    if (!floatOverContent) {
      return Container(
        width: double.infinity,
        padding: EdgeInsets.symmetric(horizontal: horizontal, vertical: vertical),
        color: background,
        child: _messageRow(context, includeDismiss: false),
      );
    }

    return DecoratedBox(
      decoration: BoxDecoration(
        color: background,
        borderRadius: const BorderRadius.vertical(
          top: Radius.circular(12),
        ),
        border: Border.all(color: scheme.outline),
      ),
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: horizontal, vertical: vertical),
        child: _messageRow(context, includeDismiss: onDismiss != null),
      ),
    );
  }

  Widget _messageRow(
    BuildContext context, {
    required bool includeDismiss,
  }) {
    final combined = (subtitle == null || subtitle!.isEmpty)
        ? title
        : '$title · $subtitle';
    final maxLines = floatOverContent ? 1 : 3;
    final textStyle = Theme.of(context).textTheme.labelLarge?.copyWith(
          color: foreground,
          fontWeight: FontWeight.w500,
          height: 1.2,
          letterSpacing: -0.1,
        ) ??
        TextStyle(
          color: foreground,
          fontSize: 13,
          fontWeight: FontWeight.w500,
          height: 1.2,
        );

    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Icon(icon, color: foreground, size: 18),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            combined,
            maxLines: maxLines,
            overflow: TextOverflow.ellipsis,
            style: textStyle,
          ),
        ),
        if (includeDismiss && onDismiss != null) ...[
          const SizedBox(width: 4),
          IconButton(
            onPressed: onDismiss,
            tooltip: dismissTooltip,
            style: IconButton.styleFrom(
              foregroundColor: foreground,
              visualDensity: VisualDensity.compact,
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
              minimumSize: const Size(32, 32),
              padding: EdgeInsets.zero,
            ),
            icon: Icon(Icons.close_rounded, size: 20, color: foreground),
          ),
        ],
      ],
    );
  }
}
