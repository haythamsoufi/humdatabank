/// Notification type values accepted by the mobile API `type` query parameter
/// (matches Backoffice `NotificationType`).
const List<String> kNotificationFilterTypeValues = [
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
  'admin_message',
  'access_request_received',
];

String formatNotificationTypeCode(String code) {
  if (code.isEmpty) return code;
  return code
      .split('_')
      .map((w) => w.isEmpty ? w : '${w[0].toUpperCase()}${w.substring(1)}')
      .join(' ');
}
