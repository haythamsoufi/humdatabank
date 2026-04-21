class NotificationActor {
  final int id;
  final String name;
  final String initials;
  final String profileColor;

  const NotificationActor({
    required this.id,
    required this.name,
    required this.initials,
    required this.profileColor,
  });

  factory NotificationActor.fromJson(Map<String, dynamic>? json) {
    if (json == null) {
      return const NotificationActor(
        id: 0,
        name: '',
        initials: '?',
        profileColor: '#64748b',
      );
    }
    return NotificationActor(
      id: (json['id'] as num?)?.toInt() ?? 0,
      name: json['name']?.toString() ?? '',
      initials: json['initials']?.toString() ?? '?',
      profileColor: json['profile_color']?.toString() ?? '#64748b',
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'initials': initials,
        'profile_color': profileColor,
      };
}

class Notification {
  final int id;
  final String title;
  final String message;
  final String type;
  final bool isRead;
  final DateTime createdAt;
  final Map<String, dynamic>? metadata;
  final String? relatedUrl;
  final String priority;
  final String? notificationTypeLabel;
  final String? entityName;
  final String? entityType;

  /// When true, [message] is the primary headline and [title] is the subtitle (category line).
  final bool primaryIsMessage;

  /// User who triggered the notification (access requester, submitter, etc.), if known.
  final NotificationActor? actor;

  /// Font Awesome icon suffix, e.g. `fa-key` (matches Backoffice `actor_action_icon`).
  final String? actorActionIcon;

  /// Raw icon classes from API, e.g. `fas fa-bell` (matches Backoffice `icon`).
  final String? iconClass;

  Notification({
    required this.id,
    required this.title,
    required this.message,
    required this.type,
    required this.isRead,
    required this.createdAt,
    this.metadata,
    this.relatedUrl,
    this.priority = 'normal',
    this.notificationTypeLabel,
    this.entityName,
    this.entityType,
    this.primaryIsMessage = false,
    this.actor,
    this.actorActionIcon,
    this.iconClass,
  });

  factory Notification.fromJson(Map<String, dynamic> json) {
    return Notification(
      id: json['id'] ?? 0,
      title: json['title'] ?? '',
      message: json['message'] ?? '',
      type: json['notification_type'] ?? json['type'] ?? 'info',
      isRead: json['is_read'] ?? false,
      createdAt: json['created_at'] != null
          ? DateTime.parse(json['created_at'])
          : DateTime.now(),
      metadata: json['metadata'] ?? {},
      relatedUrl: json['related_url'] ?? json['redirect_url'],
      priority: json['priority'] ?? 'normal',
      notificationTypeLabel: json['notification_type_label'],
      entityName: json['entity_name'],
      entityType: json['entity_type'],
      primaryIsMessage: json['primary_is_message'] == true,
      actor: json['actor'] != null && json['actor'] is Map<String, dynamic>
          ? NotificationActor.fromJson(json['actor'] as Map<String, dynamic>)
          : null,
      actorActionIcon: json['actor_action_icon']?.toString(),
      iconClass: json['icon']?.toString(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'title': title,
      'message': message,
      'type': type,
      'is_read': isRead,
      'created_at': createdAt.toIso8601String(),
      'metadata': metadata,
      'related_url': relatedUrl,
      'priority': priority,
      'notification_type_label': notificationTypeLabel,
      'entity_name': entityName,
      'entity_type': entityType,
      'primary_is_message': primaryIsMessage,
      'actor': actor?.toJson(),
      'actor_action_icon': actorActionIcon,
      'icon': iconClass,
    };
  }

  Notification copyWith({
    int? id,
    String? title,
    String? message,
    String? type,
    bool? isRead,
    DateTime? createdAt,
    Map<String, dynamic>? metadata,
    String? relatedUrl,
    String? priority,
    String? notificationTypeLabel,
    String? entityName,
    String? entityType,
    bool? primaryIsMessage,
    NotificationActor? actor,
    String? actorActionIcon,
    String? iconClass,
  }) {
    return Notification(
      id: id ?? this.id,
      title: title ?? this.title,
      message: message ?? this.message,
      type: type ?? this.type,
      isRead: isRead ?? this.isRead,
      createdAt: createdAt ?? this.createdAt,
      metadata: metadata ?? this.metadata,
      relatedUrl: relatedUrl ?? this.relatedUrl,
      priority: priority ?? this.priority,
      notificationTypeLabel:
          notificationTypeLabel ?? this.notificationTypeLabel,
      entityName: entityName ?? this.entityName,
      entityType: entityType ?? this.entityType,
      primaryIsMessage: primaryIsMessage ?? this.primaryIsMessage,
      actor: actor ?? this.actor,
      actorActionIcon: actorActionIcon ?? this.actorActionIcon,
      iconClass: iconClass ?? this.iconClass,
    );
  }

  bool get isHighPriority => priority == 'high' || priority == 'urgent';

  /// Legacy emoji icon for types without API icon (unused in new tile UI).
  String get icon {
    switch (type) {
      case 'assignment':
        return '📋';
      case 'approval':
        return '✅';
      case 'revision':
        return '⚠️';
      case 'deadline':
        return '⏰';
      default:
        return '🔔';
    }
  }
}
