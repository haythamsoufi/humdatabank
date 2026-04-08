import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import '../../providers/shared/language_provider.dart';
import '../../config/routes.dart';
import '../../models/shared/ai_chat_launch_args.dart';
import '../../providers/shared/auth_provider.dart';
import '../../utils/constants.dart';
import '../../utils/ios_constants.dart';
import '../../l10n/app_localizations.dart';
import '../../widgets/app_navigation_drawer.dart';
import '../../widgets/countries_widget.dart';
import '../../widgets/ios_button.dart';
import '../../widgets/home_landing/landing_ai_entry_card.dart';
import '../../widgets/home_landing/landing_get_started_section.dart';
import '../../widgets/home_landing/landing_hero_sliver.dart';
import '../../widgets/home_landing/landing_quick_prompts.dart';
import '../../widgets/sheets/native_modal_sheet.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();

  static void reloadFromKey(GlobalKey key) {
    final state = key.currentState;
    if (state is _HomeScreenState) {
      state.reload();
    }
  }
}

class _HomeScreenState extends State<HomeScreen>
    with AutomaticKeepAliveClientMixin {
  final ScrollController _scrollController = ScrollController();
  int _getStartedEpoch = 0;
  bool _chatExpanded = false;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    // Collapse the chat expansion when the user scrolls away from the hero.
    _scrollController.addListener(_onScroll);
  }

  void _onScroll() {
    if (_chatExpanded && _scrollController.offset > 48) {
      setState(() => _chatExpanded = false);
    }
  }

  @override
  void dispose() {
    _scrollController.removeListener(_onScroll);
    _scrollController.dispose();
    super.dispose();
  }

  /// Scrolls to the top and refreshes the "Get Started" section.
  /// Called from both the nav-drawer tap and pull-to-refresh.
  void reload() {
    setState(() {
      _getStartedEpoch++;
      _chatExpanded = false;
    });
    if (_scrollController.hasClients) {
      _scrollController.animateTo(
        0,
        duration: const Duration(milliseconds: 350),
        curve: Curves.easeOutCubic,
      );
    }
  }

  void _expandChat() {
    setState(() => _chatExpanded = true);
  }

  void _onChatNavigated() {
    // The user is navigating to the AI chat screen — reset hero to default.
    if (mounted) setState(() => _chatExpanded = false);
  }

  void _onPromptSelected(String prompt, BuildContext ctx) {
    final chatbot =
        Provider.of<AuthProvider>(ctx, listen: false).user?.chatbotEnabled ??
            false;
    _onChatNavigated();
    Navigator.of(ctx).pushNamed(
      AppRoutes.aiChat,
      arguments: AiChatLaunchArgs(
        bottomNavTabIndex: chatbot ? 3 : 2,
        startNewConversation: true,
        initialText: prompt,
        sendImmediately: true,
      ),
    );
  }

  List<LandingShortcutItem> _buildShortcuts(
    BuildContext context,
    AppLocalizations l10n,
  ) {
    return [
      LandingShortcutItem(
        icon: Icons.library_books_rounded,
        title: l10n.indicatorBank,
        subtitle: l10n.homeLandingShortcutIndicatorsSubtitle,
        onTap: () => Navigator.of(context).pushNamed(AppRoutes.indicatorBank),
      ),
      LandingShortcutItem(
        icon: Icons.folder_rounded,
        title: l10n.resources,
        subtitle: l10n.homeLandingShortcutResourcesSubtitle,
        onTap: () => Navigator.of(context).pushNamed(AppRoutes.resources),
      ),
      LandingShortcutItem(
        icon: Icons.public_rounded,
        title: l10n.countries,
        subtitle: l10n.homeLandingShortcutCountriesSubtitle,
        onTap: () => _showCountriesSheet(context, Theme.of(context), l10n),
      ),
      LandingShortcutItem(
        icon: Icons.analytics_rounded,
        title: l10n.disaggregationAnalysis,
        subtitle: l10n.homeLandingShortcutDisaggregationSubtitle,
        onTap: () =>
            Navigator.of(context).pushNamed(AppRoutes.disaggregationAnalysis),
      ),
    ];
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Consumer<LanguageProvider>(
      builder: (context, languageProvider, child) {
        final localizations = AppLocalizations.of(context)!;
        final theme = Theme.of(context);
        final language = languageProvider.currentLanguage;
        final bottomPad = MediaQuery.paddingOf(context).bottom;

        final quickPrompts = LandingQuickPrompts(
          prompts: [
            localizations.homeLandingQuickPrompt1,
            localizations.homeLandingQuickPrompt2,
            localizations.homeLandingQuickPrompt3,
          ],
          onPromptSelected: (p) => _onPromptSelected(p, context),
        );

        return Scaffold(
          backgroundColor: theme.scaffoldBackgroundColor,
          appBar: AppBar(
            backgroundColor: theme.scaffoldBackgroundColor,
            elevation: 0,
            leading: Builder(
              builder: (BuildContext scaffoldContext) {
                return IOSIconButton(
                  icon: Icons.menu,
                  onPressed: () => Scaffold.of(scaffoldContext).openDrawer(),
                  tooltip: localizations.navigation,
                  semanticLabel: localizations.navigation,
                );
              },
            ),
            title: Text(
              localizations.home,
              style: IOSTextStyle.headline(context),
            ),
          ),
          drawer: AppNavigationDrawer(
            activeScreen: ActiveDrawerScreen.home,
            onHomeSelected: reload,
            onShowCountriesSheet: () =>
                _showCountriesSheet(context, theme, localizations),
          ),
          body: RefreshIndicator(
            color: Color(AppConstants.ifrcRed),
            onRefresh: () async {
              HapticFeedback.lightImpact();
              reload();
              await Future<void>.delayed(const Duration(milliseconds: 400));
            },
            child: CustomScrollView(
              controller: _scrollController,
              physics: const AlwaysScrollableScrollPhysics(),
              clipBehavior: Clip.none,
              slivers: [
                LandingHeroSliver(
                  title: localizations.appName,
                  description: localizations.homeLandingHeroDescription,
                  chatExpanded: _chatExpanded,
                  footer: LandingAiEntryCard(
                    l10n: localizations,
                    scrollController: _scrollController,
                    isExpanded: _chatExpanded,
                    onExpand: _expandChat,
                    onNavigated: _onChatNavigated,
                  ),
                  quickPrompts: quickPrompts,
                ),
                SliverToBoxAdapter(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const SizedBox(height: 28),
                      LandingGetStartedSection(
                        key: ValueKey(_getStartedEpoch),
                        l10n: localizations,
                        locale: language,
                        shortcuts: _buildShortcuts(context, localizations),
                      ),
                      // Bottom buffer: safe area inset + fixed offset for the nav bar.
                      SizedBox(height: bottomPad + 80),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  void _showCountriesSheet(
    BuildContext context,
    ThemeData theme,
    AppLocalizations localizations,
  ) {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (BuildContext bottomSheetContext) {
        return NativeModalSheetScaffold(
          theme: theme,
          title: localizations.countries,
          closeTooltip: localizations.close,
          maxHeightFraction: 0.9,
          onClose: () => Navigator.pop(bottomSheetContext),
          child: const CountriesWidget(),
        );
      },
    );
  }
}
