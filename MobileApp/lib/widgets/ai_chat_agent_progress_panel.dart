import 'dart:async';

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

  /// Fixed square slot so [CircularProgressIndicator] never stretches into an oval
  /// when the surrounding [Row] is taller than it is wide.
  Widget _spinner(Color color) => SizedBox(
        width: 18,
        height: 18,
        child: Center(
          child: SizedBox(
            width: 14,
            height: 14,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              color: color,
            ),
          ),
        ),
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
    final currentLabel = AiChatAgentProgressCopy.stepMessage(loc, current.message);

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
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    _spinner(muted),
                    const SizedBox(width: 6),
                    Flexible(
                      child: AnimatedSwitcher(
                        duration: const Duration(milliseconds: 200),
                        child: _RunningStepLabel(
                          key: ValueKey<String>(current.message),
                          text: currentLabel,
                          style: textStyle,
                          maxLines: 3,
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
    final label = AiChatAgentProgressCopy.stepMessage(loc, step.message);
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
                height: 18,
                child: isCurrent
                    ? _spinner(muted)
                    : Icon(Icons.check, size: 16, color: doneIconColor),
              ),
              const SizedBox(width: 6),
              Expanded(
                child: isCurrent
                    ? _RunningStepLabel(
                        text: label,
                        style: textStyle.copyWith(fontSize: 14),
                      )
                    : Text(
                        label,
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

/// Step label with a trailing `.` / `..` / `...` cycle while the step is running.
class _RunningStepLabel extends StatefulWidget {
  final String text;
  final TextStyle? style;
  final int? maxLines;

  const _RunningStepLabel({
    super.key,
    required this.text,
    this.style,
    this.maxLines,
  });

  @override
  State<_RunningStepLabel> createState() => _RunningStepLabelState();
}

class _RunningStepLabelState extends State<_RunningStepLabel> {
  static const _tick = Duration(milliseconds: 450);
  Timer? _timer;
  int _dotCount = 1;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(_tick, (_) {
      if (!mounted) return;
      setState(() => _dotCount = _dotCount >= 3 ? 1 : _dotCount + 1);
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final base = widget.text.trimRight().replaceFirst(RegExp(r'\.{1,3}$'), '');
    return Text(
      '$base${'.' * _dotCount}',
      maxLines: widget.maxLines,
      overflow: widget.maxLines != null ? TextOverflow.ellipsis : TextOverflow.clip,
      style: widget.style,
    );
  }
}
