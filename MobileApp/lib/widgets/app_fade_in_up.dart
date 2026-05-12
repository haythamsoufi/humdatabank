import 'package:flutter/material.dart';
import '../utils/constants.dart';

/// Fades in and slides up slightly. Optional [staggerIndex] offsets start time
/// for list choreography; indices beyond [maxStaggerItems] snap visible (no wait).
class AppFadeInUp extends StatefulWidget {
  const AppFadeInUp({
    super.key,
    required this.child,
    this.delay = Duration.zero,
    this.staggerIndex,
    this.staggerDelay = const Duration(milliseconds: 42),
    this.maxStaggerItems = 14,
    this.duration,
    this.curve = Curves.easeOutCubic,
    /// Vertical slide as a fraction of the child height (Material [SlideTransition]).
    this.beginSlideFraction = 0.06,
  });

  final Widget child;
  final Duration delay;
  final int? staggerIndex;
  final Duration staggerDelay;
  final int maxStaggerItems;
  final Duration? duration;
  final Curve curve;
  final double beginSlideFraction;

  @override
  State<AppFadeInUp> createState() => _AppFadeInUpState();
}

class _AppFadeInUpState extends State<AppFadeInUp>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  late final Animation<double> _opacity;
  late final Animation<Offset> _slide;

  Duration get _effectiveDelay {
    var d = widget.delay;
    if (widget.staggerIndex != null) {
      final slot = widget.staggerIndex!.clamp(0, widget.maxStaggerItems);
      d += widget.staggerDelay * slot;
    }
    const cap = Duration(milliseconds: 520);
    return d > cap ? cap : d;
  }

  Duration get _animDuration =>
      widget.duration ?? AppConstants.animationMedium;

  bool get _snapVisible =>
      widget.staggerIndex != null &&
      widget.staggerIndex! > widget.maxStaggerItems;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: _animDuration);
    final curved = CurvedAnimation(parent: _controller, curve: widget.curve);
    _opacity = Tween<double>(begin: 0, end: 1).animate(curved);
    _slide = Tween<Offset>(
      begin: Offset(0, widget.beginSlideFraction),
      end: Offset.zero,
    ).animate(curved);

    if (_snapVisible) {
      _controller.value = 1;
      return;
    }

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      Future.delayed(_effectiveDelay, () {
        if (mounted) _controller.forward();
      });
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _opacity,
      child: SlideTransition(
        position: _slide,
        child: widget.child,
      ),
    );
  }
}
