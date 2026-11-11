import 'dart:async';

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

  /// When set, each send waits here so a second keyboard action can arrive
  /// before the composer is cleared.
  Completer<void>? hold;

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
    final pending = hold;
    if (pending != null) await pending.future;
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

  testWidgets('the composer keyboard has a single send action', (tester) async {
    await pumpChat(tester);
    final field = tester.widget<TextField>(composer);

    expect(field.keyboardType, TextInputType.multiline);
    expect(field.textInputAction, TextInputAction.send);
    expect(field.maxLines, 6);
    expect(field.inputFormatters, anyOf(isNull, isEmpty));
  });

  testWidgets('a newline does not submit, and the send key submits once', (
    tester,
  ) async {
    await pumpChat(tester);
    await tester.enterText(composer, 'How many volunteers?\n');
    await tester.pump();

    expect(chat.sends, 0);
    expect(
      tester.widget<TextField>(composer).controller!.text,
      'How many volunteers?\n',
    );

    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pump();

    expect(chat.sends, 1);
    expect(chat.sent, ['How many volunteers?']);
    await tester.pump(const Duration(milliseconds: 150));
  });

  testWidgets('the next message is its own single send', (tester) async {
    await pumpChat(tester);

    await tester.enterText(composer, 'How many volunteers in Kenya?');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pump();

    await tester.enterText(composer, 'And in Uganda?');
    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pump();

    expect(chat.sends, 2);
    expect(chat.sent, ['How many volunteers in Kenya?', 'And in Uganda?']);
    await tester.pump(const Duration(milliseconds: 150));
  });

  testWidgets('a newline plus the send key is still one submit', (tester) async {
    await pumpChat(tester);
    await tester.enterText(composer, 'find evidence from documents on the peaks\n');
    await tester.pump();

    await tester.testTextInput.receiveAction(TextInputAction.send);
    await tester.pump();

    expect(chat.sends, 1);
    expect(chat.sent, ['find evidence from documents on the peaks']);
    await tester.pump(const Duration(milliseconds: 150));
  });

  testWidgets('two send actions are two submits', (tester) async {
    chat.hold = Completer<void>();
    await pumpChat(tester);
    await tester.enterText(composer, 'And in Uganda?');
    await tester.pump();

    final field = tester.widget<TextField>(composer);
    field.onSubmitted!(field.controller!.text);
    field.onSubmitted!(field.controller!.text);
    expect(chat.sends, 2);

    chat.hold!.complete();
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 150));
  });

  testWidgets('the send button submits the draft once', (tester) async {
    await pumpChat(tester);
    await tester.enterText(composer, 'Show the latest appeal');
    await tester.pump();

    await tester.tap(find.byIcon(Icons.arrow_upward_rounded));
    await tester.pump();

    expect(chat.sends, 1);
    expect(chat.sent, ['Show the latest appeal']);
    await tester.pump(const Duration(milliseconds: 150));
  });
}
