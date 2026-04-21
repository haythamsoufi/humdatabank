import 'package:flutter/material.dart';

import '../models/shared/ai_chat.dart';
import '../utils/constants.dart';

/// Mirrors Backoffice `chat-progress-panel` / `chat-progress-steps` (chatbot.css).
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
  final Set<int> _collapsed = {};

  @override
  Widget build(BuildContext context) {
    if (widget.steps.isEmpty) return const SizedBox.shrink();

    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final muted = cs.onSurfaceVariant;
    final subtle = cs.outline;
    final doneGreen = const Color(AppConstants.successColor);
    final doneIconColor = theme.brightness == Brightness.dark
        ? const Color(0xFFBDBDBD)
        : doneGreen;

    return Align(
      alignment: Alignment.centerLeft,
      child: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: MediaQuery.sizeOf(context).width * 0.92),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(4, 4, 8, 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Steps in progress',
                style: theme.textTheme.titleSmall?.copyWith(
                      color: muted,
                    ) ??
                    TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                      color: muted,
                    ),
              ),
              const SizedBox(height: 6),
              ...List.generate(widget.steps.length, (i) {
                final step = widget.steps[i];
                final isLast = i == widget.steps.length - 1;
                final hasDetail = step.detailLines.isNotEmpty;
                final collapsed = _collapsed.contains(i);
                final detailText = step.detailLines.join('\n');

                return Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      InkWell(
                        onTap: hasDetail
                            ? () => setState(() {
                                  if (collapsed) {
                                    _collapsed.remove(i);
                                  } else {
                                    _collapsed.add(i);
                                  }
                                })
                            : null,
                        borderRadius: BorderRadius.circular(4),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            SizedBox(
                              width: 18,
                              child: isLast
                                  ? SizedBox(
                                      width: 14,
                                      height: 14,
                                      child: FittedBox(
                                        fit: BoxFit.contain,
                                        child: SizedBox(
                                          width: 36,
                                          height: 36,
                                          child: CircularProgressIndicator(
                                            strokeWidth: 2,
                                            color: muted,
                                          ),
                                        ),
                                      ),
                                    )
                                  : Icon(Icons.check, size: 16, color: doneIconColor),
                            ),
                            const SizedBox(width: 6),
                            Expanded(
                              child: Text(
                                step.message,
                                style: theme.textTheme.bodyLarge?.copyWith(
                                      height: 1.35,
                                      letterSpacing: -0.2,
                                      color: muted,
                                    ) ??
                                    TextStyle(
                                      fontSize: 16,
                                      height: 1.35,
                                      letterSpacing: -0.2,
                                      color: muted,
                                    ),
                              ),
                            ),
                            if (hasDetail)
                              Icon(
                                collapsed ? Icons.chevron_right : Icons.expand_more,
                                size: 16,
                                color: subtle,
                              ),
                          ],
                        ),
                      ),
                      if (hasDetail && !collapsed)
                        Padding(
                          padding: const EdgeInsets.only(left: 24, top: 2, right: 8),
                          child: Text(
                            detailText,
                            style: theme.textTheme.bodyMedium?.copyWith(
                                  height: 1.4,
                                  color: subtle,
                                ) ??
                                TextStyle(
                                  fontSize: 14,
                                  height: 1.4,
                                  color: subtle,
                                ),
                          ),
                        ),
                    ],
                  ),
                );
              }),
            ],
          ),
        ),
      ),
    );
  }
}
