import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../l10n/app_localizations.dart';
import '../providers/shared/backend_reachability_notifier.dart';
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

/// Banner widget to display offline status at top of screen
class OfflineBanner extends StatelessWidget {
  const OfflineBanner({super.key});

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Consumer2<OfflineProvider, BackendReachabilityNotifier>(
      builder: (context, offlineProvider, reachNotifier, _) {
        final showOffline = !offlineProvider.isOnline;
        final showServer = reachNotifier.showServerUnreachableBanner;
        if (!showOffline && !showServer) {
          return const SizedBox.shrink();
        }

        final l10n = AppLocalizations.of(context);
        return Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (showOffline)
              Container(
                width: double.infinity,
                padding:
                    const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                color: scheme.error,
                child: Row(
                  children: [
                    Icon(Icons.wifi_off, color: scheme.onError, size: 20),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            l10n?.offlineNoInternet ?? 'No Internet Connection',
                            style: TextStyle(
                              color: scheme.onError,
                              fontSize: 14,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          if (offlineProvider.queuedRequestsCount > 0) ...[
                            const SizedBox(height: 4),
                            Text(
                              l10n?.offlineRequestsWillSync(
                                      offlineProvider.queuedRequestsCount) ??
                                  '${offlineProvider.queuedRequestsCount} request(s) will be synced when online',
                              style: TextStyle(
                                color: scheme.onError.withValues(alpha: 0.92),
                                fontSize: 12,
                              ),
                            ),
                          ],
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            if (showServer)
              Container(
                width: double.infinity,
                padding:
                    const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                color: scheme.secondaryContainer,
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(Icons.cloud_off,
                        color: scheme.onSecondaryContainer, size: 22),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Text(
                            l10n?.backendUnreachableTitle ??
                                'Cannot reach server',
                            style: TextStyle(
                              color: scheme.onSecondaryContainer,
                              fontSize: 14,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            l10n?.backendUnreachableSubtitle ??
                                'Showing saved data where available. '
                                'Actions may not sync until the server is available again.',
                            style: TextStyle(
                              color: scheme.onSecondaryContainer
                                  .withValues(alpha: 0.92),
                              fontSize: 12,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
          ],
        );
      },
    );
  }
}
