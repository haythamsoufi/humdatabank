import 'package:flutter/material.dart';

import '../l10n/app_localizations.dart';
import '../models/shared/ai_chat.dart';
import '../utils/ai_chat_agent_progress_localize.dart';
import '../utils/constants.dart';

/// Single status line showing the current agent step; tap to expand the full workflow.
class AiChatAgentProgressPanel extends StatefulWidget {
  final List<AiChatAgentStep> steps;

  const AiChatAgentProgressPanel({
    super.key,
    required this.steps,
  });

  @override
  State<AiChatAgentProgressPanel> createState() => _AiChatAgentProgressPanelState();
}

class _AiChatAgentProgressPanelState extends State<AiChatAgentProgressPanel> {
  bool _expanded = false;

  Widget _spinner(Color color) => SizedBox(
        width: 14,
        height: 14,
        child: CircularProgressIndicator(strokeWidth: 2, color: color),
      );

  @override
  Widget build(BuildContext context) {
    if (widget.steps.isEmpty) return const SizedBox.shrink();

    final loc = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final muted = cs.onSurfaceVariant;
    final subtle = cs.outline;
    final doneIconColor = theme.brightness == Brightness.dark
        ? const Color(0xFFBDBDBD)
        : const Color(AppConstants.successColor);

    final textStyle = theme.textTheme.bodyLarge?.copyWith(
          height: 1.35,
          letterSpacing: -0.2,
          color: muted,
        ) ??
        TextStyle(fontSize: 16, height: 1.35, letterSpacing: -0.2, color: muted);
    final detailStyle = theme.textTheme.bodyMedium?.copyWith(
          height: 1.4,
          color: subtle,
        ) ??
        TextStyle(fontSize: 14, height: 1.4, color: subtle);

    final current = widget.steps.last;
    final lastIndex = widget.steps.length - 1;

    return Align(
      alignment: Alignment.centerLeft,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width * 0.92),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(4, 4, 8, 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              InkWell(
                onTap: () => setState(() => _expanded = !_expanded),
                borderRadius: BorderRadius.circular(4),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    SizedBox(width: 18, child: _spinner(muted)),
                    const SizedBox(width: 6),
                    Flexible(
                      child: AnimatedSwitcher(
                        duration: const Duration(milliseconds: 200),
                        child: Text(
                          AiChatAgentProgressCopy.stepMessage(loc, current.message),
                          key: ValueKey<String>(current.message),
                          maxLines: 3,
                          overflow: TextOverflow.ellipsis,
                          style: textStyle,
                        ),
                      ),
                    ),
                    const SizedBox(width: 4),
                    Icon(
                      _expanded ? Icons.expand_less : Icons.expand_more,
                      size: 18,
                      color: subtle,
                    ),
                  ],
                ),
              ),
              AnimatedSize(
                duration: const Duration(milliseconds: 200),
                alignment: Alignment.topLeft,
                child: _expanded
                    ? Padding(
                        padding: const EdgeInsets.only(top: 8, left: 2),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            for (var i = 0; i < widget.steps.length; i++)
                              _stepRow(
                                loc: loc,
                                step: widget.steps[i],
                                isCurrent: i == lastIndex,
                                muted: muted,
                                doneIconColor: doneIconColor,
                                textStyle: textStyle,
                                detailStyle: detailStyle,
                              ),
                          ],
                        ),
                      )
                    : const SizedBox(width: double.infinity),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _stepRow({
    required AppLocalizations loc,
    required AiChatAgentStep step,
    required bool isCurrent,
    required Color muted,
    required Color doneIconColor,
    required TextStyle textStyle,
    required TextStyle detailStyle,
  }) {
    final details = AiChatAgentProgressCopy.detailLinesForDisplay(loc, step.detailLines);
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              SizedBox(
                width: 18,
                child: isCurrent
                    ? Align(
                        alignment: Alignment.centerLeft,
                        child: _spinner(muted),
                      )
                    : Icon(Icons.check, size: 16, color: doneIconColor),
              ),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  AiChatAgentProgressCopy.stepMessage(loc, step.message),
                  style: textStyle.copyWith(fontSize: 14),
                ),
              ),
            ],
          ),
          if (details.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(left: 24, top: 2, right: 8),
              child: Text(details.join('\n'), style: detailStyle.copyWith(fontSize: 13)),
            ),
        ],
      ),
    );
  }
}
