import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/shared/notification_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../widgets/app_bar.dart';
import '../../widgets/app_switch_list_tile.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../models/shared/notification_preferences.dart';
import '../../utils/constants.dart';
import '../../utils/theme_extensions.dart';
import '../../l10n/app_localizations.dart';

class NotificationPreferencesScreen extends StatefulWidget {
  const NotificationPreferencesScreen({super.key});

  @override
  State<NotificationPreferencesScreen> createState() =>
      _NotificationPreferencesScreenState();
}

class _NotificationPreferencesScreenState
    extends State<NotificationPreferencesScreen> {
  // Available notification types from backend
  static const List<String> notificationTypes = [
    'assignment_created',
    'assignment_submitted',
    'assignment_approved',
    'assignment_reopened',
    'public_submission_received',
    'form_updated',
    'document_uploaded',
    'user_added_to_country',
    'template_updated',
    'self_report_created',
    'deadline_reminder',
  ];

  // Grid system constants (8px base unit)
  static const double gridUnit = 8.0;
  static const double grid2 = gridUnit * 2; // 16
  static const double grid3 = gridUnit * 3; // 24
  static const double grid6 = gridUnit * 6; // 48
  static const double formFieldHeight = grid6; // 48
  static const double sectionSpacing = grid2; // 16
  static const double sectionTitleSpacing = gridUnit + 2; // 10
  static const double horizontalPadding = grid2; // 16
  static const double formFieldPadding = gridUnit + 4; // 12
  static const double formFieldVerticalPadding = gridUnit + 2; // 10

  bool _soundEnabled = false;
  String _notificationFrequency = 'instant';
  String? _digestDay;
  String _digestTime = '09:00';
  Set<String> _enabledTypes = {};
  Set<String> _pushEnabledTypes = {};

  bool _isSaving = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _loadPreferences();
    });
  }

  void _loadPreferences() {
    final provider = Provider.of<NotificationProvider>(context, listen: false);
    if (provider.preferences == null) {
      provider.loadPreferences().then((_) {
        _updateLocalState(provider.preferences);
      });
    } else {
      _updateLocalState(provider.preferences);
    }
  }

  void _updateLocalState(NotificationPreferences? preferences) {
    if (preferences != null) {
      setState(() {
        _soundEnabled = preferences.soundEnabled;
        _notificationFrequency = preferences.notificationFrequency;
        _digestDay = preferences.digestDay;
        _digestTime = preferences.digestTime ?? '09:00';
        // Empty list means all enabled
        _enabledTypes = preferences.notificationTypesEnabled.isEmpty
            ? notificationTypes.toSet()
            : preferences.notificationTypesEnabled.toSet();
        // Empty list means all enabled
        _pushEnabledTypes = preferences.pushNotificationTypesEnabled.isEmpty
            ? notificationTypes.toSet()
            : preferences.pushNotificationTypesEnabled.toSet();
      });
    }
  }

  String _formatNotificationType(String type, AppLocalizations localizations) {
    switch (type) {
      case 'assignment_created':
        return localizations.assignmentCreated;
      case 'assignment_submitted':
        return localizations.assignmentSubmitted;
      case 'assignment_approved':
        return localizations.assignmentApproved;
      case 'assignment_reopened':
        return localizations.assignmentReopened;
      case 'public_submission_received':
        return localizations.publicSubmissionReceived;
      case 'form_updated':
        return localizations.formUpdated;
      case 'document_uploaded':
        return localizations.documentUploaded;
      case 'user_added_to_country':
        return localizations.userAddedToCountry;
      case 'template_updated':
        return localizations.templateUpdated;
      case 'self_report_created':
        return localizations.selfReportCreated;
      case 'deadline_reminder':
        return localizations.deadlineReminder;
      default:
        return type.replaceAll('_', ' ').split(' ').map((word) {
          return word[0].toUpperCase() + word.substring(1);
        }).join(' ');
    }
  }

  Future<void> _savePreferences() async {
    final localizations = AppLocalizations.of(context)!;
    print('=== SAVE PREFERENCES CALLED ===');
    setState(() {
      _isSaving = true;
    });

    final provider = Provider.of<NotificationProvider>(context, listen: false);
    print('Provider obtained');

    // If all types are enabled, send empty list (backend interprets as all enabled)
    final allEmailSelected = _enabledTypes.length == notificationTypes.length;
    final allPushSelected =
        _pushEnabledTypes.length == notificationTypes.length;

    final typesToSend =
        allEmailSelected ? <String>[] : List<String>.from(_enabledTypes);

    final pushTypesToSend =
        allPushSelected ? <String>[] : List<String>.from(_pushEnabledTypes);

    // Determine email_notifications and push_notifications based on whether any types are selected
    // True if all types selected (empty array) OR if some types are selected
    final emailNotifications = allEmailSelected || _enabledTypes.isNotEmpty;
    final pushNotifications = allPushSelected || _pushEnabledTypes.isNotEmpty;

    // Set digest day and time based on frequency
    String? digestDay;
    String? digestTime;
    if (_notificationFrequency == 'daily' ||
        _notificationFrequency == 'weekly') {
      digestTime = _digestTime;
      if (_notificationFrequency == 'weekly') {
        digestDay = _digestDay ?? 'monday'; // Default to Monday if not set
      }
    }

    final preferences = NotificationPreferences(
      emailNotifications: emailNotifications,
      notificationTypesEnabled: typesToSend,
      notificationFrequency: _notificationFrequency,
      digestDay: digestDay,
      digestTime: digestTime,
      soundEnabled: _soundEnabled,
      pushNotifications: pushNotifications,
      pushNotificationTypesEnabled: pushTypesToSend,
    );

    print('Calling provider.updatePreferences...');
    try {
      final success = await provider.updatePreferences(preferences);
      print('Update result: $success');

      setState(() {
        _isSaving = false;
      });

      if (success) {
        if (mounted) {
          final theme = Theme.of(context);
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(localizations.preferencesSavedSuccessfully),
              backgroundColor: theme.isDarkTheme
                  ? const Color(AppConstants.themeSwitchCheckboxActiveDark)
                  : theme.colorScheme.primary,
              duration: const Duration(seconds: 2),
            ),
          );
          Navigator.of(context).pop();
        }
      } else {
        print('Save failed - error: ${provider.preferencesError}');
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(
                  provider.preferencesError ?? localizations.failedToSavePreferences),
              backgroundColor: Theme.of(context).colorScheme.error,
              duration: const Duration(seconds: 3),
            ),
          );
        }
      }
    } catch (e, stackTrace) {
      print('=== EXCEPTION IN _savePreferences ===');
      print('Error: $e');
      print('Stack trace: $stackTrace');
      setState(() {
        _isSaving = false;
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              '${localizations.error}: ${e.toString()}',
            ),
            backgroundColor: Theme.of(context).colorScheme.error,
            duration: const Duration(seconds: 5),
          ),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;

    final theme = Theme.of(context);
    return Scaffold(
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppAppBar(
        title: localizations.notificationPreferences,
      ),
      body: Consumer<NotificationProvider>(
        builder: (context, provider, child) {
          if (provider.isLoadingPreferences && provider.preferences == null) {
            return Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  CircularProgressIndicator(
                    valueColor: AlwaysStoppedAnimation<Color>(
                      theme.isDarkTheme
                          ? const Color(
                              AppConstants.themeSwitchCheckboxActiveDark)
                          : theme.colorScheme.primary,
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    AppLocalizations.of(context)!.loadingPreferences,
                    style: TextStyle(
                      color: context.textSecondaryColor,
                      fontSize: 14,
                    ),
                  ),
                ],
              ),
            );
          }

          if (provider.preferencesError != null &&
              provider.preferences == null) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(
                      Icons.error_outline,
                      size: 48,
                      color: theme.colorScheme.error,
                    ),
                    const SizedBox(height: 16),
                    Text(
                      localizations.somethingWentWrong,
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w600,
                        color: context.textColor,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      provider.preferencesError!,
                      style: TextStyle(
                        color: context.textSecondaryColor,
                        fontSize: 14,
                      ),
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 24),
                    FilledButton.icon(
                      onPressed: () {
                        provider.clearPreferencesError();
                        _loadPreferences();
                      },
                      icon: const Icon(Icons.refresh, size: 18),
                      label: Text(localizations.retry),
                      style: FilledButton.styleFrom(
                        backgroundColor: theme.isDarkTheme
                            ? const Color(
                                AppConstants.themeSwitchCheckboxActiveDark)
                            : theme.colorScheme.primary,
                        foregroundColor: theme.colorScheme.onPrimary,
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

          return SingleChildScrollView(
            padding: const EdgeInsets.all(horizontalPadding),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Sound Notifications
                _buildSection(
                  title: localizations.soundNotifications,
                  child: AppSwitchListTile(
                    value: _soundEnabled,
                    onChanged: (value) {
                      setState(() {
                        _soundEnabled = value;
                      });
                    },
                    title: localizations.enableSound,
                    subtitle: localizations.playSoundForNewNotifications,
                  ),
                ),

                const SizedBox(height: sectionSpacing),

                // Email Frequency
                _buildSection(
                  title: localizations.emailFrequency,
                  child: SizedBox(
                    height: formFieldHeight,
                    child: DropdownButtonFormField<String>(
                      initialValue: _notificationFrequency,
                      decoration: const InputDecoration(
                        border: OutlineInputBorder(),
                        contentPadding: EdgeInsets.symmetric(
                          horizontal: formFieldPadding,
                          vertical: formFieldVerticalPadding,
                        ),
                        isDense: true,
                      ),
                      style: TextStyle(
                        fontSize: 14,
                        color: context.textColor,
                      ),
                      items: [
                        DropdownMenuItem(
                          value: 'instant',
                          child: Text(localizations.instant),
                        ),
                        DropdownMenuItem(
                          value: 'daily',
                          child: Text(localizations.dailyDigest),
                        ),
                        DropdownMenuItem(
                          value: 'weekly',
                          child: Text(localizations.weeklyDigest),
                        ),
                      ],
                      onChanged: (value) {
                        if (value != null) {
                          setState(() {
                            _notificationFrequency = value;
                            // Clear digest day if switching to daily or instant
                            if (value == 'daily' || value == 'instant') {
                              _digestDay = null;
                            } else if (value == 'weekly' &&
                                _digestDay == null) {
                              _digestDay = 'monday'; // Default to Monday
                            }
                          });
                        }
                      },
                    ),
                  ),
                ),

                // Digest Schedule (shown when daily or weekly is selected)
                if (_notificationFrequency == 'daily' ||
                    _notificationFrequency == 'weekly') ...[
                  const SizedBox(height: sectionSpacing),
                  _buildSection(
                    title: localizations.digestSchedule,
                    child: LayoutBuilder(
                      builder: (context, constraints) {
                        // Use grid layout: if weekly, show day and time in a row if space allows
                        final bool isWide = constraints.maxWidth > 400;
                        final bool isWeekly =
                            _notificationFrequency == 'weekly';

                        if (isWeekly && isWide) {
                          // Grid layout: day and time side by side
                          return Row(
                            children: [
                              Expanded(
                                child: SizedBox(
                                  height: formFieldHeight,
                                  child: DropdownButtonFormField<String>(
                                    initialValue: _digestDay ?? 'monday',
                                    decoration: InputDecoration(
                                      labelText: localizations.dayOfWeek,
                                      border: const OutlineInputBorder(),
                                      contentPadding: const EdgeInsets.symmetric(
                                        horizontal: formFieldPadding,
                                        vertical: formFieldVerticalPadding,
                                      ),
                                      isDense: true,
                                    ),
                                    style: TextStyle(
                                      fontSize: 14,
                                      color: context.textColor,
                                    ),
                                    items: [
                                      DropdownMenuItem(
                                          value: 'monday',
                                          child: Text(localizations.monday)),
                                      DropdownMenuItem(
                                          value: 'tuesday',
                                          child: Text(localizations.tuesday)),
                                      DropdownMenuItem(
                                          value: 'wednesday',
                                          child: Text(localizations.wednesday)),
                                      DropdownMenuItem(
                                          value: 'thursday',
                                          child: Text(localizations.thursday)),
                                      DropdownMenuItem(
                                          value: 'friday',
                                          child: Text(localizations.friday)),
                                      DropdownMenuItem(
                                          value: 'saturday',
                                          child: Text(localizations.saturday)),
                                      DropdownMenuItem(
                                          value: 'sunday',
                                          child: Text(localizations.sunday)),
                                    ],
                                    onChanged: (value) {
                                      if (value != null) {
                                        setState(() {
                                          _digestDay = value;
                                        });
                                      }
                                    },
                                  ),
                                ),
                              ),
                              const SizedBox(width: sectionSpacing),
                              Expanded(
                                child: SizedBox(
                                  height: formFieldHeight,
                                  child: InkWell(
                                    onTap: () async {
                                      final parts = _digestTime.split(':');
                                      final hour = int.tryParse(parts[0]) ?? 9;
                                      final minute = int.tryParse(
                                              parts.length > 1
                                                  ? parts[1]
                                                  : '0') ??
                                          0;

                                      final TimeOfDay? picked =
                                          await showTimePicker(
                                        context: context,
                                        initialTime: TimeOfDay(
                                            hour: hour, minute: minute),
                                        builder: (context, child) {
                                          return Theme(
                                            data: Theme.of(context).copyWith(
                                              colorScheme: ColorScheme.fromSeed(
                                                seedColor: theme.isDarkTheme
                                                    ? const Color(AppConstants
                                                        .themeSwitchCheckboxActiveDark)
                                                    : theme.colorScheme.primary,
                                                brightness: theme.brightness,
                                              ),
                                            ),
                                            child: child!,
                                          );
                                        },
                                      );

                                      if (picked != null) {
                                        setState(() {
                                          _digestTime =
                                              '${picked.hour.toString().padLeft(2, '0')}:${picked.minute.toString().padLeft(2, '0')}';
                                        });
                                      }
                                    },
                                    child: InputDecorator(
                                      decoration: InputDecoration(
                                        labelText: localizations.timeLocalTime,
                                        border: const OutlineInputBorder(),
                                        contentPadding: const EdgeInsets.symmetric(
                                          horizontal: formFieldPadding,
                                          vertical: formFieldVerticalPadding,
                                        ),
                                        isDense: true,
                                        suffixIcon: Icon(Icons.access_time,
                                            size: 20, color: context.iconColor),
                                      ),
                                      child: Text(
                                        _digestTime,
                                        style: TextStyle(
                                          fontSize: 14,
                                          color: context.textColor,
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            ],
                          );
                        } else {
                          // Stacked layout for narrow screens or daily digest
                          return Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              if (isWeekly) ...[
                                SizedBox(
                                  height: formFieldHeight,
                                  child: DropdownButtonFormField<String>(
                                    initialValue: _digestDay ?? 'monday',
                                    decoration: InputDecoration(
                                      labelText: localizations.dayOfWeek,
                                      border: const OutlineInputBorder(),
                                      contentPadding: const EdgeInsets.symmetric(
                                        horizontal: formFieldPadding,
                                        vertical: formFieldVerticalPadding,
                                      ),
                                      isDense: true,
                                    ),
                                    style: TextStyle(
                                      fontSize: 14,
                                      color: context.textColor,
                                    ),
                                    items: [
                                      DropdownMenuItem(
                                          value: 'monday',
                                          child: Text(localizations.monday)),
                                      DropdownMenuItem(
                                          value: 'tuesday',
                                          child: Text(localizations.tuesday)),
                                      DropdownMenuItem(
                                          value: 'wednesday',
                                          child: Text(localizations.wednesday)),
                                      DropdownMenuItem(
                                          value: 'thursday',
                                          child: Text(localizations.thursday)),
                                      DropdownMenuItem(
                                          value: 'friday',
                                          child: Text(localizations.friday)),
                                      DropdownMenuItem(
                                          value: 'saturday',
                                          child: Text(localizations.saturday)),
                                      DropdownMenuItem(
                                          value: 'sunday',
                                          child: Text(localizations.sunday)),
                                    ],
                                    onChanged: (value) {
                                      if (value != null) {
                                        setState(() {
                                          _digestDay = value;
                                        });
                                      }
                                    },
                                  ),
                                ),
                                const SizedBox(height: sectionSpacing),
                              ],
                              SizedBox(
                                height: formFieldHeight,
                                child: InkWell(
                                  onTap: () async {
                                    final parts = _digestTime.split(':');
                                    final hour = int.tryParse(parts[0]) ?? 9;
                                    final minute = int.tryParse(parts.length > 1
                                            ? parts[1]
                                            : '0') ??
                                        0;

                                    final TimeOfDay? picked =
                                        await showTimePicker(
                                      context: context,
                                      initialTime:
                                          TimeOfDay(hour: hour, minute: minute),
                                      builder: (context, child) {
                                        return Theme(
                                          data: Theme.of(context).copyWith(
                                            colorScheme: ColorScheme.fromSeed(
                                              seedColor: theme.isDarkTheme
                                                  ? const Color(AppConstants
                                                      .themeSwitchCheckboxActiveDark)
                                                  : theme.colorScheme.primary,
                                              brightness: theme.brightness,
                                            ),
                                          ),
                                          child: child!,
                                        );
                                      },
                                    );

                                    if (picked != null) {
                                      setState(() {
                                        _digestTime =
                                            '${picked.hour.toString().padLeft(2, '0')}:${picked.minute.toString().padLeft(2, '0')}';
                                      });
                                    }
                                  },
                                  child: InputDecorator(
                                    decoration: InputDecoration(
                                      labelText: localizations.timeLocalTime,
                                      border: const OutlineInputBorder(),
                                      contentPadding: const EdgeInsets.symmetric(
                                        horizontal: formFieldPadding,
                                        vertical: formFieldVerticalPadding,
                                      ),
                                      isDense: true,
                                      helperText: isWeekly
                                          ? null
                                          : localizations.selectDigestTimeDescription,
                                      suffixIcon: Icon(Icons.access_time,
                                          size: 20, color: context.iconColor),
                                    ),
                                    child: Text(
                                      _digestTime,
                                      style: TextStyle(
                                        fontSize: 14,
                                        color: context.textColor,
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            ],
                          );
                        }
                      },
                    ),
                  ),
                ],

                const SizedBox(height: sectionSpacing),

                // Notification Types Table
                _buildSection(
                  title: localizations.notificationTypes,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        localizations.configureNotificationTypesDescription,
                        style: TextStyle(
                          fontSize: 13,
                          color: context.textSecondaryColor,
                        ),
                      ),
                      const SizedBox(height: sectionSpacing),
                      Container(
                        decoration: BoxDecoration(
                          border: Border.all(
                            color: context.borderColor,
                            width: 1,
                          ),
                          borderRadius: BorderRadius.circular(gridUnit),
                        ),
                        child: Column(
                          children: [
                            // Table Header
                            Container(
                              decoration: BoxDecoration(
                                color: context.subtleSurfaceColor,
                                borderRadius: const BorderRadius.only(
                                  topLeft: Radius.circular(gridUnit),
                                  topRight: Radius.circular(gridUnit),
                                ),
                              ),
                              child: Table(
                                columnWidths: const {
                                  0: FlexColumnWidth(2),
                                  1: FlexColumnWidth(1),
                                  2: FlexColumnWidth(1),
                                },
                                children: [
                                  TableRow(
                                    decoration: BoxDecoration(
                                      border: Border(
                                        bottom: BorderSide(
                                          color: context.dividerColor,
                                          width: 1,
                                        ),
                                      ),
                                    ),
                                    children: [
                                      Padding(
                                        padding: const EdgeInsets.symmetric(
                                          horizontal: formFieldPadding,
                                          vertical: formFieldVerticalPadding,
                                        ),
                                        child: Text(
                                          localizations.notificationType,
                                          style: TextStyle(
                                            fontSize: 13,
                                            fontWeight: FontWeight.w600,
                                            color: context.textColor,
                                          ),
                                        ),
                                      ),
                                      Padding(
                                        padding: const EdgeInsets.symmetric(
                                          horizontal: 12,
                                          vertical: 10,
                                        ),
                                        child: Center(
                                          child: Text(
                                            localizations.email,
                                            style: TextStyle(
                                              fontSize: 13,
                                              fontWeight: FontWeight.w600,
                                              color: context.textColor,
                                            ),
                                          ),
                                        ),
                                      ),
                                      Padding(
                                        padding: const EdgeInsets.symmetric(
                                          horizontal: 12,
                                          vertical: 10,
                                        ),
                                        child: Center(
                                          child: Text(
                                            localizations.push,
                                            style: TextStyle(
                                              fontSize: 13,
                                              fontWeight: FontWeight.w600,
                                              color: context.textColor,
                                            ),
                                          ),
                                        ),
                                      ),
                                    ],
                                  ),
                                  // Select All Row
                                  TableRow(
                                    decoration: BoxDecoration(
                                      border: Border(
                                        bottom: BorderSide(
                                          color: context.dividerColor,
                                          width: 1,
                                        ),
                                      ),
                                    ),
                                    children: [
                                      const Padding(
                                        padding: EdgeInsets.symmetric(
                                          horizontal: formFieldPadding,
                                          vertical: gridUnit - 2,
                                        ),
                                        child: SizedBox.shrink(),
                                      ),
                                      Padding(
                                        padding: const EdgeInsets.symmetric(
                                          horizontal: gridUnit,
                                          vertical: gridUnit - 2,
                                        ),
                                        child: Center(
                                          child: InkWell(
                                            onTap: () {
                                              setState(() {
                                                final allEmailSelected =
                                                    _enabledTypes.length ==
                                                        notificationTypes
                                                            .length;
                                                if (allEmailSelected) {
                                                  _enabledTypes.clear();
                                                } else {
                                                  _enabledTypes =
                                                      notificationTypes.toSet();
                                                }
                                              });
                                            },
                                            child: Row(
                                              mainAxisSize: MainAxisSize.min,
                                              mainAxisAlignment:
                                                  MainAxisAlignment.center,
                                              children: [
                                                Checkbox(
                                                  value: _enabledTypes.length ==
                                                      notificationTypes.length,
                                                  onChanged: (value) {
                                                    setState(() {
                                                      if (value == true) {
                                                        _enabledTypes =
                                                            notificationTypes
                                                                .toSet();
                                                      } else {
                                                        _enabledTypes.clear();
                                                      }
                                                    });
                                                  },
                                                  activeColor: theme.isDarkTheme
                                                      ? const Color(AppConstants
                                                          .themeSwitchCheckboxActiveDark)
                                                      : theme.colorScheme.primary,
                                                  materialTapTargetSize:
                                                      MaterialTapTargetSize
                                                          .shrinkWrap,
                                                  visualDensity:
                                                      VisualDensity.compact,
                                                ),
                                                const SizedBox(width: 2),
                                                Flexible(
                                                  child: Text(
                                                    localizations.all,
                                                    style: TextStyle(
                                                      fontSize: 11,
                                                      fontWeight:
                                                          FontWeight.w500,
                                                      color: context.textColor,
                                                    ),
                                                    overflow:
                                                        TextOverflow.ellipsis,
                                                  ),
                                                ),
                                              ],
                                            ),
                                          ),
                                        ),
                                      ),
                                      Padding(
                                        padding: const EdgeInsets.symmetric(
                                          horizontal: gridUnit,
                                          vertical: gridUnit - 2,
                                        ),
                                        child: Center(
                                          child: InkWell(
                                            onTap: () {
                                              setState(() {
                                                final allPushSelected =
                                                    _pushEnabledTypes.length ==
                                                        notificationTypes
                                                            .length;
                                                if (allPushSelected) {
                                                  _pushEnabledTypes.clear();
                                                } else {
                                                  _pushEnabledTypes =
                                                      notificationTypes.toSet();
                                                }
                                              });
                                            },
                                            child: Row(
                                              mainAxisSize: MainAxisSize.min,
                                              mainAxisAlignment:
                                                  MainAxisAlignment.center,
                                              children: [
                                                Checkbox(
                                                  value: _pushEnabledTypes
                                                          .length ==
                                                      notificationTypes.length,
                                                  onChanged: (value) {
                                                    setState(() {
                                                      if (value == true) {
                                                        _pushEnabledTypes =
                                                            notificationTypes
                                                                .toSet();
                                                      } else {
                                                        _pushEnabledTypes
                                                            .clear();
                                                      }
                                                    });
                                                  },
                                                  activeColor: theme.isDarkTheme
                                                      ? const Color(AppConstants
                                                          .themeSwitchCheckboxActiveDark)
                                                      : theme.colorScheme.primary,
                                                  materialTapTargetSize:
                                                      MaterialTapTargetSize
                                                          .shrinkWrap,
                                                  visualDensity:
                                                      VisualDensity.compact,
                                                ),
                                                const SizedBox(width: 2),
                                                Flexible(
                                                  child: Text(
                                                    localizations.all,
                                                    style: TextStyle(
                                                      fontSize: 11,
                                                      fontWeight:
                                                          FontWeight.w500,
                                                      color: context.textColor,
                                                    ),
                                                    overflow:
                                                        TextOverflow.ellipsis,
                                                  ),
                                                ),
                                              ],
                                            ),
                                          ),
                                        ),
                                      ),
                                    ],
                                  ),
                                ],
                              ),
                            ),
                            // Table Body
                            ListView.builder(
                              shrinkWrap: true,
                              physics: const NeverScrollableScrollPhysics(),
                              itemCount: notificationTypes.length,
                              itemBuilder: (context, index) {
                                final type = notificationTypes[index];
                                final emailEnabled =
                                    _enabledTypes.contains(type);
                                final pushEnabled =
                                    _pushEnabledTypes.contains(type);

                                return Table(
                                  columnWidths: const {
                                    0: FlexColumnWidth(2),
                                    1: FlexColumnWidth(1),
                                    2: FlexColumnWidth(1),
                                  },
                                  children: [
                                    TableRow(
                                      decoration: BoxDecoration(
                                        border: Border(
                                          bottom: BorderSide(
                                            color: index <
                                                    notificationTypes.length - 1
                                                ? context.dividerColor
                                                : Colors.transparent,
                                            width: 1,
                                          ),
                                        ),
                                      ),
                                      children: [
                                        Padding(
                                          padding: const EdgeInsets.symmetric(
                                            horizontal: formFieldPadding,
                                            vertical: formFieldVerticalPadding,
                                          ),
                                          child: Text(
                                            _formatNotificationType(type, localizations),
                                            style: TextStyle(
                                              fontSize: 13,
                                              fontWeight: FontWeight.w500,
                                              color: context.textColor,
                                            ),
                                          ),
                                        ),
                                        Padding(
                                          padding: const EdgeInsets.symmetric(
                                            horizontal: formFieldPadding,
                                            vertical: formFieldVerticalPadding,
                                          ),
                                          child: Center(
                                            child: Checkbox(
                                              value: emailEnabled,
                                              onChanged: (value) {
                                                setState(() {
                                                  if (value == true) {
                                                    _enabledTypes.add(type);
                                                  } else {
                                                    _enabledTypes.remove(type);
                                                  }
                                                });
                                              },
                                              activeColor: theme.isDarkTheme
                                                  ? const Color(AppConstants
                                                      .themeSwitchCheckboxActiveDark)
                                                  : theme.colorScheme.primary,
                                              materialTapTargetSize:
                                                  MaterialTapTargetSize
                                                      .shrinkWrap,
                                            ),
                                          ),
                                        ),
                                        Padding(
                                          padding: const EdgeInsets.symmetric(
                                            horizontal: 12,
                                            vertical: 10,
                                          ),
                                          child: Center(
                                            child: Checkbox(
                                              value: pushEnabled,
                                              onChanged: (value) {
                                                setState(() {
                                                  if (value == true) {
                                                    _pushEnabledTypes.add(type);
                                                  } else {
                                                    _pushEnabledTypes
                                                        .remove(type);
                                                  }
                                                });
                                              },
                                              activeColor: theme.isDarkTheme
                                                  ? const Color(AppConstants
                                                      .themeSwitchCheckboxActiveDark)
                                                  : theme.colorScheme.primary,
                                              materialTapTargetSize:
                                                  MaterialTapTargetSize
                                                      .shrinkWrap,
                                            ),
                                          ),
                                        ),
                                      ],
                                    ),
                                  ],
                                );
                              },
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),

                const SizedBox(height: grid3),

                // Save Button
                SizedBox(
                  width: double.infinity,
                  child: FilledButton(
                    onPressed: _isSaving ? null : _savePreferences,
                    style: FilledButton.styleFrom(
                      backgroundColor: theme.isDarkTheme
                          ? const Color(
                              AppConstants.themeSwitchCheckboxActiveDark)
                          : theme.colorScheme.primary,
                      foregroundColor: theme.colorScheme.onPrimary,
                      padding:
                          const EdgeInsets.symmetric(vertical: sectionSpacing - 4),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(gridUnit - 2),
                      ),
                    ),
                    child: _isSaving
                        ? SizedBox(
                            height: 18,
                            width: 18,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              valueColor: AlwaysStoppedAnimation<Color>(
                                theme.colorScheme.onPrimary,
                              ),
                            ),
                          )
                        : Text(
                            localizations.savePreferences,
                            style: const TextStyle(
                              fontSize: 15,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                  ),
                ),
              ],
            ),
          );
        },
      ),
      bottomNavigationBar: Consumer<AuthProvider>(
        builder: (context, authProvider, child) {
          final user = authProvider.user;
          final isAdmin = user?.isAdmin ?? false;

          // For admin users, notifications is at index 0
          // For non-admin, we use -1 to indicate no tab is active
          // The default navigation behavior will handle tab switching from nested screens
          return AppBottomNavigationBar(
            currentIndex: isAdmin ? 0 : -1,
            chatbotEnabled: user?.chatbotEnabled ?? false,
            // onTap is optional - if not provided, uses NavigationHelper.navigateToMainTab by default
          );
        },
      ),
    );
  }

  Widget _buildSection({required String title, required Widget child}) {
    return Builder(
      builder: (context) => Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w600,
              color: context.textColor,
            ),
          ),
          const SizedBox(height: sectionTitleSpacing),
          child,
        ],
      ),
    );
  }
}
