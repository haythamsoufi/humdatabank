import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Vertical list of quick-prompt rows shown below the AI entry card after the
/// hero title has been dismissed. Each row is keyboard-focusable (Tab / Enter).
class LandingQuickPrompts extends StatelessWidget {
  final List<String> prompts;
  final ValueChanged<String> onPromptSelected;

  /// First [NumericFocusOrder] value for [FocusTraversalOrder] (text field +
  /// send use lower indices from the parent card).
  static const int traversalBaseIndex = 2;

  const LandingQuickPrompts({
    super.key,
    required this.prompts,
    required this.onPromptSelected,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          for (var i = 0; i < prompts.length; i++) ...[
            if (i > 0) const SizedBox(height: 8),
            FocusTraversalOrder(
              order: NumericFocusOrder((traversalBaseIndex + i).toDouble()),
              child: _PromptChip(
                label: prompts[i],
                onTap: () {
                  HapticFeedback.selectionClick();
                  onPromptSelected(prompts[i]);
                },
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _PromptChip extends StatelessWidget {
  final String label;
  final VoidCallback onTap;

  const _PromptChip({required this.label, required this.onTap});

  @override
  Widget build(BuildContext context) {
    return Focus(
      onKeyEvent: (node, event) {
        if (event is! KeyDownEvent) {
          return KeyEventResult.ignored;
        }
        if (event.logicalKey == LogicalKeyboardKey.enter ||
            event.logicalKey == LogicalKeyboardKey.space) {
          HapticFeedback.selectionClick();
          onTap();
          return KeyEventResult.handled;
        }
        return KeyEventResult.ignored;
      },
      child: Builder(
        builder: (context) {
          final focused = Focus.of(context).hasFocus;
          return Material(
            color: Colors.transparent,
            child: InkWell(
              onTap: () {
                HapticFeedback.selectionClick();
                onTap();
              },
              borderRadius: BorderRadius.circular(12),
              focusColor: Colors.white24,
              child: DecoratedBox(
                decoration: BoxDecoration(
                  color: Colors.white.withValues(alpha: focused ? 0.22 : 0.13),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(
                    color: focused
                        ? Colors.white
                        : Colors.white.withValues(alpha: 0.35),
                    width: focused ? 2 : 1,
                  ),
                ),
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 14,
                    vertical: 12,
                  ),
                  child: Text(
                    label,
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 13,
                      fontWeight: focused ? FontWeight.w600 : FontWeight.w500,
                      height: 1.2,
                    ),
                    maxLines: 1,
                    softWrap: false,
                    overflow: TextOverflow.ellipsis,
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
