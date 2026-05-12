import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../l10n/app_localizations.dart';
import '../../models/shared/ai_chat_launch_args.dart';
import '../../config/routes.dart';
import '../../utils/constants.dart';
import '../../utils/navigation_helper.dart';

/// Glass-style AI ask card.
///
/// In its default (collapsed) state the card shows a read-only pill hint.
/// Tapping it calls [onExpand] so the parent can run the hero-title dismiss
/// animation.  Once [isExpanded] flips to `true` the pill becomes a live
/// [TextField]; submitting it (or tapping a quick-prompt chip above) navigates
/// to the AI-chat screen and calls [onNavigated] so the parent can reset state.
class LandingAiEntryCard extends StatefulWidget {
  final AppLocalizations l10n;

  /// No longer used — kept so call-sites need no change.
  final ScrollController? scrollController;

  /// Whether the hero title has been dismissed and this card is in focus mode.
  final bool isExpanded;

  /// Called when the card is tapped while [isExpanded] is false.
  final VoidCallback? onExpand;

  /// Called immediately before navigating to the AI-chat screen.
  final VoidCallback? onNavigated;

  const LandingAiEntryCard({
    super.key,
    required this.l10n,
    this.scrollController,
    this.isExpanded = false,
    this.onExpand,
    this.onNavigated,
  });

  @override
  State<LandingAiEntryCard> createState() => _LandingAiEntryCardState();
}

class _LandingAiEntryCardState extends State<LandingAiEntryCard>
    with SingleTickerProviderStateMixin {
  final _textController = TextEditingController();
  final _focusNode = FocusNode();

  // Animates the inner pill → text-field swap.
  late final AnimationController _morphAnim;
  late final Animation<double> _pillFade;
  late final Animation<double> _fieldFade;

  @override
  void initState() {
    super.initState();
    _morphAnim = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 280),
      value: widget.isExpanded ? 1.0 : 0.0,
    );
    _pillFade = Tween<double>(begin: 1, end: 0).animate(
      CurvedAnimation(
        parent: _morphAnim,
        curve: const Interval(0, 0.45, curve: Curves.easeOut),
      ),
    );
    _fieldFade = Tween<double>(begin: 0, end: 1).animate(
      CurvedAnimation(
        parent: _morphAnim,
        curve: const Interval(0.45, 1.0, curve: Curves.easeIn),
      ),
    );
  }

  @override
  void didUpdateWidget(LandingAiEntryCard old) {
    super.didUpdateWidget(old);
    if (widget.isExpanded != old.isExpanded) {
      if (widget.isExpanded) {
        _morphAnim.forward();
        // Focus the chat field after the pill→field morph finishes so the
        // keyboard appears and Tab order continues to send + quick prompts.
        Future<void>(() async {
          await Future<void>.delayed(const Duration(milliseconds: 280));
          if (!mounted || !widget.isExpanded) return;
          void request() {
            if (!mounted || !widget.isExpanded) return;
            _focusNode.requestFocus();
          }

          WidgetsBinding.instance.addPostFrameCallback((_) {
            request();
            // Some platforms apply focus/IME one frame late.
            WidgetsBinding.instance.addPostFrameCallback((_) => request());
          });
        });
      } else {
        _morphAnim.reverse();
        _focusNode.unfocus();
        _textController.clear();
      }
    }
  }

  @override
  void dispose() {
    _morphAnim.dispose();
    _textController.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _submit() {
    final trimmed = _textController.text.trim();
    _navigateToChat(trimmed.isEmpty ? null : trimmed);
  }

  void _navigateToChat(String? initialText) {
    widget.onNavigated?.call();
    Navigator.of(context).pushNamed(
      AppRoutes.aiChat,
      arguments: AiChatLaunchArgs(
        bottomNavTabIndex: NavigationHelper.aiChatMainTabPageIndex(context),
        startNewConversation: true,
        initialText: initialText,
        sendImmediately: initialText != null && initialText.isNotEmpty,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final glass = isDark
        ? Colors.white.withValues(alpha: 0.08)
        : Colors.white.withValues(alpha: 0.14);
    final border = Colors.white.withValues(alpha: 0.22);
    final accent = Color(AppConstants.ifrcRed);

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: GestureDetector(
        onTap: !widget.isExpanded ? () {
          HapticFeedback.lightImpact();
          widget.onExpand?.call();
        } : null,
        behavior: HitTestBehavior.opaque,
        child: ClipRRect(
          borderRadius: BorderRadius.circular(16),
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 12, sigmaY: 12),
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: glass,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: border),
              ),
              child: Padding(
                padding: const EdgeInsets.fromLTRB(14, 10, 14, 12),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      widget.l10n.homeLandingChatTitle,
                      style: theme.textTheme.titleSmall?.copyWith(
                        color: Colors.white,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      widget.l10n.homeLandingChatDescription,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: Colors.white.withValues(alpha: 0.85),
                        height: 1.25,
                      ),
                    ),
                    const SizedBox(height: 8),
                    // Pill hint fades out; text field fades in.
                    AnimatedBuilder(
                      animation: _morphAnim,
                      builder: (context, _) {
                        return Stack(
                          children: [
                            if (_pillFade.value > 0)
                              Opacity(
                                opacity: _pillFade.value,
                                child: IgnorePointer(
                                  child: _PillHint(
                                    l10n: widget.l10n,
                                    theme: theme,
                                    accent: accent,
                                  ),
                                ),
                              ),
                            if (_fieldFade.value > 0)
                              Opacity(
                                opacity: _fieldFade.value,
                                child: _ActiveField(
                                  controller: _textController,
                                  focusNode: _focusNode,
                                  placeholder: widget.l10n.homeLandingAskPlaceholder,
                                  accent: accent,
                                  onSubmit: _submit,
                                ),
                              ),
                          ],
                        );
                      },
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Sub-widgets
// ---------------------------------------------------------------------------

class _PillHint extends StatelessWidget {
  final AppLocalizations l10n;
  final ThemeData theme;
  final Color accent;

  const _PillHint({
    required this.l10n,
    required this.theme,
    required this.accent,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(4, 4, 4, 4),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.95),
        borderRadius: BorderRadius.circular(26),
        border: Border.all(color: theme.colorScheme.outline),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Expanded(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(10, 9, 4, 9),
              child: Text(
                l10n.homeLandingAskPlaceholder,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(color: Colors.grey.shade500, fontSize: 14),
              ),
            ),
          ),
          Container(
            width: 40,
            height: 40,
            decoration: BoxDecoration(
              color: accent,
              shape: BoxShape.circle,
            ),
            child: const Icon(
              Icons.arrow_forward_rounded,
              color: Colors.white,
              size: 20,
            ),
          ),
        ],
      ),
    );
  }
}

class _ActiveField extends StatelessWidget {
  final TextEditingController controller;
  final FocusNode focusNode;
  final String placeholder;
  final Color accent;
  final VoidCallback onSubmit;

  const _ActiveField({
    required this.controller,
    required this.focusNode,
    required this.placeholder,
    required this.accent,
    required this.onSubmit,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(4, 4, 4, 4),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.95),
        borderRadius: BorderRadius.circular(26),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          Expanded(
            child: FocusTraversalOrder(
              order: const NumericFocusOrder(0),
              child: TextField(
                controller: controller,
                focusNode: focusNode,
                minLines: 1,
                maxLines: 3,
                keyboardType: TextInputType.text,
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => onSubmit(),
                style: TextStyle(
                  color: Colors.grey.shade800,
                  fontSize: 14,
                  height: 1.35,
                ),
                cursorColor: accent,
                decoration: InputDecoration(
                  hintText: placeholder,
                  hintStyle: TextStyle(
                    color: Colors.grey.shade500,
                    fontSize: 14,
                  ),
                  filled: true,
                  fillColor: Colors.transparent,
                  isDense: true,
                  border: InputBorder.none,
                  enabledBorder: InputBorder.none,
                  focusedBorder: InputBorder.none,
                  disabledBorder: InputBorder.none,
                  errorBorder: InputBorder.none,
                  focusedErrorBorder: InputBorder.none,
                  contentPadding: const EdgeInsets.fromLTRB(12, 9, 4, 9),
                ),
              ),
            ),
          ),
          FocusTraversalOrder(
            order: const NumericFocusOrder(1),
            child: IconButton(
              onPressed: onSubmit,
              style: IconButton.styleFrom(
                backgroundColor: accent,
                foregroundColor: Colors.white,
                fixedSize: const Size(40, 40),
                padding: EdgeInsets.zero,
                shape: const CircleBorder(),
              ),
              icon: const Icon(Icons.arrow_forward_rounded, size: 20),
              tooltip: 'Send',
            ),
          ),
        ],
      ),
    );
  }
}
