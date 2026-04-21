import 'package:flutter/material.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';
import '../utils/constants.dart';

/// A floating action button for refreshing webview pages
class WebViewRefreshButton extends StatelessWidget {
  final InAppWebViewController? webViewController;
  final EdgeInsets? margin;
  final String? heroTag;

  const WebViewRefreshButton({
    super.key,
    required this.webViewController,
    this.margin,
    this.heroTag,
  });

  @override
  Widget build(BuildContext context) {
    if (webViewController == null) {
      return const SizedBox.shrink();
    }

    return Positioned(
      bottom: margin?.bottom ?? 24,
      right: margin?.right ?? 24,
      child: FloatingActionButton(
        heroTag: heroTag ?? 'webview_refresh_button',
        onPressed: () {
          webViewController?.reload();
        },
        backgroundColor: Color(AppConstants.ifrcRed),
        foregroundColor: Theme.of(context).colorScheme.onPrimary,
        tooltip: 'Refresh page',
        child: const Icon(Icons.refresh),
      ),
    );
  }
}
