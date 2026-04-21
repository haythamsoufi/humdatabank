/// Lets [BackendReachabilityService] poke UI layer without importing Flutter.
class BackendReachabilityUiCallback {
  BackendReachabilityUiCallback._();

  static void Function()? bump;

  static void bumpUi() {
    final b = bump;
    if (b != null) b();
  }
}
