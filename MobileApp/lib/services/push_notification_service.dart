import 'dart:async';
import 'dart:io';
import 'dart:convert';
import 'dart:math';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:flutter/material.dart';
import 'package:device_info_plus/device_info_plus.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';
import '../config/app_config.dart';
import '../config/routes.dart';
import 'api_service.dart';
import '../utils/debug_logger.dart';

/// Top-level function to handle background messages
@pragma('vm:entry-point')
Future<void> firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    await Firebase.initializeApp();
  } catch (e) {
    DebugLogger.logError('Failed to init Firebase in background: $e');
  }
  DebugLogger.logNotifications(
      'Background message received: ${message.messageId}');
  // Handle background message here if needed
}

class PushNotificationService {
  static final PushNotificationService _instance =
      PushNotificationService._internal();
  factory PushNotificationService() => _instance;
  PushNotificationService._internal();

  FirebaseMessaging? _firebaseMessaging;
  FirebaseMessaging get _messaging {
    _firebaseMessaging ??= FirebaseMessaging.instance;
    return _firebaseMessaging!;
  }

  final FlutterLocalNotificationsPlugin _localNotifications =
      FlutterLocalNotificationsPlugin();
  final ApiService _api = ApiService();

  bool _initialized = false;
  String? _currentToken;
  GlobalKey<NavigatorState>? _navigatorKey;
  Timer? _heartbeatTimer;

  /// Initialize push notifications
  Future<void> initialize() async {
    if (_initialized) {
      DebugLogger.logNotifications('Push notifications already initialized');
      DebugLogger.logNotifications(
          'Note: Use ensureDeviceRegistered() after login to force device registration');
      return;
    }

    DebugLogger.logNotifications(
        'Starting push notification initialization...');

    try {
      // On iOS, we still register the device for tracking purposes,
      // but skip Firebase push notification setup since it's disabled
      if (Platform.isIOS) {
        DebugLogger.logNotifications(
            'iOS detected - registering device for tracking (push notifications disabled)');
        // Register device with a placeholder token for iOS
        // This allows the backend to track that the user has the app installed
        await _registerIOSDevice();
        // Start heartbeat for device activity tracking
        _startHeartbeat();
        _initialized = true;
        DebugLogger.logNotifications('✅ iOS device registered for tracking');
        return;
      }

      // Android: Full push notification setup
      // Request permission
      DebugLogger.logNotifications('Requesting notification permissions...');
      NotificationSettings settings = await _messaging.requestPermission(
        alert: true,
        badge: true,
        sound: true,
        provisional: false,
      );

      if (settings.authorizationStatus == AuthorizationStatus.authorized) {
        DebugLogger.logNotifications('✅ User granted notification permission');
      } else if (settings.authorizationStatus ==
          AuthorizationStatus.provisional) {
        DebugLogger.logWarn(
            'PUSH', '⚠️ User granted provisional notification permission');
      } else {
        DebugLogger.logWarn('PUSH', '❌ User declined notification permission');
        return;
      }

      // Initialize local notifications
      await _initializeLocalNotifications();

      // Set up message handlers
      FirebaseMessaging.onMessage.listen(_handleForegroundMessage);
      FirebaseMessaging.onMessageOpenedApp.listen(_handleMessageOpened);

      // Handle notification when app is opened from terminated state
      RemoteMessage? initialMessage = await _messaging.getInitialMessage();
      if (initialMessage != null) {
        _handleMessageOpened(initialMessage);
      }

      // Set background message handler
      FirebaseMessaging.onBackgroundMessage(firebaseMessagingBackgroundHandler);

      // Get and register FCM token
      DebugLogger.logNotifications(
          'Getting FCM token and registering device...');
      await _registerToken();

      // Listen for token refresh
      _messaging.onTokenRefresh.listen((newToken) {
        DebugLogger.logNotifications('FCM token refreshed: $newToken');
        _currentToken = newToken;
        _registerTokenWithBackend(newToken);
      });

      // Start heartbeat for device activity tracking
      _startHeartbeat();

      _initialized = true;
      DebugLogger.logNotifications(
          '✅ Push notifications initialized successfully');
    } catch (e, stackTrace) {
      DebugLogger.logError('❌ Error initializing push notifications: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
      // Don't set _initialized to true if initialization failed
    }
  }

  /// Ensure device is registered with backend (can be called even if already initialized)
  /// This is useful after login to make sure the device is registered for the current user
  Future<void> ensureDeviceRegistered() async {
    DebugLogger.logNotifications(
        'Ensuring device is registered with backend...');
    DebugLogger.logNotifications(
        'Current state: initialized=$_initialized, hasToken=${_currentToken != null}');

    try {
      // On iOS, register device if not already registered
      if (Platform.isIOS) {
        if (_currentToken == null) {
          DebugLogger.logNotifications(
              'No iOS device token found, registering...');
          await _registerIOSDevice();
        } else {
          // Re-register to update user_id if needed
          DebugLogger.logNotifications(
              'Re-registering iOS device to ensure correct user_id...');
          await _registerTokenWithBackend(_currentToken!);
        }
        // Ensure heartbeat is running
        if (!_initialized) {
          _startHeartbeat();
          _initialized = true;
        }
        DebugLogger.logNotifications('✅ iOS device registration ensured');
        return;
      }

      // Android: Ensure we have a token and it's registered
      if (!_initialized) {
        // Not initialized yet, do full initialization
        DebugLogger.logNotifications(
            'Not initialized, performing full initialization...');
        await initialize();
        return;
      }

      // Already initialized, but check if we have a token
      DebugLogger.logNotifications(
          'Service already initialized, checking token status...');
      if (_currentToken == null) {
        DebugLogger.logWarn('PUSH',
            '⚠️ Initialized but no token found, attempting to get token...');
        await _registerToken();
        if (_currentToken == null) {
          DebugLogger.logWarn(
              'PUSH', '❌ Still no token after registration attempt');
          return;
        }
      } else {
        // We have a token, re-register to ensure it's associated with current user
        DebugLogger.logNotifications(
            'Re-registering device token (${_currentToken!.substring(0, 20)}...) to ensure correct user_id...');
        await _registerTokenWithBackend(_currentToken!);
      }

      // Ensure heartbeat is running
      if (_heartbeatTimer == null) {
        DebugLogger.logNotifications('Starting heartbeat timer...');
        _startHeartbeat();
      }

      DebugLogger.logNotifications('✅ Device registration ensured');
    } catch (e, stackTrace) {
      DebugLogger.logError('❌ Error ensuring device registration: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    }
  }

  /// Initialize local notifications for foreground display
  Future<void> _initializeLocalNotifications() async {
    const AndroidInitializationSettings androidSettings =
        AndroidInitializationSettings('@mipmap/ic_launcher');
    const DarwinInitializationSettings iosSettings =
        DarwinInitializationSettings(
      requestAlertPermission: true,
      requestBadgePermission: true,
      requestSoundPermission: true,
    );

    const InitializationSettings initSettings = InitializationSettings(
      android: androidSettings,
      iOS: iosSettings,
    );

    await _localNotifications.initialize(
      initSettings,
      onDidReceiveNotificationResponse: (NotificationResponse response) {
        DebugLogger.logNotifications(
            'Notification tapped: ${response.payload}');
        // Handle notification tap navigation
        if (response.payload != null && response.payload!.isNotEmpty) {
          try {
            // Payload is a string representation of the data map
            // Parse it to extract redirect_url
            final payload = response.payload!;
            // The payload is stored as data.toString(), so we need to parse it
            // Try to extract redirect_url from the payload string
            _handleNotificationNavigation(payload);
          } catch (e) {
            DebugLogger.logNotifications(
                'Error parsing notification payload: $e');
          }
        }
      },
    );
  }

  /// Handle foreground messages
  Future<void> _handleForegroundMessage(RemoteMessage message) async {
    DebugLogger.logNotifications(
        'Foreground message received: ${message.messageId}');

    // Show local notification when app is in foreground
    if (message.notification != null) {
      // Store redirect_url in payload for local notification tap handling
      String payload = '';
      if (message.data.containsKey('redirect_url')) {
        payload = 'redirect_url: ${message.data['redirect_url']}';
      }

      await _showLocalNotification(
        message.notification!.title ?? 'Notification',
        message.notification!.body ?? '',
        message.data,
        payload: payload,
      );
    }
  }

  /// Handle message when app is opened from notification
  void _handleMessageOpened(RemoteMessage message) {
    DebugLogger.logNotifications(
        'App opened from notification: ${message.messageId}');
    // Handle navigation to specific screen based on message data
    final redirectUrl = message.data['redirect_url'];
    if (redirectUrl != null &&
        redirectUrl is String &&
        redirectUrl.isNotEmpty) {
      _navigateToRoute(redirectUrl);
    }
  }

  /// Handle notification navigation from payload string
  void _handleNotificationNavigation(String payload) {
    try {
      DebugLogger.logNotifications('Parsing notification payload: $payload');

      // Try to parse the payload to extract redirect_url
      // The payload format can be:
      // - "redirect_url: /dashboard" (simple format we create)
      // - "{redirect_url: /dashboard, ...}" (map string format)
      String? redirectUrl;

      // Try simple format first: "redirect_url: /dashboard"
      if (payload.startsWith('redirect_url:')) {
        redirectUrl = payload.substring('redirect_url:'.length).trim();
      } else if (payload.contains('redirect_url')) {
        // Try to extract from map-like string: "{redirect_url: /dashboard, ...}"
        final regex = RegExp(r'redirect_url[:\s]+([^\s,}]+)');
        final match = regex.firstMatch(payload);
        if (match != null) {
          redirectUrl =
              match.group(1)?.replaceAll("'", '').replaceAll('"', '').trim();
        }
      }

      if (redirectUrl != null && redirectUrl.isNotEmpty) {
        DebugLogger.logNotifications('Found redirect URL: $redirectUrl');
        _navigateToRoute(redirectUrl);
      } else {
        DebugLogger.logNotifications('No redirect URL found in payload');
      }
    } catch (e) {
      DebugLogger.logNotifications(
          'Error handling notification navigation: $e');
    }
  }

  /// Navigate to a route (URL or app screen)
  void _navigateToRoute(String route) async {
    if (_navigatorKey?.currentState == null) {
      DebugLogger.logNotifications(
          'Navigator not available, queueing navigation: $route');
      // Queue navigation for when navigator is available
      Future.delayed(const Duration(milliseconds: 500), () {
        _navigateToRoute(route);
      });
      return;
    }

    try {
      DebugLogger.logNotifications('Navigating to: $route');

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
          DebugLogger.logNotifications('Download started: $fullUrl');
        } else {
          DebugLogger.logNotifications('Could not start download: $fullUrl');
        }
        return;
      }

      // If it's a full URL, open in webview
      if (route.startsWith('http://') || route.startsWith('https://')) {
        _navigatorKey!.currentState!.pushNamed(
          AppRoutes.webview,
          arguments: route,
        );
      } else if (route.startsWith('/')) {
        // Relative path - navigate to app screen or webview
        // Check if it's a known app route
        if (route == AppRoutes.dashboard ||
            route == AppRoutes.notifications ||
            route == AppRoutes.settings ||
            route.startsWith(AppRoutes.admin) ||
            route.startsWith('/admin')) {
          // App screen route
          _navigatorKey!.currentState!.pushNamed(route);
        } else {
          // Likely a web route - open in webview
          final fullUrl = '${AppConfig.frontendUrl}$route';
          _navigatorKey!.currentState!.pushNamed(
            AppRoutes.webview,
            arguments: fullUrl,
          );
        }
      }
    } catch (e) {
      DebugLogger.logNotifications('Error navigating to route $route: $e');
    }
  }

  /// Set the navigator key for navigation
  void setNavigatorKey(GlobalKey<NavigatorState> navigatorKey) {
    _navigatorKey = navigatorKey;
  }

  /// Show local notification
  Future<void> _showLocalNotification(
    String title,
    String body,
    Map<String, dynamic> data, {
    String? payload,
  }) async {
    const AndroidNotificationDetails androidDetails =
        AndroidNotificationDetails(
      'ifrc_databank_channel',
      'IFRC Databank Notifications',
      channelDescription: 'Notifications for IFRC Network Databank',
      importance: Importance.high,
      priority: Priority.high,
      showWhen: true,
    );

    const DarwinNotificationDetails iosDetails = DarwinNotificationDetails(
      presentAlert: true,
      presentBadge: true,
      presentSound: true,
    );

    const NotificationDetails details = NotificationDetails(
      android: androidDetails,
      iOS: iosDetails,
    );

    // Use provided payload or generate from data
    final notificationPayload = payload ??
        (data.containsKey('redirect_url')
            ? 'redirect_url: ${data['redirect_url']}'
            : data.toString());

    await _localNotifications.show(
      DateTime.now().millisecondsSinceEpoch.remainder(100000),
      title,
      body,
      details,
      payload: notificationPayload,
    );
  }

  /// Register iOS device with backend (for tracking purposes, no push notifications)
  Future<void> _registerIOSDevice() async {
    try {
      // Generate or retrieve a persistent unique device identifier for iOS
      // Since iOS doesn't allow unique device IDs, we generate a UUID and store it
      final prefs = await SharedPreferences.getInstance();
      String? deviceId = prefs.getString('ios_device_token');

      if (deviceId == null) {
        // Generate a new UUID for this device
        deviceId = _generateUUID();
        await prefs.setString('ios_device_token', deviceId);
        DebugLogger.logNotifications(
            'Generated new iOS device identifier: ${deviceId.substring(0, 20)}...');
      } else {
        DebugLogger.logNotifications(
            'Using existing iOS device identifier: ${deviceId.substring(0, 20)}...');
      }

      _currentToken = deviceId;

      DebugLogger.logNotifications('Registering iOS device with backend...');
      await _registerTokenWithBackend(deviceId);
    } catch (e, stackTrace) {
      DebugLogger.logError('❌ Error registering iOS device: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    }
  }

  /// Generate a UUID v4-like string
  String _generateUUID() {
    final random = Random();
    final bytes = List<int>.generate(16, (i) => random.nextInt(256));

    // Set version (4) and variant bits
    bytes[6] = (bytes[6] & 0x0f) | 0x40; // Version 4
    bytes[8] = (bytes[8] & 0x3f) | 0x80; // Variant 10

    // Convert to hex string with dashes
    final hex = bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join();
    return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20, 32)}';
  }

  /// Register FCM token with backend
  Future<void> _registerToken() async {
    try {
      DebugLogger.logNotifications('Requesting FCM token from Firebase...');
      String? token = await _messaging.getToken();
      if (token != null) {
        _currentToken = token;
        DebugLogger.logNotifications(
            '✅ FCM token obtained: ${token.substring(0, 50)}...');
        await _registerTokenWithBackend(token);
      } else {
        DebugLogger.logWarn('PUSH', '❌ Failed to get FCM token (null)');
      }
    } catch (e) {
      DebugLogger.logError('❌ Error getting FCM token: $e');
    }
  }

  /// Register token with backend API
  Future<void> _registerTokenWithBackend(String token) async {
    try {
      final platform = Platform.isIOS ? 'ios' : 'android';
      final packageInfo = await _getPackageInfo();
      final deviceInfo = await _getDeviceInfo();

      final endpoint = '${AppConfig.notificationsEndpoint}/devices/register';
      final body = {
        'device_token': token,
        'platform': platform,
        'app_version': packageInfo['version'] ?? '1.0.0',
        'device_model': deviceInfo['device_model'],
        'device_name': deviceInfo['device_name'],
        'os_version': deviceInfo['os_version'],
        'timezone': deviceInfo['timezone'],
      };

      DebugLogger.logNotifications('Registering device with backend...');
      DebugLogger.logNotifications('Endpoint: $endpoint');
      DebugLogger.logNotifications('Platform: $platform');
      DebugLogger.logNotifications(
          'Device Model: ${deviceInfo['device_model']}');
      DebugLogger.logNotifications('OS Version: ${deviceInfo['os_version']}');

      final response = await _api.post(endpoint, body: body);

      DebugLogger.logNotifications(
          'Backoffice response status: ${response.statusCode}');
      DebugLogger.logNotifications('Backoffice response body: ${response.body}');

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        DebugLogger.logNotifications('✅ Device registered successfully: $data');
      } else {
        DebugLogger.logError(
            '❌ Failed to register device: ${response.statusCode}');
        DebugLogger.logError('Response: ${response.body}');
      }
    } catch (e, stackTrace) {
      DebugLogger.logError('❌ Error registering device: $e');
      DebugLogger.logError('Stack trace: $stackTrace');
    }
  }

  /// Unregister device from backend
  Future<void> unregisterDevice() async {
    if (_currentToken == null) {
      return;
    }

    try {
      final response = await _api.post(
        '${AppConfig.notificationsEndpoint}/devices/unregister',
        body: {
          'device_token': _currentToken,
        },
      );

      if (response.statusCode == 200) {
        DebugLogger.logNotifications('Device unregistered successfully');
        _currentToken = null;
      } else {
        DebugLogger.logNotifications(
            'Failed to unregister device: ${response.statusCode}');
      }
    } catch (e) {
      DebugLogger.logNotifications('Error unregistering device: $e');
    }
  }

  /// Get package info for app version
  Future<Map<String, String>> _getPackageInfo() async {
    try {
      final packageInfo = await PackageInfo.fromPlatform();
      return {
        'version': packageInfo.version,
        'buildNumber': packageInfo.buildNumber,
      };
    } catch (e) {
      DebugLogger.logWarn('PUSH', 'Error getting package info: $e');
      return {'version': '1.0.0'};
    }
  }

  /// Get device information
  Future<Map<String, String?>> _getDeviceInfo() async {
    try {
      final deviceInfoPlugin = DeviceInfoPlugin();
      String? deviceModel;
      String? deviceName;
      String? osVersion;

      if (Platform.isIOS) {
        final iosInfo = await deviceInfoPlugin.iosInfo;
        deviceModel = iosInfo.model;
        deviceName = iosInfo.name;
        osVersion = 'iOS ${iosInfo.systemVersion}';
      } else if (Platform.isAndroid) {
        final androidInfo = await deviceInfoPlugin.androidInfo;
        deviceModel = '${androidInfo.manufacturer} ${androidInfo.model}';
        deviceName = androidInfo.device; // Android device name
        osVersion = 'Android ${androidInfo.version.release}';
      }

      // Get timezone offset (e.g., "+05:30", "-08:00")
      final now = DateTime.now();
      final offset = now.timeZoneOffset;
      final hours = offset.inHours;
      final minutes = offset.inMinutes.remainder(60).abs();
      final timezoneOffset =
          '${offset.isNegative ? '-' : '+'}${hours.abs().toString().padLeft(2, '0')}:${minutes.toString().padLeft(2, '0')}';
      final timezone = '${now.timeZoneName} ($timezoneOffset)';

      return {
        'device_model': deviceModel,
        'device_name': deviceName,
        'os_version': osVersion,
        'timezone': timezone,
      };
    } catch (e) {
      DebugLogger.logWarn('PUSH', 'Error getting device info: $e');
      return {
        'device_model': null,
        'device_name': null,
        'os_version': null,
        'timezone': null,
      };
    }
  }

  /// Get current FCM token
  String? get currentToken => _currentToken;

  /// Check if push notifications are initialized
  bool get isInitialized => _initialized;

  /// Start periodic heartbeat to update device activity (every 5 minutes)
  void _startHeartbeat() {
    // Stop existing timer if any
    _heartbeatTimer?.cancel();

    // Send initial heartbeat after 30 seconds (give app time to fully load)
    Future.delayed(const Duration(seconds: 30), () {
      _sendHeartbeat();
    });

    // Then send heartbeat every 5 minutes
    _heartbeatTimer = Timer.periodic(const Duration(minutes: 5), (_) {
      _sendHeartbeat();
    });

    DebugLogger.logNotifications('✅ Heartbeat started (every 5 minutes)');
  }

  /// Stop heartbeat timer
  void _stopHeartbeat() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
    DebugLogger.logNotifications('Heartbeat stopped');
  }

  /// Send heartbeat to backend
  Future<void> _sendHeartbeat() async {
    // For iOS, we might not have a token yet if registration failed
    // Try to register if we don't have a token
    if (_currentToken == null) {
      if (Platform.isIOS) {
        DebugLogger.logWarn(
            'PUSH', 'No iOS device token, attempting to register...');
        await _registerIOSDevice();
      }
      // If still no token, skip heartbeat
      if (_currentToken == null) {
        return;
      }
    }

    try {
      final endpoint = '${AppConfig.notificationsEndpoint}/devices/heartbeat';
      final response = await _api.post(
        endpoint,
        body: {'device_token': _currentToken},
      );

      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        if (data['updated'] == true) {
          DebugLogger.logNotifications('✅ Heartbeat sent successfully');
        } else {
          DebugLogger.logNotifications('Heartbeat throttled (too soon)');
        }
      }
    } catch (e) {
      // Silently fail - heartbeat is non-critical
      DebugLogger.logWarn('PUSH', 'Heartbeat error (non-critical): $e');
    }
  }

  /// Dispose resources
  void dispose() {
    _stopHeartbeat();
  }
}
