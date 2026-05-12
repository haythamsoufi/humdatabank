import 'package:flutter/services.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/services/jwt_token_service.dart';
import 'package:hum_databank_app/services/storage_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

const _secureChannel =
    MethodChannel('plugins.it_nomads.com/flutter_secure_storage');

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
    await dotenv.load(fileName: '.env', isOptional: true);
  });

  setUp(() async {
    _secureValues = <String, String>{};
    TestDefaultBinaryMessengerBinding
        .instance.defaultBinaryMessenger
        .setMockMethodCallHandler(_secureChannel, _handleSecureCall);

    SharedPreferences.setMockInitialValues(<String, Object>{});
    final storage = StorageService();
    await storage.init();
    await storage.clear();
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding
        .instance.defaultBinaryMessenger
        .setMockMethodCallHandler(_secureChannel, null);
  });

  group('JwtTokenService', () {
    test('saveTokens persists access/refresh + expiry in secure storage',
        () async {
      final svc = JwtTokenService();
      await svc.saveTokens(
        accessToken: 'access-1',
        refreshToken: 'refresh-1',
        expiresIn: 1800, // 30 min
      );

      expect(await svc.getAccessToken(), 'access-1');
      expect(await svc.getRefreshToken(), 'refresh-1');
      expect(await svc.hasTokens(), isTrue);
      expect(await svc.hasRefreshToken(), isTrue);
      // Just-saved 30-min token: not expired (30s buffer at most).
      expect(await svc.isAccessTokenExpired(), isFalse);

      // Expiry must live in secure storage now (not SharedPreferences).
      expect(_secureValues.containsKey('jwt_access_expires_at_v2'), isTrue);
      final storage = StorageService();
      expect(await storage.getInt('jwt_access_expires_at_v1'), isNull);
    });

    test('isAccessTokenExpired is true when expiry timestamp is missing',
        () async {
      final svc = JwtTokenService();
      // No tokens saved at all.
      expect(await svc.isAccessTokenExpired(), isTrue);
    });

    test('isAccessTokenExpired is true once the buffer window is reached',
        () async {
      final svc = JwtTokenService();
      // Token expires 30 s in the future — inside the 60 s safety buffer.
      await svc.saveTokens(
        accessToken: 'access',
        refreshToken: 'refresh',
        expiresIn: 30,
      );

      expect(await svc.isAccessTokenExpired(), isTrue);
    });

    test('clearTokens removes access, refresh, and expiry from secure storage',
        () async {
      final svc = JwtTokenService();
      await svc.saveTokens(
        accessToken: 'access',
        refreshToken: 'refresh',
        expiresIn: 1800,
      );

      await svc.clearTokens();

      expect(await svc.getAccessToken(), isNull);
      expect(await svc.getRefreshToken(), isNull);
      expect(await svc.hasTokens(), isFalse);
      expect(await svc.hasRefreshToken(), isFalse);
      expect(await svc.isAccessTokenExpired(), isTrue);
      expect(_secureValues.containsKey('jwt_access_expires_at_v2'), isFalse);
    });

    test(
        'isAccessTokenExpired migrates legacy SharedPreferences expiry on first read',
        () async {
      final storage = StorageService();
      // Simulate an upgrade from a build that wrote the expiry to
      // SharedPreferences (jwt_access_expires_at_v1).
      final futureMs = DateTime.now().millisecondsSinceEpoch +
          const Duration(minutes: 30).inMilliseconds;
      await storage.setInt('jwt_access_expires_at_v1', futureMs);

      final svc = JwtTokenService();
      // Should report not-expired, *and* migrate the value into the secure
      // store, *and* drop the legacy SharedPreferences key so a future
      // pref-only wipe does not silently restore stale state.
      expect(await svc.isAccessTokenExpired(), isFalse);
      expect(_secureValues['jwt_access_expires_at_v2'], futureMs.toString());
      expect(await storage.getInt('jwt_access_expires_at_v1'), isNull);
    });
  });
}
