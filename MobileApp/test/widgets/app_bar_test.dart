import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/widgets/app_bar.dart';

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

    testWidgets('renders as a standard AppBar by default',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        const MaterialApp(
          home: Scaffold(
            appBar: AppAppBar(title: 'Settings'),
          ),
        ),
      );

      expect(find.byType(AppBar), findsOneWidget);
      expect(find.text('Settings'), findsOneWidget);
    });

    testWidgets('actions are displayed when provided',
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
    });

    testWidgets('displays custom leading widget',
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
    });

    testWidgets('renders as SliverAppBar when useLargeTitle is true',
        (WidgetTester tester) async {
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: CustomScrollView(
              slivers: [
                const AppAppBar(title: 'Large Title', useLargeTitle: true),
                SliverList(
                  delegate: SliverChildListDelegate([
                    const SizedBox(height: 500),
                  ]),
                ),
              ],
            ),
          ),
        ),
      );

      expect(find.byType(SliverAppBar), findsOneWidget);
      expect(find.text('Large Title'), findsOneWidget);
    });

    testWidgets('preferredSize matches expected height',
        (WidgetTester tester) async {
      const standardBar = AppAppBar(title: 'Standard');
      expect(standardBar.preferredSize.height, kToolbarHeight);

      const largeBar = AppAppBar(title: 'Large', useLargeTitle: true);
      expect(largeBar.preferredSize.height, 96);
    });
  });
}
