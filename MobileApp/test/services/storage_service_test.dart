import 'package:flutter/services.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/services/storage_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _secureChannel =
    MethodChannel('plugins.it_nomads.com/flutter_secure_storage');

/// In-memory backing for the secure-storage MethodChannel under `flutter test`.
late Map<String, String> _secureValues;

Future<Object?> _handleSecureCall(MethodCall call) async {
  switch (call.method) {
    case 'write':
      final args = Map<String, dynamic>.from(call.arguments as Map);
      final key = args['key'] as String;
      final value = args['value'];
      if (value == null) {
        _secureValues.remove(key);
      } else {
        _secureValues[key] = value as String;
      }
      return null;
    case 'read':
      final args = Map<String, dynamic>.from(call.arguments as Map);
      return _secureValues[args['key'] as String];
    case 'readAll':
      return Map<String, String>.from(_secureValues);
    case 'delete':
      final args = Map<String, dynamic>.from(call.arguments as Map);
      _secureValues.remove(args['key'] as String);
      return null;
    case 'deleteAll':
      _secureValues.clear();
      return null;
    case 'containsKey':
      final args = Map<String, dynamic>.from(call.arguments as Map);
      return _secureValues.containsKey(args['key'] as String);
  }
  return null;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    // [StorageService]'s singleton constructor reads [AppConfig] which
    // reads dotenv at first access. Load with no file so [dotenv.env]
    // returns an empty map instead of throwing NotInitializedError.
    await dotenv.load(fileName: '.env', isOptional: true);
  });

  setUp(() async {
    _secureValues = <String, String>{};
    TestDefaultBinaryMessengerBinding
        .instance.defaultBinaryMessenger
        .setMockMethodCallHandler(_secureChannel, _handleSecureCall);

    // Reset SharedPreferences in-memory state between tests.
    SharedPreferences.setMockInitialValues(<String, Object>{});
    // The StorageService singleton caches [_prefs]; force it to drop the
    // cached reference so each test reads/writes against a fresh
    // SharedPreferences instance.
    final storage = StorageService();
    await storage.init();
    await storage.clear();
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding
        .instance.defaultBinaryMessenger
        .setMockMethodCallHandler(_secureChannel, null);
  });

  group('StorageService.clearPrefsExcept', () {
    test('preserves only the listed keys and removes everything else',
        () async {
      final storage = StorageService();
      await storage.setString('theme_mode', 'dark');
      await storage.setString('selected_language', 'fr');
      await storage.setString('arabic_text_font', 'amiri');
      await storage.setBool('humdb_chatbot_ai_policy_acknowledged', true);
      await storage.setString(
          'cached_user_profile', '{"id":1,"email":"a@b.c"}');
      await storage.setString('cached_dashboard', '{"foo":"bar"}');
      await storage.setInt('session_last_validated', 1715000000000);
      await storage.setInt('jwt_access_expires_at_v1', 1715000600000);
      await storage.setString(
          'tab_customization_focal', '["dashboard","tasks"]');
      await storage.setInt('random_int_pref', 42);

      await storage.clearPrefsExcept(<String>{
        'theme_mode',
        'selected_language',
        'arabic_text_font',
        'humdb_chatbot_ai_policy_acknowledged',
      });

      // Survivors retained with original values + types.
      expect(await storage.getString('theme_mode'), 'dark');
      expect(await storage.getString('selected_language'), 'fr');
      expect(await storage.getString('arabic_text_font'), 'amiri');
      expect(await storage.getBool('humdb_chatbot_ai_policy_acknowledged'),
          isTrue);

      // Everything else wiped.
      expect(await storage.getString('cached_user_profile'), isNull);
      expect(await storage.getString('cached_dashboard'), isNull);
      expect(await storage.getInt('session_last_validated'), isNull);
      expect(await storage.getInt('jwt_access_expires_at_v1'), isNull);
      expect(await storage.getString('tab_customization_focal'), isNull);
      expect(await storage.getInt('random_int_pref'), isNull);
    });

    test('keepKeys not present in storage are simply ignored', () async {
      final storage = StorageService();
      await storage.setString('cached_user_profile', '{"id":1}');

      await storage.clearPrefsExcept(<String>{
        'theme_mode', // not present
      });

      expect(await storage.getString('theme_mode'), isNull);
      expect(await storage.getString('cached_user_profile'), isNull);
    });

    test('clearing with empty allow-list wipes everything', () async {
      final storage = StorageService();
      await storage.setString('theme_mode', 'dark');
      await storage.setString('cached_user_profile', '{"id":1}');

      await storage.clearPrefsExcept(const <String>{});

      expect(await storage.getString('theme_mode'), isNull);
      expect(await storage.getString('cached_user_profile'), isNull);
    });
  });

  group('StorageService.clearSecureExcept', () {
    test('preserves only the listed keys and removes everything else',
        () async {
      final storage = StorageService();
      await storage.setSecure('persistent_device_install_id', 'device-123');
      await storage.setSecure('jwt_access_token_v1', 'access-token');
      await storage.setSecure('jwt_refresh_token_v1', 'refresh-token');
      await storage.setSecure('session_cookie', 'session=abcdef');
      await storage.setSecure('csrf_token_v1', 'csrf-token');

      await storage.clearSecureExcept(<String>{
        'persistent_device_install_id',
      });

      expect(await storage.getSecure('persistent_device_install_id'),
          'device-123');
      expect(await storage.getSecure('jwt_access_token_v1'), isNull);
      expect(await storage.getSecure('jwt_refresh_token_v1'), isNull);
      expect(await storage.getSecure('session_cookie'), isNull);
      expect(await storage.getSecure('csrf_token_v1'), isNull);
    });

    test('keepKeys not present in storage are tolerated', () async {
      final storage = StorageService();
      await storage.setSecure('jwt_access_token_v1', 'access-token');

      await storage.clearSecureExcept(<String>{
        'persistent_device_install_id', // never written
      });

      expect(await storage.getSecure('persistent_device_install_id'), isNull);
      expect(await storage.getSecure('jwt_access_token_v1'), isNull);
    });

    test('clearing with empty allow-list wipes everything', () async {
      final storage = StorageService();
      await storage.setSecure('jwt_access_token_v1', 'access-token');
      await storage.setSecure('persistent_device_install_id', 'device-123');

      await storage.clearSecureExcept(const <String>{});

      expect(await storage.getSecure('jwt_access_token_v1'), isNull);
      expect(await storage.getSecure('persistent_device_install_id'), isNull);
    });
  });
}
