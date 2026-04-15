import 'package:flutter/material.dart';
import 'package:widgetbook/widgetbook.dart';
import 'package:hum_databank_app/utils/theme.dart';
import 'package:hum_databank_app/widgets/loading_indicator.dart';
import 'package:hum_databank_app/widgets/error_state.dart';
import 'package:hum_databank_app/widgets/ios_button.dart';
import 'package:hum_databank_app/widgets/ios_card.dart';
import 'package:hum_databank_app/widgets/ios_list_tile.dart';
import 'package:hum_databank_app/widgets/app_bar.dart';
import 'package:hum_databank_app/l10n/app_localizations.dart';

void main() {
  runApp(const WidgetbookApp());
}

class WidgetbookApp extends StatelessWidget {
  const WidgetbookApp({super.key});

  @override
  Widget build(BuildContext context) {
    return Widgetbook.material(
      addons: [
        MaterialThemeAddon(
          themes: [
            WidgetbookTheme(name: 'Light', data: AppTheme.lightTheme()),
            WidgetbookTheme(name: 'Dark', data: AppTheme.darkTheme()),
          ],
        ),
        TextScaleAddon(
          min: 1.0,
          max: 2.0,
          initialScale: 1.0,
        ),
        LocalizationAddon(
          locales: [
            const Locale('en'),
            const Locale('fr'),
            const Locale('es'),
            const Locale('ar'),
          ],
          localizationsDelegates: [
            AppLocalizations.delegate,
          ],
          initialLocale: const Locale('en'),
        ),
        ViewportAddon([
          Viewports.none,
          IosViewports.iPhone13,
          IosViewports.iPadPro11Inches,
          AndroidViewports.samsungGalaxyS20,
        ]),
      ],
      directories: [
        WidgetbookFolder(
          name: 'Foundation',
          children: [
            WidgetbookComponent(
              name: 'Loading Indicators',
              useCases: [
                WidgetbookUseCase(
                  name: 'Default (iOS style)',
                  builder: (context) => const Center(
                    child: AppLoadingIndicator(),
                  ),
                ),
                WidgetbookUseCase(
                  name: 'With message',
                  builder: (context) => const Center(
                    child: AppLoadingIndicator(message: 'Loading data...'),
                  ),
                ),
                WidgetbookUseCase(
                  name: 'Material style',
                  builder: (context) => const Center(
                    child: AppLoadingIndicator(useIOSStyle: false),
                  ),
                ),
                WidgetbookUseCase(
                  name: 'Full screen',
                  builder: (context) => const AppFullScreenLoading(
                    message: 'Loading your dashboard...',
                  ),
                ),
              ],
            ),
            WidgetbookComponent(
              name: 'Error States',
              useCases: [
                WidgetbookUseCase(
                  name: 'Default error',
                  builder: (context) => AppErrorState(
                    message: 'Something went wrong. Please try again.',
                    onRetry: () {},
                  ),
                ),
                WidgetbookUseCase(
                  name: 'Network error',
                  builder: (context) => AppErrorState(
                    title: 'Connection Lost',
                    message: 'No internet connection.',
                    icon: Icons.wifi_off_rounded,
                    onRetry: () {},
                  ),
                ),
              ],
            ),
          ],
        ),
        WidgetbookFolder(
          name: 'Navigation',
          children: [
            WidgetbookComponent(
              name: 'App Bar',
              useCases: [
                WidgetbookUseCase(
                  name: 'Simple title',
                  builder: (context) => const Scaffold(
                    appBar: AppAppBar(title: 'Dashboard'),
                    body: SizedBox.shrink(),
                  ),
                ),
                WidgetbookUseCase(
                  name: 'With actions',
                  builder: (context) => Scaffold(
                    appBar: AppAppBar(
                      title: 'Settings',
                      actions: [
                        IconButton(
                          icon: const Icon(Icons.search),
                          tooltip: 'Search',
                          onPressed: () {},
                        ),
                      ],
                    ),
                    body: const SizedBox.shrink(),
                  ),
                ),
              ],
            ),
          ],
        ),
        WidgetbookFolder(
          name: 'iOS Components',
          children: [
            WidgetbookComponent(
              name: 'iOS Filled Button',
              useCases: [
                WidgetbookUseCase(
                  name: 'Primary',
                  builder: (context) => Center(
                    child: IOSFilledButton(
                      onPressed: () {},
                      child: const Text(
                        'Save Changes',
                        style: TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ),
                ),
                WidgetbookUseCase(
                  name: 'Destructive',
                  builder: (context) => Center(
                    child: IOSFilledButton(
                      color: Colors.red,
                      onPressed: () {},
                      child: const Text(
                        'Delete',
                        style: TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ),
                ),
                WidgetbookUseCase(
                  name: 'Disabled',
                  builder: (context) => const Center(
                    child: IOSFilledButton(
                      disabled: true,
                      child: Text(
                        'Not Available',
                        style: TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
            WidgetbookComponent(
              name: 'iOS Outlined Button',
              useCases: [
                WidgetbookUseCase(
                  name: 'Default',
                  builder: (context) => Center(
                    child: IOSOutlinedButton(
                      onPressed: () {},
                      child: const Text('Cancel'),
                    ),
                  ),
                ),
                WidgetbookUseCase(
                  name: 'Disabled',
                  builder: (context) => const Center(
                    child: IOSOutlinedButton(
                      disabled: true,
                      child: Text('Disabled'),
                    ),
                  ),
                ),
              ],
            ),
            WidgetbookComponent(
              name: 'iOS Card',
              useCases: [
                WidgetbookUseCase(
                  name: 'Default',
                  builder: (context) => const Padding(
                    padding: EdgeInsets.all(16),
                    child: IOSCard(
                      padding: EdgeInsets.all(16),
                      child: Text('Card content goes here'),
                    ),
                  ),
                ),
                WidgetbookUseCase(
                  name: 'Tappable',
                  builder: (context) => Padding(
                    padding: const EdgeInsets.all(16),
                    child: IOSCard(
                      padding: const EdgeInsets.all(16),
                      onTap: () {},
                      child: const Text('Tap me'),
                    ),
                  ),
                ),
                WidgetbookUseCase(
                  name: 'Grouped style',
                  builder: (context) => const Padding(
                    padding: EdgeInsets.all(16),
                    child: IOSCard(
                      useGroupedStyle: true,
                      child: Text('Grouped card content'),
                    ),
                  ),
                ),
              ],
            ),
            WidgetbookComponent(
              name: 'iOS List Tile',
              useCases: [
                WidgetbookUseCase(
                  name: 'Simple',
                  builder: (context) => IOSListTile(
                    title: const Text('Wi-Fi'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () {},
                  ),
                ),
                WidgetbookUseCase(
                  name: 'With leading and subtitle',
                  builder: (context) => IOSListTile(
                    leading: const Icon(Icons.language, color: Colors.blue),
                    title: const Text('Language'),
                    subtitle: const Text('English'),
                    trailing: const Icon(Icons.chevron_right),
                    onTap: () {},
                  ),
                ),
              ],
            ),
            WidgetbookComponent(
              name: 'iOS Grouped List',
              useCases: [
                WidgetbookUseCase(
                  name: 'Settings section',
                  builder: (context) => Padding(
                    padding: const EdgeInsets.all(16),
                    child: IOSGroupedList(
                      headerText: 'GENERAL',
                      footer: 'These settings affect all users.',
                      children: [
                        IOSListTile(
                          leading:
                              const Icon(Icons.language, color: Colors.blue),
                          title: const Text('Language'),
                          subtitle: const Text('English'),
                          trailing: const Icon(Icons.chevron_right),
                          onTap: () {},
                        ),
                        IOSListTile(
                          leading: const Icon(Icons.dark_mode,
                              color: Colors.indigo),
                          title: const Text('Dark Mode'),
                          trailing: const Icon(Icons.chevron_right),
                          onTap: () {},
                        ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ],
    );
  }
}
