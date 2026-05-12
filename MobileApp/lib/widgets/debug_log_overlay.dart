import 'package:flutter/foundation.dart' show kDebugMode, kProfileMode;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show Clipboard, ClipboardData;
import '../utils/debug_logger.dart';

/// Floating in-app debug log panel. Visible only in debug/profile builds.
///
/// Shows a small pill button (bottom-right) with a live warn+error count badge.
/// Tapping it slides up a panel listing all captured [LogEntry] items (newest
/// first) with per-entry Copy and a global Copy All / Clear action.
///
/// Usage: wrap your MaterialApp child with this widget in [MaterialApp.builder].
class DebugLogOverlay extends StatefulWidget {
  final Widget child;
  const DebugLogOverlay({super.key, required this.child});

  @override
  State<DebugLogOverlay> createState() => _DebugLogOverlayState();
}

class _DebugLogOverlayState extends State<DebugLogOverlay>
    with SingleTickerProviderStateMixin {
  bool _panelOpen = false;
  late final AnimationController _animCtrl;
  late final Animation<Offset> _slideAnim;

  @override
  void initState() {
    super.initState();
    _animCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 260),
    );
    _slideAnim = Tween<Offset>(
      begin: const Offset(0, 1),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _animCtrl, curve: Curves.easeOutCubic));
  }

  @override
  void dispose() {
    _animCtrl.dispose();
    super.dispose();
  }

  void _toggle() {
    setState(() => _panelOpen = !_panelOpen);
    if (_panelOpen) {
      _animCtrl.forward();
    } else {
      _animCtrl.reverse();
    }
  }

  void _close() {
    setState(() => _panelOpen = false);
    _animCtrl.reverse();
  }

  @override
  Widget build(BuildContext context) {
    if (!kDebugMode && !kProfileMode) return widget.child;

    return Stack(
      children: [
        widget.child,
        ValueListenableBuilder<List<LogEntry>>(
          valueListenable: DebugLogger.logNotifier,
          builder: (context, entries, _) {
            final warnCount =
                entries.where((e) => e.level == LogLevel.warn).length;
            final errorCount =
                entries.where((e) => e.level == LogLevel.error).length;
            return _DebugOverlayContent(
              entries: entries,
              warnCount: warnCount,
              errorCount: errorCount,
              panelOpen: _panelOpen,
              slideAnim: _slideAnim,
              onToggle: _toggle,
              onClose: _close,
            );
          },
        ),
      ],
    );
  }
}

class _DebugOverlayContent extends StatelessWidget {
  final List<LogEntry> entries;
  final int warnCount;
  final int errorCount;
  final bool panelOpen;
  final Animation<Offset> slideAnim;
  final VoidCallback onToggle;
  final VoidCallback onClose;

  const _DebugOverlayContent({
    required this.entries,
    required this.warnCount,
    required this.errorCount,
    required this.panelOpen,
    required this.slideAnim,
    required this.onToggle,
    required this.onClose,
  });

  Color get _badgeColor {
    if (errorCount > 0) return const Color(0xFFDC2626);
    if (warnCount > 0) return const Color(0xFFEA580C);
    return const Color(0xFF6B7280);
  }

  String get _badgeLabel {
    final total = warnCount + errorCount;
    if (total == 0) return '🐛';
    if (total > 99) return '99+';
    return total.toString();
  }

  Future<void> _copyAll(BuildContext context) async {
    if (entries.isEmpty) return;
    final text = entries.reversed.map((e) => e.toString()).join('\n');
    await Clipboard.setData(ClipboardData(text: text));
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Debug logs copied to clipboard'),
          duration: Duration(seconds: 2),
        ),
      );
    }
  }

  void _clear(BuildContext context) {
    DebugLogger.clearLogBuffer();
  }

  @override
  Widget build(BuildContext context) {
    final mq = MediaQuery.of(context);
    final bottomInset = mq.padding.bottom;
    final panelHeight = mq.size.height * 0.45;

    return Stack(
      children: [
        // Slide-up log panel
        Positioned(
          left: 0,
          right: 0,
          bottom: 0,
          child: SlideTransition(
            position: slideAnim,
            child: _LogPanel(
              entries: entries,
              panelHeight: panelHeight,
              bottomInset: bottomInset,
              onClose: onClose,
              onCopyAll: () => _copyAll(context),
              onClear: () => _clear(context),
            ),
          ),
        ),
        // Floating toggle button (above panel when open)
        Positioned(
          right: 12,
          bottom: panelOpen
              ? panelHeight + bottomInset + 8
              : bottomInset + 76,
          child: _TogglePill(
            label: _badgeLabel,
            color: _badgeColor,
            onTap: onToggle,
            isOpen: panelOpen,
          ),
        ),
      ],
    );
  }
}

class _TogglePill extends StatelessWidget {
  final String label;
  final Color color;
  final VoidCallback onTap;
  final bool isOpen;

  const _TogglePill({
    required this.label,
    required this.color,
    required this.onTap,
    required this.isOpen,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.92),
          borderRadius: BorderRadius.circular(20),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.25),
              blurRadius: 6,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              label,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 13,
                fontWeight: FontWeight.w700,
                fontFamily: 'monospace',
              ),
            ),
            const SizedBox(width: 4),
            Icon(
              isOpen ? Icons.keyboard_arrow_down : Icons.keyboard_arrow_up,
              color: Colors.white,
              size: 16,
            ),
          ],
        ),
      ),
    );
  }
}

class _LogPanel extends StatelessWidget {
  final List<LogEntry> entries;
  final double panelHeight;
  final double bottomInset;
  final VoidCallback onClose;
  final VoidCallback onCopyAll;
  final VoidCallback onClear;

  const _LogPanel({
    required this.entries,
    required this.panelHeight,
    required this.bottomInset,
    required this.onClose,
    required this.onCopyAll,
    required this.onClear,
  });

  @override
  Widget build(BuildContext context) {
    final reversed = entries.reversed.toList();
    return Material(
      elevation: 12,
      color: Colors.transparent,
      child: Container(
        height: panelHeight + bottomInset,
        decoration: const BoxDecoration(
          color: Color(0xFF1A1A2E),
          borderRadius: BorderRadius.vertical(top: Radius.circular(12)),
          border: Border(
            top: BorderSide(color: Color(0xFF374151), width: 1),
          ),
        ),
        child: Column(
          children: [
            // Handle / header
            _PanelHeader(
              entryCount: entries.length,
              onClose: onClose,
              onCopyAll: onCopyAll,
              onClear: onClear,
            ),
            // Entry list
            Expanded(
              child: entries.isEmpty
                  ? const Center(
                      child: Text(
                        'No warnings or errors yet',
                        style: TextStyle(
                          color: Color(0xFF6B7280),
                          fontSize: 13,
                          fontStyle: FontStyle.italic,
                        ),
                      ),
                    )
                  : ListView.separated(
                      padding: EdgeInsets.only(
                        bottom: bottomInset + 4,
                        top: 4,
                      ),
                      itemCount: reversed.length,
                      separatorBuilder: (_, __) => const Divider(
                        height: 1,
                        color: Color(0xFF2D3748),
                        indent: 8,
                        endIndent: 8,
                      ),
                      itemBuilder: (context, i) =>
                          _LogEntryTile(entry: reversed[i]),
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PanelHeader extends StatelessWidget {
  final int entryCount;
  final VoidCallback onClose;
  final VoidCallback onCopyAll;
  final VoidCallback onClear;

  const _PanelHeader({
    required this.entryCount,
    required this.onClose,
    required this.onCopyAll,
    required this.onClear,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 8, 8, 8),
      decoration: const BoxDecoration(
        border: Border(bottom: BorderSide(color: Color(0xFF374151), width: 1)),
      ),
      child: Row(
        children: [
          const Icon(Icons.bug_report_outlined, color: Color(0xFF9CA3AF), size: 16),
          const SizedBox(width: 6),
          Text(
            'Debug Logs ($entryCount)',
            style: const TextStyle(
              color: Color(0xFFE5E7EB),
              fontSize: 13,
              fontWeight: FontWeight.w700,
            ),
          ),
          const Spacer(),
          // Copy all
          _HeaderAction(
            icon: Icons.copy_outlined,
            label: 'Copy',
            onTap: onCopyAll,
          ),
          const SizedBox(width: 4),
          // Clear
          _HeaderAction(
            icon: Icons.delete_outline,
            label: 'Clear',
            onTap: onClear,
            color: const Color(0xFFEF4444),
          ),
          const SizedBox(width: 4),
          // Close
          GestureDetector(
            onTap: onClose,
            child: const Padding(
              padding: EdgeInsets.all(4),
              child: Icon(Icons.close, color: Color(0xFF9CA3AF), size: 18),
            ),
          ),
        ],
      ),
    );
  }
}

class _HeaderAction extends StatelessWidget {
  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final Color color;

  const _HeaderAction({
    required this.icon,
    required this.label,
    required this.onTap,
    this.color = const Color(0xFF9CA3AF),
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.15),
          borderRadius: BorderRadius.circular(4),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, color: color, size: 13),
            const SizedBox(width: 3),
            Text(
              label,
              style: TextStyle(
                color: color,
                fontSize: 11,
                fontWeight: FontWeight.w600,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LogEntryTile extends StatelessWidget {
  final LogEntry entry;
  const _LogEntryTile({required this.entry});

  Color get _levelColor =>
      entry.level == LogLevel.error
          ? const Color(0xFFFC8181)
          : const Color(0xFFFBD38D);

  String get _levelLabel =>
      entry.level == LogLevel.error ? 'ERR' : 'WRN';

  String get _timeLabel {
    final t = entry.time;
    final h = t.hour.toString().padLeft(2, '0');
    final m = t.minute.toString().padLeft(2, '0');
    final s = t.second.toString().padLeft(2, '0');
    return '$h:$m:$s';
  }

  Future<void> _copyEntry(BuildContext context) async {
    await Clipboard.setData(ClipboardData(text: entry.toString()));
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Entry copied'),
          duration: Duration(seconds: 1),
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onLongPress: () => _copyEntry(context),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Tag row
            Row(
              children: [
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                  decoration: BoxDecoration(
                    color: _levelColor.withValues(alpha: 0.2),
                    borderRadius: BorderRadius.circular(3),
                    border: Border.all(color: _levelColor.withValues(alpha: 0.4)),
                  ),
                  child: Text(
                    _levelLabel,
                    style: TextStyle(
                      color: _levelColor,
                      fontSize: 10,
                      fontWeight: FontWeight.w800,
                      fontFamily: 'monospace',
                    ),
                  ),
                ),
                const SizedBox(width: 6),
                Text(
                  entry.tag,
                  style: const TextStyle(
                    color: Color(0xFF93C5FD),
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                    fontFamily: 'monospace',
                  ),
                ),
                const Spacer(),
                Text(
                  _timeLabel,
                  style: const TextStyle(
                    color: Color(0xFF6B7280),
                    fontSize: 10,
                    fontFamily: 'monospace',
                  ),
                ),
              ],
            ),
            const SizedBox(height: 3),
            // Message
            Text(
              entry.message,
              style: const TextStyle(
                color: Color(0xFFD1D5DB),
                fontSize: 11.5,
                fontFamily: 'monospace',
                height: 1.4,
              ),
              maxLines: 4,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ),
      ),
    );
  }
}
