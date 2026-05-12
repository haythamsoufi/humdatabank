import '../l10n/app_localizations.dart';
import '../providers/shared/ai_chat_provider.dart';

/// Localizes agent progress strings emitted by the Backoffice (often English in
/// inflight snapshots). Prefer server-side [force_locale]; this is a client fallback.
class AiChatAgentProgressCopy {
  AiChatAgentProgressCopy._();

  static String panelTitle(AppLocalizations loc) => loc.aiAgentProgressTitle;

  static String stepMessage(AppLocalizations loc, String raw) {
    final t = raw.trim();
    if (t == 'Preparing query…' || t == 'Preparing query...') {
      return loc.aiAgentStepPreparingQuery;
    }
    if (t == 'Planning approach…' || t == 'Planning approach...') {
      return loc.aiAgentStepPlanning;
    }
    if (t == 'Reviewing results…' || t == 'Reviewing results...') {
      return loc.aiAgentStepReviewing;
    }
    if (t == 'Drafting answer…' || t == 'Drafting answer...') {
      return loc.aiAgentStepDrafting;
    }
    if (t == 'Replying…' || t == 'Replying...') {
      return loc.aiAgentStepReplying;
    }
    if (t.contains('No single-tool shortcut') &&
        t.toLowerCase().contains('reviewing')) {
      final low = t.toLowerCase();
      final idx = low.indexOf('reviewing');
      if (idx >= 0) {
        final rest = t
            .substring(idx)
            .replaceFirst(
              RegExp(r'^reviewing\s*[:：—\-]\s*', caseSensitive: false),
              '',
            )
            .trim();
        if (rest.isNotEmpty) {
          return loc.aiAgentStepNoShortcutReviewing(rest);
        }
      }
      return loc.aiAgentStepNoShortcutFull;
    }
    if (t.contains('No single-tool shortcut') &&
        t.toLowerCase().contains('full planning')) {
      return loc.aiAgentStepNoShortcutFull;
    }
    return raw;
  }

  static String detailLine(AppLocalizations loc, String raw) {
    final t = raw.trim();
    if (t == AiChatProvider.aiAgentStepDoneSentinel) {
      return loc.aiAgentStepDone;
    }
    if (t == 'Thinking what to do next.' ||
        t == 'Thinking about what to do next.') {
      return loc.aiAgentStepThinkingNext;
    }
    if (_isInternalToolDetailLine(t)) {
      return '';
    }
    return raw;
  }

  /// Hides raw tool-arg dumps (e.g. `include_saved: True`) if they still appear.
  static bool _isInternalToolDetailLine(String t) {
    if (t.isEmpty) return true;
    if (RegExp(r'^[a-z][a-z0-9_]*\s*:\s*', caseSensitive: false).hasMatch(t)) {
      return true;
    }
    if (RegExp(r'^include_saved\s*:', caseSensitive: false).hasMatch(t)) {
      return true;
    }
    if (RegExp(r'^limit_periods\s*:', caseSensitive: false).hasMatch(t)) {
      return true;
    }
    return false;
  }

  static List<String> detailLinesForDisplay(
    AppLocalizations loc,
    List<String> lines,
  ) {
    final out = <String>[];
    for (final line in lines) {
      final d = detailLine(loc, line);
      if (d.isNotEmpty) {
        out.add(d);
      }
    }
    return out;
  }
}
