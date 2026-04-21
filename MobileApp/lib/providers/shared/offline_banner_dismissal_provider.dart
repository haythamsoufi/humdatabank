import 'package:flutter/foundation.dart';

/// In-memory only: when [dismissForSession] is called, [OfflineBanner] stays
/// hidden until the app process exits (cold start). Not persisted to disk.
class OfflineBannerDismissalProvider extends ChangeNotifier {
  bool _dismissedForSession = false;

  bool get isDismissedForSession => _dismissedForSession;

  void dismissForSession() {
    if (_dismissedForSession) return;
    _dismissedForSession = true;
    notifyListeners();
  }
}
