import 'package:flutter/cupertino.dart' as cupertino;
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/l10n/app_localizations.dart';
import 'package:hum_databank_app/widgets/error_state.dart';

Widget _wrapWithMaterialApp(Widget child) {
  return MaterialApp(
    localizationsDelegates: const [AppLocalizations.delegate],
    supportedLocales: const [Locale('en')],
    home: Scaffold(body: child),
  );
}

void main() {
  group('AppErrorState', () {
    testWidgets('shows default error title from localizations',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        _wrapWithMaterialApp(const AppErrorState()),
      );
      await tester.pumpAndSettle();

      expect(find.text('Oops! Something went wrong'), findsOneWidget);
    });

    testWidgets('shows error message when message is provided',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        _wrapWithMaterialApp(
          const AppErrorState(message: 'Network connection failed'),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Network connection failed'), findsOneWidget);
    });

    testWidgets('does not show message text when message is null',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        _wrapWithMaterialApp(const AppErrorState()),
      );
      await tester.pumpAndSettle();

      // Default title should be present
      expect(find.text('Oops! Something went wrong'), findsOneWidget);
      // The message section is guarded by `if (message != null)`
      expect(find.text('Something went wrong'), findsNothing);
    });

    testWidgets('shows custom title and message',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        _wrapWithMaterialApp(
          const AppErrorState(
            title: 'Data Load Failed',
            message: 'Could not fetch indicators',
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Data Load Failed'), findsOneWidget);
      expect(find.text('Could not fetch indicators'), findsOneWidget);
    });

    testWidgets('retry button appears when onRetry is provided',
        (WidgetTester tester) async {
      bool retryCalled = false;

      await tester.pumpWidget(
        _wrapWithMaterialApp(
          AppErrorState(onRetry: () => retryCalled = true),
        ),
      );
      await tester.pumpAndSettle();

      // Retry button with localized label
      expect(find.text('Retry'), findsOneWidget);
      expect(
        find.byType(cupertino.CupertinoButton),
        findsOneWidget,
      );

      await tester.tap(find.text('Retry'));
      await tester.pump();

      expect(retryCalled, isTrue);
    });

    testWidgets('retry button is hidden when onRetry is null',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        _wrapWithMaterialApp(const AppErrorState()),
      );
      await tester.pumpAndSettle();

      expect(find.byType(cupertino.CupertinoButton), findsNothing);
      expect(find.text('Retry'), findsNothing);
    });

    testWidgets('shows custom retry label', (WidgetTester tester) async {
      await tester.pumpWidget(
        _wrapWithMaterialApp(
          AppErrorState(
            onRetry: () {},
            retryLabel: 'Try Again',
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Try Again'), findsOneWidget);
    });

    testWidgets('displays error icon', (WidgetTester tester) async {
      await tester.pumpWidget(
        _wrapWithMaterialApp(const AppErrorState()),
      );
      await tester.pumpAndSettle();

      expect(find.byIcon(Icons.error_outline_rounded), findsOneWidget);
    });

    testWidgets('displays custom icon when provided',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        _wrapWithMaterialApp(
          const AppErrorState(icon: Icons.wifi_off_rounded),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byIcon(Icons.wifi_off_rounded), findsOneWidget);
      expect(find.byIcon(Icons.error_outline_rounded), findsNothing);
    });
  });
}
