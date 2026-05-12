/// Arguments for [AppRoutes.aiChat] (and [AiChatScreenWithBottomNav]).
///
/// Supports legacy [int] (bottom tab index only) for existing call sites.
class AiChatLaunchArgs {
  /// Bottom nav highlight while AI chat is open (Home = 2).
  final int bottomNavTabIndex;

  /// Prefills the composer when the chat screen opens.
  final String? initialText;

  /// If true, attempts to send [initialText] after prefs load (policy / auth apply).
  final bool sendImmediately;

  /// When true, clears the active thread before applying [initialText] (e.g. home → chat).
  final bool startNewConversation;

  const AiChatLaunchArgs({
    this.bottomNavTabIndex = 2,
    this.initialText,
    this.sendImmediately = false,
    this.startNewConversation = false,
  });

  /// Parse route [arguments] from [ModalRoute.settings.arguments].
  static AiChatLaunchArgs parse(Object? arguments) {
    if (arguments == null) {
      return const AiChatLaunchArgs();
    }
    if (arguments is AiChatLaunchArgs) {
      return arguments;
    }
    if (arguments is int) {
      return AiChatLaunchArgs(bottomNavTabIndex: arguments);
    }
    return const AiChatLaunchArgs();
  }

  /// Tab index only (for bottom bar); use when pushing with legacy [int].
  static int bottomNavIndexFrom(Object? arguments) =>
      parse(arguments).bottomNavTabIndex;
}
