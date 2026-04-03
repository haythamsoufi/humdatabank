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
  final String? notificationTypeLabel; // Localized notification type label
  final String? entityName; // Localized entity (country/NS branch) name
  final String? entityType; // Entity type ('country', 'ns_branch', etc.)

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
    };
  }

  bool get isHighPriority => priority == 'high' || priority == 'urgent';

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
