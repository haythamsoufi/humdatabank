import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/widgets/app_bar.dart';
import 'package:hum_databank_app/widgets/glass_circle_button.dart';

void main() {
  group('AppAppBar', () {
    testWidgets('renders title text', (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            appBar: AppAppBar(title: 'Dashboard'),
          ),
        ),
      );

      expect(find.text('Dashboard'), findsOneWidget);
    });

    testWidgets('is a flat header without a Material AppBar or divider',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            appBar: AppAppBar(title: 'Settings'),
          ),
        ),
      );

      expect(find.byType(AppBar), findsNothing);
      expect(find.byType(Divider), findsNothing);
      expect(find.text('Settings'), findsOneWidget);
    });

    testWidgets('title is left aligned like the dashboard heading',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            appBar: AppAppBar(title: 'Notifications'),
          ),
        ),
      );

      final left = tester.getTopLeft(find.text('Notifications')).dx;
      expect(left, AppAppBar.horizontalPadding);
    });

    testWidgets('actions are displayed in glass circle bubbles',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            appBar: AppAppBar(
              title: 'Home',
              actions: [
                IconButton(
                  icon: const Icon(Icons.search),
                  onPressed: () {},
                ),
                IconButton(
                  icon: const Icon(Icons.notifications),
                  onPressed: () {},
                ),
              ],
            ),
          ),
        ),
      );

      expect(find.byIcon(Icons.search), findsOneWidget);
      expect(find.byIcon(Icons.notifications), findsOneWidget);
      expect(find.byType(GlassCircleBubble), findsNWidgets(2));
      expect(
        tester.getSize(find.byType(GlassCircleBubble).first),
        const Size.square(GlassCircleBubble.defaultSize),
      );
    });

    testWidgets('displays custom leading widget in a bubble',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            appBar: AppAppBar(
              title: 'Page',
              leading: IconButton(
                icon: const Icon(Icons.menu),
                onPressed: () {},
              ),
              automaticallyImplyLeading: false,
            ),
          ),
        ),
      );

      expect(find.byIcon(Icons.menu), findsOneWidget);
      expect(find.byType(GlassCircleBubble), findsOneWidget);
    });

    testWidgets('shows a back bubble that pops when the route can pop',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Builder(
            builder: (context) => Scaffold(
              body: TextButton(
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => const Scaffold(
                      appBar: AppAppBar(title: 'Detail'),
                    ),
                  ),
                ),
                child: const Text('open'),
              ),
            ),
          ),
        ),
      );

      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();

      expect(find.text('Detail'), findsOneWidget);
      expect(find.byType(GlassCircleBubble), findsOneWidget);

      await tester.tap(find.byIcon(Icons.arrow_back_ios_new_rounded));
      await tester.pumpAndSettle();

      expect(find.text('Detail'), findsNothing);
    });

    testWidgets('has no bubble when there is nothing to show',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            appBar: AppAppBar(title: 'Tab'),
          ),
        ),
      );

      expect(find.byType(GlassCircleBubble), findsNothing);
    });

    testWidgets('long titles scale down instead of overflowing',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            appBar: AppAppBar(
              title: 'A very long screen title that cannot fit on one line',
              actions: [
                IconButton(icon: const Icon(Icons.tune), onPressed: () {}),
              ],
            ),
          ),
        ),
      );

      expect(tester.takeException(), isNull);
    });

    testWidgets('preferredSize matches the shared toolbar height',
        (WidgetTester tester) async {
      const bar = AppAppBar(title: 'Standard');
      expect(bar.preferredSize.height, AppAppBar.toolbarHeight);
    });
  });
}
