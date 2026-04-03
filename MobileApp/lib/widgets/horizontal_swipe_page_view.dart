import 'package:flutter/material.dart';
import 'package:flutter/gestures.dart';
import 'dart:math' as math;

/// A PageView wrapper that only responds to horizontal swipes within ±5 degrees.
/// Page navigation only works when swiping from screen edges (50px from left/right)
/// to avoid conflicts with interactive widgets like Dismissible.
class HorizontalSwipePageView extends StatefulWidget {
  final PageController controller;
  final ValueChanged<int>? onPageChanged;
  final List<Widget> children;

  const HorizontalSwipePageView({
    super.key,
    required this.controller,
    this.onPageChanged,
    required this.children,
  });

  @override
  State<HorizontalSwipePageView> createState() =>
      _HorizontalSwipePageViewState();
}

class _HorizontalSwipePageViewState extends State<HorizontalSwipePageView> {
  // Track drag start and current position
  Offset? _dragStartPosition;
  bool _isHorizontalSwipe = false;
  bool _shouldAllowPageSwipe = true; // Only allow if not on interactive widget
  double _dragDistance = 0.0;
  double _initialPage = 0.0;
  double? _screenWidth;

  // Convert degrees to radians
  static const double _maxAngleDegrees = 5.0;
  static const double _maxAngleRadians = _maxAngleDegrees * math.pi / 180.0;

  // More lenient angle for canceling (hysteresis) - once horizontal swipe is detected,
  // it won't cancel unless angle exceeds this
  static const double _cancelAngleDegrees = 20.0;
  static const double _cancelAngleRadians =
      _cancelAngleDegrees * math.pi / 180.0;

  // Minimum horizontal distance to consider it a swipe (reduced for faster activation)
  static const double _minSwipeDistance = 5.0;

  // Threshold to determine if swipe is horizontal enough
  // cos(5°) ≈ 0.9961946980917455, meaning horizontal distance should be at least 99.62% of total distance
  static const double _minHorizontalRatio = 0.9961946980917455;

  // More lenient ratio for canceling (hysteresis)
  // cos(20°) ≈ 0.9396926207859084, meaning horizontal distance should be at least 93.97% of total distance
  static const double _cancelHorizontalRatio = 0.9396926207859084;

  @override
  Widget build(BuildContext context) {
    _screenWidth = MediaQuery.of(context).size.width;
    return Listener(
      onPointerDown: _onPointerDown,
      onPointerMove: _onPointerMove,
      onPointerUp: _onPointerUp,
      onPointerCancel: _onPointerCancel,
      behavior: HitTestBehavior.translucent,
      child: PageView(
        controller: widget.controller,
        onPageChanged: widget.onPageChanged,
        physics: const NeverScrollableScrollPhysics(),
        children: widget.children,
      ),
    );
  }

  void _onPointerDown(PointerDownEvent event) {
    _dragStartPosition = event.position;
    _dragDistance = 0.0;
    _isHorizontalSwipe = false;

    // Only allow page navigation when swiping from the screen edges
    // This prevents conflict with Dismissible widgets (like notifications)
    final screenWidth = _screenWidth ?? MediaQuery.of(context).size.width;
    final edgeThreshold = 50.0; // 50px from left/right edges

    // Allow page swipe only if it starts from the edges
    // This way, swiping on notification items (center area) won't trigger page navigation
    final startX = event.position.dx;
    _shouldAllowPageSwipe =
        startX < edgeThreshold || startX > (screenWidth - edgeThreshold);

    if (widget.controller.hasClients) {
      _initialPage = widget.controller.page ?? 0.0;
    }
  }

  void _onPointerMove(PointerMoveEvent event) {
    if (_dragStartPosition == null || !_shouldAllowPageSwipe) return;

    final currentPosition = event.position;
    final delta = currentPosition - _dragStartPosition!;

    // Calculate the distance moved
    final horizontalDistance = delta.dx.abs();
    final verticalDistance = delta.dy.abs();
    final totalDistance = math.sqrt(horizontalDistance * horizontalDistance +
        verticalDistance * verticalDistance);

    _dragDistance = totalDistance;

    // Only check angle if we've moved enough
    if (totalDistance < _minSwipeDistance) {
      return;
    }

    // Calculate the ratio of horizontal to total distance
    // This is equivalent to cos(angle), where angle is the deviation from horizontal
    final horizontalRatio = horizontalDistance / totalDistance;

    if (_isHorizontalSwipe) {
      // Once a horizontal swipe is detected, use more lenient threshold to cancel it (hysteresis)
      // This prevents the swipe from being canceled due to minor finger movements
      if (horizontalRatio < _cancelHorizontalRatio) {
        // Angle deviated too much - cancel the swipe
        _isHorizontalSwipe = false;
        setState(() {});
      } else {
        // Continue the horizontal swipe
        // Programmatically update the page position smoothly
        // Limit movement to at most 1 page away from initial page
        if (widget.controller.hasClients && _screenWidth != null) {
          final pageDelta = -delta.dx /
              _screenWidth!; // Negative because dragging right should go to previous page
          // Clamp pageDelta to be within -1 to +1 from initial page
          final clampedDelta = pageDelta.clamp(-1.0, 1.0);
          final newPage = (_initialPage + clampedDelta)
              .clamp(0.0, (widget.children.length - 1).toDouble());
          widget.controller.jumpTo(newPage * _screenWidth!);
        }
      }
    } else {
      // Check if the swipe is within ±5 degrees of horizontal to start
      if (horizontalRatio >= _minHorizontalRatio) {
        // This is a horizontal swipe - allow it
        _isHorizontalSwipe = true;
        setState(() {});

        // Programmatically update the page position smoothly
        // Limit movement to at most 1 page away from initial page
        if (widget.controller.hasClients && _screenWidth != null) {
          final pageDelta = -delta.dx /
              _screenWidth!; // Negative because dragging right should go to previous page
          // Clamp pageDelta to be within -1 to +1 from initial page
          final clampedDelta = pageDelta.clamp(-1.0, 1.0);
          final newPage = (_initialPage + clampedDelta)
              .clamp(0.0, (widget.children.length - 1).toDouble());
          widget.controller.jumpTo(newPage * _screenWidth!);
        }
      }
      // If not horizontal enough, don't do anything - let vertical scrolling work
    }
  }

  void _onPointerUp(PointerUpEvent event) {
    if (_isHorizontalSwipe &&
        _dragStartPosition != null &&
        widget.controller.hasClients &&
        _screenWidth != null) {
      final currentPosition = event.position;
      final delta = currentPosition - _dragStartPosition!;

      // Determine if we should snap to next/previous page based on swipe distance
      // Reduced threshold for easier page changes (20% instead of 30%)
      final swipeThreshold = _screenWidth! * 0.2; // 20% of screen width

      if (delta.dx.abs() > swipeThreshold) {
        // Swipe was significant enough to change page
        // Calculate target page based on initial page, not current dragged position
        // This ensures we only move one page from where we started
        final initialPageInt = _initialPage.round();
        final targetPage = delta.dx > 0
            ? (initialPageInt - 1).clamp(0, widget.children.length - 1)
            : (initialPageInt + 1).clamp(0, widget.children.length - 1);

        widget.controller.animateToPage(
          targetPage,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );

        // Notify page change
        if (widget.onPageChanged != null) {
          widget.onPageChanged!(targetPage);
        }
      } else {
        // Swipe was too small, snap back to initial page
        final initialPageInt = _initialPage.round();
        widget.controller.animateToPage(
          initialPageInt,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    }

    _resetDragState();
  }

  void _onPointerCancel(PointerCancelEvent event) {
    // Snap back to initial page if drag was cancelled
    if (_isHorizontalSwipe && widget.controller.hasClients) {
      final initialPageInt = _initialPage.round();
      widget.controller.animateToPage(
        initialPageInt,
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeOut,
      );
    }
    _resetDragState();
  }

  void _resetDragState() {
    _dragStartPosition = null;
    _dragDistance = 0.0;
    _isHorizontalSwipe = false;
    _shouldAllowPageSwipe = true;
    _initialPage = 0.0;
    setState(() {});
  }
}
