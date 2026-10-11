import 'package:flutter/material.dart';

/// Reported by a screen whose [Scaffold.drawer] opened or closed.
///
/// Tab pages host the side menu on their own scaffold. The shell tab bar lives
/// on the parent scaffold, so it paints above that drawer. Ancestors that own
/// the bar listen for this and hide the bar until the drawer closes.
class ShellDrawerOpenNotification extends Notification {
  const ShellDrawerOpenNotification({required this.isOpen});

  final bool isOpen;
}

/// Slides and fades [child] off the bottom edge while [hidden] is true.
///
/// The slot keeps its height so [Scaffold.extendBody] padding does not jump.
/// Pointers and semantics stay off until the bar has fully returned, so a
/// closing drawer is not covered by tab taps.
class DrawerAwareBottomBar extends StatefulWidget {
  const DrawerAwareBottomBar({
    super.key,
    required this.hidden,
    required this.child,
  });

  final bool hidden;
  final Widget child;

  /// Matches [DrawerController]'s settle duration.
  static const Duration slideDuration = Duration(milliseconds: 246);

  @override
  State<DrawerAwareBottomBar> createState() => _DrawerAwareBottomBarState();
}

class _DrawerAwareBottomBarState extends State<DrawerAwareBottomBar>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final CurvedAnimation _curve;
  late final Animation<Offset> _slide;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: DrawerAwareBottomBar.slideDuration,
      value: widget.hidden ? 0 : 1,
    );
    _curve = CurvedAnimation(parent: _controller, curve: Curves.easeInOutCubic);
    _slide = Tween<Offset>(
      begin: const Offset(0, 1.15),
      end: Offset.zero,
    ).animate(_curve);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final disabled = MediaQuery.disableAnimationsOf(context);
    final duration = disabled
        ? Duration.zero
        : DrawerAwareBottomBar.slideDuration;
    _controller.duration = duration;
    _controller.reverseDuration = duration;
  }

  @override
  void didUpdateWidget(DrawerAwareBottomBar oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.hidden == oldWidget.hidden) return;
    if (widget.hidden) {
      _controller.reverse();
    } else {
      _controller.forward();
    }
  }

  @override
  void dispose() {
    _curve.dispose();
    _controller.dispose();
    super.dispose();
  }

  bool get _interactive =>
      !widget.hidden && _controller.status == AnimationStatus.completed;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        final interactive = _interactive;
        return IgnorePointer(
          ignoring: !interactive,
          child: ExcludeSemantics(
            excluding: !interactive,
            child: SlideTransition(
              position: _slide,
              child: FadeTransition(opacity: _curve, child: child),
            ),
          ),
        );
      },
      child: widget.child,
    );
  }
}
