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
      'access_denied': 'Access Denied',
      'general': 'General',
      'document_management': 'Document Management',
      'translation_management': 'Translation Management',
      'plugin_management': 'Plugin Management',
      'system_configuration': 'System Configuration',
      'user_management': 'User Management',
      'manage_users': 'Manage Users',
      'form_data_management': 'Form & Data Management',
      'manage_templates': 'Manage Templates',
      'manage_assignments': 'Manage Assignments',
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
      'mark_all_read': 'Mark all as read',
      'mark_read': 'Mark as read',
      'mark_unread': 'Mark as unread',
      'delete': 'Delete',
      'archive': 'Archive',
      'unarchive': 'Unarchive',
      'send_push_notification': 'Send Push Notification',
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
      'built_by_haytham':
          'Built by Haytham Alsoufi,\nvolunteer of Syrian Arab Red Crescent',

      // Dashboard
      'national_society': 'National Society',
      'active': 'Active',
      'completed': 'Completed',
      'current_assignments': 'Current Assignments',
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
      'unknown': 'Unknown',
      'n_a': 'N/A',
      'enter_data': 'Enter Data',
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
      'no_plugins_found': 'No plugins found',
      'no_translations_found': 'No translations found',
      'no_documents_found': 'No documents found',
      'no_users_found': 'No users found',
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
      'access_denied': 'Acceso Denegado',
      'general': 'General',
      'document_management': 'Gestión de Documentos',
      'translation_management': 'Gestión de Traducciones',
      'plugin_management': 'Gestión de Complementos',
      'system_configuration': 'Configuración del Sistema',
      'user_management': 'Gestión de Usuarios',
      'manage_users': 'Gestionar Usuarios',
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
      'login_to_account': 'Iniciar Sesión',
      'logout': 'Cerrar Sesión',
      'are_you_sure_logout': '¿Está seguro de que desea cerrar sesión?',
      'cancel': 'Cancelar',
      'name': 'Nombre',
      'title': 'Título',
      'email': 'Correo Electrónico',
      'loading': 'Cargando...',
      'loading_home': 'Cargando Inicio...',
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
      'mark_all_read': 'Marcar todo como leído',
      'mark_read': 'Marcar como leído',
      'mark_unread': 'Marcar como no leído',
      'delete': 'Eliminar',
      'archive': 'Archivar',
      'unarchive': 'Desarchivar',
      'send_push_notification': 'Enviar Notificación Push',
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
      'built_by_haytham':
          'Construido por Haytham Alsoufi,\nvoluntario de la Media Luna Roja Árabe Siria',

      // Dashboard
      'national_society': 'Sociedad Nacional',
      'active': 'Activo',
      'completed': 'Completado',
      'current_assignments': 'Asignaciones Actuales',
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
      'unknown': 'Desconocido',
      'n_a': 'N/A',
      'enter_data': 'Ingresar Datos',
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
      'no_plugins_found': 'No se encontraron complementos',
      'no_translations_found': 'No se encontraron traducciones',
      'no_documents_found': 'No se encontraron documentos',
      'no_users_found': 'No se encontraron usuarios',
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
      'access_denied': 'Accès Refusé',
      'general': 'Général',
      'document_management': 'Gestion des Documents',
      'translation_management': 'Gestion des Traductions',
      'plugin_management': 'Gestion des Plugins',
      'system_configuration': 'Configuration du Système',
      'user_management': 'Gestion des Utilisateurs',
      'manage_users': 'Gérer les Utilisateurs',
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
      'login_to_account': 'Se Connecter',
      'logout': 'Déconnexion',
      'are_you_sure_logout': 'Êtes-vous sûr de vouloir vous déconnecter?',
      'cancel': 'Annuler',
      'name': 'Nom',
      'title': 'Titre',
      'email': 'E-mail',
      'loading': 'Chargement...',
      'loading_home': 'Chargement de l\'Accueil...',
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
      'mark_all_read': 'Tout marquer comme lu',
      'mark_read': 'Marquer comme lu',
      'mark_unread': 'Marquer comme non lu',
      'delete': 'Supprimer',
      'archive': 'Archiver',
      'unarchive': 'Désarchiver',
      'send_push_notification': 'Envoyer une Notification Push',
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
      'built_by_haytham':
          'Construit par Haytham Alsoufi,\nbénévole du Croissant-Rouge Arabe Syrien',

      // Dashboard
      'national_society': 'Société Nationale',
      'active': 'Actif',
      'completed': 'Terminé',
      'current_assignments': 'Assignations Actuelles',
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
      'unknown': 'Inconnu',
      'n_a': 'N/A',
      'enter_data': 'Saisir les Données',
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
      'no_plugins_found': 'Aucun plugin trouvé',
      'no_translations_found': 'Aucune traduction trouvée',
      'no_documents_found': 'Aucun document trouvé',
      'no_users_found': 'Aucun utilisateur trouvé',
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
      'access_denied': 'تم رفض الوصول',
      'general': 'عام',
      'document_management': 'إدارة المستندات',
      'translation_management': 'إدارة الترجمات',
      'plugin_management': 'إدارة الإضافات',
      'system_configuration': 'إعدادات النظام',
      'user_management': 'إدارة المستخدمين',
      'manage_users': 'إدارة المستخدمين',
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
      'login_to_account': 'تسجيل الدخول',
      'logout': 'تسجيل الخروج',
      'are_you_sure_logout': 'هل أنت متأكد من تسجيل الخروج؟',
      'cancel': 'إلغاء',
      'name': 'الاسم',
      'title': 'المسمى الوظيفي',
      'email': 'البريد الإلكتروني',
      'loading': 'جاري التحميل...',
      'loading_home': 'جاري تحميل الصفحة الرئيسية...',
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
      'mark_all_read': 'تعليم الكل كمقروء',
      'mark_read': 'تعليم كمقروء',
      'mark_unread': 'تعليم كغير مقروء',
      'delete': 'حذف',
      'archive': 'أرشفة',
      'unarchive': 'إلغاء الأرشفة',
      'send_push_notification': 'إرسال إشعار دفع',
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
      'built_by_haytham':
          'تم بناؤه بواسطة هيثم الصوفي،\nمتطوع في الهلال الأحمر العربي السوري',

      // Dashboard
      'national_society': 'الجمعية الوطنية',
      'active': 'نشط',
      'completed': 'مكتمل',
      'current_assignments': 'المهام الحالية',
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
      'unknown': 'غير معروف',
      'n_a': 'غير متاح',
      'enter_data': 'إدخال البيانات',
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
      'no_plugins_found': 'لم يتم العثور على إضافات',
      'no_translations_found': 'لم يتم العثور على ترجمات',
      'no_documents_found': 'لم يتم العثور على مستندات',
      'no_users_found': 'لم يتم العثور على مستخدمين',
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
      'access_denied': 'पहुंच अस्वीकृत',
      'general': 'सामान्य',
      'document_management': 'दस्तावेज़ प्रबंधन',
      'translation_management': 'अनुवाद प्रबंधन',
      'plugin_management': 'प्लगइन प्रबंधन',
      'system_configuration': 'सिस्टम कॉन्फ़िगरेशन',
      'user_management': 'उपयोगकर्ता प्रबंधन',
      'manage_users': 'उपयोगकर्ता प्रबंधित करें',
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
      'login_to_account': 'खाते में लॉगिन करें',
      'logout': 'लॉगआउट',
      'are_you_sure_logout': 'क्या आप लॉगआउट करना चाहते हैं?',
      'cancel': 'रद्द करें',
      'name': 'नाम',
      'title': 'शीर्षक',
      'email': 'ईमेल',
      'loading': 'लोड हो रहा है...',
      'loading_home': 'होम लोड हो रहा है...',
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
      'mark_all_read': 'सभी को पढ़ा हुआ चिह्नित करें',
      'mark_read': 'पढ़ा हुआ चिह्नित करें',
      'mark_unread': 'अपठित चिह्नित करें',
      'delete': 'हटाएं',
      'archive': 'संग्रहीत करें',
      'unarchive': 'असंग्रहीत करें',
      'send_push_notification': 'पुश अधिसूचना भेजें',
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
      'built_by_haytham':
          'हयथम अलसौफी द्वारा निर्मित,\nसीरियाई अरब रेड क्रिसेंट के स्वयंसेवक',

      // Dashboard
      'national_society': 'राष्ट्रीय समाज',
      'active': 'सक्रिय',
      'completed': 'पूर्ण',
      'current_assignments': 'वर्तमान असाइनमेंट',
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
      'unknown': 'अज्ञात',
      'n_a': 'अनुपलब्ध',
      'enter_data': 'डेटा दर्ज करें',
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
      'no_plugins_found': 'कोई प्लगइन नहीं मिला',
      'no_translations_found': 'कोई अनुवाद नहीं मिला',
      'no_documents_found': 'कोई दस्तावेज नहीं मिला',
      'no_users_found': 'कोई उपयोगकर्ता नहीं मिला',
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
      'access_denied': 'Доступ Запрещен',
      'general': 'Общее',
      'document_management': 'Управление Документами',
      'translation_management': 'Управление Переводами',
      'plugin_management': 'Управление Плагинами',
      'system_configuration': 'Конфигурация Системы',
      'user_management': 'Управление Пользователями',
      'manage_users': 'Управлять Пользователями',
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
      'login_to_account': 'Войти в Аккаунт',
      'logout': 'Выйти',
      'are_you_sure_logout': 'Вы уверены, что хотите выйти?',
      'cancel': 'Отмена',
      'name': 'Имя',
      'title': 'Должность',
      'email': 'Электронная Почта',
      'loading': 'Загрузка...',
      'loading_home': 'Загрузка Главной...',
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
      'mark_all_read': 'Отметить все как прочитанные',
      'mark_read': 'Отметить как прочитанное',
      'mark_unread': 'Отметить как непрочитанное',
      'delete': 'Удалить',
      'archive': 'Архивировать',
      'unarchive': 'Разархивировать',
      'send_push_notification': 'Отправить Push-уведомление',
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
      'built_by_haytham':
          'Создано Хайтамом Аль-Суфи,\nволонтером Сирийского Арабского Красного Полумесяца',

      // Dashboard
      'national_society': 'Национальное Общество',
      'active': 'Активный',
      'completed': 'Завершен',
      'current_assignments': 'Текущие Назначения',
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
      'unknown': 'Неизвестно',
      'n_a': 'Н/Д',
      'enter_data': 'Ввести Данные',
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
      'no_plugins_found': 'Плагины не найдены',
      'no_translations_found': 'Переводы не найдены',
      'no_documents_found': 'Документы не найдены',
      'no_users_found': 'Пользователи не найдены',
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
      'access_denied': '访问被拒绝',
      'general': '常规',
      'document_management': '文档管理',
      'translation_management': '翻译管理',
      'plugin_management': '插件管理',
      'system_configuration': '系统配置',
      'user_management': '用户管理',
      'manage_users': '管理用户',
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
      'login_to_account': '登录账户',
      'logout': '登出',
      'are_you_sure_logout': '您确定要登出吗？',
      'cancel': '取消',
      'name': '姓名',
      'title': '职位',
      'email': '电子邮件',
      'loading': '加载中...',
      'loading_home': '加载首页...',
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
      'mark_all_read': '全部标记为已读',
      'mark_read': '标记为已读',
      'mark_unread': '标记为未读',
      'delete': '删除',
      'archive': '归档',
      'unarchive': '取消归档',
      'send_push_notification': '发送推送通知',
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
      'built_by_haytham': '由Haytham Alsoufi构建，\n叙利亚阿拉伯红新月会志愿者',

      // Dashboard
      'national_society': '国家协会',
      'active': '活跃',
      'completed': '已完成',
      'current_assignments': '当前任务',
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
      'unknown': '未知',
      'n_a': '不适用',
      'enter_data': '输入数据',
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
      'no_plugins_found': '未找到插件',
      'no_translations_found': '未找到翻译',
      'no_documents_found': '未找到文档',
      'no_users_found': '未找到用户',
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
    },
  };

  String translate(String key) {
    final translations =
        _translations[locale.languageCode] ?? _translations['en']!;
    return translations[key] ?? key;
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
  String get accessDenied => translate('access_denied');
  String get general => translate('general');
  String get documentManagement => translate('document_management');
  String get translationManagement => translate('translation_management');
  String get pluginManagement => translate('plugin_management');
  String get systemConfiguration => translate('system_configuration');
  String get userManagement => translate('user_management');
  String get manageUsers => translate('manage_users');
  String get formDataManagement => translate('form_data_management');
  String get manageTemplates => translate('manage_templates');
  String get manageAssignments => translate('manage_assignments');
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
  String get loginToAccount => translate('login_to_account');
  String get logout => translate('logout');
  String get areYouSureLogout => translate('are_you_sure_logout');
  String get cancel => translate('cancel');
  String get name => translate('name');
  String get title => translate('title');
  String get email => translate('email');
  String get loading => translate('loading');
  String get loadingHome => translate('loading_home');
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
  String get markAllRead => translate('mark_all_read');
  String get markRead => translate('mark_read');
  String get markUnread => translate('mark_unread');
  String get delete => translate('delete');
  String get archive => translate('archive');
  String get unarchive => translate('unarchive');
  String get sendPushNotification => translate('send_push_notification');
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
  String get unknown => translate('unknown');
  String get nA => translate('n_a');
  String get enterData => translate('enter_data');
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
  String get noPluginsFound => translate('no_plugins_found');
  String get noTranslationsFound => translate('no_translations_found');
  String get noDocumentsFound => translate('no_documents_found');
  String get noUsersFound => translate('no_users_found');
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
  String get builtByHaytham => translate('built_by_haytham');

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
