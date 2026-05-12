import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/l10n/app_localizations.dart';
import 'package:hum_databank_app/widgets/loading_indicator.dart';

Widget _wrapWithMaterialApp(Widget child) {
  return MaterialApp(
    localizationsDelegates: const [AppLocalizations.delegate],
    supportedLocales: const [Locale('en')],
    home: child,
  );
}

void main() {
  group('AppLoadingIndicator', () {
    testWidgets('renders a spinner', (WidgetTester tester) async {
      await tester.pumpWidget(
        _wrapWithMaterialApp(const AppLoadingIndicator()),
      );
      await tester.pump();

      expect(find.byType(CupertinoActivityIndicator), findsOneWidget);
    });

    testWidgets('renders CircularProgressIndicator when useIOSStyle is false',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        _wrapWithMaterialApp(
          const AppLoadingIndicator(useIOSStyle: false),
        ),
      );
      await tester.pump();

      expect(find.byType(CircularProgressIndicator), findsOneWidget);
      expect(find.byType(CupertinoActivityIndicator), findsNothing);
    });

    testWidgets('shows message when provided', (WidgetTester tester) async {
      await tester.pumpWidget(
        _wrapWithMaterialApp(
          const AppLoadingIndicator(message: 'Please wait...'),
        ),
      );
      await tester.pump();

      expect(find.text('Please wait...'), findsOneWidget);
    });

    testWidgets('does not show message text when message is null',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        _wrapWithMaterialApp(const AppLoadingIndicator()),
      );
      await tester.pump();

      // Only the spinner should be present, no extra Text widgets for message
      expect(find.byType(CupertinoActivityIndicator), findsOneWidget);
      expect(find.text('Please wait...'), findsNothing);
    });
  });

  group('AppFullScreenLoading', () {
    testWidgets('renders in a Scaffold', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          localizationsDelegates: [AppLocalizations.delegate],
          supportedLocales: [Locale('en')],
          home: AppFullScreenLoading(),
        ),
      );
      await tester.pump();

      expect(find.byType(Scaffold), findsOneWidget);
      expect(find.byType(CupertinoActivityIndicator), findsOneWidget);
    });

    testWidgets('shows message when provided', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          localizationsDelegates: [AppLocalizations.delegate],
          supportedLocales: [Locale('en')],
          home: AppFullScreenLoading(message: 'Loading data...'),
        ),
      );
      await tester.pump();

      expect(find.byType(Scaffold), findsOneWidget);
      expect(find.text('Loading data...'), findsOneWidget);
    });
  });
}
