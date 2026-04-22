import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_html/flutter_html.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../providers/shared/ai_chat_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../models/shared/ai_chat.dart';
import '../../models/shared/ai_chat_launch_args.dart';
import '../../widgets/ai_chat_agent_progress_panel.dart';
import '../../widgets/ai_chat_structured_views.dart';
import '../../services/organization_config_service.dart';
import '../../config/app_config.dart';
import '../../config/routes.dart';
import '../../theme/chat_immersive_palette.dart';
import '../../utils/theme_extensions.dart';
import '../../utils/accessibility_helper.dart';
import '../../utils/ai_chat_message_html_split.dart';
import '../../widgets/chat_response_sources_details_extension.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/ios_button.dart';
import '../../l10n/app_localizations.dart';

/// User-visible copy for AI chat [AiChatMessage] rows with [role] == `error`.
/// Raw transport exceptions are replaced by localized text when [errorType] or heuristics match.
String _userFacingChatErrorText(
  AppLocalizations loc,
  String raw,
  String? errorType,
) {
  switch (errorType) {
    case 'network_error':
      return loc.aiChatErrorNetwork;
    case 'timeout_error':
      return loc.aiChatErrorTimeout;
    case 'server_error':
      return loc.aiChatErrorServer;
    case 'quota_exceeded':
      return raw;
    default:
      break;
  }
  final l = raw.toLowerCase();
  if (l.contains('timeoutexception') ||
      l.contains('read timed out') ||
      l.contains('connection timed out') ||
      l.contains('timed out')) {
    return loc.aiChatErrorTimeout;
  }
  if (l.contains('socketexception') ||
      l.contains('failed host lookup') ||
      l.contains('nodename nor servname') ||
      l.contains('network is unreachable') ||
      l.contains('no address associated with hostname') ||
      (l.contains('clientexception') && (l.contains('socket') || l.contains('lookup'))) ||
      (l.contains('os error:') && l.contains('errno') && l.contains('uri=')) ) {
    return loc.aiChatErrorNetwork;
  }
  if (l.contains('clientexception') && l.contains('uri=')) {
    return loc.aiChatErrorServer;
  }
  return raw;
}

class AiChatScreen extends StatefulWidget {
  const AiChatScreen({super.key});

  @override
  State<AiChatScreen> createState() => _AiChatScreenState();
}

class _AiChatScreenState extends State<AiChatScreen> with AutomaticKeepAliveClientMixin {
  final _controller = TextEditingController();
  final _scrollController = ScrollController();
  final _searchController = TextEditingController();
  final _searchFocusNode = FocusNode();
  final _inputFocusNode = FocusNode();
  String _searchQuery = '';
  int? _editingMessageIndex;
  int? _copiedMessageIndex;
  Timer? _copiedTimer;
  Timer? _scrollDebounce;
  int _lastMessageCount = 0;
  int _lastLastMessageLen = 0;
  String? _lastShownStreamHint;
  bool _routeLaunchApplied = false;
  /// Tracks the user ID for which conversations were last loaded.
  /// null = initial load not yet completed (sentinel to avoid double-loading).
  String? _lastLoadedUserId;

  /// Last UI locale language code applied to [AiChatProvider] (API + alignment with settings).
  String? _appliedLocaleLangCode;

  /// Global density scale for the chat UI (~12% tighter).
  static const double _kUiScale = 0.88;
  /// Main chat column horizontal rhythm (8pt grid–aligned).
  static const double _chatPagePaddingH = 20 * _kUiScale;
  static const double _chatEmptyMaxWidth = 520 * _kUiScale;
  static const double _messageActionTap = 40 * _kUiScale;
  static const double _messageActionIconSize = 20 * _kUiScale;

  bool _chatGptDark(ThemeData t) => t.brightness == Brightness.dark;

  Color _chatSurface(ThemeData t) =>
      _chatGptDark(t) ? ChatImmersivePalette.darkCanvas : t.colorScheme.surface;

  Color _chatBannerSurface(ThemeData t) =>
      _chatGptDark(t) ? ChatImmersivePalette.darkRaised : t.colorScheme.surfaceContainerHigh;

  Color _chatBubble(ThemeData t) =>
      _chatGptDark(t) ? ChatImmersivePalette.darkBubble : t.colorScheme.surfaceContainerHigh;

  Color _chatComposer(ThemeData t) =>
      _chatGptDark(t) ? ChatImmersivePalette.darkComposer : t.colorScheme.surfaceContainerHighest;

  Color _chatBody(ThemeData t) =>
      _chatGptDark(t) ? ChatImmersivePalette.darkText : t.colorScheme.onSurface;

  Color _chatMuted(ThemeData t) =>
      _chatGptDark(t) ? ChatImmersivePalette.darkMuted : t.colorScheme.onSurfaceVariant;

  Color _chatOutline(ThemeData t) =>
      _chatGptDark(t) ? ChatImmersivePalette.darkBorder : t.colorScheme.outline;

  Color _chatSendDisabled(ThemeData t) => _chatGptDark(t)
      ? ChatImmersivePalette.darkStopFill
      : (t.isDarkTheme
          ? t.colorScheme.surfaceContainerHigh
          : t.colorScheme.surfaceContainerHighest);

  Color _chatLink(ThemeData t) =>
      _chatGptDark(t) ? ChatImmersivePalette.darkLink : t.colorScheme.primary;

  Color _chatThumbSelected(ThemeData t) =>
      _chatGptDark(t) ? ChatImmersivePalette.darkText : t.colorScheme.primary;

  Color _chatEditRing(ThemeData t) =>
      _chatGptDark(t) ? ChatImmersivePalette.darkEditRing : t.colorScheme.primary;

  /// Raised panel behind “Sources” blocks (matches web `chat-response-sources` intent).
  Color _chatSourcesPanelBg(ThemeData t) => _chatBannerSurface(t);

  /// Subtle accent for document citation chips (distinct from generic link underline).
  Color _chatSourceDocAccent(ThemeData t) =>
      ChatImmersivePalette.sourceDocAccentForBrightness(t.brightness);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted) return;
      // Stamp the user BEFORE loading so didChangeDependencies skips a
      // redundant reload for the same user that is already in flight here.
      final auth = context.read<AuthProvider>();
      _lastLoadedUserId = auth.user?.id.toString() ?? '';
      await context.read<AiChatProvider>().loadChatUiPrefs();
      if (!mounted) return;
      await _loadConversations();
      if (!mounted) return;
      await _applyRouteLaunchArgsOnce();
    });
  }

  Future<void> _applyRouteLaunchArgsOnce() async {
    if (!mounted || _routeLaunchApplied) return;
    _routeLaunchApplied = true;
    final launch = AiChatLaunchArgs.parse(ModalRoute.of(context)?.settings.arguments);
    if (launch.startNewConversation) {
      await context.read<AiChatProvider>().startNewConversation();
      if (!mounted) return;
    }
    final text = launch.initialText?.trim();
    if (text == null || text.isEmpty) return;
    _controller.text = text;
    if (!launch.sendImmediately) return;

    final auth = context.read<AuthProvider>();
    final isAuthed = auth.isAuthenticated;
    await _send(context, isAuthed);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();

    final lang = Localizations.localeOf(context).languageCode;
    if (_appliedLocaleLangCode != lang) {
      _appliedLocaleLangCode = lang;
      context.read<AiChatProvider>().setPreferredLanguageCode(lang);
    }

    // Detect authenticated-user changes while the screen is cached in the
    // PageView (initState is never called again after the first mount).
    // _lastLoadedUserId is null until initState's post-frame sets it, so the
    // guard below is skipped during that brief window to avoid a double-load.
    final auth = context.watch<AuthProvider>();
    final currentUserId = auth.user?.id.toString() ?? '';
    if (_lastLoadedUserId != null && currentUserId != _lastLoadedUserId) {
      _lastLoadedUserId = currentUserId;
      WidgetsBinding.instance.addPostFrameCallback((_) async {
        if (!mounted) return;
        await _loadConversations();
      });
    }

    // Watch for quota errors and restore failed message
    final ai = context.watch<AiChatProvider>();
    if (ai.errorType == 'quota_exceeded' && ai.failedMessage != null && _controller.text.isEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && _controller.text.isEmpty) {
          _controller.text = ai.failedMessage!;
        }
      });
    }
    final hint = ai.streamStatusHint;
    if (hint != null && hint.isNotEmpty && hint != _lastShownStreamHint) {
      _lastShownStreamHint = hint;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(hint)));
        context.read<AiChatProvider>().clearStreamStatusHint();
        _lastShownStreamHint = null;
      });
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    _scrollController.dispose();
    _searchController.dispose();
    _searchFocusNode.dispose();
    _inputFocusNode.dispose();
    _copiedTimer?.cancel();
    _scrollDebounce?.cancel();
    super.dispose();
  }

  Future<void> _loadConversations() async {
    final auth = context.read<AuthProvider>();
    final isAuthed = auth.isAuthenticated;
    // Don't block UI on token fetch (it can timeout/retry); conversations can still load via cookie auth / local DB.
    unawaited(context.read<AiChatProvider>().ensureTokenIfLoggedIn(isAuthenticated: isAuthed));
    await context.read<AiChatProvider>().loadConversations(
      isAuthenticated: isAuthed,
      sessionUserId: isAuthed ? auth.user?.id.toString() : null,
    );
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) return;
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 250),
        curve: Curves.easeOut,
      );
    });
  }

  void _maybeScrollToBottom(AiChatProvider ai) {
    final count = ai.messages.length;
    final lastLen = ai.messages.isNotEmpty ? ai.messages.last.content.length : 0;

    final changed = (count != _lastMessageCount) || (lastLen != _lastLastMessageLen);
    _lastMessageCount = count;
    _lastLastMessageLen = lastLen;
    if (!changed) return;

    // Debounce to avoid animating on every single streaming character.
    _scrollDebounce?.cancel();
    _scrollDebounce = Timer(const Duration(milliseconds: 80), () {
      if (!mounted) return;
      _scrollToBottom();
    });
  }

  String _welcomeAssistantName(BuildContext context) {
    try {
      if (OrganizationConfigService().isInitialized) {
        return OrganizationConfigService().config.app.name;
      }
    } catch (_) {}
    return AppLocalizations.of(context)!.aiDefaultAssistantTitle;
  }

  void _showPolicyRequiredSnack(BuildContext context) {
    final loc = AppLocalizations.of(context)!;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(loc.aiPolicyAcknowledgeSnackbar)),
    );
  }

  /// Returns true if the user was redirected (caller should stop).
  bool _redirectToLoginIfGuest(BuildContext context, bool isAuthenticated) {
    if (isAuthenticated) return false;
    Navigator.of(context).pushNamed(AppRoutes.login);
    return true;
  }

  String _scoreChipLabel(String localizedName, double v) {
    final pct = v > 1.0001 ? v : (v * 100);
    return '$localizedName ${pct.toStringAsFixed(0)}%';
  }

  void _showAiPolicyModal(BuildContext context) {
    final sheetTheme = Theme.of(context);
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: _chatSurface(sheetTheme),
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.zero),
      builder: (ctx) {
        final t = Theme.of(ctx);
        final loc = AppLocalizations.of(ctx)!;
        return DraggableScrollableSheet(
          expand: false,
          initialChildSize: 0.85,
          minChildSize: 0.45,
          maxChildSize: 0.95,
          builder: (_, scrollController) {
            return Padding(
              padding: EdgeInsets.only(
                left: 20,
                right: 20,
                top: 16,
                bottom: MediaQuery.paddingOf(ctx).bottom + 16,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    loc.aiUsePolicyTitle,
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                      color: _chatBody(t),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Expanded(
                    child: ListView(
                      controller: scrollController,
                      children: [
                        Text(
                          loc.aiPolicyDoNotShare,
                          style: TextStyle(
                            fontWeight: FontWeight.w600,
                            fontSize: 15,
                            color: _chatBody(t),
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          loc.aiPolicyTracesBody,
                          style: TextStyle(
                            fontSize: 14,
                            height: 1.4,
                            color: _chatMuted(t),
                          ),
                        ),
                        const SizedBox(height: 20),
                        _policySection(
                          ctx,
                          loc.aiPolicyPurposeTitle,
                          loc.aiPolicyPurposeBody,
                        ),
                        _policySection(
                          ctx,
                          loc.aiPolicyAcceptableUseTitle,
                          loc.aiPolicyAcceptableUseBody,
                        ),
                        _policySection(
                          ctx,
                          loc.aiPolicyAccuracyTitle,
                          loc.aiPolicyAccuracyBody,
                        ),
                      ],
                    ),
                  ),
                  Divider(
                    height: 1,
                    thickness: 1,
                    color: _chatOutline(t).withValues(alpha: 0.45),
                  ),
                  const SizedBox(height: 14),
                  Text(
                    loc.aiPolicyConfirmFooter,
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      fontSize: 13,
                      height: 1.35,
                      color: _chatMuted(t),
                    ),
                  ),
                  const SizedBox(height: 14),
                  _policyAcknowledgeButton(
                    theme: t,
                    label: loc.aiPolicyIUnderstand,
                    semanticsLabel: loc.aiPolicyAcknowledgeCta,
                    onPressed: () async {
                      Navigator.pop(ctx);
                      await context.read<AiChatProvider>().acknowledgeAiPolicy();
                    },
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }

  /// Primary CTA for accepting the AI use policy (aligned with send / retry accent).
  Widget _policyAcknowledgeButton({
    required ThemeData theme,
    required VoidCallback? onPressed,
    required String label,
    required String semanticsLabel,
  }) {
    final onGreen = AccessibilityHelper.getAccessibleTextColor(ChatImmersivePalette.sendGreen);
    return Semantics(
      button: true,
      label: semanticsLabel,
      child: SizedBox(
        width: double.infinity,
        child: FilledButton(
          style: FilledButton.styleFrom(
            backgroundColor: ChatImmersivePalette.sendGreen,
            foregroundColor: onGreen,
            padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 20),
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(12),
            ),
            elevation: 0,
          ),
          onPressed: onPressed,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.center,
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.check_circle_outline_rounded, size: 22, color: onGreen),
              const SizedBox(width: 10),
              Text(
                label,
                style: const TextStyle(
                  fontWeight: FontWeight.w600,
                  fontSize: 16,
                  letterSpacing: 0.15,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _policySection(BuildContext context, String title, String body) {
    final t = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w600,
              color: _chatBody(t),
            ),
          ),
          const SizedBox(height: 6),
          Text(
            body,
            style: TextStyle(
              fontSize: 14,
              height: 1.4,
              color: _chatMuted(t),
            ),
          ),
        ],
      ),
    );
  }

  /// Checkboxes in the sources sheet: avoid theme primary (navy) on near-black chat surfaces.
  CheckboxThemeData _sourcesSheetCheckboxTheme(ThemeData t) {
    return CheckboxThemeData(
      materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
      visualDensity: VisualDensity.compact,
      splashRadius: 18,
      fillColor: WidgetStateProperty.resolveWith((states) {
        if (states.contains(WidgetState.disabled)) {
          return _chatMuted(t).withValues(alpha: 0.35);
        }
        if (states.contains(WidgetState.selected)) {
          return ChatImmersivePalette.sendGreen;
        }
        return _chatBubble(t);
      }),
      checkColor: const WidgetStatePropertyAll<Color>(Colors.white),
      overlayColor: WidgetStatePropertyAll<Color>(_chatLink(t).withValues(alpha: 0.12)),
      side: BorderSide(color: _chatOutline(t), width: 1.5),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(4)),
    );
  }

  Widget _buildSourceSheetRow(
    ThemeData t, {
    required String label,
    required bool value,
    required ValueChanged<bool?> onChanged,
  }) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: () => onChanged(!value),
        borderRadius: BorderRadius.circular(8),
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 4),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Expanded(
                child: Text(
                  label,
                  style: TextStyle(
                    color: _chatBody(t),
                    fontSize: 15,
                    height: 1.25,
                    fontWeight: FontWeight.w400,
                  ),
                ),
              ),
              Checkbox(
                value: value,
                onChanged: onChanged,
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _showSourcesSheet(BuildContext context, AiChatProvider ai) {
    bool historical = ai.selectedSources.contains('historical');
    bool system = ai.selectedSources.contains('system_documents');
    bool upr = ai.selectedSources.contains('upr_documents');

    final sheetTheme = Theme.of(context);
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: _chatSurface(sheetTheme),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      builder: (ctx) {
        final t = Theme.of(ctx);
        final loc = AppLocalizations.of(ctx)!;
        return StatefulBuilder(
          builder: (ctx, setModal) {
            Future<void> toggle(String key, bool value) async {
              await ai.setAiSourceEnabled(key, value);
              setModal(() {
                historical = ai.selectedSources.contains('historical');
                system = ai.selectedSources.contains('system_documents');
                upr = ai.selectedSources.contains('upr_documents');
              });
            }

            return Theme(
              data: t.copyWith(
                checkboxTheme: _sourcesSheetCheckboxTheme(t),
              ),
              child: SafeArea(
                child: Padding(
                  padding: const EdgeInsets.fromLTRB(20, 12, 20, 20),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Center(
                        child: Container(
                          width: 36,
                          height: 4,
                          margin: const EdgeInsets.only(bottom: 12),
                          decoration: BoxDecoration(
                            color: _chatOutline(t),
                            borderRadius: BorderRadius.circular(2),
                          ),
                        ),
                      ),
                      Text(
                        loc.aiSourcesHeading,
                        style: TextStyle(
                          fontWeight: FontWeight.w600,
                          fontSize: 16,
                          letterSpacing: -0.2,
                          color: _chatBody(t),
                        ),
                      ),
                      const SizedBox(height: 4),
                      _buildSourceSheetRow(
                        t,
                        label: loc.aiSourceDatabank,
                        value: historical,
                        onChanged: (v) {
                          if (v != null) toggle('historical', v);
                        },
                      ),
                      _buildSourceSheetRow(
                        t,
                        label: loc.aiSourceSystemDocuments,
                        value: system,
                        onChanged: (v) {
                          if (v != null) toggle('system_documents', v);
                        },
                      ),
                      _buildSourceSheetRow(
                        t,
                        label: loc.aiSourceUprDocuments,
                        value: upr,
                        onChanged: (v) {
                          if (v != null) toggle('upr_documents', v);
                        },
                      ),
                      const SizedBox(height: 10),
                      Text(
                        loc.aiSourcesMinimumNote,
                        style: TextStyle(
                          fontSize: 12,
                          height: 1.35,
                          color: _chatMuted(t),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            );
          },
        );
      },
    );
  }

  /// Map web routes to mobile app routes.
  /// Handles differences between Backoffice web paths and mobile app paths.
  String _mapWebRouteToMobile(String route) {
    // Map root path to dashboard (web uses '/' for dashboard, mobile uses '/dashboard')
    if (route == '/') {
      return AppRoutes.dashboard;
    }

    // Map admin user routes to admin section (handled via WebView)
    if (route.startsWith('/admin/users')) {
      return AppRoutes.users;
    }

    // Map forms/assignment routes (these have dynamic IDs in the path)
    // e.g., /forms/assignment/123 stays the same
    if (route.startsWith('/forms/assignment/')) {
      return route;
    }

    // Generic /forms/assignment without ID should go to assignments list
    if (route == '/forms/assignment') {
      return AppRoutes.assignments;
    }

    return route;
  }

  /// Process HTML content from chatbot to be more mobile-friendly.
  /// Transforms tour trigger elements and marks document source links for chip-style display.
  String _processHtmlForMobile(String html) {
    // Replace tour trigger text to indicate mobile-appropriate behavior
    // The web version says "Start Interactive Tour" but mobile just navigates
    String processed = html.replaceAllMapped(
      RegExp(r"""<i class=['"]fas fa-compass['"]></i>\s*Start Interactive Tour"""),
      (match) => '📍 View This Page',
    );

    // Also handle the surrounding message about tour guidance
    processed = processed.replaceAll(
      'Would you like me to guide you through this?',
      'Would you like to go to the relevant page?',
    );

    // Mark document source links so we can style them like ChatGPT source chips
    // Backend emits [Document title — page N](/api/ai/documents/123/download); we add a class
    processed = processed.replaceAllMapped(
      RegExp("<a\\s+([^>]*href=[\"'][^\"']*?/api/ai/documents/[^\"']*[\"'][^>]*)>", caseSensitive: false),
      (match) => '<a class="source-doc-link" ${match.group(1)}>',
    );

    return processed;
  }

  /// Shared HTML + styles for assistant narrative and for [trailing sources] after charts.
  Widget _buildAssistantMessageHtml(BuildContext context, ThemeData theme, String processedData) {
    return Html(
      data: processedData,
      extensions: const [
        ChatResponseSourcesDetailsExtension(),
      ],
      style: {
        'body': Style(
          margin: Margins.zero,
          padding: HtmlPaddings.zero,
          color: _chatBody(theme),
          fontSize: FontSize(16),
          lineHeight: const LineHeight(1.45),
        ),
        'a': Style(
          color: _chatLink(theme),
          textDecoration: TextDecoration.underline,
          fontWeight: FontWeight.w500,
        ),
        'div.chat-response-sources': Style(
          display: Display.block,
          margin: Margins.only(top: 12, bottom: 4),
          padding: HtmlPaddings.all(12),
          backgroundColor: _chatSourcesPanelBg(theme),
          border: Border.all(color: _chatOutline(theme)),
        ),
        'details.chat-response-sources summary': Style(
          display: Display.block,
          fontSize: FontSize(13.5),
          fontWeight: FontWeight.w600,
          letterSpacing: 0.2,
          color: _chatMuted(theme),
        ),
        '.chat-response-sources-body': Style(
          display: Display.block,
          color: _chatMuted(theme),
          fontSize: FontSize(13.5),
          lineHeight: const LineHeight(1.45),
          fontWeight: FontWeight.w400,
        ),
        'details.chat-response-sources .chat-response-sources-body': Style(
          margin: Margins.only(top: 4),
          padding: HtmlPaddings.all(10),
          backgroundColor: _chatSourcesPanelBg(theme),
          border: Border(
            top: BorderSide(color: _chatOutline(theme)),
          ),
        ),
        '.chat-response-sources-body a': Style(
          color: _chatLink(theme),
          textDecoration: TextDecoration.underline,
          fontWeight: FontWeight.w500,
          fontSize: FontSize(13.5),
        ),
        '.chat-response-sources-body strong': Style(
          fontWeight: FontWeight.w500,
          color: _chatBody(theme),
        ),
        '.chat-response-sources-body b': Style(
          fontWeight: FontWeight.w500,
          color: _chatBody(theme),
        ),
        '.chat-response-sources-body ul': Style(
          margin: Margins.only(top: 6, bottom: 0),
          padding: HtmlPaddings.only(left: 18, top: 0, right: 0, bottom: 0),
        ),
        '.chat-response-sources-body ol': Style(
          margin: Margins.only(top: 6, bottom: 0),
          padding: HtmlPaddings.only(left: 20, top: 0, right: 0, bottom: 0),
        ),
        '.chat-response-sources-body li': Style(
          margin: Margins.only(bottom: 6),
          color: _chatMuted(theme),
          fontSize: FontSize(13.5),
          lineHeight: const LineHeight(1.45),
        ),
        '.chatbot-tour-trigger': Style(
          display: Display.inlineBlock,
          padding: HtmlPaddings.symmetric(horizontal: 12, vertical: 8),
          margin: Margins.only(top: 8),
          backgroundColor: _chatBubble(theme),
          border: Border.all(
            color: _chatOutline(theme),
          ),
        ),
        '.source-doc-link': Style(
          display: Display.inlineBlock,
          padding: HtmlPaddings.symmetric(horizontal: 10, vertical: 6),
          margin: Margins.only(top: 6, right: 6),
          backgroundColor: _chatBubble(theme),
          border: Border(
            left: BorderSide(
              color: _chatSourceDocAccent(theme),
              width: 3,
            ),
            top: BorderSide(color: _chatOutline(theme)),
            right: BorderSide(color: _chatOutline(theme)),
            bottom: BorderSide(color: _chatOutline(theme)),
          ),
          color: _chatBody(theme),
          textDecoration: TextDecoration.none,
          fontSize: FontSize(12.5),
          fontWeight: FontWeight.w500,
          letterSpacing: -0.15,
        ),
      },
      onLinkTap: (url, attributes, element) {
        _handleLinkTap(context, url);
      },
    );
  }

  /// True if [url] is a document download/source link from the AI (backend path).
  bool _isDocumentSourceUrl(String url) {
    final path = url.split('?').first.split('#').first.trim();
    return path.startsWith('/api/ai/documents/') && path.contains('/download');
  }

  bool _isAllowedInternalRoute(String route) {
    // Basic hardening: avoid path traversal-ish inputs.
    if (route.contains('..') || route.contains(r'\')) return false;
    if (!route.startsWith('/')) return false;

    final allowedPrefixes = <String>[
      AppRoutes.indicatorBank,
      AppRoutes.countries,
      AppRoutes.resources,
      AppRoutes.admin,
      '/forms', // dynamic routes under /forms/...
      '/ai', // AI routes
      AppRoutes.dashboard,
      AppRoutes.settings,
      AppRoutes.notifications,
    ];

    for (final p in allowedPrefixes) {
      if (route == p || route.startsWith('$p/')) return true;
    }
    return false;
  }

  Future<void> _handleLinkTap(BuildContext context, String? url) async {
    if (url == null || url.trim().isEmpty) return;
    final trimmed = url.trim();

    // Internal route (app screens)
    if (trimmed.startsWith('/') && !trimmed.startsWith('//')) {
      final path = trimmed.split('?').first.split('#').first;

      // Document source links: open full backend URL so user can view/download (ChatGPT-style sources)
      if (_isDocumentSourceUrl(path)) {
        final fullUrl = '${AppConfig.baseApiUrl}$path';
        final uri = Uri.tryParse(fullUrl);
        if (uri != null && await canLaunchUrl(uri)) {
          await launchUrl(uri, mode: LaunchMode.externalApplication);
        }
        return;
      }

      // Map web paths to mobile app routes
      final route = _mapWebRouteToMobile(path);
      final isTourTrigger = trimmed.contains('#chatbot-tour=');

      if (_isAllowedInternalRoute(route)) {
        if (isTourTrigger && context.mounted) {
          final loc = AppLocalizations.of(context)!;
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(loc.aiTourWebOnlySnackbar),
              duration: const Duration(seconds: 2),
            ),
          );
        }
        Navigator.of(context).pushNamed(route);
      }
      return;
    }

    // External link: only allow http/https
    final uri = Uri.tryParse(trimmed);
    if (uri == null) return;
    final scheme = uri.scheme.toLowerCase();
    if (scheme != 'http' && scheme != 'https') return;

    if (await canLaunchUrl(uri)) {
      await launchUrl(uri, mode: LaunchMode.platformDefault);
    }
  }

  @override
  bool get wantKeepAlive => true;

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final auth = context.watch<AuthProvider>();
    final ai = context.watch<AiChatProvider>();
    final isAuthed = auth.isAuthenticated;
    final theme = Theme.of(context);
    // When prefs are loaded and policy not accepted, block messaging (same gate as [_send]).
    final policyBlocksInput = ai.prefsLoaded && !ai.policyAcknowledged;

    _maybeScrollToBottom(ai);

    final localizations = AppLocalizations.of(context)!;
    // AppBar title: current conversation title or "New chat" (aligned with chat_immersive main title)
    final match = ai.conversations.where((c) => c.id == ai.conversationId);
    final appBarTitle = match.isEmpty
        ? localizations.aiNewChat
        : (match.first.title ?? localizations.aiNewChat);
    final quickPrompts = <String>[
      localizations.aiQuickPrompt1,
      localizations.aiQuickPrompt2,
      localizations.aiQuickPrompt3,
      localizations.aiQuickPrompt4,
      localizations.aiQuickPrompt5,
    ];

    // Capture the outer body height BEFORE the inner Scaffold/AppBar consumes any
    // vertical space. This lets the composer compute exactly how much of the
    // keyboard overlaps the inner body — without needing to know kToolbarHeight or
    // whether an ancestor primary Scaffold already consumed the status-bar inset.
    return LayoutBuilder(
      builder: (_, outerConstraints) {
        final outerBodyH = outerConstraints.maxHeight;
    return MediaQuery(
      data: MediaQuery.of(context).copyWith(
        textScaler: TextScaler.linear(MediaQuery.textScalerOf(context).scale(1) * _kUiScale),
      ),
      child: Scaffold(
      resizeToAvoidBottomInset: false,
      backgroundColor: _chatSurface(theme),
      onDrawerChanged: (isOpened) {
        if (isOpened != true) return;
        // Keep keyboard hidden until the user taps the drawer search field.
        _inputFocusNode.unfocus();
        _searchFocusNode.unfocus();
        FocusManager.instance.primaryFocus?.unfocus();
        SystemChannels.textInput.invokeMethod('TextInput.hide');
      },
      appBar: AppBar(
        backgroundColor: _chatSurface(theme),
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: false,
        automaticallyImplyLeading: false,
        leading: Builder(
          builder: (scaffoldContext) {
            return IOSIconButton(
              icon: Icons.menu,
              color: _chatBody(theme),
              onPressed: () {
                FocusScope.of(scaffoldContext).unfocus();
                _inputFocusNode.unfocus();
                Scaffold.of(scaffoldContext).openDrawer();
              },
              tooltip: localizations.navigation,
              semanticLabel: localizations.navigation,
              semanticHint: localizations.aiSemanticOpenDrawerHint,
            );
          },
        ),
        title: Text(
          appBarTitle,
          style: TextStyle(
            fontSize: 17,
            fontWeight: FontWeight.w600,
            letterSpacing: -0.3,
            color: _chatBody(theme),
          ),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
        ),
        iconTheme: IconThemeData(
          color: _chatBody(theme),
        ),
        actions: [
          Padding(
            padding: const EdgeInsetsDirectional.only(end: 14),
            child: IOSIconButton(
              icon: Icons.add_comment_outlined,
              color: _chatBody(theme),
              onPressed: () async {
                await context.read<AiChatProvider>().startNewConversation();
              },
              tooltip: localizations.aiTooltipNewChat,
              semanticLabel: localizations.aiSemanticNewChatLabel,
              semanticHint: localizations.aiSemanticNewChatHint,
            ),
          ),
        ],
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(1),
          child: Divider(
            height: 1,
            thickness: 1,
            color: _chatOutline(theme),
          ),
        ),
      ),
      drawer: _buildDrawer(context, auth, ai, isAuthed),
      body: SafeArea(
        bottom: false,
        child: LayoutBuilder(
          builder: (context, constraints) {
            // Prefer inline progress (last row) over the top banner so the panel stays
            // under the user message, same as while streaming.
            final hasInlineProgressSlot = ai.messages.isNotEmpty &&
                ai.messages.last.role == 'assistant' &&
                ai.messages.last.content.isEmpty &&
                (ai.isStreaming || ai.inflightRestoreActive);
            final showInflightBar = ai.inflightRestoreActive &&
                ai.agentSteps.isNotEmpty &&
                !hasInlineProgressSlot;

            return Column(
              children: [
                if (auth.user?.aiBetaTester == true)
                  Material(
                    color: _chatBannerSurface(theme),
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(
                        _chatPagePaddingH,
                        10,
                        _chatPagePaddingH,
                        10,
                      ),
                      child: Row(
                        children: [
                          Icon(Icons.science_outlined, size: 18, color: _chatMuted(theme)),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              localizations.aiBetaTesterBanner,
                              style: TextStyle(
                                fontSize: 12,
                                height: 1.25,
                                color: _chatBody(theme),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                if (showInflightBar)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(_chatPagePaddingH, 8, _chatPagePaddingH, 0),
                    child: AiChatAgentProgressPanel(steps: ai.agentSteps),
                  ),
                Flexible(
                  child: GestureDetector(
                    onTap: () {
                      // Dismiss keyboard when tapping on the chat area
                      FocusScope.of(context).unfocus();
                    },
                    behavior: HitTestBehavior.opaque,
                    child: ai.messages.isEmpty
                        ? Center(
                            child: ConstrainedBox(
                              constraints: const BoxConstraints(maxWidth: _chatEmptyMaxWidth),
                              child: SingleChildScrollView(
                                child: Padding(
                                  padding: const EdgeInsets.fromLTRB(
                                    _chatPagePaddingH,
                                    32,
                                    _chatPagePaddingH,
                                    32,
                                  ),
                                  child: Column(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    crossAxisAlignment: CrossAxisAlignment.stretch,
                                    children: [
                                      Icon(
                                        Icons.auto_awesome_outlined,
                                        size: 48,
                                        color: _chatMuted(theme),
                                      ),
                                      const SizedBox(height: 20),
                                      Text(
                                        _welcomeAssistantName(context),
                                        style: TextStyle(
                                          fontSize: 28,
                                          fontWeight: FontWeight.w600,
                                          letterSpacing: -0.5,
                                          height: 1.2,
                                          color: _chatBody(theme),
                                        ),
                                        textAlign: TextAlign.center,
                                      ),
                                      const SizedBox(height: 10),
                                      Text(
                                        localizations.aiEmptyWelcome,
                                        style: TextStyle(
                                          fontSize: 17,
                                          fontWeight: FontWeight.w400,
                                          letterSpacing: -0.2,
                                          color: _chatMuted(theme),
                                        ),
                                        textAlign: TextAlign.center,
                                      ),
                                      if (ai.prefsLoaded && !ai.policyAcknowledged) ...[
                                        const SizedBox(height: 20),
                                        Container(
                                          padding: const EdgeInsets.fromLTRB(16, 16, 16, 14),
                                          decoration: BoxDecoration(
                                            color: _chatComposer(theme),
                                            borderRadius: BorderRadius.circular(16),
                                            border: Border.all(
                                              color: _chatOutline(theme),
                                            ),
                                          ),
                                          child: Column(
                                            crossAxisAlignment: CrossAxisAlignment.stretch,
                                            children: [
                                              Row(
                                                crossAxisAlignment: CrossAxisAlignment.start,
                                                children: [
                                                  DecoratedBox(
                                                    decoration: BoxDecoration(
                                                      color: _chatBannerSurface(theme),
                                                      borderRadius: BorderRadius.circular(12),
                                                      border: Border.all(
                                                        color: _chatOutline(theme).withValues(alpha: 0.6),
                                                      ),
                                                    ),
                                                    child: Padding(
                                                      padding: const EdgeInsets.all(10),
                                                      child: Icon(
                                                        Icons.shield_outlined,
                                                        size: 22,
                                                        color: _chatLink(theme),
                                                      ),
                                                    ),
                                                  ),
                                                  const SizedBox(width: 12),
                                                  Expanded(
                                                    child: Column(
                                                      crossAxisAlignment: CrossAxisAlignment.start,
                                                      children: [
                                                        Text(
                                                          localizations.aiPolicyChipTitle,
                                                          style: TextStyle(
                                                            fontSize: 16,
                                                            fontWeight: FontWeight.w700,
                                                            height: 1.2,
                                                            color: _chatBody(theme),
                                                          ),
                                                        ),
                                                        const SizedBox(height: 4),
                                                        Text(
                                                          localizations.aiPolicySheetSummaryLine,
                                                          style: TextStyle(
                                                            fontSize: 12,
                                                            height: 1.3,
                                                            color: _chatMuted(theme),
                                                          ),
                                                        ),
                                                      ],
                                                    ),
                                                  ),
                                                ],
                                              ),
                                              const SizedBox(height: 14),
                                              Text(
                                                localizations.aiPolicyCompactWarning,
                                                style: TextStyle(
                                                  fontSize: 13,
                                                  height: 1.4,
                                                  color: _chatBody(theme),
                                                ),
                                              ),
                                              const SizedBox(height: 12),
                                              TextButton.icon(
                                                style: TextButton.styleFrom(
                                                  foregroundColor: _chatLink(theme),
                                                  alignment: Alignment.centerLeft,
                                                  padding: const EdgeInsets.symmetric(vertical: 4),
                                                ),
                                                onPressed: () => _showAiPolicyModal(context),
                                                icon: Icon(
                                                  Icons.article_outlined,
                                                  size: 18,
                                                  color: _chatLink(theme),
                                                ),
                                                label: Text(localizations.aiReadFullPolicy),
                                              ),
                                              const SizedBox(height: 4),
                                              _policyAcknowledgeButton(
                                                theme: theme,
                                                label: localizations.aiPolicyIUnderstand,
                                                semanticsLabel:
                                                    localizations.aiPolicyAcknowledgeCta,
                                                onPressed: () async {
                                                  await context
                                                      .read<AiChatProvider>()
                                                      .acknowledgeAiPolicy();
                                                },
                                              ),
                                            ],
                                          ),
                                        ),
                                        const SizedBox(height: 24),
                                      ] else
                                        const SizedBox(height: 8),
                                      if (!policyBlocksInput) ...[
                                        Text(
                                          localizations.aiTryAsking,
                                          style: TextStyle(
                                            fontSize: 13,
                                            fontWeight: FontWeight.w500,
                                            color: _chatMuted(theme),
                                          ),
                                          textAlign: TextAlign.center,
                                        ),
                                        const SizedBox(height: 14),
                                        Wrap(
                                          spacing: 8,
                                          runSpacing: 8,
                                          alignment: WrapAlignment.center,
                                          children: quickPrompts.map((prompt) {
                                            return _buildPromptChip(
                                              theme: theme,
                                              prompt: prompt,
                                              onTap: () {
                                                _controller.text = prompt;
                                                _send(context, isAuthed);
                                              },
                                            );
                                          }).toList(),
                                        ),
                                      ],
                                    ],
                                  ),
                                ),
                              ),
                            ),
                          )
                        : ListView.builder(
                            controller: _scrollController,
                            padding: const EdgeInsets.fromLTRB(
                              _chatPagePaddingH,
                              12,
                              _chatPagePaddingH,
                              20,
                            ),
                            itemCount: ai.messages.length,
                            itemBuilder: (context, i) {
                              final m = ai.messages[i];

                              // Handle error messages
                              if (m.role == 'error') {
                                return _buildErrorMessageBubble(
                                  context,
                                  m.content,
                                  m.errorType,
                                  m.retryDelay,
                                  isAuthed,
                                );
                              }

                              final isUser = m.role == 'user';
                              final isLastAssistant = !isUser &&
                                  i == ai.messages.length - 1 &&
                                  m.content.isEmpty &&
                                  (ai.isStreaming || ai.inflightRestoreActive);

                              // Defer only when structured cards render; otherwise keep Sources in the same bubble.
                              final hasStructuredVisuals = m.structuredPayloads.isNotEmpty;
                              final assistantBodySplit = (!isUser && !isLastAssistant && hasStructuredVisuals)
                                  ? splitAssistantHtmlForVisualsAfterBody(m.content)
                                  : null;

                              final isEditing = _editingMessageIndex == i;
                              final assistantMaxWidth =
                                  MediaQuery.of(context).size.width - (_chatPagePaddingH * 2);
                              final userMaxWidth = MediaQuery.of(context).size.width * 0.78;

                              // Assistant rows use CrossAxisAlignment.start on the list item, so
                              // the message Column would size to the Html intrinsic width and charts
                              // could collapse to ~0 width (one character per line). Use a fixed
                              // width for assistant so structured charts/maps get full line width.
                              return Align(
                                alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
                                child: ConstrainedBox(
                                  constraints: BoxConstraints(
                                    maxWidth: isUser ? userMaxWidth : assistantMaxWidth,
                                  ),
                                  child: SizedBox(
                                    width: isUser ? null : assistantMaxWidth,
                                    child: Column(
                                    mainAxisSize: MainAxisSize.min,
                                    crossAxisAlignment: isUser ? CrossAxisAlignment.end : CrossAxisAlignment.stretch,
                                    children: [
                                      // Message bubble (ChatGPT-style: soft pill for user, flat for assistant)
                                      Container(
                                        margin: EdgeInsets.symmetric(vertical: isUser ? 6 : 10),
                                        padding: EdgeInsets.symmetric(
                                          horizontal: isUser ? 16 : 8,
                                          vertical: isUser ? 10 : 6,
                                        ),
                                        decoration: isUser
                                            ? BoxDecoration(
                                                color: _chatBubble(theme),
                                                borderRadius: BorderRadius.circular(22),
                                                border: isEditing
                                                    ? Border.all(
                                                        color: _chatEditRing(theme),
                                                        width: 2,
                                                      )
                                                    : null,
                                              )
                                            : BoxDecoration(
                                                color: Colors.transparent,
                                                border: isEditing
                                                    ? Border.all(
                                                        color: _chatEditRing(theme),
                                                        width: 2,
                                                      )
                                                    : null,
                                                borderRadius: isEditing ? BorderRadius.circular(12) : null,
                                              ),
                                        child: isUser
                                            ? Text(
                                                m.content,
                                                style: TextStyle(
                                                  color: _chatBody(theme),
                                                  fontSize: 16,
                                                  height: 1.35,
                                                  letterSpacing: -0.2,
                                                ),
                                                softWrap: true,
                                                overflow: TextOverflow.visible,
                                              )
                                            : isLastAssistant
                                                ? (ai.agentSteps.isNotEmpty
                                                    ? AiChatAgentProgressPanel(
                                                        steps: ai.agentSteps,
                                                      )
                                                    : const _TypingIndicator())
                                                : _buildAssistantMessageHtml(
                                                    context,
                                                    theme,
                                                    _processHtmlForMobile(assistantBodySplit?.mainHtml ?? m.content),
                                                  ),
                                      ),
                                      // Show structured payloads (maps/charts) even while the assistant row
                                      // is still in "typing/steps" state if the server sent them early.
                                      if (!isUser &&
                                          (!isLastAssistant || m.structuredPayloads.isNotEmpty) &&
                                          ((m.confidence != null) ||
                                              (m.groundingScore != null) ||
                                              m.structuredPayloads.isNotEmpty))
                                        Padding(
                                          padding: const EdgeInsets.only(top: 4),
                                          child: Column(
                                            crossAxisAlignment: CrossAxisAlignment.start,
                                            children: [
                                              if ((m.confidence != null) || (m.groundingScore != null))
                                                Padding(
                                                  padding: const EdgeInsets.only(bottom: 6),
                                                  child: Wrap(
                                                    spacing: 6,
                                                    runSpacing: 4,
                                                    children: [
                                                      if (m.confidence != null)
                                                        Chip(
                                                          label: Text(
                                                            _scoreChipLabel(localizations.aiScoreConfidence, m.confidence!),
                                                            style: TextStyle(
                                                              fontSize: 11,
                                                              height: 1.2,
                                                              color: _chatBody(theme),
                                                            ),
                                                          ),
                                                          backgroundColor: _chatBubble(theme),
                                                          side: BorderSide(color: _chatOutline(theme)),
                                                          shape: RoundedRectangleBorder(
                                                            borderRadius: BorderRadius.circular(8),
                                                          ),
                                                          padding: const EdgeInsets.symmetric(horizontal: 4),
                                                          labelPadding: const EdgeInsets.symmetric(horizontal: 4),
                                                          visualDensity: VisualDensity.compact,
                                                          materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                                                        ),
                                                      if (m.groundingScore != null)
                                                        Chip(
                                                          label: Text(
                                                            _scoreChipLabel(localizations.aiScoreGrounding, m.groundingScore!),
                                                            style: TextStyle(
                                                              fontSize: 11,
                                                              height: 1.2,
                                                              color: _chatBody(theme),
                                                            ),
                                                          ),
                                                          backgroundColor: _chatBubble(theme),
                                                          side: BorderSide(color: _chatOutline(theme)),
                                                          shape: RoundedRectangleBorder(
                                                            borderRadius: BorderRadius.circular(8),
                                                          ),
                                                          padding: const EdgeInsets.symmetric(horizontal: 4),
                                                          labelPadding: const EdgeInsets.symmetric(horizontal: 4),
                                                          visualDensity: VisualDensity.compact,
                                                          materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                                                        ),
                                                    ],
                                                  ),
                                                ),
                                              AiChatStructuredPayloadsColumn(
                                                payloads: m.structuredPayloads,
                                              ),
                                            ],
                                          ),
                                        ),
                                      if (!isUser &&
                                          !isLastAssistant &&
                                          assistantBodySplit != null &&
                                          (assistantBodySplit.trailingSourcesHtml != null) &&
                                          assistantBodySplit.trailingSourcesHtml!.trim().isNotEmpty)
                                        Padding(
                                          padding: const EdgeInsets.only(top: 8),
                                          child: _buildAssistantMessageHtml(
                                            context,
                                            theme,
                                            _processHtmlForMobile(assistantBodySplit.trailingSourcesHtml!),
                                          ),
                                        ),
                                      // Icons (below the bubble)
                                      if (!isLastAssistant)
                                        Padding(
                                          padding: const EdgeInsets.only(top: 4),
                                          child: Row(
                                            mainAxisSize: MainAxisSize.min,
                                            children: [
                                              if (isUser) ...[
                                                _buildActionIcon(
                                                  icon: Icons.copy,
                                                  color: _chatMuted(theme),
                                                  onTap: () => _copyToClipboard(context, m.content, i),
                                                  tooltip: localizations.aiTooltipCopy,
                                                ),
                                                if (_copiedMessageIndex == i)
                                                  Padding(
                                                    padding: const EdgeInsets.only(left: 4),
                                                    child: AnimatedOpacity(
                                                      opacity: 1.0,
                                                      duration: const Duration(milliseconds: 300),
                                                      child: Text(
                                                        localizations.aiCopied,
                                                        style: TextStyle(
                                                          fontSize: 12,
                                                          color: _chatMuted(theme),
                                                        ),
                                                      ),
                                                    ),
                                                  ),
                                                const SizedBox(width: 4),
                                                _buildActionIcon(
                                                  icon: Icons.edit,
                                                  color: _chatMuted(theme),
                                                  onTap: () => _showEditMessageDialog(context, i, m.content),
                                                  tooltip: localizations.aiTooltipEditMessage,
                                                ),
                                              ] else ...[
                                                _buildActionIcon(
                                                  icon: Icons.copy,
                                                  color: _chatMuted(theme),
                                                  onTap: () => _copyToClipboard(context, m.content, i),
                                                  tooltip: localizations.aiTooltipCopy,
                                                ),
                                                if (_copiedMessageIndex == i)
                                                  Padding(
                                                    padding: const EdgeInsets.only(left: 4),
                                                    child: AnimatedOpacity(
                                                      opacity: 1.0,
                                                      duration: const Duration(milliseconds: 300),
                                                      child: Text(
                                                        localizations.aiCopied,
                                                        style: TextStyle(
                                                          fontSize: 12,
                                                          color: _chatMuted(theme),
                                                        ),
                                                      ),
                                                    ),
                                                  ),
                                                if (isAuthed && m.traceId != null) ...[
                                                  const SizedBox(width: 4),
                                                  _buildActionIcon(
                                                    icon: m.userRating == 'like' ? Icons.thumb_up : Icons.thumb_up_outlined,
                                                    color: m.userRating == 'like'
                                                        ? _chatThumbSelected(theme)
                                                        : _chatMuted(theme),
                                                    onTap: () => context.read<AiChatProvider>().submitMessageFeedback(i, 'like'),
                                                    tooltip: localizations.aiTooltipHelpful,
                                                  ),
                                                  _buildActionIcon(
                                                    icon: m.userRating == 'dislike' ? Icons.thumb_down : Icons.thumb_down_outlined,
                                                    color: m.userRating == 'dislike'
                                                        ? _chatThumbSelected(theme)
                                                        : _chatMuted(theme),
                                                    onTap: () => context.read<AiChatProvider>().submitMessageFeedback(i, 'dislike'),
                                                    tooltip: localizations.aiTooltipNotHelpful,
                                                  ),
                                                ],
                                              ],
                                            ],
                                          ),
                                        ),
                                    ],
                                  ),
                                ),
                                ),
                              );
                            },
                          ),
                  ),
                ),
                Builder(
                    builder: (context) {
                      final mq = MediaQuery.of(context);
                      // AiChatScreen is hosted inside an outer Scaffold that has a
                      // bottomNavigationBar (AiChatScreenWithBottomNav / MainNavigationScreen).
                      // viewInsets.bottom measures keyboard height from the SCREEN bottom, but
                      // the inner body's bottom sits ABOVE the outer nav bar.
                      //
                      // outerBottomNavH = screenH − viewPadding.top − outerBodyH
                      //
                      // outerBodyH is captured by the top-level LayoutBuilder in build()
                      // BEFORE the inner Scaffold/AppBar consumes any space, so we do not
                      // need to know kToolbarHeight or whether a parent Scaffold already
                      // consumed the status-bar inset.
                      //
                      // When there is no outer nav bar, outerBottomNavH ≤ 0 → clamped to 0
                      // → composerBottom = viewInsets.bottom (full keyboard height).
                      final outerBottomNavH = (mq.size.height
                              - mq.viewPadding.top
                              - outerBodyH)
                          .clamp(0.0, double.infinity);
                      final composerBottom =
                          (mq.viewInsets.bottom - outerBottomNavH)
                              .clamp(0.0, mq.viewInsets.bottom);
                    return Padding(
                      padding: EdgeInsets.fromLTRB(_chatPagePaddingH, 6, _chatPagePaddingH, 8 + composerBottom),
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Padding(
                            padding: const EdgeInsets.fromLTRB(0, 0, 0, 6),
                            child: Text(
                              localizations.aiFooterModelWarning,
                              textAlign: TextAlign.center,
                              style: TextStyle(
                                fontSize: 11,
                                height: 1.25,
                                color: _chatMuted(theme),
                              ),
                            ),
                          ),
                          Container(
                            padding: const EdgeInsets.fromLTRB(4, 4, 4, 4),
                            decoration: BoxDecoration(
                              color: _chatComposer(theme),
                              borderRadius: BorderRadius.circular(26),
                              border: Border.all(
                                color: _chatOutline(theme),
                                width: 1,
                              ),
                            ),
                            child: Row(
                              crossAxisAlignment: CrossAxisAlignment.end,
                              children: [
                                IconButton(
                                  style: IconButton.styleFrom(
                                    fixedSize: const Size(40, 40),
                                    padding: EdgeInsets.zero,
                                    tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                                    visualDensity: VisualDensity.compact,
                                  ),
                                  icon: Icon(
                                    Icons.tune_rounded,
                                    size: 22,
                                    color: _chatMuted(theme),
                                  ),
                                  tooltip: localizations.aiTooltipConfigureSources,
                                  onPressed: (ai.isStreaming || policyBlocksInput)
                                      ? null
                                      : () => _showSourcesSheet(context, ai),
                                ),
                                Expanded(
                                  child: TextField(
                                    controller: _controller,
                                    focusNode: _inputFocusNode,
                                    enabled: !policyBlocksInput,
                                    minLines: 1,
                                    maxLines: 6,
                                    maxLength: 4000,
                                    buildCounter: (context, {required currentLength, required isFocused, maxLength}) => null,
                                    textInputAction: TextInputAction.send,
                                    onSubmitted: (_) => _send(context, isAuthed),
                                    textAlignVertical: TextAlignVertical.center,
                                    style: TextStyle(
                                      fontSize: 16,
                                      height: 1.35,
                                      color: _chatBody(theme),
                                    ),
                                    cursorColor: ChatImmersivePalette.sendGreen,
                                    inputFormatters: [
                                      _EnterToSendFormatter(
                                        onEnterPressed: () => _send(context, isAuthed),
                                      ),
                                    ],
                                    decoration: InputDecoration(
                                      hintText: policyBlocksInput
                                          ? localizations.aiInputPolicyRequired
                                          : (_editingMessageIndex != null
                                              ? localizations.aiInputPlaceholderEdit
                                              : localizations.aiInputPlaceholderMessage),
                                      hintStyle: TextStyle(
                                        color: _chatMuted(theme),
                                        fontSize: 16,
                                      ),
                                      filled: true,
                                      fillColor: _chatComposer(theme),
                                      border: InputBorder.none,
                                      enabledBorder: InputBorder.none,
                                      focusedBorder: InputBorder.none,
                                      disabledBorder: InputBorder.none,
                                      errorBorder: InputBorder.none,
                                      focusedErrorBorder: InputBorder.none,
                                      isDense: true,
                                      contentPadding: const EdgeInsets.fromLTRB(4, 8, 4, 8),
                                      suffixIcon: _editingMessageIndex != null
                                          ? IconButton(
                                              icon: Icon(
                                                Icons.close_rounded,
                                                size: 20,
                                                color: _chatMuted(theme),
                                              ),
                                              onPressed: () {
                                                setState(() {
                                                  _editingMessageIndex = null;
                                                  _controller.clear();
                                                });
                                              },
                                              tooltip: localizations.aiTooltipCancelEdit,
                                            )
                                          : null,
                                    ),
                                  ),
                                ),
                                const SizedBox(width: 4),
                                if (ai.isStreaming || ai.inflightRestoreActive)
                                  Tooltip(
                                    message: localizations.aiStop,
                                    child: SizedBox(
                                      width: 40,
                                      height: 40,
                                      child: Material(
                                        color: _chatSendDisabled(theme),
                                        shape: const CircleBorder(),
                                        clipBehavior: Clip.antiAlias,
                                        child: InkWell(
                                          customBorder: const CircleBorder(),
                                          onTap: () => context.read<AiChatProvider>().stopStreaming(isAuthenticated: isAuthed),
                                          child: Center(
                                            child: Icon(
                                              Icons.stop_rounded,
                                              size: 20,
                                              color: _chatBody(theme),
                                            ),
                                          ),
                                        ),
                                      ),
                                    ),
                                  )
                                else if (ai.errorType == 'quota_exceeded' && ai.failedMessage != null)
                                  SizedBox(
                                    width: 40,
                                    height: 40,
                                    child: Material(
                                      color: ChatImmersivePalette.sendGreen,
                                      shape: const CircleBorder(),
                                      clipBehavior: Clip.antiAlias,
                                      child: InkWell(
                                        customBorder: const CircleBorder(),
                                        onTap: () => _retry(context, isAuthed),
                                        child: Center(
                                          child: Icon(
                                            Icons.refresh_rounded,
                                            size: 20,
                                            color: AccessibilityHelper
                                                .getAccessibleTextColor(ChatImmersivePalette.sendGreen),
                                          ),
                                        ),
                                      ),
                                    ),
                                  )
                                else
                                  ValueListenableBuilder<TextEditingValue>(
                                    valueListenable: _controller,
                                    builder: (context, value, _) {
                                      final hasText = value.text.trim().isNotEmpty;
                                      final canSend = hasText && !policyBlocksInput;
                                      return SizedBox(
                                        width: 40,
                                        height: 40,
                                        child: Material(
                                          color: canSend
                                              ? ChatImmersivePalette.sendButtonWhite
                                              : _chatSendDisabled(theme),
                                          shape: const CircleBorder(),
                                          clipBehavior: Clip.antiAlias,
                                          child: InkWell(
                                            customBorder: const CircleBorder(),
                                            onTap: canSend ? () => _send(context, isAuthed) : null,
                                            child: Center(
                                              child: Icon(
                                                Icons.arrow_upward_rounded,
                                                size: 20,
                                                color: canSend
                                                    ? ChatImmersivePalette.sendArrowBlack
                                                    : _chatMuted(theme),
                                              ),
                                            ),
                                          ),
                                        ),
                                      );
                                    },
                                  ),
                              ],
                            ),
                          ),
                        ],
                      ),
                    );
                    },
                  ),
              ],
            );
          },
        ),
      ),
    ),
    );
      }, // LayoutBuilder builder
    ); // LayoutBuilder
  }

  Future<void> _send(BuildContext context, bool isAuthenticated) async {
    final msg = _controller.text.trim();
    if (msg.isEmpty) return;

    final provider = context.read<AiChatProvider>();
    // Only enforce the policy gate once prefs have been read from storage.
    // During the brief async load window, treat the user as acknowledged so
    // a returning user is never incorrectly blocked.
    if (provider.prefsLoaded && !provider.policyAcknowledged) {
      _showPolicyRequiredSnack(context);
      return;
    }
    if (_redirectToLoginIfGuest(context, isAuthenticated)) return;
    final wasEditing = _editingMessageIndex != null;
    final editIndex = _editingMessageIndex;

    // Clear editing state before sending
    _editingMessageIndex = null;

    // Check if we're editing a message
    if (wasEditing && editIndex != null) {
      await provider.sendEditedMessage(
        message: msg,
        editIndex: editIndex,
        isAuthenticated: isAuthenticated,
      );
    } else {
      final lang = Localizations.localeOf(context).languageCode;
      await provider.sendMessageStreaming(
        message: msg,
        isAuthenticated: isAuthenticated,
        preferredLanguageCode: lang,
      );
    }

    // Clear the controller - if it's a quota error, the provider will restore it
    _controller.clear();

    // If a quota error occurs, restore the message to the controller
    // Wait a bit for the provider to process the error
    Future.delayed(const Duration(milliseconds: 100), () {
      if (!context.mounted) return;
      final ai = context.read<AiChatProvider>();
      if (ai.errorType == 'quota_exceeded' && ai.failedMessage != null && _controller.text.isEmpty) {
        _controller.text = ai.failedMessage!;
      }
    });
  }

  void _showEditMessageDialog(BuildContext context, int messageIndex, String messageContent) {
    // Get the message content for editing (messages won't be cleared until send)
    final provider = context.read<AiChatProvider>();
    final editedContent = provider.editMessageAt(messageIndex);
    if (editedContent != null) {
      setState(() {
        _editingMessageIndex = messageIndex;
        _controller.text = editedContent;
      });
      // Focus the input field
      _inputFocusNode.requestFocus();
      // Scroll to bottom to show the input
      _scrollToBottom();
    }
  }

  Future<void> _retry(BuildContext context, bool isAuthenticated) async {
    if (_redirectToLoginIfGuest(context, isAuthenticated)) return;
    final provider = context.read<AiChatProvider>();
    if (provider.failedMessage != null) {
      // Restore the message to the controller if it's not already there
      if (_controller.text != provider.failedMessage) {
        _controller.text = provider.failedMessage!;
      }
      await provider.retryFailedMessage(isAuthenticated: isAuthenticated);
    }
  }

  Widget _drawerConversationSectionHeader(ThemeData theme, String label, {required bool isFirst}) {
    return Padding(
      padding: EdgeInsets.fromLTRB(4, isFirst ? 0 : 14, 4, 6),
      child: Text(
        label,
        style: TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.35,
          color: _chatMuted(theme),
        ),
      ),
    );
  }

  Widget _buildDrawer(BuildContext context, AuthProvider auth, AiChatProvider ai, bool isAuthed) {
    final theme = Theme.of(context);
    final loc = AppLocalizations.of(context)!;
    final cs = theme.colorScheme; // error + dialogs only

    // Filter conversations based on search query
    final filteredConversations = _searchQuery.isEmpty
        ? ai.conversations
        : ai.conversations.where((c) {
            final title = (c.title ?? '').toLowerCase();
            return title.contains(_searchQuery.toLowerCase());
          }).toList();

    final pinnedFiltered = <AiConversationSummary>[];
    final unpinnedFiltered = <AiConversationSummary>[];
    for (final c in filteredConversations) {
      if (ai.isConversationPinned(c.id)) {
        pinnedFiltered.add(c);
      } else {
        unpinnedFiltered.add(c);
      }
    }

    return Drawer(
      backgroundColor: _chatSurface(theme),
      elevation: 1,
      shadowColor: Colors.black.withValues(alpha: 0.08),
      surfaceTintColor: Colors.transparent,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.zero),
      child: SafeArea(
        child: Column(
          children: [
            // Title
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 16),
              child: Row(
                children: [
                  Text(
                    loc.aiConversationsDrawerTitle,
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                      color: _chatBody(theme),
                    ),
                  ),
                ],
              ),
            ),
          // Search bar — pill style aligned with main chat composer
          if (ai.conversations.isNotEmpty)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
              child: Container(
                padding: const EdgeInsets.fromLTRB(4, 4, 4, 4),
                decoration: BoxDecoration(
                  color: _chatComposer(theme),
                  borderRadius: BorderRadius.circular(26),
                  border: Border.all(
                    color: _chatOutline(theme),
                    width: 1,
                  ),
                ),
                child: TextField(
                  controller: _searchController,
                  focusNode: _searchFocusNode,
                  autofocus: false,
                  enableInteractiveSelection: true,
                  textAlignVertical: TextAlignVertical.center,
                  onTapOutside: (_) {
                    _searchFocusNode.unfocus();
                    SystemChannels.textInput.invokeMethod('TextInput.hide');
                  },
                  onTap: () {
                    _searchFocusNode.requestFocus();
                  },
                  onChanged: (value) {
                    setState(() {
                      _searchQuery = value;
                    });
                  },
                  style: TextStyle(
                    fontSize: 15,
                    height: 1.3,
                    color: _chatBody(theme),
                  ),
                  cursorColor: ChatImmersivePalette.sendGreen,
                  decoration: InputDecoration(
                    hintText: loc.aiSearchConversationsHint,
                    hintStyle: TextStyle(
                      color: _chatMuted(theme),
                      fontSize: 15,
                    ),
                    isDense: true,
                    border: InputBorder.none,
                    enabledBorder: InputBorder.none,
                    focusedBorder: InputBorder.none,
                    disabledBorder: InputBorder.none,
                    errorBorder: InputBorder.none,
                    focusedErrorBorder: InputBorder.none,
                    filled: true,
                    fillColor: Colors.transparent,
                    contentPadding: const EdgeInsets.fromLTRB(4, 8, 4, 8),
                    prefixIcon: Icon(
                      Icons.search,
                      size: 20,
                      color: _chatMuted(theme),
                    ),
                    prefixIconConstraints: const BoxConstraints(
                      minWidth: 40,
                      minHeight: 40,
                    ),
                    suffixIcon: _searchQuery.isNotEmpty
                        ? IconButton(
                            icon: Icon(
                              Icons.clear,
                              size: 20,
                              color: _chatMuted(theme),
                            ),
                            onPressed: () {
                              _searchController.clear();
                              setState(() {
                                _searchQuery = '';
                              });
                            },
                          )
                        : null,
                    suffixIconConstraints: const BoxConstraints(
                      minWidth: 40,
                      minHeight: 40,
                    ),
                  ),
                ),
              ),
            ),
          // Conversations List (offline-first: show local conversations even when logged out)
          Expanded(
              child: ai.isLoading
                  ? const Center(child: CircularProgressIndicator())
                  : ai.conversations.isEmpty
                      ? Center(
                          child: Padding(
                            padding: const EdgeInsets.all(24.0),
                            child: Column(
                              mainAxisAlignment: MainAxisAlignment.center,
                              children: [
                                Icon(
                                  Icons.chat_bubble_outline,
                                  size: 48,
                                  color: _chatMuted(theme),
                                ),
                                const SizedBox(height: 16),
                                Text(
                                  isAuthed
                                      ? loc.aiNoConversationsBody
                                      : loc.aiNoConversationsOffline,
                                  style: TextStyle(
                                    color: _chatMuted(theme),
                                    fontSize: 14,
                                  ),
                                  textAlign: TextAlign.center,
                                ),
                              ],
                            ),
                          ),
                        )
                      : filteredConversations.isEmpty
                          ? Center(
                              child: Padding(
                                padding: const EdgeInsets.all(24.0),
                                child: Column(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: [
                                    Icon(
                                      Icons.search_off,
                                      size: 48,
                                      color: _chatMuted(theme),
                                    ),
                                    const SizedBox(height: 16),
                                    Text(
                                      loc.aiNoConversationsFiltered,
                                      style: TextStyle(
                                        color: _chatMuted(theme),
                                        fontSize: 14,
                                      ),
                                      textAlign: TextAlign.center,
                                    ),
                                  ],
                                ),
                              ),
                            )
                          : ListView(
                              padding: const EdgeInsets.fromLTRB(12, 16, 12, 10),
                              children: [
                                if (pinnedFiltered.isNotEmpty) ...[
                                  _drawerConversationSectionHeader(theme, loc.aiSectionPinned, isFirst: true),
                                  ...pinnedFiltered.map(
                                    (c) => _buildConversationTile(
                                      context,
                                      c,
                                      ai.conversationId == c.id,
                                      isAuthed,
                                      ai.isConversationOngoingInDrawer(c.id),
                                    ),
                                  ),
                                ],
                                if (unpinnedFiltered.isNotEmpty) ...[
                                  if (pinnedFiltered.isNotEmpty)
                                    _drawerConversationSectionHeader(theme, loc.aiSectionRecent, isFirst: false),
                                  ...unpinnedFiltered.map(
                                    (c) => _buildConversationTile(
                                      context,
                                      c,
                                      ai.conversationId == c.id,
                                      isAuthed,
                                      ai.isConversationOngoingInDrawer(c.id),
                                    ),
                                  ),
                                ],
                              ],
                            ),
            ),
          // Footer actions: single block, tight vertical rhythm (was three padded sections)
          Container(
            decoration: BoxDecoration(
              border: Border(
                top: BorderSide(
                  color: _chatOutline(theme),
                  width: 1,
                ),
              ),
            ),
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 6),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (ai.conversations.isNotEmpty) ...[
                  Material(
                    color: Colors.transparent,
                    child: InkWell(
                      onTap: () async {
                        final shouldClear = await showDialog<bool>(
                          context: context,
                          builder: (dialogContext) {
                            final dcs = Theme.of(dialogContext).colorScheme;
                            final dlgLoc = AppLocalizations.of(dialogContext)!;
                            return AlertDialog(
                              title: Text(
                                dlgLoc.aiClearAllDialogTitle,
                                style: TextStyle(
                                  color: dcs.onSurface,
                                ),
                              ),
                              content: Text(
                                dlgLoc.aiClearAllDialogBody,
                                style: TextStyle(
                                  color: dcs.onSurfaceVariant,
                                ),
                              ),
                              backgroundColor: dcs.surface,
                              actions: [
                                TextButton(
                                  onPressed: () => Navigator.pop(dialogContext, false),
                                  child: Text(
                                    dlgLoc.cancel,
                                    style: TextStyle(
                                      color: dcs.onSurfaceVariant,
                                    ),
                                  ),
                                ),
                                TextButton(
                                  onPressed: () => Navigator.pop(dialogContext, true),
                                  style: TextButton.styleFrom(
                                    foregroundColor: dcs.error,
                                  ),
                                  child: Text(dlgLoc.aiClearAllButton),
                                ),
                              ],
                            );
                          },
                        );
                        if (shouldClear == true && context.mounted) {
                          Navigator.pop(context);
                          await context.read<AiChatProvider>().clearAllConversations(isAuthenticated: isAuthed);
                          _searchController.clear();
                          setState(() {
                            _searchQuery = '';
                          });
                        }
                      },
                      borderRadius: BorderRadius.circular(8),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                        child: Row(
                          children: [
                            Icon(
                              Icons.delete_sweep_outlined,
                              size: 20,
                              color: cs.error,
                            ),
                            const SizedBox(width: 10),
                            Text(
                              loc.aiClearAllRow,
                              style: TextStyle(
                                fontSize: 15,
                                color: _chatGptDark(theme) ? Colors.white : cs.onSurface,
                                fontWeight: FontWeight.w500,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ],
                Material(
                  color: Colors.transparent,
                  child: InkWell(
                    onTap: () {
                      Navigator.pop(context);
                      _showHelpDialog(context);
                    },
                    borderRadius: BorderRadius.circular(8),
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                      child: Row(
                        children: [
                          Icon(
                            Icons.help_outline,
                            size: 20,
                            color: _chatMuted(theme),
                          ),
                          const SizedBox(width: 10),
                          Text(
                            loc.aiHelpAboutRow,
                            style: TextStyle(
                              fontSize: 15,
                              color: _chatBody(theme),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
          ],
        ),
      ),
    );
  }

  /// Context must be from the conversation row so [findRenderObject] matches the tile bounds.
  Future<void> _showConversationActionMenu(
    BuildContext anchorContext,
    ThemeData theme,
    AiConversationSummary conversation,
    bool isAuthed,
  ) async {
    final loc = AppLocalizations.of(anchorContext)!;
    final box = anchorContext.findRenderObject() as RenderBox?;
    final overlayState = Navigator.of(anchorContext).overlay;
    if (box == null || !box.hasSize || overlayState == null) return;
    final overlay = overlayState.context.findRenderObject() as RenderBox?;

    if (overlay == null) return;

    final topLeft = box.localToGlobal(Offset.zero, ancestor: overlay);
    final bottomRight = box.localToGlobal(box.size.bottomRight(Offset.zero), ancestor: overlay);
    // Anchor below the row (not the full tile rect) so the menu doesn't paint over the title.
    const menuGap = 8.0;
    final rowWidth = bottomRight.dx - topLeft.dx;
    final anchorRect = Rect.fromLTWH(
      topLeft.dx,
      bottomRight.dy + menuGap,
      rowWidth,
      1,
    );

    final provider = anchorContext.read<AiChatProvider>();
    final pinned = provider.isConversationPinned(conversation.id);
    final menuCs = theme.colorScheme;

    await showMenu<String>(
      context: anchorContext,
      position: RelativeRect.fromRect(anchorRect, Offset.zero & overlay.size),
      color: _chatSurface(theme),
      surfaceTintColor: Colors.transparent,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(10),
        side: BorderSide(color: _chatOutline(theme)),
      ),
      elevation: 4,
      items: <PopupMenuEntry<String>>[
        PopupMenuItem<String>(
          value: 'pin',
          height: 40,
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
          onTap: () {
            Future<void>.delayed(Duration.zero, () async {
              await provider.setConversationPinned(conversation.id, !pinned);
            });
          },
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                pinned ? Icons.push_pin : Icons.push_pin_outlined,
                size: 18,
                color: _chatBody(theme),
              ),
              const SizedBox(width: 8),
              Text(
                pinned ? loc.aiUnpin : loc.aiPin,
                style: TextStyle(
                  color: _chatBody(theme),
                  fontWeight: FontWeight.w500,
                  fontSize: 13,
                ),
              ),
            ],
          ),
        ),
        PopupMenuItem<String>(
          value: 'delete',
          height: 40,
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 0),
          onTap: () {
            Future<void>.delayed(Duration.zero, () async {
              if (!anchorContext.mounted) return;
              final shouldDelete = await showDialog<bool>(
                context: anchorContext,
                builder: (dialogContext) {
                  final dcs = Theme.of(dialogContext).colorScheme;
                  final dlgLoc = AppLocalizations.of(dialogContext)!;
                  return AlertDialog(
                    title: Text(
                      dlgLoc.aiDeleteConversationTitle,
                      style: TextStyle(
                        color: dcs.onSurface,
                      ),
                    ),
                    content: Text(
                      dlgLoc.aiDeleteConversationBody,
                      style: TextStyle(
                        color: dcs.onSurfaceVariant,
                      ),
                    ),
                    backgroundColor: dcs.surface,
                    actions: [
                      TextButton(
                        onPressed: () => Navigator.pop(dialogContext, false),
                        child: Text(
                          dlgLoc.cancel,
                          style: TextStyle(
                            color: dcs.onSurfaceVariant,
                          ),
                        ),
                      ),
                      TextButton(
                        onPressed: () => Navigator.pop(dialogContext, true),
                        style: TextButton.styleFrom(
                          foregroundColor: dcs.error,
                        ),
                        child: Text(dlgLoc.delete),
                      ),
                    ],
                  );
                },
              );
              if (shouldDelete == true && anchorContext.mounted) {
                await provider.deleteConversation(
                  conversation.id,
                  isAuthenticated: isAuthed,
                );
              }
            });
          },
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.delete_outline,
                size: 18,
                color: menuCs.error,
              ),
              const SizedBox(width: 8),
              Text(
                loc.delete,
                style: TextStyle(
                  color: menuCs.error,
                  fontWeight: FontWeight.w500,
                  fontSize: 13,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildConversationTile(
    BuildContext context,
    AiConversationSummary conversation,
    bool isSelected,
    bool isAuthed,
    bool isOngoing,
  ) {
    final loc = AppLocalizations.of(context)!;
    final title = conversation.title ?? loc.aiNewChatTitleFallback;
    final truncatedTitle = title.length > 50 ? '${title.substring(0, 50)}...' : title;
    final theme = Theme.of(context);
    final muted = _chatMuted(theme);

    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Builder(
        builder: (anchorContext) {
          return Material(
            color: Colors.transparent,
            child: InkWell(
              onTap: () async {
                Navigator.pop(context);
                await context.read<AiChatProvider>().openConversation(
                      isAuthenticated: isAuthed,
                      conversationId: conversation.id,
                    );
              },
              onLongPress: () {
                _showConversationActionMenu(anchorContext, theme, conversation, isAuthed);
              },
              borderRadius: BorderRadius.circular(10),
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                decoration: BoxDecoration(
                  color: isSelected ? _chatBubble(theme) : Colors.transparent,
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Row(
                  children: [
                    Expanded(
                      child: Text(
                        truncatedTitle,
                        style: TextStyle(
                          fontSize: 14,
                          height: 1.25,
                          color: _chatBody(theme),
                          fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    if (isOngoing) ...[
                      const SizedBox(width: 8),
                      Semantics(
                        label: 'Generating',
                        child: SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(
                            strokeWidth: 2,
                            color: muted,
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  void _showHelpDialog(BuildContext context) {
    showDialog(
      context: context,
      builder: (dialogContext) {
        final dT = Theme.of(dialogContext);
        final h = AppLocalizations.of(dialogContext)!;
        return AlertDialog(
        title: Text(
          h.aiHelpDialogTitle,
          style: TextStyle(
            color: _chatBody(dT),
          ),
        ),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                h.aiHelpAboutHeading,
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                  color: _chatBody(dT),
                ),
              ),
              const SizedBox(height: 8),
              Text(
                h.aiHelpAboutParagraph,
                style: TextStyle(
                  fontSize: 14,
                  color: _chatMuted(dT),
                ),
              ),
              const SizedBox(height: 16),
              Text(
                h.aiHelpFeaturesHeading,
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                  color: _chatBody(dT),
                ),
              ),
              const SizedBox(height: 8),
              _buildHelpItem(
                dialogContext,
                h.aiHelpFeatureBullet1,
              ),
              _buildHelpItem(
                dialogContext,
                h.aiHelpFeatureBullet2,
              ),
              _buildHelpItem(
                dialogContext,
                h.aiHelpFeatureBullet3,
              ),
              _buildHelpItem(
                dialogContext,
                h.aiHelpFeatureBullet4,
              ),
              const SizedBox(height: 16),
              Text(
                h.aiHelpTipsHeading,
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                  color: _chatBody(dT),
                ),
              ),
              const SizedBox(height: 8),
              _buildHelpItem(
                dialogContext,
                h.aiHelpTipBullet1,
              ),
              _buildHelpItem(
                dialogContext,
                h.aiHelpTipBullet2,
              ),
              _buildHelpItem(
                dialogContext,
                h.aiHelpTipBullet3,
              ),
              _buildHelpItem(
                dialogContext,
                h.aiHelpTipBullet4,
              ),
            ],
          ),
        ),
        backgroundColor: _chatSurface(dT),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: Text(
              h.aiGotIt,
              style: TextStyle(
                color: _chatBody(dT),
              ),
            ),
          ),
        ],
      );
      },
    );
  }

  Widget _buildHelpItem(BuildContext context, String text) {
    final t = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Text(
        text,
        style: TextStyle(
          fontSize: 14,
          color: _chatMuted(t),
        ),
      ),
    );
  }

  Widget _buildActionIcon({
    required IconData icon,
    double size = _messageActionIconSize,
    required Color color,
    required VoidCallback onTap,
    required String tooltip,
  }) {
    return Tooltip(
      message: tooltip,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(_messageActionTap / 2),
          child: SizedBox(
            width: _messageActionTap,
            height: _messageActionTap,
            child: Center(
              child: Icon(
                icon,
                size: size,
                color: color,
              ),
            ),
          ),
        ),
      ),
    );
  }

  void _copyToClipboard(BuildContext context, String text, int messageIndex) {
    Clipboard.setData(ClipboardData(text: text));

    // Cancel any existing timer
    _copiedTimer?.cancel();

    // Set the copied message index
    setState(() {
      _copiedMessageIndex = messageIndex;
    });

    // Clear the "Copied!" text after 1 second (fade out will happen via AnimatedOpacity)
    _copiedTimer = Timer(const Duration(seconds: 1), () {
      if (mounted) {
        setState(() {
          _copiedMessageIndex = null;
        });
      }
    });
  }

  Widget _buildErrorMessageBubble(
    BuildContext context,
    String errorMessage,
    String? errorType,
    double? retryDelay,
    bool isAuthed,
  ) {
    final loc = AppLocalizations.of(context)!;
    final ai = context.read<AiChatProvider>();
    final theme = Theme.of(context);
    final cs = theme.colorScheme;
    final gptDark = _chatGptDark(theme);
    return Align(
      alignment: Alignment.centerLeft,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width - (_chatPagePaddingH * 2),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              margin: const EdgeInsets.symmetric(vertical: 6),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: gptDark ? const Color(0xFF2A1F1F) : cs.errorContainer,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(
                  color: gptDark
                      ? const Color(0xFF6B3D3D)
                      : cs.error.withValues(alpha: 0.45),
                  width: 1,
                ),
              ),
              child: Row(
                children: [
                  Icon(
                    Icons.error_outline,
                    size: 18,
                    color: gptDark ? const Color(0xFFE57373) : cs.error,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      _userFacingChatErrorText(loc, errorMessage, errorType),
                      style: TextStyle(
                        color: gptDark ? const Color(0xFFF0D4D4) : cs.onErrorContainer,
                        fontSize: 14,
                      ),
                    ),
                  ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  _buildActionIcon(
                    icon: Icons.refresh,
                    color: gptDark ? _chatMuted(theme) : cs.onSurfaceVariant,
                    onTap: () {
                      if (_redirectToLoginIfGuest(context, isAuthed)) return;
                      final provider = context.read<AiChatProvider>();
                      // For quota errors, use retryFailedMessage which handles the stored failed message
                      if (ai.errorType == 'quota_exceeded' && ai.failedMessage != null) {
                        provider.retryFailedMessage(isAuthenticated: isAuthed);
                      } else {
                        // For other errors, retry the last user message
                        provider.retryLastMessage(isAuthenticated: isAuthed);
                      }
                    },
                    tooltip: loc.retry,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildPromptChip({
    required ThemeData theme,
    required String prompt,
    required VoidCallback onTap,
  }) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(20),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
          decoration: BoxDecoration(
            color: theme.isDarkTheme
                ? _chatBubble(theme)
                : _chatSurface(theme),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: _chatOutline(theme),
              width: 1,
            ),
            boxShadow: theme.isDarkTheme
                ? null
                : [
                    BoxShadow(
                      color: theme.ambientShadow(lightOpacity: 0.04),
                      blurRadius: 8,
                      offset: const Offset(0, 2),
                    ),
                  ],
          ),
          child: Text(
            prompt,
            style: TextStyle(
              fontSize: 13,
              height: 1.3,
              color: _chatBody(theme),
            ),
          ),
        ),
      ),
    );
  }
}

/// Pushes [AiChatScreen] with the same bottom bar as [MainNavigationScreen]; tab taps use [NavigationHelper].
class AiChatScreenWithBottomNav extends StatelessWidget {
  const AiChatScreenWithBottomNav({super.key});

  @override
  Widget build(BuildContext context) {
    final launch = AiChatLaunchArgs.parse(ModalRoute.of(context)?.settings.arguments);
    final navTabIndex = launch.bottomNavTabIndex;

    return Consumer<AuthProvider>(
      builder: (context, auth, _) {
        final isFocalPoint = auth.user?.role == 'focal_point';
        final chatbot = auth.user?.chatbotEnabled ?? false;
        return Scaffold(
          resizeToAvoidBottomInset: false,
          body: const AiChatScreen(),
          // When AiChatScreenWithBottomNav is shown as a standalone route
          // (deep link, notification tap, etc.), tapping any tab navigates to
          // the main screen at the requested tab index.
          bottomNavigationBar: AppBottomNavigationBar(
            currentIndex: navTabIndex,
            isFocalPoint: isFocalPoint,
            chatbotEnabled: chatbot,
          ),
        );
      },
    );
  }
}

class _TypingIndicator extends StatefulWidget {
  const _TypingIndicator();

  @override
  State<_TypingIndicator> createState() => _TypingIndicatorState();
}

class _TypingIndicatorState extends State<_TypingIndicator> with TickerProviderStateMixin {
  late List<AnimationController> _controllers;
  late List<Animation<double>> _animations;

  @override
  void initState() {
    super.initState();
    _controllers = List.generate(
      3,
      (index) => AnimationController(
        duration: const Duration(milliseconds: 600),
        vsync: this,
      ),
    );

    _animations = _controllers.map((controller) {
      return Tween<double>(begin: 0.0, end: 1.0).animate(
        CurvedAnimation(parent: controller, curve: Curves.easeInOut),
      );
    }).toList();

    // Stagger the animations - start each dot with a delay
    for (int i = 0; i < _controllers.length; i++) {
      Future.delayed(Duration(milliseconds: i * 200), () {
        if (mounted) {
          _controllers[i].repeat(reverse: true);
        }
      });
    }
  }

  @override
  void dispose() {
    for (final controller in _controllers) {
      controller.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final dotColor =
        t.brightness == Brightness.dark ? const Color(0xFF9B9B9B) : t.colorScheme.onSurfaceVariant;
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 6, 0, 6),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: List.generate(3, (index) {
          return AnimatedBuilder(
            animation: _animations[index],
            builder: (context, child) {
              return Opacity(
                opacity: 0.25 + (_animations[index].value * 0.65),
                child: Container(
                  margin: const EdgeInsets.symmetric(horizontal: 3),
                  width: 7,
                  height: 7,
                  decoration: BoxDecoration(
                    color: dotColor,
                    shape: BoxShape.circle,
                  ),
                ),
              );
            },
          );
        }),
      ),
    );
  }
}

/// TextInputFormatter that intercepts Enter key presses and triggers send
/// instead of creating a newline.
class _EnterToSendFormatter extends TextInputFormatter {
  final VoidCallback onEnterPressed;

  _EnterToSendFormatter({required this.onEnterPressed});

  @override
  TextEditingValue formatEditUpdate(
    TextEditingValue oldValue,
    TextEditingValue newValue,
  ) {
    // Check if exactly one character was added (likely Enter key press)
    // This distinguishes Enter key from paste operations
    final lengthDiff = newValue.text.length - oldValue.text.length;

    if (lengthDiff == 1 && newValue.text.endsWith('\n') && !oldValue.text.endsWith('\n')) {
      // Enter was pressed - remove the newline and trigger send
      final textWithoutNewline = oldValue.text; // Keep the old text (without newline)
      if (textWithoutNewline.trim().isNotEmpty) {
        // Schedule the callback to run after the current frame
        WidgetsBinding.instance.addPostFrameCallback((_) {
          onEnterPressed();
        });
      }

      // Return the value without the newline
      return TextEditingValue(
        text: textWithoutNewline,
        selection: TextSelection.collapsed(offset: textWithoutNewline.length),
      );
    }

    return newValue;
  }
}
