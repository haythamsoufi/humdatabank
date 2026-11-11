import 'package:flutter/material.dart';
import 'package:flutter_dotenv/flutter_dotenv.dart';
import 'package:flutter_inappwebview_platform_interface/flutter_inappwebview_platform_interface.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/di/service_locator.dart';
import 'package:hum_databank_app/l10n/app_localizations.dart';
import 'package:hum_databank_app/models/shared/user.dart';
import 'package:hum_databank_app/providers/shared/ai_chat_provider.dart';
import 'package:hum_databank_app/providers/shared/auth_provider.dart';
import 'package:hum_databank_app/screens/shared/ai_chat_screen.dart';
import 'package:hum_databank_app/services/api_service.dart';
import 'package:provider/provider.dart';

/// Records composer submits without opening a stream or touching SQLite.
class _CountingChat extends AiChatProvider {
  int sends = 0;
  final List<String> sent = [];

  @override
  Future<void> loadChatUiPrefs() async {}

  @override
  Future<void> loadConversations({
    required bool isAuthenticated,
    String? sessionUserId,
  }) async {}

  @override
  Future<void> ensureTokenIfLoggedIn({required bool isAuthenticated}) async {}

  @override
  Future<void> sendMessageStreaming({
    required String message,
    required bool isAuthenticated,
    String? preferredLanguageCode,
  }) async {
    sends++;
    sent.add(message);
  }
}

class _TestCookieManager extends PlatformCookieManager {
  _TestCookieManager()
    : super.implementation(const PlatformCookieManagerCreationParams());
}

class _TestInAppWebViewPlatform extends InAppWebViewPlatform {
  @override
  PlatformCookieManager createPlatformCookieManager(
    PlatformCookieManagerCreationParams params,
  ) {
    return _TestCookieManager();
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    await dotenv.load(fileName: '.env', isOptional: true);
    InAppWebViewPlatform.instance = _TestInAppWebViewPlatform();
    if (!sl.isRegistered<ApiService>()) {
      sl.registerSingleton<ApiService>(ApiService());
    }
  });

  late AuthProvider auth;
  late _CountingChat chat;

  setUp(() {
    auth = AuthProvider()
      ..debugSeedUser = User(
        id: 7,
        email: 'tester@example.com',
        role: 'admin',
        chatbotEnabled: true,
        aiBetaTester: true,
      );
    chat = _CountingChat();
  });

  Future<void> pumpChat(WidgetTester tester) async {
    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<AuthProvider>.value(value: auth),
          ChangeNotifierProvider<AiChatProvider>.value(value: chat),
        ],
        child: const MaterialApp(
          locale: Locale('en'),
          localizationsDelegates: [
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
            AppLocalizations.delegate,
          ],
          supportedLocales: [Locale('en')],
          home: AiChatScreen(),
        ),
      ),
    );
    await tester.pump();
  }

  final composer = find.byWidgetPredicate(
    (widget) => widget is TextField && widget.decoration?.hintText == 'Message',
  );

  Future<void> submitTwice(WidgetTester tester, String text) async {
    expect(composer, findsOneWidget);
    await tester.enterText(composer, text);
    await tester.pump();
    final field = tester.widget<TextField>(composer);
    field.onSubmitted!(text);
    field.onSubmitted!(text);
    await tester.pump();
  }

  testWidgets('a repeated keyboard submit sends the message once', (
    tester,
  ) async {
    await pumpChat(tester);
    await submitTwice(tester, 'How many volunteers in Kenya?');

    expect(chat.sends, 1);
    expect(chat.sent, ['How many volunteers in Kenya?']);
    expect(tester.widget<TextField>(composer).controller!.text, isEmpty);
    await tester.pump(const Duration(milliseconds: 150));
  });

  testWidgets(
    'the following message still sends once after a duplicate submit',
    (tester) async {
      await pumpChat(tester);
      await submitTwice(tester, 'How many volunteers in Kenya?');
      await submitTwice(tester, 'And in Uganda?');

      expect(chat.sends, 2);
      expect(chat.sent, ['How many volunteers in Kenya?', 'And in Uganda?']);
      await tester.pump(const Duration(milliseconds: 150));
    },
  );

  testWidgets('tapping send twice submits once', (tester) async {
    await pumpChat(tester);
    await tester.enterText(composer, 'Show the latest appeal');
    await tester.pump();

    final sendIcon = find.byIcon(Icons.arrow_upward_rounded);
    expect(sendIcon, findsOneWidget);
    final onTap = tester
        .widget<InkWell>(
          find.ancestor(of: sendIcon, matching: find.byType(InkWell)).first,
        )
        .onTap!;
    onTap();
    onTap();
    await tester.pump();

    expect(chat.sends, 1);
    expect(chat.sent, ['Show the latest appeal']);
    await tester.pump(const Duration(milliseconds: 150));
  });
}
