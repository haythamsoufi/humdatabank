import 'package:flutter/foundation.dart';
import 'dart:convert';
import '../../models/shared/user.dart';
import '../../services/auth_service.dart';
import '../../services/user_profile_service.dart';
import '../../services/storage_service.dart';
import '../../services/api_service.dart';
import '../../services/push_notification_service.dart';
import '../../config/app_config.dart';
import '../../utils/debug_logger.dart';
import '../../services/api_service.dart' show AuthenticationException;

class AuthProvider with ChangeNotifier {
  final AuthService _authService = AuthService();
  final StorageService _storage = StorageService();

  User? _user;
  bool _isLoading = false;
  String? _error;
  bool _authCheckedThisSession = false;

  User? get user => _user;
  bool get isLoading => _isLoading;
  String? get error => _error;
  bool get isAuthenticated => _user != null;

  Future<bool> checkAuthStatus({bool forceRevalidate = false}) async {
    // Skip redundant non-forced checks within the same session to avoid
    // duplicate device registration calls from multiple screens.
    if (_authCheckedThisSession && !forceRevalidate && _user != null) {
      return true;
    }

    // Load user from cache first (synchronous, fast)
    await _loadUserFromCache();

    // If we have cached user and not forcing revalidation, notify listeners immediately
    // This allows UI to render while we validate in background
    if (_user != null && !forceRevalidate) {
      notifyListeners();
    }

    // Set loading if we don't have cached user or forcing revalidation
    if (_user == null || forceRevalidate) {
      _isLoading = true;
      notifyListeners();
    }

    try {
      // Always validate session (forceRevalidate ensures fresh validation on app start)
      final isLoggedIn =
          await _authService.isLoggedIn(forceRevalidate: forceRevalidate);
      if (isLoggedIn) {
        // Always refresh user from AuthService to get latest data including profile color
        _user = _authService.currentUser;
        if (_user != null) {
          await _saveUserToCache(_user!);
          DebugLogger.logAuth(
              'User loaded from backend: ${_user!.email}, profile_color: ${_user!.profileColor ?? "null"}');

          // Register device for push notifications if user is already logged in
          try {
            // Use ensureDeviceRegistered to force registration even if already initialized
            await PushNotificationService().ensureDeviceRegistered();
          } catch (e) {
            // Don't fail auth check if push notification registration fails
            DebugLogger.logWarn(
                'AUTH', 'Failed to register device during auth check: $e');
          }
        } else {
          // No user after login - session might be invalid
          _user = null;
          await _storage.remove(AppConfig.cachedUserProfileKey);
          return false;
        }
      } else {
        // Session invalid, clear cached user
        _user = null;
        await _storage.remove(AppConfig.cachedUserProfileKey);
      }
      if (isLoggedIn) _authCheckedThisSession = true;
      return isLoggedIn;
    } catch (e) {
      _error = e.toString();
      DebugLogger.logError('Error checking auth status: $e');
      // On error, only keep cached user if we're not forcing revalidation
      if (forceRevalidate) {
        // Force revalidation failed - clear user
        _user = null;
        await _storage.remove(AppConfig.cachedUserProfileKey);
        return false;
      }
      // If we have cached user and not forcing revalidation, assume still logged in
      if (_user == null) {
        return false;
      }
      return true;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  // Refresh user from AuthService (useful after role update)
  // This will reload the user profile from backend to get latest data including profile color
  Future<void> refreshUser() async {
    try {
      DebugLogger.logAuth('refreshUser: calling isLoggedIn(forceRevalidate: true)');
      final isLoggedIn = await _authService.isLoggedIn(forceRevalidate: true);
      DebugLogger.logAuth(
          'refreshUser: isLoggedIn=$isLoggedIn, '
          'currentUser=${_authService.currentUser?.email ?? "null"}');
      if (isLoggedIn) {
        _user = _authService.currentUser;
        if (_user != null) {
          await _saveUserToCache(_user!);
          DebugLogger.logAuth(
              'refreshUser: profile loaded from backend '
              '(${_user!.email}, role: ${_user!.role})');
        } else {
          DebugLogger.logWarn('AUTH',
              'refreshUser: isLoggedIn=true but currentUser is null');
        }
      } else {
        DebugLogger.logWarn('AUTH',
            'refreshUser: isLoggedIn returned false — '
            'user profile not available');
      }
      notifyListeners();
    } catch (e) {
      DebugLogger.logError('refreshUser error: $e');
      _user = _authService.currentUser;
      if (_user != null) {
        await _saveUserToCache(_user!);
        DebugLogger.logWarn('AUTH',
            'refreshUser: fell back to cached user '
            '(${_user!.email}, error: $e)');
      } else {
        DebugLogger.logWarn('AUTH',
            'refreshUser: no cached user available either (error: $e)');
      }
      notifyListeners();
    }
  }

  Future<void> _loadUserFromCache() async {
    try {
      final cachedUser =
          await _storage.getString(AppConfig.cachedUserProfileKey);
      if (cachedUser != null) {
        final data = jsonDecode(cachedUser);
        _user = User.fromJson(data);
        notifyListeners();
      }
    } catch (e) {
      DebugLogger.logWarn('AUTH', 'Error loading user from cache: $e');
    }
  }

  Future<void> _saveUserToCache(User user) async {
    try {
      await _storage.setString(
        AppConfig.cachedUserProfileKey,
        jsonEncode(user.toJson()),
      );
    } catch (e) {
      DebugLogger.logWarn('AUTH', 'Error saving user to cache: $e');
    }
  }

  Future<bool> login({
    required String email,
    required String password,
    bool rememberMe = false,
  }) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final result = await _authService.loginWithEmailPassword(
        email: email,
        password: password,
        rememberMe: rememberMe,
      );

      if (result.success) {
        _user = _authService.currentUser;
        if (_user != null) {
          await _saveUserToCache(_user!);

          // Register device for push notifications after successful login
          DebugLogger.logAuth(
              'Attempting to register device for push notifications...');
          try {
            // Use ensureDeviceRegistered instead of initialize to force registration
            // even if service was already initialized (e.g., from app startup)
            await PushNotificationService().ensureDeviceRegistered();
            DebugLogger.logAuth(
                '✅ Push notification device registration ensured');
          } catch (e, stackTrace) {
            // Don't fail login if push notification registration fails
            DebugLogger.logWarn(
                'AUTH', '❌ Failed to register device after login: $e');
            DebugLogger.logWarn('AUTH', 'Stack trace: $stackTrace');
          }
        }
        return true;
      } else {
        _error = result.error;
        return false;
      }
    } catch (e) {
      _error = e.toString();
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  /// Quick login for testing purposes (debug + local backoffice only)
  Future<bool> quickLogin(String email, String password) async {
    if (!AppConfig.isQuickLoginEnabled) {
      _error =
          'Quick login is only available in debug mode with a local backoffice URL';
      DebugLogger.logWarn('AUTH', 'Quick login blocked (requires debug + local backoffice)');
      return false;
    }

    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final result = await _authService.quickLogin(email, password);
      if (result.success) {
        _user = _authService.currentUser;
        if (_user != null) {
          await _saveUserToCache(_user!);

          // Register device for push notifications after successful login
          DebugLogger.logAuth(
              'Attempting to register device for push notifications...');
          try {
            // Use ensureDeviceRegistered instead of initialize to force registration
            // even if service was already initialized (e.g., from app startup)
            await PushNotificationService().ensureDeviceRegistered();
            DebugLogger.logAuth(
                '✅ Push notification device registration ensured');
          } catch (e, stackTrace) {
            // Don't fail login if push notification registration fails
            DebugLogger.logWarn(
                'AUTH', '❌ Failed to register device after login: $e');
            DebugLogger.logWarn('AUTH', 'Stack trace: $stackTrace');
          }
        }
        return true;
      } else {
        _error = result.error;
        return false;
      }
    } catch (e) {
      _error = e.toString();
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> logout() async {
    _isLoading = true;
    _authCheckedThisSession = false;
    notifyListeners();

    try {
      // AuthService.logout() unregisters the device before blacklisting the
      // JWT, then clears all local state.  Do not call unregisterDevice here
      // to avoid a duplicate API call with an already-invalidated token.
      await _authService.logout();
      _user = null;
      _error = null;
      // Clear cached user data
      await _storage.remove(AppConfig.cachedUserProfileKey);
    } catch (e) {
      _error = e.toString();
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<String?> getSavedEmail() async {
    return await _authService.getSavedEmail();
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }

  // Handle authentication errors (e.g., session expired)
  Future<void> handleAuthenticationError() async {
    DebugLogger.logWarn(
        'AUTH', 'Handling authentication error - clearing session');
    _user = null;
    _error = null;
    await _storage.remove(AppConfig.cachedUserProfileKey);
    await _authService.logout();
    notifyListeners();
  }

  // Update profile color
  /// Update user profile fields (name, title, chatbot_enabled, profile_color)
  Future<bool> updateProfile({
    String? name,
    String? title,
    bool? chatbotEnabled,
    String? profileColor,
  }) async {
    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final profileService = UserProfileService();
      final updatedUser = await profileService.updateProfile(
        name: name,
        title: title,
        chatbotEnabled: chatbotEnabled,
        profileColor: profileColor,
      );

      if (updatedUser != null) {
        // Update current user with new data
        _user = updatedUser;
        await _saveUserToCache(_user!);
        DebugLogger.logAuth(
            'Profile updated successfully: ${_user!.email}');
        _isLoading = false;
        notifyListeners();
        return true;
      } else {
        _error = 'Failed to update profile';
        _isLoading = false;
        notifyListeners();
        return false;
      }
    } catch (e) {
      _error = e.toString();
      DebugLogger.logError('Error updating profile: $e');
      _isLoading = false;
      notifyListeners();
      return false;
    }
  }

  Future<bool> updateProfileColor(String color) async {
    if (_user == null) {
      _error = 'User not authenticated';
      return false;
    }

    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final success = await _authService.updateProfileColor(color);
      if (success) {
        // Refresh user from AuthService to get updated profile color
        _user = _authService.currentUser;
        if (_user != null) {
          await _saveUserToCache(_user!);
        }
        return true;
      } else {
        _error = 'Failed to update profile color';
        return false;
      }
    } catch (e) {
      _error = e.toString();
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  // Change password
  Future<String?> changePassword({
    required String currentPassword,
    required String newPassword,
  }) async {
    if (_user == null) {
      _error = 'User not authenticated';
      return 'User not authenticated';
    }

    _isLoading = true;
    _error = null;
    notifyListeners();

    try {
      final result = await _authService.changePassword(
        currentPassword: currentPassword,
        newPassword: newPassword,
      );

      if (result.success) {
        // If password change requires re-authentication, clear user and session
        if (result.requiresReauth) {
          _user = null;
          await _storage.remove(AppConfig.cachedUserProfileKey);
          DebugLogger.logAuth('Password changed - session invalidated, user must re-login');
        }
        return null; // Success
      } else {
        _error = result.error ?? 'Failed to change password';
        return result.error ?? 'Failed to change password';
      }
    } on AuthenticationException catch (e) {
      // Handle authentication errors (session expired)
      _error = e.toString();
      _user = null;
      await _storage.remove(AppConfig.cachedUserProfileKey);
      return e.toString();
    } catch (e) {
      _error = e.toString();
      return e.toString();
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }
}
