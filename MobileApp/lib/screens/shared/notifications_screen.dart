import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../providers/shared/notification_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../services/error_handler.dart';
import '../../utils/debug_logger.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/app_fade_in_up.dart';
import '../../widgets/fa_icon_suffix.dart';
import '../../widgets/profile_leading_avatar.dart';
import '../../models/shared/notification.dart' as model;
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../config/routes.dart';
import '../../config/app_config.dart';
import '../../utils/url_helper.dart';
import 'package:intl/intl.dart';
import 'notification_preferences_screen.dart';
import '../../l10n/app_localizations.dart';

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({super.key});

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  bool _isMarkingAllAsRead = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      Provider.of<NotificationProvider>(context, listen: false)
          .loadNotifications();
    });
  }

  @override
  Widget build(BuildContext context) {
    // Consumer builders shadow `context`; keep State's context for post-async UI.
    final stateContext = context;
    return Consumer<AuthProvider>(
      builder: (context, authProvider, child) {
        final localizations = AppLocalizations.of(context)!;
        final theme = Theme.of(context);

        return Scaffold(
          backgroundColor: theme.scaffoldBackgroundColor,
          appBar: AppAppBar(
            title: localizations.notifications,
            actions: [
              Consumer<NotificationProvider>(
                builder: (context, provider, child) {
                  final unreadIds = provider.notifications
                      .where((n) => !n.isRead)
                      .map((n) => n.id)
                      .toList();

                  if (unreadIds.isEmpty) {
                    return const SizedBox.shrink();
                  }

                  return Semantics(
                    label: localizations.markAllRead,
                    button: true,
                    enabled: !_isMarkingAllAsRead,
                    child: IconButton(
                      icon: _isMarkingAllAsRead
                          ? SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                valueColor: AlwaysStoppedAnimation<Color>(
                                  context.isDarkTheme
                                      ? const Color(AppConstants
                                          .themeSwitchCheckboxActiveDark)
                                      : Theme.of(context).colorScheme.primary,
                                ),
                              ),
                            )
                          : Icon(
                              Icons.done_all,
                              color:
                                  context.isDarkTheme
                                      ? const Color(AppConstants
                                          .themeSwitchCheckboxActiveDark)
                                      : Theme.of(context).colorScheme.primary,
                            ),
                      onPressed: _isMarkingAllAsRead
                          ? null
                          : () async {
                            // Show confirmation dialog
                            final confirmed = await showDialog<bool>(
                              context: context,
                              builder: (BuildContext dialogContext) {
                                return AlertDialog(
                                  title: Text(localizations.markAllRead),
                                  content: Text(
                                    'Are you sure you want to mark all ${unreadIds.length} notification${unreadIds.length == 1 ? '' : 's'} as read?',
                                  ),
                                  actions: [
                                    TextButton(
                                      onPressed: () {
                                        Navigator.of(dialogContext).pop(false);
                                      },
                                      child: Text(
                                        localizations.cancel,
                                        style: TextStyle(
                                          color: Theme.of(context)
                                              .textTheme
                                              .bodyLarge
                                              ?.color,
                                        ),
                                      ),
                                    ),
                                    Semantics(
                                      label: localizations.markAllRead,
                                      button: true,
                                      child: FilledButton(
                                        onPressed: () {
                                          Navigator.of(dialogContext).pop(true);
                                        },
                                        child: Text(localizations.markAllRead),
                                      ),
                                    ),
                                  ],
                                );
                              },
                            );

                            if (confirmed != true || !stateContext.mounted) {
                              return;
                            }

                            setState(() {
                              _isMarkingAllAsRead = true;
                            });

                            try {
                              final success =
                                  await provider.markAsRead(unreadIds);

                              if (!stateContext.mounted) {
                                return;
                              }
                              if (success) {
                                // Refresh notifications to ensure UI is in sync
                                await provider.loadNotifications();

                                if (!stateContext.mounted) {
                                  return;
                                }
                                ScaffoldMessenger.of(stateContext).showSnackBar(
                                  SnackBar(
                                    content: Text(localizations
                                        .allNotificationsMarkedAsRead),
                                    duration: const Duration(seconds: 2),
                                    backgroundColor:
                                        Theme.of(stateContext)
                                            .colorScheme
                                            .primary,
                                  ),
                                );
                              } else {
                                // Refresh to get latest state even on failure
                                await provider.loadNotifications();

                                if (!stateContext.mounted) {
                                  return;
                                }
                                ScaffoldMessenger.of(stateContext).showSnackBar(
                                  SnackBar(
                                    content: Text(
                                      provider.error ??
                                          'Failed to mark notifications as read',
                                    ),
                                    duration: const Duration(seconds: 4),
                                    backgroundColor:
                                        Theme.of(stateContext)
                                            .colorScheme
                                            .error,
                                  ),
                                );
                              }
                            } catch (e, stackTrace) {
                              // Refresh to get latest state even on error
                              await provider.loadNotifications();

                              if (!stateContext.mounted) {
                                return;
                              }
                              final errorHandler = ErrorHandler();
                              final error = errorHandler.parseError(
                                error: e,
                                stackTrace: stackTrace,
                                context: 'Mark All Notifications Read',
                              );
                              errorHandler.logError(error);

                              ScaffoldMessenger.of(stateContext).showSnackBar(
                                SnackBar(
                                  content: Text(error.getUserMessage()),
                                  duration: const Duration(seconds: 4),
                                  backgroundColor:
                                      Theme.of(stateContext)
                                          .colorScheme
                                          .error,
                                ),
                              );
                            } finally {
                              if (stateContext.mounted) {
                                setState(() {
                                  _isMarkingAllAsRead = false;
                                });
                              }
                            }
                          },
                    tooltip: localizations.markAllRead,
                    ),
                  );
                },
              ),
              IconButton(
                icon: const Icon(Icons.settings_outlined),
                onPressed: () {
                  Navigator.of(context).push(
                    MaterialPageRoute(
                      settings: const RouteSettings(name: '/notification-preferences'),
                      builder: (context) =>
                          const NotificationPreferencesScreen(),
                    ),
                  );
                },
                tooltip: localizations.notificationPreferences,
              ),
            ],
          ),
          body: ColoredBox(
            color: theme.scaffoldBackgroundColor,
            child: Consumer<NotificationProvider>(
              builder: (context, provider, child) {
                if (provider.isLoading) {
                  return Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const CircularProgressIndicator(),
                        const SizedBox(height: 16),
                        Text(
                          AppLocalizations.of(context)!.loadingNotifications,
                          style: Theme.of(context).textTheme.bodyMedium,
                        ),
                      ],
                    ),
                  );
                }

                if (provider.error != null) {
                  final localizations = AppLocalizations.of(context)!;
                  return Center(
                    child: Padding(
                      padding: const EdgeInsets.all(24),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(
                            Icons.error_outline,
                            size: 48,
                            color: Theme.of(context).colorScheme.error,
                          ),
                          const SizedBox(height: 16),
                          Text(
                            localizations.somethingWentWrong,
                            style: Theme.of(context)
                                .textTheme
                                .titleMedium
                                ?.copyWith(
                                  fontWeight: FontWeight.w600,
                                ),
                          ),
                          const SizedBox(height: 8),
                          Text(
                            provider.error!,
                            style: Theme.of(context).textTheme.bodyMedium,
                            textAlign: TextAlign.center,
                          ),
                          const SizedBox(height: 24),
                          FilledButton.icon(
                            onPressed: () {
                              provider.clearError();
                              provider.loadNotifications();
                            },
                            icon: const Icon(Icons.refresh, size: 18),
                            label: Text(localizations.retry),
                            style: FilledButton.styleFrom(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 24,
                                vertical: 12,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  );
                }

                if (provider.notifications.isEmpty) {
                  final localizations = AppLocalizations.of(context)!;
                  return Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(
                          Icons.notifications_none,
                          size: 56,
                          color: Theme.of(context).textTheme.bodySmall?.color,
                        ),
                        const SizedBox(height: 16),
                        Text(
                          localizations.noNotifications,
                          style:
                              Theme.of(context).textTheme.titleMedium?.copyWith(
                                    fontWeight: FontWeight.w600,
                                  ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          localizations.allCaughtUp,
                          style: Theme.of(context).textTheme.bodyMedium,
                        ),
                      ],
                    ),
                  );
                }

                final localizations = AppLocalizations.of(context)!;
                return RefreshIndicator(
                  onRefresh: () async {
                    await provider.loadNotifications();
                  },
                  color: context.navyIconColor,
                  child: ListView.builder(
                    padding: EdgeInsets.zero,
                    itemCount: provider.notifications.length,
                    itemBuilder: (context, index) {
                      final notification = provider.notifications[index];
                      return AppFadeInUp(
                        staggerIndex: index,
                        child: _RestrictedSwipeDismissible(
                          key: Key('notification_${notification.id}'),
                          notification: notification,
                          localizations: localizations,
                          provider: provider,
                        ),
                      );
                    },
                  ),
                );
              },
            ),
          ),
        );
      },
    );
  }
}

class _RestrictedSwipeDismissible extends StatefulWidget {
  final model.Notification notification;
  final AppLocalizations localizations;
  final NotificationProvider provider;

  const _RestrictedSwipeDismissible({
    super.key,
    required this.notification,
    required this.localizations,
    required this.provider,
  });

  @override
  State<_RestrictedSwipeDismissible> createState() =>
      _RestrictedSwipeDismissibleState();
}

class _RestrictedSwipeDismissibleState
    extends State<_RestrictedSwipeDismissible> {
  double? _cardWidth;
  bool _allowSwipe = true;
  double? _initialTouchX;

  bool _isTouchInAllowedArea(double touchX) {
    if (_cardWidth == null) return true;
    // Allow swipes from 0% to 90% of width (right 10% is non-touchable)
    final allowedEnd = _cardWidth! * 0.9;
    return touchX <= allowedEnd;
  }

  /// Navigate to a route (URL or app screen)
  Future<void> _navigateToRoute(BuildContext context, String route) async {
    try {
      // Check if this is a download URL
      final isDownloadUrl = route.contains('/api/download-app') ||
          route.contains('/download') ||
          route.endsWith('.apk') ||
          route.endsWith('.ipa') ||
          route.endsWith('.pdf') ||
          route.endsWith('.zip');

      // If it's a download URL, trigger download directly using Android's download manager
      if (isDownloadUrl) {
        String fullUrl;
        if (route.startsWith('http://') || route.startsWith('https://')) {
          fullUrl = route;
        } else if (route.startsWith('/')) {
          // Check if it's a backend API route
          if (route.startsWith('/api/')) {
            fullUrl = '${AppConfig.baseApiUrl}$route';
          } else {
            fullUrl = '${AppConfig.frontendUrl}$route';
          }
        } else {
          fullUrl = route;
        }

        // Directly trigger download using platformDefault to use Android's download manager
        // This keeps the download in-app context without opening external browser
        final uri = Uri.parse(fullUrl);
        if (await canLaunchUrl(uri)) {
          await launchUrl(uri, mode: LaunchMode.platformDefault);
          if (!context.mounted) {
            return;
          }
          final localizations = AppLocalizations.of(context)!;
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(localizations.downloadStarted),
              duration: const Duration(seconds: 2),
              backgroundColor: Theme.of(context).colorScheme.primary,
            ),
          );
        } else {
          if (!context.mounted) {
            return;
          }
          final localizations = AppLocalizations.of(context)!;
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(localizations.couldNotStartDownload),
              backgroundColor: Theme.of(context).colorScheme.error,
            ),
          );
        }
        return;
      }

      // If it's a full URL, open in webview
      if (route.startsWith('http://') || route.startsWith('https://')) {
        Navigator.of(context).pushNamed(
          AppRoutes.webview,
          arguments: route,
        );
      } else if (route.startsWith('/')) {
        // Relative path - navigate to app screen or webview
        // Check if it's a known app route
        if (route == AppRoutes.dashboard ||
            route == AppRoutes.notifications ||
            route == AppRoutes.settings ||
            AppRoutes.isNativeAdminPath(route)) {
          // App screen route
          Navigator.of(context).pushNamed(route);
        } else {
          // Web-only path: Flask backoffice (forms, admin, login, …) vs Next.js site
          final base = UrlHelper.isBackendPath(route)
              ? AppConfig.backendUrl
              : AppConfig.frontendUrl;
          final fullUrl = '$base$route';
          Navigator.of(context).pushNamed(
            AppRoutes.webview,
            arguments: fullUrl,
          );
        }
      }
    } catch (e) {
      DebugLogger.logError('Error navigating to route $route: $e');
      if (!context.mounted) {
        return;
      }
      final localizations = AppLocalizations.of(context)!;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('${localizations.error}: ${e.toString()}'),
          backgroundColor: Theme.of(context).colorScheme.error,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        _cardWidth = constraints.maxWidth;
        return Listener(
          onPointerDown: (event) {
            // Track the initial touch position
            _initialTouchX = event.localPosition.dx;
            final isInAllowedArea = _isTouchInAllowedArea(_initialTouchX!);
            setState(() {
              _allowSwipe = isInAllowedArea;
            });
          },
          onPointerUp: (event) {
            // Reset after pointer is released
            _initialTouchX = null;
            if (!_allowSwipe) {
              setState(() {
                _allowSwipe = true;
              });
            }
          },
          onPointerCancel: (event) {
            // Reset on cancel
            _initialTouchX = null;
            if (!_allowSwipe) {
              setState(() {
                _allowSwipe = true;
              });
            }
          },
          child: Stack(
            children: [
              Dismissible(
                key: widget.key!,
                direction: DismissDirection.endToStart,
                dismissThresholds: const {
                  DismissDirection.endToStart: 0.4,
                },
                movementDuration: const Duration(milliseconds: 200),
                background: Builder(
                  builder: (context) {
                    final theme = Theme.of(context);
                    return Container(
                      alignment: Alignment.centerRight,
                      padding: const EdgeInsets.only(right: 20),
                      decoration: BoxDecoration(
                        color: widget.notification.isRead
                            ? theme.colorScheme.primary
                            : theme.textTheme.bodySmall?.color,
                        border: Border(
                          bottom: BorderSide(
                            color: theme.dividerColor,
                            width: 0.5,
                          ),
                        ),
                      ),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.end,
                        children: [
                          Icon(
                            widget.notification.isRead
                                ? Icons.mark_email_unread_outlined
                                : Icons.mark_email_read_outlined,
                            color: Theme.of(context).colorScheme.onPrimary,
                            size: 24,
                          ),
                          const SizedBox(width: 8),
                          Text(
                            widget.notification.isRead
                                ? widget.localizations.markAsUnread
                                : widget.localizations.markAsRead,
                            style:
                                Theme.of(context).textTheme.labelLarge?.copyWith(
                                      color:
                                          Theme.of(context).colorScheme.onPrimary,
                                      fontWeight: FontWeight.w600,
                                    ),
                          ),
                        ],
                      ),
                    );
                  },
                ),
                confirmDismiss: (direction) async {
                  // Prevent swipe if it didn't start in the allowed area
                  if (!_allowSwipe) {
                    return false;
                  }
                  final messenger = ScaffoldMessenger.of(context);
                  final errorColor = Theme.of(context).colorScheme.error;
                  // Update the notification state
                  bool success = false;
                  if (widget.notification.isRead) {
                    success = await widget.provider
                        .markAsUnread([widget.notification.id]);
                  } else {
                    success = await widget.provider
                        .markAsRead([widget.notification.id]);
                  }

                  // Show error message if operation failed
                  if (!success) {
                    messenger.showSnackBar(
                      SnackBar(
                        content: Text(
                          widget.provider.error ??
                              'Failed to update notification',
                        ),
                        duration: const Duration(seconds: 3),
                        backgroundColor: errorColor,
                      ),
                    );
                  }

                  // Return false to prevent dismissal (keep item in list)
                  return false;
                },
                child: _NotificationTile(
                  notification: widget.notification,
                  onTap: () async {
                    if (!widget.notification.isRead) {
                      await widget.provider
                          .markAsRead([widget.notification.id]);
                    }
                    if (!context.mounted) {
                      return;
                    }
                    // Navigate to related URL or screen if available
                    if (widget.notification.relatedUrl != null &&
                        widget.notification.relatedUrl!.isNotEmpty) {
                      final redirectUrl = widget.notification.relatedUrl!;
                      _navigateToRoute(context, redirectUrl);
                    }
                  },
                ),
              ),
              // Absorb pointer events in the right 10% to prevent swipe gestures from starting
              if (_cardWidth != null)
                Positioned(
                  right: 0,
                  top: 0,
                  bottom: 0,
                  width: _cardWidth! * 0.1,
                  child: AbsorbPointer(
                    child: Container(color: Colors.transparent),
                  ),
                ),
            ],
          ),
        );
      },
    );
  }
}

class _NotificationLeadingAvatar extends StatelessWidget {
  final model.Notification notification;
  final bool isUnread;
  final bool isHighPriority;

  const _NotificationLeadingAvatar({
    required this.notification,
    required this.isUnread,
    required this.isHighPriority,
  });

  Color _actionIconColor(ThemeData theme) {
    if (!isUnread) {
      return theme.textTheme.bodySmall?.color ?? Colors.grey;
    }
    if (notification.priority == 'urgent') {
      return Colors.red.shade600;
    }
    if (isHighPriority) {
      return const Color(AppConstants.semanticNotificationOrange);
    }
    return theme.colorScheme.primary;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final mainActionIcon = (notification.actorActionIcon != null &&
            notification.actorActionIcon!.isNotEmpty)
        ? faIconForSuffix(notification.actorActionIcon)
        : faIconFromApiIconClass(notification.iconClass);

    final actor = notification.actor;
    if (actor != null && actor.initials.isNotEmpty) {
      final initials = actor.initials.length > 2
          ? actor.initials.substring(0, 2)
          : actor.initials;
      final badge = (notification.actorActionIcon != null &&
              notification.actorActionIcon!.isNotEmpty)
          ? faIconForSuffix(notification.actorActionIcon)
          : null;
      final diskColor = parseProfileColorHex(actor.profileColor) ??
          const Color(0xFF64748B);
      return ProfileLeadingAvatar(
        initials: initials,
        backgroundColor: diskColor,
        badgeIcon: badge,
      );
    }

    return ProfileLeadingIconFallback(
      icon: mainActionIcon,
      iconColor: _actionIconColor(theme),
    );
  }
}

class _NotificationTile extends StatelessWidget {
  final model.Notification notification;
  final VoidCallback onTap;

  const _NotificationTile({
    required this.notification,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    // Get current locale for date formatting
    final locale = Localizations.localeOf(context);

    // Format date with localized month names but keep Western numerals
    String formatDate(DateTime date) {
      // Disable native digits for Arabic to keep Western numerals (0-9)
      if (locale.languageCode == 'ar') {
        DateFormat.useNativeDigitsByDefaultFor('ar', false);
      }

      final dateFormat = DateFormat('MMM d, y • h:mm a', locale.languageCode);
      String formatted = dateFormat.format(date);

      // Replace any Indic numerals with Western numerals as a safety measure
      formatted = formatted
          .replaceAll('٠', '0')
          .replaceAll('١', '1')
          .replaceAll('٢', '2')
          .replaceAll('٣', '3')
          .replaceAll('٤', '4')
          .replaceAll('٥', '5')
          .replaceAll('٦', '6')
          .replaceAll('٧', '7')
          .replaceAll('٨', '8')
          .replaceAll('٩', '9');

      return formatted;
    }

    final formattedDate = formatDate(notification.createdAt);
    final isUnread = !notification.isRead;
    final isHighPriority = notification.isHighPriority;
    final isAdminMessage = notification.type == 'admin_message';
    final hasRedirect =
        notification.relatedUrl != null && notification.relatedUrl!.isNotEmpty;

    final primaryLine = notification.primaryIsMessage
        ? (notification.message.isNotEmpty
            ? notification.message
            : notification.title)
        : notification.title;
    final secondaryLine = notification.primaryIsMessage
        ? (notification.title.isNotEmpty && notification.title != primaryLine
            ? notification.title
            : '')
        : notification.message;

    final titleChipsRow = Row(
      children: [
        Flexible(
          child: Text(
            primaryLine,
            style: Theme.of(context).textTheme.titleMedium?.copyWith(
                  fontWeight: isUnread
                      ? FontWeight.w600
                      : (isHighPriority
                          ? FontWeight.w500
                          : FontWeight.w400),
                  color: isHighPriority
                      ? (isUnread
                          ? (theme.isDarkTheme
                              ? const Color(AppConstants
                                  .semanticNotificationOrangeDarkUnread)
                              : const Color(AppConstants
                                  .semanticNotificationOrangeTextStrongLight))
                          : (theme.isDarkTheme
                              ? const Color(AppConstants
                                  .semanticNotificationOrangeDarkRead)
                              : const Color(AppConstants
                                  .semanticNotificationOrangeTextMutedLight)))
                      : theme.textTheme.bodyLarge?.color,
                ),
          ),
        ),
        if (isAdminMessage)
          Container(
            margin: const EdgeInsets.only(left: 6),
            padding: const EdgeInsets.symmetric(
              horizontal: 6,
              vertical: 2,
            ),
            decoration: BoxDecoration(
              color: theme.isDarkTheme
                  ? const Color(AppConstants.themeSwitchCheckboxActiveDark)
                      .withValues(alpha: isUnread ? 1.0 : 0.7)
                  : theme.colorScheme.primary
                      .withValues(alpha: isUnread ? 1.0 : 0.7),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(
              'ADMIN',
              style: theme.textTheme.labelSmall?.copyWith(
                fontWeight: FontWeight.w700,
                color: theme.colorScheme.onPrimary,
                letterSpacing: 0.5,
              ),
            ),
          ),
        if (hasRedirect)
          Padding(
            padding: const EdgeInsets.only(left: 6),
            child: Icon(
              Icons.open_in_new,
              size: 14,
              color: theme.isDarkTheme
                  ? const Color(AppConstants.themeSwitchCheckboxActiveDark)
                      .withValues(alpha: isUnread ? 1.0 : 0.7)
                  : theme.colorScheme.primary
                      .withValues(alpha: isUnread ? 1.0 : 0.7),
            ),
          ),
      ],
    );

    // Theme-aware background colors
    Color getBackgroundColor() {
      if (theme.isDarkTheme) {
        if (isUnread) {
          return isHighPriority
              ? const Color(AppConstants.semanticNotificationOrange).withValues(alpha: 0.15)
              : const Color(AppConstants.themeSwitchCheckboxActiveDark)
                  .withValues(alpha: 0.25);
        }
        return theme.cardTheme.color ?? theme.colorScheme.surface;
      } else {
        if (isUnread) {
          return isHighPriority
              ? const Color(AppConstants.semanticNotificationUnreadRoseWash)
              : const Color(AppConstants.semanticNotificationUnreadBlueWash);
        }
        return theme.cardTheme.color ?? theme.colorScheme.surface;
      }
    }

    return Container(
      decoration: BoxDecoration(
        color: getBackgroundColor(),
        border: Border(
          left: isHighPriority
              ? (isUnread
                  ? const BorderSide(
                      color: Color(AppConstants.semanticNotificationOrange),
                      width: 6,
                    )
                  : BorderSide.none)
              : (isUnread
                  ? BorderSide(
                      color: theme.isDarkTheme
                          ? context.linkOnSurfaceColor
                          : const Color(AppConstants.errorColor),
                      width: 6,
                    )
                  : BorderSide.none),
          bottom: BorderSide(
            color: theme.dividerColor,
            width: 0.5,
          ),
        ),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                _NotificationLeadingAvatar(
                  notification: notification,
                  isUnread: isUnread,
                  isHighPriority: isHighPriority,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Stack(
                    clipBehavior: Clip.none,
                    children: [
                      Padding(
                        padding: EdgeInsets.only(right: isUnread ? 20 : 0),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Expanded(child: titleChipsRow),
                              ],
                            ),
                            if (secondaryLine.isNotEmpty) ...[
                              const SizedBox(height: 4),
                              Text(
                                secondaryLine,
                                style: Theme.of(context)
                                    .textTheme
                                    .bodyMedium
                                    ?.copyWith(
                                      height: 1.4,
                                      fontSize: notification.primaryIsMessage
                                          ? 13
                                          : null,
                                      color: notification.primaryIsMessage
                                          ? theme.textTheme.bodySmall?.color
                                          : null,
                                    ),
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ],
                            const SizedBox(height: 6),
                            Row(
                              children: [
                                if (notification.entityName != null &&
                                    notification.entityName!.isNotEmpty)
                                  Flexible(
                                    child: Container(
                                      padding: const EdgeInsets.symmetric(
                                        horizontal: 8,
                                        vertical: 4,
                                      ),
                                      decoration: BoxDecoration(
                                        color: theme.isDarkTheme
                                            ? const Color(AppConstants
                                                    .semanticNotificationSky)
                                                .withValues(alpha: 0.2)
                                            : const Color(AppConstants
                                                .semanticEntityChipLightWash),
                                        borderRadius: BorderRadius.circular(4),
                                        border: Border.all(
                                          color: theme.isDarkTheme
                                              ? const Color(AppConstants
                                                      .semanticNotificationSky)
                                                  .withValues(alpha: 0.5)
                                              : const Color(AppConstants
                                                      .semanticNotificationSky)
                                                  .withValues(alpha: 0.3),
                                          width: 0.5,
                                        ),
                                      ),
                                      child: Row(
                                        mainAxisSize: MainAxisSize.min,
                                        children: [
                                          Icon(
                                            Icons.location_on,
                                            size: 12,
                                            color: theme.isDarkTheme
                                                ? const Color(AppConstants
                                                    .semanticNotificationSkyLight)
                                                : const Color(AppConstants
                                                    .semanticNotificationSky),
                                          ),
                                          const SizedBox(width: 4),
                                          Flexible(
                                            child: Text(
                                              notification.entityName!,
                                              style: theme.textTheme.labelSmall
                                                  ?.copyWith(
                                                fontWeight: FontWeight.w500,
                                                color: theme.isDarkTheme
                                                    ? const Color(AppConstants
                                                        .semanticNotificationSkyLight)
                                                    : const Color(AppConstants
                                                        .semanticNotificationSky),
                                              ),
                                              overflow: TextOverflow.ellipsis,
                                              maxLines: 1,
                                            ),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ),
                                if (notification.entityName != null &&
                                    notification.entityName!.isNotEmpty)
                                  const SizedBox(width: 8),
                                Flexible(
                                  child: Text(
                                    formattedDate,
                                    style: Theme.of(context).textTheme.bodySmall,
                                    overflow: TextOverflow.ellipsis,
                                    maxLines: 1,
                                  ),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                      if (isUnread)
                        PositionedDirectional(
                          end: 0,
                          top: 0,
                          bottom: 0,
                          child: Center(
                            child: Container(
                              width: 8,
                              height: 8,
                              decoration: BoxDecoration(
                                color: theme.isDarkTheme
                                    ? theme.colorScheme.inversePrimary
                                    : (isHighPriority
                                        ? const Color(
                                            AppConstants
                                                .semanticNotificationOrange)
                                        : const Color(AppConstants.errorColor)),
                                shape: BoxShape.circle,
                              ),
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
