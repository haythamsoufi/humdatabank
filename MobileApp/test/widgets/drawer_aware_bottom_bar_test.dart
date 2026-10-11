import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/widgets/drawer_aware_bottom_bar.dart';

void main() {
  testWidgets('shell tab bar hides while a nested side drawer is open', (
    tester,
  ) async {
    var taps = 0;
    await tester.pumpWidget(
      MaterialApp(home: _ShellPage(onBarTap: () => taps++)),
    );

    final bar = find.text('Tab');
    expect(bar, findsOneWidget);
    final restingCenter = tester.getCenter(bar);

    await tester.tapAt(restingCenter);
    await tester.pump();
    expect(taps, 1);

    await tester.tap(find.byTooltip('Open navigation menu'));
    await tester.pumpAndSettle();

    expect(find.text('Drawer item').hitTestable(), findsOneWidget);
    expect(tester.getCenter(bar).dy, greaterThan(restingCenter.dy + 40));

    await tester.tapAt(restingCenter);
    await tester.pump();
    expect(taps, 1);

    // Scrim sits to the right of the default 304px drawer.
    await tester.tapAt(const Offset(360, 200));
    await tester.pumpAndSettle();

    expect(find.text('Drawer item').hitTestable(), findsNothing);
    expect(tester.getCenter(bar).dy, closeTo(restingCenter.dy, 1));

    await tester.tapAt(restingCenter);
    await tester.pump();
    expect(taps, 2);
  });

  testWidgets('hidden bar ignores taps before it slides back', (tester) async {
    var taps = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: const SizedBox.expand(),
          bottomNavigationBar: DrawerAwareBottomBar(
            hidden: true,
            child: TextButton(
              onPressed: () => taps++,
              child: const Text('Tab'),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('Tab'), warnIfMissed: false);
    await tester.pump();
    expect(taps, 0);
  });
}

class _ShellPage extends StatefulWidget {
  const _ShellPage({required this.onBarTap});

  final VoidCallback onBarTap;

  @override
  State<_ShellPage> createState() => _ShellPageState();
}

class _ShellPageState extends State<_ShellPage> {
  bool _drawerOpen = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      extendBody: true,
      body: NotificationListener<ShellDrawerOpenNotification>(
        onNotification: (notification) {
          if (_drawerOpen == notification.isOpen) return true;
          setState(() => _drawerOpen = notification.isOpen);
          return true;
        },
        child: Builder(
          builder: (drawerContext) {
            return Scaffold(
              appBar: AppBar(title: const Text('Page')),
              onDrawerChanged: (isOpened) {
                ShellDrawerOpenNotification(
                  isOpen: isOpened,
                ).dispatch(drawerContext);
              },
              drawer: const Drawer(child: Text('Drawer item')),
              body: const SizedBox.expand(),
            );
          },
        ),
      ),
      bottomNavigationBar: DrawerAwareBottomBar(
        hidden: _drawerOpen,
        child: TextButton(onPressed: widget.onBarTap, child: const Text('Tab')),
      ),
    );
  }
}
