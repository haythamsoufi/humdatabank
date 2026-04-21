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

/// Banner widget to display offline / server status at the top of the screen.
///
/// When [floatOverContent] is true (recommended for tab shell and login), the
/// banner is laid out in a [Stack] so it does not push the body down; it uses
/// a compact strip and softer colours instead of a full error block.
class OfflineBanner extends StatelessWidget {
  /// If true, wrap in [SafeArea] (top) and add a light shadow — for [Stack] overlay.
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
        final column = Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (showOffline)
              _OfflineBannerStrip(
                floatOverContent: floatOverContent,
                background: context.offlineDisconnectedInlineBackground,
                foreground: context.offlineDisconnectedInlineForeground,
                icon: Icons.wifi_off,
                title: l10n?.offlineNoInternet ?? 'No Internet Connection',
                subtitle: offlineProvider.queuedRequestsCount > 0
                    ? (l10n?.offlineRequestsWillSync(
                            offlineProvider.queuedRequestsCount) ??
                        '${offlineProvider.queuedRequestsCount} request(s) will sync when online')
                    : null,
              ),
            if (showServer)
              _OfflineBannerStrip(
                floatOverContent: floatOverContent,
                background: scheme.secondaryContainer,
                foreground: scheme.onSecondaryContainer,
                icon: Icons.cloud_off,
                title: l10n?.backendUnreachableTitle ?? 'Cannot reach server',
                subtitle: l10n?.backendUnreachableSubtitle ??
                    'Showing saved data where available. '
                        'Actions may not sync until the server is available again.',
              ),
          ],
        );

        if (!floatOverContent) {
          return column;
        }

        final closeTooltip = l10n?.close ?? 'Close';
        final dismissIconColor = scheme.onSurface.withValues(alpha: 0.65);

        return SafeArea(
          bottom: false,
          left: false,
          right: false,
          minimum: EdgeInsets.zero,
          child: Material(
            elevation: 2,
            shadowColor: Colors.black26,
            color: Colors.transparent,
            child: Stack(
              clipBehavior: Clip.none,
              children: [
                Padding(
                  padding: const EdgeInsets.only(right: 36),
                  child: column,
                ),
                Positioned(
                  top: 0,
                  right: 0,
                  child: IconButton(
                    visualDensity: VisualDensity.compact,
                    padding: const EdgeInsets.all(4),
                    constraints: const BoxConstraints(
                      minWidth: 36,
                      minHeight: 36,
                    ),
                    tooltip: closeTooltip,
                    onPressed: () => dismissal.dismissForSession(),
                    icon: Icon(Icons.close, size: 20, color: dismissIconColor),
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

class _OfflineBannerStrip extends StatelessWidget {
  final bool floatOverContent;
  final Color background;
  final Color foreground;
  final IconData icon;
  final String title;
  final String? subtitle;

  const _OfflineBannerStrip({
    required this.floatOverContent,
    required this.background,
    required this.foreground,
    required this.icon,
    required this.title,
    this.subtitle,
  });

  @override
  Widget build(BuildContext context) {
    final horizontal = floatOverContent ? 12.0 : 16.0;
    final vertical = floatOverContent ? 6.0 : 10.0;

    if (!floatOverContent) {
      return Container(
        width: double.infinity,
        padding: EdgeInsets.symmetric(horizontal: horizontal, vertical: vertical),
        color: background,
        child: _stripRow(foreground),
      );
    }

    return Container(
      width: double.infinity,
      padding: EdgeInsets.symmetric(horizontal: horizontal, vertical: vertical),
      decoration: BoxDecoration(
        color: background,
        border: Border(
          bottom: BorderSide(
            color: foreground.withValues(alpha: 0.12),
          ),
        ),
      ),
      child: _stripRow(foreground),
    );
  }

  Widget _stripRow(Color foreground) {
    final combined = (subtitle == null || subtitle!.isEmpty)
        ? title
        : '$title · $subtitle';
    final maxLines = floatOverContent ? 1 : 3;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Icon(icon, color: foreground, size: 18),
        const SizedBox(width: 8),
        Expanded(
          child: Text(
            combined,
            maxLines: maxLines,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: foreground,
              fontSize: 13,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
      ],
    );
  }
}
