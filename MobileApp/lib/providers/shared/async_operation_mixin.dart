import 'package:flutter/foundation.dart';

/// Lightweight loading/error state for [ChangeNotifier] providers.
///
/// Use [runAsyncOperation] for a single async body; surface [opLoading]/[opError]
/// via your provider’s public getters (see [LeaderboardProvider]).
mixin AsyncOperationMixin on ChangeNotifier {
  bool opLoading = false;
  String? opError;

  void clearOpError() {
    opError = null;
    notifyListeners();
  }

  Future<void> runAsyncOperation(Future<void> Function() body) async {
    opLoading = true;
    opError = null;
    notifyListeners();
    try {
      await body();
    } catch (e) {
      opError = e.toString();
    } finally {
      opLoading = false;
      notifyListeners();
    }
  }
}
