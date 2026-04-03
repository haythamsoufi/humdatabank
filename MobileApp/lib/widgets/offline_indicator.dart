import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../providers/shared/offline_provider.dart';

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
        if (offlineProvider.isOnline) {
          // Show online status if there are queued requests
          if (offlineProvider.queuedRequestsCount > 0) {
            return Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              color: Colors.orange.shade100,
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.sync, size: 16, color: Colors.orange.shade900),
                  const SizedBox(width: 8),
                  Text(
                    '${offlineProvider.queuedRequestsCount} pending',
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.orange.shade900,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                  if (showSyncButton && !offlineProvider.isSyncing) ...[
                    const SizedBox(width: 8),
                    InkWell(
                      onTap: () => offlineProvider.manualSync(),
                      child: Text(
                        'Sync',
                        style: TextStyle(
                          fontSize: 12,
                          color: Colors.orange.shade900,
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
                          Colors.orange.shade900,
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
              color: Colors.green.shade50,
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.check_circle,
                      size: 16, color: Colors.green.shade700),
                  const SizedBox(width: 8),
                  Text(
                    'Synced ${offlineProvider.lastSyncedFormatted}',
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.green.shade700,
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
            color: Colors.red.shade100,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.offline_bolt, size: 16, color: Colors.red.shade900),
                const SizedBox(width: 8),
                Text(
                  'Offline',
                  style: TextStyle(
                    fontSize: 12,
                    color: Colors.red.shade900,
                    fontWeight: FontWeight.w500,
                  ),
                ),
                if (offlineProvider.queuedRequestsCount > 0) ...[
                  const SizedBox(width: 8),
                  Text(
                    '(${offlineProvider.queuedRequestsCount} queued)',
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.red.shade900,
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
    return Consumer<OfflineProvider>(
      builder: (context, offlineProvider, child) {
        if (offlineProvider.isOnline) {
          return const SizedBox.shrink();
        }

        return Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          color: Colors.red.shade600,
          child: Row(
            children: [
              const Icon(Icons.wifi_off, color: Colors.white, size: 20),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Text(
                      'No Internet Connection',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 14,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    if (offlineProvider.queuedRequestsCount > 0) ...[
                      const SizedBox(height: 4),
                      Text(
                        '${offlineProvider.queuedRequestsCount} request(s) will be synced when online',
                        style: const TextStyle(
                          color: Colors.white,
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
