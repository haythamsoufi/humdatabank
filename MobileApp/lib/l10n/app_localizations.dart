import 'package:flutter/material.dart';

/// App-specific localizations for the IFRC Network Databank app
class AppLocalizations {
  final Locale locale;

  AppLocalizations(this.locale);

  static AppLocalizations? of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations);
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  // Translation maps
  static const Map<String, Map<String, String>> _translations = {
    'en': {
      // App
      'app_name': 'IFRC Network Databank',

      // Navigation
      'navigation': 'Navigation',
      'home': 'Home',
      'dashboard': 'Dashboard',
      'resources': 'Resources',
      'indicator_bank': 'Indicator Bank',
      'disaggregation_analysis': 'Disaggregation Analysis',
      'analysis': 'Analysis',
      'data_visualization': 'Data Visualization',
      'settings': 'Settings',
      'notifications': 'Notifications',
      'admin': 'Admin',
      'admin_panel': 'Admin Panel',
      'customize_tabs': 'Customize Tabs',
      'customize_tabs_description': 'Select which tabs to show and drag to reorder them.',
      'reset_to_default': 'Reset to Default',
      'tab_always_shown': 'Always shown',
      'minimum_tabs_warning': 'You must keep at least 2 tabs visible.',
      'access_denied': 'Access Denied',
      'general': 'General',
      'document_management': 'Document Management',
      'translation_management': 'Translation Management',
      'plugin_management': 'Plugin Management',
      'system_configuration': 'System Configuration',
      'user_management': 'User Management',
      'manage_users': 'Manage Users',
      'access_requests_title': 'Country access requests',
      'access_requests_subtitle':
          'Approve or reject requests for country-level access.',
      'access_requests_pending': 'Pending',
      'access_requests_processed': 'Recent decisions',
      'access_requests_empty': 'No access requests.',
      'access_requests_approve': 'Approve',
      'access_requests_reject': 'Reject',
      'access_requests_approve_all': 'Approve all',
      'access_requests_approve_all_confirm':
          'Approve all pending country access requests?',
      'access_requests_reject_confirm':
          'Reject this access request? The user will not be granted access.',
      'access_requests_country': 'Country',
      'access_requests_message': 'Message',
      'access_requests_requested_at': 'Requested',
      'access_requests_processed_at': 'Processed',
      'access_requests_auto_approve_hint':
          'Automatic approval may be enabled in server settings.',
      'access_requests_status_pending': 'Pending',
      'access_requests_status_approved': 'Approved',
      'access_requests_status_rejected': 'Rejected',
      'access_requests_by': 'By',
      'access_requests_load_failed': 'Could not load access requests.',
      'access_requests_action_failed': 'Action could not be completed.',
      'access_requests_view_forbidden':
          'You do not have permission to view access requests on the server.',
      'access_requests_unexpected_response': 'Unexpected response from server.',
      'access_requests_action_forbidden':
          'You do not have permission for this action.',
      'users_directory_read_only':
          'This directory is read-only. Create or change accounts in the web backoffice.',
      'login_logs_title': 'Login Logs',
      'login_logs_filters': 'Filters',
      'login_logs_email_hint': 'Search by email',
      'login_logs_event_type': 'Event type',
      'login_logs_event_all': 'All types',
      'login_logs_event_login': 'Login',
      'login_logs_event_logout': 'Logout',
      'login_logs_event_failed': 'Failed login',
      'login_logs_ip_label': 'IP address',
      'login_logs_date_from': 'From date',
      'login_logs_date_to': 'To date',
      'login_logs_suspicious_only': 'Suspicious only',
      'login_logs_apply': 'Apply',
      'login_logs_clear': 'Clear',
      'login_logs_no_entries': 'No login events match your filters.',
      'login_logs_total': '%s events total',
      'login_logs_load_more': 'Load more',
      'login_logs_user_not_resolved': 'No matching user account',
      'login_logs_device': 'Device',
      'login_logs_browser': 'Browser',
      'login_logs_suspicious_badge': 'Suspicious',
      'login_logs_recent_failures': '%s recent failures',
      'login_logs_open': 'Login logs',
      'session_logs_title': 'Session Logs',
      'admin_filters': 'Filters',
      'session_logs_email_hint': 'Search by email',
      'session_logs_min_duration': 'Min minutes (session or active)',
      'session_logs_active_only': 'Active sessions only',
      'admin_filters_apply': 'Apply',
      'admin_filters_clear': 'Clear',
      'session_logs_no_entries': 'No sessions match your filters.',
      'session_logs_total': '%s sessions total',
      'session_logs_load_more': 'Load more',
      'session_logs_session_start': 'Session start',
      'session_logs_duration': 'Duration',
      'session_logs_session_length': 'Session length',
      'session_logs_active_time': 'Active time',
      'session_logs_minutes': '%s min',
      'session_logs_page_views': 'Page views',
      'session_logs_path_breakdown_title': 'Page views by path',
      'session_logs_path_breakdown_open': 'View path breakdown',
      'session_logs_path_breakdown_empty':
          'No path breakdown recorded for this session.',
      'session_logs_path_other_bucket': 'Other paths (aggregated)',
      'session_logs_path_column': 'Path',
      'session_logs_path_count_column': 'Count',
      'session_logs_distinct_paths': 'Distinct paths',
      'session_logs_activities': 'Activities',
      'session_logs_last_activity': 'Last activity',
      'session_logs_status_active': 'Active',
      'session_logs_status_ended': 'Ended',
      'session_logs_force_logout': 'Force logout',
      'session_logs_force_logout_confirm':
          'Force logout this user? They will be logged out immediately.',
      'session_logs_unknown_user': 'Unknown user',
      'session_logs_no_activity': 'No activity',
      'session_logs_open': 'Session logs',
      'session_logs_ended_ok': 'Session ended.',
      'session_logs_os': 'OS',
      'session_logs_user_agent': 'User agent',
      'session_logs_device_section': 'Device details',
      'form_data_management': 'Form & Data Management',
      'manage_templates': 'Manage Templates',
      'manage_assignments': 'Manage Assignments',
      'assignment_details': 'Assignment details',
      'assignment_reporting_period': 'Reporting period',
      'assignment_template_id': 'Template ID',
      'assignment_has_public_link': 'Public link available',
      'assignment_detail_missing_data':
          'Open this assignment from the assignments list.',
      'copy_link': 'Copy link',
      'assignment_schedule_section': 'Schedule & deadlines',
      'assignment_state_section': 'Assignment status',
      'assignment_expiry_date': 'Assignment expiry',
      'assignment_earliest_entity_due': 'Earliest entity due date',
      'assignment_multiple_due_dates_hint':
          'Entities use different due dates; check each entity below.',
      'assignment_flag_active': 'Assignment active',
      'assignment_flag_closed': 'Marked closed',
      'assignment_flag_effective_closed': 'Closed (incl. past expiry)',
      'assignment_load_detail_failed': 'Could not load full details.',
      'assignment_closed': 'Closed',
      'assignment_open': 'Open',
      'entity_public_reporting': 'Public reporting available',
      'entity_submitted_at': 'Submitted',
      'frontend_management': 'Website Management',
      'manage_resources': 'Manage Resources',
      'reference_data': 'Reference Data',
      'organizational_structure': 'Organizational Structure',
      'analytics_monitoring': 'Analytics & Monitoring',
      'user_analytics': 'User Analytics',
      'audit_trail': 'Audit Trail',
      'api_management': 'API Management',

      // Settings
      'account_settings': 'Account Settings',
      'profile': 'Profile',
      'preferences': 'Preferences',
      'language': 'Language',
      'select_language': 'Select Language',
      'change_password': 'Change Password',
      'profile_color': 'Profile Color',
      'chatbot': 'Chatbot',
      'enable_chatbot_assistance': 'Enable chatbot assistance',
      'dark_theme': 'Dark Theme',
      'enable_dark_theme': 'Enable dark theme',
      'settings_theme': 'Theme',
      'light_theme': 'Light Theme',
      'system_theme': 'System',
      'select_theme': 'Select theme',
      'arabic_text_font': 'Arabic text font',
      'arabic_font_tajawal': 'Tajawal',
      'arabic_font_system': 'System default',
      'login_to_account': 'Login to Account',
      'logout': 'Logout',
      'are_you_sure_logout': 'Are you sure you want to logout?',
      'cancel': 'Cancel',

      // Common
      'name': 'Name',
      'title': 'Title',
      'email': 'Email',
      'loading': 'Loading...',
      'loading_home': 'Loading Home...',
      'home_landing_hero_description':
          'Explore comprehensive humanitarian data, indicators, and insights from the International Federation of Red Cross and Red Crescent Societies.',
      'home_landing_chat_title': 'Chat with our data',
      'home_landing_chat_description': 'Type your questions about our data below.',
      'home_landing_ask_placeholder': 'Ask about funding, programs, countries...',
      'home_landing_quick_prompt_1': 'Tell me about Afghan Red Crescent volunteers',
      'home_landing_quick_prompt_2': 'Show me global disaster response data',
      'home_landing_quick_prompt_3': 'What are the key humanitarian indicators?',
      'home_landing_shortcuts_heading': 'Get started',
      'home_landing_shortcut_indicators_subtitle': 'Browse definitions and metadata',
      'home_landing_shortcut_resources_subtitle': 'Publications and materials',
      'home_landing_shortcut_countries_subtitle': 'Profiles and regional views',
      'home_landing_shortcut_disaggregation_subtitle': 'Break down indicator values',
      'home_landing_explore_title': 'Global map & charts',
      'home_landing_explore_subtitle':
          'Native map and chart using the same FDRS totals as the website — without leaving the app.',
      'home_landing_global_indicator_volunteers': 'Volunteers',
      'home_landing_global_indicator_staff': 'Staff',
      'home_landing_global_indicator_branches': 'Branches',
      'home_landing_global_indicator_local_units': 'Local units',
      'home_landing_global_indicator_blood_donors': 'Blood donors',
      'home_landing_global_indicator_first_aid': 'First aid',
      'home_landing_global_indicator_people_reached': 'People reached',
      'home_landing_global_indicator_income': 'Income',
      'home_landing_global_indicator_expenditure': 'Expenditure',
      'home_landing_global_top_countries': 'Top countries',
      'home_landing_global_load_error':
          'Could not load map data. Check your connection and try again.',
      'home_landing_global_empty':
          'No values for this indicator in the latest period.',
      'home_landing_global_period': 'Period: %s',
      'home_landing_global_map_hint':
          'Pinch, drag, and tap a country for details',
      'home_landing_global_map_open_fullscreen': 'Full screen',
      'home_landing_global_period_filter_label': 'Reporting period',
      'home_landing_global_map_mode_bubble': 'Bubbles',
      'home_landing_global_map_mode_choropleth': 'Choropleth',
      'home_landing_global_map_zoom_in': 'Zoom in',
      'home_landing_global_map_zoom_out': 'Zoom out',
      'home_landing_global_map_reset_bounds': 'Fit data',
      'home_landing_global_map_legend_low': 'Low',
      'home_landing_global_map_legend_high': 'High',
      'home_landing_global_map_country_no_data': 'No data for this indicator',
      'home_landing_global_map_value_label': 'Value',
      'home_landing_global_map_country_trend': 'By reporting period',
      'home_landing_global_map_filters_title': 'Map options',
      'loading_page': 'Loading page...',
      'loading_preferences': 'Loading preferences...',
      'loading_notifications': 'Loading notifications...',
      'loading_dashboard': 'Loading dashboard...',
      'loading_audit_logs': 'Loading audit logs...',
      'loading_analytics': 'Loading analytics...',
      'loading_organizations': 'Loading organizations...',
      'loading_templates': 'Loading templates...',
      'loading_assignments': 'Loading assignments...',
      'loading_translations': 'Loading translations...',
      'loading_plugins': 'Loading plugins...',
      'loading_resources': 'Loading resources...',
      'loading_indicators': 'Loading indicators...',
      'loading_documents': 'Loading documents...',
      'loading_api_endpoints': 'Loading API endpoints...',
      'loading_users': 'Loading users...',
      'error_loading_page': 'Error loading page',
      'error': 'Error',
      'retry': 'Retry',
      'refresh': 'Refresh',
      'close': 'Close',
      'save': 'Save',
      'saved': 'Saved',
      'success': 'Success',
      'oops_something_went_wrong': 'Oops! Something went wrong',
      'go_back': 'Go Back',
      'edit': 'Edit',
      'duplicate': 'Duplicate',
      'preview': 'Preview',
      'download_started': 'Download started',
      'could_not_start_download': 'Could not start download',
      'could_not_open_download_link': 'Could not open download link',
      'error_opening_download': 'Error opening download',
      'please_select_at_least_one_user': 'Please select at least one user',
      'indicator_updated_successfully': 'Indicator updated successfully',
      'failed_to_load_indicator': 'Failed to load indicator',
      'user_deleted': 'User deleted',
      'public_url_copied': 'Public URL copied to clipboard!',
      'please_use_web_interface': 'Please use the web interface to save entity changes',
      'open_in_web_browser': 'Open in Web Browser',
      'countries': 'Countries',
      'all_roles': 'All Roles',
      'admin_role': 'Administrator',
      'focal_point_role': 'Focal Point',
      'system_manager_role': 'System Manager',
      'viewer_role': 'Viewer',
      'all_status': 'All Status',
      'active_status': 'Active',
      'inactive_status': 'Inactive',
      'normal_priority': 'Normal',
      'high_priority': 'High',
      'none': 'None',
      'app_screen': 'App Screen',
      'custom_url': 'Custom URL',
      'create_template': 'Create Template',
      'delete_template': 'Delete Template',
      'create_assignment': 'Create Assignment',
      'delete_assignment': 'Delete Assignment',
      'edit_document': 'Edit Document',
      'preview_document': 'Preview Document',
      'download_document': 'Download Document',
      'upload_document': 'Upload Document',
      'new_translation': 'New Translation',
      'new_resource': 'New Resource',
      'install_plugin': 'Install Plugin',
      'template_deleted_successfully': 'Template deleted successfully',
      'failed_to_delete_template': 'Failed to delete template',

      // Notifications
      'no_notifications': 'No notifications',
      'all_caught_up': 'You\'re all caught up',
      'notifications_load_more': 'Load more',
      'notifications_filter': 'Filters',
      'notifications_filter_title': 'Filter notifications',
      'notifications_filter_read_status': 'Read status',
      'notifications_filter_all': 'All',
      'notifications_filter_unread_only': 'Unread only',
      'notifications_filter_type': 'Notification type',
      'notifications_filter_type_any': 'All types',
      'notifications_filter_from': 'From',
      'notifications_filter_from_any': 'Anyone',
      'notifications_filter_from_empty_hint':
          'People appear here when their notifications are in the loaded list. Use Load more to find others.',
      'notifications_filter_priority': 'Priority',
      'notifications_filter_priority_any': 'Any priority',
      'notifications_filter_priority_normal': 'Normal',
      'notifications_filter_priority_high': 'High',
      'notifications_filter_priority_urgent': 'Urgent',
      'notifications_filter_apply': 'Apply',
      'notifications_filter_reset': 'Reset all',
      'notifications_filter_no_matches_loaded':
          'No notifications match these filters in the loaded list. Load more or adjust filters.',
      'mark_all_read': 'Mark all as read',
      'mark_read': 'Mark as read',
      'mark_unread': 'Mark as unread',
      'delete': 'Delete',
      'archive': 'Archive',
      'unarchive': 'Unarchive',
      'send_push_notification': 'Send Push Notification',
      'admin_push_user_ids_label': 'Recipient user IDs',
      'admin_push_user_ids_hint':
          'Comma-separated numeric IDs (from Manage Users).',
      'admin_push_user_ids_invalid':
          'Enter one or more numeric user IDs, separated by commas.',
      'select_users': 'Select Users',
      'search_users': 'Search users by name or email',
      'message': 'Message',
      'redirect_url': 'Redirect (Optional)',
      'send': 'Send',

      // Login
      'login': 'Login',
      'log_in': 'Log In',
      'email_address': 'Email Address',
      'phone_username_email': 'Phone number, username, or email',
      'password': 'Password',
      'remember_me': 'Remember me',
      'forgot_password': 'Forgot password?',
      'forgot_password_coming_soon': 'Forgot password feature coming soon',
      'please_enter_email': 'Please enter your email',
      'please_enter_valid_email': 'Please enter a valid email',
      'please_enter_password': 'Please enter your password',
      'current_password': 'Current Password',
      'new_password': 'New Password',
      'confirm_password': 'Confirm Password',
      'enter_current_password': 'Enter your current password',
      'enter_new_password': 'Enter your new password',
      'confirm_new_password': 'Confirm your new password',
      'passwords_do_not_match': 'Passwords do not match',
      'password_changed_successfully': 'Password changed successfully',
      'password_change_failed': 'Failed to change password',
      'show': 'Show',
      'hide': 'Hide',
      'or': 'OR',
      'dont_have_account': "Don't have an account?",
      'sign_up': 'Sign up',
      'registration_coming_soon': 'Registration feature coming soon',
      'quick_login_testing': 'Quick Login for Testing',
      'test_as_admin': 'Test as Admin',
      'test_as_focal_point': 'Test as Focal Point',
      'public_login_disabled': 'Public login is temporarily disabled',
      'tester_accounts_info':
          'Tester accounts can still sign in using the buttons above.',
      'could_not_open_azure_login': 'Could not open Azure login',
      'login_with_ifrc_account': 'Login with IFRC Account',
      'use_ifrc_federation_account':
          'Use your IFRC Federation Account to sign in',
      'your_account_or_create_account': 'Your account or create an account',
      'login_failed': 'Login failed',

      // Messages
      'language_changed_to': 'Language changed to',

      // Splash Screen
      'welcome_to_ifrc_network_databank':
          'Welcome to the IFRC Network Databank',
      'splash_description':
          'This is the one and only system for reporting data to IFRC. Say goodbye to scattered Excel files, KoBo forms, multiple platforms, and logins — everything is now centralized and streamlined here.',
      'powered_by_hum_databank': 'Powered by Humanitarian Databank',
      'open_on_github': 'Open on GitHub',

      // Dashboard
      'national_society': 'National Society',
      'active': 'Active',
      'completed': 'Completed',
      'current_assignments': 'Current Assignments',
      'dashboard_you_have_no_open_assignments': 'You have no open assignments',
      'dashboard_you_have_one_open_assignment': 'You have 1 open assignment',
      'dashboard_you_have_open_assignments_count': 'You have %s open assignments',
      'past_assignments': 'Past Assignments',
      'assignments_for': 'Assignments for',
      'past_submissions_for': 'Past Submissions for',
      'something_went_wrong': 'Something went wrong',
      'no_assignments_yet': 'All clear! No active assignments at this time.',
      'new_assignments_will_appear':
          'New assignments will appear here when available.',
      'get_started_by_creating': 'Get started by creating a new assignment',
      'filters': 'Filters',
      'period': 'Period',
      'template': 'Template',
      'status': 'Status',
      'clear': 'Clear',
      'approved': 'Approved',
      'requires_revision': 'Requires Revision',
      'pending': 'Pending',
      'in_progress': 'In Progress',
      'submitted': 'Submitted',
      'other': 'Other',
      'entities': 'Entities',
      'search_placeholder': 'Search...',
      'no_results_found': 'No results found',
      'entity_type_country': 'Country',
      'entity_type_ns_branch': 'NS Branch',
      'entity_type_ns_sub_branch': 'NS Sub-Branch',
      'entity_type_ns_local_unit': 'NS Local Unit',
      'entity_type_division': 'Division',
      'entity_type_department': 'Department',
      'delete_assignment_confirm_message':
          'Are you sure you want to delete this assignment and all its associated country statuses and data?',
      'no_assignments_match_filters':
          'No assignments match the selected filters',
      'form': 'Form',
      'last_updated': 'Last Updated',
      'actions': 'Actions',
      'all_years': 'All Years',
      'all_templates': 'All Templates',
      'all_statuses': 'All Statuses',
      'template_missing': 'Template Missing',
      'self_reported': 'Self-Reported',
      'no_actions_available': 'No actions available',
      'previous': 'Previous',
      'next': 'Next',
      'showing': 'Showing',
      'to': 'to',
      'of': 'of',
      'results': 'results',
      'no_past_assignments_for': 'No past assignments for',
      'yet': 'yet.',
      'submission_history_and_data_quality_for':
          'Submission History and Data Quality for',
      'overall_performance': 'Overall Performance',
      'average_completion_rate_past_3_periods':
          'Average Completion Rate (Past 3 Periods)',
      'average_submission_timeliness':
          'Average Submission Timeliness (Days Early/Late)',
      'data_quality_index_fake_metric': 'Data Quality Index (Fake Metric)',
      'number_of_revisions_requested_past_year':
          'Number of Revisions Requested (Past Year)',
      'trend_analysis': 'Trend Analysis',
      'recent_activities': 'Recent Activities',
      'last_7_days': 'Last 7 days',
      'unknown_user': 'Unknown User',
      'added': 'Added',
      'updated': 'Updated',
      'removed': 'Removed',
      'show_less': 'Show less',
      'more_change': 'more change',
      'no_recent_activities': 'No recent activities',
      'activities_from_other_focal_points_in':
          'Activities from other focal points in',
      'will_appear_here': 'will appear here',
      'focal_points_for': 'Focal Points for',
      'national_society_focal_points': 'National Society Focal Points',
      'ifrc_focal_points': 'IFRC Focal Points',
      'no_focal_points_assigned_to': 'No focal points assigned to',
      'your_user_account_not_associated':
          'Your user account is not associated with any countries.',
      'please_contact_administrator': 'Please contact an administrator.',
      'due_date': 'Due Date',
      'no_due_date': 'No due date',
      'overdue': 'Overdue',
      'latest_submission': 'Latest Submission',
      'submitted_through_public_link': 'Submitted through public link',
      'submission': 'submission',
      'submissions': 'submissions',
      'completion': 'Completion',
      'received_1_submission_using_public_link':
          'Received 1 submission using the public link',
      'received_count_submissions_using_public_link':
          'Received %(count)d submissions using the public link',
      'at_datetime': 'at: %(datetime)s',
      'latest_datetime': 'Latest: %(datetime)s',
      'last_modified_by': 'Last modified by',
      'assignment_assigned_date': 'Assigned',
      'assignment_status_updated': 'Status updated',
      'contributors': 'Contributors',
      'assignment_submitted_by': 'Submitted by',
      'assignment_approved_by': 'Approved by',
      'public_link_enabled': 'Public link enabled',
      'public_link': 'Public link',
      'unknown': 'Unknown',
      'n_a': 'N/A',
      'enter_data': 'Enter Data',
      'download_for_offline': 'Download for offline',
      'downloading_offline_form': 'Downloading form for offline use…',
      'offline_form_saved': 'Form saved for offline access.',
      'offline_form_save_failed': 'Could not save the form offline. Try again when you have a stable connection.',
      'offline_form_not_downloaded': 'This form is not available offline. Download it while you are online.',
      'offline_download_requires_connection': 'Connect to the internet to download this form for offline use.',
      'offline_form_export_requires_connection':
          'Connect to the internet to export PDF, Excel, or validation reports. The offline copy does not include exports.',
      'offline_open_saved_copy': 'Open saved offline copy',
      'remove_offline_copy': 'Remove offline copy',
      'offline_form_removed': 'Offline copy removed. Download again when online.',
      'offline_saved_copy_details_tooltip':
          'Offline copy — details and remove',
      'offline_copy_sheet_title': 'Offline form copy',
      'offline_copy_saved_on_label': 'Saved on',
      'offline_copy_files_cached': '%(count)d cached resources',
      'offline_stale_bundle_banner_title': 'Offline forms need updating',
      'offline_stale_bundle_banner_body_online':
          'The online form changed. Your device refreshes offline copies automatically when connected. If that fails, open each form with the warning badge and tap Update offline copy.',
      'offline_stale_bundle_banner_body_offline':
          'The online form changed. Connect to the internet so your device can refresh offline copies automatically.',
      'offline_stale_bundle_updates_snackbar':
          'Offline copies were updated to the latest version.',
      'offline_stale_bundle_partial_refresh':
          'Some offline copies could not be updated. Tap the warning badge on a form, then Update offline copy.',
      'offline_stale_bundle_sheet_notice':
          'This offline copy may not match the current online form. Update it to avoid version issues.',
      'offline_stale_bundle_update_now': 'Update offline copy',
      'approve': 'Approve',
      'reopen': 'Reopen',
      'view_public_submissions': 'View Public Submissions',
      'view_submission': 'View Submission',
      'view_submissions': 'View Submissions',
      'open_form': 'Open Form',
      'no_forms_assigned_or_submitted_for':
          'No forms have been assigned or submitted via public links for',
      'admins_can_assign_forms':
          'Admins can assign forms or create public links via the Admin Dashboard.',
      'create_a_report': 'Create a Report',
      'delete_self_reported_assignment': 'Delete Self-Reported Assignment',
      'quick_actions': 'Quick Actions',
      'new_assignment': 'New Assignment',
      'new_template': 'New Template',
      'key_metrics': 'Key Metrics',
      'overview': 'Overview',
      'create_new_assignment': 'Create a new assignment',
      'browse_available_templates': 'Browse available templates',
      'enter_your_name': 'Enter your name',
      'enter_your_job_title': 'Enter your job title',
      'edit_name': 'Edit Name',
      'edit_title': 'Edit Title',
      'name_cannot_be_empty': 'Name cannot be empty',
      'title_cannot_be_empty': 'Title cannot be empty',
      'profile_updated_successfully': 'Profile updated successfully',
      'error_updating_profile': 'Error updating profile',
      'color_picker_coming_soon': 'Color picker coming soon',
      'chatbot_preference_update_coming_soon':
          'Chatbot preference update coming soon',
      'select_color': 'Select a color',
      'current_color': 'Current Color',
      'profile_color_updated': 'Profile color updated successfully',
      'profile_color_update_failed': 'Failed to update profile color',
      'admin_dashboard': 'Admin Dashboard',
      'no_data_available': 'No data available',
      'total_users': 'Total Users',
      'admins': 'Admins',
      'system_administrators': 'System administrators',
      'focal_points': 'Focal Points',
      'country_focal_points': 'Country focal points',
      'templates': 'Templates',
      'form_templates': 'Form templates',
      'assignments': 'Assignments',
      'active_assignments': 'Active assignments',
      'todays_logins': 'Today\'s Logins',
      'successful_logins_today': 'Successful logins today',
      'pending_submissions': 'Pending Submissions',
      'overdue_assignments': 'Overdue Assignments',
      'security_alerts': 'Security Alerts',
      'successful_logins': 'Successful Logins',
      'user_activities': 'User Activities',
      'active_sessions': 'Active Sessions',
      'all_notifications_marked_as_read': 'All notifications marked as read',
      'mark_as_read': 'Mark as read',
      'mark_as_unread': 'Mark as unread',
      'notification_preferences': 'Notification Preferences',
      'sound_notifications': 'Sound Notifications',
      'email_frequency': 'Email Frequency',
      'instant': 'Instant',
      'daily_digest': 'Daily Digest',
      'weekly_digest': 'Weekly Digest',
      'digest_schedule': 'Digest Schedule',
      'day_of_week': 'Day of Week',
      'monday': 'Monday',
      'tuesday': 'Tuesday',
      'wednesday': 'Wednesday',
      'thursday': 'Thursday',
      'friday': 'Friday',
      'saturday': 'Saturday',
      'sunday': 'Sunday',
      'time_local_time': 'Time (Local Time)',
      'notification_types': 'Notification Types',
      'preferences_saved_successfully': 'Preferences saved successfully',
      'enable_sound': 'Enable Sound',
      'play_sound_for_new_notifications': 'Play sound for new notifications',
      'configure_notification_types_description': 'Configure which notification types to receive via email and push notifications',
      'notification_type': 'Notification Type',
      'push': 'Push',
      'all': 'All',
      'save_preferences': 'Save Preferences',
      'select_digest_time_description': 'Select the time when you want to receive your digest',
      'failed_to_save_preferences': 'Failed to save preferences',
      'assignment_created': 'Assignment Created',
      'assignment_submitted': 'Assignment Submitted',
      'assignment_approved': 'Assignment Approved',
      'assignment_reopened': 'Assignment Reopened',
      'public_submission_received': 'Public Submission Received',
      'form_updated': 'Form Updated',
      'document_uploaded': 'Document Uploaded',
      'user_added_to_country': 'User Added To Country',
      'template_updated': 'Template Updated',
      'self_report_created': 'Self Report Created',
      'deadline_reminder': 'Deadline Reminder',
      'search_audit_logs': 'Search audit logs...',
      'audit_trail_no_entries': 'No activity matches your filters.',
      'audit_trail_activity_label': 'Activity',
      'home_screen_widget_title': 'Home screen widget',
      'audit_widget_activity_types_hint':
          'Choose activity types for the widget. Leave all unchecked to show every type. Saved on this device.',
      'action': 'Action',
      'all_actions': 'All Actions',
      'create': 'Create',
      'update': 'Update',
      'user': 'User',
      'all_users': 'All Users',
      'from_date': 'From Date',
      'to_date': 'To Date',
      'select_date': 'Select date',
      'no_description': 'No description',
      'search_api_endpoints': 'Search API endpoints...',
      'http_method': 'HTTP Method',
      'all_methods': 'All Methods',
      'get': 'GET',
      'post': 'POST',
      'put': 'PUT',
      'delete_method': 'DELETE',
      'api_status': 'Status',
      'api_active': 'Active',
      'deprecated': 'Deprecated',
      'beta': 'Beta',
      'new_api_key': 'New API Key',
      'time_range': 'Time Range',
      'last_30_days': 'Last 30 Days',
      'last_90_days': 'Last 90 Days',
      'last_year': 'Last Year',
      'all_time': 'All Time',
      'metric': 'Metric',
      'all_metrics': 'All Metrics',
      'active_users': 'Active Users',
      'logins': 'Logins',
      'metric_submissions': 'Submissions',
      'page_views': 'Page Views',
      'search_indicators': 'Search indicators...',
      'category': 'Category',
      'all_categories': 'All Categories',
      'output': 'Output',
      'outcome': 'Outcome',
      'impact': 'Impact',
      'sector': 'Sector',
      'all_sectors': 'All Sectors',
      'health': 'Health',
      'wash': 'WASH',
      'shelter': 'Shelter',
      'education': 'Education',
      'indicators': 'Indicators',
      'new_indicator': 'New Indicator',
      'search_organizations': 'Search organizations...',
      'entity_type': 'Entity Type',
      'all_types': 'All Types',
      'national_societies': 'National Societies',
      'ns_structure': 'NS Structure',
      'secretariat': 'Secretariat',
      'divisions': 'Divisions',
      'departments': 'Departments',
      'regional_offices': 'Regional Offices',
      'cluster_offices': 'Cluster Offices',
      'add_organization': 'Add Organization',
      'add_user': 'Add User',
      'search_resources': 'Search resources...',
      'search_documents': 'Search documents...',
      'search_translations': 'Search translations...',
      'search_plugins': 'Search plugins...',
      'type': 'Type',
      'inactive': 'Inactive',
      'publication': 'Publication',
      'resource': 'Resource',
      'document': 'Document',
      'no_indicators_found': 'No indicators found',
      'no_organizations_found': 'No organizations found',
      'no_resources_found': 'No resources found',
      'resources_unified_planning_section_title': 'Unified plans and reports',
      'resources_unified_planning_section_subtitle':
          'Plans, mid-year reports, and annual reports from IFRC GO (loaded in the app).',
      'unified_planning_empty': 'No unified planning documents match your search.',
      'unified_planning_fresh_badge': 'Fresh',
      'unified_planning_sort_by': 'Sort by',
      'unified_planning_sort_date_newest': 'Publish date: newest first',
      'unified_planning_sort_date_oldest': 'Publish date: oldest first',
      'unified_planning_sort_country_az': 'Country: A–Z',
      'unified_planning_sort_country_za': 'Country: Z–A',
      'unified_planning_filter_all_countries': 'All Countries',
      'unified_error_config':
          'Could not load unified planning settings from the server. Try again later.',
      'unified_error_credentials':
          'IFRC documents are not available in this app. Contact your administrator.',
      'unified_error_ifrc_auth':
          'Could not access IFRC documents. Contact your administrator if this continues.',
      'unified_error_ifrc':
          'Could not load documents from IFRC GO. Check your connection and try again.',
      'unified_planning_analytics_title': 'Plans & reports overview',
      'unified_planning_analytics_tooltip': 'Overview and statistics',
      'unified_planning_analytics_total': 'Total documents',
      'unified_planning_analytics_countries': 'Countries',
      'unified_planning_analytics_types': 'Document types',
      'unified_planning_analytics_by_year_type': 'Document types by year',
      'unified_planning_analytics_by_country': 'By country',
      'unified_planning_analytics_recent': 'Published in last 3 days',
      'unified_planning_analytics_unknown_year': 'Year not set',
      'unified_planning_analytics_unknown_country': 'Country not set',
      'unified_planning_analytics_unknown_type': 'Type not set',
      'unified_planning_analytics_more': 'And %s more',
      'unified_planning_analytics_filters_tooltip': 'Filters',
      'unified_planning_analytics_filters_title': 'Filters',
      'unified_planning_analytics_filter_years': 'Years',
      'unified_planning_analytics_filter_rounds': 'Rounds (document types)',
      'unified_planning_analytics_filter_all_years': 'All years',
      'unified_planning_analytics_filter_all_rounds': 'All rounds',
      'unified_planning_analytics_filter_reset': 'Reset',
      'unified_planning_analytics_filter_apply': 'Apply',
      'unified_planning_analytics_filter_invalid':
          'Select at least one year (or year not set) and one round, or choose All.',
      'unified_planning_analytics_map_tooltip': 'Participation world map',
      'unified_planning_participation_map_title': 'Participation by country',
      'unified_planning_participation_slots_label':
          '%s year & document type combinations',
      'unified_planning_participation_no_slots':
          'Nothing matches the current filters.',
      'unified_planning_participation_stats': '%s full · %s partial · %s off map',
      'unified_planning_participation_sheet_slots': '%s of %s combinations',
      'unified_planning_participation_sheet_full': 'Full participation',
      'unified_planning_participation_sheet_partial': 'Partial participation',
      'unified_planning_participation_sheet_none': 'No coverage',
      'unified_planning_participation_legend_full': 'Full participation',
      'unified_planning_participation_legend_partial': 'Partial participation',
      'unified_planning_participation_legend_no_data': 'No coverage',
      'no_plugins_found': 'No plugins found',
      'no_translations_found': 'No translations found',
      'no_documents_found': 'No documents found',
      'no_users_found': 'No users found',
      'loading_user_profile': 'Loading user profile…',
      'failed_load_user_profile': 'Could not load this user.',
      'admin_user_detail_confirm_save_title': 'Save changes?',
      'admin_user_detail_confirm_save_message':
          'Update this user\'s profile name, title, status, and preferences.',
      'admin_user_detail_invalid_profile_color':
          'Enter a valid color as #RRGGBB (e.g. #3B82F6).',
      'admin_user_detail_changes_saved': 'Changes saved.',
      'admin_user_detail_save_changes': 'Save changes',
      'admin_user_detail_profile_color_label': 'Profile color',
      'admin_user_detail_profile_color_hint': '#RRGGBB',
      'admin_user_detail_cannot_deactivate_self':
          'You cannot deactivate your own account.',
      'admin_user_detail_matrix_read_only_bundled':
          'Bundled admin roles (full/core/system) — use the web backoffice to change granular area access.',
      'admin_user_detail_rbac_incomplete':
          'Could not build a valid role list. Check area access or try again.',
      'assigned_roles_title': 'Assigned roles',
      'role_type_label': 'Role type',
      'permissions_by_role': 'Permissions by role',
      'all_permissions_union': 'All permissions (from roles)',
      'entity_permissions_title': 'Entity permissions',
      'manage_users_detail_footer':
          'To edit roles, entity access, devices, or notifications, use the web backoffice user form.',
      'no_roles_assigned': 'No RBAC roles assigned.',
      'no_entities_assigned': 'No entity assignments.',
      'entity_permission_unnamed': 'Unnamed',
      'entity_region_other': 'Other region',
      'no_permissions_listed': 'No permissions listed for this role.',
      'user_dir_assignment_roles': 'Assignment roles',
      'user_dir_admin_roles': 'Admin & system roles',
      'user_dir_other_roles': 'Other roles',
      'admin_role_access_area': 'Area',
      'admin_role_access_view': 'View',
      'admin_role_access_manage': 'Manage',
      'admin_role_de_heading': 'Data Explorer',
      'admin_role_de_table': 'Table',
      'admin_role_de_analysis': 'Analysis',
      'admin_role_de_compliance': 'Compliance',
      'admin_role_note_admin_full': 'All admin permissions (bundled role)',
      'admin_role_note_admin_core': 'Core admin essentials (bundled role)',
      'admin_role_other_admin_roles': 'Other admin roles',
      'users_directory_role_all': 'All roles',
      'users_directory_country_all': 'All countries',
      'no_assignments_found': 'No assignments found',
      'no_templates_found': 'No templates found',
      'assignment_deleted_successfully': 'Assignment deleted successfully',
      'failed_to_delete_assignment': 'Failed to delete assignment',
      'timeline_view': 'Timeline View',
      'view_all_public_submissions': 'View All Public Submissions',
      'items_requiring_attention': 'Items Requiring Attention',
      'recent_activity': 'Recent Activity',
      'recent_activity_7_days': 'Recent Activity (7 days)',
      'general_settings': 'General Settings',
      'security_settings': 'Security Settings',
      'system_settings': 'System Settings',
      'application_settings': 'Application Settings',
      'language_settings': 'Language Settings',
      'notification_settings': 'Notification Settings',
      'authentication_settings': 'Authentication Settings',
      'permission_settings': 'Permission Settings',
      'database_settings': 'Database Settings',
      'cloud_storage_settings': 'Cloud Storage Settings',
      'configure_general_application_settings':
          'Configure general application settings',
      'manage_supported_languages_and_translations':
          'Manage supported languages and translations',
      'configure_notification_preferences':
          'Configure notification preferences',
      'configure_authentication_and_authorization':
          'Configure authentication and authorization',
      'manage_user_permissions_and_roles': 'Manage user permissions and roles',
      'configure_database_connections_and_backups':
          'Configure database connections and backups',
      'configure_cloud_storage_and_file_management':
          'Configure cloud storage and file management',

      // Indicator Bank
      'indicator_bank_title': 'Indicator Bank',
      'indicator_bank_loading': 'Loading Indicator Bank...',
      'indicator_bank_error': 'Something went wrong',
      'indicator_bank_search_placeholder': 'Search indicators...',
      'indicator_bank_filter_placeholder': 'Filter indicators...',
      'indicator_bank_browse_description':
          'Browse and search indicators for humanitarian response',
      'indicator_bank_grid_view': 'Grid View',
      'indicator_bank_table_view': 'Table View',
      'indicator_bank_show_filters': 'Show Filters',
      'indicator_bank_hide_filters': 'Hide Filters',
      'indicator_bank_filters': 'Filters',
      'indicator_bank_filter_type': 'Type',
      'indicator_bank_filter_type_all': 'All Types',
      'indicator_bank_filter_sector': 'Sector',
      'indicator_bank_filter_sector_all': 'All Sectors',
      'indicator_bank_filter_subsector': 'Sub-Sector',
      'indicator_bank_filter_subsector_all': 'All Sub-Sectors',
      'indicator_bank_list_tier_also_related': 'Also related',
      'indicator_bank_filter_status': 'Status',
      'indicator_bank_filter_status_active': 'Active Only',
      'indicator_bank_filter_status_all': 'All',
      'indicator_bank_apply_filters': 'Apply Filters',
      'indicator_bank_clear_all': 'Clear All',
      'indicator_bank_showing': 'Showing',
      'indicator_bank_indicators': 'indicators',
      'indicator_bank_indicator': 'indicator',
      'indicator_bank_no_sectors': 'No sectors found',
      'indicator_bank_no_indicators': 'No indicators found',
      'indicator_bank_table_name': 'Name',
      'indicator_bank_table_type': 'Type',
      'indicator_bank_table_sector': 'Sector',
      'indicator_bank_table_subsector': 'Sub-Sector',
      'indicator_bank_table_unit': 'Unit',
      'indicator_bank_propose_new': 'Propose New Indicator',
      'indicator_bank_propose_title': 'Propose New Indicator',
      'indicator_bank_propose_contact_info': 'Contact Information',
      'indicator_bank_propose_your_name': 'Your Name *',
      'indicator_bank_propose_email': 'Email Address *',
      'indicator_bank_propose_indicator_info': 'Indicator Information',
      'indicator_bank_propose_indicator_name': 'Indicator Name *',
      'indicator_bank_propose_definition': 'Definition *',
      'indicator_bank_propose_type': 'Type',
      'indicator_bank_propose_unit': 'Unit of Measurement',
      'indicator_bank_propose_sector': 'Sector',
      'indicator_bank_propose_primary_sector': 'Primary Sector *',
      'indicator_bank_propose_secondary_sector': 'Secondary Sector',
      'indicator_bank_propose_tertiary_sector': 'Tertiary Sector',
      'indicator_bank_propose_subsector': 'Sub-Sector',
      'indicator_bank_propose_primary_subsector': 'Primary Sub-Sector *',
      'indicator_bank_propose_secondary_subsector': 'Secondary Sub-Sector',
      'indicator_bank_propose_tertiary_subsector': 'Tertiary Sub-Sector',
      'indicator_bank_propose_emergency': 'Emergency Context',
      'indicator_bank_propose_related_programs': 'Related Programs',
      'indicator_bank_propose_reason': 'Reason for Proposal *',
      'indicator_bank_propose_additional_notes': 'Additional Notes',
      'indicator_bank_propose_submit': 'Submit Proposal',
      'indicator_bank_propose_thank_you': 'Thank You!',
      'indicator_bank_propose_success':
          'Your indicator proposal has been submitted successfully.',
      'indicator_bank_propose_failed':
          'Failed to submit proposal. Please try again.',
      'indicator_bank_name_required': 'Name is required',
      'indicator_bank_email_required': 'Email is required',
      'indicator_bank_indicator_name_required': 'Indicator name is required',
      'indicator_bank_definition_required': 'Definition is required',
      'indicator_bank_primary_sector_required': 'Primary sector is required',
      'indicator_bank_primary_subsector_required':
          'Primary sub-sector is required',
      'indicator_bank_reason_required': 'Reason is required',

      // Indicator Detail
      'indicator_detail_title': 'Indicator Details',
      'indicator_detail_loading': 'Loading indicator details...',
      'indicator_detail_error': 'Something went wrong',
      'indicator_detail_not_found': 'Indicator not found',
      'indicator_detail_go_back': 'Go Back',
      'indicator_detail_definition': 'Definition',
      'indicator_detail_details': 'Details',
      'indicator_detail_type': 'Type',
      'indicator_detail_unit': 'Unit',
      'indicator_detail_sector': 'Sector',
      'indicator_detail_subsector': 'Sub-Sector',
      'indicator_detail_emergency_context': 'Emergency Context',
      'indicator_detail_related_programs': 'Related Programs',
      'indicator_detail_status': 'Status',
      'indicator_detail_archived': 'Archived',
      'indicator_detail_yes': 'Yes',
      'editIndicator': 'Edit Indicator',

      // Quiz Game
      'quiz_game': 'Quiz Game',
      'quiz_game_title': 'Quiz Game',
      'quiz_game_test_your_knowledge': 'Test your knowledge!',
      'quiz_game_loading': 'Loading quiz...',
      'quiz_game_error': 'Error loading quiz',
      'quiz_game_try_again': 'Try Again',
      'quiz_game_start_quiz': 'Start Quiz',
      'quiz_game_which_sector': 'Which sector does this indicator belong to?',
      'quiz_game_which_subsector': 'Which subsector does this indicator belong to?',
      'quiz_game_definition': 'Definition',
      'quiz_game_no_definition': 'No definition available',
      'quiz_game_correct': 'Correct!',
      'quiz_game_incorrect': 'Incorrect',
      'quiz_game_next_question': 'Next Question',
      'quiz_game_view_results': 'View Results',
      'quiz_game_quiz_complete': 'Quiz Complete!',
      'quiz_game_excellent_work': 'Excellent work!',
      'quiz_game_well_done': 'Well done!',
      'quiz_game_good_effort': 'Good effort!',
      'quiz_game_keep_practicing': 'Keep practicing!',
      'quiz_game_out_of': 'out of',
      'quiz_game_statistics': 'Statistics',
      'quiz_game_correct_answers': 'Correct',
      'quiz_game_incorrect_answers': 'Incorrect',
      'quiz_game_total': 'Total',
      'quiz_game_home': 'Home',
      'quiz_game_play_again': 'Play Again',
      'quiz_game_no_indicators_available': 'No indicators with sectors or subsectors available for quiz',
      'quiz_game_failed_to_start': 'Failed to start quiz',
      'quiz_game_leaderboard': 'Leaderboard',
      'quiz_game_view_leaderboard': 'View Leaderboard',
      'quiz_game_loading_leaderboard': 'Loading leaderboard...',
      'quiz_game_no_leaderboard_data': 'No leaderboard data available yet',
      'quiz_game_top_players': 'Top Players',
      'quiz_game_you': 'You',
      'quiz_game_points': 'Points',

      // Offline indicator
      'offline_status': 'Offline',
      'offline_sync': 'Sync',
      'offline_no_internet': 'No Internet Connection',
      'offline_pending_count': '%s pending',
      'offline_queued_count': '(%s queued)',
      'offline_synced_time': 'Synced %s',
      'offline_requests_will_sync':
          '%s request(s) will be synced when online',
      'backend_unreachable_title': 'Cannot reach server',
      'backend_unreachable_subtitle':
          'Showing saved data where available. Actions may not sync until the server is available again.',

      // PDF viewer
      'pdf_viewer_connecting': 'Connecting…',
      'pdf_viewer_downloading_percent': 'Downloading… %s%',
      'pdf_viewer_could_not_load': 'Could not load document.',
      'pdf_viewer_download_failed_http': 'Download failed. Please try again.',
      'pdf_viewer_filename_fallback': 'document',
      'action_share': 'Share',

      // Translation entry UI
      'translation_unknown_key': 'Unknown Key',
      'translation_language_label': 'Language: %s',
      'lang_display_en': 'English',
      'lang_display_fr': 'French',
      'lang_display_es': 'Spanish',
      'lang_display_ar': 'Arabic',
      'lang_display_ru': 'Russian',
      'lang_display_zh': 'Chinese',
      'lang_display_hi': 'Hindi',
      'lang_display_nl': 'Dutch',
      'lang_display_hu': 'Hungarian',
      'lang_display_ja': 'Japanese',
      'empty_em_dash': '—',

      // Navigation / WebView
      'nav_url_not_allowed': 'Navigation to this URL is not allowed',
      'navigation_menu': 'Navigation Menu',
      'http_error': 'This page could not be loaded. Please try again.',

      // Azure SSO
      'azure_complete_sign_in_browser':
          'Complete sign-in in the browser,\nthen return to this app.',
      'azure_opening_sign_in_browser': 'Opening sign-in browser…',
      'azure_reopen_browser': 'Reopen Browser',

      // Settings
      'settings_theme_set_to': 'Theme set to %s',

      // Resources / search tooltips
      'resources_search_tooltip': 'Search',
      'resources_close_search_tooltip': 'Close search',

      // Countries
      'countries_search_hint': 'Search countries…',
      'countries_no_results': 'No countries found',
      'countries_no_available': 'No countries available',

      // NS structure
      'ns_select_branch_prompt': 'Select a branch to view sub-branches',

      // Templates
      'template_delete_has_data':
          'This template has %s saved data entries that will be permanently deleted. Continue?',
      'template_delete_simple': 'Are you sure you want to delete this template?',
      'template_duplicated_success': 'Template duplicated successfully',
      'template_duplicate_failed': 'Failed to duplicate template',

      // Translation management filters
      'translation_filter_source': 'Source',
      'translation_filter_source_hint': 'Search or select file path',

      // Organization entity editor
      'org_entity_division': 'Division',
      'org_entity_department': 'Department',
      'org_entity_regional_office': 'Regional Office',
      'org_entity_cluster_office': 'Cluster Office',
      'org_entity_ns_structure': 'NS Structure',
      'org_entity_country': 'Country',
      'org_entity_national_society': 'National Society',
      'org_entity_generic': 'Entity',
      'entity_edit_title': 'Edit %s',
      'entity_name_label': '%s Name *',
      'entity_name_hint': 'Enter %s name',
      'entity_name_required': '%s name is required',
      'field_code': 'Code',
      'field_code_hint': 'Enter code (optional)',
      'field_description': 'Description',
      'field_description_hint': 'Enter description (optional)',
      'field_display_order': 'Display Order',
      'field_display_order_hint': 'Enter display order',
      'field_active': 'Active',

      // Indicator admin editor
      'indicator_edit_name_label': 'Indicator Name *',
      'indicator_edit_name_hint': 'Enter indicator name',
      'indicator_edit_name_required': 'Indicator name is required',
      'indicator_edit_type_label': 'Type *',
      'indicator_edit_type_required': 'Type is required',
      'indicator_edit_unit_hint': 'e.g., People, %, Items',
      'indicator_edit_definition_hint': 'Detailed definition of this indicator',
      'indicator_edit_sector_hint': 'Enter sector',
      'indicator_edit_subsector_hint': 'Enter sub-sector',
      'indicator_edit_related_programs_hint':
          'Comma-separated list of related programs',
      'indicator_edit_comments_hint': 'Internal comments about this indicator',
      'indicator_edit_comments_label': 'Comments',
      'indicator_edit_emergency': 'Emergency Indicator',
      'indicator_edit_save': 'Save Indicator',
      'indicator_edit_fdrs_kpi_label': 'FDRS KPI Code',
      'indicator_edit_fdrs_kpi_hint': 'e.g. FDRS KPI code (optional)',
      'indicator_edit_multilingual_section': 'Multilingual names (optional)',
      'indicator_edit_name_for_language': 'Name (%s)',
      'indicator_edit_select_none': '— Select —',
      'indicator_edit_sector_group': 'Sector',
      'indicator_edit_subsector_group': 'Sub-sector',
      'indicator_edit_sector_level_primary': 'Primary',
      'indicator_edit_sector_level_secondary': 'Secondary',
      'indicator_edit_sector_level_tertiary': 'Tertiary',

      // Generics / fallbacks
      'generic_untitled': 'Untitled',
      'generic_untitled_document': 'Untitled Document',
      'generic_lowercase_resource': 'resource',
      'generic_unnamed_indicator': 'Unnamed Indicator',
      'generic_untitled_resource': 'Untitled Resource',

      // AI Chat (immersive)
      'ai_policy_acknowledge_snackbar':
          'Please acknowledge the AI policy to continue.',
      'ai_use_policy_title': 'AI Use Policy',
      'ai_policy_do_not_share': 'Don\'t share sensitive information.',
      'ai_policy_traces_body':
          'We use system traces and telemetry to improve the assistant. Your messages may be processed by external AI providers.',
      'ai_policy_purpose_title': 'Purpose',
      'ai_policy_purpose_body':
          'The AI assistant helps you explore data and documents on this platform. It can answer questions about indicators, countries, assignments, and search through uploaded documents.',
      'ai_policy_acceptable_use_title': 'Acceptable use',
      'ai_policy_acceptable_use_body':
          '• Ask about platform data, indicators, and documents.\n'
          '• Do NOT share passwords, credentials, or highly confidential operational details.\n'
          '• Do NOT paste personal or financial data.',
      'ai_policy_accuracy_title': 'Accuracy',
      'ai_policy_accuracy_body':
          'AI can make mistakes or misinterpret data. Always verify important information against source data or documents.',
      'ai_policy_confirm_footer':
          'Confirm you\'ve read the information above to use the assistant.',
      'ai_policy_i_understand': 'I understand',
      'ai_policy_acknowledge_cta': 'Acknowledge AI use policy',
      'ai_sources_heading': 'Use sources:',
      'ai_source_databank': 'Databank',
      'ai_source_system_documents': 'System documents',
      'ai_source_upr_documents': 'UPR documents',
      'ai_sources_minimum_note':
          'At least one source stays enabled (same as the web assistant).',
      'ai_tour_guide_question': 'Would you like me to guide you through this?',
      'ai_tour_navigate_question': 'Would you like to go to the relevant page?',
      'ai_tour_web_only_snackbar':
          'Interactive tours are available on the web version. Navigating to the page...',
      'ai_new_chat': 'New chat',
      'ai_semantic_open_drawer_hint': 'Opens conversations and settings',
      'ai_tooltip_new_chat': 'New chat',
      'ai_semantic_new_chat_label': 'New chat',
      'ai_semantic_new_chat_hint': 'Starts a new empty conversation',
      'ai_beta_tester_banner':
          'AI beta tester — experimental assistant features may be enabled.',
      'ai_empty_welcome': 'How can I help you today?',
      'ai_policy_chip_title': 'AI use policy',
      'ai_policy_sheet_summary_line':
          'Short summary — open the sheet for full details.',
      'ai_policy_compact_warning':
          'Don\'t share sensitive information. We use system traces and telemetry to improve the assistant; messages may be processed by external AI providers.',
      'ai_read_full_policy': 'Read full policy',
      'ai_try_asking': 'Try asking',
      'ai_copied': 'Copied!',
      'ai_tooltip_copy': 'Copy',
      'ai_tooltip_edit_message': 'Edit',
      'ai_tooltip_helpful': 'Helpful',
      'ai_tooltip_not_helpful': 'Not helpful',
      'ai_footer_model_warning':
          'AI can make mistakes. Check important information.',
      'ai_chat_error_network':
          'Couldn\'t reach the AI service. Check your internet connection and try again.',
      'ai_chat_error_timeout':
          'The request timed out. Check your connection and try again.',
      'ai_chat_error_server': 'Something went wrong. Please try again.',
      'ai_agent_progress_title': 'Steps in progress',
      'ai_agent_step_done': 'Done.',
      'ai_agent_step_preparing_query': 'Preparing query…',
      'ai_agent_step_planning': 'Planning approach…',
      'ai_agent_step_reviewing': 'Reviewing results…',
      'ai_agent_step_drafting': 'Drafting answer…',
      'ai_agent_step_replying': 'Replying…',
      'ai_agent_step_thinking_next': 'Thinking about what to do next.',
      'ai_agent_step_no_shortcut_full':
          'No single-tool shortcut — using the full planning path.',
      'ai_agent_step_no_shortcut_reviewing':
          'No single-tool shortcut for this request — reviewing: %s',
      'ai_response_sources': 'Sources',
      'ai_response_sources_with_count': 'Sources (%s)',
      'ai_tooltip_configure_sources': 'Configure data sources',
      'ai_input_policy_required':
          'Acknowledge the AI policy above to send messages',
      'ai_input_placeholder_message': 'Message',
      'ai_input_placeholder_edit': 'Edit message…',
      'ai_tooltip_cancel_edit': 'Cancel edit',
      'ai_stop': 'Stop',
      'ai_conversations_drawer_title': 'Conversations',
      'ai_search_conversations_hint': 'Search conversations',
      'ai_no_conversations_body': 'No conversations yet.\nStart a new chat!',
      'ai_no_conversations_offline':
          'No conversations yet.\nStart a new chat (offline).',
      'ai_no_conversations_filtered': 'No conversations found',
      'ai_section_pinned': 'Pinned',
      'ai_section_recent': 'Recent',
      'ai_quick_prompt_1': 'How many volunteers in Bangladesh?',
      'ai_quick_prompt_2': 'Volunteers in Syria over time',
      'ai_quick_prompt_3': 'World heatmap of volunteers by country',
      'ai_quick_prompt_4': 'Number of branches in Kenya',
      'ai_quick_prompt_5': 'Staff and local units in Nigeria',
      'ai_clear_all_dialog_title': 'Clear all conversations',
      'ai_clear_all_dialog_body':
          'Are you sure you want to delete all conversations? This action cannot be undone.',
      'ai_clear_all_button': 'Clear All',
      'ai_clear_all_row': 'Clear all conversations',
      'ai_help_about_row': 'Help & About',
      'ai_pin': 'Pin',
      'ai_unpin': 'Unpin',
      'ai_delete_conversation_title': 'Delete conversation?',
      'ai_delete_conversation_body':
          'Delete this conversation? This cannot be undone.',
      'ai_new_chat_title_fallback': 'New Chat',
      'ai_help_dialog_title': 'AI Assistant Help',
      'ai_help_about_heading': 'About',
      'ai_help_about_paragraph':
          'The AI Assistant helps you find information and answer questions about the IFRC Network Databank.',
      'ai_help_features_heading': 'Features',
      'ai_help_feature_bullet_1':
          '• Ask questions about assignments, resources, and more',
      'ai_help_feature_bullet_2': '• Get help navigating the app',
      'ai_help_feature_bullet_3': '• Search through your conversation history',
      'ai_help_feature_bullet_4':
          '• All conversations are saved when you\'re logged in',
      'ai_help_tips_heading': 'Tips',
      'ai_help_tip_bullet_1': '• Be specific in your questions for better results',
      'ai_help_tip_bullet_2':
          '• Tap on links in responses to navigate to relevant pages',
      'ai_help_tip_bullet_3': '• Use the search bar to quickly find past conversations',
      'ai_help_tip_bullet_4':
          '• Long-press a conversation to open a menu (pin or delete) next to that row',
      'ai_got_it': 'Got it',
      'ai_score_confidence': 'Confidence',
      'ai_score_grounding': 'Grounding',
      'ai_default_assistant_title': 'AI Assistant',
      'resources_other_subgroup': 'Other',
      'resources_list_truncated_hint':
          'Showing the most recent items. Use search to find a specific document.',

      // AI
      'ai_assistant': 'AI Assistant',
    },
    'es': {
      'app_name': 'Banco de Datos de la Red IFRC',
      'navigation': 'Navegación',
      'home': 'Inicio',
      'dashboard': 'Panel',
      'resources': 'Recursos',
      'indicator_bank': 'Banco de Indicadores',
      'disaggregation_analysis': 'Análisis de Desagregación',
      'analysis': 'Análisis',
      'data_visualization': 'Visualización de Datos',
      'settings': 'Configuración',
      'notifications': 'Notificaciones',
      'admin': 'Administración',
      'admin_panel': 'Panel de Administración',
      'customize_tabs': 'Personalizar Pestañas',
      'customize_tabs_description': 'Seleccione qué pestañas mostrar y arrástrelas para reordenarlas.',
      'reset_to_default': 'Restablecer',
      'tab_always_shown': 'Siempre visible',
      'minimum_tabs_warning': 'Debe mantener al menos 2 pestañas visibles.',
      'access_denied': 'Acceso Denegado',
      'general': 'General',
      'document_management': 'Gestión de Documentos',
      'translation_management': 'Gestión de Traducciones',
      'plugin_management': 'Gestión de Complementos',
      'system_configuration': 'Configuración del Sistema',
      'user_management': 'Gestión de Usuarios',
      'manage_users': 'Gestionar Usuarios',
      'access_requests_title': 'Solicitudes de acceso por país',
      'access_requests_subtitle':
          'Apruebe o rechace solicitudes de acceso a nivel de país.',
      'access_requests_pending': 'Pendiente',
      'access_requests_processed': 'Decisiones recientes',
      'access_requests_empty': 'No hay solicitudes de acceso.',
      'access_requests_approve': 'Aprobar',
      'access_requests_reject': 'Rechazar',
      'access_requests_approve_all': 'Aprobar todas',
      'access_requests_approve_all_confirm':
          '¿Aprobar todas las solicitudes de acceso por país pendientes?',
      'access_requests_reject_confirm':
          '¿Rechazar esta solicitud de acceso? El usuario no obtendrá acceso.',
      'access_requests_country': 'País',
      'access_requests_message': 'Mensaje',
      'access_requests_requested_at': 'Solicitado',
      'access_requests_processed_at': 'Procesado',
      'access_requests_auto_approve_hint':
          'La aprobación automática puede estar habilitada en la configuración del servidor.',
      'access_requests_status_pending': 'Pendiente',
      'access_requests_status_approved': 'Aprobado',
      'access_requests_status_rejected': 'Rechazado',
      'access_requests_by': 'Por',
      'access_requests_load_failed':
          'No se pudieron cargar las solicitudes de acceso.',
      'access_requests_action_failed': 'No se pudo completar la acción.',
      'access_requests_view_forbidden':
          'No tiene permiso para ver las solicitudes de acceso en el servidor.',
      'access_requests_unexpected_response':
          'Respuesta inesperada del servidor.',
      'access_requests_action_forbidden':
          'No tiene permiso para realizar esta acción.',
      'users_directory_read_only':
          'Este listado es solo lectura. Cree o modifique cuentas en el backoffice web.',
      'login_logs_title': 'Registros de inicio de sesión',
      'login_logs_filters': 'Filtros',
      'login_logs_email_hint': 'Buscar por correo',
      'login_logs_event_type': 'Tipo de evento',
      'login_logs_event_all': 'Todos los tipos',
      'login_logs_event_login': 'Inicio de sesión',
      'login_logs_event_logout': 'Cierre de sesión',
      'login_logs_event_failed': 'Fallo de inicio de sesión',
      'login_logs_ip_label': 'Dirección IP',
      'login_logs_date_from': 'Desde',
      'login_logs_date_to': 'Hasta',
      'login_logs_suspicious_only': 'Solo sospechosos',
      'login_logs_apply': 'Aplicar',
      'login_logs_clear': 'Borrar',
      'login_logs_no_entries': 'No hay eventos que coincidan con los filtros.',
      'login_logs_total': '%s eventos en total',
      'login_logs_load_more': 'Cargar más',
      'login_logs_user_not_resolved': 'Sin usuario coincidente',
      'login_logs_device': 'Dispositivo',
      'login_logs_browser': 'Navegador',
      'login_logs_suspicious_badge': 'Sospechoso',
      'login_logs_recent_failures': '%s fallos recientes',
      'login_logs_open': 'Registros de inicio de sesión',
      'session_logs_title': 'Registros de sesión',
      'admin_filters': 'Filtros',
      'session_logs_email_hint': 'Buscar por correo',
      'session_logs_min_duration': 'Min. minutos (sesión o activo)',
      'session_logs_active_only': 'Solo sesiones activas',
      'admin_filters_apply': 'Aplicar',
      'admin_filters_clear': 'Borrar',
      'session_logs_no_entries': 'No hay sesiones que coincidan con los filtros.',
      'session_logs_total': '%s sesiones en total',
      'session_logs_load_more': 'Cargar más',
      'session_logs_session_start': 'Inicio de sesión',
      'session_logs_duration': 'Duración',
      'session_logs_session_length': 'Duración de sesión',
      'session_logs_active_time': 'Tiempo activo',
      'session_logs_minutes': '%s min',
      'session_logs_page_views': 'Vistas de página',
      'session_logs_path_breakdown_title': 'Vistas por ruta',
      'session_logs_path_breakdown_open': 'Ver desglose de rutas',
      'session_logs_path_breakdown_empty':
          'No hay desglose de rutas para esta sesión.',
      'session_logs_path_other_bucket': 'Otras rutas (agregadas)',
      'session_logs_path_column': 'Ruta',
      'session_logs_path_count_column': 'Recuento',
      'session_logs_distinct_paths': 'Rutas distintas',
      'session_logs_activities': 'Actividades',
      'session_logs_last_activity': 'Última actividad',
      'session_logs_status_active': 'Activa',
      'session_logs_status_ended': 'Finalizada',
      'session_logs_force_logout': 'Cerrar sesión forzado',
      'session_logs_force_logout_confirm':
          '¿Forzar el cierre de sesión de este usuario? Se cerrará de inmediato.',
      'session_logs_unknown_user': 'Usuario desconocido',
      'session_logs_no_activity': 'Sin actividad',
      'session_logs_open': 'Registros de sesión',
      'session_logs_ended_ok': 'Sesión finalizada.',
      'session_logs_os': 'SO',
      'session_logs_user_agent': 'Agente de usuario',
      'session_logs_device_section': 'Detalles del dispositivo',
      'form_data_management': 'Gestión de Formularios y Datos',
      'manage_templates': 'Gestionar Plantillas',
      'manage_assignments': 'Gestionar Asignaciones',
      'frontend_management': 'Gestión de Website',
      'manage_resources': 'Gestionar Recursos',
      'reference_data': 'Datos de Referencia',
      'organizational_structure': 'Estructura Organizacional',
      'analytics_monitoring': 'Análisis y Monitoreo',
      'user_analytics': 'Análisis de Usuarios',
      'audit_trail': 'Registro de Auditoría',
      'api_management': 'Gestión de API',
      'account_settings': 'Configuración de Cuenta',
      'profile': 'Perfil',
      'preferences': 'Preferencias',
      'language': 'Idioma',
      'select_language': 'Seleccionar Idioma',
      'change_password': 'Cambiar Contraseña',
      'profile_color': 'Color de Perfil',
      'chatbot': 'Chatbot',
      'enable_chatbot_assistance': 'Habilitar asistencia de chatbot',
      'dark_theme': 'Tema Oscuro',
      'enable_dark_theme': 'Habilitar tema oscuro',
      'settings_theme': 'Tema',
      'light_theme': 'Tema claro',
      'system_theme': 'Sistema',
      'select_theme': 'Seleccionar tema',
      'settings_theme_set_to': 'Tema configurado como %s',
      'arabic_text_font': 'Tipografía árabe',
      'arabic_font_tajawal': 'Tajawal',
      'arabic_font_system': 'Predeterminado del sistema',
      'login_to_account': 'Iniciar Sesión',
      'logout': 'Cerrar Sesión',
      'are_you_sure_logout': '¿Está seguro de que desea cerrar sesión?',
      'cancel': 'Cancelar',
      'name': 'Nombre',
      'title': 'Título',
      'email': 'Correo Electrónico',
      'loading': 'Cargando...',
      'loading_home': 'Cargando Inicio...',
      'home_landing_hero_description':
          'Explora datos humanitarios integrales, indicadores e información de la Federación Internacional de Sociedades de la Cruz Roja y de la Media Luna Roja.',
      'home_landing_chat_title': 'Chatea con nuestros datos',
      'home_landing_chat_description': 'Escribe tus preguntas sobre nuestros datos abajo.',
      'home_landing_ask_placeholder': 'Pregunta sobre financiación, programas, países...',
      'home_landing_quick_prompt_1': 'Cuéntame sobre los voluntarios del Creciente Rojo Afgano',
      'home_landing_quick_prompt_2': 'Muéstrame datos globales de respuesta a desastres',
      'home_landing_quick_prompt_3': '¿Cuáles son los indicadores humanitarios clave?',
      'home_landing_shortcuts_heading': 'Primeros pasos',
      'home_landing_shortcut_indicators_subtitle': 'Explora definiciones y metadatos',
      'home_landing_shortcut_resources_subtitle': 'Publicaciones y materiales',
      'home_landing_shortcut_countries_subtitle': 'Perfiles y vistas regionales',
      'home_landing_shortcut_disaggregation_subtitle': 'Desglosa los valores de indicadores',
      'home_landing_explore_title': 'Mapa global y gráficos',
      'home_landing_explore_subtitle':
          'Mapa y gráfico nativos con los mismos totales FDRS que el sitio web, sin salir de la aplicación.',
      'home_landing_global_indicator_volunteers': 'Voluntarios',
      'home_landing_global_indicator_staff': 'Personal',
      'home_landing_global_indicator_branches': 'Sucursales',
      'home_landing_global_indicator_local_units': 'Local units',
      'home_landing_global_indicator_blood_donors': 'Blood donors',
      'home_landing_global_indicator_first_aid': 'First aid',
      'home_landing_global_indicator_people_reached': 'People reached',
      'home_landing_global_indicator_income': 'Income',
      'home_landing_global_indicator_expenditure': 'Expenditure',
      'home_landing_global_top_countries': 'Principales países',
      'home_landing_global_load_error':
          'No se pudieron cargar los datos del mapa. Compruebe su conexión e inténtelo de nuevo.',
      'home_landing_global_empty':
          'No hay valores para este indicador en el último período.',
      'home_landing_global_period': 'Período: %s',
      'home_landing_global_map_hint':
          'Pellizque, arrastre y toque un país para ver detalles',
      'home_landing_global_map_open_fullscreen': 'Pantalla completa',
      'home_landing_global_period_filter_label': 'Período de reporte',
      'home_landing_global_map_mode_bubble': 'Burbujas',
      'home_landing_global_map_mode_choropleth': 'Coropletas',
      'home_landing_global_map_zoom_in': 'Acercar',
      'home_landing_global_map_zoom_out': 'Alejar',
      'home_landing_global_map_reset_bounds': 'Ajustar datos',
      'home_landing_global_map_legend_low': 'Bajo',
      'home_landing_global_map_legend_high': 'Alto',
      'home_landing_global_map_country_no_data':
          'Sin datos para este indicador',
      'home_landing_global_map_value_label': 'Valor',
      'home_landing_global_map_country_trend': 'Por período de reporte',
      'home_landing_global_map_filters_title': 'Opciones del mapa',
      'loading_page': 'Cargando página...',
      'loading_preferences': 'Cargando preferencias...',
      'loading_notifications': 'Cargando notificaciones...',
      'loading_dashboard': 'Cargando panel...',
      'loading_audit_logs': 'Cargando registros de auditoría...',
      'loading_analytics': 'Cargando análisis...',
      'loading_organizations': 'Cargando organizaciones...',
      'loading_templates': 'Cargando plantillas...',
      'loading_assignments': 'Cargando asignaciones...',
      'loading_translations': 'Cargando traducciones...',
      'loading_plugins': 'Cargando complementos...',
      'loading_resources': 'Cargando recursos...',
      'loading_indicators': 'Cargando indicadores...',
      'loading_documents': 'Cargando documentos...',
      'loading_api_endpoints': 'Cargando endpoints de API...',
      'loading_users': 'Cargando usuarios...',
      'error': 'Error',
      'retry': 'Reintentar',
      'refresh': 'Actualizar',
      'close': 'Cerrar',
      'save': 'Guardar',
      'saved': 'Guardado',
      'success': 'Éxito',
      'oops_something_went_wrong': '¡Ups! Algo salió mal',
      'go_back': 'Volver',
      'edit': 'Editar',
      'duplicate': 'Duplicar',
      'preview': 'Vista Previa',
      'download_started': 'Descarga iniciada',
      'could_not_start_download': 'No se pudo iniciar la descarga',
      'could_not_open_download_link': 'No se pudo abrir el enlace de descarga',
      'error_opening_download': 'Error al abrir la descarga',
      'please_select_at_least_one_user': 'Por favor seleccione al menos un usuario',
      'indicator_updated_successfully': 'Indicador actualizado exitosamente',
      'failed_to_load_indicator': 'Error al cargar el indicador',
      'user_deleted': 'Usuario eliminado',
      'public_url_copied': '¡URL pública copiada al portapapeles!',
      'please_use_web_interface': 'Por favor use la interfaz web para guardar cambios de entidad',
      'open_in_web_browser': 'Abrir en Navegador Web',
      'countries': 'Países',
      'all_roles': 'Todos los Roles',
      'admin_role': 'Administrador',
      'focal_point_role': 'Punto Focal',
      'system_manager_role': 'Administrador del Sistema',
      'viewer_role': 'Visualizador',
      'all_status': 'Todos los Estados',
      'active_status': 'Activo',
      'inactive_status': 'Inactivo',
      'normal_priority': 'Normal',
      'high_priority': 'Alta',
      'none': 'Ninguno',
      'app_screen': 'Pantalla de Aplicación',
      'custom_url': 'URL Personalizada',
      'create_template': 'Crear Plantilla',
      'delete_template': 'Eliminar Plantilla',
      'create_assignment': 'Crear Asignación',
      'delete_assignment': 'Eliminar Asignación',
      'edit_document': 'Editar Documento',
      'preview_document': 'Vista Previa del Documento',
      'download_document': 'Descargar Documento',
      'upload_document': 'Subir Documento',
      'new_translation': 'Nueva Traducción',
      'new_resource': 'Nuevo Recurso',
      'install_plugin': 'Instalar Complemento',
      'template_deleted_successfully': 'Plantilla eliminada exitosamente',
      'failed_to_delete_template': 'Error al eliminar la plantilla',
      'error_loading_page': 'Error al cargar la página',
      'no_notifications': 'No hay notificaciones',
      'all_caught_up': 'Estás al día',
      'notifications_load_more': 'Cargar más',
      'notifications_filter': 'Filtros',
      'notifications_filter_title': 'Filtrar notificaciones',
      'notifications_filter_read_status': 'Estado de lectura',
      'notifications_filter_all': 'Todas',
      'notifications_filter_unread_only': 'No leídas',
      'notifications_filter_type': 'Tipo',
      'notifications_filter_type_any': 'Todos los tipos',
      'notifications_filter_from': 'De',
      'notifications_filter_from_any': 'Cualquiera',
      'notifications_filter_from_empty_hint':
          'Las personas aparecen cuando sus notificaciones están en la lista cargada. Use Cargar más para encontrar otras.',
      'notifications_filter_priority': 'Prioridad',
      'notifications_filter_priority_any': 'Cualquier prioridad',
      'notifications_filter_priority_normal': 'Normal',
      'notifications_filter_priority_high': 'Alta',
      'notifications_filter_priority_urgent': 'Urgente',
      'notifications_filter_apply': 'Aplicar',
      'notifications_filter_reset': 'Restablecer',
      'notifications_filter_no_matches_loaded':
          'Ninguna notificación coincide con los filtros en la lista cargada. Cargue más o ajuste los filtros.',
      'mark_all_read': 'Marcar todo como leído',
      'mark_read': 'Marcar como leído',
      'mark_unread': 'Marcar como no leído',
      'delete': 'Eliminar',
      'archive': 'Archivar',
      'unarchive': 'Desarchivar',
      'send_push_notification': 'Enviar Notificación Push',
      'admin_push_user_ids_label': 'ID de usuario de los destinatarios',
      'admin_push_user_ids_hint':
          'ID numéricos separados por comas (en Gestionar usuarios).',
      'admin_push_user_ids_invalid':
          'Introduzca uno o más ID de usuario numéricos, separados por comas.',
      'select_users': 'Seleccionar Usuarios',
      'search_users': 'Buscar usuarios por nombre o correo',
      'redirect_url': 'Redirigir (Opcional)',
      'login': 'Iniciar Sesión',
      'log_in': 'Iniciar Sesión',
      'phone_username_email': 'Teléfono, nombre de usuario o correo',
      'forgot_password_coming_soon':
          'Función de contraseña olvidada próximamente',
      'please_enter_email': 'Por favor ingrese su correo',
      'please_enter_valid_email': 'Por favor ingrese un correo válido',
      'please_enter_password': 'Por favor ingrese su contraseña',
      'show': 'Mostrar',
      'hide': 'Ocultar',
      'or': 'O',
      'dont_have_account': '¿No tienes una cuenta?',
      'sign_up': 'Regístrate',
      'registration_coming_soon': 'Función de registro próximamente',
      'quick_login_testing': 'Inicio de Sesión Rápido para Pruebas',
      'test_as_admin': 'Probar como Administrador',
      'test_as_focal_point': 'Probar como Punto Focal',
      'public_login_disabled':
          'El inicio de sesión público está temporalmente deshabilitado',
      'tester_accounts_info':
          'Las cuentas de prueba aún pueden iniciar sesión usando los botones de arriba.',
      'could_not_open_azure_login':
          'No se pudo abrir el inicio de sesión de Azure',
      'login_with_ifrc_account': 'Iniciar sesión con cuenta IFRC',
      'use_ifrc_federation_account':
          'Use su cuenta de la Federación IFRC para iniciar sesión',
      'your_account_or_create_account': 'Tu cuenta o crear una cuenta',
      'login_failed': 'Error al iniciar sesión',
      'email_address': 'Dirección de Correo',
      'password': 'Contraseña',
      'remember_me': 'Recordarme',
      'forgot_password': '¿Olvidó su contraseña?',
      'language_changed_to': 'Idioma cambiado a',

      // Splash Screen
      'welcome_to_ifrc_network_databank':
          'Bienvenido al Banco de Datos de la Red IFRC',
      'splash_description':
          'Este es el único sistema para reportar datos a la FICR. Di adiós a archivos Excel dispersos, formularios KoBo, múltiples plataformas e inicios de sesión: todo está ahora centralizado y optimizado aquí.',
      'powered_by_hum_databank': 'Impulsado por Humanitarian Databank',
      'open_on_github': 'Abrir en GitHub',

      // Dashboard
      'national_society': 'Sociedad Nacional',
      'active': 'Activo',
      'completed': 'Completado',
      'current_assignments': 'Asignaciones Actuales',
      'dashboard_you_have_no_open_assignments': 'No tienes asignaciones abiertas',
      'dashboard_you_have_one_open_assignment': 'Tienes 1 asignación abierta',
      'dashboard_you_have_open_assignments_count': 'Tienes %s asignaciones abiertas',
      'past_assignments': 'Asignaciones Pasadas',
      'assignments_for': 'Asignaciones para',
      'past_submissions_for': 'Envíos Pasados para',
      'something_went_wrong': 'Algo salió mal',
      'no_assignments_yet':
          '¡Todo claro! No hay asignaciones activas en este momento.',
      'new_assignments_will_appear':
          'Las nuevas asignaciones aparecerán aquí cuando estén disponibles.',
      'get_started_by_creating': 'Comience creando una nueva asignación',
      'filters': 'Filtros',
      'period': 'Período',
      'template': 'Plantilla',
      'status': 'Estado',
      'clear': 'Limpiar',
      'approved': 'Aprobado',
      'requires_revision': 'Requiere Revisión',
      'pending': 'Pendiente',
      'in_progress': 'En Progreso',
      'submitted': 'Enviado',
      'other': 'Otro',
      'entities': 'Entidades',
      'search_placeholder': 'Buscar...',
      'no_results_found': 'No se encontraron resultados',
      'entity_type_country': 'País',
      'entity_type_ns_branch': 'Rama SN',
      'entity_type_ns_sub_branch': 'Sub-Rama SN',
      'entity_type_ns_local_unit': 'Unidad Local SN',
      'entity_type_division': 'División',
      'entity_type_department': 'Departamento',
      'delete_assignment_confirm_message':
          '¿Está seguro de que desea eliminar esta asignación y todos sus estados de país y datos asociados?',
      'no_assignments_match_filters':
          'No hay asignaciones que coincidan con los filtros seleccionados',
      'form': 'Formulario',
      'last_updated': 'Última Actualización',
      'actions': 'Acciones',
      'all_years': 'Todos los Años',
      'all_templates': 'Todas las Plantillas',
      'all_statuses': 'Todos los Estados',
      'template_missing': 'Plantilla Faltante',
      'self_reported': 'Auto-Reportado',
      'no_actions_available': 'No hay acciones disponibles',
      'previous': 'Anterior',
      'next': 'Siguiente',
      'showing': 'Mostrando',
      'to': 'a',
      'of': 'de',
      'results': 'resultados',
      'no_past_assignments_for': 'No hay asignaciones pasadas para',
      'yet': 'aún.',
      'submission_history_and_data_quality_for':
          'Historial de Envíos y Calidad de Datos para',
      'overall_performance': 'Rendimiento General',
      'average_completion_rate_past_3_periods':
          'Tasa de Finalización Promedio (Últimos 3 Períodos)',
      'average_submission_timeliness':
          'Puntualidad de Envío Promedio (Días Antes/Después)',
      'data_quality_index_fake_metric':
          'Índice de Calidad de Datos (Métrica Falsa)',
      'number_of_revisions_requested_past_year':
          'Número de Revisiones Solicitadas (Año Pasado)',
      'trend_analysis': 'Análisis de Tendencias',
      'recent_activities': 'Actividades Recientes',
      'last_7_days': 'Últimos 7 días',
      'unknown_user': 'Usuario Desconocido',
      'added': 'Agregado',
      'updated': 'Actualizado',
      'removed': 'Eliminado',
      'show_less': 'Mostrar menos',
      'more_change': 'cambio más',
      'no_recent_activities': 'No hay actividades recientes',
      'activities_from_other_focal_points_in':
          'Actividades de otros puntos focales en',
      'will_appear_here': 'aparecerán aquí',
      'focal_points_for': 'Puntos Focales para',
      'national_society_focal_points': 'Puntos Focales de la Sociedad Nacional',
      'ifrc_focal_points': 'Puntos Focales de la FICR',
      'no_focal_points_assigned_to': 'No hay puntos focales asignados a',
      'your_user_account_not_associated':
          'Su cuenta de usuario no está asociada con ningún país.',
      'please_contact_administrator': 'Por favor contacte a un administrador.',
      'due_date': 'Fecha de Vencimiento',
      'no_due_date': 'Sin fecha de vencimiento',
      'overdue': 'Vencido',
      'latest_submission': 'Último Envío',
      'submitted_through_public_link': 'Enviado a través de enlace público',
      'submission': 'envío',
      'submissions': 'envíos',
      'completion': 'Finalización',
      'received_1_submission_using_public_link':
          'Recibido 1 envío usando el enlace público',
      'received_count_submissions_using_public_link':
          'Recibidos %(count)d envíos usando el enlace público',
      'at_datetime': 'en: %(datetime)s',
      'latest_datetime': 'Más reciente: %(datetime)s',
      'last_modified_by': 'Última modificación por',
      'assignment_assigned_date': 'Asignado',
      'assignment_status_updated': 'Estado actualizado',
      'contributors': 'Colaboradores',
      'assignment_submitted_by': 'Enviado por',
      'assignment_approved_by': 'Aprobado por',
      'public_link_enabled': 'Enlace público activo',
      'public_link': 'Enlace público',
      'unknown': 'Desconocido',
      'n_a': 'N/A',
      'enter_data': 'Ingresar Datos',
      'download_for_offline': 'Descargar para uso sin conexión',
      'downloading_offline_form': 'Descargando formulario para uso sin conexión…',
      'offline_form_saved': 'Formulario guardado para acceso sin conexión.',
      'offline_form_save_failed': 'No se pudo guardar el formulario sin conexión. Inténtelo de nuevo con una conexión estable.',
      'offline_form_not_downloaded': 'Este formulario no está disponible sin conexión. Descárguelo mientras esté en línea.',
      'offline_download_requires_connection': 'Conéctese a internet para descargar este formulario para uso sin conexión.',
      'offline_form_export_requires_connection':
          'Conéctese a internet para exportar PDF, Excel o informes de validación. La copia sin conexión no incluye exportaciones.',
      'offline_open_saved_copy': 'Abrir copia sin conexión guardada',
      'remove_offline_copy': 'Quitar copia sin conexión',
      'offline_form_removed':
          'Copia sin conexión eliminada. Vuelva a descargar cuando tenga conexión.',
      'offline_saved_copy_details_tooltip':
          'Copia sin conexión — detalles y eliminar',
      'offline_copy_sheet_title': 'Copia de formulario sin conexión',
      'offline_copy_saved_on_label': 'Guardada el',
      'offline_copy_files_cached': '%(count)d recursos en caché',
      'offline_stale_bundle_banner_title':
          'Los formularios sin conexión necesitan actualización',
      'offline_stale_bundle_banner_body_online':
          'El formulario en línea cambió. El dispositivo actualiza las copias sin conexión automáticamente cuando hay conexión. Si falla, abra cada formulario con la advertencia y pulse Actualizar copia sin conexión.',
      'offline_stale_bundle_banner_body_offline':
          'El formulario en línea cambió. Conéctese a internet para que el dispositivo pueda actualizar las copias sin conexión automáticamente.',
      'offline_stale_bundle_updates_snackbar':
          'Las copias sin conexión se actualizaron a la última versión.',
      'offline_stale_bundle_partial_refresh':
          'No se pudieron actualizar algunas copias sin conexión. Pulse la advertencia en un formulario y luego Actualizar copia sin conexión.',
      'offline_stale_bundle_sheet_notice':
          'Esta copia sin conexión puede no coincidir con el formulario en línea actual. Actualícela para evitar problemas de versión.',
      'offline_stale_bundle_update_now': 'Actualizar copia sin conexión',
      'approve': 'Aprobar',
      'reopen': 'Reabrir',
      'view_public_submissions': 'Ver Envíos Públicos',
      'view_submission': 'Ver Envío',
      'view_submissions': 'Ver Envíos',
      'open_form': 'Abrir Formulario',
      'no_forms_assigned_or_submitted_for':
          'No se han asignado o enviado formularios a través de enlaces públicos para',
      'admins_can_assign_forms':
          'Los administradores pueden asignar formularios o crear enlaces públicos a través del Panel de Administración.',
      'create_a_report': 'Crear un Informe',
      'delete_self_reported_assignment': 'Eliminar Asignación Auto-Reportada',
      'quick_actions': 'Acciones Rápidas',
      'new_assignment': 'Nueva Asignación',
      'new_template': 'Nueva Plantilla',
      'key_metrics': 'Métricas Clave',
      'overview': 'Resumen',
      'create_new_assignment': 'Crear una nueva asignación',
      'templates': 'Plantillas',
      'browse_available_templates': 'Explorar plantillas disponibles',
      'enter_your_name': 'Ingrese su nombre',
      'enter_your_job_title': 'Ingrese su título de trabajo',
      'edit_name': 'Editar Nombre',
      'edit_title': 'Editar Título',
      'name_cannot_be_empty': 'El nombre no puede estar vacío',
      'title_cannot_be_empty': 'El título no puede estar vacío',
      'profile_updated_successfully': 'Perfil actualizado exitosamente',
      'error_updating_profile': 'Error al actualizar el perfil',
      'color_picker_coming_soon': 'Selector de color próximamente',
      'chatbot_preference_update_coming_soon':
          'Actualización de preferencias de chatbot próximamente',
      'select_color': 'Seleccione un color',
      'current_color': 'Color Actual',
      'profile_color_updated': 'Color de perfil actualizado exitosamente',
      'profile_color_update_failed': 'Error al actualizar el color de perfil',
      'admin_dashboard': 'Panel de Administración',
      'no_data_available': 'No hay datos disponibles',
      'total_users': 'Total de Usuarios',
      'admins': 'Administradores',
      'system_administrators': 'Administradores del sistema',
      'focal_points': 'Puntos Focales',
      'country_focal_points': 'Puntos focales del país',
      'form_templates': 'Plantillas de formularios',
      'active_assignments': 'Asignaciones activas',
      'todays_logins': 'Inicios de Sesión de Hoy',
      'successful_logins_today': 'Inicios de sesión exitosos hoy',
      'pending_submissions': 'Envíos Pendientes',
      'overdue_assignments': 'Asignaciones Vencidas',
      'security_alerts': 'Alertas de Seguridad',
      'successful_logins': 'Inicios de Sesión Exitosos',
      'user_activities': 'Actividades del Usuario',
      'active_sessions': 'Sesiones Activas',
      'all_notifications_marked_as_read':
          'Todas las notificaciones marcadas como leídas',
      'mark_as_read': 'Marcar como leído',
      'mark_as_unread': 'Marcar como no leído',
      'notification_preferences': 'Preferencias de Notificaciones',
      'sound_notifications': 'Notificaciones de Sonido',
      'email_frequency': 'Frecuencia de Correo',
      'instant': 'Instantáneo',
      'daily_digest': 'Resumen Diario',
      'weekly_digest': 'Resumen Semanal',
      'digest_schedule': 'Programa de Resumen',
      'day_of_week': 'Día de la Semana',
      'monday': 'Lunes',
      'tuesday': 'Martes',
      'wednesday': 'Miércoles',
      'thursday': 'Jueves',
      'friday': 'Viernes',
      'saturday': 'Sábado',
      'sunday': 'Domingo',
      'time_local_time': 'Hora (Hora Local)',
      'notification_types': 'Tipos de Notificaciones',
      'preferences_saved_successfully': 'Preferencias guardadas exitosamente',
      'enable_sound': 'Activar Sonido',
      'play_sound_for_new_notifications': 'Reproducir sonido para nuevas notificaciones',
      'configure_notification_types_description': 'Configure qué tipos de notificaciones recibir por correo electrónico y notificaciones push',
      'notification_type': 'Tipo de Notificación',
      'push': 'Push',
      'all': 'Todos',
      'save_preferences': 'Guardar Preferencias',
      'select_digest_time_description': 'Seleccione la hora en la que desea recibir su resumen',
      'failed_to_save_preferences': 'Error al guardar las preferencias',
      'assignment_created': 'Asignación Creada',
      'assignment_submitted': 'Asignación Enviada',
      'assignment_approved': 'Asignación Aprobada',
      'assignment_reopened': 'Asignación Reabierta',
      'public_submission_received': 'Envío Público Recibido',
      'form_updated': 'Formulario Actualizado',
      'document_uploaded': 'Documento Subido',
      'user_added_to_country': 'Usuario Agregado al País',
      'template_updated': 'Plantilla Actualizada',
      'self_report_created': 'Informe Propio Creado',
      'deadline_reminder': 'Recordatorio de Fecha Límite',
      'search_audit_logs': 'Buscar registros de auditoría...',
      'home_screen_widget_title': 'Widget de inicio',
      'audit_widget_activity_types_hint':
          'Elija tipos de actividad para el widget. Sin selección, se muestran todos. Se guarda en este dispositivo.',
      'action': 'Acción',
      'all_actions': 'Todas las Acciones',
      'create': 'Crear',
      'update': 'Actualizar',
      'user': 'Usuario',
      'all_users': 'Todos los Usuarios',
      'from_date': 'Desde Fecha',
      'to_date': 'Hasta Fecha',
      'select_date': 'Seleccionar fecha',
      'no_description': 'Sin descripción',
      'search_api_endpoints': 'Buscar endpoints de API...',
      'http_method': 'Método HTTP',
      'all_methods': 'Todos los Métodos',
      'get': 'GET',
      'post': 'POST',
      'put': 'PUT',
      'delete_method': 'DELETE',
      'deprecated': 'Obsoleto',
      'beta': 'Beta',
      'new_api_key': 'Nueva Clave API',
      'time_range': 'Rango de Tiempo',
      'last_30_days': 'Últimos 30 Días',
      'last_90_days': 'Últimos 90 Días',
      'last_year': 'Último Año',
      'all_time': 'Todo el Tiempo',
      'metric': 'Métrica',
      'all_metrics': 'Todas las Métricas',
      'active_users': 'Usuarios Activos',
      'logins': 'Inicios de Sesión',
      'metric_submissions': 'Envíos',
      'page_views': 'Vistas de Página',
      'search_indicators': 'Buscar indicadores...',
      'category': 'Categoría',
      'all_categories': 'Todas las Categorías',
      'output': 'Salida',
      'outcome': 'Resultado',
      'impact': 'Impacto',
      'all_sectors': 'Todos los Sectores',
      'health': 'Salud',
      'wash': 'WASH',
      'shelter': 'Refugio',
      'education': 'Educación',
      'indicators': 'Indicadores',
      'new_indicator': 'Nuevo Indicador',
      'search_organizations': 'Buscar organizaciones...',
      'entity_type': 'Tipo de Entidad',
      'all_types': 'Todos los Tipos',
      'national_societies': 'Sociedades Nacionales',
      'ns_structure': 'Estructura NS',
      'secretariat': 'Secretariado',
      'divisions': 'Divisiones',
      'departments': 'Departamentos',
      'regional_offices': 'Oficinas Regionales',
      'cluster_offices': 'Oficinas de Cluster',
      'add_organization': 'Agregar Organización',
      'search_resources': 'Buscar recursos...',
      'no_indicators_found': 'No se encontraron indicadores',
      'no_organizations_found': 'No se encontraron organizaciones',
      'no_resources_found': 'No se encontraron recursos',
      'resources_unified_planning_section_title': 'Planes e informes unificados',
      'resources_unified_planning_section_subtitle':
          'Planes, informes de mitad de año e informes anuales desde IFRC GO (cargados en la app).',
      'unified_planning_empty':
          'Ningún documento de planificación unificada coincide con su búsqueda.',
      'unified_planning_fresh_badge': 'Reciente',
      'unified_planning_sort_by': 'Ordenar por',
      'unified_planning_sort_date_newest': 'Fecha: más reciente primero',
      'unified_planning_sort_date_oldest': 'Fecha: más antiguo primero',
      'unified_planning_sort_country_az': 'País: A–Z',
      'unified_planning_sort_country_za': 'País: Z–A',
      'unified_planning_filter_all_countries': 'Todos los países',
      'unified_error_config':
          'No se pudieron cargar los ajustes de planificación unificada desde el servidor. Inténtelo más tarde.',
      'unified_error_credentials':
          'Los documentos IFRC no están disponibles en esta aplicación. Póngase en contacto con el administrador.',
      'unified_error_ifrc_auth':
          'No se pudieron acceder a los documentos IFRC. Póngase en contacto con el administrador si el problema continúa.',
      'unified_error_ifrc':
          'No se pudieron cargar documentos desde IFRC GO. Compruebe la conexión e inténtelo de nuevo.',
      'no_plugins_found': 'No se encontraron complementos',
      'no_translations_found': 'No se encontraron traducciones',
      'no_documents_found': 'No se encontraron documentos',
      'no_users_found': 'No se encontraron usuarios',
      'loading_user_profile': 'Cargando perfil de usuario…',
      'failed_load_user_profile': 'No se pudo cargar este usuario.',
      'admin_user_detail_confirm_save_title': '¿Guardar cambios?',
      'admin_user_detail_confirm_save_message':
          'Actualizar el nombre, el cargo, el estado y las preferencias del perfil de este usuario.',
      'admin_user_detail_invalid_profile_color':
          'Introduzca un color válido como #RRGGBB (p. ej. #3B82F6).',
      'admin_user_detail_changes_saved': 'Cambios guardados.',
      'admin_user_detail_save_changes': 'Guardar cambios',
      'admin_user_detail_profile_color_label': 'Color del perfil',
      'admin_user_detail_profile_color_hint': '#RRGGBB',
      'admin_user_detail_cannot_deactivate_self':
          'No puede desactivar su propia cuenta.',
      'admin_user_detail_matrix_read_only_bundled':
          'Roles de administración agrupados (completos/núcleo/sistema): use la web para el acceso por área.',
      'admin_user_detail_rbac_incomplete':
          'No se pudo construir una lista de roles válida. Revise el acceso por área o reintente.',
      'assigned_roles_title': 'Roles asignados',
      'role_type_label': 'Tipo de rol',
      'permissions_by_role': 'Permisos por rol',
      'all_permissions_union': 'Todos los permisos (desde roles)',
      'entity_permissions_title': 'Permisos de entidad',
      'manage_users_detail_footer':
          'Para editar roles, acceso a entidades, dispositivos o notificaciones, use el formulario de usuario en la web.',
      'no_roles_assigned': 'No hay roles RBAC asignados.',
      'no_entities_assigned': 'Sin asignaciones de entidad.',
      'entity_permission_unnamed': 'Sin nombre',
      'entity_region_other': 'Otra región',
      'no_permissions_listed': 'No hay permisos listados para este rol.',
      'user_dir_assignment_roles': 'Roles de asignación',
      'user_dir_admin_roles': 'Admin y sistema',
      'user_dir_other_roles': 'Otros roles',
      'admin_role_access_area': 'Área',
      'admin_role_access_view': 'Ver',
      'admin_role_access_manage': 'Gestionar',
      'admin_role_de_heading': 'Explorador de datos',
      'admin_role_de_table': 'Tabla',
      'admin_role_de_analysis': 'Análisis',
      'admin_role_de_compliance': 'Cumplimiento',
      'admin_role_note_admin_full': 'Todos los permisos de administración (rol agrupado)',
      'admin_role_note_admin_core': 'Administración esencial básica (rol agrupado)',
      'admin_role_other_admin_roles': 'Otros roles de administración',
      'users_directory_role_all': 'Todos los roles',
      'users_directory_country_all': 'Todos los países',
      'no_assignments_found': 'No se encontraron asignaciones',
      'no_templates_found': 'No se encontraron plantillas',
      'assignment_deleted_successfully': 'Asignación eliminada exitosamente',
      'failed_to_delete_assignment': 'Error al eliminar asignación',
      'timeline_view': 'Vista de Línea de Tiempo',
      'view_all_public_submissions': 'Ver Todas las Presentaciones Públicas',
      'items_requiring_attention': 'Elementos que Requieren Atención',
      'recent_activity': 'Actividad Reciente',
      'recent_activity_7_days': 'Actividad Reciente (7 días)',
      'general_settings': 'Configuración General',
      'security_settings': 'Configuración de Seguridad',
      'system_settings': 'Configuración del Sistema',
      'application_settings': 'Configuración de la Aplicación',
      'language_settings': 'Configuración de Idioma',
      'notification_settings': 'Configuración de Notificaciones',
      'authentication_settings': 'Configuración de Autenticación',
      'permission_settings': 'Configuración de Permisos',
      'database_settings': 'Configuración de Base de Datos',
      'cloud_storage_settings': 'Configuración de Almacenamiento en la Nube',
      'configure_general_application_settings':
          'Configurar la configuración general de la aplicación',
      'manage_supported_languages_and_translations':
          'Gestionar idiomas y traducciones compatibles',
      'configure_notification_preferences':
          'Configurar preferencias de notificaciones',
      'configure_authentication_and_authorization':
          'Configurar autenticación y autorización',
      'manage_user_permissions_and_roles':
          'Gestionar permisos y roles de usuario',
      'configure_database_connections_and_backups':
          'Configurar conexiones de base de datos y copias de seguridad',
      'configure_cloud_storage_and_file_management':
          'Configurar almacenamiento en la nube y gestión de archivos',

      // Indicator Bank
      'indicator_bank_title': 'Banco de Indicadores',
      'indicator_bank_loading': 'Cargando Banco de Indicadores...',
      'indicator_bank_error': 'Algo salió mal',
      'indicator_bank_search_placeholder': 'Buscar indicadores...',
      'indicator_bank_filter_placeholder': 'Filtrar indicadores...',
      'indicator_bank_browse_description':
          'Explorar y buscar indicadores para respuesta humanitaria',
      'indicator_bank_grid_view': 'Vista de Cuadrícula',
      'indicator_bank_table_view': 'Vista de Tabla',
      'indicator_bank_show_filters': 'Mostrar Filtros',
      'indicator_bank_hide_filters': 'Ocultar Filtros',
      'indicator_bank_filters': 'Filtros',
      'indicator_bank_filter_type': 'Tipo',
      'indicator_bank_filter_type_all': 'Todos los Tipos',
      'indicator_bank_filter_sector': 'Sector',
      'indicator_bank_filter_sector_all': 'Todos los Sectores',
      'indicator_bank_filter_subsector': 'Subsector',
      'indicator_bank_filter_subsector_all': 'Todos los Subsectores',
      'indicator_bank_list_tier_also_related': 'También relacionados',
      'indicator_bank_filter_status': 'Estado',
      'indicator_bank_filter_status_active': 'Solo Activos',
      'indicator_bank_filter_status_all': 'Todos',
      'indicator_bank_apply_filters': 'Aplicar Filtros',
      'indicator_bank_clear_all': 'Limpiar Todo',
      'indicator_bank_showing': 'Mostrando',
      'indicator_bank_indicators': 'indicadores',
      'indicator_bank_indicator': 'indicador',
      'indicator_bank_no_sectors': 'No se encontraron sectores',
      'indicator_bank_no_indicators': 'No se encontraron indicadores',
      'indicator_bank_table_name': 'Nombre',
      'indicator_bank_table_type': 'Tipo',
      'indicator_bank_table_sector': 'Sector',
      'indicator_bank_table_subsector': 'Subsector',
      'indicator_bank_table_unit': 'Unidad',
      'indicator_bank_propose_new': 'Proponer Nuevo Indicador',
      'indicator_bank_propose_title': 'Proponer Nuevo Indicador',
      'indicator_bank_propose_contact_info': 'Información de Contacto',
      'indicator_bank_propose_your_name': 'Su Nombre *',
      'indicator_bank_propose_email': 'Dirección de Correo *',
      'indicator_bank_propose_indicator_info': 'Información del Indicador',
      'indicator_bank_propose_indicator_name': 'Nombre del Indicador *',
      'indicator_bank_propose_definition': 'Definición *',
      'indicator_bank_propose_type': 'Tipo',
      'indicator_bank_propose_unit': 'Unidad de Medida',
      'indicator_bank_propose_sector': 'Sector',
      'indicator_bank_propose_primary_sector': 'Sector Primario *',
      'indicator_bank_propose_secondary_sector': 'Sector Secundario',
      'indicator_bank_propose_tertiary_sector': 'Sector Terciario',
      'indicator_bank_propose_subsector': 'Subsector',
      'indicator_bank_propose_primary_subsector': 'Subsector Primario *',
      'indicator_bank_propose_secondary_subsector': 'Subsector Secundario',
      'indicator_bank_propose_tertiary_subsector': 'Subsector Terciario',
      'indicator_bank_propose_emergency': 'Contexto de Emergencia',
      'indicator_bank_propose_related_programs': 'Programas Relacionados',
      'indicator_bank_propose_reason': 'Razón de la Propuesta *',
      'indicator_bank_propose_additional_notes': 'Notas Adicionales',
      'indicator_bank_propose_submit': 'Enviar Propuesta',
      'indicator_bank_propose_thank_you': '¡Gracias!',
      'indicator_bank_propose_success':
          'Su propuesta de indicador se ha enviado exitosamente.',
      'indicator_bank_propose_failed':
          'Error al enviar la propuesta. Por favor intente nuevamente.',
      'indicator_bank_name_required': 'El nombre es requerido',
      'indicator_bank_email_required': 'El correo es requerido',
      'indicator_bank_indicator_name_required':
          'El nombre del indicador es requerido',
      'indicator_bank_definition_required': 'La definición es requerida',
      'indicator_bank_primary_sector_required':
          'El sector primario es requerido',
      'indicator_bank_primary_subsector_required':
          'El subsector primario es requerido',
      'indicator_bank_reason_required': 'La razón es requerida',

      // Indicator Detail
      'indicator_detail_title': 'Detalles del Indicador',
      'indicator_detail_loading': 'Cargando detalles del indicador...',
      'indicator_detail_error': 'Algo salió mal',
      'indicator_detail_not_found': 'Indicador no encontrado',
      'indicator_detail_go_back': 'Volver',
      'indicator_detail_definition': 'Definición',
      'indicator_detail_details': 'Detalles',
      'indicator_detail_type': 'Tipo',
      'indicator_detail_unit': 'Unidad',
      'indicator_detail_sector': 'Sector',
      'indicator_detail_subsector': 'Subsector',
      'indicator_detail_emergency_context': 'Contexto de Emergencia',
      'indicator_detail_related_programs': 'Programas Relacionados',
      'indicator_detail_status': 'Estado',
      'indicator_detail_archived': 'Archivado',
      'indicator_detail_yes': 'Sí',
      'editIndicator': 'Editar Indicador',

      // Quiz Game
      'quiz_game': 'Juego de Quiz',
      'quiz_game_title': 'Juego de Quiz',
      'quiz_game_test_your_knowledge': '¡Pon a prueba tus conocimientos!',
      'quiz_game_loading': 'Cargando quiz...',
      'quiz_game_error': 'Error al cargar quiz',
      'quiz_game_try_again': 'Intentar de Nuevo',
      'quiz_game_start_quiz': 'Iniciar Quiz',
      'quiz_game_which_sector': '¿A qué sector pertenece este indicador?',
      'quiz_game_which_subsector': '¿A qué subsector pertenece este indicador?',
      'quiz_game_definition': 'Definición',
      'quiz_game_no_definition': 'No hay definición disponible',
      'quiz_game_correct': '¡Correcto!',
      'quiz_game_incorrect': 'Incorrecto',
      'quiz_game_next_question': 'Siguiente Pregunta',
      'quiz_game_view_results': 'Ver Resultados',
      'quiz_game_quiz_complete': '¡Quiz Completado!',
      'quiz_game_excellent_work': '¡Excelente trabajo!',
      'quiz_game_well_done': '¡Bien hecho!',
      'quiz_game_good_effort': '¡Buen esfuerzo!',
      'quiz_game_keep_practicing': '¡Sigue practicando!',
      'quiz_game_out_of': 'de',
      'quiz_game_statistics': 'Estadísticas',
      'quiz_game_correct_answers': 'Correctas',
      'quiz_game_incorrect_answers': 'Incorrectas',
      'quiz_game_total': 'Total',
      'quiz_game_home': 'Inicio',
      'quiz_game_play_again': 'Jugar de Nuevo',
      'quiz_game_no_indicators_available': 'No hay indicadores con sectores o subsectores disponibles para el quiz',
      'quiz_game_failed_to_start': 'Error al iniciar el quiz',
      'quiz_game_leaderboard': 'Clasificación',
      'quiz_game_view_leaderboard': 'Ver Clasificación',
      'quiz_game_loading_leaderboard': 'Cargando clasificación...',
      'quiz_game_no_leaderboard_data': 'Aún no hay datos de clasificación disponibles',
      'quiz_game_top_players': 'Mejores Jugadores',
      'quiz_game_you': 'Tú',
      'quiz_game_points': 'Puntos',

      // AI Chat (immersive)
      'ai_policy_acknowledge_snackbar':
          'Reconozca la política de IA para continuar.',
      'ai_use_policy_title': 'Política de uso de IA',
      'ai_policy_do_not_share': 'No comparta información sensible.',
      'ai_policy_traces_body':
          'Usamos trazas del sistema y telemetría para mejorar el asistente. Sus mensajes pueden ser procesados por proveedores de IA externos.',
      'ai_policy_purpose_title': 'Finalidad',
      'ai_policy_purpose_body':
          'El asistente de IA le ayuda a explorar datos y documentos en esta plataforma. Puede responder sobre indicadores, países, asignaciones y buscar en documentos cargados.',
      'ai_policy_acceptable_use_title': 'Uso aceptable',
      'ai_policy_acceptable_use_body':
          '• Pregunte sobre datos de la plataforma, indicadores y documentos.\n'
          '• NO comparta contraseñas, credenciales ni detalles operativos altamente confidenciales.\n'
          '• NO pegue datos personales ni financieros.',
      'ai_policy_accuracy_title': 'Precisión',
      'ai_policy_accuracy_body':
          'La IA puede equivocarse o malinterpretar datos. Verifique siempre la información importante con los datos o documentos de origen.',
      'ai_policy_confirm_footer':
          'Confirme que ha leído la información anterior para usar el asistente.',
      'ai_policy_i_understand': 'Entiendo',
      'ai_policy_acknowledge_cta': 'Reconocer la política de uso de IA',
      'ai_sources_heading': 'Usar fuentes:',
      'ai_source_databank': 'Banco de datos',
      'ai_source_system_documents': 'Documentos del sistema',
      'ai_source_upr_documents': 'Documentos UPR',
      'ai_sources_minimum_note':
          'Al menos una fuente permanece activada (igual que en el asistente web).',
      'ai_tour_guide_question': '¿Quiere que le guíe por esto?',
      'ai_tour_navigate_question': '¿Quiere ir a la página correspondiente?',
      'ai_tour_web_only_snackbar':
          'Los recorridos interactivos están disponibles en la versión web. Abriendo la página...',
      'ai_new_chat': 'Nuevo chat',
      'ai_semantic_open_drawer_hint': 'Abre conversaciones y ajustes',
      'ai_tooltip_new_chat': 'Nuevo chat',
      'ai_semantic_new_chat_label': 'Nuevo chat',
      'ai_semantic_new_chat_hint': 'Inicia una conversación nueva vacía',
      'ai_beta_tester_banner':
          'Evaluador beta de IA: pueden estar activas funciones experimentales.',
      'ai_empty_welcome': '¿En qué puedo ayudarle hoy?',
      'ai_policy_chip_title': 'Política de uso de IA',
      'ai_policy_sheet_summary_line':
          'Resumen breve — abra la hoja para ver todos los detalles.',
      'ai_policy_compact_warning':
          'No comparta información sensible. Usamos trazas y telemetría para mejorar el asistente; los mensajes pueden ser procesados por proveedores de IA externos.',
      'ai_read_full_policy': 'Leer política completa',
      'ai_try_asking': 'Pruebe a preguntar',
      'ai_copied': '¡Copiado!',
      'ai_tooltip_copy': 'Copiar',
      'ai_tooltip_edit_message': 'Editar',
      'ai_tooltip_helpful': 'Útil',
      'ai_tooltip_not_helpful': 'No útil',
      'ai_footer_model_warning':
          'La IA puede equivocarse. Compruebe la información importante.',
      'ai_chat_error_network':
          'No se pudo conectar con el servicio de IA. Compruebe su conexión a internet e inténtelo de nuevo.',
      'ai_chat_error_timeout':
          'La solicitud tardó demasiado. Compruebe su conexión e inténtelo de nuevo.',
      'ai_chat_error_server': 'Algo salió mal. Inténtelo de nuevo.',
      'ai_agent_progress_title': 'Pasos en curso',
      'ai_agent_step_done': 'Hecho.',
      'ai_agent_step_preparing_query': 'Preparando la consulta…',
      'ai_agent_step_planning': 'Planificando el enfoque…',
      'ai_agent_step_reviewing': 'Revisando resultados…',
      'ai_agent_step_drafting': 'Redactando la respuesta…',
      'ai_agent_step_replying': 'Respondiendo…',
      'ai_agent_step_thinking_next': 'Pensando qué hacer a continuación.',
      'ai_agent_step_no_shortcut_full':
          'Sin atajo de una sola herramienta — usando la planificación completa.',
      'ai_agent_step_no_shortcut_reviewing':
          'Sin atajo de una sola herramienta para esta solicitud — revisando: %s',
      'ai_response_sources': 'Fuentes',
      'ai_response_sources_with_count': 'Fuentes (%s)',
      'ai_tooltip_configure_sources': 'Configurar fuentes de datos',
      'ai_input_policy_required':
          'Reconozca la política de IA arriba para enviar mensajes',
      'ai_input_placeholder_message': 'Mensaje',
      'ai_input_placeholder_edit': 'Editar mensaje…',
      'ai_tooltip_cancel_edit': 'Cancelar edición',
      'ai_stop': 'Detener',
      'ai_conversations_drawer_title': 'Conversaciones',
      'ai_search_conversations_hint': 'Buscar conversaciones',
      'ai_no_conversations_body':
          'Aún no hay conversaciones.\n¡Inicie un nuevo chat!',
      'ai_no_conversations_offline':
          'Aún no hay conversaciones.\nInicie un nuevo chat (sin conexión).',
      'ai_no_conversations_filtered': 'No se encontraron conversaciones',
      'ai_section_pinned': 'Fijadas',
      'ai_section_recent': 'Recientes',
      'ai_quick_prompt_1': '¿Cuántos voluntarios en Bangladesh?',
      'ai_quick_prompt_2': 'Voluntarios en Siria a lo largo del tiempo',
      'ai_quick_prompt_3': 'Mapa mundial de calor de voluntarios por país',
      'ai_quick_prompt_4': 'Número de sucursales en Kenia',
      'ai_quick_prompt_5': 'Personal y unidades locales en Nigeria',
      'ai_clear_all_dialog_title': 'Borrar todas las conversaciones',
      'ai_clear_all_dialog_body':
          '¿Seguro que desea eliminar todas las conversaciones? Esta acción no se puede deshacer.',
      'ai_clear_all_button': 'Borrar todo',
      'ai_clear_all_row': 'Borrar todas las conversaciones',
      'ai_help_about_row': 'Ayuda e información',
      'ai_pin': 'Fijar',
      'ai_unpin': 'Desfijar',
      'ai_delete_conversation_title': '¿Eliminar conversación?',
      'ai_delete_conversation_body':
          '¿Eliminar esta conversación? No se puede deshacer.',
      'ai_new_chat_title_fallback': 'Nuevo chat',
      'ai_help_dialog_title': 'Ayuda del asistente de IA',
      'ai_help_about_heading': 'Acerca de',
      'ai_help_about_paragraph':
          'El asistente de IA le ayuda a encontrar información y responder preguntas sobre el Banco de Datos de la Red IFRC.',
      'ai_help_features_heading': 'Funciones',
      'ai_help_feature_bullet_1':
          '• Haga preguntas sobre asignaciones, recursos y más',
      'ai_help_feature_bullet_2': '• Obtenga ayuda para navegar por la app',
      'ai_help_feature_bullet_3':
          '• Busque en el historial de conversaciones',
      'ai_help_feature_bullet_4':
          '• Las conversaciones se guardan cuando ha iniciado sesión',
      'ai_help_tips_heading': 'Consejos',
      'ai_help_tip_bullet_1':
          '• Sea específico en sus preguntas para mejores resultados',
      'ai_help_tip_bullet_2':
          '• Toque los enlaces en las respuestas para ir a páginas relacionadas',
      'ai_help_tip_bullet_3':
          '• Use la barra de búsqueda para encontrar conversaciones anteriores',
      'ai_help_tip_bullet_4':
          '• Mantenga pulsada una conversación para abrir el menú (fijar o eliminar)',
      'ai_got_it': 'Entendido',
      'ai_score_confidence': 'Confianza',
      'ai_score_grounding': 'Fundamentación',
      'ai_default_assistant_title': 'Asistente de IA',
      'resources_other_subgroup': 'Otros',
      'resources_list_truncated_hint':
          'Se muestran los elementos más recientes. Use la búsqueda para encontrar un documento concreto.',
      'ai_assistant': 'Asistente de IA',
    },
    'fr': {
      'app_name': 'Banque de Données du Réseau IFRC',
      'navigation': 'Navigation',
      'home': 'Accueil',
      'dashboard': 'Tableau de bord',
      'resources': 'Ressources',
      'indicator_bank': 'Banque d\'Indicateurs',
      'disaggregation_analysis': 'Analyse de Désagrégation',
      'analysis': 'Analyse',
      'data_visualization': 'Visualisation des Données',
      'settings': 'Paramètres',
      'notifications': 'Notifications',
      'admin': 'Administration',
      'admin_panel': 'Panneau d\'Administration',
      'customize_tabs': 'Personnaliser les Onglets',
      'customize_tabs_description': 'Sélectionnez les onglets à afficher et faites-les glisser pour les réorganiser.',
      'reset_to_default': 'Réinitialiser',
      'tab_always_shown': 'Toujours affiché',
      'minimum_tabs_warning': 'Vous devez garder au moins 2 onglets visibles.',
      'access_denied': 'Accès Refusé',
      'general': 'Général',
      'document_management': 'Gestion des Documents',
      'translation_management': 'Gestion des Traductions',
      'plugin_management': 'Gestion des Plugins',
      'system_configuration': 'Configuration du Système',
      'user_management': 'Gestion des Utilisateurs',
      'manage_users': 'Gérer les Utilisateurs',
      'access_requests_title': 'Demandes d\'accès par pays',
      'access_requests_subtitle':
          'Approuvez ou refusez les demandes d\'accès au niveau pays.',
      'access_requests_pending': 'En attente',
      'access_requests_processed': 'Décisions récentes',
      'access_requests_empty': 'Aucune demande d\'accès.',
      'access_requests_approve': 'Approuver',
      'access_requests_reject': 'Refuser',
      'access_requests_approve_all': 'Tout approuver',
      'access_requests_approve_all_confirm':
          'Approuver toutes les demandes d\'accès par pays en attente ?',
      'access_requests_reject_confirm':
          'Refuser cette demande d\'accès ? L\'utilisateur n\'obtiendra pas l\'accès.',
      'access_requests_country': 'Pays',
      'access_requests_message': 'Message',
      'access_requests_requested_at': 'Demandé',
      'access_requests_processed_at': 'Traité',
      'access_requests_auto_approve_hint':
          'L\'approbation automatique peut être activée dans les paramètres du serveur.',
      'access_requests_status_pending': 'En attente',
      'access_requests_status_approved': 'Approuvé',
      'access_requests_status_rejected': 'Refusé',
      'access_requests_by': 'Par',
      'access_requests_load_failed':
          'Impossible de charger les demandes d\'accès.',
      'access_requests_action_failed':
          'L\'action n\'a pas pu être effectuée.',
      'access_requests_view_forbidden':
          'Vous n\'avez pas l\'autorisation de consulter les demandes d\'accès sur le serveur.',
      'access_requests_unexpected_response':
          'Réponse inattendue du serveur.',
      'access_requests_action_forbidden':
          'Vous n\'avez pas l\'autorisation d\'effectuer cette action.',
      'users_directory_read_only':
          'Annuaire en lecture seule. Créez ou modifiez les comptes sur le backoffice web.',
      'login_logs_title': 'Journaux de connexion',
      'login_logs_filters': 'Filtres',
      'login_logs_email_hint': 'Rechercher par e-mail',
      'login_logs_event_type': "Type d'événement",
      'login_logs_event_all': 'Tous les types',
      'login_logs_event_login': 'Connexion',
      'login_logs_event_logout': 'Déconnexion',
      'login_logs_event_failed': 'Échec de connexion',
      'login_logs_ip_label': 'Adresse IP',
      'login_logs_date_from': 'Du',
      'login_logs_date_to': 'Au',
      'login_logs_suspicious_only': 'Suspects uniquement',
      'login_logs_apply': 'Appliquer',
      'login_logs_clear': 'Effacer',
      'login_logs_no_entries': 'Aucun événement ne correspond aux filtres.',
      'login_logs_total': '%s événements au total',
      'login_logs_load_more': 'Charger plus',
      'login_logs_user_not_resolved': 'Aucun compte utilisateur correspondant',
      'login_logs_device': 'Appareil',
      'login_logs_browser': 'Navigateur',
      'login_logs_suspicious_badge': 'Suspect',
      'login_logs_recent_failures': '%s échecs récents',
      'login_logs_open': 'Journaux de connexion',
      'session_logs_title': 'Journaux de session',
      'admin_filters': 'Filtres',
      'session_logs_email_hint': 'Rechercher par e-mail',
      'session_logs_min_duration': 'Minutes min. (session ou actif)',
      'session_logs_active_only': 'Sessions actives uniquement',
      'admin_filters_apply': 'Appliquer',
      'admin_filters_clear': 'Effacer',
      'session_logs_no_entries': 'Aucune session ne correspond aux filtres.',
      'session_logs_total': '%s sessions au total',
      'session_logs_load_more': 'Charger plus',
      'session_logs_session_start': 'Début de session',
      'session_logs_duration': 'Durée',
      'session_logs_session_length': 'Durée de session',
      'session_logs_active_time': 'Temps actif',
      'session_logs_minutes': '%s min',
      'session_logs_page_views': 'Pages vues',
      'session_logs_path_breakdown_title': 'Pages vues par chemin',
      'session_logs_path_breakdown_open': 'Voir le détail des chemins',
      'session_logs_path_breakdown_empty':
          'Aucun détail de chemin pour cette session.',
      'session_logs_path_other_bucket': 'Autres chemins (agrégés)',
      'session_logs_path_column': 'Chemin',
      'session_logs_path_count_column': 'Nombre',
      'session_logs_distinct_paths': 'Chemins distincts',
      'session_logs_activities': 'Activités',
      'session_logs_last_activity': 'Dernière activité',
      'session_logs_status_active': 'Active',
      'session_logs_status_ended': 'Terminée',
      'session_logs_force_logout': 'Forcer la déconnexion',
      'session_logs_force_logout_confirm':
          'Forcer la déconnexion de cet utilisateur ? Il sera déconnecté immédiatement.',
      'session_logs_unknown_user': 'Utilisateur inconnu',
      'session_logs_no_activity': 'Aucune activité',
      'session_logs_open': 'Journaux de session',
      'session_logs_ended_ok': 'Session terminée.',
      'session_logs_os': 'OS',
      'session_logs_user_agent': 'Agent utilisateur',
      'session_logs_device_section': 'Détails de l’appareil',
      'form_data_management': 'Gestion des Formulaires et Données',
      'manage_templates': 'Gérer les Modèles',
      'manage_assignments': 'Gérer les Affectations',
      'frontend_management': 'Gestion du Website',
      'manage_resources': 'Gérer les Ressources',
      'reference_data': 'Données de Référence',
      'organizational_structure': 'Structure Organisationnelle',
      'analytics_monitoring': 'Analyse et Surveillance',
      'user_analytics': 'Analyse des Utilisateurs',
      'audit_trail': 'Piste d\'Audit',
      'api_management': 'Gestion de l\'API',
      'account_settings': 'Paramètres du Compte',
      'profile': 'Profil',
      'preferences': 'Préférences',
      'language': 'Langue',
      'select_language': 'Sélectionner la Langue',
      'change_password': 'Changer le Mot de Passe',
      'profile_color': 'Couleur du Profil',
      'chatbot': 'Chatbot',
      'enable_chatbot_assistance': 'Activer l\'assistance chatbot',
      'dark_theme': 'Thème Sombre',
      'enable_dark_theme': 'Activer le thème sombre',
      'settings_theme': 'Thème',
      'light_theme': 'Thème clair',
      'system_theme': 'Système',
      'select_theme': 'Choisir le thème',
      'settings_theme_set_to': 'Thème défini sur %s',
      'arabic_text_font': 'Police arabe',
      'arabic_font_tajawal': 'Tajawal',
      'arabic_font_system': 'Police système',
      'login_to_account': 'Se Connecter',
      'logout': 'Déconnexion',
      'are_you_sure_logout': 'Êtes-vous sûr de vouloir vous déconnecter?',
      'cancel': 'Annuler',
      'name': 'Nom',
      'title': 'Titre',
      'email': 'E-mail',
      'loading': 'Chargement...',
      'loading_home': 'Chargement de l\'Accueil...',
      'home_landing_hero_description':
          'Explorez les données humanitaires complètes, les indicateurs et les insights de la Fédération Internationale des Sociétés de la Croix-Rouge et du Croissant-Rouge.',
      'home_landing_chat_title': 'Chat avec nos données',
      'home_landing_chat_description': 'Tapez vos questions sur les données de la plateforme ci-dessous.',
      'home_landing_ask_placeholder': 'Posez des questions sur le financement, les programmes, les pays...',
      'home_landing_quick_prompt_1': 'Parlez-moi des bénévoles du Croissant-Rouge afghan',
      'home_landing_quick_prompt_2': 'Montrez-moi les données mondiales de réponse aux catastrophes',
      'home_landing_quick_prompt_3': 'Quels sont les indicateurs humanitaires clés ?',
      'home_landing_shortcuts_heading': 'Pour commencer',
      'home_landing_shortcut_indicators_subtitle': 'Parcourir définitions et métadonnées',
      'home_landing_shortcut_resources_subtitle': 'Publications et ressources',
      'home_landing_shortcut_countries_subtitle': 'Profils et vues régionales',
      'home_landing_shortcut_disaggregation_subtitle': 'Décomposer les valeurs d\'indicateurs',
      'home_landing_explore_title': 'Carte mondiale et graphiques',
      'home_landing_explore_subtitle':
          'Carte et graphique natifs avec les mêmes totaux FDRS que le site web, sans quitter l’application.',
      'home_landing_global_indicator_volunteers': 'Bénévoles',
      'home_landing_global_indicator_staff': 'Personnel',
      'home_landing_global_indicator_branches': 'Antennes',
      'home_landing_global_indicator_local_units': 'Local units',
      'home_landing_global_indicator_blood_donors': 'Blood donors',
      'home_landing_global_indicator_first_aid': 'First aid',
      'home_landing_global_indicator_people_reached': 'People reached',
      'home_landing_global_indicator_income': 'Income',
      'home_landing_global_indicator_expenditure': 'Expenditure',
      'home_landing_global_top_countries': 'Principaux pays',
      'home_landing_global_load_error':
          'Impossible de charger les données de la carte. Vérifiez votre connexion et réessayez.',
      'home_landing_global_empty':
          'Aucune valeur pour cet indicateur sur la dernière période.',
      'home_landing_global_period': 'Période : %s',
      'home_landing_global_map_hint':
          'Pincez, faites glisser et touchez un pays pour les détails',
      'home_landing_global_map_open_fullscreen': 'Plein écran',
      'home_landing_global_period_filter_label': 'Période de reporting',
      'home_landing_global_map_mode_bubble': 'Bulles',
      'home_landing_global_map_mode_choropleth': 'Choroplète',
      'home_landing_global_map_zoom_in': 'Zoom avant',
      'home_landing_global_map_zoom_out': 'Zoom arrière',
      'home_landing_global_map_reset_bounds': 'Ajuster aux données',
      'home_landing_global_map_legend_low': 'Faible',
      'home_landing_global_map_legend_high': 'Élevé',
      'home_landing_global_map_country_no_data':
          'Aucune donnée pour cet indicateur',
      'home_landing_global_map_value_label': 'Valeur',
      'home_landing_global_map_country_trend': 'Par période de déclaration',
      'home_landing_global_map_filters_title': 'Options de la carte',
      'loading_page': 'Chargement de la page...',
      'loading_preferences': 'Chargement des préférences...',
      'loading_notifications': 'Chargement des notifications...',
      'loading_dashboard': 'Chargement du tableau de bord...',
      'loading_audit_logs': 'Chargement des journaux d\'audit...',
      'loading_analytics': 'Chargement des analyses...',
      'loading_organizations': 'Chargement des organisations...',
      'loading_templates': 'Chargement des modèles...',
      'loading_assignments': 'Chargement des affectations...',
      'loading_translations': 'Chargement des traductions...',
      'loading_plugins': 'Chargement des plugins...',
      'loading_resources': 'Chargement des ressources...',
      'loading_indicators': 'Chargement des indicateurs...',
      'loading_documents': 'Chargement des documents...',
      'loading_api_endpoints': 'Chargement des points de terminaison API...',
      'loading_users': 'Chargement des utilisateurs...',
      'error': 'Erreur',
      'retry': 'Réessayer',
      'refresh': 'Actualiser',
      'close': 'Fermer',
      'save': 'Enregistrer',
      'saved': 'Enregistré',
      'success': 'Succès',
      'oops_something_went_wrong': 'Oups! Quelque chose s\'est mal passé',
      'go_back': 'Retour',
      'edit': 'Modifier',
      'duplicate': 'Dupliquer',
      'preview': 'Aperçu',
      'download_started': 'Téléchargement démarré',
      'could_not_start_download': 'Impossible de démarrer le téléchargement',
      'could_not_open_download_link': 'Impossible d\'ouvrir le lien de téléchargement',
      'error_opening_download': 'Erreur lors de l\'ouverture du téléchargement',
      'please_select_at_least_one_user': 'Veuillez sélectionner au moins un utilisateur',
      'indicator_updated_successfully': 'Indicateur mis à jour avec succès',
      'failed_to_load_indicator': 'Échec du chargement de l\'indicateur',
      'user_deleted': 'Utilisateur supprimé',
      'public_url_copied': 'URL publique copiée dans le presse-papiers!',
      'please_use_web_interface': 'Veuillez utiliser l\'interface Web pour enregistrer les modifications de l\'entité',
      'open_in_web_browser': 'Ouvrir dans le Navigateur Web',
      'countries': 'Pays',
      'all_roles': 'Tous les Rôles',
      'admin_role': 'Administrateur',
      'focal_point_role': 'Point Focal',
      'system_manager_role': 'Gestionnaire Système',
      'viewer_role': 'Visualiseur',
      'all_status': 'Tous les États',
      'active_status': 'Actif',
      'inactive_status': 'Inactif',
      'normal_priority': 'Normal',
      'high_priority': 'Élevé',
      'none': 'Aucun',
      'app_screen': 'Écran de l\'Application',
      'custom_url': 'URL Personnalisée',
      'create_template': 'Créer un Modèle',
      'delete_template': 'Supprimer le Modèle',
      'create_assignment': 'Créer une Affectation',
      'delete_assignment': 'Supprimer l\'Affectation',
      'edit_document': 'Modifier le Document',
      'preview_document': 'Aperçu du Document',
      'download_document': 'Télécharger le Document',
      'upload_document': 'Télécharger le Document',
      'new_translation': 'Nouvelle Traduction',
      'new_resource': 'Nouvelle Ressource',
      'install_plugin': 'Installer le Plugin',
      'template_deleted_successfully': 'Modèle supprimé avec succès',
      'failed_to_delete_template': 'Échec de la suppression du modèle',
      'error_loading_page': 'Erreur lors du chargement de la page',
      'no_notifications': 'Aucune notification',
      'all_caught_up': 'Vous êtes à jour',
      'notifications_load_more': 'Charger plus',
      'notifications_filter': 'Filtres',
      'notifications_filter_title': 'Filtrer les notifications',
      'notifications_filter_read_status': 'État de lecture',
      'notifications_filter_all': 'Toutes',
      'notifications_filter_unread_only': 'Non lues seulement',
      'notifications_filter_type': 'Type',
      'notifications_filter_type_any': 'Tous les types',
      'notifications_filter_from': 'De',
      'notifications_filter_from_any': 'Tout le monde',
      'notifications_filter_from_empty_hint':
          'Les personnes apparaissent lorsque leurs notifications figurent dans la liste chargée. Utilisez Charger plus.',
      'notifications_filter_priority': 'Priorité',
      'notifications_filter_priority_any': 'Toute priorité',
      'notifications_filter_priority_normal': 'Normale',
      'notifications_filter_priority_high': 'Haute',
      'notifications_filter_priority_urgent': 'Urgente',
      'notifications_filter_apply': 'Appliquer',
      'notifications_filter_reset': 'Réinitialiser',
      'notifications_filter_no_matches_loaded':
          'Aucune notification ne correspond aux filtres dans la liste chargée. Chargez plus ou modifiez les filtres.',
      'mark_all_read': 'Tout marquer comme lu',
      'mark_read': 'Marquer comme lu',
      'mark_unread': 'Marquer comme non lu',
      'delete': 'Supprimer',
      'archive': 'Archiver',
      'unarchive': 'Désarchiver',
      'send_push_notification': 'Envoyer une Notification Push',
      'admin_push_user_ids_label': 'ID utilisateurs destinataires',
      'admin_push_user_ids_hint':
          'ID numériques séparés par des virgules (voir Utilisateurs).',
      'admin_push_user_ids_invalid':
          'Saisissez un ou plusieurs ID numériques, séparés par des virgules.',
      'select_users': 'Sélectionner les Utilisateurs',
      'search_users': 'Rechercher des utilisateurs par nom ou e-mail',
      'redirect_url': 'Rediriger (Optionnel)',
      'login': 'Connexion',
      'log_in': 'Se Connecter',
      'phone_username_email': 'Téléphone, nom d\'utilisateur ou e-mail',
      'forgot_password_coming_soon': 'Fonction de mot de passe oublié à venir',
      'please_enter_email': 'Veuillez entrer votre e-mail',
      'please_enter_valid_email': 'Veuillez entrer un e-mail valide',
      'please_enter_password': 'Veuillez entrer votre mot de passe',
      'show': 'Afficher',
      'hide': 'Masquer',
      'or': 'OU',
      'dont_have_account': 'Vous n\'avez pas de compte?',
      'sign_up': 'S\'inscrire',
      'registration_coming_soon': 'Fonction d\'inscription à venir',
      'quick_login_testing': 'Connexion Rapide pour les Tests',
      'test_as_admin': 'Tester en tant qu\'Administrateur',
      'test_as_focal_point': 'Tester en tant que Point Focal',
      'public_login_disabled':
          'La connexion publique est temporairement désactivée',
      'tester_accounts_info':
          'Les comptes de test peuvent toujours se connecter en utilisant les boutons ci-dessus.',
      'could_not_open_azure_login': 'Impossible d\'ouvrir la connexion Azure',
      'login_with_ifrc_account': 'Se connecter avec le compte IFRC',
      'use_ifrc_federation_account':
          'Utilisez votre compte de la Fédération IFRC pour vous connecter',
      'your_account_or_create_account': 'Votre compte ou créer un compte',
      'login_failed': 'Échec de la connexion',
      'email_address': 'Adresse E-mail',
      'password': 'Mot de Passe',
      'remember_me': 'Se souvenir de moi',
      'forgot_password': 'Mot de passe oublié?',
      'language_changed_to': 'Langue changée en',

      // Splash Screen
      'welcome_to_ifrc_network_databank':
          'Bienvenue dans la Banque de Données du Réseau IFRC',
      'splash_description':
          'C\'est le seul système pour rapporter des données à la FICR. Dites adieu aux fichiers Excel dispersés, aux formulaires KoBo, aux multiples plateformes et connexions — tout est maintenant centralisé et rationalisé ici.',
      'powered_by_hum_databank': 'Propulsé par Humanitarian Databank',
      'open_on_github': 'Ouvrir sur GitHub',

      // Dashboard
      'national_society': 'Société Nationale',
      'active': 'Actif',
      'completed': 'Terminé',
      'current_assignments': 'Assignations Actuelles',
      'dashboard_you_have_no_open_assignments':
          'Vous n\'avez aucune assignation ouverte',
      'dashboard_you_have_one_open_assignment':
          'Vous avez 1 assignation ouverte',
      'dashboard_you_have_open_assignments_count':
          'Vous avez %s assignations ouvertes',
      'past_assignments': 'Assignations Passées',
      'assignments_for': 'Assignations pour',
      'past_submissions_for': 'Soumissions Passées pour',
      'something_went_wrong': 'Quelque chose s\'est mal passé',
      'no_assignments_yet':
          'Tout est clair ! Aucune assignation active pour le moment.',
      'new_assignments_will_appear':
          'Les nouvelles assignations apparaîtront ici lorsqu\'elles seront disponibles.',
      'get_started_by_creating': 'Commencez par créer une nouvelle assignation',
      'filters': 'Filtres',
      'period': 'Période',
      'template': 'Modèle',
      'status': 'Statut',
      'clear': 'Effacer',
      'approved': 'Approuvé',
      'requires_revision': 'Nécessite une Révision',
      'pending': 'En Attente',
      'in_progress': 'En Cours',
      'submitted': 'Soumis',
      'other': 'Autre',
      'entities': 'Entités',
      'search_placeholder': 'Rechercher...',
      'no_results_found': 'Aucun résultat trouvé',
      'entity_type_country': 'Pays',
      'entity_type_ns_branch': 'Branche SN',
      'entity_type_ns_sub_branch': 'Sous-Branche SN',
      'entity_type_ns_local_unit': 'Unité Locale SN',
      'entity_type_division': 'Division',
      'entity_type_department': 'Département',
      'delete_assignment_confirm_message':
          'Êtes-vous sûr de vouloir supprimer cette assignation et tous ses statuts de pays et données associés ?',
      'no_assignments_match_filters':
          'Aucune assignation ne correspond aux filtres sélectionnés',
      'form': 'Formulaire',
      'last_updated': 'Dernière Mise à Jour',
      'actions': 'Actions',
      'all_years': 'Toutes les Années',
      'all_templates': 'Tous les Modèles',
      'all_statuses': 'Tous les Statuts',
      'template_missing': 'Modèle Manquant',
      'self_reported': 'Auto-Déclaré',
      'no_actions_available': 'Aucune action disponible',
      'previous': 'Précédent',
      'next': 'Suivant',
      'showing': 'Affichage',
      'to': 'à',
      'of': 'de',
      'results': 'résultats',
      'no_past_assignments_for': 'Aucune assignation passée pour',
      'yet': 'encore.',
      'submission_history_and_data_quality_for':
          'Historique des Soumissions et Qualité des Données pour',
      'overall_performance': 'Performance Globale',
      'average_completion_rate_past_3_periods':
          'Taux de Complétion Moyen (3 Dernières Périodes)',
      'average_submission_timeliness':
          'Ponctualité Moyenne des Soumissions (Jours en Avance/Retard)',
      'data_quality_index_fake_metric':
          'Indice de Qualité des Données (Métrique Factice)',
      'number_of_revisions_requested_past_year':
          'Nombre de Révisions Demandées (Année Passée)',
      'trend_analysis': 'Analyse des Tendances',
      'recent_activities': 'Activités Récentes',
      'last_7_days': '7 derniers jours',
      'unknown_user': 'Utilisateur Inconnu',
      'added': 'Ajouté',
      'updated': 'Mis à Jour',
      'removed': 'Supprimé',
      'show_less': 'Afficher moins',
      'more_change': 'changement de plus',
      'no_recent_activities': 'Aucune activité récente',
      'activities_from_other_focal_points_in':
          'Activités d\'autres points focaux dans',
      'will_appear_here': 'apparaîtront ici',
      'focal_points_for': 'Points Focaux pour',
      'national_society_focal_points': 'Points Focaux de la Société Nationale',
      'ifrc_focal_points': 'Points Focaux de la FICR',
      'no_focal_points_assigned_to': 'Aucun point focal assigné à',
      'your_user_account_not_associated':
          'Votre compte utilisateur n\'est associé à aucun pays.',
      'please_contact_administrator': 'Veuillez contacter un administrateur.',
      'due_date': 'Date d\'Échéance',
      'no_due_date': 'Aucune date d\'échéance',
      'overdue': 'En Retard',
      'latest_submission': 'Dernière Soumission',
      'submitted_through_public_link': 'Soumis via lien public',
      'submission': 'soumission',
      'submissions': 'soumissions',
      'completion': 'Complétion',
      'received_1_submission_using_public_link':
          'Reçu 1 soumission en utilisant le lien public',
      'received_count_submissions_using_public_link':
          'Reçu %(count)d soumissions en utilisant le lien public',
      'at_datetime': 'à: %(datetime)s',
      'latest_datetime': 'Dernier: %(datetime)s',
      'last_modified_by': 'Dernière modification par',
      'assignment_assigned_date': 'Assigné',
      'assignment_status_updated': 'Statut mis à jour',
      'contributors': 'Contributeurs',
      'assignment_submitted_by': 'Soumis par',
      'assignment_approved_by': 'Approuvé par',
      'public_link_enabled': 'Lien public activé',
      'public_link': 'Lien public',
      'unknown': 'Inconnu',
      'n_a': 'N/A',
      'enter_data': 'Saisir les Données',
      'download_for_offline': 'Télécharger pour hors ligne',
      'downloading_offline_form': 'Téléchargement du formulaire pour utilisation hors ligne…',
      'offline_form_saved': 'Formulaire enregistré pour un accès hors ligne.',
      'offline_form_save_failed': 'Impossible d’enregistrer le formulaire hors ligne. Réessayez avec une connexion stable.',
      'offline_form_not_downloaded': 'Ce formulaire n’est pas disponible hors ligne. Téléchargez-le en étant connecté.',
      'offline_download_requires_connection': 'Connectez-vous à Internet pour télécharger ce formulaire pour une utilisation hors ligne.',
      'offline_form_export_requires_connection':
          'Connectez-vous à Internet pour exporter PDF, Excel ou rapports de validation. La copie hors ligne n’inclut pas les exports.',
      'offline_open_saved_copy': 'Ouvrir la copie hors ligne enregistrée',
      'remove_offline_copy': 'Supprimer la copie hors ligne',
      'offline_form_removed':
          'Copie hors ligne supprimée. Téléchargez à nouveau en ligne.',
      'offline_saved_copy_details_tooltip':
          'Copie hors ligne — détails et suppression',
      'offline_copy_sheet_title': 'Copie hors ligne du formulaire',
      'offline_copy_saved_on_label': 'Enregistrée le',
      'offline_copy_files_cached': '%(count)d ressources mises en cache',
      'offline_stale_bundle_banner_title':
          'Mise à jour des formulaires hors ligne requise',
      'offline_stale_bundle_banner_body_online':
          'Le formulaire en ligne a changé. L’appareil actualise les copies hors ligne automatiquement lorsqu’il est connecté. Sinon, ouvrez chaque formulaire avec l’avertissement puis appuyez sur Mettre à jour la copie hors ligne.',
      'offline_stale_bundle_banner_body_offline':
          'Le formulaire en ligne a changé. Connectez-vous à Internet pour que l’appareil puisse actualiser les copies hors ligne automatiquement.',
      'offline_stale_bundle_updates_snackbar':
          'Les copies hors ligne ont été mises à jour vers la dernière version.',
      'offline_stale_bundle_partial_refresh':
          'Certaines copies hors ligne n’ont pas pu être mises à jour. Touchez l’avertissement sur un formulaire, puis Mettre à jour la copie hors ligne.',
      'offline_stale_bundle_sheet_notice':
          'Cette copie hors ligne peut ne plus correspondre au formulaire en ligne actuel. Mettez-la à jour pour éviter des problèmes de version.',
      'offline_stale_bundle_update_now': 'Mettre à jour la copie hors ligne',
      'approve': 'Approuver',
      'reopen': 'Rouvrir',
      'view_public_submissions': 'Voir les Soumissions Publiques',
      'view_submission': 'Voir la Soumission',
      'view_submissions': 'Voir les Soumissions',
      'open_form': 'Ouvrir le Formulaire',
      'no_forms_assigned_or_submitted_for':
          'Aucun formulaire n\'a été assigné ou soumis via des liens publics pour',
      'admins_can_assign_forms':
          'Les administrateurs peuvent assigner des formulaires ou créer des liens publics via le Tableau de Bord d\'Administration.',
      'create_a_report': 'Créer un Rapport',
      'delete_self_reported_assignment':
          'Supprimer l\'Assignation Auto-Déclarée',
      'quick_actions': 'Actions Rapides',
      'new_assignment': 'Nouvelle Assignation',
      'new_template': 'Nouveau Modèle',
      'key_metrics': 'Métriques Clés',
      'overview': 'Aperçu',
      'create_new_assignment': 'Créer une nouvelle assignation',
      'templates': 'Modèles',
      'browse_available_templates': 'Parcourir les modèles disponibles',
      'enter_your_name': 'Entrez votre nom',
      'enter_your_job_title': 'Entrez votre titre de poste',
      'edit_name': 'Modifier le Nom',
      'edit_title': 'Modifier le Titre',
      'name_cannot_be_empty': 'Le nom ne peut pas être vide',
      'title_cannot_be_empty': 'Le titre ne peut pas être vide',
      'profile_updated_successfully': 'Profil mis à jour avec succès',
      'error_updating_profile': 'Erreur lors de la mise à jour du profil',
      'color_picker_coming_soon': 'Sélecteur de couleur à venir',
      'chatbot_preference_update_coming_soon':
          'Mise à jour des préférences du chatbot à venir',
      'select_color': 'Sélectionnez une couleur',
      'current_color': 'Couleur Actuelle',
      'profile_color_updated': 'Couleur de profil mise à jour avec succès',
      'profile_color_update_failed':
          'Échec de la mise à jour de la couleur de profil',
      'admin_dashboard': 'Tableau de Bord Administrateur',
      'no_data_available': 'Aucune donnée disponible',
      'total_users': 'Total des Utilisateurs',
      'admins': 'Administrateurs',
      'system_administrators': 'Administrateurs système',
      'focal_points': 'Points Focaux',
      'country_focal_points': 'Points focaux du pays',
      'form_templates': 'Modèles de formulaires',
      'active_assignments': 'Assignations actives',
      'todays_logins': 'Connexions d\'Aujourd\'hui',
      'successful_logins_today': 'Connexions réussies aujourd\'hui',
      'pending_submissions': 'Soumissions en Attente',
      'overdue_assignments': 'Assignations en Retard',
      'security_alerts': 'Alertes de Sécurité',
      'successful_logins': 'Connexions Réussies',
      'user_activities': 'Activités Utilisateur',
      'active_sessions': 'Sessions Actives',
      'all_notifications_marked_as_read':
          'Toutes les notifications marquées comme lues',
      'mark_as_read': 'Marquer comme lu',
      'mark_as_unread': 'Marquer comme non lu',
      'notification_preferences': 'Préférences de Notifications',
      'sound_notifications': 'Notifications Sonores',
      'email_frequency': 'Fréquence des E-mails',
      'instant': 'Instantané',
      'daily_digest': 'Résumé Quotidien',
      'weekly_digest': 'Résumé Hebdomadaire',
      'digest_schedule': 'Planification du Résumé',
      'day_of_week': 'Jour de la Semaine',
      'monday': 'Lundi',
      'tuesday': 'Mardi',
      'wednesday': 'Mercredi',
      'thursday': 'Jeudi',
      'friday': 'Vendredi',
      'saturday': 'Samedi',
      'sunday': 'Dimanche',
      'time_local_time': 'Heure (Heure Locale)',
      'notification_types': 'Types de Notifications',
      'preferences_saved_successfully': 'Préférences enregistrées avec succès',
      'enable_sound': 'Activer le Son',
      'play_sound_for_new_notifications': 'Jouer un son pour les nouvelles notifications',
      'configure_notification_types_description': 'Configurez les types de notifications à recevoir par e-mail et notifications push',
      'notification_type': 'Type de Notification',
      'push': 'Push',
      'all': 'Tous',
      'save_preferences': 'Enregistrer les Préférences',
      'select_digest_time_description': 'Sélectionnez l\'heure à laquelle vous souhaitez recevoir votre résumé',
      'failed_to_save_preferences': 'Échec de l\'enregistrement des préférences',
      'assignment_created': 'Mission Créée',
      'assignment_submitted': 'Mission Soumise',
      'assignment_approved': 'Mission Approuvée',
      'assignment_reopened': 'Mission Rouverte',
      'public_submission_received': 'Soumission Publique Reçue',
      'form_updated': 'Formulaire Mis à Jour',
      'document_uploaded': 'Document Téléchargé',
      'user_added_to_country': 'Utilisateur Ajouté au Pays',
      'template_updated': 'Modèle Mis à Jour',
      'self_report_created': 'Rapport Personnel Créé',
      'deadline_reminder': 'Rappel d\'Échéance',
      'search_audit_logs': 'Rechercher les journaux d\'audit...',
      'home_screen_widget_title': 'Widget écran d\'accueil',
      'audit_widget_activity_types_hint':
          'Choisissez les types d\'activité pour le widget. Aucune sélection = tous les types. Enregistré sur cet appareil.',
      'action': 'Action',
      'all_actions': 'Toutes les Actions',
      'create': 'Créer',
      'update': 'Mettre à jour',
      'user': 'Utilisateur',
      'all_users': 'Tous les Utilisateurs',
      'from_date': 'Date de Début',
      'to_date': 'Date de Fin',
      'select_date': 'Sélectionner la date',
      'no_description': 'Aucune description',
      'search_api_endpoints': 'Rechercher les points de terminaison API...',
      'http_method': 'Méthode HTTP',
      'all_methods': 'Toutes les Méthodes',
      'get': 'GET',
      'post': 'POST',
      'put': 'PUT',
      'delete_method': 'DELETE',
      'deprecated': 'Obsolète',
      'beta': 'Bêta',
      'new_api_key': 'Nouvelle Clé API',
      'time_range': 'Plage de Temps',
      'last_30_days': '30 Derniers Jours',
      'last_90_days': '90 Derniers Jours',
      'last_year': 'Dernière Année',
      'all_time': 'Tout le Temps',
      'metric': 'Métrique',
      'all_metrics': 'Toutes les Métriques',
      'active_users': 'Utilisateurs Actifs',
      'logins': 'Connexions',
      'metric_submissions': 'Soumissions',
      'page_views': 'Vues de Page',
      'search_indicators': 'Rechercher des indicateurs...',
      'category': 'Catégorie',
      'all_categories': 'Toutes les Catégories',
      'output': 'Sortie',
      'outcome': 'Résultat',
      'impact': 'Impact',
      'all_sectors': 'Tous les Secteurs',
      'health': 'Santé',
      'wash': 'WASH',
      'shelter': 'Abri',
      'education': 'Éducation',
      'indicators': 'Indicateurs',
      'new_indicator': 'Nouvel Indicateur',
      'search_organizations': 'Rechercher des organisations...',
      'entity_type': 'Type d\'Entité',
      'all_types': 'Tous les Types',
      'national_societies': 'Sociétés Nationales',
      'ns_structure': 'Structure NS',
      'secretariat': 'Secrétariat',
      'divisions': 'Divisions',
      'departments': 'Départements',
      'regional_offices': 'Bureaux Régionaux',
      'cluster_offices': 'Bureaux de Cluster',
      'add_organization': 'Ajouter une Organisation',
      'search_resources': 'Rechercher des ressources...',
      'no_indicators_found': 'Aucun indicateur trouvé',
      'no_organizations_found': 'Aucune organisation trouvée',
      'no_resources_found': 'Aucune ressource trouvée',
      'resources_unified_planning_section_title': 'Plans et rapports unifiés',
      'resources_unified_planning_section_subtitle':
          'Plans, rapports de mi-parcours et rapports annuels depuis IFRC GO (chargés dans l’application).',
      'unified_planning_empty':
          'Aucun document de planification unifiée ne correspond à votre recherche.',
      'unified_planning_fresh_badge': 'Récent',
      'unified_planning_sort_by': 'Trier par',
      'unified_planning_sort_date_newest': 'Date de publication : plus récent d’abord',
      'unified_planning_sort_date_oldest': 'Date de publication : plus ancien d’abord',
      'unified_planning_sort_country_az': 'Pays : A–Z',
      'unified_planning_sort_country_za': 'Pays : Z–A',
      'unified_planning_filter_all_countries': 'Tous les pays',
      'unified_error_config':
          'Impossible de charger les paramètres de planification unifiée depuis le serveur. Réessayez plus tard.',
      'unified_error_credentials':
          'Les documents IFRC ne sont pas disponibles dans cette application. Contactez votre administrateur.',
      'unified_error_ifrc_auth':
          'Impossible d’accéder aux documents IFRC. Contactez votre administrateur si le problème persiste.',
      'unified_error_ifrc':
          'Impossible de charger les documents depuis IFRC GO. Vérifiez votre connexion et réessayez.',
      'no_plugins_found': 'Aucun plugin trouvé',
      'no_translations_found': 'Aucune traduction trouvée',
      'no_documents_found': 'Aucun document trouvé',
      'no_users_found': 'Aucun utilisateur trouvé',
      'loading_user_profile': 'Chargement du profil…',
      'failed_load_user_profile': 'Impossible de charger cet utilisateur.',
      'admin_user_detail_confirm_save_title': 'Enregistrer les modifications ?',
      'admin_user_detail_confirm_save_message':
          'Mettre à jour le nom, le titre, le statut et les préférences du profil de cet utilisateur.',
      'admin_user_detail_invalid_profile_color':
          'Saisissez une couleur valide au format #RRGGBB (ex. #3B82F6).',
      'admin_user_detail_changes_saved': 'Modifications enregistrées.',
      'admin_user_detail_save_changes': 'Enregistrer les modifications',
      'admin_user_detail_profile_color_label': 'Couleur du profil',
      'admin_user_detail_profile_color_hint': '#RRGGBB',
      'admin_user_detail_cannot_deactivate_self':
          'Vous ne pouvez pas désactiver votre propre compte.',
      'admin_user_detail_matrix_read_only_bundled':
          'Rôles admin groupés (complet/noyau/système) — utilisez le web pour l’accès par domaine.',
      'admin_user_detail_rbac_incomplete':
          'Impossible de construire une liste de rôles valide. Vérifiez l’accès ou réessayez.',
      'assigned_roles_title': 'Rôles attribués',
      'role_type_label': 'Type de rôle',
      'permissions_by_role': 'Permissions par rôle',
      'all_permissions_union': 'Toutes les permissions (via les rôles)',
      'entity_permissions_title': 'Permissions d’entité',
      'manage_users_detail_footer':
          'Pour modifier les rôles, l’accès aux entités, les appareils ou les notifications, utilisez le formulaire web.',
      'no_roles_assigned': 'Aucun rôle RBAC attribué.',
      'no_entities_assigned': 'Aucune entité attribuée.',
      'entity_permission_unnamed': 'Sans nom',
      'entity_region_other': 'Autre région',
      'no_permissions_listed': 'Aucune permission listée pour ce rôle.',
      'user_dir_assignment_roles': 'Rôles d’affectation',
      'user_dir_admin_roles': 'Admin et système',
      'user_dir_other_roles': 'Autres rôles',
      'admin_role_access_area': 'Domaine',
      'admin_role_access_view': 'Consultation',
      'admin_role_access_manage': 'Gestion',
      'admin_role_de_heading': 'Explorateur de données',
      'admin_role_de_table': 'Tableau',
      'admin_role_de_analysis': 'Analyse',
      'admin_role_de_compliance': 'Conformité',
      'admin_role_note_admin_full': 'Tous les droits d’administration (rôle groupé)',
      'admin_role_note_admin_core': 'Fonctions d’administration essentielles (rôle groupé)',
      'admin_role_other_admin_roles': 'Autres rôles d’administration',
      'users_directory_role_all': 'Tous les rôles',
      'users_directory_country_all': 'Tous les pays',
      'no_assignments_found': 'Aucune assignation trouvée',
      'no_templates_found': 'Aucun modèle trouvé',
      'assignment_deleted_successfully': 'Assignation supprimée avec succès',
      'failed_to_delete_assignment':
          'Échec de la suppression de l\'assignation',
      'timeline_view': 'Vue Chronologique',
      'view_all_public_submissions': 'Voir Toutes les Soumissions Publiques',
      'items_requiring_attention': 'Éléments Nécessitant une Attention',
      'recent_activity': 'Activité Récente',
      'recent_activity_7_days': 'Activité Récente (7 jours)',
      'general_settings': 'Paramètres Généraux',
      'security_settings': 'Paramètres de Sécurité',
      'system_settings': 'Paramètres Système',
      'application_settings': 'Paramètres de l\'Application',
      'language_settings': 'Paramètres de Langue',
      'notification_settings': 'Paramètres de Notification',
      'authentication_settings': 'Paramètres d\'Authentification',
      'permission_settings': 'Paramètres de Permission',
      'database_settings': 'Paramètres de Base de Données',
      'cloud_storage_settings': 'Paramètres de Stockage Cloud',
      'configure_general_application_settings':
          'Configurer les paramètres généraux de l\'application',
      'manage_supported_languages_and_translations':
          'Gérer les langues et traductions prises en charge',
      'configure_notification_preferences':
          'Configurer les préférences de notification',
      'configure_authentication_and_authorization':
          'Configurer l\'authentification et l\'autorisation',
      'manage_user_permissions_and_roles':
          'Gérer les permissions et rôles des utilisateurs',
      'configure_database_connections_and_backups':
          'Configurer les connexions de base de données et les sauvegardes',
      'configure_cloud_storage_and_file_management':
          'Configurer le stockage cloud et la gestion des fichiers',

      // Indicator Bank
      'indicator_bank_title': 'Banque d\'Indicateurs',
      'indicator_bank_loading': 'Chargement de la Banque d\'Indicateurs...',
      'indicator_bank_error': 'Quelque chose s\'est mal passé',
      'indicator_bank_search_placeholder': 'Rechercher des indicateurs...',
      'indicator_bank_filter_placeholder': 'Filtrer les indicateurs...',
      'indicator_bank_browse_description':
          'Parcourir et rechercher des indicateurs pour la réponse humanitaire',
      'indicator_bank_grid_view': 'Vue Grille',
      'indicator_bank_table_view': 'Vue Tableau',
      'indicator_bank_show_filters': 'Afficher les Filtres',
      'indicator_bank_hide_filters': 'Masquer les Filtres',
      'indicator_bank_filters': 'Filtres',
      'indicator_bank_filter_type': 'Type',
      'indicator_bank_filter_type_all': 'Tous les Types',
      'indicator_bank_filter_sector': 'Secteur',
      'indicator_bank_filter_sector_all': 'Tous les Secteurs',
      'indicator_bank_filter_subsector': 'Sous-secteur',
      'indicator_bank_filter_subsector_all': 'Tous les Sous-secteurs',
      'indicator_bank_list_tier_also_related': 'Également liés',
      'indicator_bank_filter_status': 'Statut',
      'indicator_bank_filter_status_active': 'Actifs Seulement',
      'indicator_bank_filter_status_all': 'Tous',
      'indicator_bank_apply_filters': 'Appliquer les Filtres',
      'indicator_bank_clear_all': 'Tout Effacer',
      'indicator_bank_showing': 'Affichage de',
      'indicator_bank_indicators': 'indicateurs',
      'indicator_bank_indicator': 'indicateur',
      'indicator_bank_no_sectors': 'Aucun secteur trouvé',
      'indicator_bank_no_indicators': 'Aucun indicateur trouvé',
      'indicator_bank_table_name': 'Nom',
      'indicator_bank_table_type': 'Type',
      'indicator_bank_table_sector': 'Secteur',
      'indicator_bank_table_subsector': 'Sous-secteur',
      'indicator_bank_table_unit': 'Unité',
      'indicator_bank_propose_new': 'Proposer un Nouvel Indicateur',
      'indicator_bank_propose_title': 'Proposer un Nouvel Indicateur',
      'indicator_bank_propose_contact_info': 'Informations de Contact',
      'indicator_bank_propose_your_name': 'Votre Nom *',
      'indicator_bank_propose_email': 'Adresse E-mail *',
      'indicator_bank_propose_indicator_info': 'Informations sur l\'Indicateur',
      'indicator_bank_propose_indicator_name': 'Nom de l\'Indicateur *',
      'indicator_bank_propose_definition': 'Définition *',
      'indicator_bank_propose_type': 'Type',
      'indicator_bank_propose_unit': 'Unité de Mesure',
      'indicator_bank_propose_sector': 'Secteur',
      'indicator_bank_propose_primary_sector': 'Secteur Primaire *',
      'indicator_bank_propose_secondary_sector': 'Secteur Secondaire',
      'indicator_bank_propose_tertiary_sector': 'Secteur Tertiaire',
      'indicator_bank_propose_subsector': 'Sous-secteur',
      'indicator_bank_propose_primary_subsector': 'Sous-secteur Primaire *',
      'indicator_bank_propose_secondary_subsector': 'Sous-secteur Secondaire',
      'indicator_bank_propose_tertiary_subsector': 'Sous-secteur Tertiaire',
      'indicator_bank_propose_emergency': 'Contexte d\'Urgence',
      'indicator_bank_propose_related_programs': 'Programmes Connexes',
      'indicator_bank_propose_reason': 'Raison de la Proposition *',
      'indicator_bank_propose_additional_notes': 'Notes Supplémentaires',
      'indicator_bank_propose_submit': 'Soumettre la Proposition',
      'indicator_bank_propose_thank_you': 'Merci!',
      'indicator_bank_propose_success':
          'Votre proposition d\'indicateur a été soumise avec succès.',
      'indicator_bank_propose_failed':
          'Échec de la soumission de la proposition. Veuillez réessayer.',
      'indicator_bank_name_required': 'Le nom est requis',
      'indicator_bank_email_required': 'L\'e-mail est requis',
      'indicator_bank_indicator_name_required':
          'Le nom de l\'indicateur est requis',
      'indicator_bank_definition_required': 'La définition est requise',
      'indicator_bank_primary_sector_required':
          'Le secteur primaire est requis',
      'indicator_bank_primary_subsector_required':
          'Le sous-secteur primaire est requis',
      'indicator_bank_reason_required': 'La raison est requise',

      // Indicator Detail
      'indicator_detail_title': 'Détails de l\'Indicateur',
      'indicator_detail_loading': 'Chargement des détails de l\'indicateur...',
      'indicator_detail_error': 'Quelque chose s\'est mal passé',
      'indicator_detail_not_found': 'Indicateur non trouvé',
      'indicator_detail_go_back': 'Retour',
      'indicator_detail_definition': 'Définition',
      'indicator_detail_details': 'Détails',
      'indicator_detail_type': 'Type',
      'indicator_detail_unit': 'Unité',
      'indicator_detail_sector': 'Secteur',
      'indicator_detail_subsector': 'Sous-secteur',
      'indicator_detail_emergency_context': 'Contexte d\'Urgence',
      'indicator_detail_related_programs': 'Programmes Connexes',
      'indicator_detail_status': 'Statut',
      'indicator_detail_archived': 'Archivé',
      'indicator_detail_yes': 'Oui',
      'editIndicator': 'Modifier l\'Indicateur',

      // Quiz Game
      'quiz_game': 'Jeu de Quiz',
      'quiz_game_title': 'Jeu de Quiz',
      'quiz_game_test_your_knowledge': 'Testez vos connaissances!',
      'quiz_game_loading': 'Chargement du quiz...',
      'quiz_game_error': 'Erreur lors du chargement du quiz',
      'quiz_game_try_again': 'Réessayer',
      'quiz_game_start_quiz': 'Démarrer le Quiz',
      'quiz_game_which_sector': 'À quel secteur appartient cet indicateur?',
      'quiz_game_which_subsector': 'À quel sous-secteur appartient cet indicateur?',
      'quiz_game_definition': 'Définition',
      'quiz_game_no_definition': 'Aucune définition disponible',
      'quiz_game_correct': 'Correct!',
      'quiz_game_incorrect': 'Incorrect',
      'quiz_game_next_question': 'Question Suivante',
      'quiz_game_view_results': 'Voir les Résultats',
      'quiz_game_quiz_complete': 'Quiz Terminé!',
      'quiz_game_excellent_work': 'Excellent travail!',
      'quiz_game_well_done': 'Bien joué!',
      'quiz_game_good_effort': 'Bon effort!',
      'quiz_game_keep_practicing': 'Continuez à pratiquer!',
      'quiz_game_out_of': 'sur',
      'quiz_game_statistics': 'Statistiques',
      'quiz_game_correct_answers': 'Correctes',
      'quiz_game_incorrect_answers': 'Incorrectes',
      'quiz_game_total': 'Total',
      'quiz_game_home': 'Accueil',
      'quiz_game_play_again': 'Rejouer',
      'quiz_game_no_indicators_available': 'Aucun indicateur avec secteurs ou sous-secteurs disponible pour le quiz',
      'quiz_game_failed_to_start': 'Échec du démarrage du quiz',
      'quiz_game_leaderboard': 'Classement',
      'quiz_game_view_leaderboard': 'Voir le Classement',
      'quiz_game_loading_leaderboard': 'Chargement du classement...',
      'quiz_game_no_leaderboard_data': 'Aucune donnée de classement disponible pour le moment',
      'quiz_game_top_players': 'Meilleurs Joueurs',
      'quiz_game_you': 'Vous',
      'quiz_game_points': 'Points',

      // AI Chat (immersive)
      'ai_policy_acknowledge_snackbar':
          'Veuillez reconnaître la politique IA pour continuer.',
      'ai_use_policy_title': 'Politique d\'utilisation de l\'IA',
      'ai_policy_do_not_share': 'Ne partagez pas d\'informations sensibles.',
      'ai_policy_traces_body':
          'Nous utilisons des traces système et de la télémétrie pour améliorer l\'assistant. Vos messages peuvent être traités par des fournisseurs d\'IA externes.',
      'ai_policy_purpose_title': 'Objectif',
      'ai_policy_purpose_body':
          'L\'assistant IA vous aide à explorer les données et documents sur cette plateforme. Il peut répondre sur les indicateurs, pays, affectations et rechercher dans les documents téléversés.',
      'ai_policy_acceptable_use_title': 'Utilisation acceptable',
      'ai_policy_acceptable_use_body':
          '• Posez des questions sur les données de la plateforme, les indicateurs et les documents.\n'
          '• Ne partagez PAS mots de passe, identifiants ou détails opérationnels hautement confidentiels.\n'
          '• Ne collez PAS de données personnelles ou financières.',
      'ai_policy_accuracy_title': 'Exactitude',
      'ai_policy_accuracy_body':
          'L\'IA peut se tromper ou mal interpréter les données. Vérifiez toujours les informations importantes auprès des sources ou documents d\'origine.',
      'ai_policy_confirm_footer':
          'Confirmez avoir lu les informations ci-dessus pour utiliser l\'assistant.',
      'ai_policy_i_understand': 'Je comprends',
      'ai_policy_acknowledge_cta': 'Reconnaître la politique d\'utilisation de l\'IA',
      'ai_sources_heading': 'Utiliser les sources :',
      'ai_source_databank': 'Banque de données',
      'ai_source_system_documents': 'Documents système',
      'ai_source_upr_documents': 'Documents UPR',
      'ai_sources_minimum_note':
          'Au moins une source reste activée (comme sur l\'assistant web).',
      'ai_tour_guide_question': 'Souhaitez-vous que je vous guide ?',
      'ai_tour_navigate_question': 'Souhaitez-vous aller à la page concernée ?',
      'ai_tour_web_only_snackbar':
          'Les visites interactives sont disponibles sur la version web. Ouverture de la page...',
      'ai_new_chat': 'Nouvelle conversation',
      'ai_semantic_open_drawer_hint': 'Ouvre les conversations et les réglages',
      'ai_tooltip_new_chat': 'Nouvelle conversation',
      'ai_semantic_new_chat_label': 'Nouvelle conversation',
      'ai_semantic_new_chat_hint': 'Démarre une nouvelle conversation vide',
      'ai_beta_tester_banner':
          'Testeur bêta IA — des fonctions expérimentales peuvent être activées.',
      'ai_empty_welcome': 'Comment puis-je vous aider aujourd\'hui ?',
      'ai_policy_chip_title': 'Politique d\'utilisation de l\'IA',
      'ai_policy_sheet_summary_line':
          'Résumé court — ouvrez la fiche pour tous les détails.',
      'ai_policy_compact_warning':
          'Ne partagez pas d\'informations sensibles. Nous utilisons des traces et de la télémétrie pour améliorer l\'assistant ; les messages peuvent être traités par des fournisseurs d\'IA externes.',
      'ai_read_full_policy': 'Lire la politique complète',
      'ai_try_asking': 'Essayez de demander',
      'ai_copied': 'Copié !',
      'ai_tooltip_copy': 'Copier',
      'ai_tooltip_edit_message': 'Modifier',
      'ai_tooltip_helpful': 'Utile',
      'ai_tooltip_not_helpful': 'Pas utile',
      'ai_footer_model_warning':
          'L\'IA peut se tromper. Vérifiez les informations importantes.',
      'ai_chat_error_network':
          'Impossible d\'accéder au service d\'IA. Vérifiez votre connexion internet et réessayez.',
      'ai_chat_error_timeout':
          'La requête a expiré. Vérifiez votre connexion et réessayez.',
      'ai_chat_error_server': 'Un problème est survenu. Veuillez réessayer.',
      'ai_agent_progress_title': 'Étapes en cours',
      'ai_agent_step_done': 'Terminé.',
      'ai_agent_step_preparing_query': 'Préparation de la requête…',
      'ai_agent_step_planning': 'Planification de l\'approche…',
      'ai_agent_step_reviewing': 'Examen des résultats…',
      'ai_agent_step_drafting': 'Rédaction de la réponse…',
      'ai_agent_step_replying': 'Réponse en cours…',
      'ai_agent_step_thinking_next': 'Réflexion sur la suite à donner.',
      'ai_agent_step_no_shortcut_full':
          'Pas de raccourci à un seul outil — chemin de planification complet.',
      'ai_agent_step_no_shortcut_reviewing':
          'Pas de raccourci à un seul outil pour cette demande — examen : %s',
      'ai_response_sources': 'Sources',
      'ai_response_sources_with_count': 'Sources (%s)',
      'ai_tooltip_configure_sources': 'Configurer les sources de données',
      'ai_input_policy_required':
          'Reconnaissez la politique IA ci-dessus pour envoyer des messages',
      'ai_input_placeholder_message': 'Message',
      'ai_input_placeholder_edit': 'Modifier le message…',
      'ai_tooltip_cancel_edit': 'Annuler la modification',
      'ai_stop': 'Arrêter',
      'ai_conversations_drawer_title': 'Conversations',
      'ai_search_conversations_hint': 'Rechercher des conversations',
      'ai_no_conversations_body':
          'Pas encore de conversations.\nDémarrez une nouvelle discussion !',
      'ai_no_conversations_offline':
          'Pas encore de conversations.\nDémarrez une discussion (hors ligne).',
      'ai_no_conversations_filtered': 'Aucune conversation trouvée',
      'ai_section_pinned': 'Épinglées',
      'ai_section_recent': 'Récentes',
      'ai_quick_prompt_1': 'Combien de bénévoles au Bangladesh ?',
      'ai_quick_prompt_2': 'Bénévoles en Syrie dans le temps',
      'ai_quick_prompt_3': 'Carte mondiale des bénévoles par pays',
      'ai_quick_prompt_4': 'Nombre de branches au Kenya',
      'ai_quick_prompt_5': 'Personnel et unités locales au Nigeria',
      'ai_clear_all_dialog_title': 'Effacer toutes les conversations',
      'ai_clear_all_dialog_body':
          'Voulez-vous vraiment supprimer toutes les conversations ? Cette action est irréversible.',
      'ai_clear_all_button': 'Tout effacer',
      'ai_clear_all_row': 'Effacer toutes les conversations',
      'ai_help_about_row': 'Aide et à propos',
      'ai_pin': 'Épingler',
      'ai_unpin': 'Désépingler',
      'ai_delete_conversation_title': 'Supprimer la conversation ?',
      'ai_delete_conversation_body':
          'Supprimer cette conversation ? Cette action est irréversible.',
      'ai_new_chat_title_fallback': 'Nouvelle conversation',
      'ai_help_dialog_title': 'Aide de l\'assistant IA',
      'ai_help_about_heading': 'À propos',
      'ai_help_about_paragraph':
          'L\'assistant IA vous aide à trouver des informations et répondre aux questions sur la Banque de Données du Réseau IFRC.',
      'ai_help_features_heading': 'Fonctionnalités',
      'ai_help_feature_bullet_1':
          '• Posez des questions sur les affectations, ressources, etc.',
      'ai_help_feature_bullet_2': '• Obtenez de l\'aide pour naviguer dans l\'app',
      'ai_help_feature_bullet_3':
          '• Parcourez l\'historique de vos conversations',
      'ai_help_feature_bullet_4':
          '• Les conversations sont enregistrées lorsque vous êtes connecté',
      'ai_help_tips_heading': 'Conseils',
      'ai_help_tip_bullet_1':
          '• Soyez précis dans vos questions pour de meilleurs résultats',
      'ai_help_tip_bullet_2':
          '• Touchez les liens dans les réponses pour aller aux pages utiles',
      'ai_help_tip_bullet_3':
          '• Utilisez la barre de recherche pour retrouver d\'anciennes conversations',
      'ai_help_tip_bullet_4':
          '• Appui long sur une conversation pour le menu (épingler ou supprimer)',
      'ai_got_it': 'Compris',
      'ai_score_confidence': 'Confiance',
      'ai_score_grounding': 'Ancrage',
      'ai_default_assistant_title': 'Assistant IA',
      'resources_other_subgroup': 'Autres',
      'resources_list_truncated_hint':
          'Affichage des éléments les plus récents. Utilisez la recherche pour trouver un document précis.',
      'ai_assistant': 'Assistant IA',
    },
    'ar': {
      'app_name': 'بنك بيانات شبكة الاتحاد الدولي',
      'navigation': 'التنقل',
      'home': 'الرئيسية',
      'dashboard': 'لوحة التحكم',
      'resources': 'الموارد',
      'indicator_bank': 'بنك المؤشرات',
      'disaggregation_analysis': 'تحليل التفكيك',
      'analysis': 'التحليل',
      'data_visualization': 'تصور البيانات',
      'settings': 'الإعدادات',
      'notifications': 'الإشعارات',
      'admin': 'الإدارة',
      'admin_panel': 'لوحة الإدارة',
      'customize_tabs': 'تخصيص علامات التبويب',
      'customize_tabs_description': 'حدد علامات التبويب المراد عرضها واسحبها لإعادة ترتيبها.',
      'reset_to_default': 'إعادة تعيين',
      'tab_always_shown': 'يظهر دائماً',
      'minimum_tabs_warning': 'يجب الاحتفاظ بعلامتي تبويب مرئيتين على الأقل.',
      'access_denied': 'تم رفض الوصول',
      'general': 'عام',
      'document_management': 'إدارة المستندات',
      'translation_management': 'إدارة الترجمات',
      'plugin_management': 'إدارة الإضافات',
      'system_configuration': 'إعدادات النظام',
      'user_management': 'إدارة المستخدمين',
      'manage_users': 'إدارة المستخدمين',
      'access_requests_title': 'طلبات الوصول على مستوى البلد',
      'access_requests_subtitle':
          'وافق على طلبات الوصول أو ارفضها على مستوى البلد.',
      'access_requests_pending': 'قيد الانتظار',
      'access_requests_processed': 'قرارات حديثة',
      'access_requests_empty': 'لا توجد طلبات وصول.',
      'access_requests_approve': 'موافقة',
      'access_requests_reject': 'رفض',
      'access_requests_approve_all': 'الموافقة على الكل',
      'access_requests_approve_all_confirm':
          'الموافقة على جميع طلبات الوصول على مستوى البلد المعلقة؟',
      'access_requests_reject_confirm':
          'رفض طلب الوصول هذا؟ لن يُمنح المستخدم الوصول.',
      'access_requests_country': 'البلد',
      'access_requests_message': 'الرسالة',
      'access_requests_requested_at': 'طُلب في',
      'access_requests_processed_at': 'عُولج في',
      'access_requests_auto_approve_hint':
          'قد تكون الموافقة التلقائية مفعّلة في إعدادات الخادم.',
      'access_requests_status_pending': 'قيد الانتظار',
      'access_requests_status_approved': 'موافق عليه',
      'access_requests_status_rejected': 'مرفوض',
      'access_requests_by': 'بواسطة',
      'access_requests_load_failed': 'تعذر تحميل طلبات الوصول.',
      'access_requests_action_failed': 'تعذر إتمام الإجراء.',
      'access_requests_view_forbidden':
          'ليس لديك إذن لعرض طلبات الوصول على الخادم.',
      'access_requests_unexpected_response': 'استجابة غير متوقعة من الخادم.',
      'access_requests_action_forbidden':
          'ليس لديك إذن لتنفيذ هذا الإجراء.',
      'users_directory_read_only':
          'هذا الدليل للقراءة فقط. أنشئ الحسابات أو عدّلها من لوحة الويب.',
      'login_logs_title': 'سجلات تسجيل الدخول',
      'login_logs_filters': 'عوامل التصفية',
      'login_logs_email_hint': 'البحث بالبريد الإلكتروني',
      'login_logs_event_type': 'نوع الحدث',
      'login_logs_event_all': 'كل الأنواع',
      'login_logs_event_login': 'تسجيل دخول',
      'login_logs_event_logout': 'تسجيل خروج',
      'login_logs_event_failed': 'فشل تسجيل الدخول',
      'login_logs_ip_label': 'عنوان IP',
      'login_logs_date_from': 'من تاريخ',
      'login_logs_date_to': 'إلى تاريخ',
      'login_logs_suspicious_only': 'المشبوه فقط',
      'login_logs_apply': 'تطبيق',
      'login_logs_clear': 'مسح',
      'login_logs_no_entries': 'لا توجد أحداث مطابقة لعوامل التصفية.',
      'login_logs_total': '%s حدثًا إجمالاً',
      'login_logs_load_more': 'تحميل المزيد',
      'login_logs_user_not_resolved': 'لا يوجد حساب مستخدم مطابق',
      'login_logs_device': 'الجهاز',
      'login_logs_browser': 'المتصفح',
      'login_logs_suspicious_badge': 'مشبوه',
      'login_logs_recent_failures': '%s إخفاقات حديثة',
      'login_logs_open': 'سجلات تسجيل الدخول',
      'session_logs_title': 'سجلات الجلسات',
      'admin_filters': 'عوامل التصفية',
      'session_logs_email_hint': 'البحث بالبريد الإلكتروني',
      'session_logs_min_duration': 'أدنى دقائق (الجلسة أو النشاط)',
      'session_logs_active_only': 'الجلسات النشطة فقط',
      'admin_filters_apply': 'تطبيق',
      'admin_filters_clear': 'مسح',
      'session_logs_no_entries': 'لا توجد جلسات مطابقة لعوامل التصفية.',
      'session_logs_total': '%s جلسة إجمالاً',
      'session_logs_load_more': 'تحميل المزيد',
      'session_logs_session_start': 'بداية الجلسة',
      'session_logs_duration': 'المدة',
      'session_logs_session_length': 'طول الجلسة',
      'session_logs_active_time': 'وقت النشاط',
      'session_logs_minutes': '%s د',
      'session_logs_page_views': 'مشاهدات الصفحات',
      'session_logs_path_breakdown_title': 'مشاهدات الصفحات حسب المسار',
      'session_logs_path_breakdown_open': 'عرض تفصيل المسارات',
      'session_logs_path_breakdown_empty':
          'لا يوجد تفصيل مسارات مسجّل لهذه الجلسة.',
      'session_logs_path_other_bucket': 'مسارات أخرى (مجمّعة)',
      'session_logs_path_column': 'المسار',
      'session_logs_path_count_column': 'العدد',
      'session_logs_distinct_paths': 'مسارات مميّزة',
      'session_logs_activities': 'الأنشطة',
      'session_logs_last_activity': 'آخر نشاط',
      'session_logs_status_active': 'نشطة',
      'session_logs_status_ended': 'منتهية',
      'session_logs_force_logout': 'إنهاء الجلسة قسراً',
      'session_logs_force_logout_confirm':
          'إنهاء جلسة هذا المستخدم قسراً؟ سيتم تسجيل خروجه فوراً.',
      'session_logs_unknown_user': 'مستخدم غير معروف',
      'session_logs_no_activity': 'لا نشاط',
      'session_logs_open': 'سجلات الجلسات',
      'session_logs_ended_ok': 'تم إنهاء الجلسة.',
      'session_logs_os': 'نظام التشغيل',
      'session_logs_user_agent': 'وكيل المستخدم',
      'session_logs_device_section': 'تفاصيل الجهاز',
      'form_data_management': 'إدارة النماذج والبيانات',
      'manage_templates': 'إدارة القوالب',
      'manage_assignments': 'إدارة المهام',
      'frontend_management': 'إدارة الواجهة الأمامية',
      'manage_resources': 'إدارة الموارد',
      'reference_data': 'البيانات المرجعية',
      'organizational_structure': 'الهيكل التنظيمي',
      'analytics_monitoring': 'التحليلات والمراقبة',
      'user_analytics': 'تحليلات المستخدمين',
      'audit_trail': 'سجل التدقيق',
      'api_management': 'إدارة API',
      'account_settings': 'إعدادات الحساب',
      'profile': 'الملف الشخصي',
      'preferences': 'التفضيلات',
      'language': 'اللغة',
      'select_language': 'اختر اللغة',
      'change_password': 'تغيير كلمة المرور',
      'profile_color': 'لون الملف الشخصي',
      'chatbot': 'المساعد الذكي',
      'enable_chatbot_assistance': 'تفعيل المساعدة الذكية',
      'dark_theme': 'المظهر الداكن',
      'enable_dark_theme': 'تفعيل المظهر الداكن',
      'settings_theme': 'المظهر',
      'light_theme': 'المظهر الفاتح',
      'system_theme': 'النظام',
      'select_theme': 'اختر المظهر',
      'settings_theme_set_to': 'تم تعيين المظهر إلى %s',
      'arabic_text_font': 'خط النص العربي',
      'arabic_font_tajawal': 'تجوال',
      'arabic_font_system': 'خط النظام',
      'login_to_account': 'تسجيل الدخول',
      'logout': 'تسجيل الخروج',
      'are_you_sure_logout': 'هل أنت متأكد من تسجيل الخروج؟',
      'cancel': 'إلغاء',
      'name': 'الاسم',
      'title': 'المسمى الوظيفي',
      'email': 'البريد الإلكتروني',
      'loading': 'جاري التحميل...',
      'loading_home': 'جاري تحميل الصفحة الرئيسية...',
      'home_landing_hero_description':
          'استكشف البيانات الإنسانية الشاملة والمؤشرات والرؤى من الاتحاد الدولي لجمعيات الصليب الأحمر والهلال الأحمر.',
      'home_landing_chat_title': 'الدردشة مع بياناتنا',
      'home_landing_chat_description': 'اكتب أسئلتك حول بيانات الاتحاد الدولي أدناه.',
      'home_landing_ask_placeholder': 'اسأل عن التمويل والبرامج والبلدان...',
      'home_landing_quick_prompt_1': 'أخبرني عن متطوعي الهلال الأحمر الأفغاني',
      'home_landing_quick_prompt_2': 'أرني بيانات الاستجابة للكوارث العالمية',
      'home_landing_quick_prompt_3': 'ما هي المؤشرات الإنسانية الرئيسية؟',
      'home_landing_shortcuts_heading': 'ابدأ',
      'home_landing_shortcut_indicators_subtitle': 'تصفح التعريفات والبيانات الوصفية',
      'home_landing_shortcut_resources_subtitle': 'المنشورات والمواد',
      'home_landing_shortcut_countries_subtitle': 'الملفات التعريفية والمناطق',
      'home_landing_shortcut_disaggregation_subtitle': 'تفصيل قيم المؤشرات',
      'home_landing_explore_title': 'الخريطة العالمية والمخططات',
      'home_landing_explore_subtitle':
          'خريطة ومخطط أصليان بنفس إجماليات FDRS كالموقع الإلكتروني دون مغادرة التطبيق.',
      'home_landing_global_indicator_volunteers': 'المتطوعون',
      'home_landing_global_indicator_staff': 'الموظفون',
      'home_landing_global_indicator_branches': 'الفروع',
      'home_landing_global_indicator_local_units': 'Local units',
      'home_landing_global_indicator_blood_donors': 'Blood donors',
      'home_landing_global_indicator_first_aid': 'First aid',
      'home_landing_global_indicator_people_reached': 'People reached',
      'home_landing_global_indicator_income': 'Income',
      'home_landing_global_indicator_expenditure': 'Expenditure',
      'home_landing_global_top_countries': 'أبرز الدول',
      'home_landing_global_load_error':
          'تعذر تحميل بيانات الخريطة. تحقق من الاتصال وحاول مرة أخرى.',
      'home_landing_global_empty':
          'لا توجد قيم لهذا المؤشر في أحدث فترة.',
      'home_landing_global_period': 'الفترة: %s',
      'home_landing_global_map_hint':
          'قرص واسحب واضغط على بلد لعرض التفاصيل',
      'home_landing_global_map_open_fullscreen': 'ملء الشاشة',
      'home_landing_global_period_filter_label': 'فترة التقرير',
      'home_landing_global_map_mode_bubble': 'فقاعات',
      'home_landing_global_map_mode_choropleth': 'خريطة لونية',
      'home_landing_global_map_zoom_in': 'تكبير',
      'home_landing_global_map_zoom_out': 'تصغير',
      'home_landing_global_map_reset_bounds': 'ملاءمة البيانات',
      'home_landing_global_map_legend_low': 'منخفض',
      'home_landing_global_map_legend_high': 'مرتفع',
      'home_landing_global_map_country_no_data': 'لا توجد بيانات لهذا المؤشر',
      'home_landing_global_map_value_label': 'القيمة',
      'home_landing_global_map_filters_title': 'خيارات الخريطة',
      'loading_page': 'جاري تحميل الصفحة...',
      'loading_preferences': 'جاري تحميل التفضيلات...',
      'loading_notifications': 'جاري تحميل الإشعارات...',
      'loading_dashboard': 'جاري تحميل لوحة التحكم...',
      'loading_audit_logs': 'جاري تحميل سجلات التدقيق...',
      'loading_analytics': 'جاري تحميل التحليلات...',
      'loading_organizations': 'جاري تحميل المنظمات...',
      'loading_templates': 'جاري تحميل القوالب...',
      'loading_assignments': 'جاري تحميل المهام...',
      'loading_translations': 'جاري تحميل الترجمات...',
      'loading_plugins': 'جاري تحميل الإضافات...',
      'loading_resources': 'جاري تحميل الموارد...',
      'loading_indicators': 'جاري تحميل المؤشرات...',
      'loading_documents': 'جاري تحميل المستندات...',
      'loading_api_endpoints': 'جاري تحميل نقاط نهاية API...',
      'loading_users': 'جاري تحميل المستخدمين...',
      'error': 'خطأ',
      'retry': 'إعادة المحاولة',
      'refresh': 'تحديث',
      'close': 'إغلاق',
      'save': 'حفظ',
      'saved': 'تم الحفظ',
      'success': 'نجح',
      'oops_something_went_wrong': 'عذراً! حدث خطأ ما',
      'go_back': 'رجوع',
      'edit': 'تعديل',
      'duplicate': 'نسخ',
      'preview': 'معاينة',
      'download_started': 'بدأ التحميل',
      'could_not_start_download': 'تعذر بدء التحميل',
      'could_not_open_download_link': 'تعذر فتح رابط التحميل',
      'error_opening_download': 'خطأ في فتح التحميل',
      'please_select_at_least_one_user': 'يرجى اختيار مستخدم واحد على الأقل',
      'indicator_updated_successfully': 'تم تحديث المؤشر بنجاح',
      'failed_to_load_indicator': 'فشل تحميل المؤشر',
      'user_deleted': 'تم حذف المستخدم',
      'public_url_copied': 'تم نسخ رابط URL العام إلى الحافظة!',
      'please_use_web_interface': 'يرجى استخدام واجهة الويب لحفظ تغييرات الكيان',
      'open_in_web_browser': 'فتح في متصفح الويب',
      'countries': 'الدول',
      'all_roles': 'جميع الأدوار',
      'admin_role': 'مسؤول',
      'focal_point_role': 'نقطة الاتصال',
      'system_manager_role': 'مدير النظام',
      'viewer_role': 'عارض',
      'all_status': 'جميع الحالات',
      'active_status': 'نشط',
      'inactive_status': 'غير نشط',
      'normal_priority': 'عادي',
      'high_priority': 'عالي',
      'none': 'لا شيء',
      'app_screen': 'شاشة التطبيق',
      'custom_url': 'رابط مخصص',
      'create_template': 'إنشاء قالب',
      'delete_template': 'حذف القالب',
      'create_assignment': 'إنشاء مهمة',
      'delete_assignment': 'حذف المهمة',
      'edit_document': 'تعديل المستند',
      'preview_document': 'معاينة المستند',
      'download_document': 'تحميل المستند',
      'upload_document': 'رفع المستند',
      'new_translation': 'ترجمة جديدة',
      'new_resource': 'مورد جديد',
      'install_plugin': 'تثبيت الإضافة',
      'template_deleted_successfully': 'تم حذف القالب بنجاح',
      'failed_to_delete_template': 'فشل حذف القالب',
      'error_loading_page': 'خطأ في تحميل الصفحة',
      'no_notifications': 'لا توجد إشعارات',
      'all_caught_up': 'لقد انتهيت من جميع الإشعارات',
      'notifications_load_more': 'تحميل المزيد',
      'notifications_filter': 'عوامل التصفية',
      'notifications_filter_title': 'تصفية الإشعارات',
      'notifications_filter_read_status': 'حالة القراءة',
      'notifications_filter_all': 'الكل',
      'notifications_filter_unread_only': 'غير المقروءة فقط',
      'notifications_filter_type': 'النوع',
      'notifications_filter_type_any': 'كل الأنواع',
      'notifications_filter_from': 'من',
      'notifications_filter_from_any': 'أي شخص',
      'notifications_filter_from_empty_hint':
          'يظهر الأشخاص عندما تكون إشعاراتهم في القائمة المحمّلة. استخدم تحميل المزيد.',
      'notifications_filter_priority': 'الأولوية',
      'notifications_filter_priority_any': 'أي أولوية',
      'notifications_filter_priority_normal': 'عادية',
      'notifications_filter_priority_high': 'مرتفعة',
      'notifications_filter_priority_urgent': 'عاجلة',
      'notifications_filter_apply': 'تطبيق',
      'notifications_filter_reset': 'إعادة التعيين',
      'notifications_filter_no_matches_loaded':
          'لا توجد إشعارات تطابق عوامل التصفية في القائمة المحمّلة. حمّل المزيد أو عدّل عوامل التصفية.',
      'mark_all_read': 'تعليم الكل كمقروء',
      'mark_read': 'تعليم كمقروء',
      'mark_unread': 'تعليم كغير مقروء',
      'delete': 'حذف',
      'archive': 'أرشفة',
      'unarchive': 'إلغاء الأرشفة',
      'send_push_notification': 'إرسال إشعار دفع',
      'admin_push_user_ids_label': 'معرّفات المستخدمين المستلمين',
      'admin_push_user_ids_hint':
          'أرقام مفصولة بفواصل (من إدارة المستخدمين).',
      'admin_push_user_ids_invalid':
          'أدخل معرّف مستخدم رقمي واحدًا أو أكثر، مفصولة بفواصل.',
      'select_users': 'اختر المستخدمين',
      'search_users': 'البحث عن المستخدمين بالاسم أو البريد الإلكتروني',
      'redirect_url': 'إعادة التوجيه (اختياري)',
      'login': 'تسجيل الدخول',
      'log_in': 'تسجيل الدخول',
      'phone_username_email': 'رقم الهاتف أو اسم المستخدم أو البريد الإلكتروني',
      'forgot_password_coming_soon': 'ميزة نسيان كلمة المرور قريباً',
      'please_enter_email': 'يرجى إدخال بريدك الإلكتروني',
      'please_enter_valid_email': 'يرجى إدخال بريد إلكتروني صالح',
      'please_enter_password': 'يرجى إدخال كلمة المرور',
      'show': 'إظهار',
      'hide': 'إخفاء',
      'or': 'أو',
      'dont_have_account': 'ليس لديك حساب؟',
      'sign_up': 'سجل',
      'registration_coming_soon': 'ميزة التسجيل قريباً',
      'quick_login_testing': 'تسجيل دخول سريع للاختبار',
      'test_as_admin': 'اختبار كمسؤول',
      'test_as_focal_point': 'اختبار كنقطة اتصال',
      'public_login_disabled': 'تم تعطيل تسجيل الدخول العام مؤقتاً',
      'tester_accounts_info':
          'لا يزال بإمكان حسابات الاختبار تسجيل الدخول باستخدام الأزرار أعلاه.',
      'could_not_open_azure_login': 'تعذر فتح تسجيل الدخول إلى Azure',
      'login_with_ifrc_account': 'تسجيل الدخول بحساب الاتحاد الدولي',
      'use_ifrc_federation_account':
          'استخدم حساب اتحاد الاتحاد الدولي لتسجيل الدخول',
      'your_account_or_create_account': 'حسابك أو إنشاء حساب',
      'login_failed': 'فشل تسجيل الدخول',
      'email_address': 'عنوان البريد الإلكتروني',
      'password': 'كلمة المرور',
      'remember_me': 'تذكرني',
      'forgot_password': 'نسيت كلمة المرور؟',
      'language_changed_to': 'تم تغيير اللغة إلى',

      // Splash Screen
      'welcome_to_ifrc_network_databank':
          'مرحباً بك في بنك بيانات شبكة الاتحاد الدولي',
      'splash_description':
          'هذا هو النظام الوحيد للإبلاغ عن البيانات إلى الاتحاد الدولي. وداعاً لملفات Excel المتناثرة ونماذج KoBo والمنصات المتعددة وتسجيلات الدخول — كل شيء الآن مركزي ومبسط هنا.',
      'powered_by_hum_databank': 'مدعوم بواسطة Humanitarian Databank',
      'open_on_github': 'فتح على GitHub',

      // Dashboard
      'national_society': 'الجمعية الوطنية',
      'active': 'نشط',
      'completed': 'مكتمل',
      'current_assignments': 'المهام الحالية',
      'dashboard_you_have_no_open_assignments': 'ليس لديك مهام مفتوحة',
      'dashboard_you_have_one_open_assignment': 'لديك مهمة مفتوحة واحدة',
      'dashboard_you_have_open_assignments_count': 'لديك %s مهام مفتوحة',
      'past_assignments': 'المهام السابقة',
      'assignments_for': 'المهام لـ',
      'past_submissions_for': 'التقديمات السابقة لـ',
      'something_went_wrong': 'حدث خطأ ما',
      'no_assignments_yet': 'كل شيء واضح! لا توجد مهام نشطة في هذا الوقت.',
      'new_assignments_will_appear': 'ستظهر المهام الجديدة هنا عند توفرها.',
      'get_started_by_creating': 'ابدأ بإنشاء مهمة جديدة',
      'filters': 'المرشحات',
      'period': 'الفترة',
      'template': 'القالب',
      'status': 'الحالة',
      'clear': 'مسح',
      'approved': 'موافق عليه',
      'requires_revision': 'يتطلب مراجعة',
      'pending': 'قيد الانتظار',
      'in_progress': 'قيد التنفيذ',
      'submitted': 'تم التقديم',
      'other': 'أخرى',
      'entities': 'الكيانات',
      'search_placeholder': 'بحث...',
      'no_results_found': 'لم يتم العثور على نتائج',
      'entity_type_country': 'البلد',
      'entity_type_ns_branch': 'فرع الجمعية الوطنية',
      'entity_type_ns_sub_branch': 'فرع فرعي للجمعية الوطنية',
      'entity_type_ns_local_unit': 'وحدة محلية للجمعية الوطنية',
      'entity_type_division': 'قسم',
      'entity_type_department': 'إدارة',
      'delete_assignment_confirm_message':
          'هل أنت متأكد من أنك تريد حذف هذه المهمة وجميع حالات البلدان والبيانات المرتبطة بها؟',
      'no_assignments_match_filters': 'لا توجد مهام تطابق المرشحات المحددة',
      'form': 'النموذج',
      'last_updated': 'آخر تحديث',
      'actions': 'الإجراءات',
      'all_years': 'جميع السنوات',
      'all_templates': 'جميع القوالب',
      'all_statuses': 'جميع الحالات',
      'template_missing': 'القالب مفقود',
      'self_reported': 'تم الإبلاغ عنه ذاتياً',
      'no_actions_available': 'لا توجد إجراءات متاحة',
      'previous': 'السابق',
      'next': 'التالي',
      'showing': 'عرض',
      'to': 'إلى',
      'of': 'من',
      'results': 'النتائج',
      'no_past_assignments_for': 'لا توجد مهام سابقة لـ',
      'yet': 'حتى الآن',
      'submission_history_and_data_quality_for':
          'سجل التقديمات وجودة البيانات لـ',
      'overall_performance': 'الأداء الإجمالي',
      'average_completion_rate_past_3_periods':
          'متوسط معدل الإتمام (آخر 3 فترات)',
      'average_submission_timeliness':
          'متوسط التوقيت في التقديم (أيام مبكراً/متأخراً)',
      'data_quality_index_fake_metric': 'مؤشر جودة البيانات (مقياس وهمي)',
      'number_of_revisions_requested_past_year':
          'عدد المراجعات المطلوبة (العام الماضي)',
      'trend_analysis': 'تحليل الاتجاه',
      'recent_activities': 'الأنشطة الأخيرة',
      'last_7_days': 'آخر 7 أيام',
      'unknown_user': 'مستخدم غير معروف',
      'added': 'تمت الإضافة',
      'updated': 'تم التحديث',
      'removed': 'تمت الإزالة',
      'show_less': 'عرض أقل',
      'more_change': 'المزيد من التغييرات',
      'no_recent_activities': 'لا توجد أنشطة حديثة',
      'activities_from_other_focal_points_in':
          'الأنشطة من نقاط الاتصال الأخرى في',
      'will_appear_here': 'ستظهر هنا',
      'focal_points_for': 'نقاط الاتصال لـ',
      'national_society_focal_points': 'نقاط الاتصال في الجمعية الوطنية',
      'ifrc_focal_points': 'نقاط الاتصال في الاتحاد الدولي',
      'no_focal_points_assigned_to': 'لا توجد نقاط اتصال مخصصة لـ',
      'your_user_account_not_associated':
          'حساب المستخدم الخاص بك غير مرتبط بأي دول',
      'please_contact_administrator': 'يرجى الاتصال بالمسؤول',
      'due_date': 'تاريخ الاستحقاق',
      'no_due_date': 'لا يوجد تاريخ استحقاق',
      'overdue': 'متأخر',
      'latest_submission': 'آخر تقديم',
      'submitted_through_public_link': 'تم التقديم من خلال رابط عام',
      'submission': 'تقديم',
      'submissions': 'تقديمات',
      'completion': 'الإتمام',
      'received_1_submission_using_public_link':
          'تم استلام تقديم واحد باستخدام الرابط العام',
      'received_count_submissions_using_public_link':
          'تم استلام %(count)d تقديم باستخدام الرابط العام',
      'at_datetime': 'في: %(datetime)s',
      'latest_datetime': 'الأحدث: %(datetime)s',
      'last_modified_by': 'آخر تعديل بواسطة',
      'assignment_assigned_date': 'تاريخ التعيين',
      'assignment_status_updated': 'آخر تحديث للحالة',
      'contributors': 'المساهمون',
      'assignment_submitted_by': 'مُرسل من قبل',
      'assignment_approved_by': 'اعتمد من قبل',
      'public_link_enabled': 'رابط عام مفعّل',
      'public_link': 'رابط عام',
      'unknown': 'غير معروف',
      'n_a': 'غير متاح',
      'enter_data': 'إدخال البيانات',
      'download_for_offline': 'تنزيل للعمل دون اتصال',
      'downloading_offline_form': 'جارٍ تنزيل النموذج للاستخدام دون اتصال…',
      'offline_form_saved': 'تم حفظ النموذج للوصول دون اتصال.',
      'offline_form_save_failed': 'تعذر حفظ النموذج دون اتصال. أعد المحاولة عند توفر اتصال مستقر.',
      'offline_form_not_downloaded': 'هذا النموذج غير متاح دون اتصال. قم بتنزيله أثناء الاتصال بالإنترنت.',
      'offline_download_requires_connection': 'اتصل بالإنترنت لتنزيل هذا النموذج للاستخدام دون اتصال.',
      'offline_form_export_requires_connection':
          'اتصل بالإنترنت لتصدير PDF أو Excel أو تقارير التحقق. النسخة دون اتصال لا تتضمن ملفات التصدير.',
      'offline_open_saved_copy': 'فتح النسخة المحفوظة دون اتصال',
      'remove_offline_copy': 'إزالة النسخة دون اتصال',
      'offline_form_removed':
          'تمت إزالة النسخة دون اتصال. أعد التنزيل عند الاتصال بالإنترنت.',
      'offline_saved_copy_details_tooltip':
          'نسخة دون اتصال — التفاصيل والإزالة',
      'offline_copy_sheet_title': 'نسخة النموذج دون اتصال',
      'offline_copy_saved_on_label': 'تم الحفظ في',
      'offline_copy_files_cached': '%(count)d موارد مخزنة مؤقتًا',
      'offline_stale_bundle_banner_title': 'النماذج دون اتصال تحتاج إلى تحديث',
      'offline_stale_bundle_banner_body_online':
          'تغيّر النموذج على الخادم. يُحدّث الجهاز النسخ دون اتصال تلقائيًا عند الاتصال. إذا تعذّر ذلك، افتح كل نموذج يظهر عليه التحذير ثم اضغط تحديث النسخة دون اتصال.',
      'offline_stale_bundle_banner_body_offline':
          'تغيّر النموذج على الخادم. اتصل بالإنترنت ليتمكن الجهاز من تحديث النسخ دون اتصال تلقائيًا.',
      'offline_stale_bundle_updates_snackbar':
          'تم تحديث النسخ دون اتصال إلى أحدث إصدار.',
      'offline_stale_bundle_partial_refresh':
          'تعذّر تحديث بعض النسخ دون اتصال. اضغط رمز التحذير على النموذج ثم تحديث النسخة دون اتصال.',
      'offline_stale_bundle_sheet_notice':
          'قد لا تطابق هذه النسخة دون اتصال النموذج الحالي على الخادم. حدّثها لتجنب مشاكل الإصدارات.',
      'offline_stale_bundle_update_now': 'تحديث النسخة دون اتصال',
      'approve': 'الموافقة',
      'reopen': 'إعادة الفتح',
      'view_public_submissions': 'عرض التقديمات العامة',
      'view_submission': 'عرض التقديم',
      'view_submissions': 'عرض التقديمات',
      'open_form': 'فتح النموذج',
      'no_forms_assigned_or_submitted_for':
          'لم يتم تعيين أو تقديم أي نماذج من خلال الروابط العامة لـ',
      'admins_can_assign_forms':
          'يمكن للمسؤولين تعيين النماذج أو إنشاء روابط عامة من خلال لوحة تحكم المسؤول',
      'create_a_report': 'إنشاء تقرير',
      'delete_self_reported_assignment': 'حذف المهمة المبلغ عنها ذاتياً',
      'quick_actions': 'إجراءات سريعة',
      'new_assignment': 'مهمة جديدة',
      'new_template': 'قالب جديد',
      'key_metrics': 'مقاييس رئيسية',
      'overview': 'نظرة عامة',
      'create_new_assignment': 'إنشاء مهمة جديدة',
      'browse_available_templates': 'تصفح القوالب المتاحة',
      'enter_your_name': 'أدخل اسمك',
      'enter_your_job_title': 'أدخل مسمى وظيفتك',
      'edit_name': 'تعديل الاسم',
      'edit_title': 'تعديل المسمى الوظيفي',
      'name_cannot_be_empty': 'لا يمكن أن يكون الاسم فارغاً',
      'title_cannot_be_empty': 'لا يمكن أن يكون المسمى الوظيفي فارغاً',
      'profile_updated_successfully': 'تم تحديث الملف الشخصي بنجاح',
      'error_updating_profile': 'خطأ في تحديث الملف الشخصي',
      'color_picker_coming_soon': 'أداة اختيار الألوان قريباً',
      'chatbot_preference_update_coming_soon':
          'تحديث تفضيلات المساعد الذكي قريباً',
      'select_color': 'اختر لوناً',
      'current_color': 'اللون الحالي',
      'profile_color_updated': 'تم تحديث لون الملف الشخصي بنجاح',
      'profile_color_update_failed': 'فشل تحديث لون الملف الشخصي',
      'admin_dashboard': 'لوحة تحكم المسؤول',
      'no_data_available': 'لا توجد بيانات متاحة',
      'total_users': 'إجمالي المستخدمين',
      'admins': 'المسؤولون',
      'system_administrators': 'مسؤولو النظام',
      'focal_points': 'النقاط المحورية',
      'country_focal_points': 'النقاط المحورية للدولة',
      'form_templates': 'قوالب النماذج',
      'active_assignments': 'المهام النشطة',
      'todays_logins': 'تسجيلات الدخول اليوم',
      'successful_logins_today': 'تسجيلات دخول ناجحة اليوم',
      'pending_submissions': 'الطلبات المعلقة',
      'overdue_assignments': 'المهام المتأخرة',
      'security_alerts': 'تنبيهات الأمان',
      'successful_logins': 'تسجيلات الدخول الناجحة',
      'user_activities': 'أنشطة المستخدم',
      'active_sessions': 'الجلسات النشطة',
      'all_notifications_marked_as_read': 'تم تعليم جميع الإشعارات كمقروءة',
      'mark_as_read': 'تعليم كمقروء',
      'mark_as_unread': 'تعليم كغير مقروء',
      'notification_preferences': 'تفضيلات الإشعارات',
      'sound_notifications': 'إشعارات الصوت',
      'email_frequency': 'تكرار البريد الإلكتروني',
      'instant': 'فوري',
      'daily_digest': 'ملخص يومي',
      'weekly_digest': 'ملخص أسبوعي',
      'digest_schedule': 'جدول الملخص',
      'day_of_week': 'يوم الأسبوع',
      'monday': 'الاثنين',
      'tuesday': 'الثلاثاء',
      'wednesday': 'الأربعاء',
      'thursday': 'الخميس',
      'friday': 'الجمعة',
      'saturday': 'السبت',
      'sunday': 'الأحد',
      'time_local_time': 'الوقت (الوقت المحلي)',
      'notification_types': 'أنواع الإشعارات',
      'preferences_saved_successfully': 'تم حفظ التفضيلات بنجاح',
      'enable_sound': 'تفعيل الصوت',
      'play_sound_for_new_notifications': 'تشغيل الصوت للإشعارات الجديدة',
      'configure_notification_types_description': 'قم بتكوين أنواع الإشعارات التي تريد تلقيها عبر البريد الإلكتروني والإشعارات الفورية',
      'notification_type': 'نوع الإشعار',
      'push': 'فوري',
      'all': 'الكل',
      'save_preferences': 'حفظ التفضيلات',
      'select_digest_time_description': 'حدد الوقت الذي تريد فيه تلقي الملخص',
      'failed_to_save_preferences': 'فشل في حفظ التفضيلات',
      'assignment_created': 'تم إنشاء المهمة',
      'assignment_submitted': 'تم إرسال المهمة',
      'assignment_approved': 'تم الموافقة على المهمة',
      'assignment_reopened': 'تم إعادة فتح المهمة',
      'public_submission_received': 'تم استلام التقديم العام',
      'form_updated': 'تم تحديث النموذج',
      'document_uploaded': 'تم تحميل المستند',
      'user_added_to_country': 'تمت إضافة المستخدم إلى البلد',
      'template_updated': 'تم تحديث القالب',
      'self_report_created': 'تم إنشاء التقرير الذاتي',
      'deadline_reminder': 'تذكير بالموعد النهائي',
      'search_audit_logs': 'البحث في سجلات التدقيق...',
      'home_screen_widget_title': 'عنصر الشاشة الرئيسية',
      'audit_widget_activity_types_hint':
          'اختر أنواع النشاط للعنصر. بدون اختيار تُعرض كل الأنواع. يُحفظ على هذا الجهاز.',
      'action': 'الإجراء',
      'all_actions': 'جميع الإجراءات',
      'create': 'إنشاء',
      'update': 'تحديث',
      'user': 'المستخدم',
      'all_users': 'جميع المستخدمين',
      'from_date': 'من تاريخ',
      'to_date': 'إلى تاريخ',
      'select_date': 'اختر التاريخ',
      'no_description': 'لا يوجد وصف',
      'search_api_endpoints': 'البحث في نقاط نهاية API...',
      'http_method': 'طريقة HTTP',
      'all_methods': 'جميع الطرق',
      'get': 'GET',
      'post': 'POST',
      'put': 'PUT',
      'delete_method': 'DELETE',
      'deprecated': 'مهجور',
      'beta': 'بيتا',
      'new_api_key': 'مفتاح API جديد',
      'time_range': 'النطاق الزمني',
      'last_30_days': 'آخر 30 يوماً',
      'last_90_days': 'آخر 90 يوماً',
      'last_year': 'العام الماضي',
      'all_time': 'كل الوقت',
      'metric': 'المقياس',
      'all_metrics': 'جميع المقاييس',
      'active_users': 'المستخدمون النشطون',
      'logins': 'تسجيلات الدخول',
      'metric_submissions': 'الطلبات',
      'page_views': 'مشاهدات الصفحة',
      'search_indicators': 'البحث عن المؤشرات...',
      'category': 'الفئة',
      'all_categories': 'جميع الفئات',
      'output': 'الإخراج',
      'outcome': 'النتيجة',
      'impact': 'التأثير',
      'all_sectors': 'جميع القطاعات',
      'health': 'الصحة',
      'wash': 'WASH',
      'shelter': 'المأوى',
      'education': 'التعليم',
      'indicators': 'المؤشرات',
      'new_indicator': 'مؤشر جديد',
      'search_organizations': 'البحث عن المنظمات...',
      'entity_type': 'نوع الكيان',
      'all_types': 'جميع الأنواع',
      'national_societies': 'الجمعيات الوطنية',
      'ns_structure': 'هيكل NS',
      'secretariat': 'الأمانة',
      'divisions': 'الأقسام',
      'departments': 'الإدارات',
      'regional_offices': 'المكاتب الإقليمية',
      'cluster_offices': 'مكاتب الكتلة',
      'add_organization': 'إضافة منظمة',
      'search_resources': 'البحث عن الموارد...',
      'no_indicators_found': 'لم يتم العثور على مؤشرات',
      'no_organizations_found': 'لم يتم العثور على منظمات',
      'no_resources_found': 'لم يتم العثور على موارد',
      'resources_unified_planning_section_title': 'الخطط والتقارير الموحدة',
      'resources_unified_planning_section_subtitle':
          'خطط وتقارير منتصف العام والتقارير السنوية من IFRC GO (يتم تحميلها في التطبيق).',
      'unified_planning_empty': 'لا توجد وثائق تخطيط موحدة تطابق بحثك.',
      'unified_planning_fresh_badge': 'جديد',
      'unified_planning_filter_all_countries': 'جميع الدول',
      'unified_error_config':
          'تعذر تحميل إعدادات التخطيط الموحد من الخادم. حاول مرة أخرى لاحقًا.',
      'unified_error_credentials':
          'وثائق الاتحاد غير متوفرة في هذا التطبيق. يُرجى الاتصال بمسؤول النظام.',
      'unified_error_ifrc_auth':
          'تعذر الوصول إلى وثائق الاتحاد. يُرجى الاتصال بمسؤول النظام إذا استمرت المشكلة.',
      'unified_error_ifrc':
          'تعذر تحميل الوثائق من IFRC GO. تحقق من الاتصال وحاول مرة أخرى.',
      'no_plugins_found': 'لم يتم العثور على إضافات',
      'no_translations_found': 'لم يتم العثور على ترجمات',
      'no_documents_found': 'لم يتم العثور على مستندات',
      'no_users_found': 'لم يتم العثور على مستخدمين',
      'loading_user_profile': 'جاري تحميل ملف المستخدم…',
      'failed_load_user_profile': 'تعذر تحميل هذا المستخدم.',
      'admin_user_detail_matrix_read_only_bundled':
          'أدوار إدارية مجمّعة (كاملة/أساسية/نظام) — استخدم الويب لتعديل الوصول حسب المجال.',
      'admin_user_detail_rbac_incomplete':
          'تعذر إنشاء قائمة أدوار صالحة. تحقق من الوصول أو أعد المحاولة.',
      'assigned_roles_title': 'الأدوار المعيّنة',
      'role_type_label': 'نوع الدور',
      'permissions_by_role': 'الأذونات حسب الدور',
      'all_permissions_union': 'جميع الأذونات (من الأدوار)',
      'entity_permissions_title': 'أذونات الكيان',
      'manage_users_detail_footer':
          'لتعديل الأدوار أو صلاحيات الكيانات أو الأجهزة أو الإشعارات، استخدم نموذج المستخدم في الويب.',
      'no_roles_assigned': 'لا توجد أدوار RBAC معيّنة.',
      'no_entities_assigned': 'لا توجد كيانات معيّنة.',
      'entity_permission_unnamed': 'بدون اسم',
      'entity_region_other': 'منطقة أخرى',
      'no_permissions_listed': 'لا توجد أذونات مدرجة لهذا الدور.',
      'user_dir_assignment_roles': 'أدوار المهام',
      'user_dir_admin_roles': 'المسؤول والنظام',
      'user_dir_other_roles': 'أدوار أخرى',
      'admin_role_access_area': 'المجال',
      'admin_role_access_view': 'عرض',
      'admin_role_access_manage': 'إدارة',
      'admin_role_de_heading': 'مستكشف البيانات',
      'admin_role_de_table': 'جدول',
      'admin_role_de_analysis': 'تحليل',
      'admin_role_de_compliance': 'الامتثال',
      'admin_role_note_admin_full': 'جميع صلاحيات الإدارة (دور مجمّع)',
      'admin_role_note_admin_core': 'أساسيات الإدارة (دور مجمّع)',
      'admin_role_other_admin_roles': 'أدوار إدارية أخرى',
      'users_directory_role_all': 'جميع الأدوار',
      'users_directory_country_all': 'جميع البلدان',
      'no_assignments_found': 'لم يتم العثور على مهام',
      'no_templates_found': 'لم يتم العثور على قوالب',
      'assignment_deleted_successfully': 'تم حذف المهمة بنجاح',
      'failed_to_delete_assignment': 'فشل حذف المهمة',
      'timeline_view': 'عرض الجدول الزمني',
      'view_all_public_submissions': 'عرض جميع التقديمات العامة',
      'items_requiring_attention': 'العناصر التي تحتاج إلى انتباه',
      'recent_activity': 'النشاط الأخير',
      'recent_activity_7_days': 'النشاط الأخير (7 أيام)',
      'general_settings': 'الإعدادات العامة',
      'security_settings': 'إعدادات الأمان',
      'system_settings': 'إعدادات النظام',
      'application_settings': 'إعدادات التطبيق',
      'language_settings': 'إعدادات اللغة',
      'notification_settings': 'إعدادات الإشعارات',
      'authentication_settings': 'إعدادات المصادقة',
      'permission_settings': 'إعدادات الأذونات',
      'database_settings': 'إعدادات قاعدة البيانات',
      'cloud_storage_settings': 'إعدادات التخزين السحابي',
      'configure_general_application_settings':
          'تكوين الإعدادات العامة للتطبيق',
      'manage_supported_languages_and_translations':
          'إدارة اللغات والترجمات المدعومة',
      'configure_notification_preferences': 'تكوين تفضيلات الإشعارات',
      'configure_authentication_and_authorization': 'تكوين المصادقة والتفويض',
      'manage_user_permissions_and_roles': 'إدارة أذونات المستخدمين والأدوار',
      'configure_database_connections_and_backups':
          'تكوين اتصالات قاعدة البيانات والنسخ الاحتياطية',
      'configure_cloud_storage_and_file_management':
          'تكوين التخزين السحابي وإدارة الملفات',

      // Indicator Bank
      'indicator_bank_title': 'بنك المؤشرات',
      'indicator_bank_loading': 'جاري تحميل بنك المؤشرات...',
      'indicator_bank_error': 'حدث خطأ ما',
      'indicator_bank_search_placeholder': 'البحث في المؤشرات...',
      'indicator_bank_filter_placeholder': 'تصفية المؤشرات...',
      'indicator_bank_browse_description':
          'تصفح والبحث عن المؤشرات للاستجابة الإنسانية',
      'indicator_bank_grid_view': 'عرض الشبكة',
      'indicator_bank_table_view': 'عرض الجدول',
      'indicator_bank_show_filters': 'إظهار المرشحات',
      'indicator_bank_hide_filters': 'إخفاء المرشحات',
      'indicator_bank_filters': 'المرشحات',
      'indicator_bank_filter_type': 'النوع',
      'indicator_bank_filter_type_all': 'جميع الأنواع',
      'indicator_bank_filter_sector': 'القطاع',
      'indicator_bank_filter_sector_all': 'جميع القطاعات',
      'indicator_bank_filter_subsector': 'القطاع الفرعي',
      'indicator_bank_filter_subsector_all': 'جميع القطاعات الفرعية',
      'indicator_bank_list_tier_also_related': 'مرتبط أيضًا',
      'indicator_bank_filter_status': 'الحالة',
      'indicator_bank_filter_status_active': 'النشطة فقط',
      'indicator_bank_filter_status_all': 'الكل',
      'indicator_bank_apply_filters': 'تطبيق المرشحات',
      'indicator_bank_clear_all': 'مسح الكل',
      'indicator_bank_showing': 'عرض',
      'indicator_bank_indicators': 'مؤشرات',
      'indicator_bank_indicator': 'مؤشر',
      'indicator_bank_no_sectors': 'لم يتم العثور على قطاعات',
      'indicator_bank_no_indicators': 'لم يتم العثور على مؤشرات',
      'indicator_bank_table_name': 'الاسم',
      'indicator_bank_table_type': 'النوع',
      'indicator_bank_table_sector': 'القطاع',
      'indicator_bank_table_subsector': 'القطاع الفرعي',
      'indicator_bank_table_unit': 'الوحدة',
      'indicator_bank_propose_new': 'اقتراح مؤشر جديد',
      'indicator_bank_propose_title': 'اقتراح مؤشر جديد',
      'indicator_bank_propose_contact_info': 'معلومات الاتصال',
      'indicator_bank_propose_your_name': 'اسمك *',
      'indicator_bank_propose_email': 'عنوان البريد الإلكتروني *',
      'indicator_bank_propose_indicator_info': 'معلومات المؤشر',
      'indicator_bank_propose_indicator_name': 'اسم المؤشر *',
      'indicator_bank_propose_definition': 'التعريف *',
      'indicator_bank_propose_type': 'النوع',
      'indicator_bank_propose_unit': 'وحدة القياس',
      'indicator_bank_propose_sector': 'القطاع',
      'indicator_bank_propose_primary_sector': 'القطاع الأساسي *',
      'indicator_bank_propose_secondary_sector': 'القطاع الثانوي',
      'indicator_bank_propose_tertiary_sector': 'القطاع الثالث',
      'indicator_bank_propose_subsector': 'القطاع الفرعي',
      'indicator_bank_propose_primary_subsector': 'القطاع الفرعي الأساسي *',
      'indicator_bank_propose_secondary_subsector': 'القطاع الفرعي الثانوي',
      'indicator_bank_propose_tertiary_subsector': 'القطاع الفرعي الثالث',
      'indicator_bank_propose_emergency': 'سياق الطوارئ',
      'indicator_bank_propose_related_programs': 'البرامج ذات الصلة',
      'indicator_bank_propose_reason': 'سبب الاقتراح *',
      'indicator_bank_propose_additional_notes': 'ملاحظات إضافية',
      'indicator_bank_propose_submit': 'إرسال الاقتراح',
      'indicator_bank_propose_thank_you': 'شكراً لك!',
      'indicator_bank_propose_success': 'تم إرسال اقتراح المؤشر بنجاح.',
      'indicator_bank_propose_failed':
          'فشل إرسال الاقتراح. يرجى المحاولة مرة أخرى.',
      'indicator_bank_name_required': 'الاسم مطلوب',
      'indicator_bank_email_required': 'البريد الإلكتروني مطلوب',
      'indicator_bank_indicator_name_required': 'اسم المؤشر مطلوب',
      'indicator_bank_definition_required': 'التعريف مطلوب',
      'indicator_bank_primary_sector_required': 'القطاع الأساسي مطلوب',
      'indicator_bank_primary_subsector_required':
          'القطاع الفرعي الأساسي مطلوب',
      'indicator_bank_reason_required': 'السبب مطلوب',

      // Indicator Detail
      'indicator_detail_title': 'تفاصيل المؤشر',
      'indicator_detail_loading': 'جاري تحميل تفاصيل المؤشر...',
      'indicator_detail_error': 'حدث خطأ ما',
      'indicator_detail_not_found': 'لم يتم العثور على المؤشر',
      'indicator_detail_go_back': 'رجوع',
      'indicator_detail_definition': 'التعريف',
      'indicator_detail_details': 'التفاصيل',
      'indicator_detail_type': 'النوع',
      'indicator_detail_unit': 'الوحدة',
      'indicator_detail_sector': 'القطاع',
      'indicator_detail_subsector': 'القطاع الفرعي',
      'indicator_detail_emergency_context': 'سياق الطوارئ',
      'indicator_detail_related_programs': 'البرامج ذات الصلة',
      'indicator_detail_status': 'الحالة',
      'indicator_detail_archived': 'مؤرشف',
      'indicator_detail_yes': 'نعم',
      'editIndicator': 'تعديل المؤشر',

      // Quiz Game
      'quiz_game': 'لعبة الاختبار',
      'quiz_game_title': 'لعبة الاختبار',
      'quiz_game_test_your_knowledge': 'اختبر معرفتك!',
      'quiz_game_loading': 'جاري تحميل الاختبار...',
      'quiz_game_error': 'خطأ في تحميل الاختبار',
      'quiz_game_try_again': 'حاول مرة أخرى',
      'quiz_game_start_quiz': 'بدء الاختبار',
      'quiz_game_which_sector': 'إلى أي قطاع ينتمي هذا المؤشر؟',
      'quiz_game_which_subsector': 'إلى أي قطاع فرعي ينتمي هذا المؤشر؟',
      'quiz_game_definition': 'التعريف',
      'quiz_game_no_definition': 'لا يوجد تعريف متاح',
      'quiz_game_correct': 'صحيح!',
      'quiz_game_incorrect': 'غير صحيح',
      'quiz_game_next_question': 'السؤال التالي',
      'quiz_game_view_results': 'عرض النتائج',
      'quiz_game_quiz_complete': 'اكتمل الاختبار!',
      'quiz_game_excellent_work': 'عمل ممتاز!',
      'quiz_game_well_done': 'أحسنت!',
      'quiz_game_good_effort': 'جهد جيد!',
      'quiz_game_keep_practicing': 'استمر في الممارسة!',
      'quiz_game_out_of': 'من',
      'quiz_game_statistics': 'الإحصائيات',
      'quiz_game_correct_answers': 'صحيحة',
      'quiz_game_incorrect_answers': 'خاطئة',
      'quiz_game_total': 'الإجمالي',
      'quiz_game_home': 'الرئيسية',
      'quiz_game_play_again': 'العب مرة أخرى',
      'quiz_game_no_indicators_available': 'لا توجد مؤشرات مع قطاعات أو قطاعات فرعية متاحة للاختبار',
      'quiz_game_failed_to_start': 'فشل في بدء الاختبار',
      'quiz_game_leaderboard': 'لوحة المتصدرين',
      'quiz_game_view_leaderboard': 'عرض لوحة المتصدرين',
      'quiz_game_loading_leaderboard': 'جاري تحميل لوحة المتصدرين...',
      'quiz_game_no_leaderboard_data': 'لا توجد بيانات لوحة متصدرين متاحة بعد',
      'quiz_game_top_players': 'أفضل اللاعبين',
      'quiz_game_you': 'أنت',
      'quiz_game_points': 'نقاط',

      // AI Chat (immersive)
      'ai_policy_acknowledge_snackbar':
          'يرجى الإقرار بسياسة الذكاء الاصطناعي للمتابعة.',
      'ai_use_policy_title': 'سياسة استخدام الذكاء الاصطناعي',
      'ai_policy_do_not_share': 'لا تشارك معلومات حساسة.',
      'ai_policy_traces_body':
          'نستخدم سجلات النظام والقياس عن بُعد لتحسين المساعد. قد تُعالج رسائلك لدى مزودي ذكاء اصطناعي خارجيين.',
      'ai_policy_purpose_title': 'الغرض',
      'ai_policy_purpose_body':
          'يساعدك مساعد الذكاء الاصطناعي على استكشاف البيانات والمستندات على هذه المنصة. يمكنه الإجابة عن المؤشرات والبلدان والمهام والبحث في المستندات المرفوعة.',
      'ai_policy_acceptable_use_title': 'الاستخدام المقبول',
      'ai_policy_acceptable_use_body':
          '• اسأل عن بيانات المنصة والمؤشرات والمستندات.\n'
          '• لا تشارك كلمات مرور أو بيانات اعتماد أو تفاصيل تشغيلية سرية للغاية.\n'
          '• لا تلصق بيانات شخصية أو مالية.',
      'ai_policy_accuracy_title': 'الدقة',
      'ai_policy_accuracy_body':
          'قد يخطئ الذكاء الاصطناعي أو يُسيء فهم البيانات. تحقق دائمًا من المعلومات المهمة مقابل المصدر أو المستندات.',
      'ai_policy_confirm_footer':
          'أكد أنك قرأت المعلومات أعلاه لاستخدام المساعد.',
      'ai_policy_i_understand': 'أفهم',
      'ai_policy_acknowledge_cta': 'الإقرار بسياسة استخدام الذكاء الاصطناعي',
      'ai_sources_heading': 'استخدام المصادر:',
      'ai_source_databank': 'بنك البيانات',
      'ai_source_system_documents': 'مستندات النظام',
      'ai_source_upr_documents': 'مستندات UPR',
      'ai_sources_minimum_note':
          'يبقى مصدر واحد على الأقل مفعّلًا (كما في المساعد على الويب).',
      'ai_tour_guide_question': 'هل تريد أن أرشدك خلال هذا؟',
      'ai_tour_navigate_question': 'هل تريد الانتقال إلى الصفحة ذات الصلة؟',
      'ai_tour_web_only_snackbar':
          'الجولات التفاعلية متاحة على نسخة الويب. جارٍ فتح الصفحة...',
      'ai_new_chat': 'محادثة جديدة',
      'ai_semantic_open_drawer_hint': 'يفتح المحادثات والإعدادات',
      'ai_tooltip_new_chat': 'محادثة جديدة',
      'ai_semantic_new_chat_label': 'محادثة جديدة',
      'ai_semantic_new_chat_hint': 'يبدأ محادثة فارغة جديدة',
      'ai_beta_tester_banner':
          'مختبر بيتا للذكاء الاصطناعي — قد تكون ميزات تجريبية مفعّلة.',
      'ai_empty_welcome': 'كيف يمكنني مساعدتك اليوم؟',
      'ai_policy_chip_title': 'سياسة استخدام الذكاء الاصطناعي',
      'ai_policy_sheet_summary_line':
          'ملخص قصير — افتح الورقة لجميع التفاصيل.',
      'ai_policy_compact_warning':
          'لا تشارك معلومات حساسة. نستخدم سجلات النظام والقياس لتحسين المساعد؛ قد تُعالج الرسائل لدى مزودي ذكاء اصطناعي خارجيين.',
      'ai_read_full_policy': 'قراءة السياسة كاملة',
      'ai_try_asking': 'جرّب أن تسأل',
      'ai_copied': 'تم النسخ!',
      'ai_tooltip_copy': 'نسخ',
      'ai_tooltip_edit_message': 'تعديل',
      'ai_tooltip_helpful': 'مفيد',
      'ai_tooltip_not_helpful': 'غير مفيد',
      'ai_footer_model_warning':
          'قد يخطئ الذكاء الاصطناعي. تحقق من المعلومات المهمة.',
      'ai_chat_error_network':
          'تعذر الوصول إلى خدمة الذكاء الاصطناعي. تحقق من اتصال الإنترنت وحاول مرة أخرى.',
      'ai_chat_error_timeout': 'انتهت مهلة الطلب. تحقق من الاتصال وحاول مرة أخرى.',
      'ai_chat_error_server': 'حدث خطأ. يرجى المحاولة مرة أخرى.',
      'ai_agent_progress_title': 'خطوات قيد التنفيذ',
      'ai_agent_step_done': 'تم.',
      'ai_agent_step_preparing_query': 'جارٍ تحضير الاستفسار…',
      'ai_agent_step_planning': 'جارٍ التخطيط للنهج…',
      'ai_agent_step_reviewing': 'جارٍ مراجعة النتائج…',
      'ai_agent_step_drafting': 'جارٍ صياغة الإجابة…',
      'ai_agent_step_replying': 'جارٍ الرد…',
      'ai_agent_step_thinking_next': 'أفكر فيما يجب فعله بعد ذلك.',
      'ai_agent_step_no_shortcut_full':
          'لا يوجد اختصار بأداة واحدة — استخدام مسار التخطيط الكامل.',
      'ai_agent_step_no_shortcut_reviewing':
          'لا يوجد اختصار بأداة واحدة لهذا الطلب — جارٍ المراجعة: %s',
      'ai_response_sources': 'المصادر',
      'ai_response_sources_with_count': 'المصادر (%s)',
      'ai_tooltip_configure_sources': 'تهيئة مصادر البيانات',
      'ai_input_policy_required':
          'أقر بسياسة الذكاء الاصطناعي أعلاه لإرسال الرسائل',
      'ai_input_placeholder_message': 'رسالة',
      'ai_input_placeholder_edit': 'تعديل الرسالة…',
      'ai_tooltip_cancel_edit': 'إلغاء التعديل',
      'ai_stop': 'إيقاف',
      'ai_conversations_drawer_title': 'المحادثات',
      'ai_search_conversations_hint': 'البحث في المحادثات',
      'ai_no_conversations_body':
          'لا محادثات بعد.\nابدأ محادثة جديدة!',
      'ai_no_conversations_offline':
          'لا محادثات بعد.\nابدأ محادثة جديدة (دون اتصال).',
      'ai_no_conversations_filtered': 'لم يُعثر على محادثات',
      'ai_section_pinned': 'مثبّتة',
      'ai_section_recent': 'حديثة',
      'ai_quick_prompt_1': 'كم عدد المتطوعين في بنغلاديش؟',
      'ai_quick_prompt_2': 'المتطوعون في سوريا عبر الزمن',
      'ai_quick_prompt_3': 'خريطة حرارية عالمية للمتطوعين حسب البلد',
      'ai_quick_prompt_4': 'عدد الفروع في كينيا',
      'ai_quick_prompt_5': 'الموظفون والوحدات المحلية في نيجيريا',
      'ai_clear_all_dialog_title': 'مسح كل المحادثات',
      'ai_clear_all_dialog_body':
          'هل تريد بالتأكيد حذف جميع المحادثات؟ لا يمكن التراجع عن هذا الإجراء.',
      'ai_clear_all_button': 'مسح الكل',
      'ai_clear_all_row': 'مسح كل المحادثات',
      'ai_help_about_row': 'المساعدة وحول',
      'ai_pin': 'تثبيت',
      'ai_unpin': 'إلغاء التثبيت',
      'ai_delete_conversation_title': 'حذف المحادثة؟',
      'ai_delete_conversation_body':
          'حذف هذه المحادثة؟ لا يمكن التراجع.',
      'ai_new_chat_title_fallback': 'محادثة جديدة',
      'ai_help_dialog_title': 'مساعدة مساعد الذكاء الاصطناعي',
      'ai_help_about_heading': 'حول',
      'ai_help_about_paragraph':
          'يساعدك مساعد الذكاء الاصطناعي على العثور على معلومات والإجابة عن أسئلة حول بنك بيانات شبكة الاتحاد الدولي.',
      'ai_help_features_heading': 'الميزات',
      'ai_help_feature_bullet_1':
          '• اطرح أسئلة عن المهام والموارد وغير ذلك',
      'ai_help_feature_bullet_2': '• احصل على مساعدة للتنقل في التطبيق',
      'ai_help_feature_bullet_3':
          '• ابحث في سجل محادثاتك',
      'ai_help_feature_bullet_4':
          '• تُحفظ المحادثات عند تسجيل الدخول',
      'ai_help_tips_heading': 'نصائح',
      'ai_help_tip_bullet_1':
          '• كن محددًا في أسئلتك لنتائج أفضل',
      'ai_help_tip_bullet_2':
          '• انقر الروابط في الردود للانتقال إلى الصفحات',
      'ai_help_tip_bullet_3':
          '• استخدم شريط البحث للعثور على محادثات سابقة',
      'ai_help_tip_bullet_4':
          '• اضغط مطولًا على محادثة لفتح القائمة (تثبيت أو حذف)',
      'ai_got_it': 'فهمت',
      'ai_score_confidence': 'الثقة',
      'ai_score_grounding': 'التأسيس',
      'ai_default_assistant_title': 'مساعد الذكاء الاصطناعي',
      'resources_other_subgroup': 'أخرى',
      'resources_list_truncated_hint':
          'عرض أحدث العناصر. استخدم البحث للعثور على مستند معيّن.',
      'ai_assistant': 'مساعد الذكاء الاصطناعي',
    },
    'hi': {
      'app_name': 'IFRC नेटवर्क डेटाबैंक',
      'navigation': 'नेविगेशन',
      'home': 'होम',
      'dashboard': 'डैशबोर्ड',
      'resources': 'संसाधन',
      'indicator_bank': 'संकेतक बैंक',
      'disaggregation_analysis': 'विघटन विश्लेषण',
      'analysis': 'विश्लेषण',
      'data_visualization': 'डेटा विज़ुअलाइज़ेशन',
      'settings': 'सेटिंग्स',
      'notifications': 'सूचनाएं',
      'admin': 'प्रशासन',
      'admin_panel': 'प्रशासन पैनल',
      'customize_tabs': 'टैब कस्टमाइज़ करें',
      'customize_tabs_description': 'दिखाने के लिए टैब चुनें और उन्हें पुनर्क्रमित करने के लिए खींचें।',
      'reset_to_default': 'डिफ़ॉल्ट पर रीसेट',
      'tab_always_shown': 'हमेशा दिखाया गया',
      'minimum_tabs_warning': 'कम से कम 2 टैब दिखाई देने चाहिए।',
      'access_denied': 'पहुंच अस्वीकृत',
      'general': 'सामान्य',
      'document_management': 'दस्तावेज़ प्रबंधन',
      'translation_management': 'अनुवाद प्रबंधन',
      'plugin_management': 'प्लगइन प्रबंधन',
      'system_configuration': 'सिस्टम कॉन्फ़िगरेशन',
      'user_management': 'उपयोगकर्ता प्रबंधन',
      'manage_users': 'उपयोगकर्ता प्रबंधित करें',
      'access_requests_title': 'देश स्तरीय पहुँच अनुरोध',
      'access_requests_subtitle':
          'देश-स्तर की पहुँच के अनुरोधों को स्वीकार या अस्वीकार करें।',
      'access_requests_pending': 'लंबित',
      'access_requests_processed': 'हाल के निर्णय',
      'access_requests_empty': 'कोई पहुँच अनुरोध नहीं।',
      'access_requests_approve': 'स्वीकार करें',
      'access_requests_reject': 'अस्वीकार करें',
      'access_requests_approve_all': 'सभी स्वीकार करें',
      'access_requests_approve_all_confirm':
          'सभी लंबित देश स्तरीय पहुँच अनुरोध स्वीकार करें?',
      'access_requests_reject_confirm':
          'इस पहुँच अनुरोध को अस्वीकार करें? उपयोगकर्ता को पहुँच नहीं मिलेगी।',
      'access_requests_country': 'देश',
      'access_requests_message': 'संदेश',
      'access_requests_requested_at': 'अनुरोधित',
      'access_requests_processed_at': 'संसाधित',
      'access_requests_auto_approve_hint':
          'सर्वर सेटिंग्स में स्वचालित स्वीकृति सक्षम हो सकती है।',
      'access_requests_status_pending': 'लंबित',
      'access_requests_status_approved': 'स्वीकृत',
      'access_requests_status_rejected': 'अस्वीकृत',
      'access_requests_by': 'द्वारा',
      'access_requests_load_failed':
          'पहुँच अनुरोध लोड नहीं किए जा सके।',
      'access_requests_action_failed': 'कार्रवाई पूरी नहीं हो सकी।',
      'access_requests_view_forbidden':
          'आपके पास सर्वर पर पहुँच अनुरोध देखने की अनुमति नहीं है।',
      'access_requests_unexpected_response': 'सर्वर से अप्रत्याशित प्रतिक्रिया।',
      'access_requests_action_forbidden':
          'आपके पास यह कार्रवाई करने की अनुमति नहीं है।',
      'users_directory_read_only':
          'यह सूची केवल पढ़ने योग्य है। वेब बैकऑफ़िस में खाते बनाएं या बदलें।',
      'login_logs_title': 'लॉगिन लॉग',
      'login_logs_filters': 'फ़िल्टर',
      'login_logs_email_hint': 'ईमेल से खोजें',
      'login_logs_event_type': 'इवेंट प्रकार',
      'login_logs_event_all': 'सभी प्रकार',
      'login_logs_event_login': 'लॉगिन',
      'login_logs_event_logout': 'लॉगआउट',
      'login_logs_event_failed': 'लॉगिन विफल',
      'login_logs_ip_label': 'IP पता',
      'login_logs_date_from': 'तिथि से',
      'login_logs_date_to': 'तिथि तक',
      'login_logs_suspicious_only': 'केवल संदिग्ध',
      'login_logs_apply': 'लागू करें',
      'login_logs_clear': 'साफ़ करें',
      'login_logs_no_entries': 'कोई इवेंट फ़िल्टर से मेल नहीं खाता।',
      'login_logs_total': 'कुल %s इवेंट',
      'login_logs_load_more': 'और लोड करें',
      'login_logs_user_not_resolved': 'कोई मेल खाता उपयोगकर्ता खाता नहीं',
      'login_logs_device': 'डिवाइस',
      'login_logs_browser': 'ब्राउज़र',
      'login_logs_suspicious_badge': 'संदिग्ध',
      'login_logs_recent_failures': '%s हाल की विफलताएँ',
      'login_logs_open': 'लॉगिन लॉग',
      'session_logs_title': 'सत्र लॉग',
      'admin_filters': 'फ़िल्टर',
      'session_logs_email_hint': 'ईमेल से खोजें',
      'session_logs_min_duration': 'न्यूनतम मिनट (सत्र या सक्रिय)',
      'session_logs_active_only': 'केवल सक्रिय सत्र',
      'admin_filters_apply': 'लागू करें',
      'admin_filters_clear': 'साफ़ करें',
      'session_logs_no_entries': 'कोई सत्र फ़िल्टर से मेल नहीं खाता।',
      'session_logs_total': 'कुल %s सत्र',
      'session_logs_load_more': 'और लोड करें',
      'session_logs_session_start': 'सत्र प्रारंभ',
      'session_logs_duration': 'अवधि',
      'session_logs_session_length': 'सत्र की लंबाई',
      'session_logs_active_time': 'सक्रिय समय',
      'session_logs_minutes': '%s मि',
      'session_logs_page_views': 'पृष्ठ दृश्य',
      'session_logs_path_breakdown_title': 'पथ के अनुसार पृष्ठ दृश्य',
      'session_logs_path_breakdown_open': 'पथ विवरण देखें',
      'session_logs_path_breakdown_empty':
          'इस सत्र के लिए कोई पथ विवरण दर्ज नहीं है।',
      'session_logs_path_other_bucket': 'अन्य पथ (समेकित)',
      'session_logs_path_column': 'पथ',
      'session_logs_path_count_column': 'गिनती',
      'session_logs_distinct_paths': 'विभिन्न पथ',
      'session_logs_activities': 'गतिविधियाँ',
      'session_logs_last_activity': 'अंतिम गतिविधि',
      'session_logs_status_active': 'सक्रिय',
      'session_logs_status_ended': 'समाप्त',
      'session_logs_force_logout': 'ज़बरदस्ती लॉगआउट',
      'session_logs_force_logout_confirm':
          'इस उपयोगकर्ता को ज़बरदस्ती लॉगआउट करें? वे तुरंत लॉग आउट हो जाएँगे।',
      'session_logs_unknown_user': 'अज्ञात उपयोगकर्ता',
      'session_logs_no_activity': 'कोई गतिविधि नहीं',
      'session_logs_open': 'सत्र लॉग',
      'session_logs_ended_ok': 'सत्र समाप्त।',
      'session_logs_os': 'ऑपरेटिंग सिस्टम',
      'session_logs_user_agent': 'यूज़र एजेंट',
      'session_logs_device_section': 'डिवाइस विवरण',
      'form_data_management': 'फ़ॉर्म और डेटा प्रबंधन',
      'manage_templates': 'टेम्प्लेट प्रबंधित करें',
      'manage_assignments': 'असाइनमेंट प्रबंधित करें',
      'frontend_management': 'फ्रंटएंड प्रबंधन',
      'manage_resources': 'संसाधन प्रबंधित करें',
      'reference_data': 'संदर्भ डेटा',
      'organizational_structure': 'संगठनात्मक संरचना',
      'analytics_monitoring': 'विश्लेषण और निगरानी',
      'user_analytics': 'उपयोगकर्ता विश्लेषण',
      'audit_trail': 'ऑडिट ट्रेल',
      'api_management': 'API प्रबंधन',
      'account_settings': 'खाता सेटिंग्स',
      'profile': 'प्रोफ़ाइल',
      'preferences': 'प्राथमिकताएं',
      'language': 'भाषा',
      'select_language': 'भाषा चुनें',
      'change_password': 'पासवर्ड बदलें',
      'profile_color': 'प्रोफ़ाइल रंग',
      'chatbot': 'चैटबॉट',
      'enable_chatbot_assistance': 'चैटबॉट सहायता सक्षम करें',
      'dark_theme': 'डार्क थीम',
      'enable_dark_theme': 'डार्क थीम सक्षम करें',
      'settings_theme': 'थीम',
      'light_theme': 'लाइट थीम',
      'system_theme': 'सिस्टम',
      'select_theme': 'थीम चुनें',
      'settings_theme_set_to': 'थीम %s पर सेट की गई',
      'arabic_text_font': 'अरबी टेक्स्ट फ़ॉन्ट',
      'arabic_font_tajawal': 'ताजवाल',
      'arabic_font_system': 'सिस्टम डिफ़ॉल्ट',
      'login_to_account': 'खाते में लॉगिन करें',
      'logout': 'लॉगआउट',
      'are_you_sure_logout': 'क्या आप लॉगआउट करना चाहते हैं?',
      'cancel': 'रद्द करें',
      'name': 'नाम',
      'title': 'शीर्षक',
      'email': 'ईमेल',
      'loading': 'लोड हो रहा है...',
      'loading_home': 'होम लोड हो रहा है...',
      'home_landing_hero_description':
          'अंतर्राष्ट्रीय रेड क्रॉस और रेड क्रिसेंट सोसायटीज के फेडरेशन से व्यापक मानवीय डेटा, संकेतक और अंतर्दृष्टि का अन्वेषण करें।',
      'home_landing_chat_title': 'हमारे डेटा के साथ चैट करें',
      'home_landing_chat_description': 'नीचे प्लेटफ़ॉर्म डेटा के बारे में अपने प्रश्न टाइप करें।',
      'home_landing_ask_placeholder': 'फंडिंग, कार्यक्रमों, देशों के बारे में पूछें...',
      'home_landing_quick_prompt_1': 'मुझे अफगान रेड क्रिसेंट स्वयंसेवकों के बारे में बताएं',
      'home_landing_quick_prompt_2': 'मुझे वैश्विक आपदा प्रतिक्रिया डेटा दिखाएं',
      'home_landing_quick_prompt_3': 'मुख्य मानवीय संकेतक क्या हैं?',
      'home_landing_shortcuts_heading': 'शुरू करें',
      'home_landing_shortcut_indicators_subtitle': 'परिभाषाएँ और मेटाडेटा ब्राउज़ करें',
      'home_landing_shortcut_resources_subtitle': 'प्रकाशन और सामग्री',
      'home_landing_shortcut_countries_subtitle': 'प्रोफ़ाइल और क्षेत्रीय दृश्य',
      'home_landing_shortcut_disaggregation_subtitle': 'संकेतक मानों का विवरण',
      'home_landing_explore_title': 'वैश्विक मानचित्र और चार्ट',
      'home_landing_explore_subtitle':
          'वेबसाइट जैसे ही FDRS कुल के साथ नेटिव मानचित्र और चार्ट — ऐप छोड़े बिना।',
      'home_landing_global_indicator_volunteers': 'स्वयंसेवक',
      'home_landing_global_indicator_staff': 'कर्मचारी',
      'home_landing_global_indicator_branches': 'शाखाएँ',
      'home_landing_global_indicator_local_units': 'Local units',
      'home_landing_global_indicator_blood_donors': 'Blood donors',
      'home_landing_global_indicator_first_aid': 'First aid',
      'home_landing_global_indicator_people_reached': 'People reached',
      'home_landing_global_indicator_income': 'Income',
      'home_landing_global_indicator_expenditure': 'Expenditure',
      'home_landing_global_top_countries': 'शीर्ष देश',
      'home_landing_global_load_error':
          'मानचित्र डेटा लोड नहीं हो सका। अपना कनेक्शन जाँचें और पुनः प्रयास करें।',
      'home_landing_global_empty':
          'नवीनतम अवधि में इस संकेतक के लिए कोई मान नहीं।',
      'home_landing_global_period': 'अवधि: %s',
      'home_landing_global_map_hint':
          'पिंच करें, खींचें और विवरण के लिए किसी देश पर टैप करें',
      'home_landing_global_map_open_fullscreen': 'पूर्ण स्क्रीन',
      'home_landing_global_period_filter_label': 'रिपोर्टिंग अवधि',
      'home_landing_global_map_mode_bubble': 'बुलबुले',
      'home_landing_global_map_mode_choropleth': 'कोरोप्लेथ',
      'home_landing_global_map_zoom_in': 'ज़ूम इन',
      'home_landing_global_map_zoom_out': 'ज़ूम आउट',
      'home_landing_global_map_reset_bounds': 'डेटा फिट करें',
      'home_landing_global_map_legend_low': 'निम्न',
      'home_landing_global_map_legend_high': 'उच्च',
      'home_landing_global_map_country_no_data':
          'इस संकेतक के लिए कोई डेटा नहीं',
      'home_landing_global_map_value_label': 'मान',
      'home_landing_global_map_country_trend': 'रिपोर्टिंग अवधि के अनुसार',
      'home_landing_global_map_filters_title': 'मानचित्र विकल्प',
      'loading_page': 'पृष्ठ लोड हो रहा है...',
      'loading_preferences': 'प्राथमिकताएं लोड हो रही हैं...',
      'loading_notifications': 'सूचनाएं लोड हो रही हैं...',
      'loading_dashboard': 'डैशबोर्ड लोड हो रहा है...',
      'loading_audit_logs': 'ऑडिट लॉग लोड हो रहे हैं...',
      'loading_analytics': 'विश्लेषण लोड हो रहा है...',
      'loading_organizations': 'संगठन लोड हो रहे हैं...',
      'loading_templates': 'टेम्प्लेट लोड हो रहे हैं...',
      'loading_assignments': 'असाइनमेंट लोड हो रहे हैं...',
      'loading_translations': 'अनुवाद लोड हो रहे हैं...',
      'loading_plugins': 'प्लगइन्स लोड हो रहे हैं...',
      'loading_resources': 'संसाधन लोड हो रहे हैं...',
      'loading_indicators': 'संकेतक लोड हो रहे हैं...',
      'loading_documents': 'दस्तावेज़ लोड हो रहे हैं...',
      'loading_api_endpoints': 'API एंडपॉइंट्स लोड हो रहे हैं...',
      'loading_users': 'उपयोगकर्ता लोड हो रहे हैं...',
      'error': 'त्रुटि',
      'retry': 'पुनः प्रयास करें',
      'refresh': 'ताज़ा करें',
      'close': 'बंद करें',
      'save': 'सहेजें',
      'saved': 'सहेजा गया',
      'success': 'सफल',
      'oops_something_went_wrong': 'उफ़! कुछ गलत हो गया',
      'go_back': 'वापस जाएं',
      'edit': 'संपादित करें',
      'duplicate': 'डुप्लिकेट',
      'preview': 'पूर्वावलोकन',
      'download_started': 'डाउनलोड शुरू हो गया',
      'could_not_start_download': 'डाउनलोड शुरू नहीं कर सका',
      'could_not_open_download_link': 'डाउनलोड लिंक खोल नहीं सका',
      'error_opening_download': 'डाउनलोड खोलने में त्रुटि',
      'please_select_at_least_one_user': 'कृपया कम से कम एक उपयोगकर्ता चुनें',
      'indicator_updated_successfully': 'संकेतक सफलतापूर्वक अपडेट किया गया',
      'failed_to_load_indicator': 'संकेतक लोड करने में विफल',
      'user_deleted': 'उपयोगकर्ता हटाया गया',
      'public_url_copied': 'सार्वजनिक URL क्लिपबोर्ड पर कॉपी किया गया!',
      'please_use_web_interface': 'कृपया इकाई परिवर्तन सहेजने के लिए वेब इंटरफ़ेस का उपयोग करें',
      'open_in_web_browser': 'वेब ब्राउज़र में खोलें',
      'countries': 'देश',
      'all_roles': 'सभी भूमिकाएं',
      'admin_role': 'व्यवस्थापक',
      'focal_point_role': 'फोकल पॉइंट',
      'system_manager_role': 'सिस्टम प्रबंधक',
      'viewer_role': 'दर्शक',
      'all_status': 'सभी स्थिति',
      'active_status': 'सक्रिय',
      'inactive_status': 'निष्क्रिय',
      'normal_priority': 'सामान्य',
      'high_priority': 'उच्च',
      'none': 'कोई नहीं',
      'app_screen': 'ऐप स्क्रीन',
      'custom_url': 'कस्टम URL',
      'create_template': 'टेम्पलेट बनाएं',
      'delete_template': 'टेम्पलेट हटाएं',
      'create_assignment': 'असाइनमेंट बनाएं',
      'delete_assignment': 'असाइनमेंट हटाएं',
      'edit_document': 'दस्तावेज़ संपादित करें',
      'preview_document': 'दस्तावेज़ का पूर्वावलोकन',
      'download_document': 'दस्तावेज़ डाउनलोड करें',
      'upload_document': 'दस्तावेज़ अपलोड करें',
      'new_translation': 'नई अनुवाद',
      'new_resource': 'नया संसाधन',
      'install_plugin': 'प्लगइन इंस्टॉल करें',
      'template_deleted_successfully': 'टेम्पलेट सफलतापूर्वक हटाया गया',
      'failed_to_delete_template': 'टेम्पलेट हटाने में विफल',
      'error_loading_page': 'पृष्ठ लोड करने में त्रुटि',
      'no_notifications': 'कोई सूचना नहीं',
      'all_caught_up': 'आप सभी को पकड़ लिया है',
      'notifications_load_more': 'और लोड करें',
      'notifications_filter': 'फ़िल्टर',
      'notifications_filter_title': 'सूचनाएँ फ़िल्टर करें',
      'notifications_filter_read_status': 'पढ़ने की स्थिति',
      'notifications_filter_all': 'सभी',
      'notifications_filter_unread_only': 'केवल अपठित',
      'notifications_filter_type': 'प्रकार',
      'notifications_filter_type_any': 'सभी प्रकार',
      'notifications_filter_from': 'से',
      'notifications_filter_from_any': 'कोई भी',
      'notifications_filter_from_empty_hint':
          'जब उनकी सूचनाएँ लोड की सूची में हों तो लोग यहाँ दिखते हैं। और लोड करें का उपयोग करें।',
      'notifications_filter_priority': 'प्राथमिकता',
      'notifications_filter_priority_any': 'कोई भी प्राथमिकता',
      'notifications_filter_priority_normal': 'सामान्य',
      'notifications_filter_priority_high': 'उच्च',
      'notifications_filter_priority_urgent': 'तत्काल',
      'notifications_filter_apply': 'लागू करें',
      'notifications_filter_reset': 'सभी रीसेट करें',
      'notifications_filter_no_matches_loaded':
          'लोड की सूची में इन फ़िल्टर से मेल खाती कोई सूचना नहीं। और लोड करें या फ़िल्टर बदलें।',
      'mark_all_read': 'सभी को पढ़ा हुआ चिह्नित करें',
      'mark_read': 'पढ़ा हुआ चिह्नित करें',
      'mark_unread': 'अपठित चिह्नित करें',
      'delete': 'हटाएं',
      'archive': 'संग्रहीत करें',
      'unarchive': 'असंग्रहीत करें',
      'send_push_notification': 'पुश अधिसूचना भेजें',
      'admin_push_user_ids_label': 'प्राप्तकर्ता उपयोगकर्ता ID',
      'admin_push_user_ids_hint':
          'अल्पविराम से अलग संख्यात्मक ID (उपयोगकर्ता प्रबंधन से)।',
      'admin_push_user_ids_invalid':
          'एक या अधिक संख्यात्मक उपयोगकर्ता ID अल्पविराम से अलग करके दर्ज करें।',
      'select_users': 'उपयोगकर्ता चुनें',
      'search_users': 'नाम या ईमेल से उपयोगकर्ता खोजें',
      'redirect_url': 'पुनर्निर्देशित करें (वैकल्पिक)',
      'login': 'लॉगिन',
      'log_in': 'लॉग इन करें',
      'phone_username_email': 'फ़ोन नंबर, उपयोगकर्ता नाम या ईमेल',
      'forgot_password_coming_soon': 'भूला हुआ पासवर्ड सुविधा जल्द ही आ रही है',
      'please_enter_email': 'कृपया अपना ईमेल दर्ज करें',
      'please_enter_valid_email': 'कृपया एक वैध ईमेल दर्ज करें',
      'please_enter_password': 'कृपया अपना पासवर्ड दर्ज करें',
      'show': 'दिखाएं',
      'hide': 'छुपाएं',
      'or': 'या',
      'dont_have_account': 'खाता नहीं है?',
      'sign_up': 'साइन अप करें',
      'registration_coming_soon': 'पंजीकरण सुविधा जल्द ही आ रही है',
      'quick_login_testing': 'परीक्षण के लिए त्वरित लॉगिन',
      'test_as_admin': 'व्यवस्थापक के रूप में परीक्षण',
      'test_as_focal_point': 'फोकल पॉइंट के रूप में परीक्षण',
      'public_login_disabled': 'सार्वजनिक लॉगिन अस्थायी रूप से अक्षम है',
      'tester_accounts_info':
          'टेस्टर खाते अभी भी ऊपर दिए गए बटन का उपयोग करके लॉग इन कर सकते हैं।',
      'could_not_open_azure_login': 'Azure लॉगिन नहीं खोल सका',
      'login_with_ifrc_account': 'IFRC खाते के साथ लॉगिन करें',
      'use_ifrc_federation_account':
          'साइन इन करने के लिए अपने IFRC फेडरेशन खाते का उपयोग करें',
      'your_account_or_create_account': 'आपका खाता या खाता बनाएं',
      'login_failed': 'लॉगिन विफल',
      'email_address': 'ईमेल पता',
      'password': 'पासवर्ड',
      'remember_me': 'मुझे याद रखें',
      'forgot_password': 'पासवर्ड भूल गए?',
      'language_changed_to': 'भाषा बदली गई',

      // Splash Screen
      'welcome_to_ifrc_network_databank':
          'IFRC नेटवर्क डेटाबैंक में आपका स्वागत है',
      'splash_description':
          'यह IFRC को डेटा रिपोर्ट करने के लिए एकमात्र प्रणाली है। बिखरे हुए Excel फ़ाइलों, KoBo फ़ॉर्म, कई प्लेटफ़ॉर्म और लॉगिन को अलविदा कहें — सब कुछ अब यहाँ केंद्रीकृत और सुव्यवस्थित है।',
      'powered_by_hum_databank': 'मानवीय डेटाबैंक द्वारा संचालित',
      'open_on_github': 'GitHub पर खोलें',

      // Dashboard
      'national_society': 'राष्ट्रीय समाज',
      'active': 'सक्रिय',
      'completed': 'पूर्ण',
      'current_assignments': 'वर्तमान असाइनमेंट',
      'dashboard_you_have_no_open_assignments':
          'आपके पास कोई खुला असाइनमेंट नहीं है',
      'dashboard_you_have_one_open_assignment':
          'आपके पास 1 खुला असाइनमेंट है',
      'dashboard_you_have_open_assignments_count':
          'आपके पास %s खुले असाइनमेंट हैं',
      'past_assignments': 'पिछले असाइनमेंट',
      'assignments_for': 'के लिए असाइनमेंट',
      'past_submissions_for': 'के लिए पिछले सबमिशन',
      'something_went_wrong': 'कुछ गलत हो गया',
      'no_assignments_yet': 'सब साफ़! इस समय कोई सक्रिय असाइनमेंट नहीं है।',
      'new_assignments_will_appear':
          'नए असाइनमेंट यहां तब दिखाई देंगे जब वे उपलब्ध होंगे।',
      'get_started_by_creating': 'एक नया असाइनमेंट बनाकर शुरू करें',
      'filters': 'फ़िल्टर',
      'period': 'अवधि',
      'template': 'टेम्प्लेट',
      'status': 'स्थिति',
      'clear': 'साफ़ करें',
      'approved': 'अनुमोदित',
      'requires_revision': 'संशोधन की आवश्यकता',
      'pending': 'लंबित',
      'in_progress': 'प्रगति में',
      'submitted': 'प्रस्तुत',
      'other': 'अन्य',
      'entities': 'इकाइयाँ',
      'search_placeholder': 'खोजें...',
      'no_results_found': 'कोई परिणाम नहीं मिला',
      'entity_type_country': 'देश',
      'entity_type_ns_branch': 'एनएस शाखा',
      'entity_type_ns_sub_branch': 'एनएस उप-शाखा',
      'entity_type_ns_local_unit': 'एनएस स्थानीय इकाई',
      'entity_type_division': 'प्रभाग',
      'entity_type_department': 'विभाग',
      'delete_assignment_confirm_message':
          'क्या आप वाकई इस असाइनमेंट और इससे जुड़ी सभी देश स्थितियों और डेटा को हटाना चाहते हैं?',
      'no_assignments_match_filters':
          'कोई असाइनमेंट चयनित फ़िल्टर से मेल नहीं खाता',
      'form': 'फ़ॉर्म',
      'last_updated': 'अंतिम अद्यतन',
      'actions': 'कार्रवाई',
      'all_years': 'सभी वर्ष',
      'all_templates': 'सभी टेम्प्लेट',
      'all_statuses': 'सभी स्थिति',
      'template_missing': 'टेम्प्लेट गुम',
      'self_reported': 'स्व-रिपोर्टेड',
      'no_actions_available': 'कोई कार्रवाई उपलब्ध नहीं',
      'previous': 'पिछला',
      'next': 'अगला',
      'showing': 'दिखा रहा है',
      'to': 'से',
      'of': 'का',
      'results': 'परिणाम',
      'no_past_assignments_for': 'के लिए कोई पिछला असाइनमेंट नहीं',
      'yet': 'अभी तक',
      'submission_history_and_data_quality_for':
          'के लिए सबमिशन इतिहास और डेटा गुणवत्ता',
      'overall_performance': 'समग्र प्रदर्शन',
      'average_completion_rate_past_3_periods': 'औसत पूर्णता दर (पिछले 3 अवधि)',
      'average_submission_timeliness':
          'औसत सबमिशन समयबद्धता (दिन जल्दी/देर से)',
      'data_quality_index_fake_metric': 'डेटा गुणवत्ता सूचकांक (नकली मीट्रिक)',
      'number_of_revisions_requested_past_year':
          'संशोधन की संख्या अनुरोधित (पिछला वर्ष)',
      'trend_analysis': 'रुझान विश्लेषण',
      'recent_activities': 'हाल की गतिविधियां',
      'last_7_days': 'पिछले 7 दिन',
      'unknown_user': 'अज्ञात उपयोगकर्ता',
      'added': 'जोड़ा गया',
      'updated': 'अद्यतन किया गया',
      'removed': 'हटाया गया',
      'show_less': 'कम दिखाएं',
      'more_change': 'अधिक परिवर्तन',
      'no_recent_activities': 'कोई हाल की गतिविधि नहीं',
      'activities_from_other_focal_points_in':
          'अन्य फोकल पॉइंट्स की गतिविधियां',
      'will_appear_here': 'यहां दिखाई देंगी',
      'focal_points_for': 'के लिए फोकल पॉइंट्स',
      'national_society_focal_points': 'राष्ट्रीय समाज फोकल पॉइंट्स',
      'ifrc_focal_points': 'IFRC फोकल पॉइंट्स',
      'no_focal_points_assigned_to': 'कोई फोकल पॉइंट असाइन नहीं',
      'your_user_account_not_associated':
          'आपका उपयोगकर्ता खाता किसी देश से संबद्ध नहीं है',
      'please_contact_administrator': 'कृपया प्रशासक से संपर्क करें',
      'due_date': 'नियत तारीख',
      'no_due_date': 'कोई नियत तारीख नहीं',
      'overdue': 'अतिदेय',
      'latest_submission': 'नवीनतम सबमिशन',
      'submitted_through_public_link': 'सार्वजनिक लिंक के माध्यम से प्रस्तुत',
      'submission': 'सबमिशन',
      'submissions': 'सबमिशन',
      'completion': 'पूर्णता',
      'received_1_submission_using_public_link':
          'सार्वजनिक लिंक का उपयोग करके 1 सबमिशन प्राप्त किया',
      'received_count_submissions_using_public_link':
          'सार्वजनिक लिंक का उपयोग करके %(count)d सबमिशन प्राप्त किए',
      'at_datetime': 'पर: %(datetime)s',
      'latest_datetime': 'नवीनतम: %(datetime)s',
      'last_modified_by': 'अंतिम संशोधित द्वारा',
      'assignment_assigned_date': 'सौंपा गया',
      'assignment_status_updated': 'स्थिति अपडेट',
      'contributors': 'योगदानकर्ता',
      'assignment_submitted_by': 'जमा किया गया',
      'assignment_approved_by': 'अनुमोदित किया गया',
      'public_link_enabled': 'सार्वजनिक लिंक सक्रिय',
      'public_link': 'सार्वजनिक लिंक',
      'unknown': 'अज्ञात',
      'n_a': 'अनुपलब्ध',
      'enter_data': 'डेटा दर्ज करें',
      'download_for_offline': 'ऑफ़लाइन के लिए डाउनलोड करें',
      'downloading_offline_form': 'ऑफ़लाइन उपयोग के लिए फ़ॉर्म डाउनलोड हो रहा है…',
      'offline_form_saved': 'फ़ॉर्म ऑफ़लाइन पहुँच के लिए सहेजा गया।',
      'offline_form_save_failed': 'फ़ॉर्म ऑफ़लाइन सहेजा नहीं जा सका। स्थिर कनेक्शन पर पुनः प्रयास करें।',
      'offline_form_not_downloaded': 'यह फ़ॉर्म ऑफ़लाइन उपलब्ध नहीं है। ऑनलाइन रहते हुए इसे डाउनलोड करें।',
      'offline_download_requires_connection': 'ऑफ़लाइन उपयोग के लिए इस फ़ॉर्म को डाउनलोड करने हेतु इंटरनेट से जुड़ें।',
      'offline_form_export_requires_connection':
          'PDF, Excel या सत्यापन रिपोर्ट निर्यात करने के लिए इंटरनेट से जुड़ें। ऑफ़लाइन प्रति में निर्यात शामिल नहीं हैं।',
      'offline_open_saved_copy': 'सहेजी गई ऑफ़लाइन प्रति खोलें',
      'remove_offline_copy': 'ऑफ़लाइन प्रति हटाएँ',
      'offline_form_removed':
          'ऑफ़लाइन प्रति हटा दी गई। ऑनलाइन होने पर फिर से डाउनलोड करें।',
      'offline_saved_copy_details_tooltip':
          'ऑफ़लाइन प्रति — विवरण और हटाएँ',
      'offline_copy_sheet_title': 'ऑफ़लाइन फ़ॉर्म प्रति',
      'offline_copy_saved_on_label': 'सहेजा गया',
      'offline_copy_files_cached': '%(count)d कैश संसाधन',
      'offline_stale_bundle_banner_title': 'ऑफ़लाइन फ़ॉर्म अपडेट करें',
      'offline_stale_bundle_banner_body_online':
          'ऑनलाइन फ़ॉर्म बदल गया। कनेक्ट होने पर डिवाइस ऑफ़लाइन प्रतियाँ स्वतः अपडेट करता है। यदि न हो, चेतावनी वाले प्रत्येक फ़ॉर्म पर जाकर ऑफ़लाइन प्रति अपडेट करें पर टैप करें।',
      'offline_stale_bundle_banner_body_offline':
          'ऑनलाइन फ़ॉर्म बदल गया। इंटरनेट से जुड़ें ताकि डिवाइस ऑफ़लाइन प्रतियाँ स्वतः अपडेट कर सके।',
      'offline_stale_bundle_updates_snackbar':
          'ऑफ़लाइन प्रतियाँ नवीनतम संस्करण पर अपडेट हो गईं।',
      'offline_stale_bundle_partial_refresh':
          'कुछ ऑफ़लाइन प्रतियाँ अपडेट नहीं हो सकीं। फ़ॉर्म पर चेतावनी बैज पर टैप करें, फिर ऑफ़लाइन प्रति अपडेट करें।',
      'offline_stale_bundle_sheet_notice':
          'यह ऑफ़लाइन प्रति वर्तमान ऑनलाइन फ़ॉर्म से मेल नहीं खा सकती। संस्करण समस्याओं से बचने के लिए अपडेट करें।',
      'offline_stale_bundle_update_now': 'ऑफ़लाइन प्रति अपडेट करें',
      'approve': 'अनुमोदित करें',
      'reopen': 'पुनः खोलें',
      'view_public_submissions': 'सार्वजनिक सबमिशन देखें',
      'view_submission': 'सबमिशन देखें',
      'view_submissions': 'सबमिशन देखें',
      'open_form': 'फ़ॉर्म खोलें',
      'no_forms_assigned_or_submitted_for':
          'के लिए कोई फ़ॉर्म असाइन या सार्वजनिक लिंक के माध्यम से प्रस्तुत नहीं किया गया',
      'admins_can_assign_forms':
          'प्रशासक प्रशासन डैशबोर्ड के माध्यम से फ़ॉर्म असाइन कर सकते हैं या सार्वजनिक लिंक बना सकते हैं',
      'create_a_report': 'एक रिपोर्ट बनाएं',
      'delete_self_reported_assignment': 'स्व-रिपोर्टेड असाइनमेंट हटाएं',
      'quick_actions': 'त्वरित कार्रवाई',
      'new_assignment': 'नया असाइनमेंट',
      'new_template': 'नया टेम्प्लेट',
      'key_metrics': 'मुख्य मैट्रिक्स',
      'overview': 'अवलोकन',
      'create_new_assignment': 'एक नया असाइनमेंट बनाएं',
      'browse_available_templates': 'उपलब्ध टेम्प्लेट ब्राउज़ करें',
      'enter_your_name': 'अपना नाम दर्ज करें',
      'enter_your_job_title': 'अपना जॉब टाइटल दर्ज करें',
      'edit_name': 'नाम संपादित करें',
      'edit_title': 'शीर्षक संपादित करें',
      'name_cannot_be_empty': 'नाम खाली नहीं हो सकता',
      'title_cannot_be_empty': 'शीर्षक खाली नहीं हो सकता',
      'profile_updated_successfully': 'प्रोफ़ाइल सफलतापूर्वक अपडेट की गई',
      'error_updating_profile': 'प्रोफ़ाइल अपडेट करने में त्रुटि',
      'color_picker_coming_soon': 'रंग चयनकर्ता जल्द ही आ रहा है',
      'chatbot_preference_update_coming_soon':
          'चैटबॉट प्राथमिकता अपडेट जल्द ही आ रहा है',
      'select_color': 'एक रंग चुनें',
      'current_color': 'वर्तमान रंग',
      'profile_color_updated': 'प्रोफ़ाइल रंग सफलतापूर्वक अपडेट किया गया',
      'profile_color_update_failed': 'प्रोफ़ाइल रंग अपडेट करने में विफल',
      'admin_dashboard': 'एडमिन डैशबोर्ड',
      'no_data_available': 'कोई डेटा उपलब्ध नहीं',
      'total_users': 'कुल उपयोगकर्ता',
      'admins': 'एडमिन',
      'system_administrators': 'सिस्टम प्रशासक',
      'focal_points': 'फोकल पॉइंट्स',
      'country_focal_points': 'देश के फोकल पॉइंट्स',
      'form_templates': 'फॉर्म टेम्प्लेट',
      'active_assignments': 'सक्रिय असाइनमेंट',
      'todays_logins': 'आज के लॉगिन',
      'successful_logins_today': 'आज सफल लॉगिन',
      'pending_submissions': 'लंबित सबमिशन',
      'overdue_assignments': 'अतिदेय असाइनमेंट',
      'security_alerts': 'सुरक्षा अलर्ट',
      'successful_logins': 'सफल लॉगिन',
      'user_activities': 'उपयोगकर्ता गतिविधियां',
      'active_sessions': 'सक्रिय सत्र',
      'all_notifications_marked_as_read':
          'सभी सूचनाएं पढ़ी गई के रूप में चिह्नित',
      'mark_as_read': 'पढ़ा हुआ चिह्नित करें',
      'mark_as_unread': 'अपठित चिह्नित करें',
      'notification_preferences': 'सूचना प्राथमिकताएं',
      'sound_notifications': 'ध्वनि सूचनाएं',
      'email_frequency': 'ईमेल आवृत्ति',
      'instant': 'तत्काल',
      'daily_digest': 'दैनिक सारांश',
      'weekly_digest': 'साप्ताहिक सारांश',
      'digest_schedule': 'सारांश अनुसूची',
      'day_of_week': 'सप्ताह का दिन',
      'monday': 'सोमवार',
      'tuesday': 'मंगलवार',
      'wednesday': 'बुधवार',
      'thursday': 'गुरुवार',
      'friday': 'शुक्रवार',
      'saturday': 'शनिवार',
      'sunday': 'रविवार',
      'time_local_time': 'समय (स्थानीय समय)',
      'notification_types': 'सूचना प्रकार',
      'preferences_saved_successfully': 'प्राथमिकताएं सफलतापूर्वक सहेजी गईं',
      'enable_sound': 'ध्वनि सक्षम करें',
      'play_sound_for_new_notifications': 'नई सूचनाओं के लिए ध्वनि चलाएं',
      'configure_notification_types_description': 'कॉन्फ़िगर करें कि ईमेल और पुश सूचनाओं के माध्यम से कौन से सूचना प्रकार प्राप्त करें',
      'notification_type': 'सूचना प्रकार',
      'push': 'पुश',
      'all': 'सभी',
      'save_preferences': 'प्राथमिकताएं सहेजें',
      'select_digest_time_description': 'उस समय का चयन करें जब आप अपना सारांश प्राप्त करना चाहते हैं',
      'failed_to_save_preferences': 'प्राथमिकताएं सहेजने में विफल',
      'assignment_created': 'कार्य बनाया गया',
      'assignment_submitted': 'कार्य जमा किया गया',
      'assignment_approved': 'कार्य स्वीकृत',
      'assignment_reopened': 'कार्य पुनः खोला गया',
      'public_submission_received': 'सार्वजनिक सबमिशन प्राप्त',
      'form_updated': 'फॉर्म अपडेट किया गया',
      'document_uploaded': 'दस्तावेज़ अपलोड किया गया',
      'user_added_to_country': 'उपयोगकर्ता देश में जोड़ा गया',
      'template_updated': 'टेम्प्लेट अपडेट किया गया',
      'self_report_created': 'स्व-रिपोर्ट बनाई गई',
      'deadline_reminder': 'अंतिम तिथि अनुस्मारक',
      'search_audit_logs': 'ऑडिट लॉग खोजें...',
      'home_screen_widget_title': 'होम स्क्रीन विजेट',
      'audit_widget_activity_types_hint':
          'विजेट के लिए गतिविधि प्रकार चुनें। कोई चयन न होने पर सभी दिखेंगे। इस डिवाइस पर सहेजा जाता है।',
      'action': 'कार्रवाई',
      'all_actions': 'सभी कार्रवाइयां',
      'create': 'बनाएं',
      'update': 'अपडेट करें',
      'user': 'उपयोगकर्ता',
      'all_users': 'सभी उपयोगकर्ता',
      'from_date': 'तारीख से',
      'to_date': 'तारीख तक',
      'select_date': 'तारीख चुनें',
      'no_description': 'कोई विवरण नहीं',
      'search_api_endpoints': 'API एंडपॉइंट खोजें...',
      'http_method': 'HTTP विधि',
      'all_methods': 'सभी विधियां',
      'get': 'GET',
      'post': 'POST',
      'put': 'PUT',
      'delete_method': 'DELETE',
      'deprecated': 'अप्रचलित',
      'beta': 'बीटा',
      'new_api_key': 'नई API कुंजी',
      'time_range': 'समय सीमा',
      'last_30_days': 'पिछले 30 दिन',
      'last_90_days': 'पिछले 90 दिन',
      'last_year': 'पिछला वर्ष',
      'all_time': 'सभी समय',
      'metric': 'मीट्रिक',
      'all_metrics': 'सभी मीट्रिक',
      'active_users': 'सक्रिय उपयोगकर्ता',
      'logins': 'लॉगिन',
      'metric_submissions': 'सबमिशन',
      'page_views': 'पृष्ठ दृश्य',
      'search_indicators': 'संकेतक खोजें...',
      'category': 'श्रेणी',
      'all_categories': 'सभी श्रेणियां',
      'output': 'आउटपुट',
      'outcome': 'परिणाम',
      'impact': 'प्रभाव',
      'all_sectors': 'सभी क्षेत्र',
      'health': 'स्वास्थ्य',
      'wash': 'WASH',
      'shelter': 'आश्रय',
      'education': 'शिक्षा',
      'indicators': 'संकेतक',
      'new_indicator': 'नया संकेतक',
      'search_organizations': 'संगठन खोजें...',
      'entity_type': 'इकाई प्रकार',
      'all_types': 'सभी प्रकार',
      'national_societies': 'राष्ट्रीय समाज',
      'ns_structure': 'NS संरचना',
      'secretariat': 'सचिवालय',
      'divisions': 'विभाग',
      'departments': 'विभाग',
      'regional_offices': 'क्षेत्रीय कार्यालय',
      'cluster_offices': 'क्लस्टर कार्यालय',
      'add_organization': 'संगठन जोड़ें',
      'search_resources': 'संसाधन खोजें...',
      'no_indicators_found': 'कोई संकेतक नहीं मिला',
      'no_organizations_found': 'कोई संगठन नहीं मिला',
      'no_resources_found': 'कोई संसाधन नहीं मिला',
      'resources_unified_planning_section_title': 'एकीकृत योजनाएँ और रिपोर्ट',
      'resources_unified_planning_section_subtitle':
          'IFRC GO से योजनाएँ, मध्यवर्ष रिपोर्ट और वार्षिक रिपोर्ट (ऐप में लोड)।',
      'unified_planning_empty':
          'आपकी खोज से मेल खाने वाली कोई एकीकृत योजना दस्तावेज़ नहीं।',
      'unified_planning_fresh_badge': 'ताज़ा',
      'unified_planning_sort_by': 'क्रमबद्ध करें',
      'unified_planning_sort_date_newest': 'प्रकाशन तिथि: पहले नवीनतम',
      'unified_planning_sort_date_oldest': 'प्रकाशन तिथि: पहले सबसे पुराना',
      'unified_planning_sort_country_az': 'देश: A–Z',
      'unified_planning_sort_country_za': 'देश: Z–A',
      'unified_planning_filter_all_countries': 'सभी देश',
      'unified_error_config':
          'सर्वर से एकीकृत योजना सेटिंग लोड नहीं हो सकीं। बाद में पुनः प्रयास करें।',
      'unified_error_credentials':
          'इस ऐप में IFRC दस्तावेज़ उपलब्ध नहीं हैं। अपने व्यवस्थापक से संपर्क करें।',
      'unified_error_ifrc_auth':
          'IFRC दस्तावेज़ों तक पहुँच नहीं हो सकी। यदि समस्या बनी रहे तो अपने व्यवस्थापक से संपर्क करें।',
      'unified_error_ifrc':
          'IFRC GO से दस्तावेज़ लोड नहीं हो सके। कनेक्शन जाँचें और पुनः प्रयास करें।',
      'no_plugins_found': 'कोई प्लगइन नहीं मिला',
      'no_translations_found': 'कोई अनुवाद नहीं मिला',
      'no_documents_found': 'कोई दस्तावेज नहीं मिला',
      'no_users_found': 'कोई उपयोगकर्ता नहीं मिला',
      'loading_user_profile': 'उपयोगकर्ता प्रोफ़ाइल लोड हो रही है…',
      'failed_load_user_profile': 'इस उपयोगकर्ता को लोड नहीं किया जा सका.',
      'admin_user_detail_confirm_save_title': 'परिवर्तन सहेजें?',
      'admin_user_detail_confirm_save_message':
          'इस उपयोगकर्ता का नाम, पद, स्थिति और प्राथमिकताएँ अपडेट करें।',
      'admin_user_detail_invalid_profile_color':
          'मान्य रंग #RRGGBB प्रारूप में दर्ज करें (जैसे #3B82F6)।',
      'admin_user_detail_changes_saved': 'परिवर्तन सहेजे गए।',
      'admin_user_detail_save_changes': 'परिवर्तन सहेजें',
      'admin_user_detail_profile_color_label': 'प्रोफ़ाइल रंग',
      'admin_user_detail_profile_color_hint': '#RRGGBB',
      'admin_user_detail_cannot_deactivate_self':
          'आप अपना खाता निष्क्रिय नहीं कर सकते।',
      'admin_user_detail_matrix_read_only_bundled':
          'बंडल किए गए व्यवस्थापक भूमिकाएँ (पूर्ण/कोर/सिस्टम) — क्षेत्रीय पहुँच के लिए वेब का उपयोग करें।',
      'admin_user_detail_rbac_incomplete':
          'मान्य भूमिका सूची नहीं बन सकी। पहुँच जाँचें या पुनः प्रयास करें।',
      'assigned_roles_title': 'निर्धारित भूमिकाएँ',
      'role_type_label': 'भूमिका प्रकार',
      'permissions_by_role': 'भूमिका के अनुसार अनुमतियाँ',
      'all_permissions_union': 'सभी अनुमतियाँ (भूमिकाओं से)',
      'entity_permissions_title': 'इकाई अनुमतियाँ',
      'manage_users_detail_footer':
          'भूमिकाएँ, इकाई पहुँच, उपकरण या सूचनाएँ संपादित करने के लिए वेब बैकऑफिस उपयोगकर्ता फ़ॉर्म का उपयोग करें।',
      'no_roles_assigned': 'कोई RBAC भूमिका निर्धारित नहीं।',
      'no_entities_assigned': 'कोई इकाई असाइनमेंट नहीं।',
      'entity_permission_unnamed': 'अनाम',
      'entity_region_other': 'अन्य क्षेत्र',
      'no_permissions_listed': 'इस भूमिका के लिए कोई अनुमति सूचीबद्ध नहीं।',
      'user_dir_assignment_roles': 'असाइनमेंट भूमिकाएँ',
      'user_dir_admin_roles': 'व्यवस्थापक और सिस्टम',
      'user_dir_other_roles': 'अन्य भूमिकाएँ',
      'admin_role_access_area': 'क्षेत्र',
      'admin_role_access_view': 'देखें',
      'admin_role_access_manage': 'प्रबंधन',
      'admin_role_de_heading': 'डेटा एक्सप्लोरर',
      'admin_role_de_table': 'तालिका',
      'admin_role_de_analysis': 'विश्लेषण',
      'admin_role_de_compliance': 'अनुपालन',
      'admin_role_note_admin_full': 'सभी व्यवस्थापक अनुमतियाँ (बंडल भूमिका)',
      'admin_role_note_admin_core': 'मुख्य व्यवस्थापन (बंडल भूमिका)',
      'admin_role_other_admin_roles': 'अन्य व्यवस्थापक भूमिकाएँ',
      'users_directory_role_all': 'सभी भूमिकाएँ',
      'users_directory_country_all': 'सभी देश',
      'no_assignments_found': 'कोई असाइनमेंट नहीं मिला',
      'no_templates_found': 'कोई टेम्प्लेट नहीं मिला',
      'assignment_deleted_successfully': 'असाइनमेंट सफलतापूर्वक हटाया गया',
      'failed_to_delete_assignment': 'असाइनमेंट हटाने में विफल',
      'timeline_view': 'टाइमलाइन दृश्य',
      'view_all_public_submissions': 'सभी सार्वजनिक सबमिशन देखें',
      'items_requiring_attention': 'ध्यान देने योग्य वस्तुएं',
      'recent_activity': 'हाल की गतिविधि',
      'recent_activity_7_days': 'हाल की गतिविधि (7 दिन)',
      'general_settings': 'सामान्य सेटिंग्स',
      'security_settings': 'सुरक्षा सेटिंग्स',
      'system_settings': 'सिस्टम सेटिंग्स',
      'application_settings': 'एप्लिकेशन सेटिंग्स',
      'language_settings': 'भाषा सेटिंग्स',
      'notification_settings': 'सूचना सेटिंग्स',
      'authentication_settings': 'प्रमाणीकरण सेटिंग्स',
      'permission_settings': 'अनुमति सेटिंग्स',
      'database_settings': 'डेटाबेस सेटिंग्स',
      'cloud_storage_settings': 'क्लाउड स्टोरेज सेटिंग्स',
      'configure_general_application_settings':
          'सामान्य एप्लिकेशन सेटिंग्स कॉन्फ़िगर करें',
      'manage_supported_languages_and_translations':
          'समर्थित भाषाएं और अनुवाद प्रबंधित करें',
      'configure_notification_preferences': 'सूचना प्राथमिकताएं कॉन्फ़िगर करें',
      'configure_authentication_and_authorization':
          'प्रमाणीकरण और अधिकार कॉन्फ़िगर करें',
      'manage_user_permissions_and_roles':
          'उपयोगकर्ता अनुमतियां और भूमिकाएं प्रबंधित करें',
      'configure_database_connections_and_backups':
          'डेटाबेस कनेक्शन और बैकअप कॉन्फ़िगर करें',
      'configure_cloud_storage_and_file_management':
          'क्लाउड स्टोरेज और फ़ाइल प्रबंधन कॉन्फ़िगर करें',

      // Indicator Bank
      'indicator_bank_title': 'संकेतक बैंक',
      'indicator_bank_loading': 'संकेतक बैंक लोड हो रहा है...',
      'indicator_bank_error': 'कुछ गलत हो गया',
      'indicator_bank_search_placeholder': 'संकेतक खोजें...',
      'indicator_bank_filter_placeholder': 'संकेतक फ़िल्टर करें...',
      'indicator_bank_browse_description':
          'मानवीय प्रतिक्रिया के लिए संकेतक ब्राउज़ और खोजें',
      'indicator_bank_grid_view': 'ग्रिड व्यू',
      'indicator_bank_table_view': 'टेबल व्यू',
      'indicator_bank_show_filters': 'फ़िल्टर दिखाएं',
      'indicator_bank_hide_filters': 'फ़िल्टर छुपाएं',
      'indicator_bank_filters': 'फ़िल्टर',
      'indicator_bank_filter_type': 'प्रकार',
      'indicator_bank_filter_type_all': 'सभी प्रकार',
      'indicator_bank_filter_sector': 'क्षेत्र',
      'indicator_bank_filter_sector_all': 'सभी क्षेत्र',
      'indicator_bank_filter_subsector': 'उपक्षेत्र',
      'indicator_bank_filter_subsector_all': 'सभी उपक्षेत्र',
      'indicator_bank_list_tier_also_related': 'संबंधित भी',
      'indicator_bank_filter_status': 'स्थिति',
      'indicator_bank_filter_status_active': 'केवल सक्रिय',
      'indicator_bank_filter_status_all': 'सभी',
      'indicator_bank_apply_filters': 'फ़िल्टर लागू करें',
      'indicator_bank_clear_all': 'सभी साफ़ करें',
      'indicator_bank_showing': 'दिखा रहा है',
      'indicator_bank_indicators': 'संकेतक',
      'indicator_bank_indicator': 'संकेतक',
      'indicator_bank_no_sectors': 'कोई क्षेत्र नहीं मिला',
      'indicator_bank_no_indicators': 'कोई संकेतक नहीं मिला',
      'indicator_bank_table_name': 'नाम',
      'indicator_bank_table_type': 'प्रकार',
      'indicator_bank_table_sector': 'क्षेत्र',
      'indicator_bank_table_subsector': 'उपक्षेत्र',
      'indicator_bank_table_unit': 'इकाई',
      'indicator_bank_propose_new': 'नया संकेतक प्रस्तावित करें',
      'indicator_bank_propose_title': 'नया संकेतक प्रस्तावित करें',
      'indicator_bank_propose_contact_info': 'संपर्क जानकारी',
      'indicator_bank_propose_your_name': 'आपका नाम *',
      'indicator_bank_propose_email': 'ईमेल पता *',
      'indicator_bank_propose_indicator_info': 'संकेतक जानकारी',
      'indicator_bank_propose_indicator_name': 'संकेतक नाम *',
      'indicator_bank_propose_definition': 'परिभाषा *',
      'indicator_bank_propose_type': 'प्रकार',
      'indicator_bank_propose_unit': 'माप की इकाई',
      'indicator_bank_propose_sector': 'क्षेत्र',
      'indicator_bank_propose_primary_sector': 'प्राथमिक क्षेत्र *',
      'indicator_bank_propose_secondary_sector': 'द्वितीयक क्षेत्र',
      'indicator_bank_propose_tertiary_sector': 'तृतीयक क्षेत्र',
      'indicator_bank_propose_subsector': 'उपक्षेत्र',
      'indicator_bank_propose_primary_subsector': 'प्राथमिक उपक्षेत्र *',
      'indicator_bank_propose_secondary_subsector': 'द्वितीयक उपक्षेत्र',
      'indicator_bank_propose_tertiary_subsector': 'तृतीयक उपक्षेत्र',
      'indicator_bank_propose_emergency': 'आपातकालीन संदर्भ',
      'indicator_bank_propose_related_programs': 'संबंधित कार्यक्रम',
      'indicator_bank_propose_reason': 'प्रस्ताव का कारण *',
      'indicator_bank_propose_additional_notes': 'अतिरिक्त नोट्स',
      'indicator_bank_propose_submit': 'प्रस्ताव सबमिट करें',
      'indicator_bank_propose_thank_you': 'धन्यवाद!',
      'indicator_bank_propose_success':
          'आपका संकेतक प्रस्ताव सफलतापूर्वक सबमिट किया गया है।',
      'indicator_bank_propose_failed':
          'प्रस्ताव सबमिट करने में विफल। कृपया पुनः प्रयास करें।',
      'indicator_bank_name_required': 'नाम आवश्यक है',
      'indicator_bank_email_required': 'ईमेल आवश्यक है',
      'indicator_bank_indicator_name_required': 'संकेतक नाम आवश्यक है',
      'indicator_bank_definition_required': 'परिभाषा आवश्यक है',
      'indicator_bank_primary_sector_required': 'प्राथमिक क्षेत्र आवश्यक है',
      'indicator_bank_primary_subsector_required':
          'प्राथमिक उपक्षेत्र आवश्यक है',
      'indicator_bank_reason_required': 'कारण आवश्यक है',

      // Indicator Detail
      'indicator_detail_title': 'संकेतक विवरण',
      'indicator_detail_loading': 'संकेतक विवरण लोड हो रहा है...',
      'indicator_detail_error': 'कुछ गलत हो गया',
      'indicator_detail_not_found': 'संकेतक नहीं मिला',
      'indicator_detail_go_back': 'वापस जाएं',
      'indicator_detail_definition': 'परिभाषा',
      'indicator_detail_details': 'विवरण',
      'indicator_detail_type': 'प्रकार',
      'indicator_detail_unit': 'इकाई',
      'indicator_detail_sector': 'क्षेत्र',
      'indicator_detail_subsector': 'उपक्षेत्र',
      'indicator_detail_emergency_context': 'आपातकालीन संदर्भ',
      'indicator_detail_related_programs': 'संबंधित कार्यक्रम',
      'indicator_detail_status': 'स्थिति',
      'indicator_detail_archived': 'संग्रहीत',
      'indicator_detail_yes': 'हाँ',
      'editIndicator': 'संकेतक संपादित करें',

      // Quiz Game
      'quiz_game': 'क्विज़ गेम',
      'quiz_game_title': 'क्विज़ गेम',
      'quiz_game_test_your_knowledge': 'अपने ज्ञान का परीक्षण करें!',
      'quiz_game_loading': 'क्विज़ लोड हो रहा है...',
      'quiz_game_error': 'क्विज़ लोड करने में त्रुटि',
      'quiz_game_try_again': 'पुनः प्रयास करें',
      'quiz_game_start_quiz': 'क्विज़ शुरू करें',
      'quiz_game_which_sector': 'यह संकेतक किस क्षेत्र से संबंधित है?',
      'quiz_game_which_subsector': 'यह संकेतक किस उपक्षेत्र से संबंधित है?',
      'quiz_game_definition': 'परिभाषा',
      'quiz_game_no_definition': 'कोई परिभाषा उपलब्ध नहीं',
      'quiz_game_correct': 'सही!',
      'quiz_game_incorrect': 'गलत',
      'quiz_game_next_question': 'अगला प्रश्न',
      'quiz_game_view_results': 'परिणाम देखें',
      'quiz_game_quiz_complete': 'क्विज़ पूर्ण!',
      'quiz_game_excellent_work': 'उत्कृष्ट कार्य!',
      'quiz_game_well_done': 'बहुत बढ़िया!',
      'quiz_game_good_effort': 'अच्छा प्रयास!',
      'quiz_game_keep_practicing': 'अभ्यास जारी रखें!',
      'quiz_game_out_of': 'में से',
      'quiz_game_statistics': 'आंकड़े',
      'quiz_game_correct_answers': 'सही',
      'quiz_game_incorrect_answers': 'गलत',
      'quiz_game_total': 'कुल',
      'quiz_game_home': 'होम',
      'quiz_game_play_again': 'फिर से खेलें',
      'quiz_game_no_indicators_available': 'क्विज़ के लिए क्षेत्रों या उपक्षेत्रों के साथ कोई संकेतक उपलब्ध नहीं',
      'quiz_game_failed_to_start': 'क्विज़ शुरू करने में विफल',
      'quiz_game_leaderboard': 'लीडरबोर्ड',
      'quiz_game_view_leaderboard': 'लीडरबोर्ड देखें',
      'quiz_game_loading_leaderboard': 'लीडरबोर्ड लोड हो रहा है...',
      'quiz_game_no_leaderboard_data': 'अभी तक कोई लीडरबोर्ड डेटा उपलब्ध नहीं',
      'quiz_game_top_players': 'शीर्ष खिलाड़ी',
      'quiz_game_you': 'आप',
      'quiz_game_points': 'अंक',

      // AI Chat (immersive)
      'ai_policy_acknowledge_snackbar':
          'जारी रखने के लिए कृपया AI नीति स्वीकार करें।',
      'ai_use_policy_title': 'AI उपयोग नीति',
      'ai_policy_do_not_share': 'संवेदनशील जानकारी साझा न करें।',
      'ai_policy_traces_body':
          'हम सहायक को बेहतर बनाने के लिए सिस्टम ट्रेस और टेलीमेट्री का उपयोग करते हैं। आपके संदेश बाहरी AI प्रदाताओं द्वारा संसाधित हो सकते हैं।',
      'ai_policy_purpose_title': 'उद्देश्य',
      'ai_policy_purpose_body':
          'AI सहायक आपको इस प्लेटफ़ॉर्म पर डेटा और दस्तावेज़ खोजने में मदद करता है। यह संकेतकों, देशों, असाइनमेंट के बारे में उत्तर दे सकता है और अपलोड किए गए दस्तावेज़ों में खोज सकता है।',
      'ai_policy_acceptable_use_title': 'स्वीकार्य उपयोग',
      'ai_policy_acceptable_use_body':
          '• प्लेटफ़ॉर्म डेटा, संकेतक और दस्तावेज़ों के बारे में पूछें।\n'
          '• पासवर्ड, क्रेडेंशियल या अत्यधिक गोपनीय परिचालन विवरण साझा न करें।\n'
          '• व्यक्तिगत या वित्तीय डेटा चिपकाएं नहीं।',
      'ai_policy_accuracy_title': 'सटीकता',
      'ai_policy_accuracy_body':
          'AI गलतियाँ कर सकता है या डेटा गलत समझ सकता है। महत्वपूर्ण जानकारी हमेशा स्रोत डेटा या दस्तावेज़ों से सत्यापित करें।',
      'ai_policy_confirm_footer':
          'सहायक का उपयोग करने के लिए ऊपर की जानकारी पढ़ने की पुष्टि करें।',
      'ai_policy_i_understand': 'मैं समझता/समझती हूँ',
      'ai_policy_acknowledge_cta': 'AI उपयोग नीति स्वीकार करें',
      'ai_sources_heading': 'स्रोत उपयोग करें:',
      'ai_source_databank': 'डेटाबैंक',
      'ai_source_system_documents': 'सिस्टम दस्तावेज़',
      'ai_source_upr_documents': 'UPR दस्तावेज़',
      'ai_sources_minimum_note':
          'कम से कम एक स्रोत सक्षम रहता है (वेब सहायक जैसा)।',
      'ai_tour_guide_question': 'क्या आप चाहते हैं कि मैं आपको इसमें मार्गदर्शन करूँ?',
      'ai_tour_navigate_question': 'क्या आप संबंधित पृष्ठ पर जाना चाहते हैं?',
      'ai_tour_web_only_snackbar':
          'इंटरैक्टिव टूर वेब संस्करण पर उपलब्ध हैं। पृष्ठ खोला जा रहा है...',
      'ai_new_chat': 'नई चैट',
      'ai_semantic_open_drawer_hint': 'बातचीत और सेटिंग्स खोलता है',
      'ai_tooltip_new_chat': 'नई चैट',
      'ai_semantic_new_chat_label': 'नई चैट',
      'ai_semantic_new_chat_hint': 'एक नई खाली बातचीत शुरू करता है',
      'ai_beta_tester_banner':
          'AI बीटा परीक्षक — प्रायोगिक सुविधाएँ सक्षम हो सकती हैं।',
      'ai_empty_welcome': 'आज मैं आपकी कैसे मदद कर सकता हूँ?',
      'ai_policy_chip_title': 'AI उपयोग नीति',
      'ai_policy_sheet_summary_line':
          'संक्षिप्त सारांश — पूर्ण विवरण के लिए शीट खोलें।',
      'ai_policy_compact_warning':
          'संवेदनशील जानकारी साझा न करें। हम सहायक को बेहतर बनाने के लिए ट्रेस और टेलीमेट्री का उपयोग करते हैं; संदेश बाहरी AI प्रदाताओं द्वारा संसाधित हो सकते हैं।',
      'ai_read_full_policy': 'पूर्ण नीति पढ़ें',
      'ai_try_asking': 'पूछकर देखें',
      'ai_copied': 'कॉपी हो गया!',
      'ai_tooltip_copy': 'कॉपी',
      'ai_tooltip_edit_message': 'संपादित करें',
      'ai_tooltip_helpful': 'उपयोगी',
      'ai_tooltip_not_helpful': 'उपयोगी नहीं',
      'ai_footer_model_warning':
          'AI गलतियाँ कर सकता है। महत्वपूर्ण जानकारी जाँचें।',
      'ai_chat_error_network':
          'AI सेवा तक पहुंच नहीं हो सकी। अपना इंटरनेट कनेक्शन जांचें और फिर कोशिश करें।',
      'ai_chat_error_timeout':
          'अनुरोध का समय समाप्त हो गया। कनेक्शन जांचें और फिर कोशिश करें।',
      'ai_chat_error_server': 'कुछ गलत हुआ। कृपया फिर कोशिश करें।',
      'ai_agent_progress_title': 'प्रगति में चरण',
      'ai_agent_step_done': 'पूर्ण।',
      'ai_agent_step_preparing_query': 'क्वेरी तैयार की जा रही है…',
      'ai_agent_step_planning': 'दृष्टिकोण की योजना बनाई जा रही है…',
      'ai_agent_step_reviewing': 'परिणामों की समीक्षा…',
      'ai_agent_step_drafting': 'उत्तर का मसौदा…',
      'ai_agent_step_replying': 'उत्तर दिया जा रहा है…',
      'ai_agent_step_thinking_next': 'आगे क्या करना है, सोच रहा हूँ।',
      'ai_agent_step_no_shortcut_full':
          'एकल-टूल शॉर्टकट नहीं — पूर्ण योजना मार्ग का उपयोग।',
      'ai_agent_step_no_shortcut_reviewing':
          'इस अनुरोध के लिए एकल-टूल शॉर्टकट नहीं — समीक्षा: %s',
      'ai_response_sources': 'स्रोत',
      'ai_response_sources_with_count': 'स्रोत (%s)',
      'ai_tooltip_configure_sources': 'डेटा स्रोत कॉन्फ़िगर करें',
      'ai_input_policy_required':
          'संदेश भेजने के लिए ऊपर AI नीति स्वीकार करें',
      'ai_input_placeholder_message': 'संदेश',
      'ai_input_placeholder_edit': 'संदेश संपादित करें…',
      'ai_tooltip_cancel_edit': 'संपादन रद्द करें',
      'ai_stop': 'रोकें',
      'ai_conversations_drawer_title': 'बातचीत',
      'ai_search_conversations_hint': 'बातचीत खोजें',
      'ai_no_conversations_body':
          'अभी तक कोई बातचीत नहीं।\nनई चैट शुरू करें!',
      'ai_no_conversations_offline':
          'अभी तक कोई बातचीत नहीं।\nनई चैट शुरू करें (ऑफ़लाइन)।',
      'ai_no_conversations_filtered': 'कोई बातचीत नहीं मिली',
      'ai_section_pinned': 'पिन की गई',
      'ai_section_recent': 'हाल की',
      'ai_quick_prompt_1': 'बांग्लादेश में कितने स्वयंसेवक?',
      'ai_quick_prompt_2': 'समय के साथ सीरिया में स्वयंसेवक',
      'ai_quick_prompt_3': 'देश के अनुसार स्वयंसेवकों का विश्व हीटमैप',
      'ai_quick_prompt_4': 'केन्या में शाखाओं की संख्या',
      'ai_quick_prompt_5': 'नाइजीरिया में स्टाफ और स्थानीय इकाइयाँ',
      'ai_clear_all_dialog_title': 'सभी बातचीत साफ़ करें',
      'ai_clear_all_dialog_body':
          'क्या आप वाकई सभी बातचीत हटाना चाहते हैं? यह पूर्ववत नहीं हो सकता।',
      'ai_clear_all_button': 'सभी साफ़ करें',
      'ai_clear_all_row': 'सभी बातचीत साफ़ करें',
      'ai_help_about_row': 'सहायता और परिचय',
      'ai_pin': 'पिन',
      'ai_unpin': 'अनपिन',
      'ai_delete_conversation_title': 'बातचीत हटाएँ?',
      'ai_delete_conversation_body':
          'यह बातचीत हटाएँ? इसे पूर्ववत नहीं किया जा सकता।',
      'ai_new_chat_title_fallback': 'नई चैट',
      'ai_help_dialog_title': 'AI सहायक सहायता',
      'ai_help_about_heading': 'परिचय',
      'ai_help_about_paragraph':
          'AI सहायक आपको IFRC नेटवर्क डेटाबैंक के बारे में जानकारी खोजने और प्रश्नों के उत्तर देने में मदद करता है।',
      'ai_help_features_heading': 'सुविधाएँ',
      'ai_help_feature_bullet_1':
          '• असाइनमेंट, संसाधन और अधिक के बारे में पूछें',
      'ai_help_feature_bullet_2': '• ऐप में नेविगेट करने में सहायता पाएँ',
      'ai_help_feature_bullet_3':
          '• अपने बातचीत इतिहास में खोजें',
      'ai_help_feature_bullet_4':
          '• लॉग इन होने पर सभी बातचीत सहेजी जाती हैं',
      'ai_help_tips_heading': 'सुझाव',
      'ai_help_tip_bullet_1':
          '• बेहतर परिणामों के लिए प्रश्न विशिष्ट रखें',
      'ai_help_tip_bullet_2':
          '• प्रासंगिक पृष्ठों पर जाने के लिए उत्तरों में लिंक पर टैप करें',
      'ai_help_tip_bullet_3':
          '• पिछली बातचीत जल्दी खोजने के लिए खोज बार का उपयोग करें',
      'ai_help_tip_bullet_4':
          '• मेनू (पिन या हटाएँ) के लिए बातचीत पर लंबा दबाएँ',
      'ai_got_it': 'समझ गया',
      'ai_score_confidence': 'विश्वास',
      'ai_score_grounding': 'आधार',
      'ai_default_assistant_title': 'AI सहायक',
      'resources_other_subgroup': 'अन्य',
      'resources_list_truncated_hint':
          'सबसे हाल के आइटम दिखाए जा रहे हैं। किसी विशिष्ट दस्तावेज़ के लिए खोज का उपयोग करें।',
      'ai_assistant': 'AI सहायक',
    },
    'ru': {
      'app_name': 'Банк Данных Сети IFRC',
      'navigation': 'Навигация',
      'home': 'Главная',
      'dashboard': 'Панель управления',
      'resources': 'Ресурсы',
      'indicator_bank': 'Банк Показателей',
      'disaggregation_analysis': 'Анализ Дезгрегации',
      'analysis': 'Анализ',
      'data_visualization': 'Визуализация Данных',
      'settings': 'Настройки',
      'notifications': 'Уведомления',
      'admin': 'Администрирование',
      'admin_panel': 'Панель Администратора',
      'customize_tabs': 'Настроить Вкладки',
      'customize_tabs_description': 'Выберите, какие вкладки показывать, и перетащите для изменения порядка.',
      'reset_to_default': 'Сбросить',
      'tab_always_shown': 'Всегда отображается',
      'minimum_tabs_warning': 'Должно быть видно не менее 2 вкладок.',
      'access_denied': 'Доступ Запрещен',
      'general': 'Общее',
      'document_management': 'Управление Документами',
      'translation_management': 'Управление Переводами',
      'plugin_management': 'Управление Плагинами',
      'system_configuration': 'Конфигурация Системы',
      'user_management': 'Управление Пользователями',
      'manage_users': 'Управлять Пользователями',
      'access_requests_title': 'Запросы доступа к странам',
      'access_requests_subtitle':
          'Одобряйте или отклоняйте запросы доступа на уровне страны.',
      'access_requests_pending': 'В ожидании',
      'access_requests_processed': 'Недавние решения',
      'access_requests_empty': 'Нет запросов доступа.',
      'access_requests_approve': 'Одобрить',
      'access_requests_reject': 'Отклонить',
      'access_requests_approve_all': 'Одобрить все',
      'access_requests_approve_all_confirm':
          'Одобрить все ожидающие запросы доступа к странам?',
      'access_requests_reject_confirm':
          'Отклонить этот запрос доступа? Пользователь не получит доступ.',
      'access_requests_country': 'Страна',
      'access_requests_message': 'Сообщение',
      'access_requests_requested_at': 'Запрошено',
      'access_requests_processed_at': 'Обработано',
      'access_requests_auto_approve_hint':
          'Автоодобрение может быть включено в настройках сервера.',
      'access_requests_status_pending': 'В ожидании',
      'access_requests_status_approved': 'Одобрено',
      'access_requests_status_rejected': 'Отклонено',
      'access_requests_by': 'Кем',
      'access_requests_load_failed':
          'Не удалось загрузить запросы доступа.',
      'access_requests_action_failed': 'Не удалось выполнить действие.',
      'access_requests_view_forbidden':
          'У вас нет прав на просмотр запросов доступа на сервере.',
      'access_requests_unexpected_response':
          'Неожиданный ответ сервера.',
      'access_requests_action_forbidden':
          'У вас нет прав на это действие.',
      'users_directory_read_only':
          'Список только для чтения. Создавайте и меняйте учётные записи в веб-бэкофисе.',
      'login_logs_title': 'Журналы входа',
      'login_logs_filters': 'Фильтры',
      'login_logs_email_hint': 'Поиск по email',
      'login_logs_event_type': 'Тип события',
      'login_logs_event_all': 'Все типы',
      'login_logs_event_login': 'Вход',
      'login_logs_event_logout': 'Выход',
      'login_logs_event_failed': 'Неудачный вход',
      'login_logs_ip_label': 'IP-адрес',
      'login_logs_date_from': 'С даты',
      'login_logs_date_to': 'По дату',
      'login_logs_suspicious_only': 'Только подозрительные',
      'login_logs_apply': 'Применить',
      'login_logs_clear': 'Сбросить',
      'login_logs_no_entries': 'Нет событий по выбранным фильтрам.',
      'login_logs_total': 'Всего событий: %s',
      'login_logs_load_more': 'Загрузить ещё',
      'login_logs_user_not_resolved': 'Нет соответствующей учётной записи',
      'login_logs_device': 'Устройство',
      'login_logs_browser': 'Браузер',
      'login_logs_suspicious_badge': 'Подозрительно',
      'login_logs_recent_failures': 'Недавних сбоев: %s',
      'login_logs_open': 'Журналы входа',
      'session_logs_title': 'Журналы сессий',
      'admin_filters': 'Фильтры',
      'session_logs_email_hint': 'Поиск по email',
      'session_logs_min_duration': 'Мин. минут (сессия или активность)',
      'session_logs_active_only': 'Только активные сессии',
      'admin_filters_apply': 'Применить',
      'admin_filters_clear': 'Сбросить',
      'session_logs_no_entries': 'Нет сессий по выбранным фильтрам.',
      'session_logs_total': 'Всего сессий: %s',
      'session_logs_load_more': 'Загрузить ещё',
      'session_logs_session_start': 'Начало сессии',
      'session_logs_duration': 'Длительность',
      'session_logs_session_length': 'Длина сессии',
      'session_logs_active_time': 'Активное время',
      'session_logs_minutes': '%s мин',
      'session_logs_page_views': 'Просмотры',
      'session_logs_path_breakdown_title': 'Просмотры по путям',
      'session_logs_path_breakdown_open': 'Разбивка по путям',
      'session_logs_path_breakdown_empty':
          'Для этого сеанса нет разбивки по путям.',
      'session_logs_path_other_bucket': 'Прочие пути (агрегировано)',
      'session_logs_path_column': 'Путь',
      'session_logs_path_count_column': 'Счёт',
      'session_logs_distinct_paths': 'Различные пути',
      'session_logs_activities': 'Действия',
      'session_logs_last_activity': 'Последняя активность',
      'session_logs_status_active': 'Активна',
      'session_logs_status_ended': 'Завершена',
      'session_logs_force_logout': 'Принудительный выход',
      'session_logs_force_logout_confirm':
          'Принудительно завершить сессию этого пользователя? Он будет немедленно разлогинен.',
      'session_logs_unknown_user': 'Неизвестный пользователь',
      'session_logs_no_activity': 'Нет активности',
      'session_logs_open': 'Журналы сессий',
      'session_logs_ended_ok': 'Сессия завершена.',
      'session_logs_os': 'ОС',
      'session_logs_user_agent': 'User-Agent',
      'session_logs_device_section': 'Сведения об устройстве',
      'form_data_management': 'Управление Формами и Данными',
      'manage_templates': 'Управлять Шаблонами',
      'manage_assignments': 'Управлять Назначениями',
      'frontend_management': 'Управление Website',
      'manage_resources': 'Управлять Ресурсами',
      'reference_data': 'Справочные Данные',
      'organizational_structure': 'Организационная Структура',
      'analytics_monitoring': 'Аналитика и Мониторинг',
      'user_analytics': 'Аналитика Пользователей',
      'audit_trail': 'Журнал Аудита',
      'api_management': 'Управление API',
      'account_settings': 'Настройки Аккаунта',
      'profile': 'Профиль',
      'preferences': 'Предпочтения',
      'language': 'Язык',
      'select_language': 'Выбрать Язык',
      'change_password': 'Изменить Пароль',
      'profile_color': 'Цвет Профиля',
      'chatbot': 'Чатбот',
      'enable_chatbot_assistance': 'Включить помощь чатбота',
      'dark_theme': 'Темная Тема',
      'enable_dark_theme': 'Включить темную тему',
      'settings_theme': 'Тема',
      'light_theme': 'Светлая тема',
      'system_theme': 'Системная',
      'select_theme': 'Выберите тему',
      'settings_theme_set_to': 'Тема: %s',
      'arabic_text_font': 'Арабский шрифт',
      'arabic_font_tajawal': 'Tajawal',
      'arabic_font_system': 'Системный',
      'login_to_account': 'Войти в Аккаунт',
      'logout': 'Выйти',
      'are_you_sure_logout': 'Вы уверены, что хотите выйти?',
      'cancel': 'Отмена',
      'name': 'Имя',
      'title': 'Должность',
      'email': 'Электронная Почта',
      'loading': 'Загрузка...',
      'loading_home': 'Загрузка Главной...',
      'home_landing_hero_description':
          'Изучайте комплексные гуманитарные данные, индикаторы и аналитику от Международной Федерации обществ Красного Креста и Красного Полумесяца.',
      'home_landing_chat_title': 'Чат с нашими данными',
      'home_landing_chat_description': 'Введите ваши вопросы о данных МФОКК ниже.',
      'home_landing_ask_placeholder': 'Спрашивайте о финансировании, программах, странах...',
      'home_landing_quick_prompt_1': 'Расскажите мне о волонтерах Афганского Красного Полумесяца',
      'home_landing_quick_prompt_2': 'Покажите мне глобальные данные о реагировании на бедствия',
      'home_landing_quick_prompt_3': 'Какие основные гуманитарные индикаторы?',
      'home_landing_shortcuts_heading': 'Начать',
      'home_landing_shortcut_indicators_subtitle': 'Определения и метаданные',
      'home_landing_shortcut_resources_subtitle': 'Публикации и материалы',
      'home_landing_shortcut_countries_subtitle': 'Профили и региональные обзоры',
      'home_landing_shortcut_disaggregation_subtitle': 'Разбивка значений индикаторов',
      'home_landing_explore_title': 'Глобальная карта и графики',
      'home_landing_explore_subtitle':
          'Нативная карта и график с теми же итогами FDRS, что на сайте — без выхода из приложения.',
      'home_landing_global_indicator_volunteers': 'Волонтёры',
      'home_landing_global_indicator_staff': 'Персонал',
      'home_landing_global_indicator_branches': 'Филиалы',
      'home_landing_global_indicator_local_units': 'Local units',
      'home_landing_global_indicator_blood_donors': 'Blood donors',
      'home_landing_global_indicator_first_aid': 'First aid',
      'home_landing_global_indicator_people_reached': 'People reached',
      'home_landing_global_indicator_income': 'Income',
      'home_landing_global_indicator_expenditure': 'Expenditure',
      'home_landing_global_top_countries': 'Топ стран',
      'home_landing_global_load_error':
          'Не удалось загрузить данные карты. Проверьте подключение и попробуйте снова.',
      'home_landing_global_empty':
          'Нет значений по этому показателю за последний период.',
      'home_landing_global_period': 'Период: %s',
      'home_landing_global_map_hint':
          'Сведите, перетащите и нажмите на страну для подробностей',
      'home_landing_global_map_open_fullscreen': 'На весь экран',
      'home_landing_global_period_filter_label': 'Отчётный период',
      'home_landing_global_map_mode_bubble': 'Пузыри',
      'home_landing_global_map_mode_choropleth': 'Картограмма',
      'home_landing_global_map_zoom_in': 'Приблизить',
      'home_landing_global_map_zoom_out': 'Отдалить',
      'home_landing_global_map_reset_bounds': 'По данным',
      'home_landing_global_map_legend_low': 'Низк.',
      'home_landing_global_map_legend_high': 'Высок.',
      'home_landing_global_map_country_no_data': 'Нет данных по показателю',
      'home_landing_global_map_value_label': 'Значение',
      'home_landing_global_map_country_trend': 'По отчётным периодам',
      'home_landing_global_map_filters_title': 'Параметры карты',
      'loading_page': 'Загрузка страницы...',
      'loading_preferences': 'Загрузка настроек...',
      'loading_notifications': 'Загрузка уведомлений...',
      'loading_dashboard': 'Загрузка панели управления...',
      'loading_audit_logs': 'Загрузка журналов аудита...',
      'loading_analytics': 'Загрузка аналитики...',
      'loading_organizations': 'Загрузка организаций...',
      'loading_templates': 'Загрузка шаблонов...',
      'loading_assignments': 'Загрузка назначений...',
      'loading_translations': 'Загрузка переводов...',
      'loading_plugins': 'Загрузка плагинов...',
      'loading_resources': 'Загрузка ресурсов...',
      'loading_indicators': 'Загрузка индикаторов...',
      'loading_documents': 'Загрузка документов...',
      'loading_api_endpoints': 'Загрузка API endpoints...',
      'loading_users': 'Загрузка пользователей...',
      'error': 'Ошибка',
      'retry': 'Повторить',
      'refresh': 'Обновить',
      'close': 'Закрыть',
      'save': 'Сохранить',
      'saved': 'Сохранено',
      'success': 'Успешно',
      'oops_something_went_wrong': 'Упс! Что-то пошло не так',
      'go_back': 'Назад',
      'edit': 'Редактировать',
      'duplicate': 'Дублировать',
      'preview': 'Предпросмотр',
      'download_started': 'Загрузка началась',
      'could_not_start_download': 'Не удалось начать загрузку',
      'could_not_open_download_link': 'Не удалось открыть ссылку для загрузки',
      'error_opening_download': 'Ошибка при открытии загрузки',
      'please_select_at_least_one_user': 'Пожалуйста, выберите хотя бы одного пользователя',
      'indicator_updated_successfully': 'Индикатор успешно обновлен',
      'failed_to_load_indicator': 'Не удалось загрузить индикатор',
      'user_deleted': 'Пользователь удален',
      'public_url_copied': 'Публичный URL скопирован в буфер обмена!',
      'please_use_web_interface': 'Пожалуйста, используйте веб-интерфейс для сохранения изменений сущности',
      'open_in_web_browser': 'Открыть в веб-браузере',
      'countries': 'Страны',
      'all_roles': 'Все роли',
      'admin_role': 'Администратор',
      'focal_point_role': 'Контактное лицо',
      'system_manager_role': 'Системный менеджер',
      'viewer_role': 'Наблюдатель',
      'all_status': 'Все статусы',
      'active_status': 'Активный',
      'inactive_status': 'Неактивный',
      'normal_priority': 'Обычный',
      'high_priority': 'Высокий',
      'none': 'Нет',
      'app_screen': 'Экран приложения',
      'custom_url': 'Пользовательский URL',
      'create_template': 'Создать шаблон',
      'delete_template': 'Удалить шаблон',
      'create_assignment': 'Создать назначение',
      'delete_assignment': 'Удалить назначение',
      'edit_document': 'Редактировать документ',
      'preview_document': 'Предпросмотр документа',
      'download_document': 'Скачать документ',
      'upload_document': 'Загрузить документ',
      'new_translation': 'Новый перевод',
      'new_resource': 'Новый ресурс',
      'install_plugin': 'Установить плагин',
      'template_deleted_successfully': 'Шаблон успешно удален',
      'failed_to_delete_template': 'Не удалось удалить шаблон',
      'error_loading_page': 'Ошибка загрузки страницы',
      'no_notifications': 'Нет уведомлений',
      'all_caught_up': 'Вы все наверстали',
      'notifications_load_more': 'Загрузить ещё',
      'notifications_filter': 'Фильтры',
      'notifications_filter_title': 'Фильтр уведомлений',
      'notifications_filter_read_status': 'Статус прочтения',
      'notifications_filter_all': 'Все',
      'notifications_filter_unread_only': 'Только непрочитанные',
      'notifications_filter_type': 'Тип',
      'notifications_filter_type_any': 'Все типы',
      'notifications_filter_from': 'От',
      'notifications_filter_from_any': 'Любой',
      'notifications_filter_from_empty_hint':
          'Люди появляются, когда их уведомления есть в загруженном списке. Используйте «Загрузить ещё».',
      'notifications_filter_priority': 'Приоритет',
      'notifications_filter_priority_any': 'Любой приоритет',
      'notifications_filter_priority_normal': 'Обычный',
      'notifications_filter_priority_high': 'Высокий',
      'notifications_filter_priority_urgent': 'Срочный',
      'notifications_filter_apply': 'Применить',
      'notifications_filter_reset': 'Сбросить всё',
      'notifications_filter_no_matches_loaded':
          'Нет уведомлений по фильтрам в загруженном списке. Загрузите ещё или измените фильтры.',
      'mark_all_read': 'Отметить все как прочитанные',
      'mark_read': 'Отметить как прочитанное',
      'mark_unread': 'Отметить как непрочитанное',
      'delete': 'Удалить',
      'archive': 'Архивировать',
      'unarchive': 'Разархивировать',
      'send_push_notification': 'Отправить Push-уведомление',
      'admin_push_user_ids_label': 'ID получателей',
      'admin_push_user_ids_hint':
          'Числовые ID через запятую (см. раздел «Пользователи»).',
      'admin_push_user_ids_invalid':
          'Введите один или несколько числовых ID пользователей через запятую.',
      'select_users': 'Выбрать пользователей',
      'search_users': 'Поиск пользователей по имени или email',
      'redirect_url': 'Перенаправить (Необязательно)',
      'login': 'Вход',
      'log_in': 'Войти',
      'phone_username_email': 'Телефон, имя пользователя или электронная почта',
      'forgot_password_coming_soon': 'Функция забытого пароля скоро появится',
      'please_enter_email': 'Пожалуйста, введите ваш email',
      'please_enter_valid_email': 'Пожалуйста, введите действительный email',
      'please_enter_password': 'Пожалуйста, введите ваш пароль',
      'show': 'Показать',
      'hide': 'Скрыть',
      'or': 'ИЛИ',
      'dont_have_account': 'Нет аккаунта?',
      'sign_up': 'Зарегистрироваться',
      'registration_coming_soon': 'Функция регистрации скоро появится',
      'quick_login_testing': 'Быстрый Вход для Тестирования',
      'test_as_admin': 'Тест как Администратор',
      'test_as_focal_point': 'Тест как Координатор',
      'public_login_disabled': 'Публичный вход временно отключен',
      'tester_accounts_info':
          'Тестовые аккаунты все еще могут войти, используя кнопки выше.',
      'could_not_open_azure_login': 'Не удалось открыть вход Azure',
      'login_with_ifrc_account': 'Войти с учетной записью IFRC',
      'use_ifrc_federation_account':
          'Используйте свою учетную запись IFRC Federation для входа',
      'your_account_or_create_account': 'Ваш аккаунт или создать аккаунт',
      'login_failed': 'Ошибка входа',
      'email_address': 'Адрес Электронной Почты',
      'password': 'Пароль',
      'remember_me': 'Запомнить меня',
      'forgot_password': 'Забыли пароль?',
      'language_changed_to': 'Язык изменен на',

      // Splash Screen
      'welcome_to_ifrc_network_databank':
          'Добро пожаловать в Банк Данных Сети МФОКК',
      'splash_description':
          'Это единственная система для отчетности данных в МФОКК. Попрощайтесь с разбросанными файлами Excel, формами KoBo, множественными платформами и входами — все теперь централизовано и оптимизировано здесь.',
      'powered_by_hum_databank': 'На платформе Humanitarian Databank',
      'open_on_github': 'Открыть на GitHub',

      // Dashboard
      'national_society': 'Национальное Общество',
      'active': 'Активный',
      'completed': 'Завершен',
      'current_assignments': 'Текущие Назначения',
      'dashboard_you_have_no_open_assignments':
          'У вас нет открытых назначений',
      'dashboard_you_have_one_open_assignment':
          'У вас 1 открытое назначение',
      'dashboard_you_have_open_assignments_count':
          'У вас %s открытых назначений',
      'past_assignments': 'Прошлые Назначения',
      'assignments_for': 'Назначения для',
      'past_submissions_for': 'Прошлые Отправки для',
      'something_went_wrong': 'Что-то пошло не так',
      'no_assignments_yet':
          'Всё ясно! Нет активных назначений на данный момент.',
      'new_assignments_will_appear':
          'Новые назначения появятся здесь, когда будут доступны.',
      'get_started_by_creating': 'Начните с создания нового назначения',
      'filters': 'Фильтры',
      'period': 'Период',
      'template': 'Шаблон',
      'status': 'Статус',
      'clear': 'Очистить',
      'approved': 'Одобрено',
      'requires_revision': 'Требуется Редакция',
      'pending': 'В Ожидании',
      'in_progress': 'В Процессе',
      'submitted': 'Отправлено',
      'other': 'Другое',
      'entities': 'Сущности',
      'search_placeholder': 'Поиск...',
      'no_results_found': 'Результаты не найдены',
      'entity_type_country': 'Страна',
      'entity_type_ns_branch': 'Филиал НО',
      'entity_type_ns_sub_branch': 'Подфилиал НО',
      'entity_type_ns_local_unit': 'Местная единица НО',
      'entity_type_division': 'Подразделение',
      'entity_type_department': 'Отдел',
      'delete_assignment_confirm_message':
          'Вы уверены, что хотите удалить это назначение и все связанные с ним статусы стран и данные?',
      'no_assignments_match_filters':
          'Нет назначений, соответствующих выбранным фильтрам',
      'form': 'Форма',
      'last_updated': 'Последнее Обновление',
      'actions': 'Действия',
      'all_years': 'Все Годы',
      'all_templates': 'Все Шаблоны',
      'all_statuses': 'Все Статусы',
      'template_missing': 'Шаблон Отсутствует',
      'self_reported': 'Самостоятельно Сообщено',
      'no_actions_available': 'Нет доступных действий',
      'previous': 'Предыдущий',
      'next': 'Следующий',
      'showing': 'Показано',
      'to': 'до',
      'of': 'из',
      'results': 'результатов',
      'no_past_assignments_for': 'Нет прошлых назначений для',
      'yet': 'пока',
      'submission_history_and_data_quality_for':
          'История Отправок и Качество Данных для',
      'overall_performance': 'Общая Производительность',
      'average_completion_rate_past_3_periods':
          'Средняя Скорость Завершения (Последние 3 Периода)',
      'average_submission_timeliness':
          'Средняя Своевременность Отправки (Дней Ранее/Позже)',
      'data_quality_index_fake_metric':
          'Индекс Качества Данных (Фиктивный Метрика)',
      'number_of_revisions_requested_past_year':
          'Количество Запрошенных Редакций (Прошлый Год)',
      'trend_analysis': 'Анализ Тренда',
      'recent_activities': 'Недавняя Активность',
      'last_7_days': 'Последние 7 дней',
      'unknown_user': 'Неизвестный Пользователь',
      'added': 'Добавлено',
      'updated': 'Обновлено',
      'removed': 'Удалено',
      'show_less': 'Показать меньше',
      'more_change': 'больше изменений',
      'no_recent_activities': 'Нет недавней активности',
      'activities_from_other_focal_points_in':
          'Активность от других координаторов в',
      'will_appear_here': 'появится здесь',
      'focal_points_for': 'Координаторы для',
      'national_society_focal_points': 'Координаторы Национального Общества',
      'ifrc_focal_points': 'Координаторы МФОКК',
      'no_focal_points_assigned_to': 'Нет координаторов, назначенных для',
      'your_user_account_not_associated':
          'Ваша учетная запись не связана ни с одной страной',
      'please_contact_administrator': 'Пожалуйста, свяжитесь с администратором',
      'due_date': 'Срок Выполнения',
      'no_due_date': 'Нет срока выполнения',
      'overdue': 'Просрочено',
      'latest_submission': 'Последняя Отправка',
      'submitted_through_public_link': 'Отправлено через публичную ссылку',
      'submission': 'отправка',
      'submissions': 'отправки',
      'completion': 'Завершение',
      'received_1_submission_using_public_link':
          'Получена 1 отправка с использованием публичной ссылки',
      'received_count_submissions_using_public_link':
          'Получено %(count)d отправок с использованием публичной ссылки',
      'at_datetime': 'в: %(datetime)s',
      'latest_datetime': 'Последняя: %(datetime)s',
      'last_modified_by': 'Последнее изменение от',
      'assignment_assigned_date': 'Назначено',
      'assignment_status_updated': 'Статус обновлён',
      'contributors': 'Участники',
      'assignment_submitted_by': 'Отправил(а)',
      'assignment_approved_by': 'Утвердил(а)',
      'public_link_enabled': 'Публичная ссылка включена',
      'public_link': 'Публичная ссылка',
      'unknown': 'Неизвестно',
      'n_a': 'Н/Д',
      'enter_data': 'Ввести Данные',
      'download_for_offline': 'Скачать для офлайн',
      'downloading_offline_form': 'Скачивание формы для офлайн-использования…',
      'offline_form_saved': 'Форма сохранена для офлайн-доступа.',
      'offline_form_save_failed': 'Не удалось сохранить форму офлайн. Повторите при стабильном соединении.',
      'offline_form_not_downloaded': 'Эта форма недоступна офлайн. Скачайте её при подключении к сети.',
      'offline_download_requires_connection': 'Подключитесь к интернету, чтобы скачать эту форму для офлайн-использования.',
      'offline_form_export_requires_connection':
          'Подключитесь к интернету, чтобы экспортировать PDF, Excel или отчёты проверки. Офлайн-копия не содержит файлов экспорта.',
      'offline_open_saved_copy': 'Открыть сохранённую офлайн-копию',
      'remove_offline_copy': 'Удалить офлайн-копию',
      'offline_form_removed':
          'Офлайн-копия удалена. Скачайте снова при подключении к сети.',
      'offline_saved_copy_details_tooltip':
          'Офлайн-копия — сведения и удаление',
      'offline_copy_sheet_title': 'Офлайн-копия формы',
      'offline_copy_saved_on_label': 'Сохранено',
      'offline_copy_files_cached': '%(count)d кэшированных ресурсов',
      'offline_stale_bundle_banner_title': 'Нужно обновить офлайн-формы',
      'offline_stale_bundle_banner_body_online':
          'Онлайн-форма изменилась. Устройство автоматически обновляет офлайн-копии при подключении. Если не получилось, откройте форму с предупреждением и нажмите «Обновить офлайн-копию».',
      'offline_stale_bundle_banner_body_offline':
          'Онлайн-форма изменилась. Подключитесь к интернету, чтобы устройство могло автоматически обновить офлайн-копии.',
      'offline_stale_bundle_updates_snackbar':
          'Офлайн-копии обновлены до последней версии.',
      'offline_stale_bundle_partial_refresh':
          'Не удалось обновить некоторые офлайн-копии. Нажмите значок предупреждения на форме, затем «Обновить офлайн-копию».',
      'offline_stale_bundle_sheet_notice':
          'Эта офлайн-копия может не соответствовать текущей онлайн-форме. Обновите её, чтобы избежать проблем с версией.',
      'offline_stale_bundle_update_now': 'Обновить офлайн-копию',
      'approve': 'Одобрить',
      'reopen': 'Переоткрыть',
      'view_public_submissions': 'Просмотр Публичных Отправок',
      'view_submission': 'Просмотр Отправки',
      'view_submissions': 'Просмотр Отправок',
      'open_form': 'Открыть Форму',
      'no_forms_assigned_or_submitted_for':
          'Не было назначено или отправлено форм через публичные ссылки для',
      'admins_can_assign_forms':
          'Администраторы могут назначать формы или создавать публичные ссылки через Панель Администратора',
      'create_a_report': 'Создать Отчет',
      'delete_self_reported_assignment':
          'Удалить Самостоятельно Сообщенное Назначение',
      'quick_actions': 'Быстрые Действия',
      'new_assignment': 'Новое Назначение',
      'new_template': 'Новый Шаблон',
      'key_metrics': 'Ключевые Показатели',
      'overview': 'Обзор',
      'create_new_assignment': 'Создать новое назначение',
      'browse_available_templates': 'Просмотр доступных шаблонов',
      'enter_your_name': 'Введите ваше имя',
      'enter_your_job_title': 'Введите вашу должность',
      'edit_name': 'Редактировать Имя',
      'edit_title': 'Редактировать Должность',
      'name_cannot_be_empty': 'Имя не может быть пустым',
      'title_cannot_be_empty': 'Должность не может быть пустой',
      'profile_updated_successfully': 'Профиль успешно обновлен',
      'error_updating_profile': 'Ошибка при обновлении профиля',
      'color_picker_coming_soon': 'Выбор цвета скоро',
      'chatbot_preference_update_coming_soon':
          'Обновление настроек чатбота скоро',
      'select_color': 'Выберите цвет',
      'current_color': 'Текущий цвет',
      'profile_color_updated': 'Цвет профиля успешно обновлен',
      'profile_color_update_failed': 'Не удалось обновить цвет профиля',
      'admin_dashboard': 'Панель Администратора',
      'no_data_available': 'Нет доступных данных',
      'total_users': 'Всего Пользователей',
      'admins': 'Администраторы',
      'system_administrators': 'Системные администраторы',
      'focal_points': 'Координаторы',
      'country_focal_points': 'Координаторы страны',
      'form_templates': 'Шаблоны форм',
      'active_assignments': 'Активные назначения',
      'todays_logins': 'Входы Сегодня',
      'successful_logins_today': 'Успешные входы сегодня',
      'pending_submissions': 'Ожидающие Отправки',
      'overdue_assignments': 'Просроченные Назначения',
      'security_alerts': 'Оповещения Безопасности',
      'successful_logins': 'Успешные Входы',
      'user_activities': 'Активность Пользователей',
      'active_sessions': 'Активные Сессии',
      'all_notifications_marked_as_read':
          'Все уведомления отмечены как прочитанные',
      'mark_as_read': 'Отметить как прочитанное',
      'mark_as_unread': 'Отметить как непрочитанное',
      'notification_preferences': 'Настройки Уведомлений',
      'sound_notifications': 'Звуковые Уведомления',
      'email_frequency': 'Частота Электронной Почты',
      'instant': 'Мгновенно',
      'daily_digest': 'Ежедневный Дайджест',
      'weekly_digest': 'Еженедельный Дайджест',
      'digest_schedule': 'Расписание Дайджеста',
      'day_of_week': 'День Недели',
      'monday': 'Понедельник',
      'tuesday': 'Вторник',
      'wednesday': 'Среда',
      'thursday': 'Четверг',
      'friday': 'Пятница',
      'saturday': 'Суббота',
      'sunday': 'Воскресенье',
      'time_local_time': 'Время (Местное Время)',
      'notification_types': 'Типы Уведомлений',
      'preferences_saved_successfully': 'Настройки успешно сохранены',
      'enable_sound': 'Включить Звук',
      'play_sound_for_new_notifications': 'Воспроизводить звук для новых уведомлений',
      'configure_notification_types_description': 'Настройте типы уведомлений для получения по электронной почте и push-уведомлениям',
      'notification_type': 'Тип Уведомления',
      'push': 'Push',
      'all': 'Все',
      'save_preferences': 'Сохранить Настройки',
      'select_digest_time_description': 'Выберите время, когда вы хотите получать сводку',
      'failed_to_save_preferences': 'Не удалось сохранить настройки',
      'assignment_created': 'Задание Создано',
      'assignment_submitted': 'Задание Отправлено',
      'assignment_approved': 'Задание Одобрено',
      'assignment_reopened': 'Задание Переоткрыто',
      'public_submission_received': 'Публичная Отправка Получена',
      'form_updated': 'Форма Обновлена',
      'document_uploaded': 'Документ Загружен',
      'user_added_to_country': 'Пользователь Добавлен в Страну',
      'template_updated': 'Шаблон Обновлен',
      'self_report_created': 'Собственный Отчет Создан',
      'deadline_reminder': 'Напоминание о Сроке',
      'search_audit_logs': 'Поиск журналов аудита...',
      'home_screen_widget_title': 'Виджет главного экрана',
      'audit_widget_activity_types_hint':
          'Выберите типы активности для виджета. Без выбора — все типы. Сохраняется на этом устройстве.',
      'action': 'Действие',
      'all_actions': 'Все Действия',
      'create': 'Создать',
      'update': 'Обновить',
      'user': 'Пользователь',
      'all_users': 'Все Пользователи',
      'from_date': 'С Дата',
      'to_date': 'По Дата',
      'select_date': 'Выберите дату',
      'no_description': 'Нет описания',
      'search_api_endpoints': 'Поиск конечных точек API...',
      'http_method': 'HTTP Метод',
      'all_methods': 'Все Методы',
      'get': 'GET',
      'post': 'POST',
      'put': 'PUT',
      'delete_method': 'DELETE',
      'deprecated': 'Устаревший',
      'beta': 'Бета',
      'new_api_key': 'Новый API Ключ',
      'time_range': 'Временной Диапазон',
      'last_30_days': 'Последние 30 Дней',
      'last_90_days': 'Последние 90 Дней',
      'last_year': 'Прошлый Год',
      'all_time': 'Все Время',
      'metric': 'Метрика',
      'all_metrics': 'Все Метрики',
      'active_users': 'Активные Пользователи',
      'logins': 'Входы',
      'metric_submissions': 'Отправки',
      'page_views': 'Просмотры Страниц',
      'search_indicators': 'Поиск индикаторов...',
      'category': 'Категория',
      'all_categories': 'Все Категории',
      'output': 'Выход',
      'outcome': 'Результат',
      'impact': 'Воздействие',
      'all_sectors': 'Все Секторы',
      'health': 'Здоровье',
      'wash': 'WASH',
      'shelter': 'Убежище',
      'education': 'Образование',
      'indicators': 'Индикаторы',
      'new_indicator': 'Новый Индикатор',
      'search_organizations': 'Поиск организаций...',
      'entity_type': 'Тип Сущности',
      'all_types': 'Все Типы',
      'national_societies': 'Национальные Общества',
      'ns_structure': 'Структура NS',
      'secretariat': 'Секретариат',
      'divisions': 'Отделы',
      'departments': 'Департаменты',
      'regional_offices': 'Региональные Офисы',
      'cluster_offices': 'Кластерные Офисы',
      'add_organization': 'Добавить Организацию',
      'search_resources': 'Поиск ресурсов...',
      'no_indicators_found': 'Индикаторы не найдены',
      'no_organizations_found': 'Организации не найдены',
      'no_resources_found': 'Ресурсы не найдены',
      'resources_unified_planning_section_title': 'Единые планы и отчёты',
      'resources_unified_planning_section_subtitle':
          'Планы, полугодовые и годовые отчёты из IFRC GO (загружаются в приложении).',
      'unified_planning_empty':
          'Нет документов единого планирования по вашему запросу.',
      'unified_planning_fresh_badge': 'Свежее',
      'unified_planning_sort_by': 'Сортировка',
      'unified_planning_sort_date_newest': 'Дата: сначала новые',
      'unified_planning_sort_date_oldest': 'Дата: сначала старые',
      'unified_planning_sort_country_az': 'Страна: А–Я',
      'unified_planning_sort_country_za': 'Страна: Я–А',
      'unified_planning_filter_all_countries': 'Все страны',
      'unified_error_config':
          'Не удалось загрузить настройки единого планирования с сервера. Попробуйте позже.',
      'unified_error_credentials':
          'Документы IFRC недоступны в этом приложении. Обратитесь к администратору.',
      'unified_error_ifrc_auth':
          'Не удалось получить доступ к документам IFRC. Обратитесь к администратору, если проблема сохранится.',
      'unified_error_ifrc':
          'Не удалось загрузить документы из IFRC GO. Проверьте соединение и повторите попытку.',
      'no_plugins_found': 'Плагины не найдены',
      'no_translations_found': 'Переводы не найдены',
      'no_documents_found': 'Документы не найдены',
      'no_users_found': 'Пользователи не найдены',
      'loading_user_profile': 'Загрузка профиля…',
      'failed_load_user_profile': 'Не удалось загрузить пользователя.',
      'admin_user_detail_confirm_save_title': 'Сохранить изменения?',
      'admin_user_detail_confirm_save_message':
          'Обновить имя, должность, статус и настройки профиля этого пользователя.',
      'admin_user_detail_invalid_profile_color':
          'Введите корректный цвет в формате #RRGGBB (например #3B82F6).',
      'admin_user_detail_changes_saved': 'Изменения сохранены.',
      'admin_user_detail_save_changes': 'Сохранить изменения',
      'admin_user_detail_profile_color_label': 'Цвет профиля',
      'admin_user_detail_profile_color_hint': '#RRGGBB',
      'admin_user_detail_cannot_deactivate_self':
          'Нельзя деактивировать собственную учётную запись.',
      'admin_user_detail_matrix_read_only_bundled':
          'Сводные админ-роли (полный/базовый/система) — детальный доступ по областям меняйте в веб-интерфейсе.',
      'admin_user_detail_rbac_incomplete':
          'Не удалось сформировать корректный список ролей. Проверьте доступ или повторите попытку.',
      'assigned_roles_title': 'Назначенные роли',
      'role_type_label': 'Тип роли',
      'permissions_by_role': 'Разрешения по ролям',
      'all_permissions_union': 'Все разрешения (из ролей)',
      'entity_permissions_title': 'Разрешения на сущности',
      'manage_users_detail_footer':
          'Чтобы изменить роли, доступ к сущностям, устройства или уведомления, используйте веб-форму пользователя.',
      'no_roles_assigned': 'RBAC-роли не назначены.',
      'no_entities_assigned': 'Нет назначений сущностей.',
      'entity_permission_unnamed': 'Без названия',
      'entity_region_other': 'Другой регион',
      'no_permissions_listed': 'Для этой роли разрешения не перечислены.',
      'user_dir_assignment_roles': 'Роли назначений',
      'user_dir_admin_roles': 'Админ и система',
      'user_dir_other_roles': 'Прочие роли',
      'admin_role_access_area': 'Область',
      'admin_role_access_view': 'Просмотр',
      'admin_role_access_manage': 'Управление',
      'admin_role_de_heading': 'Исследование данных',
      'admin_role_de_table': 'Таблица',
      'admin_role_de_analysis': 'Анализ',
      'admin_role_de_compliance': 'Соответствие',
      'admin_role_note_admin_full': 'Все права администратора (сводная роль)',
      'admin_role_note_admin_core': 'Базовые админ-функции (сводная роль)',
      'admin_role_other_admin_roles': 'Прочие админ-роли',
      'users_directory_role_all': 'Все роли',
      'users_directory_country_all': 'Все страны',
      'no_assignments_found': 'Назначения не найдены',
      'no_templates_found': 'Шаблоны не найдены',
      'assignment_deleted_successfully': 'Назначение успешно удалено',
      'failed_to_delete_assignment': 'Не удалось удалить назначение',
      'timeline_view': 'Временная Шкала',
      'view_all_public_submissions': 'Просмотр Всех Публичных Отправлений',
      'items_requiring_attention': 'Элементы, Требующие Внимания',
      'recent_activity': 'Недавняя Активность',
      'recent_activity_7_days': 'Недавняя Активность (7 дней)',
      'general_settings': 'Общие Настройки',
      'security_settings': 'Настройки Безопасности',
      'system_settings': 'Системные Настройки',
      'application_settings': 'Настройки Приложения',
      'language_settings': 'Языковые Настройки',
      'notification_settings': 'Настройки Уведомлений',
      'authentication_settings': 'Настройки Аутентификации',
      'permission_settings': 'Настройки Разрешений',
      'database_settings': 'Настройки Базы Данных',
      'cloud_storage_settings': 'Настройки Облачного Хранилища',
      'configure_general_application_settings':
          'Настроить общие параметры приложения',
      'manage_supported_languages_and_translations':
          'Управлять поддерживаемыми языками и переводами',
      'configure_notification_preferences':
          'Настроить предпочтения уведомлений',
      'configure_authentication_and_authorization':
          'Настроить аутентификацию и авторизацию',
      'manage_user_permissions_and_roles':
          'Управлять разрешениями и ролями пользователей',
      'configure_database_connections_and_backups':
          'Настроить подключения к базе данных и резервное копирование',
      'configure_cloud_storage_and_file_management':
          'Настроить облачное хранилище и управление файлами',

      // Indicator Bank
      'indicator_bank_title': 'Банк Индикаторов',
      'indicator_bank_loading': 'Загрузка Банка Индикаторов...',
      'indicator_bank_error': 'Что-то пошло не так',
      'indicator_bank_search_placeholder': 'Поиск индикаторов...',
      'indicator_bank_filter_placeholder': 'Фильтрация индикаторов...',
      'indicator_bank_browse_description':
          'Просмотр и поиск индикаторов для гуманитарного реагирования',
      'indicator_bank_grid_view': 'Вид Сетки',
      'indicator_bank_table_view': 'Вид Таблицы',
      'indicator_bank_show_filters': 'Показать Фильтры',
      'indicator_bank_hide_filters': 'Скрыть Фильтры',
      'indicator_bank_filters': 'Фильтры',
      'indicator_bank_filter_type': 'Тип',
      'indicator_bank_filter_type_all': 'Все Типы',
      'indicator_bank_filter_sector': 'Сектор',
      'indicator_bank_filter_sector_all': 'Все Секторы',
      'indicator_bank_filter_subsector': 'Подсектор',
      'indicator_bank_filter_subsector_all': 'Все Подсекторы',
      'indicator_bank_list_tier_also_related': 'Также связано',
      'indicator_bank_filter_status': 'Статус',
      'indicator_bank_filter_status_active': 'Только Активные',
      'indicator_bank_filter_status_all': 'Все',
      'indicator_bank_apply_filters': 'Применить Фильтры',
      'indicator_bank_clear_all': 'Очистить Все',
      'indicator_bank_showing': 'Показано',
      'indicator_bank_indicators': 'индикаторов',
      'indicator_bank_indicator': 'индикатор',
      'indicator_bank_no_sectors': 'Секторы не найдены',
      'indicator_bank_no_indicators': 'Индикаторы не найдены',
      'indicator_bank_table_name': 'Название',
      'indicator_bank_table_type': 'Тип',
      'indicator_bank_table_sector': 'Сектор',
      'indicator_bank_table_subsector': 'Подсектор',
      'indicator_bank_table_unit': 'Единица',
      'indicator_bank_propose_new': 'Предложить Новый Индикатор',
      'indicator_bank_propose_title': 'Предложить Новый Индикатор',
      'indicator_bank_propose_contact_info': 'Контактная Информация',
      'indicator_bank_propose_your_name': 'Ваше Имя *',
      'indicator_bank_propose_email': 'Адрес Электронной Почты *',
      'indicator_bank_propose_indicator_info': 'Информация об Индикаторе',
      'indicator_bank_propose_indicator_name': 'Название Индикатора *',
      'indicator_bank_propose_definition': 'Определение *',
      'indicator_bank_propose_type': 'Тип',
      'indicator_bank_propose_unit': 'Единица Измерения',
      'indicator_bank_propose_sector': 'Сектор',
      'indicator_bank_propose_primary_sector': 'Основной Сектор *',
      'indicator_bank_propose_secondary_sector': 'Вторичный Сектор',
      'indicator_bank_propose_tertiary_sector': 'Третичный Сектор',
      'indicator_bank_propose_subsector': 'Подсектор',
      'indicator_bank_propose_primary_subsector': 'Основной Подсектор *',
      'indicator_bank_propose_secondary_subsector': 'Вторичный Подсектор',
      'indicator_bank_propose_tertiary_subsector': 'Третичный Подсектор',
      'indicator_bank_propose_emergency': 'Контекст Чрезвычайной Ситуации',
      'indicator_bank_propose_related_programs': 'Связанные Программы',
      'indicator_bank_propose_reason': 'Причина Предложения *',
      'indicator_bank_propose_additional_notes': 'Дополнительные Заметки',
      'indicator_bank_propose_submit': 'Отправить Предложение',
      'indicator_bank_propose_thank_you': 'Спасибо!',
      'indicator_bank_propose_success':
          'Ваше предложение индикатора успешно отправлено.',
      'indicator_bank_propose_failed':
          'Не удалось отправить предложение. Пожалуйста, попробуйте снова.',
      'indicator_bank_name_required': 'Имя обязательно',
      'indicator_bank_email_required': 'Электронная почта обязательна',
      'indicator_bank_indicator_name_required':
          'Название индикатора обязательно',
      'indicator_bank_definition_required': 'Определение обязательно',
      'indicator_bank_primary_sector_required': 'Основной сектор обязателен',
      'indicator_bank_primary_subsector_required':
          'Основной подсектор обязателен',
      'indicator_bank_reason_required': 'Причина обязательна',

      // Indicator Detail
      'indicator_detail_title': 'Детали Индикатора',
      'indicator_detail_loading': 'Загрузка деталей индикатора...',
      'indicator_detail_error': 'Что-то пошло не так',
      'indicator_detail_not_found': 'Индикатор не найден',
      'indicator_detail_go_back': 'Назад',
      'indicator_detail_definition': 'Определение',
      'indicator_detail_details': 'Детали',
      'indicator_detail_type': 'Тип',
      'indicator_detail_unit': 'Единица',
      'indicator_detail_sector': 'Сектор',
      'indicator_detail_subsector': 'Подсектор',
      'indicator_detail_emergency_context': 'Контекст Чрезвычайной Ситуации',
      'indicator_detail_related_programs': 'Связанные Программы',
      'indicator_detail_status': 'Статус',
      'indicator_detail_archived': 'Архивирован',
      'indicator_detail_yes': 'Да',
      'editIndicator': 'Редактировать Индикатор',

      // Quiz Game
      'quiz_game': 'Викторина',
      'quiz_game_title': 'Викторина',
      'quiz_game_test_your_knowledge': 'Проверьте свои знания!',
      'quiz_game_loading': 'Загрузка викторины...',
      'quiz_game_error': 'Ошибка загрузки викторины',
      'quiz_game_try_again': 'Попробовать снова',
      'quiz_game_start_quiz': 'Начать викторину',
      'quiz_game_which_sector': 'К какому сектору относится этот индикатор?',
      'quiz_game_which_subsector': 'К какому подсектору относится этот индикатор?',
      'quiz_game_definition': 'Определение',
      'quiz_game_no_definition': 'Определение недоступно',
      'quiz_game_correct': 'Правильно!',
      'quiz_game_incorrect': 'Неправильно',
      'quiz_game_next_question': 'Следующий вопрос',
      'quiz_game_view_results': 'Посмотреть результаты',
      'quiz_game_quiz_complete': 'Викторина завершена!',
      'quiz_game_excellent_work': 'Отличная работа!',
      'quiz_game_well_done': 'Молодец!',
      'quiz_game_good_effort': 'Хорошая попытка!',
      'quiz_game_keep_practicing': 'Продолжайте практиковаться!',
      'quiz_game_out_of': 'из',
      'quiz_game_statistics': 'Статистика',
      'quiz_game_correct_answers': 'Правильные',
      'quiz_game_incorrect_answers': 'Неправильные',
      'quiz_game_total': 'Всего',
      'quiz_game_home': 'Главная',
      'quiz_game_play_again': 'Играть снова',
      'quiz_game_no_indicators_available': 'Нет индикаторов с секторами или подсекторами для викторины',
      'quiz_game_failed_to_start': 'Не удалось запустить викторину',
      'quiz_game_leaderboard': 'Таблица лидеров',
      'quiz_game_view_leaderboard': 'Посмотреть таблицу лидеров',
      'quiz_game_loading_leaderboard': 'Загрузка таблицы лидеров...',
      'quiz_game_no_leaderboard_data': 'Данные таблицы лидеров пока недоступны',
      'quiz_game_top_players': 'Лучшие игроки',
      'quiz_game_you': 'Вы',
      'quiz_game_points': 'Очки',

      // AI Chat (immersive)
      'ai_policy_acknowledge_snackbar':
          'Подтвердите политику ИИ, чтобы продолжить.',
      'ai_use_policy_title': 'Политика использования ИИ',
      'ai_policy_do_not_share': 'Не делитесь конфиденциальной информацией.',
      'ai_policy_traces_body':
          'Мы используем системные следы и телеметрию для улучшения помощника. Ваши сообщения могут обрабатываться внешними поставщиками ИИ.',
      'ai_policy_purpose_title': 'Назначение',
      'ai_policy_purpose_body':
          'ИИ-помощник помогает изучать данные и документы на этой платформе. Он может отвечать на вопросы об индикаторах, странах, назначениях и искать в загруженных документах.',
      'ai_policy_acceptable_use_title': 'Допустимое использование',
      'ai_policy_acceptable_use_body':
          '• Спрашивайте о данных платформы, индикаторах и документах.\n'
          '• НЕ делитесь паролями, учётными данными или крайне конфиденциальными операционными сведениями.\n'
          '• НЕ вставляйте личные или финансовые данные.',
      'ai_policy_accuracy_title': 'Точность',
      'ai_policy_accuracy_body':
          'ИИ может ошибаться или неверно интерпретировать данные. Всегда проверяйте важную информацию по исходным данным или документам.',
      'ai_policy_confirm_footer':
          'Подтвердите, что вы прочитали информацию выше, чтобы использовать помощника.',
      'ai_policy_i_understand': 'Я понимаю',
      'ai_policy_acknowledge_cta': 'Подтвердить политику использования ИИ',
      'ai_sources_heading': 'Использовать источники:',
      'ai_source_databank': 'Банк данных',
      'ai_source_system_documents': 'Системные документы',
      'ai_source_upr_documents': 'Документы UPR',
      'ai_sources_minimum_note':
          'Как минимум один источник остаётся включённым (как в веб-помощнике).',
      'ai_tour_guide_question': 'Хотите, чтобы я провёл вас через это?',
      'ai_tour_navigate_question': 'Перейти на соответствующую страницу?',
      'ai_tour_web_only_snackbar':
          'Интерактивные туры доступны в веб-версии. Открываю страницу...',
      'ai_new_chat': 'Новый чат',
      'ai_semantic_open_drawer_hint': 'Открывает беседы и настройки',
      'ai_tooltip_new_chat': 'Новый чат',
      'ai_semantic_new_chat_label': 'Новый чат',
      'ai_semantic_new_chat_hint': 'Начинает новую пустую беседу',
      'ai_beta_tester_banner':
          'Бета-тестер ИИ — могут быть включены экспериментальные функции.',
      'ai_empty_welcome': 'Чем могу помочь сегодня?',
      'ai_policy_chip_title': 'Политика использования ИИ',
      'ai_policy_sheet_summary_line':
          'Краткое резюме — откройте панель для полных сведений.',
      'ai_policy_compact_warning':
          'Не делитесь конфиденциальной информацией. Мы используем следы и телеметрию для улучшения помощника; сообщения могут обрабатываться внешними поставщиками ИИ.',
      'ai_read_full_policy': 'Читать полную политику',
      'ai_try_asking': 'Попробуйте спросить',
      'ai_copied': 'Скопировано!',
      'ai_tooltip_copy': 'Копировать',
      'ai_tooltip_edit_message': 'Изменить',
      'ai_tooltip_helpful': 'Полезно',
      'ai_tooltip_not_helpful': 'Не полезно',
      'ai_footer_model_warning':
          'ИИ может ошибаться. Проверяйте важную информацию.',
      'ai_chat_error_network':
          'Не удалось подключиться к сервису ИИ. Проверьте подключение к интернету и повторите попытку.',
      'ai_chat_error_timeout':
          'Время ожидания запроса истекло. Проверьте соединение и повторите попытку.',
      'ai_chat_error_server': 'Что-то пошло не так. Повторите попытку.',
      'ai_agent_progress_title': 'Шаги выполняются',
      'ai_agent_step_done': 'Готово.',
      'ai_agent_step_preparing_query': 'Подготовка запроса…',
      'ai_agent_step_planning': 'Планирование подхода…',
      'ai_agent_step_reviewing': 'Проверка результатов…',
      'ai_agent_step_drafting': 'Формулировка ответа…',
      'ai_agent_step_replying': 'Ответ…',
      'ai_agent_step_thinking_next': 'Думаю, что делать дальше.',
      'ai_agent_step_no_shortcut_full':
          'Нет быстрого пути одним инструментом — полный цикл планирования.',
      'ai_agent_step_no_shortcut_reviewing':
          'Для этого запроса нет быстрого пути одним инструментом — проверка: %s',
      'ai_response_sources': 'Источники',
      'ai_response_sources_with_count': 'Источники (%s)',
      'ai_tooltip_configure_sources': 'Настроить источники данных',
      'ai_input_policy_required':
          'Подтвердите политику ИИ выше, чтобы отправлять сообщения',
      'ai_input_placeholder_message': 'Сообщение',
      'ai_input_placeholder_edit': 'Изменить сообщение…',
      'ai_tooltip_cancel_edit': 'Отменить правку',
      'ai_stop': 'Стоп',
      'ai_conversations_drawer_title': 'Беседы',
      'ai_search_conversations_hint': 'Поиск бесед',
      'ai_no_conversations_body':
          'Пока нет бесед.\nНачните новый чат!',
      'ai_no_conversations_offline':
          'Пока нет бесед.\nНачните новый чат (офлайн).',
      'ai_no_conversations_filtered': 'Беседы не найдены',
      'ai_section_pinned': 'Закреплённые',
      'ai_section_recent': 'Недавние',
      'ai_quick_prompt_1': 'Сколько добровольцев в Бангладеш?',
      'ai_quick_prompt_2': 'Добровольцы в Сирии со временем',
      'ai_quick_prompt_3': 'Тепловая карта добровольцев по странам',
      'ai_quick_prompt_4': 'Число отделений в Кении',
      'ai_quick_prompt_5': 'Персонал и местные подразделения в Нигерии',
      'ai_clear_all_dialog_title': 'Удалить все беседы',
      'ai_clear_all_dialog_body':
          'Удалить все беседы? Это действие нельзя отменить.',
      'ai_clear_all_button': 'Удалить всё',
      'ai_clear_all_row': 'Удалить все беседы',
      'ai_help_about_row': 'Справка и о приложении',
      'ai_pin': 'Закрепить',
      'ai_unpin': 'Открепить',
      'ai_delete_conversation_title': 'Удалить беседу?',
      'ai_delete_conversation_body':
          'Удалить эту беседу? Это нельзя отменить.',
      'ai_new_chat_title_fallback': 'Новый чат',
      'ai_help_dialog_title': 'Справка ИИ-помощника',
      'ai_help_about_heading': 'О помощнике',
      'ai_help_about_paragraph':
          'ИИ-помощник помогает находить информацию и отвечать на вопросы о Банке Данных Сети IFRC.',
      'ai_help_features_heading': 'Возможности',
      'ai_help_feature_bullet_1':
          '• Задавайте вопросы о назначениях, ресурсах и др.',
      'ai_help_feature_bullet_2': '• Получайте помощь в навигации по приложению',
      'ai_help_feature_bullet_3':
          '• Ищите в истории бесед',
      'ai_help_feature_bullet_4':
          '• Беседы сохраняются, когда вы вошли в аккаунт',
      'ai_help_tips_heading': 'Советы',
      'ai_help_tip_bullet_1':
          '• Формулируйте вопросы конкретно для лучших результатов',
      'ai_help_tip_bullet_2':
          '• Нажимайте ссылки в ответах для перехода на страницы',
      'ai_help_tip_bullet_3':
          '• Используйте строку поиска для быстрого поиска прошлых бесед',
      'ai_help_tip_bullet_4':
          '• Долгое нажатие на беседу открывает меню (закрепить или удалить)',
      'ai_got_it': 'Понятно',
      'ai_score_confidence': 'Уверенность',
      'ai_score_grounding': 'Обоснование',
      'ai_default_assistant_title': 'ИИ-помощник',
      'resources_other_subgroup': 'Прочее',
      'resources_list_truncated_hint':
          'Показаны самые последние материалы. Используйте поиск, чтобы найти конкретный документ.',
      'ai_assistant': 'ИИ-помощник',
    },
    'zh': {
      'app_name': 'IFRC网络数据库',
      'navigation': '导航',
      'home': '首页',
      'dashboard': '仪表板',
      'resources': '资源',
      'indicator_bank': '指标库',
      'disaggregation_analysis': '分类分析',
      'analysis': '分析',
      'data_visualization': '数据可视化',
      'settings': '设置',
      'notifications': '通知',
      'admin': '管理',
      'admin_panel': '管理面板',
      'customize_tabs': '自定义标签',
      'customize_tabs_description': '选择要显示的标签并拖动以重新排列。',
      'reset_to_default': '重置为默认',
      'tab_always_shown': '始终显示',
      'minimum_tabs_warning': '至少需要保留2个可见标签。',
      'access_denied': '访问被拒绝',
      'general': '常规',
      'document_management': '文档管理',
      'translation_management': '翻译管理',
      'plugin_management': '插件管理',
      'system_configuration': '系统配置',
      'user_management': '用户管理',
      'manage_users': '管理用户',
      'access_requests_title': '国家访问权限申请',
      'access_requests_subtitle': '批准或拒绝国家级访问权限申请。',
      'access_requests_pending': '待处理',
      'access_requests_processed': '最近处理结果',
      'access_requests_empty': '暂无访问申请。',
      'access_requests_approve': '批准',
      'access_requests_reject': '拒绝',
      'access_requests_approve_all': '全部批准',
      'access_requests_approve_all_confirm': '批准所有待处理的国家访问权限申请？',
      'access_requests_reject_confirm':
          '拒绝此访问申请？该用户将不会获得访问权限。',
      'access_requests_country': '国家',
      'access_requests_message': '留言',
      'access_requests_requested_at': '申请时间',
      'access_requests_processed_at': '处理时间',
      'access_requests_auto_approve_hint': '服务器设置中可能已启用自动批准。',
      'access_requests_status_pending': '待处理',
      'access_requests_status_approved': '已批准',
      'access_requests_status_rejected': '已拒绝',
      'access_requests_by': '由',
      'access_requests_load_failed': '无法加载访问申请。',
      'access_requests_action_failed': '无法完成操作。',
      'access_requests_view_forbidden': '您无权在服务器上查看访问申请。',
      'access_requests_unexpected_response': '服务器返回了意外响应。',
      'access_requests_action_forbidden': '您无权执行此操作。',
      'users_directory_read_only': '此列表为只读。请在网页管理后台创建或修改账户。',
      'login_logs_title': '登录日志',
      'login_logs_filters': '筛选',
      'login_logs_email_hint': '按邮箱搜索',
      'login_logs_event_type': '事件类型',
      'login_logs_event_all': '全部类型',
      'login_logs_event_login': '登录',
      'login_logs_event_logout': '登出',
      'login_logs_event_failed': '登录失败',
      'login_logs_ip_label': 'IP 地址',
      'login_logs_date_from': '开始日期',
      'login_logs_date_to': '结束日期',
      'login_logs_suspicious_only': '仅可疑',
      'login_logs_apply': '应用',
      'login_logs_clear': '清除',
      'login_logs_no_entries': '没有符合筛选条件的登录事件。',
      'login_logs_total': '共 %s 条事件',
      'login_logs_load_more': '加载更多',
      'login_logs_user_not_resolved': '无匹配用户账户',
      'login_logs_device': '设备',
      'login_logs_browser': '浏览器',
      'login_logs_suspicious_badge': '可疑',
      'login_logs_recent_failures': '最近失败 %s 次',
      'login_logs_open': '登录日志',
      'session_logs_title': '会话日志',
      'admin_filters': '筛选',
      'session_logs_email_hint': '按邮箱搜索',
      'session_logs_min_duration': '最少分钟（会话或活跃）',
      'session_logs_active_only': '仅活跃会话',
      'admin_filters_apply': '应用',
      'admin_filters_clear': '清除',
      'session_logs_no_entries': '没有符合筛选条件的会话。',
      'session_logs_total': '共 %s 个会话',
      'session_logs_load_more': '加载更多',
      'session_logs_session_start': '会话开始',
      'session_logs_duration': '时长',
      'session_logs_session_length': '会话时长',
      'session_logs_active_time': '活跃时长',
      'session_logs_minutes': '%s 分钟',
      'session_logs_page_views': '页面浏览',
      'session_logs_path_breakdown_title': '按路径的页面浏览',
      'session_logs_path_breakdown_open': '查看路径明细',
      'session_logs_path_breakdown_empty': '此会话未记录路径明细。',
      'session_logs_path_other_bucket': '其他路径（汇总）',
      'session_logs_path_column': '路径',
      'session_logs_path_count_column': '次数',
      'session_logs_distinct_paths': '不同路径数',
      'session_logs_activities': '活动',
      'session_logs_last_activity': '最后活动',
      'session_logs_status_active': '活跃',
      'session_logs_status_ended': '已结束',
      'session_logs_force_logout': '强制登出',
      'session_logs_force_logout_confirm': '强制登出该用户？将立即终止其会话。',
      'session_logs_unknown_user': '未知用户',
      'session_logs_no_activity': '无活动',
      'session_logs_open': '会话日志',
      'session_logs_ended_ok': '会话已结束。',
      'session_logs_os': '操作系统',
      'session_logs_user_agent': '用户代理',
      'session_logs_device_section': '设备详情',
      'form_data_management': '表单和数据管理',
      'manage_templates': '管理模板',
      'manage_assignments': '管理任务',
      'frontend_management': '前端管理',
      'manage_resources': '管理资源',
      'reference_data': '参考数据',
      'organizational_structure': '组织结构',
      'analytics_monitoring': '分析和监控',
      'user_analytics': '用户分析',
      'audit_trail': '审计跟踪',
      'api_management': 'API管理',
      'account_settings': '账户设置',
      'profile': '个人资料',
      'preferences': '偏好设置',
      'language': '语言',
      'select_language': '选择语言',
      'change_password': '更改密码',
      'profile_color': '个人资料颜色',
      'chatbot': '聊天机器人',
      'enable_chatbot_assistance': '启用聊天机器人协助',
      'dark_theme': '深色主题',
      'enable_dark_theme': '启用深色主题',
      'settings_theme': '主题',
      'light_theme': '浅色主题',
      'system_theme': '系统',
      'select_theme': '选择主题',
      'settings_theme_set_to': '主题已设为 %s',
      'arabic_text_font': '阿拉伯语文本字体',
      'arabic_font_tajawal': 'Tajawal',
      'arabic_font_system': '系统默认',
      'login_to_account': '登录账户',
      'logout': '登出',
      'are_you_sure_logout': '您确定要登出吗？',
      'cancel': '取消',
      'name': '姓名',
      'title': '职位',
      'email': '电子邮件',
      'loading': '加载中...',
      'loading_home': '加载首页...',
      'home_landing_hero_description':
          '探索来自红十字与红新月会国际联合会的综合人道主义数据、指标和见解。',
      'home_landing_chat_title': '与我们的数据聊天',
      'home_landing_chat_description': '在下面输入您关于平台数据的问题。',
      'home_landing_ask_placeholder': '询问资金、项目、国家...',
      'home_landing_quick_prompt_1': '告诉我关于阿富汗红新月会志愿者的情况',
      'home_landing_quick_prompt_2': '向我展示全球灾害响应数据',
      'home_landing_quick_prompt_3': '主要的人道主义指标是什么？',
      'home_landing_shortcuts_heading': '快速开始',
      'home_landing_shortcut_indicators_subtitle': '浏览定义和元数据',
      'home_landing_shortcut_resources_subtitle': '出版物与资料',
      'home_landing_shortcut_countries_subtitle': '国家概况与区域视图',
      'home_landing_shortcut_disaggregation_subtitle': '分解指标数值',
      'home_landing_explore_title': '全球地图与图表',
      'home_landing_explore_subtitle':
          '原生地图与图表，数据与网站 FDRS 汇总一致，无需离开应用。',
      'home_landing_global_indicator_volunteers': '志愿者',
      'home_landing_global_indicator_staff': '员工',
      'home_landing_global_indicator_branches': '分支机构',
      'home_landing_global_indicator_local_units': 'Local units',
      'home_landing_global_indicator_blood_donors': 'Blood donors',
      'home_landing_global_indicator_first_aid': 'First aid',
      'home_landing_global_indicator_people_reached': 'People reached',
      'home_landing_global_indicator_income': 'Income',
      'home_landing_global_indicator_expenditure': 'Expenditure',
      'home_landing_global_top_countries': '主要国家/地区',
      'home_landing_global_load_error':
          '无法加载地图数据。请检查网络连接后重试。',
      'home_landing_global_empty': '最新报告期没有该指标的数值。',
      'home_landing_global_period': '报告期：%s',
      'home_landing_global_map_hint': '双指缩放、拖动地图，点按国家查看详情',
      'home_landing_global_map_open_fullscreen': '全屏',
      'home_landing_global_period_filter_label': '报告期',
      'home_landing_global_map_mode_bubble': '气泡',
      'home_landing_global_map_mode_choropleth': '分级设色',
      'home_landing_global_map_zoom_in': '放大',
      'home_landing_global_map_zoom_out': '缩小',
      'home_landing_global_map_reset_bounds': '适配数据',
      'home_landing_global_map_legend_low': '低',
      'home_landing_global_map_legend_high': '高',
      'home_landing_global_map_country_no_data': '该指标暂无数据',
      'home_landing_global_map_value_label': '数值',
      'home_landing_global_map_country_trend': '按报告期',
      'home_landing_global_map_filters_title': '地图选项',
      'loading_page': '加载页面...',
      'loading_preferences': '加载首选项...',
      'loading_notifications': '加载通知...',
      'loading_dashboard': '加载仪表板...',
      'loading_audit_logs': '加载审计日志...',
      'loading_analytics': '加载分析...',
      'loading_organizations': '加载组织...',
      'loading_templates': '加载模板...',
      'loading_assignments': '加载任务...',
      'loading_translations': '加载翻译...',
      'loading_plugins': '加载插件...',
      'loading_resources': '加载资源...',
      'loading_indicators': '加载指标...',
      'loading_documents': '加载文档...',
      'loading_api_endpoints': '加载API端点...',
      'loading_users': '加载用户...',
      'error': '错误',
      'retry': '重试',
      'refresh': '刷新',
      'close': '关闭',
      'save': '保存',
      'saved': '已保存',
      'success': '成功',
      'oops_something_went_wrong': '糟糕！出了点问题',
      'go_back': '返回',
      'edit': '编辑',
      'duplicate': '复制',
      'preview': '预览',
      'download_started': '下载已开始',
      'could_not_start_download': '无法开始下载',
      'could_not_open_download_link': '无法打开下载链接',
      'error_opening_download': '打开下载时出错',
      'please_select_at_least_one_user': '请至少选择一个用户',
      'indicator_updated_successfully': '指标更新成功',
      'failed_to_load_indicator': '加载指标失败',
      'user_deleted': '用户已删除',
      'public_url_copied': '公共URL已复制到剪贴板！',
      'please_use_web_interface': '请使用Web界面保存实体更改',
      'open_in_web_browser': '在Web浏览器中打开',
      'countries': '国家',
      'all_roles': '所有角色',
      'admin_role': '管理员',
      'focal_point_role': '联络点',
      'system_manager_role': '系统管理员',
      'viewer_role': '查看者',
      'all_status': '所有状态',
      'active_status': '活跃',
      'inactive_status': '非活跃',
      'normal_priority': '普通',
      'high_priority': '高',
      'none': '无',
      'app_screen': '应用屏幕',
      'custom_url': '自定义URL',
      'create_template': '创建模板',
      'delete_template': '删除模板',
      'create_assignment': '创建任务',
      'delete_assignment': '删除任务',
      'edit_document': '编辑文档',
      'preview_document': '预览文档',
      'download_document': '下载文档',
      'upload_document': '上传文档',
      'new_translation': '新翻译',
      'new_resource': '新资源',
      'install_plugin': '安装插件',
      'template_deleted_successfully': '模板删除成功',
      'failed_to_delete_template': '删除模板失败',
      'error_loading_page': '加载页面时出错',
      'no_notifications': '没有通知',
      'all_caught_up': '您已全部看完',
      'notifications_load_more': '加载更多',
      'notifications_filter': '筛选',
      'notifications_filter_title': '筛选通知',
      'notifications_filter_read_status': '阅读状态',
      'notifications_filter_all': '全部',
      'notifications_filter_unread_only': '仅未读',
      'notifications_filter_type': '类型',
      'notifications_filter_type_any': '所有类型',
      'notifications_filter_from': '来自',
      'notifications_filter_from_any': '任何人',
      'notifications_filter_from_empty_hint':
          '当某人的通知出现在已加载列表中时，会显示在此处。请使用加载更多。',
      'notifications_filter_priority': '优先级',
      'notifications_filter_priority_any': '任意优先级',
      'notifications_filter_priority_normal': '普通',
      'notifications_filter_priority_high': '高',
      'notifications_filter_priority_urgent': '紧急',
      'notifications_filter_apply': '应用',
      'notifications_filter_reset': '全部重置',
      'notifications_filter_no_matches_loaded':
          '已加载列表中没有符合这些筛选条件的通知。请加载更多或调整筛选。',
      'mark_all_read': '全部标记为已读',
      'mark_read': '标记为已读',
      'mark_unread': '标记为未读',
      'delete': '删除',
      'archive': '归档',
      'unarchive': '取消归档',
      'send_push_notification': '发送推送通知',
      'admin_push_user_ids_label': '收件人用户 ID',
      'admin_push_user_ids_hint': '逗号分隔的数字 ID（可在用户管理中找到）。',
      'admin_push_user_ids_invalid': '请输入一个或多个数字用户 ID，以逗号分隔。',
      'select_users': '选择用户',
      'search_users': '按姓名或电子邮件搜索用户',
      'redirect_url': '重定向（可选）',
      'login': '登录',
      'log_in': '登录',
      'phone_username_email': '电话号码、用户名或电子邮件',
      'forgot_password_coming_soon': '忘记密码功能即将推出',
      'please_enter_email': '请输入您的电子邮件',
      'please_enter_valid_email': '请输入有效的电子邮件',
      'please_enter_password': '请输入您的密码',
      'show': '显示',
      'hide': '隐藏',
      'or': '或',
      'dont_have_account': '没有账户？',
      'sign_up': '注册',
      'registration_coming_soon': '注册功能即将推出',
      'quick_login_testing': '快速登录测试',
      'test_as_admin': '以管理员身份测试',
      'test_as_focal_point': '以联络点身份测试',
      'public_login_disabled': '公共登录已暂时禁用',
      'tester_accounts_info': '测试账户仍可使用上面的按钮登录。',
      'could_not_open_azure_login': '无法打开 Azure 登录',
      'login_with_ifrc_account': '使用 IFRC 帐户登录',
      'use_ifrc_federation_account': '使用您的 IFRC 联合会帐户登录',
      'your_account_or_create_account': '您的帐户或创建帐户',
      'login_failed': '登录失败',
      'email_address': '电子邮件地址',
      'password': '密码',
      'remember_me': '记住我',
      'forgot_password': '忘记密码？',
      'language_changed_to': '语言已更改为',

      // Splash Screen
      'welcome_to_ifrc_network_databank': '欢迎使用IFRC网络数据库',
      'splash_description':
          '这是向IFRC报告数据的唯一系统。告别分散的Excel文件、KoBo表单、多个平台和登录 — 现在一切都集中并简化在这里。',
      'powered_by_hum_databank': '由 Humanitarian Databank 提供支持',
      'open_on_github': '在 GitHub 上打开',

      // Dashboard
      'national_society': '国家协会',
      'active': '活跃',
      'completed': '已完成',
      'current_assignments': '当前任务',
      'dashboard_you_have_no_open_assignments': '您没有进行中的任务',
      'dashboard_you_have_one_open_assignment': '您有 1 个进行中的任务',
      'dashboard_you_have_open_assignments_count': '您有 %s 个进行中的任务',
      'past_assignments': '过往任务',
      'assignments_for': '的任务',
      'past_submissions_for': '的过往提交',
      'something_went_wrong': '出了点问题',
      'no_assignments_yet': '一切正常！目前没有活动任务。',
      'new_assignments_will_appear': '新任务在可用时会在此处显示。',
      'get_started_by_creating': '通过创建新任务开始',
      'filters': '筛选器',
      'period': '期间',
      'template': '模板',
      'status': '状态',
      'clear': '清除',
      'approved': '已批准',
      'requires_revision': '需要修订',
      'pending': '待处理',
      'in_progress': '进行中',
      'submitted': '已提交',
      'other': '其他',
      'entities': '实体',
      'search_placeholder': '搜索...',
      'no_results_found': '未找到结果',
      'entity_type_country': '国家',
      'entity_type_ns_branch': '国家协会分支',
      'entity_type_ns_sub_branch': '国家协会子分支',
      'entity_type_ns_local_unit': '国家协会地方单位',
      'entity_type_division': '部门',
      'entity_type_department': '科室',
      'delete_assignment_confirm_message':
          '您确定要删除此任务及其所有相关的国家状态和数据吗？',
      'no_assignments_match_filters': '没有任务匹配所选筛选器',
      'form': '表单',
      'last_updated': '最后更新',
      'actions': '操作',
      'all_years': '所有年份',
      'all_templates': '所有模板',
      'all_statuses': '所有状态',
      'template_missing': '模板缺失',
      'self_reported': '自我报告',
      'no_actions_available': '无可用操作',
      'previous': '上一页',
      'next': '下一页',
      'showing': '显示',
      'to': '至',
      'of': '共',
      'results': '结果',
      'no_past_assignments_for': '没有过往任务',
      'yet': '尚未',
      'submission_history_and_data_quality_for': '的提交历史和数据质量',
      'overall_performance': '整体表现',
      'average_completion_rate_past_3_periods': '平均完成率（过去3个期间）',
      'average_submission_timeliness': '平均提交及时性（提前/延迟天数）',
      'data_quality_index_fake_metric': '数据质量指数（虚假指标）',
      'number_of_revisions_requested_past_year': '请求修订次数（过去一年）',
      'trend_analysis': '趋势分析',
      'recent_activities': '最近活动',
      'last_7_days': '过去7天',
      'unknown_user': '未知用户',
      'added': '已添加',
      'updated': '已更新',
      'removed': '已删除',
      'show_less': '显示更少',
      'more_change': '更多更改',
      'no_recent_activities': '无最近活动',
      'activities_from_other_focal_points_in': '其他联络点的活动',
      'will_appear_here': '将出现在这里',
      'focal_points_for': '的联络点',
      'national_society_focal_points': '国家协会联络点',
      'ifrc_focal_points': 'IFRC联络点',
      'no_focal_points_assigned_to': '没有为以下分配的联络点',
      'your_user_account_not_associated': '您的用户账户未与任何国家关联',
      'please_contact_administrator': '请联系管理员',
      'due_date': '截止日期',
      'no_due_date': '无截止日期',
      'overdue': '逾期',
      'latest_submission': '最新提交',
      'submitted_through_public_link': '通过公开链接提交',
      'submission': '提交',
      'submissions': '提交',
      'completion': '完成',
      'received_1_submission_using_public_link': '通过公开链接收到1份提交',
      'received_count_submissions_using_public_link': '通过公开链接收到%(count)d份提交',
      'at_datetime': '于：%(datetime)s',
      'latest_datetime': '最新：%(datetime)s',
      'last_modified_by': '最后修改人',
      'assignment_assigned_date': '分配时间',
      'assignment_status_updated': '状态更新时间',
      'contributors': '贡献者',
      'assignment_submitted_by': '提交者',
      'assignment_approved_by': '审批者',
      'public_link_enabled': '公开链接已启用',
      'public_link': '公开链接',
      'unknown': '未知',
      'n_a': '不适用',
      'enter_data': '输入数据',
      'download_for_offline': '下载以供离线使用',
      'downloading_offline_form': '正在下载表单以供离线使用…',
      'offline_form_saved': '表单已保存，可离线访问。',
      'offline_form_save_failed': '无法离线保存表单。请在网络稳定时重试。',
      'offline_form_not_downloaded': '此表单无法离线使用。请在联网时下载。',
      'offline_download_requires_connection': '请连接互联网以下载此表单以供离线使用。',
      'offline_form_export_requires_connection':
          '请连接互联网以导出 PDF、Excel 或验证报告。离线副本不包含导出文件。',
      'offline_open_saved_copy': '打开已保存的离线副本',
      'remove_offline_copy': '删除离线副本',
      'offline_form_removed': '已删除离线副本。联网后请重新下载。',
      'offline_saved_copy_details_tooltip': '离线副本 — 详情与移除',
      'offline_copy_sheet_title': '离线表单副本',
      'offline_copy_saved_on_label': '保存时间',
      'offline_copy_files_cached': '已缓存 %(count)d 个资源',
      'offline_stale_bundle_banner_title': '离线表单需要更新',
      'offline_stale_bundle_banner_body_online':
          '在线表单已更改。联网时设备会自动刷新离线副本。若未成功，请点击带警告标记的表单并选择“更新离线副本”。',
      'offline_stale_bundle_banner_body_offline':
          '在线表单已更改。请连接互联网，以便设备自动刷新离线副本。',
      'offline_stale_bundle_updates_snackbar': '离线副本已更新到最新版本。',
      'offline_stale_bundle_partial_refresh':
          '部分离线副本未能更新。请点击表单上的警告标记，然后选择“更新离线副本”。',
      'offline_stale_bundle_sheet_notice':
          '此离线副本可能与当前在线表单不一致。请更新以避免版本问题。',
      'offline_stale_bundle_update_now': '更新离线副本',
      'approve': '批准',
      'reopen': '重新开放',
      'view_public_submissions': '查看公开提交',
      'view_submission': '查看提交',
      'view_submissions': '查看提交',
      'open_form': '打开表单',
      'no_forms_assigned_or_submitted_for': '没有为以下分配或通过公开链接提交的表单',
      'admins_can_assign_forms': '管理员可以通过管理仪表板分配表单或创建公开链接',
      'create_a_report': '创建报告',
      'delete_self_reported_assignment': '删除自我报告的任务',
      'quick_actions': '快速操作',
      'new_assignment': '新任务',
      'new_template': '新模板',
      'key_metrics': '关键指标',
      'overview': '概览',
      'create_new_assignment': '创建新任务',
      'browse_available_templates': '浏览可用模板',
      'enter_your_name': '输入您的姓名',
      'enter_your_job_title': '输入您的职位',
      'edit_name': '编辑姓名',
      'edit_title': '编辑职位',
      'name_cannot_be_empty': '姓名不能为空',
      'title_cannot_be_empty': '职位不能为空',
      'profile_updated_successfully': '个人资料更新成功',
      'error_updating_profile': '更新个人资料时出错',
      'color_picker_coming_soon': '颜色选择器即将推出',
      'chatbot_preference_update_coming_soon': '聊天机器人偏好更新即将推出',
      'select_color': '选择颜色',
      'current_color': '当前颜色',
      'profile_color_updated': '个人资料颜色更新成功',
      'profile_color_update_failed': '更新个人资料颜色失败',
      'admin_dashboard': '管理员仪表板',
      'no_data_available': '无可用数据',
      'total_users': '总用户数',
      'admins': '管理员',
      'system_administrators': '系统管理员',
      'focal_points': '联络点',
      'country_focal_points': '国家联络点',
      'form_templates': '表单模板',
      'active_assignments': '活动任务',
      'todays_logins': '今日登录',
      'successful_logins_today': '今日成功登录',
      'pending_submissions': '待提交',
      'overdue_assignments': '逾期任务',
      'security_alerts': '安全警报',
      'successful_logins': '成功登录',
      'user_activities': '用户活动',
      'active_sessions': '活动会话',
      'all_notifications_marked_as_read': '所有通知已标记为已读',
      'mark_as_read': '标记为已读',
      'mark_as_unread': '标记为未读',
      'notification_preferences': '通知偏好',
      'sound_notifications': '声音通知',
      'email_frequency': '电子邮件频率',
      'instant': '即时',
      'daily_digest': '每日摘要',
      'weekly_digest': '每周摘要',
      'digest_schedule': '摘要计划',
      'day_of_week': '星期几',
      'monday': '星期一',
      'tuesday': '星期二',
      'wednesday': '星期三',
      'thursday': '星期四',
      'friday': '星期五',
      'saturday': '星期六',
      'sunday': '星期日',
      'time_local_time': '时间（本地时间）',
      'notification_types': '通知类型',
      'preferences_saved_successfully': '偏好设置已成功保存',
      'enable_sound': '启用声音',
      'play_sound_for_new_notifications': '为新通知播放声音',
      'configure_notification_types_description': '配置要通过电子邮件和推送通知接收的通知类型',
      'notification_type': '通知类型',
      'push': '推送',
      'all': '全部',
      'save_preferences': '保存偏好设置',
      'select_digest_time_description': '选择您希望接收摘要的时间',
      'failed_to_save_preferences': '保存偏好设置失败',
      'assignment_created': '任务已创建',
      'assignment_submitted': '任务已提交',
      'assignment_approved': '任务已批准',
      'assignment_reopened': '任务已重新打开',
      'public_submission_received': '已收到公开提交',
      'form_updated': '表单已更新',
      'document_uploaded': '文档已上传',
      'user_added_to_country': '用户已添加到国家',
      'template_updated': '模板已更新',
      'self_report_created': '自报告已创建',
      'deadline_reminder': '截止日期提醒',
      'search_audit_logs': '搜索审计日志...',
      'home_screen_widget_title': '主屏幕小组件',
      'audit_widget_activity_types_hint':
          '选择要在小组件中显示的活动类型。不选则显示全部类型。已保存在本机。',
      'action': '操作',
      'all_actions': '所有操作',
      'create': '创建',
      'update': '更新',
      'user': '用户',
      'all_users': '所有用户',
      'from_date': '开始日期',
      'to_date': '结束日期',
      'select_date': '选择日期',
      'no_description': '无描述',
      'search_api_endpoints': '搜索API端点...',
      'http_method': 'HTTP方法',
      'all_methods': '所有方法',
      'get': 'GET',
      'post': 'POST',
      'put': 'PUT',
      'delete_method': 'DELETE',
      'deprecated': '已弃用',
      'beta': '测试版',
      'new_api_key': '新API密钥',
      'time_range': '时间范围',
      'last_30_days': '最近30天',
      'last_90_days': '最近90天',
      'last_year': '去年',
      'all_time': '全部时间',
      'metric': '指标',
      'all_metrics': '所有指标',
      'active_users': '活跃用户',
      'logins': '登录',
      'metric_submissions': '提交',
      'page_views': '页面浏览量',
      'search_indicators': '搜索指标...',
      'category': '类别',
      'all_categories': '所有类别',
      'output': '输出',
      'outcome': '结果',
      'impact': '影响',
      'all_sectors': '所有部门',
      'health': '健康',
      'wash': 'WASH',
      'shelter': '住所',
      'education': '教育',
      'indicators': '指标',
      'new_indicator': '新指标',
      'search_organizations': '搜索组织...',
      'entity_type': '实体类型',
      'all_types': '所有类型',
      'national_societies': '国家协会',
      'ns_structure': 'NS结构',
      'secretariat': '秘书处',
      'divisions': '部门',
      'departments': '处',
      'regional_offices': '区域办事处',
      'cluster_offices': '集群办事处',
      'add_organization': '添加组织',
      'search_resources': '搜索资源...',
      'no_indicators_found': '未找到指标',
      'no_organizations_found': '未找到组织',
      'no_resources_found': '未找到资源',
      'resources_unified_planning_section_title': '统一规划与报告',
      'resources_unified_planning_section_subtitle':
          '来自 IFRC GO 的计划、年中报告和年度报告（在应用中加载）。',
      'unified_planning_empty': '没有符合您搜索条件的统一规划文件。',
      'unified_planning_fresh_badge': '最新',
      'unified_planning_sort_by': '排序',
      'unified_planning_sort_date_newest': '发布日期：由新到旧',
      'unified_planning_sort_date_oldest': '发布日期：由旧到新',
      'unified_planning_sort_country_az': '国家/地区：A–Z',
      'unified_planning_sort_country_za': '国家/地区：Z–A',
      'unified_planning_filter_all_countries': '所有国家/地区',
      'unified_error_config': '无法从服务器加载统一规划设置。请稍后重试。',
      'unified_error_credentials':
          '此应用无法使用 IFRC 文档。请联系管理员。',
      'unified_error_ifrc_auth':
          '无法访问 IFRC 文档。若问题持续，请联系管理员。',
      'unified_error_ifrc': '无法从 IFRC GO 加载文档。请检查网络连接后重试。',
      'no_plugins_found': '未找到插件',
      'no_translations_found': '未找到翻译',
      'no_documents_found': '未找到文档',
      'no_users_found': '未找到用户',
      'loading_user_profile': '正在加载用户资料…',
      'failed_load_user_profile': '无法加载该用户。',
      'admin_user_detail_confirm_save_title': '保存更改？',
      'admin_user_detail_confirm_save_message':
          '更新该用户的姓名、职位、状态和资料偏好。',
      'admin_user_detail_invalid_profile_color':
          '请输入有效的 #RRGGBB 颜色（例如 #3B82F6）。',
      'admin_user_detail_changes_saved': '更改已保存。',
      'admin_user_detail_save_changes': '保存更改',
      'admin_user_detail_profile_color_label': '资料颜色',
      'admin_user_detail_profile_color_hint': '#RRGGBB',
      'admin_user_detail_cannot_deactivate_self': '您无法停用本人的帐户。',
      'admin_user_detail_matrix_read_only_bundled':
          '已打包的管理员角色（完整/核心/系统）— 请在网页后台调整各区域权限。',
      'admin_user_detail_rbac_incomplete': '无法生成有效的角色列表。请检查区域权限或重试。',
      'assigned_roles_title': '已分配角色',
      'role_type_label': '角色类型',
      'permissions_by_role': '按角色的权限',
      'all_permissions_union': '全部权限（来自角色）',
      'entity_permissions_title': '实体权限',
      'manage_users_detail_footer': '若要编辑角色、实体访问、设备或通知，请使用网页后台的用户表单。',
      'no_roles_assigned': '未分配 RBAC 角色。',
      'no_entities_assigned': '无实体分配。',
      'entity_permission_unnamed': '未命名',
      'entity_region_other': '其他区域',
      'no_permissions_listed': '此角色下列出的权限为空。',
      'user_dir_assignment_roles': '任务角色',
      'user_dir_admin_roles': '管理与系统',
      'user_dir_other_roles': '其他角色',
      'admin_role_access_area': '范围',
      'admin_role_access_view': '查看',
      'admin_role_access_manage': '管理',
      'admin_role_de_heading': '数据探索',
      'admin_role_de_table': '数据表',
      'admin_role_de_analysis': '分析',
      'admin_role_de_compliance': '合规',
      'admin_role_note_admin_full': '全部管理权限（组合角色）',
      'admin_role_note_admin_core': '核心管理权限（组合角色）',
      'admin_role_other_admin_roles': '其他管理角色',
      'users_directory_role_all': '全部角色',
      'users_directory_country_all': '全部国家',
      'no_assignments_found': '未找到任务',
      'no_templates_found': '未找到模板',
      'assignment_deleted_successfully': '任务已成功删除',
      'failed_to_delete_assignment': '删除任务失败',
      'timeline_view': '时间线视图',
      'view_all_public_submissions': '查看所有公开提交',
      'items_requiring_attention': '需要关注的项目',
      'recent_activity': '最近活动',
      'recent_activity_7_days': '最近活动（7天）',
      'general_settings': '常规设置',
      'security_settings': '安全设置',
      'system_settings': '系统设置',
      'application_settings': '应用程序设置',
      'language_settings': '语言设置',
      'notification_settings': '通知设置',
      'authentication_settings': '身份验证设置',
      'permission_settings': '权限设置',
      'database_settings': '数据库设置',
      'cloud_storage_settings': '云存储设置',
      'configure_general_application_settings': '配置常规应用程序设置',
      'manage_supported_languages_and_translations': '管理支持的语言和翻译',
      'configure_notification_preferences': '配置通知首选项',
      'configure_authentication_and_authorization': '配置身份验证和授权',
      'manage_user_permissions_and_roles': '管理用户权限和角色',
      'configure_database_connections_and_backups': '配置数据库连接和备份',
      'configure_cloud_storage_and_file_management': '配置云存储和文件管理',

      // Indicator Bank
      'indicator_bank_title': '指标库',
      'indicator_bank_loading': '正在加载指标库...',
      'indicator_bank_error': '出了点问题',
      'indicator_bank_search_placeholder': '搜索指标...',
      'indicator_bank_filter_placeholder': '筛选指标...',
      'indicator_bank_browse_description': '浏览和搜索人道主义响应指标',
      'indicator_bank_grid_view': '网格视图',
      'indicator_bank_table_view': '表格视图',
      'indicator_bank_show_filters': '显示筛选器',
      'indicator_bank_hide_filters': '隐藏筛选器',
      'indicator_bank_filters': '筛选器',
      'indicator_bank_filter_type': '类型',
      'indicator_bank_filter_type_all': '所有类型',
      'indicator_bank_filter_sector': '部门',
      'indicator_bank_filter_sector_all': '所有部门',
      'indicator_bank_filter_subsector': '子部门',
      'indicator_bank_filter_subsector_all': '所有子部门',
      'indicator_bank_list_tier_also_related': '亦相关',
      'indicator_bank_filter_status': '状态',
      'indicator_bank_filter_status_active': '仅活跃',
      'indicator_bank_filter_status_all': '全部',
      'indicator_bank_apply_filters': '应用筛选器',
      'indicator_bank_clear_all': '清除全部',
      'indicator_bank_showing': '显示',
      'indicator_bank_indicators': '个指标',
      'indicator_bank_indicator': '个指标',
      'indicator_bank_no_sectors': '未找到部门',
      'indicator_bank_no_indicators': '未找到指标',
      'indicator_bank_table_name': '名称',
      'indicator_bank_table_type': '类型',
      'indicator_bank_table_sector': '部门',
      'indicator_bank_table_subsector': '子部门',
      'indicator_bank_table_unit': '单位',
      'indicator_bank_propose_new': '提议新指标',
      'indicator_bank_propose_title': '提议新指标',
      'indicator_bank_propose_contact_info': '联系信息',
      'indicator_bank_propose_your_name': '您的姓名 *',
      'indicator_bank_propose_email': '电子邮件地址 *',
      'indicator_bank_propose_indicator_info': '指标信息',
      'indicator_bank_propose_indicator_name': '指标名称 *',
      'indicator_bank_propose_definition': '定义 *',
      'indicator_bank_propose_type': '类型',
      'indicator_bank_propose_unit': '测量单位',
      'indicator_bank_propose_sector': '部门',
      'indicator_bank_propose_primary_sector': '主要部门 *',
      'indicator_bank_propose_secondary_sector': '次要部门',
      'indicator_bank_propose_tertiary_sector': '第三部门',
      'indicator_bank_propose_subsector': '子部门',
      'indicator_bank_propose_primary_subsector': '主要子部门 *',
      'indicator_bank_propose_secondary_subsector': '次要子部门',
      'indicator_bank_propose_tertiary_subsector': '第三子部门',
      'indicator_bank_propose_emergency': '紧急情况',
      'indicator_bank_propose_related_programs': '相关计划',
      'indicator_bank_propose_reason': '提议原因 *',
      'indicator_bank_propose_additional_notes': '附加说明',
      'indicator_bank_propose_submit': '提交提议',
      'indicator_bank_propose_thank_you': '谢谢！',
      'indicator_bank_propose_success': '您的指标提议已成功提交。',
      'indicator_bank_propose_failed': '提交提议失败。请重试。',
      'indicator_bank_name_required': '姓名是必填项',
      'indicator_bank_email_required': '电子邮件是必填项',
      'indicator_bank_indicator_name_required': '指标名称是必填项',
      'indicator_bank_definition_required': '定义是必填项',
      'indicator_bank_primary_sector_required': '主要部门是必填项',
      'indicator_bank_primary_subsector_required': '主要子部门是必填项',
      'indicator_bank_reason_required': '原因是必填项',

      // Indicator Detail
      'indicator_detail_title': '指标详情',
      'indicator_detail_loading': '正在加载指标详情...',
      'indicator_detail_error': '出了点问题',
      'indicator_detail_not_found': '未找到指标',
      'indicator_detail_go_back': '返回',
      'indicator_detail_definition': '定义',
      'indicator_detail_details': '详情',
      'indicator_detail_type': '类型',
      'indicator_detail_unit': '单位',
      'indicator_detail_sector': '部门',
      'indicator_detail_subsector': '子部门',
      'indicator_detail_emergency_context': '紧急情况',
      'indicator_detail_related_programs': '相关计划',
      'indicator_detail_status': '状态',
      'indicator_detail_archived': '已归档',
      'indicator_detail_yes': '是',
      'editIndicator': '编辑指标',

      // Quiz Game
      'quiz_game': '测验游戏',
      'quiz_game_title': '测验游戏',
      'quiz_game_test_your_knowledge': '测试你的知识！',
      'quiz_game_loading': '加载测验...',
      'quiz_game_error': '加载测验时出错',
      'quiz_game_try_again': '重试',
      'quiz_game_start_quiz': '开始测验',
      'quiz_game_which_sector': '此指标属于哪个部门？',
      'quiz_game_which_subsector': '此指标属于哪个子部门？',
      'quiz_game_definition': '定义',
      'quiz_game_no_definition': '无可用定义',
      'quiz_game_correct': '正确！',
      'quiz_game_incorrect': '错误',
      'quiz_game_next_question': '下一题',
      'quiz_game_view_results': '查看结果',
      'quiz_game_quiz_complete': '测验完成！',
      'quiz_game_excellent_work': '出色的工作！',
      'quiz_game_well_done': '做得好！',
      'quiz_game_good_effort': '不错的努力！',
      'quiz_game_keep_practicing': '继续练习！',
      'quiz_game_out_of': '共',
      'quiz_game_statistics': '统计',
      'quiz_game_correct_answers': '正确',
      'quiz_game_incorrect_answers': '错误',
      'quiz_game_total': '总计',
      'quiz_game_home': '首页',
      'quiz_game_play_again': '再玩一次',
      'quiz_game_no_indicators_available': '没有可用于测验的带部门或子部门的指标',
      'quiz_game_failed_to_start': '启动测验失败',
      'quiz_game_leaderboard': '排行榜',
      'quiz_game_view_leaderboard': '查看排行榜',
      'quiz_game_loading_leaderboard': '加载排行榜...',
      'quiz_game_no_leaderboard_data': '暂无排行榜数据',
      'quiz_game_top_players': '顶级玩家',
      'quiz_game_you': '你',
      'quiz_game_points': '积分',

      // AI Chat (immersive)
      'ai_policy_acknowledge_snackbar':
          '请确认 AI 使用政策以继续。',
      'ai_use_policy_title': 'AI 使用政策',
      'ai_policy_do_not_share': '请勿分享敏感信息。',
      'ai_policy_traces_body':
          '我们使用系统跟踪和遥测来改进助手。您的消息可能会由外部 AI 提供商处理。',
      'ai_policy_purpose_title': '用途',
      'ai_policy_purpose_body':
          'AI 助手帮助您浏览本平台上的数据和文档。它可以回答关于指标、国家、任务的问题，并搜索已上传的文档。',
      'ai_policy_acceptable_use_title': '可接受的使用',
      'ai_policy_acceptable_use_body':
          '• 可询问平台数据、指标和文档。\n'
          '• 请勿分享密码、凭据或高度机密的运营细节。\n'
          '• 请勿粘贴个人或财务数据。',
      'ai_policy_accuracy_title': '准确性',
      'ai_policy_accuracy_body':
          'AI 可能出错或误解数据。请务必对照原始数据或文档核实重要信息。',
      'ai_policy_confirm_footer':
          '确认您已阅读上述信息后再使用助手。',
      'ai_policy_i_understand': '我理解',
      'ai_policy_acknowledge_cta': '确认 AI 使用政策',
      'ai_sources_heading': '使用来源：',
      'ai_source_databank': '数据库',
      'ai_source_system_documents': '系统文档',
      'ai_source_upr_documents': 'UPR 文档',
      'ai_sources_minimum_note':
          '至少保留一个来源启用（与网页版助手相同）。',
      'ai_tour_guide_question': '需要我带您了解吗？',
      'ai_tour_navigate_question': '要前往相关页面吗？',
      'ai_tour_web_only_snackbar':
          '交互式导览仅在网页版提供。正在打开页面…',
      'ai_new_chat': '新对话',
      'ai_semantic_open_drawer_hint': '打开对话和设置',
      'ai_tooltip_new_chat': '新对话',
      'ai_semantic_new_chat_label': '新对话',
      'ai_semantic_new_chat_hint': '开始新的空白对话',
      'ai_beta_tester_banner':
          'AI 内测用户 — 可能启用实验性功能。',
      'ai_empty_welcome': '今天我能为您做什么？',
      'ai_policy_chip_title': 'AI 使用政策',
      'ai_policy_sheet_summary_line':
          '简要摘要 — 打开面板查看完整详情。',
      'ai_policy_compact_warning':
          '请勿分享敏感信息。我们使用跟踪和遥测改进助手；消息可能由外部 AI 提供商处理。',
      'ai_read_full_policy': '阅读完整政策',
      'ai_try_asking': '试着问问',
      'ai_copied': '已复制！',
      'ai_tooltip_copy': '复制',
      'ai_tooltip_edit_message': '编辑',
      'ai_tooltip_helpful': '有帮助',
      'ai_tooltip_not_helpful': '没有帮助',
      'ai_footer_model_warning':
          'AI 可能出错。请核实重要信息。',
      'ai_chat_error_network': '无法连接到 AI 服务。请检查网络连接后重试。',
      'ai_chat_error_timeout': '请求超时。请检查连接后重试。',
      'ai_chat_error_server': '出了点问题。请重试。',
      'ai_agent_progress_title': '进行中的步骤',
      'ai_agent_step_done': '完成。',
      'ai_agent_step_preparing_query': '正在准备查询…',
      'ai_agent_step_planning': '正在规划方案…',
      'ai_agent_step_reviewing': '正在查看结果…',
      'ai_agent_step_drafting': '正在起草回复…',
      'ai_agent_step_replying': '正在回复…',
      'ai_agent_step_thinking_next': '正在思考接下来该怎么做。',
      'ai_agent_step_no_shortcut_full': '无单工具捷径 — 使用完整规划流程。',
      'ai_agent_step_no_shortcut_reviewing': '此请求无单工具捷径 — 正在审核：%s',
      'ai_response_sources': '来源',
      'ai_response_sources_with_count': '来源（%s）',
      'ai_tooltip_configure_sources': '配置数据来源',
      'ai_input_policy_required':
          '请先确认上方的 AI 政策再发送消息',
      'ai_input_placeholder_message': '消息',
      'ai_input_placeholder_edit': '编辑消息…',
      'ai_tooltip_cancel_edit': '取消编辑',
      'ai_stop': '停止',
      'ai_conversations_drawer_title': '对话',
      'ai_search_conversations_hint': '搜索对话',
      'ai_no_conversations_body':
          '还没有对话。\n开始新聊天！',
      'ai_no_conversations_offline':
          '还没有对话。\n开始新聊天（离线）。',
      'ai_no_conversations_filtered': '未找到对话',
      'ai_section_pinned': '已固定',
      'ai_section_recent': '最近',
      'ai_quick_prompt_1': '孟加拉国有多少志愿者？',
      'ai_quick_prompt_2': '叙利亚志愿者随时间变化',
      'ai_quick_prompt_3': '各国志愿者的世界热力图',
      'ai_quick_prompt_4': '肯尼亚分支机构数量',
      'ai_quick_prompt_5': '尼日利亚的员工与地方单位',
      'ai_clear_all_dialog_title': '清除所有对话',
      'ai_clear_all_dialog_body':
          '确定要删除所有对话吗？此操作无法撤销。',
      'ai_clear_all_button': '全部清除',
      'ai_clear_all_row': '清除所有对话',
      'ai_help_about_row': '帮助与关于',
      'ai_pin': '固定',
      'ai_unpin': '取消固定',
      'ai_delete_conversation_title': '删除对话？',
      'ai_delete_conversation_body':
          '删除此对话？无法撤销。',
      'ai_new_chat_title_fallback': '新对话',
      'ai_help_dialog_title': 'AI 助手帮助',
      'ai_help_about_heading': '关于',
      'ai_help_about_paragraph':
          'AI 助手帮助您查找信息并回答关于 IFRC 网络数据库的问题。',
      'ai_help_features_heading': '功能',
      'ai_help_feature_bullet_1':
          '• 询问任务、资源等问题',
      'ai_help_feature_bullet_2': '• 获取应用导航帮助',
      'ai_help_feature_bullet_3':
          '• 搜索对话历史',
      'ai_help_feature_bullet_4':
          '• 登录后对话会保存',
      'ai_help_tips_heading': '提示',
      'ai_help_tip_bullet_1':
          '• 提问越具体，结果越好',
      'ai_help_tip_bullet_2':
          '• 点击回复中的链接前往相关页面',
      'ai_help_tip_bullet_3':
          '• 使用搜索栏快速查找过往对话',
      'ai_help_tip_bullet_4':
          '• 长按对话可打开菜单（固定或删除）',
      'ai_got_it': '知道了',
      'ai_score_confidence': '置信度',
      'ai_score_grounding': '依据度',
      'ai_default_assistant_title': 'AI 助手',
      'resources_other_subgroup': '其他',
      'resources_list_truncated_hint':
          '仅显示最近的项目。请使用搜索查找特定文档。',
      'ai_assistant': 'AI 助手',
    },
  };

  String translate(String key) {
    final translations =
        _translations[locale.languageCode] ?? _translations['en']!;
    final en = _translations['en']!;
    return translations[key] ?? en[key] ?? key;
  }

  // Convenience getters
  String get appName => translate('app_name');
  String get navigation => translate('navigation');
  String get home => translate('home');
  String get dashboard => translate('dashboard');
  String get resources => translate('resources');
  String get indicatorBank => translate('indicator_bank');
  String get disaggregationAnalysis => translate('disaggregation_analysis');
  String get analysis => translate('analysis');
  String get dataVisualization => translate('data_visualization');
  // Convenience getters for snake_case keys (used in some screens)
  String get indicator_bank => indicatorBank;
  String get disaggregation_analysis => disaggregationAnalysis;
  String get settings => translate('settings');
  String get notifications => translate('notifications');
  String get admin => translate('admin');
  String get adminPanel => translate('admin_panel');
  String get customizeTabs => translate('customize_tabs');
  String get customizeTabsDescription => translate('customize_tabs_description');
  String get resetToDefault => translate('reset_to_default');
  String get tabAlwaysShown => translate('tab_always_shown');
  String get minimumTabsWarning => translate('minimum_tabs_warning');
  String get accessDenied => translate('access_denied');
  String get general => translate('general');
  String get documentManagement => translate('document_management');
  String get translationManagement => translate('translation_management');
  String get pluginManagement => translate('plugin_management');
  String get systemConfiguration => translate('system_configuration');
  String get userManagement => translate('user_management');
  String get manageUsers => translate('manage_users');

  String get accessRequestsTitle => translate('access_requests_title');
  String get accessRequestsSubtitle => translate('access_requests_subtitle');
  String get accessRequestsPending => translate('access_requests_pending');
  String get accessRequestsProcessed => translate('access_requests_processed');
  String get accessRequestsEmpty => translate('access_requests_empty');
  String get accessRequestsApprove => translate('access_requests_approve');
  String get accessRequestsReject => translate('access_requests_reject');
  String get accessRequestsApproveAll => translate('access_requests_approve_all');
  String get accessRequestsApproveAllConfirm =>
      translate('access_requests_approve_all_confirm');
  String get accessRequestsRejectConfirm =>
      translate('access_requests_reject_confirm');
  String get accessRequestsCountry => translate('access_requests_country');
  String get accessRequestsMessage => translate('access_requests_message');
  String get accessRequestsRequestedAt =>
      translate('access_requests_requested_at');
  String get accessRequestsProcessedAt =>
      translate('access_requests_processed_at');
  String get accessRequestsAutoApproveHint =>
      translate('access_requests_auto_approve_hint');
  String get accessRequestsStatusPending =>
      translate('access_requests_status_pending');
  String get accessRequestsStatusApproved =>
      translate('access_requests_status_approved');
  String get accessRequestsStatusRejected =>
      translate('access_requests_status_rejected');
  String get accessRequestsBy => translate('access_requests_by');
  String get accessRequestsLoadFailed =>
      translate('access_requests_load_failed');
  String get accessRequestsActionFailed =>
      translate('access_requests_action_failed');
  String get accessRequestsViewForbidden =>
      translate('access_requests_view_forbidden');
  String get accessRequestsUnexpectedResponse =>
      translate('access_requests_unexpected_response');
  String get accessRequestsActionForbidden =>
      translate('access_requests_action_forbidden');

  String get loginLogsTitle => translate('login_logs_title');
  String get loginLogsFilters => translate('login_logs_filters');
  String get loginLogsEmailHint => translate('login_logs_email_hint');
  String get loginLogsEventType => translate('login_logs_event_type');
  String get loginLogsEventAll => translate('login_logs_event_all');
  String get loginLogsEventLogin => translate('login_logs_event_login');
  String get loginLogsEventLogout => translate('login_logs_event_logout');
  String get loginLogsEventFailed => translate('login_logs_event_failed');
  String get loginLogsIpLabel => translate('login_logs_ip_label');
  String get loginLogsDateFrom => translate('login_logs_date_from');
  String get loginLogsDateTo => translate('login_logs_date_to');
  String get loginLogsSuspiciousOnly => translate('login_logs_suspicious_only');
  String get loginLogsApply => translate('login_logs_apply');
  String get loginLogsClear => translate('login_logs_clear');
  String get loginLogsNoEntries => translate('login_logs_no_entries');
  String get loginLogsLoadMore => translate('login_logs_load_more');
  String get loginLogsUserNotResolved => translate('login_logs_user_not_resolved');
  String get loginLogsDevice => translate('login_logs_device');
  String get loginLogsBrowser => translate('login_logs_browser');
  String get loginLogsSuspiciousBadge => translate('login_logs_suspicious_badge');
  String get loginLogsOpen => translate('login_logs_open');

  String loginLogsTotalCount(int total) =>
      translate('login_logs_total').replaceAll('%s', '$total');

  String loginLogsRecentFailures(int n) =>
      translate('login_logs_recent_failures').replaceAll('%s', '$n');

  String get sessionLogsTitle => translate('session_logs_title');
  String get adminFilters => translate('admin_filters');
  String get sessionLogsEmailHint => translate('session_logs_email_hint');
  String get sessionLogsMinDuration => translate('session_logs_min_duration');
  String get sessionLogsActiveOnly => translate('session_logs_active_only');
  String get adminFiltersApply => translate('admin_filters_apply');
  String get adminFiltersClear => translate('admin_filters_clear');
  String get sessionLogsNoEntries => translate('session_logs_no_entries');
  String get sessionLogsLoadMore => translate('session_logs_load_more');
  String get sessionLogsSessionStart => translate('session_logs_session_start');
  String get sessionLogsDuration => translate('session_logs_duration');
  String get sessionLogsSessionLength => translate('session_logs_session_length');
  String get sessionLogsActiveTime => translate('session_logs_active_time');
  String get sessionLogsPageViews => translate('session_logs_page_views');
  String get sessionLogsPathBreakdownTitle =>
      translate('session_logs_path_breakdown_title');
  String get sessionLogsPathBreakdownOpen =>
      translate('session_logs_path_breakdown_open');
  String get sessionLogsPathBreakdownEmpty =>
      translate('session_logs_path_breakdown_empty');
  String get sessionLogsPathOtherBucket =>
      translate('session_logs_path_other_bucket');
  String get sessionLogsPathColumn => translate('session_logs_path_column');
  String get sessionLogsPathCountColumn =>
      translate('session_logs_path_count_column');
  String get sessionLogsDistinctPaths => translate('session_logs_distinct_paths');
  String get sessionLogsActivities => translate('session_logs_activities');
  String get sessionLogsLastActivity => translate('session_logs_last_activity');
  String get sessionLogsStatusActive => translate('session_logs_status_active');
  String get sessionLogsStatusEnded => translate('session_logs_status_ended');
  String get sessionLogsForceLogout => translate('session_logs_force_logout');
  String get sessionLogsForceLogoutConfirm =>
      translate('session_logs_force_logout_confirm');
  String get sessionLogsUnknownUser => translate('session_logs_unknown_user');
  String get sessionLogsNoActivity => translate('session_logs_no_activity');
  String get sessionLogsOpen => translate('session_logs_open');
  String get sessionLogsEndedOk => translate('session_logs_ended_ok');
  String get sessionLogsOs => translate('session_logs_os');
  String get sessionLogsUserAgent => translate('session_logs_user_agent');
  String get sessionLogsDeviceSection => translate('session_logs_device_section');

  String sessionLogsTotalCount(int total) =>
      translate('session_logs_total').replaceAll('%s', '$total');

  String sessionLogsMinutes(int m) =>
      translate('session_logs_minutes').replaceAll('%s', '$m');

  String get usersDirectoryReadOnly => translate('users_directory_read_only');
  String get formDataManagement => translate('form_data_management');
  String get manageTemplates => translate('manage_templates');
  String get manageAssignments => translate('manage_assignments');
  String get assignmentDetails => translate('assignment_details');
  String get assignmentReportingPeriod =>
      translate('assignment_reporting_period');
  String get assignmentTemplateId => translate('assignment_template_id');
  String get assignmentHasPublicLink =>
      translate('assignment_has_public_link');
  String get assignmentDetailMissingData =>
      translate('assignment_detail_missing_data');
  String get copyLink => translate('copy_link');
  String get assignmentScheduleSection =>
      translate('assignment_schedule_section');
  String get assignmentStateSection => translate('assignment_state_section');
  String get assignmentExpiryDate => translate('assignment_expiry_date');
  String get assignmentEarliestEntityDue =>
      translate('assignment_earliest_entity_due');
  String get assignmentMultipleDueDatesHint =>
      translate('assignment_multiple_due_dates_hint');
  String get assignmentFlagActive => translate('assignment_flag_active');
  String get assignmentFlagClosed => translate('assignment_flag_closed');
  String get assignmentFlagEffectiveClosed =>
      translate('assignment_flag_effective_closed');
  String get assignmentLoadDetailFailed =>
      translate('assignment_load_detail_failed');
  String get assignmentClosed => translate('assignment_closed');
  String get assignmentOpen => translate('assignment_open');
  String get entityPublicReporting => translate('entity_public_reporting');
  String get entitySubmittedAt => translate('entity_submitted_at');
  String get frontendManagement => translate('frontend_management');
  String get manageResources => translate('manage_resources');
  String get referenceData => translate('reference_data');
  String get organizationalStructure => translate('organizational_structure');
  String get analyticsMonitoring => translate('analytics_monitoring');
  String get userAnalytics => translate('user_analytics');
  String get auditTrail => translate('audit_trail');
  String get apiManagement => translate('api_management');
  String get accountSettings => translate('account_settings');
  String get profile => translate('profile');
  String get preferences => translate('preferences');
  String get language => translate('language');
  String get selectLanguage => translate('select_language');
  String get changePassword => translate('change_password');
  String get profileColor => translate('profile_color');
  String get chatbot => translate('chatbot');
  String get enableChatbotAssistance => translate('enable_chatbot_assistance');
  String get darkTheme => translate('dark_theme');
  String get enableDarkTheme => translate('enable_dark_theme');
  String get settingsTheme => translate('settings_theme');
  String get lightTheme => translate('light_theme');
  String get systemTheme => translate('system_theme');
  String get selectTheme => translate('select_theme');
  String get arabicTextFont => translate('arabic_text_font');
  String get arabicFontTajawal => translate('arabic_font_tajawal');
  String get arabicFontSystem => translate('arabic_font_system');
  String get loginToAccount => translate('login_to_account');
  String get logout => translate('logout');
  String get areYouSureLogout => translate('are_you_sure_logout');
  String get cancel => translate('cancel');
  String get name => translate('name');
  String get title => translate('title');
  String get email => translate('email');
  String get loading => translate('loading');
  String get loadingHome => translate('loading_home');
  String get homeLandingHeroDescription => translate('home_landing_hero_description');
  String get homeLandingChatTitle => translate('home_landing_chat_title');
  String get homeLandingChatDescription => translate('home_landing_chat_description');
  String get homeLandingAskPlaceholder => translate('home_landing_ask_placeholder');
  String get homeLandingQuickPrompt1 => translate('home_landing_quick_prompt_1');
  String get homeLandingQuickPrompt2 => translate('home_landing_quick_prompt_2');
  String get homeLandingQuickPrompt3 => translate('home_landing_quick_prompt_3');
  String get homeLandingShortcutsHeading => translate('home_landing_shortcuts_heading');
  String get homeLandingShortcutIndicatorsSubtitle =>
      translate('home_landing_shortcut_indicators_subtitle');
  String get homeLandingShortcutResourcesSubtitle =>
      translate('home_landing_shortcut_resources_subtitle');
  String get homeLandingShortcutCountriesSubtitle =>
      translate('home_landing_shortcut_countries_subtitle');
  String get homeLandingShortcutDisaggregationSubtitle =>
      translate('home_landing_shortcut_disaggregation_subtitle');
  String get homeLandingExploreTitle => translate('home_landing_explore_title');
  String get homeLandingExploreSubtitle => translate('home_landing_explore_subtitle');
  String get homeLandingGlobalIndicatorVolunteers =>
      translate('home_landing_global_indicator_volunteers');
  String get homeLandingGlobalIndicatorStaff =>
      translate('home_landing_global_indicator_staff');
  String get homeLandingGlobalIndicatorBranches =>
      translate('home_landing_global_indicator_branches');
  String get homeLandingGlobalIndicatorLocalUnits =>
      translate('home_landing_global_indicator_local_units');
  String get homeLandingGlobalIndicatorBloodDonors =>
      translate('home_landing_global_indicator_blood_donors');
  String get homeLandingGlobalIndicatorFirstAid =>
      translate('home_landing_global_indicator_first_aid');
  String get homeLandingGlobalIndicatorPeopleReached =>
      translate('home_landing_global_indicator_people_reached');
  String get homeLandingGlobalIndicatorIncome =>
      translate('home_landing_global_indicator_income');
  String get homeLandingGlobalIndicatorExpenditure =>
      translate('home_landing_global_indicator_expenditure');
  String get homeLandingGlobalTopCountries =>
      translate('home_landing_global_top_countries');
  String get homeLandingGlobalLoadError =>
      translate('home_landing_global_load_error');
  String get homeLandingGlobalEmpty => translate('home_landing_global_empty');
  String get homeLandingGlobalMapHint =>
      translate('home_landing_global_map_hint');
  String get homeLandingGlobalMapOpenFullscreen =>
      translate('home_landing_global_map_open_fullscreen');
  String get homeLandingGlobalPeriodFilterLabel =>
      translate('home_landing_global_period_filter_label');
  String get homeLandingGlobalMapModeBubble =>
      translate('home_landing_global_map_mode_bubble');
  String get homeLandingGlobalMapModeChoropleth =>
      translate('home_landing_global_map_mode_choropleth');
  String get homeLandingGlobalMapZoomIn =>
      translate('home_landing_global_map_zoom_in');
  String get homeLandingGlobalMapZoomOut =>
      translate('home_landing_global_map_zoom_out');
  String get homeLandingGlobalMapResetBounds =>
      translate('home_landing_global_map_reset_bounds');
  String get homeLandingGlobalMapLegendLow =>
      translate('home_landing_global_map_legend_low');
  String get homeLandingGlobalMapLegendHigh =>
      translate('home_landing_global_map_legend_high');
  String get homeLandingGlobalMapCountryNoData =>
      translate('home_landing_global_map_country_no_data');
  String get homeLandingGlobalMapValueLabel =>
      translate('home_landing_global_map_value_label');
  String get homeLandingGlobalMapCountryTrend =>
      translate('home_landing_global_map_country_trend');
  String get homeLandingGlobalMapFiltersTitle =>
      translate('home_landing_global_map_filters_title');

  String homeLandingGlobalPeriod(String period) =>
      translate('home_landing_global_period').replaceFirst('%s', period);

  String get loadingPage => translate('loading_page');
  String get loadingPreferences => translate('loading_preferences');
  String get loadingNotifications => translate('loading_notifications');
  String get loadingDashboard => translate('loading_dashboard');
  String get loadingAuditLogs => translate('loading_audit_logs');
  String get loadingAnalytics => translate('loading_analytics');
  String get loadingOrganizations => translate('loading_organizations');
  String get loadingTemplates => translate('loading_templates');
  String get loadingAssignments => translate('loading_assignments');
  String get loadingTranslations => translate('loading_translations');
  String get loadingPlugins => translate('loading_plugins');
  String get loadingResources => translate('loading_resources');
  String get loadingIndicators => translate('loading_indicators');
  String get loadingDocuments => translate('loading_documents');
  String get loadingApiEndpoints => translate('loading_api_endpoints');
  String get loadingUsers => translate('loading_users');
  String get errorLoadingPage => translate('error_loading_page');
  String get error => translate('error');
  String get retry => translate('retry');
  String get refresh => translate('refresh');
  String get close => translate('close');
  String get save => translate('save');
  String get saved => translate('saved');
  String get success => translate('success');
  String get oopsSomethingWentWrong => translate('oops_something_went_wrong');
  String get goBack => translate('go_back');
  String get edit => translate('edit');
  String get duplicate => translate('duplicate');
  String get preview => translate('preview');
  String get downloadStarted => translate('download_started');
  String get couldNotStartDownload => translate('could_not_start_download');
  String get couldNotOpenDownloadLink => translate('could_not_open_download_link');
  String get errorOpeningDownload => translate('error_opening_download');
  String get pleaseSelectAtLeastOneUser => translate('please_select_at_least_one_user');
  String get indicatorUpdatedSuccessfully => translate('indicator_updated_successfully');
  String get failedToLoadIndicator => translate('failed_to_load_indicator');
  String get userDeleted => translate('user_deleted');
  String get publicUrlCopied => translate('public_url_copied');
  String get pleaseUseWebInterface => translate('please_use_web_interface');
  String get openInWebBrowser => translate('open_in_web_browser');
  String get countries => translate('countries');
  String get allRoles => translate('all_roles');
  String get adminRole => translate('admin_role');
  String get focalPointRole => translate('focal_point_role');
  String get systemManagerRole => translate('system_manager_role');
  String get viewerRole => translate('viewer_role');
  String get allStatus => translate('all_status');
  String get activeStatus => translate('active_status');
  String get inactiveStatus => translate('inactive_status');
  String get normalPriority => translate('normal_priority');
  String get highPriority => translate('high_priority');
  String get none => translate('none');
  String get appScreen => translate('app_screen');
  String get customUrl => translate('custom_url');
  String get createTemplate => translate('create_template');
  String get deleteTemplate => translate('delete_template');
  String get createAssignment => translate('create_assignment');
  String get deleteAssignment => translate('delete_assignment');
  String get editDocument => translate('edit_document');
  String get previewDocument => translate('preview_document');
  String get downloadDocument => translate('download_document');
  String get uploadDocument => translate('upload_document');
  String get newTranslation => translate('new_translation');
  String get newResource => translate('new_resource');
  String get installPlugin => translate('install_plugin');
  String get templateDeletedSuccessfully => translate('template_deleted_successfully');
  String get failedToDeleteTemplate => translate('failed_to_delete_template');
  String get noNotifications => translate('no_notifications');
  String get allCaughtUp => translate('all_caught_up');
  String get notificationsLoadMore => translate('notifications_load_more');
  String get notificationsFilter => translate('notifications_filter');
  String get notificationsFilterTitle => translate('notifications_filter_title');
  String get notificationsFilterReadStatus =>
      translate('notifications_filter_read_status');
  String get notificationsFilterAll => translate('notifications_filter_all');
  String get notificationsFilterUnreadOnly =>
      translate('notifications_filter_unread_only');
  String get notificationsFilterType => translate('notifications_filter_type');
  String get notificationsFilterTypeAny =>
      translate('notifications_filter_type_any');
  String get notificationsFilterFrom => translate('notifications_filter_from');
  String get notificationsFilterFromAny =>
      translate('notifications_filter_from_any');
  String get notificationsFilterFromEmptyHint =>
      translate('notifications_filter_from_empty_hint');
  String get notificationsFilterPriority =>
      translate('notifications_filter_priority');
  String get notificationsFilterPriorityAny =>
      translate('notifications_filter_priority_any');
  String get notificationsFilterPriorityNormal =>
      translate('notifications_filter_priority_normal');
  String get notificationsFilterPriorityHigh =>
      translate('notifications_filter_priority_high');
  String get notificationsFilterPriorityUrgent =>
      translate('notifications_filter_priority_urgent');
  String get notificationsFilterApply => translate('notifications_filter_apply');
  String get notificationsFilterReset => translate('notifications_filter_reset');
  String get notificationsFilterNoMatchesLoaded =>
      translate('notifications_filter_no_matches_loaded');
  String get markAllRead => translate('mark_all_read');
  String get markRead => translate('mark_read');
  String get markUnread => translate('mark_unread');
  String get delete => translate('delete');
  String get archive => translate('archive');
  String get unarchive => translate('unarchive');
  String get sendPushNotification => translate('send_push_notification');
  String get adminPushUserIdsLabel => translate('admin_push_user_ids_label');
  String get adminPushUserIdsHint => translate('admin_push_user_ids_hint');
  String get adminPushUserIdsInvalid => translate('admin_push_user_ids_invalid');
  String get message => translate('message');
  String get send => translate('send');
  String get editIndicator => translate('editIndicator');
  String get selectUsers => translate('select_users');
  String get searchUsers => translate('search_users');
  String get redirectUrl => translate('redirect_url');
  String get login => translate('login');
  String get logIn => translate('log_in');
  String get emailAddress => translate('email_address');
  String get phoneUsernameEmail => translate('phone_username_email');
  String get password => translate('password');
  String get rememberMe => translate('remember_me');
  String get forgotPassword => translate('forgot_password');
  String get forgotPasswordComingSoon =>
      translate('forgot_password_coming_soon');
  String get pleaseEnterEmail => translate('please_enter_email');
  String get pleaseEnterValidEmail => translate('please_enter_valid_email');
  String get pleaseEnterPassword => translate('please_enter_password');
  String get currentPassword => translate('current_password');
  String get newPassword => translate('new_password');
  String get confirmPassword => translate('confirm_password');
  String get enterCurrentPassword => translate('enter_current_password');
  String get enterNewPassword => translate('enter_new_password');
  String get confirmNewPassword => translate('confirm_new_password');
  String get passwordsDoNotMatch => translate('passwords_do_not_match');
  String get passwordChangedSuccessfully =>
      translate('password_changed_successfully');
  String get passwordChangeFailed => translate('password_change_failed');
  String get show => translate('show');
  String get hide => translate('hide');
  String get or => translate('or');
  String get dontHaveAccount => translate('dont_have_account');
  String get signUp => translate('sign_up');
  String get registrationComingSoon => translate('registration_coming_soon');
  String get quickLoginTesting => translate('quick_login_testing');
  String get testAsAdmin => translate('test_as_admin');
  String get testAsFocalPoint => translate('test_as_focal_point');
  String get publicLoginDisabled => translate('public_login_disabled');
  String get testerAccountsInfo => translate('tester_accounts_info');
  String get couldNotOpenAzureLogin => translate('could_not_open_azure_login');
  String get loginWithIfrcAccount => translate('login_with_ifrc_account');
  String get useIfrcFederationAccount =>
      translate('use_ifrc_federation_account');
  String get yourAccountOrCreateAccount =>
      translate('your_account_or_create_account');
  String get loginFailed => translate('login_failed');
  String languageChangedTo(String language) =>
      '${translate('language_changed_to')} $language';

  // Indicator Bank getters
  String get indicatorBankTitle => translate('indicator_bank_title');
  String get indicatorBankLoading => translate('indicator_bank_loading');
  String get indicatorBankError => translate('indicator_bank_error');
  String get indicatorBankSearchPlaceholder =>
      translate('indicator_bank_search_placeholder');
  String get indicatorBankFilterPlaceholder =>
      translate('indicator_bank_filter_placeholder');
  String get indicatorBankBrowseDescription =>
      translate('indicator_bank_browse_description');
  String get indicatorBankGridView => translate('indicator_bank_grid_view');
  String get indicatorBankTableView => translate('indicator_bank_table_view');
  String get indicatorBankShowFilters =>
      translate('indicator_bank_show_filters');
  String get indicatorBankHideFilters =>
      translate('indicator_bank_hide_filters');
  String get indicatorBankFilters => translate('indicator_bank_filters');
  String get indicatorBankFilterType => translate('indicator_bank_filter_type');
  String get indicatorBankFilterTypeAll =>
      translate('indicator_bank_filter_type_all');
  String get indicatorBankFilterSector =>
      translate('indicator_bank_filter_sector');
  String get indicatorBankFilterSectorAll =>
      translate('indicator_bank_filter_sector_all');
  String get indicatorBankFilterSubsector =>
      translate('indicator_bank_filter_subsector');
  String get indicatorBankFilterSubsectorAll =>
      translate('indicator_bank_filter_subsector_all');
  String get indicatorBankListTierAlsoRelated =>
      translate('indicator_bank_list_tier_also_related');
  String get indicatorBankFilterStatus =>
      translate('indicator_bank_filter_status');
  String get indicatorBankFilterStatusActive =>
      translate('indicator_bank_filter_status_active');
  String get indicatorBankFilterStatusAll =>
      translate('indicator_bank_filter_status_all');
  String get indicatorBankApplyFilters =>
      translate('indicator_bank_apply_filters');
  String get indicatorBankClearAll => translate('indicator_bank_clear_all');
  String get indicatorBankShowing => translate('indicator_bank_showing');
  String get indicatorBankIndicators => translate('indicator_bank_indicators');
  String get indicatorBankIndicator => translate('indicator_bank_indicator');
  String get indicatorBankNoSectors => translate('indicator_bank_no_sectors');
  String get indicatorBankNoIndicators =>
      translate('indicator_bank_no_indicators');
  String get indicatorBankTableName => translate('indicator_bank_table_name');
  String get indicatorBankTableType => translate('indicator_bank_table_type');
  String get indicatorBankTableSector =>
      translate('indicator_bank_table_sector');
  String get indicatorBankTableSubsector =>
      translate('indicator_bank_table_subsector');
  String get indicatorBankTableUnit => translate('indicator_bank_table_unit');
  String get indicatorBankProposeNew => translate('indicator_bank_propose_new');
  String get indicatorBankProposeTitle =>
      translate('indicator_bank_propose_title');
  String get indicatorBankProposeContactInfo =>
      translate('indicator_bank_propose_contact_info');
  String get indicatorBankProposeYourName =>
      translate('indicator_bank_propose_your_name');
  String get indicatorBankProposeEmail =>
      translate('indicator_bank_propose_email');
  String get indicatorBankProposeIndicatorInfo =>
      translate('indicator_bank_propose_indicator_info');
  String get indicatorBankProposeIndicatorName =>
      translate('indicator_bank_propose_indicator_name');
  String get indicatorBankProposeDefinition =>
      translate('indicator_bank_propose_definition');
  String get indicatorBankProposeType =>
      translate('indicator_bank_propose_type');
  String get indicatorBankProposeUnit =>
      translate('indicator_bank_propose_unit');
  String get indicatorBankProposeSector =>
      translate('indicator_bank_propose_sector');
  String get indicatorBankProposePrimarySector =>
      translate('indicator_bank_propose_primary_sector');
  String get indicatorBankProposeSecondarySector =>
      translate('indicator_bank_propose_secondary_sector');
  String get indicatorBankProposeTertiarySector =>
      translate('indicator_bank_propose_tertiary_sector');
  String get indicatorBankProposeSubsector =>
      translate('indicator_bank_propose_subsector');
  String get indicatorBankProposePrimarySubsector =>
      translate('indicator_bank_propose_primary_subsector');
  String get indicatorBankProposeSecondarySubsector =>
      translate('indicator_bank_propose_secondary_subsector');
  String get indicatorBankProposeTertiarySubsector =>
      translate('indicator_bank_propose_tertiary_subsector');
  String get indicatorBankProposeEmergency =>
      translate('indicator_bank_propose_emergency');
  String get indicatorBankProposeRelatedPrograms =>
      translate('indicator_bank_propose_related_programs');
  String get indicatorBankProposeReason =>
      translate('indicator_bank_propose_reason');
  String get indicatorBankProposeAdditionalNotes =>
      translate('indicator_bank_propose_additional_notes');
  String get indicatorBankProposeSubmit =>
      translate('indicator_bank_propose_submit');
  String get indicatorBankProposeThankYou =>
      translate('indicator_bank_propose_thank_you');
  String get indicatorBankProposeSuccess =>
      translate('indicator_bank_propose_success');
  String get indicatorBankProposeFailed =>
      translate('indicator_bank_propose_failed');
  String get indicatorBankNameRequired =>
      translate('indicator_bank_name_required');
  String get indicatorBankEmailRequired =>
      translate('indicator_bank_email_required');
  String get indicatorBankIndicatorNameRequired =>
      translate('indicator_bank_indicator_name_required');
  String get indicatorBankDefinitionRequired =>
      translate('indicator_bank_definition_required');
  String get indicatorBankPrimarySectorRequired =>
      translate('indicator_bank_primary_sector_required');
  String get indicatorBankPrimarySubsectorRequired =>
      translate('indicator_bank_primary_subsector_required');
  String get indicatorBankReasonRequired =>
      translate('indicator_bank_reason_required');

  // Dashboard getters
  String get nationalSociety => translate('national_society');
  String get active => translate('active');
  String get completed => translate('completed');
  String get currentAssignments => translate('current_assignments');

  /// Short title for the open-assignments group (e.g. "You have 3 open assignments").
  String dashboardYouHaveOpenAssignmentsTitle(int count) {
    if (count <= 0) {
      return translate('dashboard_you_have_no_open_assignments');
    }
    if (count == 1) {
      return translate('dashboard_you_have_one_open_assignment');
    }
    return translate('dashboard_you_have_open_assignments_count')
        .replaceAll('%s', '$count');
  }

  String get pastAssignments => translate('past_assignments');
  String get assignmentsFor => translate('assignments_for');
  String get pastSubmissionsFor => translate('past_submissions_for');
  String get somethingWentWrong => translate('something_went_wrong');
  String get noAssignmentsYet => translate('no_assignments_yet');
  String get newAssignmentsWillAppear =>
      translate('new_assignments_will_appear');
  String get getStartedByCreating => translate('get_started_by_creating');
  String get filters => translate('filters');
  String get period => translate('period');
  String get template => translate('template');
  String get status => translate('status');
  String get clear => translate('clear');
  String get approved => translate('approved');
  String get requiresRevision => translate('requires_revision');
  String get pending => translate('pending');
  String get inProgress => translate('in_progress');
  String get submitted => translate('submitted');
  String get other => translate('other');
  String get entities => translate('entities');
  String get searchPlaceholder => translate('search_placeholder');
  String get noResultsFound => translate('no_results_found');
  String get entityTypeCountry => translate('entity_type_country');
  String get entityTypeNsBranch => translate('entity_type_ns_branch');
  String get entityTypeNsSubBranch => translate('entity_type_ns_sub_branch');
  String get entityTypeNsLocalUnit => translate('entity_type_ns_local_unit');
  String get entityTypeDivision => translate('entity_type_division');
  String get entityTypeDepartment => translate('entity_type_department');
  String get deleteAssignmentConfirmMessage =>
      translate('delete_assignment_confirm_message');

  /// Localizes an assignment status value
  String localizeStatus(String status) {
    final statusLower = status.toLowerCase().trim();
    switch (statusLower) {
      case 'approved':
        return approved;
      case 'requires revision':
        return requiresRevision;
      case 'pending':
        return pending;
      case 'in progress':
        return inProgress;
      case 'submitted':
        return submitted;
      default:
        return status; // Return original if not found
    }
  }
  String get noAssignmentsMatchFilters =>
      translate('no_assignments_match_filters');
  String get form => translate('form');
  String get lastUpdated => translate('last_updated');
  String get actions => translate('actions');
  String get allYears => translate('all_years');
  String get allTemplates => translate('all_templates');
  String get allStatuses => translate('all_statuses');
  String get templateMissing => translate('template_missing');
  String get selfReported => translate('self_reported');
  String get noActionsAvailable => translate('no_actions_available');
  String get previous => translate('previous');
  String get next => translate('next');
  String get showing => translate('showing');
  String get to => translate('to');
  String get ofText => translate('of');
  String get results => translate('results');
  String get noPastAssignmentsFor => translate('no_past_assignments_for');
  String get yet => translate('yet');
  String get submissionHistoryAndDataQualityFor =>
      translate('submission_history_and_data_quality_for');
  String get overallPerformance => translate('overall_performance');
  String get averageCompletionRatePast3Periods =>
      translate('average_completion_rate_past_3_periods');
  String get averageSubmissionTimeliness =>
      translate('average_submission_timeliness');
  String get dataQualityIndexFakeMetric =>
      translate('data_quality_index_fake_metric');
  String get numberOfRevisionsRequestedPastYear =>
      translate('number_of_revisions_requested_past_year');
  String get trendAnalysis => translate('trend_analysis');
  String get recentActivities => translate('recent_activities');
  String get last7Days => translate('last_7_days');
  String get unknownUser => translate('unknown_user');
  String get added => translate('added');
  String get updated => translate('updated');
  String get removed => translate('removed');
  String get showLess => translate('show_less');
  String get moreChange => translate('more_change');
  String get noRecentActivities => translate('no_recent_activities');
  String get activitiesFromOtherFocalPointsIn =>
      translate('activities_from_other_focal_points_in');
  String get willAppearHere => translate('will_appear_here');
  String get focalPointsFor => translate('focal_points_for');
  String get nationalSocietyFocalPoints =>
      translate('national_society_focal_points');
  String get ifrcFocalPoints => translate('ifrc_focal_points');
  String get noFocalPointsAssignedTo =>
      translate('no_focal_points_assigned_to');
  String get yourUserAccountNotAssociated =>
      translate('your_user_account_not_associated');
  String get pleaseContactAdministrator =>
      translate('please_contact_administrator');
  String get dueDate => translate('due_date');
  String get noDueDate => translate('no_due_date');
  String get overdue => translate('overdue');
  String get latestSubmission => translate('latest_submission');
  String get submittedThroughPublicLink =>
      translate('submitted_through_public_link');
  String get submission => translate('submission');
  String get submissions => translate('submissions');
  String get completion => translate('completion');
  String get received1SubmissionUsingPublicLink =>
      translate('received_1_submission_using_public_link');
  String receivedCountSubmissionsUsingPublicLink(int count) =>
      translate('received_count_submissions_using_public_link')
          .replaceAll('%(count)d', count.toString());
  String atDatetime(String datetime) =>
      translate('at_datetime').replaceAll('%(datetime)s', datetime);
  String latestDatetime(String datetime) =>
      translate('latest_datetime').replaceAll('%(datetime)s', datetime);
  String get lastModifiedBy => translate('last_modified_by');
  String get assignmentAssignedDate => translate('assignment_assigned_date');
  String get assignmentStatusUpdated => translate('assignment_status_updated');
  String get contributors => translate('contributors');
  String get assignmentSubmittedBy => translate('assignment_submitted_by');
  String get assignmentApprovedBy => translate('assignment_approved_by');
  String get publicLinkEnabled => translate('public_link_enabled');
  String get publicLink => translate('public_link');
  String get unknown => translate('unknown');
  String get nA => translate('n_a');
  String get enterData => translate('enter_data');
  String get downloadForOffline => translate('download_for_offline');
  String get downloadingOfflineForm =>
      translate('downloading_offline_form');
  String get offlineFormSaved => translate('offline_form_saved');
  String get offlineFormSaveFailed =>
      translate('offline_form_save_failed');
  String get offlineFormNotDownloaded =>
      translate('offline_form_not_downloaded');
  String get offlineDownloadRequiresConnection =>
      translate('offline_download_requires_connection');
  String get offlineFormExportRequiresConnection =>
      translate('offline_form_export_requires_connection');
  String get offlineOpenSavedCopy => translate('offline_open_saved_copy');
  String get removeOfflineCopy => translate('remove_offline_copy');
  String get offlineFormRemoved => translate('offline_form_removed');
  String get offlineSavedCopyDetailsTooltip =>
      translate('offline_saved_copy_details_tooltip');
  String get offlineCopySheetTitle => translate('offline_copy_sheet_title');
  String get offlineCopySavedOnLabel =>
      translate('offline_copy_saved_on_label');
  String offlineCopyFilesCached(int count) =>
      translate('offline_copy_files_cached')
          .replaceAll('%(count)d', count.toString());
  String get offlineStaleBundleBannerTitle =>
      translate('offline_stale_bundle_banner_title');
  String get offlineStaleBundleBannerBodyOnline =>
      translate('offline_stale_bundle_banner_body_online');
  String get offlineStaleBundleBannerBodyOffline =>
      translate('offline_stale_bundle_banner_body_offline');
  String get offlineStaleBundleUpdatesSnackbar =>
      translate('offline_stale_bundle_updates_snackbar');
  String get offlineStaleBundlePartialRefresh =>
      translate('offline_stale_bundle_partial_refresh');
  String get offlineStaleBundleSheetNotice =>
      translate('offline_stale_bundle_sheet_notice');
  String get offlineStaleBundleUpdateNow =>
      translate('offline_stale_bundle_update_now');
  String get approve => translate('approve');
  String get reopen => translate('reopen');
  String get viewPublicSubmissions => translate('view_public_submissions');
  String get viewSubmission => translate('view_submission');
  String get viewSubmissions => translate('view_submissions');
  String get openForm => translate('open_form');
  String get noFormsAssignedOrSubmittedFor =>
      translate('no_forms_assigned_or_submitted_for');
  String get adminsCanAssignForms => translate('admins_can_assign_forms');
  String get createAReport => translate('create_a_report');
  String get deleteSelfReportedAssignment =>
      translate('delete_self_reported_assignment');
  String get quickActions => translate('quick_actions');
  String get newAssignment => translate('new_assignment');
  String get newTemplate => translate('new_template');
  String get keyMetrics => translate('key_metrics');
  String get overview => translate('overview');
  String get createNewAssignment => translate('create_new_assignment');
  String get templates => translate('templates');
  String get browseAvailableTemplates =>
      translate('browse_available_templates');
  String get enterYourName => translate('enter_your_name');
  String get enterYourJobTitle => translate('enter_your_job_title');
  String get editName => translate('edit_name');
  String get editTitle => translate('edit_title');
  String get nameCannotBeEmpty => translate('name_cannot_be_empty');
  String get titleCannotBeEmpty => translate('title_cannot_be_empty');
  String get profileUpdatedSuccessfully =>
      translate('profile_updated_successfully');
  String get errorUpdatingProfile => translate('error_updating_profile');
  String get colorPickerComingSoon => translate('color_picker_coming_soon');
  String get chatbotPreferenceUpdateComingSoon =>
      translate('chatbot_preference_update_coming_soon');
  String get selectColor => translate('select_color');
  String get currentColor => translate('current_color');
  String get profileColorUpdated => translate('profile_color_updated');
  String get profileColorUpdateFailed =>
      translate('profile_color_update_failed');
  String get adminDashboard => translate('admin_dashboard');
  String get noDataAvailable => translate('no_data_available');
  String get totalUsers => translate('total_users');
  String get admins => translate('admins');
  String get systemAdministrators => translate('system_administrators');
  String get focalPoints => translate('focal_points');
  String get countryFocalPoints => translate('country_focal_points');
  String get formTemplates => translate('form_templates');
  String get assignments => translate('assignments');
  String get activeAssignments => translate('active_assignments');
  String get todaysLogins => translate('todays_logins');
  String get successfulLoginsToday => translate('successful_logins_today');
  String get pendingSubmissions => translate('pending_submissions');
  String get overdueAssignments => translate('overdue_assignments');
  String get securityAlerts => translate('security_alerts');
  String get successfulLogins => translate('successful_logins');
  String get userActivities => translate('user_activities');
  String get activeSessions => translate('active_sessions');
  String get allNotificationsMarkedAsRead =>
      translate('all_notifications_marked_as_read');
  String get markAsRead => translate('mark_as_read');
  String get markAsUnread => translate('mark_as_unread');
  String get notificationPreferences => translate('notification_preferences');
  String get soundNotifications => translate('sound_notifications');
  String get emailFrequency => translate('email_frequency');
  String get instant => translate('instant');
  String get dailyDigest => translate('daily_digest');
  String get weeklyDigest => translate('weekly_digest');
  String get digestSchedule => translate('digest_schedule');
  String get dayOfWeek => translate('day_of_week');
  String get monday => translate('monday');
  String get tuesday => translate('tuesday');
  String get wednesday => translate('wednesday');
  String get thursday => translate('thursday');
  String get friday => translate('friday');
  String get saturday => translate('saturday');
  String get sunday => translate('sunday');
  String get timeLocalTime => translate('time_local_time');
  String get notificationTypes => translate('notification_types');
  String get preferencesSavedSuccessfully =>
      translate('preferences_saved_successfully');
  String get enableSound => translate('enable_sound');
  String get playSoundForNewNotifications =>
      translate('play_sound_for_new_notifications');
  String get configureNotificationTypesDescription =>
      translate('configure_notification_types_description');
  String get notificationType => translate('notification_type');
  String get push => translate('push');
  String get all => translate('all');
  String get savePreferences => translate('save_preferences');
  String get selectDigestTimeDescription =>
      translate('select_digest_time_description');
  String get failedToSavePreferences =>
      translate('failed_to_save_preferences');
  String get assignmentCreated => translate('assignment_created');
  String get assignmentSubmitted => translate('assignment_submitted');
  String get assignmentApproved => translate('assignment_approved');
  String get assignmentReopened => translate('assignment_reopened');
  String get publicSubmissionReceived =>
      translate('public_submission_received');
  String get formUpdated => translate('form_updated');
  String get documentUploaded => translate('document_uploaded');
  String get userAddedToCountry => translate('user_added_to_country');
  String get templateUpdated => translate('template_updated');
  String get selfReportCreated => translate('self_report_created');
  String get deadlineReminder => translate('deadline_reminder');
  String get searchAuditLogs => translate('search_audit_logs');
  String get auditTrailNoEntries => translate('audit_trail_no_entries');
  String get auditTrailActivityLabel => translate('audit_trail_activity_label');
  String get homeScreenWidgetTitle => translate('home_screen_widget_title');
  String get auditWidgetActivityTypesHint =>
      translate('audit_widget_activity_types_hint');
  String get allActions => translate('all_actions');
  String get allUsers => translate('all_users');
  String get fromDate => translate('from_date');
  String get toDate => translate('to_date');
  String get selectDate => translate('select_date');
  String get noDescription => translate('no_description');
  String get searchApiEndpoints => translate('search_api_endpoints');
  String get httpMethod => translate('http_method');
  String get allMethods => translate('all_methods');
  String get httpGet => translate('get');
  String get httpPost => translate('post');
  String get httpPut => translate('put');
  String get httpDelete => translate('delete_method');
  String get apiStatus => translate('api_status');
  String get apiActive => translate('api_active');
  String get newApiKey => translate('new_api_key');
  String get timeRange => translate('time_range');
  String get last30Days => translate('last_30_days');
  String get last90Days => translate('last_90_days');
  String get lastYear => translate('last_year');
  String get allTime => translate('all_time');
  String get allMetrics => translate('all_metrics');
  String get activeUsers => translate('active_users');
  String get pageViews => translate('page_views');
  String get searchIndicators => translate('search_indicators');
  String get allCategories => translate('all_categories');
  String get allSectors => translate('all_sectors');
  String get sector => translate('sector');
  String get health => translate('health');
  String get wash => translate('wash');
  String get shelter => translate('shelter');
  String get education => translate('education');
  String get output => translate('output');
  String get outcome => translate('outcome');
  String get impact => translate('impact');
  String get category => translate('category');
  String get resource => translate('resource');
  String get secretariat => translate('secretariat');
  String get divisions => translate('divisions');
  String get departments => translate('departments');
  String get metric => translate('metric');
  String get logins => translate('logins');
  String get metricSubmissions => translate('metric_submissions');
  String get action => translate('action');
  String get create => translate('create');
  String get update => translate('update');
  String get user => translate('user');
  String get deprecated => translate('deprecated');
  String get beta => translate('beta');
  String get indicators => translate('indicators');
  String get newIndicator => translate('new_indicator');
  String get searchOrganizations => translate('search_organizations');
  String get entityType => translate('entity_type');
  String get allTypes => translate('all_types');
  String get nationalSocieties => translate('national_societies');
  String get nsStructure => translate('ns_structure');
  String get regionalOffices => translate('regional_offices');
  String get clusterOffices => translate('cluster_offices');
  String get addOrganization => translate('add_organization');
  String get addUser => translate('add_user');
  String get searchResources => translate('search_resources');
  String get searchDocuments => translate('search_documents');
  String get searchTranslations => translate('search_translations');
  String get searchPlugins => translate('search_plugins');
  String get type => translate('type');
  String get inactive => translate('inactive');
  String get publication => translate('publication');
  String get document => translate('document');
  String get noIndicatorsFound => translate('no_indicators_found');
  String get noOrganizationsFound => translate('no_organizations_found');
  String get noResourcesFound => translate('no_resources_found');
  String get resourcesUnifiedPlanningSectionTitle =>
      translate('resources_unified_planning_section_title');
  String get resourcesUnifiedPlanningSectionSubtitle =>
      translate('resources_unified_planning_section_subtitle');
  String get unifiedPlanningEmpty => translate('unified_planning_empty');
  String get unifiedPlanningFreshBadge =>
      translate('unified_planning_fresh_badge');
  String get unifiedPlanningSortBy => translate('unified_planning_sort_by');
  String get unifiedPlanningSortDateNewest =>
      translate('unified_planning_sort_date_newest');
  String get unifiedPlanningSortDateOldest =>
      translate('unified_planning_sort_date_oldest');
  String get unifiedPlanningSortCountryAz =>
      translate('unified_planning_sort_country_az');
  String get unifiedPlanningSortCountryZa =>
      translate('unified_planning_sort_country_za');
  String get unifiedPlanningFilterAllCountries =>
      translate('unified_planning_filter_all_countries');
  String get unifiedPlanningErrorConfig => translate('unified_error_config');
  String get unifiedPlanningErrorCredentials =>
      translate('unified_error_credentials');
  String get unifiedPlanningErrorIfrcAuth =>
      translate('unified_error_ifrc_auth');
  String get unifiedPlanningErrorIfrc => translate('unified_error_ifrc');
  String get unifiedPlanningAnalyticsTitle =>
      translate('unified_planning_analytics_title');
  String get unifiedPlanningAnalyticsTooltip =>
      translate('unified_planning_analytics_tooltip');
  String get unifiedPlanningAnalyticsTotal =>
      translate('unified_planning_analytics_total');
  String get unifiedPlanningAnalyticsCountries =>
      translate('unified_planning_analytics_countries');
  String get unifiedPlanningAnalyticsTypes =>
      translate('unified_planning_analytics_types');
  String get unifiedPlanningAnalyticsByYearType =>
      translate('unified_planning_analytics_by_year_type');
  String get unifiedPlanningAnalyticsByCountry =>
      translate('unified_planning_analytics_by_country');
  String get unifiedPlanningAnalyticsRecent =>
      translate('unified_planning_analytics_recent');
  String get unifiedPlanningAnalyticsUnknownYear =>
      translate('unified_planning_analytics_unknown_year');
  String get unifiedPlanningAnalyticsUnknownCountry =>
      translate('unified_planning_analytics_unknown_country');
  String get unifiedPlanningAnalyticsUnknownType =>
      translate('unified_planning_analytics_unknown_type');
  String unifiedPlanningAnalyticsMore(int n) =>
      translate('unified_planning_analytics_more').replaceFirst('%s', '$n');
  String get unifiedPlanningAnalyticsFiltersTooltip =>
      translate('unified_planning_analytics_filters_tooltip');
  String get unifiedPlanningAnalyticsFiltersTitle =>
      translate('unified_planning_analytics_filters_title');
  String get unifiedPlanningAnalyticsFilterYears =>
      translate('unified_planning_analytics_filter_years');
  String get unifiedPlanningAnalyticsFilterRounds =>
      translate('unified_planning_analytics_filter_rounds');
  String get unifiedPlanningAnalyticsFilterAllYears =>
      translate('unified_planning_analytics_filter_all_years');
  String get unifiedPlanningAnalyticsFilterAllRounds =>
      translate('unified_planning_analytics_filter_all_rounds');
  String get unifiedPlanningAnalyticsFilterReset =>
      translate('unified_planning_analytics_filter_reset');
  String get unifiedPlanningAnalyticsFilterApply =>
      translate('unified_planning_analytics_filter_apply');
  String get unifiedPlanningAnalyticsFilterInvalid =>
      translate('unified_planning_analytics_filter_invalid');
  String get unifiedPlanningAnalyticsMapTooltip =>
      translate('unified_planning_analytics_map_tooltip');
  String get unifiedPlanningParticipationMapTitle =>
      translate('unified_planning_participation_map_title');
  String unifiedPlanningParticipationSlotsLabel(String n) =>
      translate('unified_planning_participation_slots_label')
          .replaceFirst('%s', n);
  String get unifiedPlanningParticipationNoSlots =>
      translate('unified_planning_participation_no_slots');
  String unifiedPlanningParticipationStats(int full, int partial, int offMap) {
    var s = translate('unified_planning_participation_stats');
    s = s.replaceFirst('%s', '$full');
    s = s.replaceFirst('%s', '$partial');
    return s.replaceFirst('%s', '$offMap');
  }

  String unifiedPlanningParticipationSheetSlots(String covered, String total) {
    var s = translate('unified_planning_participation_sheet_slots');
    s = s.replaceFirst('%s', covered);
    return s.replaceFirst('%s', total);
  }

  String get unifiedPlanningParticipationSheetFull =>
      translate('unified_planning_participation_sheet_full');
  String get unifiedPlanningParticipationSheetPartial =>
      translate('unified_planning_participation_sheet_partial');
  String get unifiedPlanningParticipationSheetNone =>
      translate('unified_planning_participation_sheet_none');
  String get unifiedPlanningParticipationLegendFull =>
      translate('unified_planning_participation_legend_full');
  String get unifiedPlanningParticipationLegendPartial =>
      translate('unified_planning_participation_legend_partial');
  String get unifiedPlanningParticipationLegendNoData =>
      translate('unified_planning_participation_legend_no_data');
  String get noPluginsFound => translate('no_plugins_found');
  String get noTranslationsFound => translate('no_translations_found');
  String get noDocumentsFound => translate('no_documents_found');
  String get noUsersFound => translate('no_users_found');
  String get loadingUserProfile => translate('loading_user_profile');
  String get failedLoadUserProfile => translate('failed_load_user_profile');
  String get adminUserDetailConfirmSaveTitle =>
      translate('admin_user_detail_confirm_save_title');
  String get adminUserDetailConfirmSaveMessage =>
      translate('admin_user_detail_confirm_save_message');
  String get adminUserDetailInvalidProfileColor =>
      translate('admin_user_detail_invalid_profile_color');
  String get adminUserDetailChangesSaved =>
      translate('admin_user_detail_changes_saved');
  String get adminUserDetailSaveChanges =>
      translate('admin_user_detail_save_changes');
  String get adminUserDetailProfileColorLabel =>
      translate('admin_user_detail_profile_color_label');
  String get adminUserDetailProfileColorHint =>
      translate('admin_user_detail_profile_color_hint');
  String get adminUserDetailCannotDeactivateSelf =>
      translate('admin_user_detail_cannot_deactivate_self');
  String get adminUserDetailMatrixReadOnlyBundled =>
      translate('admin_user_detail_matrix_read_only_bundled');
  String get adminUserDetailRbacIncomplete =>
      translate('admin_user_detail_rbac_incomplete');
  String get assignedRolesTitle => translate('assigned_roles_title');
  String get roleTypeLabel => translate('role_type_label');
  String get permissionsByRole => translate('permissions_by_role');
  String get allPermissionsUnion => translate('all_permissions_union');
  String get entityPermissionsTitle => translate('entity_permissions_title');
  String get manageUsersDetailFooter => translate('manage_users_detail_footer');
  String get noRolesAssigned => translate('no_roles_assigned');
  String get noEntitiesAssigned => translate('no_entities_assigned');
  String get entityPermissionUnnamed => translate('entity_permission_unnamed');
  String get entityRegionOther => translate('entity_region_other');
  String get noPermissionsListed => translate('no_permissions_listed');
  String get userDirAssignmentRoles => translate('user_dir_assignment_roles');
  String get userDirAdminRoles => translate('user_dir_admin_roles');
  String get userDirOtherRoles => translate('user_dir_other_roles');
  String get adminRoleAccessArea => translate('admin_role_access_area');
  String get adminRoleAccessView => translate('admin_role_access_view');
  String get adminRoleAccessManage => translate('admin_role_access_manage');
  String get adminRoleDeHeading => translate('admin_role_de_heading');
  String get adminRoleDeTable => translate('admin_role_de_table');
  String get adminRoleDeAnalysis => translate('admin_role_de_analysis');
  String get adminRoleDeCompliance => translate('admin_role_de_compliance');
  String get adminRoleNoteAdminFull => translate('admin_role_note_admin_full');
  String get adminRoleNoteAdminCore => translate('admin_role_note_admin_core');
  String get adminRoleOtherAdminRoles => translate('admin_role_other_admin_roles');
  String get usersDirectoryRoleAll => translate('users_directory_role_all');
  String get usersDirectoryCountryAll => translate('users_directory_country_all');
  String get noAssignmentsFound => translate('no_assignments_found');
  String get noTemplatesFound => translate('no_templates_found');
  String get assignmentDeletedSuccessfully =>
      translate('assignment_deleted_successfully');
  String get failedToDeleteAssignment =>
      translate('failed_to_delete_assignment');
  String get timelineView => translate('timeline_view');
  String get viewAllPublicSubmissions =>
      translate('view_all_public_submissions');
  String get itemsRequiringAttention => translate('items_requiring_attention');
  String get recentActivity => translate('recent_activity');
  String get recentActivity7Days => translate('recent_activity_7_days');
  String get generalSettings => translate('general_settings');
  String get securitySettings => translate('security_settings');
  String get systemSettings => translate('system_settings');
  String get applicationSettings => translate('application_settings');
  String get languageSettings => translate('language_settings');
  String get notificationSettings => translate('notification_settings');
  String get authenticationSettings => translate('authentication_settings');
  String get permissionSettings => translate('permission_settings');
  String get databaseSettings => translate('database_settings');
  String get cloudStorageSettings => translate('cloud_storage_settings');
  String get configureGeneralApplicationSettings =>
      translate('configure_general_application_settings');
  String get manageSupportedLanguagesAndTranslations =>
      translate('manage_supported_languages_and_translations');
  String get configureNotificationPreferences =>
      translate('configure_notification_preferences');
  String get configureAuthenticationAndAuthorization =>
      translate('configure_authentication_and_authorization');
  String get manageUserPermissionsAndRoles =>
      translate('manage_user_permissions_and_roles');
  String get configureDatabaseConnectionsAndBackups =>
      translate('configure_database_connections_and_backups');
  String get configureCloudStorageAndFileManagement =>
      translate('configure_cloud_storage_and_file_management');

  // Splash Screen getters
  String get welcomeToIfrcNetworkDatabank =>
      translate('welcome_to_ifrc_network_databank');
  String get splashDescription => translate('splash_description');
  String get poweredByHumDatabank => translate('powered_by_hum_databank');
  String get openOnGithub => translate('open_on_github');

  // Indicator Detail getters
  String get indicatorDetailTitle => translate('indicator_detail_title');
  String get indicatorDetailLoading => translate('indicator_detail_loading');
  String get indicatorDetailError => translate('indicator_detail_error');
  String get indicatorDetailNotFound => translate('indicator_detail_not_found');
  String get indicatorDetailGoBack => translate('indicator_detail_go_back');
  String get indicatorDetailDefinition =>
      translate('indicator_detail_definition');
  String get indicatorDetailDetails => translate('indicator_detail_details');
  String get indicatorDetailType => translate('indicator_detail_type');
  String get indicatorDetailUnit => translate('indicator_detail_unit');
  String get indicatorDetailSector => translate('indicator_detail_sector');
  String get indicatorDetailSubsector =>
      translate('indicator_detail_subsector');
  String get indicatorDetailEmergencyContext =>
      translate('indicator_detail_emergency_context');
  String get indicatorDetailRelatedPrograms =>
      translate('indicator_detail_related_programs');
  String get indicatorDetailStatus => translate('indicator_detail_status');
  String get indicatorDetailArchived => translate('indicator_detail_archived');
  String get indicatorDetailYes => translate('indicator_detail_yes');

  // Quiz Game getters
  String get quizGame => translate('quiz_game');
  String get quizGameTitle => translate('quiz_game_title');
  String get quizGameTestYourKnowledge => translate('quiz_game_test_your_knowledge');
  String get quizGameLoading => translate('quiz_game_loading');
  String get quizGameError => translate('quiz_game_error');
  String get quizGameTryAgain => translate('quiz_game_try_again');
  String get quizGameStartQuiz => translate('quiz_game_start_quiz');
  String get quizGameWhichSector => translate('quiz_game_which_sector');
  String get quizGameWhichSubsector => translate('quiz_game_which_subsector');
  String get quizGameDefinition => translate('quiz_game_definition');
  String get quizGameNoDefinition => translate('quiz_game_no_definition');
  String get quizGameCorrect => translate('quiz_game_correct');
  String get quizGameIncorrect => translate('quiz_game_incorrect');
  String get quizGameNextQuestion => translate('quiz_game_next_question');
  String get quizGameViewResults => translate('quiz_game_view_results');
  String get quizGameQuizComplete => translate('quiz_game_quiz_complete');
  String get quizGameExcellentWork => translate('quiz_game_excellent_work');
  String get quizGameWellDone => translate('quiz_game_well_done');
  String get quizGameGoodEffort => translate('quiz_game_good_effort');
  String get quizGameKeepPracticing => translate('quiz_game_keep_practicing');
  String get quizGameOutOf => translate('quiz_game_out_of');
  String get quizGameStatistics => translate('quiz_game_statistics');
  String get quizGameCorrectAnswers => translate('quiz_game_correct_answers');
  String get quizGameIncorrectAnswers => translate('quiz_game_incorrect_answers');
  String get quizGameTotal => translate('quiz_game_total');
  String get quizGameHome => translate('quiz_game_home');
  String get quizGamePlayAgain => translate('quiz_game_play_again');
  String get quizGameNoIndicatorsAvailable => translate('quiz_game_no_indicators_available');
  String get quizGameFailedToStart => translate('quiz_game_failed_to_start');
  String get quizGameLeaderboard => translate('quiz_game_leaderboard');
  String get quizGameViewLeaderboard => translate('quiz_game_view_leaderboard');
  String get quizGameLoadingLeaderboard => translate('quiz_game_loading_leaderboard');
  String get quizGameNoLeaderboardData => translate('quiz_game_no_leaderboard_data');
  String get quizGameTopPlayers => translate('quiz_game_top_players');
  String get quizGameYou => translate('quiz_game_you');
  String get quizGamePoints => translate('quiz_game_points');

  // Offline indicator
  String get offlineStatus => translate('offline_status');
  String get offlineSync => translate('offline_sync');
  String get offlineNoInternet => translate('offline_no_internet');
  String offlinePendingCount(int count) =>
      translate('offline_pending_count').replaceAll('%s', '$count');
  String offlineQueuedCount(int count) =>
      translate('offline_queued_count').replaceAll('%s', '$count');
  String offlineSyncedTime(String time) =>
      translate('offline_synced_time').replaceAll('%s', time);
  String offlineRequestsWillSync(int count) =>
      translate('offline_requests_will_sync').replaceAll('%s', '$count');
  String get backendUnreachableTitle =>
      translate('backend_unreachable_title');
  String get backendUnreachableSubtitle =>
      translate('backend_unreachable_subtitle');

  // PDF viewer & sharing
  String get pdfViewerConnecting => translate('pdf_viewer_connecting');
  String pdfViewerDownloadingPercent(int pct) =>
      translate('pdf_viewer_downloading_percent').replaceAll('%s', '$pct');
  String get pdfViewerCouldNotLoad => translate('pdf_viewer_could_not_load');
  String pdfViewerDownloadFailedHttp(int code) =>
      translate('pdf_viewer_download_failed_http');
  String get pdfViewerFilenameFallback => translate('pdf_viewer_filename_fallback');
  String get actionShare => translate('action_share');

  // Translation entry UI
  String get translationUnknownKey => translate('translation_unknown_key');
  String translationLanguageLabel(String language) =>
      translate('translation_language_label').replaceAll('%s', language);
  String get emptyEmDash => translate('empty_em_dash');

  /// Localized display name for a BCP-47 language/locale code (for translation UI).
  String languageDisplayNameForLocaleCode(String code) {
    final base = code.toLowerCase().split(RegExp(r'[-_]')).first;
    switch (base) {
      case 'en':
        return translate('lang_display_en');
      case 'fr':
        return translate('lang_display_fr');
      case 'es':
        return translate('lang_display_es');
      case 'ar':
        return translate('lang_display_ar');
      case 'ru':
        return translate('lang_display_ru');
      case 'zh':
        return translate('lang_display_zh');
      case 'hi':
        return translate('lang_display_hi');
      case 'nl':
        return translate('lang_display_nl');
      case 'hu':
        return translate('lang_display_hu');
      case 'ja':
        return translate('lang_display_ja');
      default:
        return code.toUpperCase();
    }
  }

  String get navUrlNotAllowed => translate('nav_url_not_allowed');
  String get navigationMenu => translate('navigation_menu');
  String httpError(int code) => translate('http_error');

  String get azureCompleteSignInBrowser => translate('azure_complete_sign_in_browser');
  String get azureOpeningSignInBrowser => translate('azure_opening_sign_in_browser');
  String get azureReopenBrowser => translate('azure_reopen_browser');

  String settingsThemeSetTo(String name) =>
      translate('settings_theme_set_to').replaceAll('%s', name);

  String get resourcesSearchTooltip => translate('resources_search_tooltip');
  String get resourcesCloseSearchTooltip => translate('resources_close_search_tooltip');
  String get resourcesOtherSubgroup => translate('resources_other_subgroup');
  String get resourcesListTruncatedHint =>
      translate('resources_list_truncated_hint');

  String get countriesSearchHint => translate('countries_search_hint');
  String get countriesNoResults => translate('countries_no_results');
  String get countriesNoAvailable => translate('countries_no_available');

  String get nsSelectBranchPrompt => translate('ns_select_branch_prompt');

  String templateDeleteHasData(int count) =>
      translate('template_delete_has_data').replaceAll('%s', '$count');
  String get templateDeleteSimple => translate('template_delete_simple');
  String get templateDuplicatedSuccess => translate('template_duplicated_success');
  String get templateDuplicateFailed => translate('template_duplicate_failed');

  String get translationFilterSource => translate('translation_filter_source');
  String get translationFilterSourceHint => translate('translation_filter_source_hint');

  String entityEditTypeLabel(String entityType) {
    switch (entityType) {
      case 'countries':
        return translate('org_entity_country');
      case 'nss':
        return translate('org_entity_national_society');
      case 'divisions':
        return translate('org_entity_division');
      case 'departments':
        return translate('org_entity_department');
      case 'regions':
        return translate('org_entity_regional_office');
      case 'clusters':
        return translate('org_entity_cluster_office');
      case 'ns_structure':
        return translate('org_entity_ns_structure');
      default:
        return translate('org_entity_generic');
    }
  }

  String entityEditTitle(String entityType) =>
      translate('entity_edit_title').replaceAll('%s', entityEditTypeLabel(entityType));
  String entityNameLabel(String entityType) =>
      translate('entity_name_label').replaceAll('%s', entityEditTypeLabel(entityType));
  String entityNameHint(String entityType) =>
      translate('entity_name_hint').replaceAll('%s', entityEditTypeLabel(entityType).toLowerCase());
  String entityNameRequired(String entityType) =>
      translate('entity_name_required').replaceAll('%s', entityEditTypeLabel(entityType));

  String get fieldCode => translate('field_code');
  String get fieldCodeHint => translate('field_code_hint');
  String get fieldDescription => translate('field_description');
  String get fieldDescriptionHint => translate('field_description_hint');
  String get fieldDisplayOrder => translate('field_display_order');
  String get fieldDisplayOrderHint => translate('field_display_order_hint');
  String get fieldActive => translate('field_active');

  String get indicatorEditNameLabel => translate('indicator_edit_name_label');
  String get indicatorEditNameHint => translate('indicator_edit_name_hint');
  String get indicatorEditNameRequired => translate('indicator_edit_name_required');
  String get indicatorEditTypeLabel => translate('indicator_edit_type_label');
  String get indicatorEditTypeRequired => translate('indicator_edit_type_required');
  String get indicatorEditUnitHint => translate('indicator_edit_unit_hint');
  String get indicatorEditDefinitionHint => translate('indicator_edit_definition_hint');
  String get indicatorEditSectorHint => translate('indicator_edit_sector_hint');
  String get indicatorEditSubsectorHint => translate('indicator_edit_subsector_hint');
  String get indicatorEditRelatedProgramsHint =>
      translate('indicator_edit_related_programs_hint');
  String get indicatorEditCommentsHint => translate('indicator_edit_comments_hint');
  String get indicatorEditCommentsLabel => translate('indicator_edit_comments_label');
  String get indicatorEditEmergency => translate('indicator_edit_emergency');
  String get indicatorEditSave => translate('indicator_edit_save');
  String get indicatorEditFdrsKpiLabel => translate('indicator_edit_fdrs_kpi_label');
  String get indicatorEditFdrsKpiHint => translate('indicator_edit_fdrs_kpi_hint');
  String get indicatorEditMultilingualSection =>
      translate('indicator_edit_multilingual_section');
  String indicatorEditNameForLanguage(String code) => translate('indicator_edit_name_for_language')
      .replaceAll('%s', code);
  String get indicatorEditSelectNone => translate('indicator_edit_select_none');
  String get indicatorEditSectorGroup => translate('indicator_edit_sector_group');
  String get indicatorEditSubsectorGroup => translate('indicator_edit_subsector_group');
  String get indicatorEditSectorLevelPrimary =>
      translate('indicator_edit_sector_level_primary');
  String get indicatorEditSectorLevelSecondary =>
      translate('indicator_edit_sector_level_secondary');
  String get indicatorEditSectorLevelTertiary =>
      translate('indicator_edit_sector_level_tertiary');

  String get genericUntitled => translate('generic_untitled');
  String get genericUntitledDocument => translate('generic_untitled_document');
  String get genericLowercaseResource => translate('generic_lowercase_resource');
  String get genericUnnamedIndicator => translate('generic_unnamed_indicator');
  String get genericUntitledResource => translate('generic_untitled_resource');

  // AI Chat strings
  String get aiPolicyAcknowledgeSnackbar => translate('ai_policy_acknowledge_snackbar');
  String get aiUsePolicyTitle => translate('ai_use_policy_title');
  String get aiPolicyDoNotShare => translate('ai_policy_do_not_share');
  String get aiPolicyTracesBody => translate('ai_policy_traces_body');
  String get aiPolicyPurposeTitle => translate('ai_policy_purpose_title');
  String get aiPolicyPurposeBody => translate('ai_policy_purpose_body');
  String get aiPolicyAcceptableUseTitle => translate('ai_policy_acceptable_use_title');
  String get aiPolicyAcceptableUseBody => translate('ai_policy_acceptable_use_body');
  String get aiPolicyAccuracyTitle => translate('ai_policy_accuracy_title');
  String get aiPolicyAccuracyBody => translate('ai_policy_accuracy_body');
  String get aiPolicyConfirmFooter => translate('ai_policy_confirm_footer');
  String get aiPolicyIUnderstand => translate('ai_policy_i_understand');
  String get aiPolicyAcknowledgeCta => translate('ai_policy_acknowledge_cta');
  String get aiSourcesHeading => translate('ai_sources_heading');
  String get aiSourceDatabank => translate('ai_source_databank');
  String get aiSourceSystemDocuments => translate('ai_source_system_documents');
  String get aiSourceUprDocuments => translate('ai_source_upr_documents');
  String get aiSourcesMinimumNote => translate('ai_sources_minimum_note');
  String get aiTourGuideQuestion => translate('ai_tour_guide_question');
  String get aiTourNavigateQuestion => translate('ai_tour_navigate_question');
  String get aiTourWebOnlySnackbar => translate('ai_tour_web_only_snackbar');
  String get aiNewChat => translate('ai_new_chat');
  String get aiSemanticOpenDrawerHint => translate('ai_semantic_open_drawer_hint');
  String get aiTooltipNewChat => translate('ai_tooltip_new_chat');
  String get aiSemanticNewChatLabel => translate('ai_semantic_new_chat_label');
  String get aiSemanticNewChatHint => translate('ai_semantic_new_chat_hint');
  String get aiBetaTesterBanner => translate('ai_beta_tester_banner');
  String get aiEmptyWelcome => translate('ai_empty_welcome');
  String get aiPolicyChipTitle => translate('ai_policy_chip_title');
  String get aiPolicySheetSummaryLine => translate('ai_policy_sheet_summary_line');
  String get aiPolicyCompactWarning => translate('ai_policy_compact_warning');
  String get aiReadFullPolicy => translate('ai_read_full_policy');
  String get aiTryAsking => translate('ai_try_asking');
  String get aiCopied => translate('ai_copied');
  String get aiTooltipCopy => translate('ai_tooltip_copy');
  String get aiTooltipEditMessage => translate('ai_tooltip_edit_message');
  String get aiTooltipHelpful => translate('ai_tooltip_helpful');
  String get aiTooltipNotHelpful => translate('ai_tooltip_not_helpful');
  String get aiFooterModelWarning => translate('ai_footer_model_warning');
  String get aiChatErrorNetwork => translate('ai_chat_error_network');
  String get aiChatErrorTimeout => translate('ai_chat_error_timeout');
  String get aiChatErrorServer => translate('ai_chat_error_server');

  String get aiAgentProgressTitle => translate('ai_agent_progress_title');
  String get aiAgentStepDone => translate('ai_agent_step_done');
  String get aiAgentStepPreparingQuery =>
      translate('ai_agent_step_preparing_query');
  String get aiAgentStepPlanning => translate('ai_agent_step_planning');
  String get aiAgentStepReviewing => translate('ai_agent_step_reviewing');
  String get aiAgentStepDrafting => translate('ai_agent_step_drafting');
  String get aiAgentStepReplying => translate('ai_agent_step_replying');
  String get aiAgentStepThinkingNext =>
      translate('ai_agent_step_thinking_next');
  String get aiAgentStepNoShortcutFull =>
      translate('ai_agent_step_no_shortcut_full');
  String aiAgentStepNoShortcutReviewing(String snippet) =>
      translate('ai_agent_step_no_shortcut_reviewing')
          .replaceAll('%s', snippet);
  String get aiResponseSources => translate('ai_response_sources');
  String aiResponseSourcesWithCount(int n) =>
      translate('ai_response_sources_with_count').replaceAll('%s', '$n');

  String get aiTooltipConfigureSources => translate('ai_tooltip_configure_sources');
  String get aiInputPolicyRequired => translate('ai_input_policy_required');
  String get aiInputPlaceholderMessage => translate('ai_input_placeholder_message');
  String get aiInputPlaceholderEdit => translate('ai_input_placeholder_edit');
  String get aiTooltipCancelEdit => translate('ai_tooltip_cancel_edit');
  String get aiStop => translate('ai_stop');
  String get aiConversationsDrawerTitle => translate('ai_conversations_drawer_title');
  String get aiSearchConversationsHint => translate('ai_search_conversations_hint');
  String get aiNoConversationsBody => translate('ai_no_conversations_body');
  String get aiNoConversationsOffline => translate('ai_no_conversations_offline');
  String get aiNoConversationsFiltered => translate('ai_no_conversations_filtered');
  String get aiSectionPinned => translate('ai_section_pinned');
  String get aiSectionRecent => translate('ai_section_recent');
  String get aiQuickPrompt1 => translate('ai_quick_prompt_1');
  String get aiQuickPrompt2 => translate('ai_quick_prompt_2');
  String get aiQuickPrompt3 => translate('ai_quick_prompt_3');
  String get aiQuickPrompt4 => translate('ai_quick_prompt_4');
  String get aiQuickPrompt5 => translate('ai_quick_prompt_5');
  String get aiClearAllDialogTitle => translate('ai_clear_all_dialog_title');
  String get aiClearAllDialogBody => translate('ai_clear_all_dialog_body');
  String get aiClearAllButton => translate('ai_clear_all_button');
  String get aiClearAllRow => translate('ai_clear_all_row');
  String get aiHelpAboutRow => translate('ai_help_about_row');
  String get aiPin => translate('ai_pin');
  String get aiUnpin => translate('ai_unpin');
  String get aiDeleteConversationTitle => translate('ai_delete_conversation_title');
  String get aiDeleteConversationBody => translate('ai_delete_conversation_body');
  String get aiNewChatTitleFallback => translate('ai_new_chat_title_fallback');
  String get aiHelpDialogTitle => translate('ai_help_dialog_title');
  String get aiHelpAboutHeading => translate('ai_help_about_heading');
  String get aiHelpAboutParagraph => translate('ai_help_about_paragraph');
  String get aiHelpFeaturesHeading => translate('ai_help_features_heading');
  String get aiHelpFeatureBullet1 => translate('ai_help_feature_bullet_1');
  String get aiHelpFeatureBullet2 => translate('ai_help_feature_bullet_2');
  String get aiHelpFeatureBullet3 => translate('ai_help_feature_bullet_3');
  String get aiHelpFeatureBullet4 => translate('ai_help_feature_bullet_4');
  String get aiHelpTipsHeading => translate('ai_help_tips_heading');
  String get aiHelpTipBullet1 => translate('ai_help_tip_bullet_1');
  String get aiHelpTipBullet2 => translate('ai_help_tip_bullet_2');
  String get aiHelpTipBullet3 => translate('ai_help_tip_bullet_3');
  String get aiHelpTipBullet4 => translate('ai_help_tip_bullet_4');
  String get aiGotIt => translate('ai_got_it');
  String get aiScoreConfidence => translate('ai_score_confidence');
  String get aiScoreGrounding => translate('ai_score_grounding');
  String get aiDefaultAssistantTitle => translate('ai_default_assistant_title');

  // AI
  String get aiAssistant => translate('ai_assistant');
}

class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  bool isSupported(Locale locale) {
    return ['en', 'es', 'fr', 'ar', 'hi', 'ru', 'zh']
        .contains(locale.languageCode);
  }

  @override
  Future<AppLocalizations> load(Locale locale) async {
    return AppLocalizations(locale);
  }

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}
