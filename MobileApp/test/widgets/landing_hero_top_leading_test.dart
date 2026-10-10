import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:hum_databank_app/widgets/home_landing/landing_hero_sliver.dart';

void main() {
  testWidgets('hero shows topLeading below the status bar without overflow',
      (tester) async {
    const inset = 47.0;
    await tester.pumpWidget(
      MaterialApp(
        home: MediaQuery(
          data: const MediaQueryData(
            size: Size(390, 844),
            padding: EdgeInsets.only(top: inset),
          ),
          child: Scaffold(
            body: CustomScrollView(
              slivers: [
                LandingHeroSliver(
                  title: 'Title',
                  description: 'Description',
                  topLeading: IconButton(
                    icon: const Icon(Icons.menu_rounded),
                    onPressed: () {},
                  ),
                  footer: const SizedBox(height: 120),
                ),
                const SliverToBoxAdapter(child: SizedBox(height: 1200)),
              ],
            ),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(tester.takeException(), isNull);
    expect(find.byIcon(Icons.menu_rounded), findsOneWidget);
    expect(tester.getTopLeft(find.byType(IconButton)).dy, greaterThan(inset));
    expect(
      tester.getSize(find.byType(FlexibleSpaceBar)).height,
      LandingHeroSliver.bodyHeroExtent() + inset,
    );
  });
}
