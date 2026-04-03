import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import 'dart:async';
import '../utils/constants.dart';

/// A smart pull-to-refresh wrapper for WebViews that only triggers
/// when the WebView is scrolled to the top, preventing conflicts with normal scrolling.
///
/// This widget wraps a WebView and provides pull-to-refresh functionality that:
/// - Only triggers when the WebView content is scrolled to the top
/// - Uses JavaScript to detect scroll position before allowing refresh
/// - Prevents conflicts with normal WebView scrolling
class WebViewPullToRefresh extends StatefulWidget {
  final InAppWebViewController? webViewController;
  final Widget child;
  final Future<void> Function() onRefresh;
  final Color? color;

  const WebViewPullToRefresh({
    super.key,
    required this.webViewController,
    required this.child,
    required this.onRefresh,
    this.color,
  });

  @override
  State<WebViewPullToRefresh> createState() => _WebViewPullToRefreshState();
}

class _WebViewPullToRefreshState extends State<WebViewPullToRefresh> {
  bool _isCheckingScroll = false;
  Timer? _scrollCheckTimer;
  bool _isAtTop = true;

  @override
  void initState() {
    super.initState();
    // Periodically check scroll position to enable/disable refresh
    _scrollCheckTimer = Timer.periodic(const Duration(milliseconds: 300), (_) {
      if (mounted) {
        _checkScrollPosition();
      }
    });
  }

  @override
  void dispose() {
    _scrollCheckTimer?.cancel();
    super.dispose();
  }

  /// Check if WebView is scrolled to the top using JavaScript
  Future<void> _checkScrollPosition() async {
    if (widget.webViewController == null || _isCheckingScroll) {
      return;
    }

    try {
      _isCheckingScroll = true;

      // Use JavaScript to check scroll position
      final result = await widget.webViewController!.evaluateJavascript(source: '''
        (function() {
          // Check window scroll position
          var scrollTop = window.pageYOffset || document.documentElement.scrollTop || document.body.scrollTop || 0;
          // Also check if document body is scrollable
          var bodyScrollTop = document.body.scrollTop || 0;
          var documentElementScrollTop = document.documentElement.scrollTop || 0;

          // Return true if we're at the top (with small threshold for floating point precision)
          return (scrollTop <= 10 && bodyScrollTop <= 10 && documentElementScrollTop <= 10);
        })();
      ''');

      final isAtTop = result == 'true' || result == true;

      if (mounted && _isAtTop != isAtTop) {
        setState(() {
          _isAtTop = isAtTop;
        });
      }
    } catch (e) {
      // If we can't check, assume we're at top (fail-safe)
      if (mounted && !_isAtTop) {
        setState(() {
          _isAtTop = true;
        });
      }
    } finally {
      _isCheckingScroll = false;
    }
  }

  /// Handle refresh with scroll position check
  Future<void> _handleRefresh() async {
    // Double-check scroll position before refreshing
    await _checkScrollPosition();

    if (_isAtTop) {
      // Only refresh if we're at the top
      await widget.onRefresh();
    }
    // If not at top, do nothing (RefreshIndicator will dismiss automatically)
  }

  @override
  Widget build(BuildContext context) {
    // RefreshIndicator can work with WebViews by detecting pull-down gestures
    // We check scroll position before refreshing to prevent conflicts
    return RefreshIndicator(
      onRefresh: _handleRefresh,
      color: widget.color ?? Color(AppConstants.ifrcRed),
      // The child is the WebView - RefreshIndicator will detect gestures on it
      child: widget.child,
    );
  }
}
