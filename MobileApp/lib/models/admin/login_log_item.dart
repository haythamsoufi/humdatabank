/// One row from [GET /admin/api/analytics/login-logs].
class LoginLogItem {
  const LoginLogItem({
    required this.id,
    required this.timestampIso,
    required this.eventType,
    required this.emailAttempted,
    this.userName,
    this.userEmail,
    required this.ipAddress,
    this.location,
    this.browser,
    this.deviceType,
    this.userAgent,
    required this.isSuspicious,
    this.failureReason,
    this.failureReasonDisplay,
    required this.failedAttemptsCount,
  });

  final int id;
  final String timestampIso;
  final String eventType;
  final String emailAttempted;
  final String? userName;
  final String? userEmail;
  final String ipAddress;
  final String? location;
  final String? browser;
  final String? deviceType;
  final String? userAgent;
  final bool isSuspicious;
  final String? failureReason;
  final String? failureReasonDisplay;
  final int failedAttemptsCount;

  factory LoginLogItem.fromJson(Map<String, dynamic> json) {
    final user = json['user'];
    String? uname;
    String? uemail;
    if (user is Map<String, dynamic>) {
      uname = user['name']?.toString();
      uemail = user['email']?.toString();
    }
    return LoginLogItem(
      id: json['id'] is int ? json['id'] as int : int.parse('${json['id']}'),
      timestampIso: json['timestamp']?.toString() ?? '',
      eventType: json['event_type']?.toString() ?? '',
      emailAttempted: json['email_attempted']?.toString() ?? '',
      userName: uname,
      userEmail: uemail,
      ipAddress: json['ip_address']?.toString() ?? '',
      location: json['location']?.toString(),
      browser: json['browser']?.toString(),
      deviceType: json['device_type']?.toString(),
      userAgent: json['user_agent']?.toString(),
      isSuspicious: json['is_suspicious'] == true,
      failureReason: json['failure_reason']?.toString(),
      failureReasonDisplay: json['failure_reason_display']?.toString(),
      failedAttemptsCount: json['failed_attempts_count'] is int
          ? json['failed_attempts_count'] as int
          : int.tryParse('${json['failed_attempts_count'] ?? 0}') ?? 0,
    );
  }
}
