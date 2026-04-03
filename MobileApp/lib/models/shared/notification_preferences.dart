class NotificationPreferences {
  final bool emailNotifications;
  final List<String> notificationTypesEnabled;
  final String notificationFrequency; // 'instant', 'daily', 'weekly'
  final String? digestDay; // For weekly: 'monday', 'tuesday', etc.
  final String? digestTime; // Time in HH:MM format (24-hour)
  final bool soundEnabled;
  final bool pushNotifications;
  final List<String> pushNotificationTypesEnabled;

  NotificationPreferences({
    required this.emailNotifications,
    required this.notificationTypesEnabled,
    required this.notificationFrequency,
    this.digestDay,
    this.digestTime,
    required this.soundEnabled,
    required this.pushNotifications,
    required this.pushNotificationTypesEnabled,
  });

  factory NotificationPreferences.fromJson(Map<String, dynamic> json) {
    return NotificationPreferences(
      emailNotifications: json['email_notifications'] ?? true,
      notificationTypesEnabled: json['notification_types_enabled'] != null
          ? List<String>.from(json['notification_types_enabled'])
          : [],
      notificationFrequency: json['notification_frequency'] ?? 'instant',
      digestDay: json['digest_day'],
      digestTime: json['digest_time'],
      soundEnabled: json['sound_enabled'] ?? false,
      pushNotifications: json['push_notifications'] ?? true,
      pushNotificationTypesEnabled:
          json['push_notification_types_enabled'] != null
              ? List<String>.from(json['push_notification_types_enabled'])
              : [],
    );
  }

  Map<String, dynamic> toJson() {
    final json = <String, dynamic>{
      'email_notifications': emailNotifications,
      'notification_types_enabled': notificationTypesEnabled,
      'notification_frequency': notificationFrequency,
      'sound_enabled': soundEnabled,
      'push_notifications': pushNotifications,
      'push_notification_types_enabled': pushNotificationTypesEnabled,
    };

    // Always include digest fields - use null if not set
    // This ensures the backend always receives these fields
    json['digest_day'] = digestDay;
    json['digest_time'] = digestTime;

    return json;
  }

  NotificationPreferences copyWith({
    bool? emailNotifications,
    List<String>? notificationTypesEnabled,
    String? notificationFrequency,
    String? digestDay,
    String? digestTime,
    bool? soundEnabled,
    bool? pushNotifications,
    List<String>? pushNotificationTypesEnabled,
  }) {
    return NotificationPreferences(
      emailNotifications: emailNotifications ?? this.emailNotifications,
      notificationTypesEnabled:
          notificationTypesEnabled ?? this.notificationTypesEnabled,
      notificationFrequency:
          notificationFrequency ?? this.notificationFrequency,
      digestDay: digestDay ?? this.digestDay,
      digestTime: digestTime ?? this.digestTime,
      soundEnabled: soundEnabled ?? this.soundEnabled,
      pushNotifications: pushNotifications ?? this.pushNotifications,
      pushNotificationTypesEnabled:
          pushNotificationTypesEnabled ?? this.pushNotificationTypesEnabled,
    );
  }
}
