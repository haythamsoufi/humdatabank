import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../../l10n/app_localizations.dart';
import '../../models/shared/ai_chat_launch_args.dart';
import '../../config/routes.dart';
import '../../utils/navigation_helper.dart';

/// Horizontally scrollable quick prompts → AI chat with auto-send.
class LandingQuickPromptsRow extends StatelessWidget {
  final AppLocalizations l10n;
  /// When true, styles for chips on the dark hero gradient (light text / glass).
  /// When false, uses [ThemeData] surfaces for use on scaffold background.
  final bool onHeroBackdrop;

  const LandingQuickPromptsRow({
    super.key,
    required this.l10n,
    this.onHeroBackdrop = false,
  });

  void _onTap(BuildContext context, String prompt) {
    HapticFeedback.selectionClick();
    Navigator.of(context).pushNamed(
      AppRoutes.aiChat,
      arguments: AiChatLaunchArgs(
        bottomNavTabIndex: NavigationHelper.aiChatMainTabPageIndex(context),
        startNewConversation: true,
        initialText: prompt,
        sendImmediately: true,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final isDark = theme.brightness == Brightness.dark;
    final prompts = [
      l10n.homeLandingQuickPrompt1,
      l10n.homeLandingQuickPrompt2,
      l10n.homeLandingQuickPrompt3,
    ];

    return SizedBox(
      height: 44,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 20),
        itemCount: prompts.length,
        separatorBuilder: (context, index) => const SizedBox(width: 10),
        itemBuilder: (context, i) {
          final text = prompts[i];
          final Color bg;
          final Color borderColor;
          final Color fg;
          if (onHeroBackdrop) {
            bg = Colors.white.withValues(alpha: 0.22);
            borderColor = Colors.white.withValues(alpha: 0.4);
            fg = Colors.white;
          } else {
            bg = cs.surfaceContainerHigh;
            borderColor =
                cs.outlineVariant.withValues(alpha: isDark ? 0.5 : 0.4);
            fg = cs.onSurface;
          }
          return Material(
            color: bg,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
              side: BorderSide(color: borderColor),
            ),
            clipBehavior: Clip.antiAlias,
            child: InkWell(
              onTap: () => _onTap(context, text),
              borderRadius: BorderRadius.circular(12),
              splashColor: onHeroBackdrop
                  ? Colors.white.withValues(alpha: 0.15)
                  : cs.primary.withValues(alpha: 0.08),
              child: Padding(
                padding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                child: Center(
                  child: Text(
                    text,
                    style: theme.textTheme.labelLarge?.copyWith(
                      color: fg,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
  }
}
