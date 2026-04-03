import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_html/flutter_html.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:cross_file/cross_file.dart';

import '../../providers/shared/ai_chat_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../models/shared/ai_chat.dart';
import '../../utils/ios_constants.dart';
import '../../widgets/bottom_navigation_bar.dart';
import '../../widgets/ai_chat_agent_progress_panel.dart';
import '../../widgets/ai_chat_structured_views.dart';
import '../../services/ai_chat_service.dart';
import '../../services/organization_config_service.dart';
import '../../config/app_config.dart';
import '../../config/routes.dart';

class AiChatScreen extends StatefulWidget {
  const AiChatScreen({super.key});

  @override
  State<AiChatScreen> createState() => _AiChatScreenState();
}

class _AiChatScreenState extends State<AiChatScreen> {
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

  /// Same example prompts as `chat_immersive.html` (English source strings).
  static const List<String> _quickPrompts = [
    'How many volunteers in Bangladesh?',
    'Volunteers in Syria over time',
    'World heatmap of volunteers by country',
    'Number of branches in Kenya',
    'Staff and local units in Nigeria',
  ];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final lang = Localizations.localeOf(context).languageCode;
      context.read<AiChatProvider>().setPreferredLanguageCode(lang);
      unawaited(context.read<AiChatProvider>().loadChatUiPrefs());
      _loadConversations();
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
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
    await context.read<AiChatProvider>().loadConversations(isAuthenticated: isAuthed);
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

  String _welcomeAssistantName() {
    try {
      if (OrganizationConfigService().isInitialized) {
        return OrganizationConfigService().config.app.name;
      }
    } catch (_) {}
    return 'AI Assistant';
  }

  void _showPolicyRequiredSnack(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Please acknowledge the AI policy to continue.')),
    );
  }

  String _scoreChipLabel(String name, double v) {
    final pct = v > 1.0001 ? v : (v * 100);
    return '$name ${pct.toStringAsFixed(0)}%';
  }

  void _showAiPolicyModal(BuildContext context, bool isDark) {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      backgroundColor: isDark ? Colors.grey[900] : Colors.white,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.zero),
      builder: (ctx) {
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
                    'AI Use Policy',
                    style: TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                      color: isDark ? Colors.grey[100] : Colors.grey[900],
                    ),
                  ),
                  const SizedBox(height: 12),
                  Expanded(
                    child: ListView(
                      controller: scrollController,
                      children: [
                        Text(
                          "Don't share sensitive information.",
                          style: TextStyle(
                            fontWeight: FontWeight.w600,
                            fontSize: 15,
                            color: isDark ? Colors.amber[200] : Colors.amber[900],
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'We use system traces and telemetry to improve the assistant. Your messages may be processed by external AI providers.',
                          style: TextStyle(
                            fontSize: 14,
                            height: 1.4,
                            color: isDark ? Colors.grey[300] : Colors.grey[800],
                          ),
                        ),
                        const SizedBox(height: 20),
                        _policySection(
                          isDark,
                          'Purpose',
                          'The AI assistant helps you explore data and documents on this platform. It can answer questions about indicators, countries, assignments, and search through uploaded documents.',
                        ),
                        _policySection(
                          isDark,
                          'Acceptable use',
                          '• Ask about platform data, indicators, and documents.\n'
                          '• Do NOT share passwords, credentials, or highly confidential operational details.\n'
                          '• Do NOT paste personal or financial data.',
                        ),
                        _policySection(
                          isDark,
                          'Accuracy',
                          'AI can make mistakes or misinterpret data. Always verify important information against source data or documents.',
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),
                  FilledButton(
                    onPressed: () async {
                      Navigator.pop(ctx);
                      await context.read<AiChatProvider>().acknowledgeAiPolicy();
                    },
                    child: const Text('I understand'),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }

  Widget _policySection(bool isDark, String title, String body) {
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
              color: isDark ? Colors.grey[200] : Colors.grey[900],
            ),
          ),
          const SizedBox(height: 6),
          Text(
            body,
            style: TextStyle(
              fontSize: 14,
              height: 1.4,
              color: isDark ? Colors.grey[400] : Colors.grey[700],
            ),
          ),
        ],
      ),
    );
  }

  void _showSourcesSheet(BuildContext context, AiChatProvider ai, bool isDark) {
    bool historical = ai.selectedSources.contains('historical');
    bool system = ai.selectedSources.contains('system_documents');
    bool upr = ai.selectedSources.contains('upr_documents');

    showModalBottomSheet<void>(
      context: context,
      backgroundColor: isDark ? Colors.grey[900] : Colors.white,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.zero),
      builder: (ctx) {
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

            return Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    'Use sources:',
                    style: TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 14,
                      color: isDark ? Colors.grey[200] : Colors.grey[900],
                    ),
                  ),
                  const SizedBox(height: 12),
                  CheckboxListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text('Databank', style: TextStyle(color: isDark ? Colors.grey[300] : Colors.grey[800])),
                    value: historical,
                    onChanged: (v) => toggle('historical', v ?? false),
                  ),
                  CheckboxListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text('System documents', style: TextStyle(color: isDark ? Colors.grey[300] : Colors.grey[800])),
                    value: system,
                    onChanged: (v) => toggle('system_documents', v ?? false),
                  ),
                  CheckboxListTile(
                    contentPadding: EdgeInsets.zero,
                    title: Text('UPR documents', style: TextStyle(color: isDark ? Colors.grey[300] : Colors.grey[800])),
                    value: upr,
                    onChanged: (v) => toggle('upr_documents', v ?? false),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'At least one source stays enabled (same as the web assistant).',
                    style: TextStyle(fontSize: 12, color: isDark ? Colors.grey[500] : Colors.grey[600]),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }

  Future<void> _exportCurrentConversation(BuildContext context, AiChatProvider ai) async {
    final cid = ai.conversationId;
    if (cid == null || cid.isEmpty) return;
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Preparing export…')));
    final bytes = await AiChatService().exportConversationJsonBytes(cid);
    if (!context.mounted) return;
    if (bytes == null || bytes.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Export failed')));
      return;
    }
    try {
      final dir = await getTemporaryDirectory();
      final file = File('${dir.path}/ai-conversation-$cid.json');
      await file.writeAsBytes(bytes);
      await Share.shareXFiles([XFile(file.path)], subject: 'AI conversation export');
    } catch (_) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Could not share export')));
      }
    }
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

  /// True if [url] is a document download/source link from the AI (backend path).
  bool _isDocumentSourceUrl(String url) {
    final path = url.split('?').first.split('#').first.trim();
    return path.startsWith('/api/ai/documents/') && path.contains('/download');
  }

  bool _isAllowedInternalRoute(String route) {
    // Basic hardening: avoid path traversal-ish inputs.
    if (route.contains('..') || route.contains('\\')) return false;
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
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Interactive tours are available on the web version. Navigating to the page...'),
              duration: Duration(seconds: 2),
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
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    final ai = context.watch<AiChatProvider>();
    final isAuthed = auth.isAuthenticated;
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    _maybeScrollToBottom(ai);

    // AppBar title: current conversation title or "New chat" (aligned with chat_immersive main title)
    final match = ai.conversations.where((c) => c.id == ai.conversationId);
    final appBarTitle = match.isEmpty ? 'New chat' : (match.first.title ?? 'New chat');

    return Scaffold(
      resizeToAvoidBottomInset: true,
      appBar: AppBar(
        title: Text(appBarTitle),
        actions: [
          IconButton(
            icon: const Icon(Icons.add_comment_outlined),
            tooltip: 'New chat',
            onPressed: () => context.read<AiChatProvider>().startNewConversation(),
          ),
        ],
      ),
      drawer: _buildDrawer(context, auth, ai, isAuthed),
      body: SafeArea(
        bottom: false,
        child: LayoutBuilder(
          builder: (context, constraints) {
            final showInflightBar = ai.inflightRestoreActive &&
                ai.agentSteps.isNotEmpty &&
                !(ai.isStreaming &&
                    ai.messages.isNotEmpty &&
                    ai.messages.last.role == 'assistant' &&
                    ai.messages.last.content.isEmpty);

            return Column(
              children: [
                if (auth.user?.aiBetaTester == true)
                  Material(
                    color: isDark ? const Color(0xFF422006) : Colors.amber.shade100,
                    child: Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                      child: Row(
                        children: [
                          Icon(Icons.science_outlined, size: 18, color: isDark ? Colors.amber.shade200 : Colors.amber.shade900),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              'AI beta tester — experimental assistant features may be enabled.',
                              style: TextStyle(
                                fontSize: 12,
                                height: 1.25,
                                color: isDark ? Colors.amber.shade100 : Colors.amber.shade900,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                if (showInflightBar)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
                    child: AiChatAgentProgressPanel(steps: ai.agentSteps, isDark: isDark),
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
                            child: SingleChildScrollView(
                              child: Padding(
                                padding: const EdgeInsets.all(32.0),
                                child: Column(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  crossAxisAlignment: CrossAxisAlignment.stretch,
                                  children: [
                                    Icon(
                                      Icons.forum_outlined,
                                      size: 56,
                                      color: isDark ? Colors.grey[600] : Colors.grey[400],
                                    ),
                                    const SizedBox(height: 12),
                                    Text(
                                      _welcomeAssistantName(),
                                      style: TextStyle(
                                        fontSize: 22,
                                        fontWeight: FontWeight.w600,
                                        color: isDark ? Colors.grey[200] : Colors.grey[800],
                                      ),
                                      textAlign: TextAlign.center,
                                    ),
                                    const SizedBox(height: 8),
                                    Text(
                                      'How can I help you today?',
                                      style: TextStyle(
                                        fontSize: 17,
                                        fontWeight: FontWeight.w500,
                                        color: isDark ? Colors.grey[400] : Colors.grey[600],
                                      ),
                                      textAlign: TextAlign.center,
                                    ),
                                    const SizedBox(height: 20),
                                    Container(
                                      padding: const EdgeInsets.all(14),
                                      decoration: BoxDecoration(
                                        color: isDark ? const Color(0xFF171717) : Colors.grey[50],
                                        border: Border.all(
                                          color: isDark ? Colors.grey[800]! : Colors.grey[300]!,
                                        ),
                                      ),
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Text(
                                            "Don't share sensitive information. We use system traces/telemetry to improve the assistant.",
                                            style: TextStyle(
                                              fontSize: 13,
                                              height: 1.35,
                                              color: isDark ? Colors.grey[300] : Colors.grey[800],
                                            ),
                                          ),
                                          const SizedBox(height: 8),
                                          Text(
                                            'AI can make mistakes. Check important information.',
                                            style: TextStyle(
                                              fontSize: 12,
                                              color: isDark ? Colors.grey[500] : Colors.grey[600],
                                            ),
                                          ),
                                          const SizedBox(height: 12),
                                          Wrap(
                                            spacing: 8,
                                            runSpacing: 8,
                                            crossAxisAlignment: WrapCrossAlignment.center,
                                            children: [
                                              TextButton(
                                                onPressed: () => _showAiPolicyModal(context, isDark),
                                                child: const Text('View AI policy'),
                                              ),
                                              if (!ai.policyAcknowledged)
                                                FilledButton(
                                                  onPressed: () async {
                                                    await context.read<AiChatProvider>().acknowledgeAiPolicy();
                                                  },
                                                  child: const Text('I understand'),
                                                ),
                                            ],
                                          ),
                                        ],
                                      ),
                                    ),
                                    const SizedBox(height: 24),
                                    Text(
                                      'Try asking',
                                      style: TextStyle(
                                        fontSize: 14,
                                        fontWeight: FontWeight.w500,
                                        color: isDark ? Colors.grey[400] : Colors.grey[600],
                                      ),
                                      textAlign: TextAlign.center,
                                    ),
                                    const SizedBox(height: 12),
                                    Wrap(
                                      spacing: 8,
                                      runSpacing: 8,
                                      alignment: WrapAlignment.center,
                                      children: _quickPrompts.map((prompt) {
                                        return _buildPromptChip(
                                          prompt: prompt,
                                          isDark: isDark,
                                          onTap: () {
                                            _controller.text = prompt;
                                            _send(context, isAuthed);
                                          },
                                        );
                                      }).toList(),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          )
                        : ListView.builder(
                            controller: _scrollController,
                            padding: const EdgeInsets.all(12),
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
                                  isDark,
                                  isAuthed,
                                );
                              }

                              final isUser = m.role == 'user';
                              final isLastAssistant = !isUser &&
                                  i == ai.messages.length - 1 &&
                                  ai.isStreaming &&
                                  m.content.isEmpty;

                              final isEditing = _editingMessageIndex == i;
                              return Align(
                                alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
                                child: ConstrainedBox(
                                  constraints: BoxConstraints(
                                    maxWidth: MediaQuery.of(context).size.width * 0.85,
                                  ),
                                  child: Column(
                                    mainAxisSize: MainAxisSize.min,
                                    crossAxisAlignment: isUser ? CrossAxisAlignment.end : CrossAxisAlignment.start,
                                    children: [
                                      // Message bubble
                                      Container(
                                        margin: const EdgeInsets.symmetric(vertical: 6),
                                        padding: const EdgeInsets.all(12),
                                        decoration: BoxDecoration(
                                          color: isUser
                                              ? IOSColors.systemBlue
                                              : (isDark ? IOSColors.secondarySystemBackgroundDark : IOSColors.secondarySystemBackground),
                                          borderRadius: BorderRadius.circular(14),
                                          border: isEditing
                                              ? Border.all(
                                                  color: IOSColors.getSystemBlue(context),
                                                  width: 2,
                                                )
                                              : null,
                                        ),
                                        child: isUser
                                            ? Text(
                                                m.content,
                                                style: const TextStyle(color: Colors.white),
                                                softWrap: true,
                                                overflow: TextOverflow.visible,
                                              )
                                            : isLastAssistant
                                                ? (ai.agentSteps.isNotEmpty
                                                    ? AiChatAgentProgressPanel(
                                                        steps: ai.agentSteps,
                                                        isDark: isDark,
                                                      )
                                                    : _TypingIndicator(isDark: isDark))
                                                : Html(
                                                    data: _processHtmlForMobile(m.content),
                                                    style: {
                                                      "a": Style(
                                                        color: isDark
                                                            ? IOSColors.systemBlueDark
                                                            : IOSColors.systemBlue,
                                                        textDecoration: TextDecoration.underline,
                                                      ),
                                                      "body": Style(
                                                        margin: Margins.zero,
                                                        padding: HtmlPaddings.zero,
                                                        color: isDark
                                                            ? Colors.grey[200]
                                                            : Colors.grey[900],
                                                      ),
                                                      // Style tour trigger links with a button-like appearance
                                                      ".chatbot-tour-trigger": Style(
                                                        display: Display.inlineBlock,
                                                        padding: HtmlPaddings.symmetric(horizontal: 12, vertical: 8),
                                                        margin: Margins.only(top: 8),
                                                        backgroundColor: isDark
                                                            ? Color(0xFF1E3A5F)
                                                            : Color(0xFFE3F2FD),
                                                        border: Border.all(
                                                          color: isDark
                                                              ? IOSColors.systemBlueDark
                                                              : IOSColors.systemBlue,
                                                        ),
                                                      ),
                                                      // ChatGPT-style source document links: chip/pill appearance
                                                      ".source-doc-link": Style(
                                                        display: Display.inlineBlock,
                                                        padding: HtmlPaddings.symmetric(horizontal: 10, vertical: 6),
                                                        margin: Margins.only(top: 6, right: 6),
                                                        backgroundColor: isDark
                                                            ? Color(0xFF1A2E4A)
                                                            : Color(0xFFE8F4FD),
                                                        border: Border.all(
                                                          color: isDark
                                                              ? IOSColors.systemBlueDark
                                                              : IOSColors.systemBlue,
                                                          width: 1,
                                                        ),
                                                        color: isDark
                                                            ? IOSColors.systemBlueDark
                                                            : IOSColors.systemBlue,
                                                        textDecoration: TextDecoration.none,
                                                        fontSize: FontSize.small,
                                                      ),
                                                    },
                                                    onLinkTap: (url, attributes, element) {
                                                      _handleLinkTap(context, url);
                                                    },
                                                  ),
                                      ),
                                      if (!isUser &&
                                          !isLastAssistant &&
                                          ((m.confidence != null) ||
                                              (m.groundingScore != null) ||
                                              m.structuredPayloads.isNotEmpty))
                                        Padding(
                                          padding: const EdgeInsets.only(top: 2),
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
                                                            _scoreChipLabel('Confidence', m.confidence!),
                                                            style: const TextStyle(fontSize: 11),
                                                          ),
                                                          visualDensity: VisualDensity.compact,
                                                          materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                                                        ),
                                                      if (m.groundingScore != null)
                                                        Chip(
                                                          label: Text(
                                                            _scoreChipLabel('Grounding', m.groundingScore!),
                                                            style: const TextStyle(fontSize: 11),
                                                          ),
                                                          visualDensity: VisualDensity.compact,
                                                          materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                                                        ),
                                                    ],
                                                  ),
                                                ),
                                              AiChatStructuredPayloadsColumn(
                                                payloads: m.structuredPayloads,
                                                isDark: isDark,
                                              ),
                                            ],
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
                                                  size: 16,
                                                  color: isDark ? (Colors.grey[400] ?? Colors.grey) : (Colors.grey[700] ?? Colors.grey),
                                                  onTap: () => _copyToClipboard(context, m.content, i),
                                                  tooltip: 'Copy',
                                                ),
                                                if (_copiedMessageIndex == i)
                                                  Padding(
                                                    padding: const EdgeInsets.only(left: 4),
                                                    child: AnimatedOpacity(
                                                      opacity: 1.0,
                                                      duration: const Duration(milliseconds: 300),
                                                      child: Text(
                                                        'Copied!',
                                                        style: TextStyle(
                                                          fontSize: 12,
                                                          color: isDark ? Colors.grey[400] : Colors.grey[600],
                                                        ),
                                                      ),
                                                    ),
                                                  ),
                                                const SizedBox(width: 8),
                                                _buildActionIcon(
                                                  icon: Icons.edit,
                                                  size: 16,
                                                  color: isDark ? (Colors.grey[400] ?? Colors.grey) : (Colors.grey[700] ?? Colors.grey),
                                                  onTap: () => _showEditMessageDialog(context, i, m.content, isDark),
                                                  tooltip: 'Edit',
                                                ),
                                              ] else ...[
                                                _buildActionIcon(
                                                  icon: Icons.copy,
                                                  size: 16,
                                                  color: isDark ? (Colors.grey[400] ?? Colors.grey) : (Colors.grey[600] ?? Colors.grey),
                                                  onTap: () => _copyToClipboard(context, m.content, i),
                                                  tooltip: 'Copy',
                                                ),
                                                if (_copiedMessageIndex == i)
                                                  Padding(
                                                    padding: const EdgeInsets.only(left: 4),
                                                    child: AnimatedOpacity(
                                                      opacity: 1.0,
                                                      duration: const Duration(milliseconds: 300),
                                                      child: Text(
                                                        'Copied!',
                                                        style: TextStyle(
                                                          fontSize: 12,
                                                          color: isDark ? Colors.grey[400] : Colors.grey[600],
                                                        ),
                                                      ),
                                                    ),
                                                  ),
                                                if (isAuthed && m.traceId != null) ...[
                                                  const SizedBox(width: 8),
                                                  _buildActionIcon(
                                                    icon: m.userRating == 'like' ? Icons.thumb_up : Icons.thumb_up_outlined,
                                                    size: 16,
                                                    color: m.userRating == 'like'
                                                        ? IOSColors.getSystemBlue(context)
                                                        : (isDark ? (Colors.grey[400] ?? Colors.grey) : (Colors.grey[600] ?? Colors.grey)),
                                                    onTap: () => context.read<AiChatProvider>().submitMessageFeedback(i, 'like'),
                                                    tooltip: 'Helpful',
                                                  ),
                                                  const SizedBox(width: 4),
                                                  _buildActionIcon(
                                                    icon: m.userRating == 'dislike' ? Icons.thumb_down : Icons.thumb_down_outlined,
                                                    size: 16,
                                                    color: m.userRating == 'dislike'
                                                        ? IOSColors.getSystemBlue(context)
                                                        : (isDark ? (Colors.grey[400] ?? Colors.grey) : (Colors.grey[600] ?? Colors.grey)),
                                                    onTap: () => context.read<AiChatProvider>().submitMessageFeedback(i, 'dislike'),
                                                    tooltip: 'Not helpful',
                                                  ),
                                                ],
                                              ],
                                            ],
                                          ),
                                        ),
                                    ],
                                  ),
                                ),
                              );
                            },
                          ),
                  ),
                ),
                Padding(
                  padding: EdgeInsets.only(bottom: MediaQuery.of(context).viewInsets.bottom),
                  child: SafeArea(
                    top: false,
                    child: Container(
                      padding: const EdgeInsets.fromLTRB(12, 8, 12, 12),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          IconButton(
                            icon: const Icon(Icons.tune),
                            tooltip: 'Configure data sources',
                            onPressed: ai.isStreaming ? null : () => _showSourcesSheet(context, ai, isDark),
                          ),
                          Expanded(
                            child: TextField(
                              controller: _controller,
                              focusNode: _inputFocusNode,
                              minLines: 1,
                              maxLines: 6,
                              maxLength: 4000,
                              buildCounter: (context, {required currentLength, required isFocused, maxLength}) => null,
                              textInputAction: TextInputAction.send,
                              onSubmitted: (_) => _send(context, isAuthed),
                              inputFormatters: [
                                _EnterToSendFormatter(
                                  onEnterPressed: () => _send(context, isAuthed),
                                ),
                              ],
                              decoration: InputDecoration(
                                hintText: _editingMessageIndex != null ? 'Edit message...' : 'Ask anything',
                                border: const OutlineInputBorder(),
                                suffixIcon: _editingMessageIndex != null
                                    ? IconButton(
                                        icon: const Icon(Icons.close, size: 20),
                                        onPressed: () {
                                          setState(() {
                                            _editingMessageIndex = null;
                                            _controller.clear();
                                          });
                                        },
                                        tooltip: 'Cancel edit',
                                      )
                                    : null,
                              ),
                            ),
                          ),
                          const SizedBox(width: 4),
                          if (ai.isStreaming || ai.inflightRestoreActive)
                            IconButton(
                              icon: const Icon(Icons.stop),
                              tooltip: 'Stop',
                              onPressed: () => context.read<AiChatProvider>().stopStreaming(isAuthenticated: isAuthed),
                            )
                          else if (ai.errorType == 'quota_exceeded' && ai.failedMessage != null)
                            IconButton(
                              icon: const Icon(Icons.refresh),
                              tooltip: 'Retry',
                              onPressed: () => _retry(context, isAuthed),
                            )
                          else
                            IconButton(
                              icon: const Icon(Icons.send),
                              onPressed: () => _send(context, isAuthed),
                            ),
                        ],
                      ),
                    ),
                  ),
                ),
                // Disclaimer aligned with chat_immersive.html
                Padding(
                  padding: const EdgeInsets.only(top: 4, left: 12, right: 12),
                  child: Text(
                    'AI can make mistakes. Check important information.',
                    style: TextStyle(
                      fontSize: 11,
                      color: isDark ? Colors.grey[500] : Colors.grey[600],
                    ),
                  ),
                ),
              ],
            );
          },
        ),
      ),
      bottomNavigationBar: AppBottomNavigationBar(
        currentIndex: 2, // Home index
      ),
    );
  }

  Future<void> _send(BuildContext context, bool isAuthenticated) async {
    final msg = _controller.text.trim();
    if (msg.isEmpty) return;

    final provider = context.read<AiChatProvider>();
    if (!provider.policyAcknowledged) {
      _showPolicyRequiredSnack(context);
      return;
    }
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
      if (mounted) {
        final ai = context.read<AiChatProvider>();
        if (ai.errorType == 'quota_exceeded' && ai.failedMessage != null && _controller.text.isEmpty) {
          _controller.text = ai.failedMessage!;
        }
      }
    });
  }

  void _showEditMessageDialog(BuildContext context, int messageIndex, String messageContent, bool isDark) {
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
    final provider = context.read<AiChatProvider>();
    if (provider.failedMessage != null) {
      // Restore the message to the controller if it's not already there
      if (_controller.text != provider.failedMessage) {
        _controller.text = provider.failedMessage!;
      }
      await provider.retryFailedMessage(isAuthenticated: isAuthenticated);
    }
  }

  Widget _buildDrawer(BuildContext context, AuthProvider auth, AiChatProvider ai, bool isAuthed) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;

    // Filter conversations based on search query
    final filteredConversations = _searchQuery.isEmpty
        ? ai.conversations
        : ai.conversations.where((c) {
            final title = (c.title ?? '').toLowerCase();
            return title.contains(_searchQuery.toLowerCase());
          }).toList();

    return Drawer(
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.zero,
      ),
      child: SafeArea(
        child: Column(
          children: [
            // Title
            Container(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 16),
            decoration: BoxDecoration(
              border: Border(
                bottom: BorderSide(
                  color: isDark ? Colors.grey[800]! : Colors.grey[300]!,
                  width: 1,
                ),
              ),
            ),
            child: Row(
              children: [
                Text(
                  'Conversations',
                  style: TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w600,
                    color: isDark ? Colors.grey[200] : Colors.grey[900],
                  ),
                ),
              ],
            ),
          ),
          // Search Bar with New Chat Icon
          if (ai.conversations.isNotEmpty)
            Container(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
              decoration: BoxDecoration(
                border: Border(
                  bottom: BorderSide(
                    color: isDark ? Colors.grey[800]! : Colors.grey[300]!,
                    width: 1,
                  ),
                ),
              ),
              child: Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: _searchController,
                      focusNode: _searchFocusNode,
                      autofocus: false,
                      enableInteractiveSelection: true,
                      onTap: () {
                        // Ensure the search field gets focus when tapped
                        _searchFocusNode.requestFocus();
                      },
                      onChanged: (value) {
                        setState(() {
                          _searchQuery = value;
                        });
                      },
                      decoration: InputDecoration(
                        hintText: 'Search conversations',
                        prefixIcon: Icon(
                          Icons.search,
                          size: 18,
                          color: isDark ? Colors.grey[400] : Colors.grey[600],
                        ),
                        suffixIcon: _searchQuery.isNotEmpty
                            ? IconButton(
                                icon: Icon(
                                  Icons.clear,
                                  size: 18,
                                  color: isDark ? Colors.grey[400] : Colors.grey[600],
                                ),
                                onPressed: () {
                                  _searchController.clear();
                                  setState(() {
                                    _searchQuery = '';
                                  });
                                },
                              )
                            : null,
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(8),
                          borderSide: BorderSide(
                            color: isDark ? Colors.grey[700]! : Colors.grey[300]!,
                          ),
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(8),
                          borderSide: BorderSide(
                            color: isDark ? Colors.grey[700]! : Colors.grey[300]!,
                          ),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(8),
                          borderSide: BorderSide(
                            color: IOSColors.getSystemBlue(context),
                            width: 2,
                          ),
                        ),
                        filled: true,
                        fillColor: isDark ? Colors.grey[850] : Colors.grey[100],
                        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                        isDense: true,
                      ),
                      style: TextStyle(
                        fontSize: 13,
                        color: isDark ? Colors.grey[200] : Colors.grey[900],
                      ),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Material(
                    color: Colors.transparent,
                    child: InkWell(
                      onTap: () {
                        Navigator.pop(context);
                        context.read<AiChatProvider>().startNewConversation();
                      },
                      borderRadius: BorderRadius.circular(8),
                      child: Container(
                        padding: const EdgeInsets.all(8),
                        child: Icon(
                          Icons.chat_bubble_outline,
                          size: 20,
                          color: IOSColors.getSystemBlue(context),
                        ),
                      ),
                    ),
                  ),
                ],
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
                                  color: isDark ? Colors.grey[600] : Colors.grey[400],
                                ),
                                const SizedBox(height: 16),
                                Text(
                                  isAuthed
                                      ? 'No conversations yet.\nStart a new chat!'
                                      : 'No conversations yet.\nStart a new chat (offline).',
                                  style: TextStyle(
                                    color: isDark ? Colors.grey[400] : Colors.grey[600],
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
                                      color: isDark ? Colors.grey[600] : Colors.grey[400],
                                    ),
                                    const SizedBox(height: 16),
                                    Text(
                                      'No conversations found',
                                      style: TextStyle(
                                        color: isDark ? Colors.grey[400] : Colors.grey[600],
                                        fontSize: 14,
                                      ),
                                      textAlign: TextAlign.center,
                                    ),
                                  ],
                                ),
                              ),
                            )
                          : ListView.builder(
                              padding: const EdgeInsets.symmetric(vertical: 8),
                              itemCount: filteredConversations.length,
                              itemBuilder: (context, i) {
                                final c = filteredConversations[i];
                                final isSelected = ai.conversationId == c.id;
                                return _buildConversationTile(
                                  context,
                                  c,
                                  isSelected,
                                  isAuthed,
                                  isDark,
                                );
                              },
                            ),
            ),
          // Actions Section
          if (ai.conversations.isNotEmpty)
            Container(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
              decoration: BoxDecoration(
                border: Border(
                  top: BorderSide(
                    color: isDark ? Colors.grey[800]! : Colors.grey[300]!,
                    width: 1,
                  ),
                ),
              ),
              child: Column(
                children: [
                  if (isAuthed && ai.conversationId != null && ai.conversationId!.isNotEmpty)
                    Material(
                      color: Colors.transparent,
                      child: InkWell(
                        onTap: () async {
                          Navigator.pop(context);
                          await _exportCurrentConversation(context, ai);
                        },
                        borderRadius: BorderRadius.circular(10),
                        child: Container(
                          width: double.infinity,
                          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                          child: Row(
                            children: [
                              Icon(
                                Icons.file_download_outlined,
                                size: 20,
                                color: IOSColors.getSystemBlue(context),
                              ),
                              const SizedBox(width: 12),
                              Text(
                                'Export conversation (JSON)',
                                style: TextStyle(
                                  fontSize: 16,
                                  color: isDark ? Colors.grey[200] : Colors.grey[900],
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  Material(
                    color: Colors.transparent,
                    child: InkWell(
                      onTap: () async {
                        final shouldClear = await showDialog<bool>(
                          context: context,
                          builder: (context) => AlertDialog(
                            title: Text(
                              'Clear all conversations',
                              style: TextStyle(
                                color: isDark ? Colors.grey[200] : Colors.grey[900],
                              ),
                            ),
                            content: Text(
                              'Are you sure you want to delete all conversations? This action cannot be undone.',
                              style: TextStyle(
                                color: isDark ? Colors.grey[300] : Colors.grey[700],
                              ),
                            ),
                            backgroundColor: isDark ? Colors.grey[850] : Colors.white,
                            actions: [
                              TextButton(
                                onPressed: () => Navigator.pop(context, false),
                                child: Text(
                                  'Cancel',
                                  style: TextStyle(
                                    color: isDark ? Colors.grey[300] : Colors.grey[700],
                                  ),
                                ),
                              ),
                              TextButton(
                                onPressed: () => Navigator.pop(context, true),
                                style: TextButton.styleFrom(
                                  foregroundColor: isDark ? Colors.red.shade400 : Colors.red,
                                ),
                                child: const Text('Clear All'),
                              ),
                            ],
                          ),
                        );
                        if (shouldClear == true && context.mounted) {
                          Navigator.pop(context);
                          await context.read<AiChatProvider>().clearAllConversations(isAuthenticated: isAuthed);
                          // Clear search
                          _searchController.clear();
                          setState(() {
                            _searchQuery = '';
                          });
                        }
                      },
                      borderRadius: BorderRadius.circular(10),
                      child: Container(
                        width: double.infinity,
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                        child: Row(
                          children: [
                            Icon(
                              Icons.delete_sweep_outlined,
                              size: 20,
                              color: isDark ? Colors.red.shade400 : Colors.red,
                            ),
                            const SizedBox(width: 12),
                            Text(
                              'Clear all conversations',
                              style: TextStyle(
                                fontSize: 16,
                                color: isDark ? Colors.red.shade400 : Colors.red,
                                fontWeight: FontWeight.w500,
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
          // Help/About Section
          Container(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
            decoration: BoxDecoration(
              border: Border(
                top: BorderSide(
                  color: isDark ? Colors.grey[800]! : Colors.grey[300]!,
                  width: 1,
                ),
              ),
            ),
            child: Material(
              color: Colors.transparent,
              child: InkWell(
                onTap: () {
                  Navigator.pop(context);
                  _showHelpDialog(context, isDark);
                },
                borderRadius: BorderRadius.circular(10),
                child: Container(
                  width: double.infinity,
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  child: Row(
                    children: [
                      Icon(
                        Icons.help_outline,
                        size: 20,
                        color: isDark ? Colors.grey[400] : Colors.grey[600],
                      ),
                      const SizedBox(width: 12),
                      Text(
                        'Help & About',
                        style: TextStyle(
                          fontSize: 16,
                          color: isDark ? Colors.grey[300] : Colors.grey[700],
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
          ],
        ),
      ),
    );
  }

  Widget _buildConversationTile(
    BuildContext context,
    AiConversationSummary conversation,
    bool isSelected,
    bool isAuthed,
    bool isDark,
  ) {
    final title = conversation.title ?? 'New Chat';
    final truncatedTitle = title.length > 50 ? '${title.substring(0, 50)}...' : title;

    return InkWell(
      onTap: () async {
        Navigator.pop(context);
        await context.read<AiChatProvider>().openConversation(
              isAuthenticated: isAuthed,
              conversationId: conversation.id,
            );
      },
      child: Container(
        margin: const EdgeInsets.symmetric(horizontal: 8, vertical: 1),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: isSelected
              ? (isDark ? Colors.grey[800] : Colors.grey[200])
              : Colors.transparent,
        ),
        child: Row(
          children: [
            Expanded(
              child: Row(
                children: [
                  Icon(
                    Icons.chat_bubble_outline,
                    size: 16,
                    color: isDark ? Colors.grey[400] : Colors.grey[600],
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      truncatedTitle,
                      style: TextStyle(
                        fontSize: 13,
                        color: isDark ? Colors.grey[200] : Colors.grey[900],
                        fontWeight: isSelected ? FontWeight.w500 : FontWeight.normal,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
            ),
            IconButton(
              icon: Icon(
                Icons.delete_outline,
                size: 18,
                color: isDark ? Colors.grey[400] : Colors.grey[600],
              ),
              onPressed: () async {
                // Copy aligned with chat-immersive.js / showDangerConfirmation
                final shouldDelete = await showDialog<bool>(
                  context: context,
                  builder: (context) => AlertDialog(
                    title: Text(
                      'Delete conversation?',
                      style: TextStyle(
                        color: isDark ? Colors.grey[200] : Colors.grey[900],
                      ),
                    ),
                    content: Text(
                      'Delete this conversation? This cannot be undone.',
                      style: TextStyle(
                        color: isDark ? Colors.grey[300] : Colors.grey[700],
                      ),
                    ),
                    backgroundColor: isDark ? Colors.grey[850] : Colors.white,
                    actions: [
                      TextButton(
                        onPressed: () => Navigator.pop(context, false),
                        child: Text(
                          'Cancel',
                          style: TextStyle(
                            color: isDark ? Colors.grey[300] : Colors.grey[700],
                          ),
                        ),
                      ),
                      TextButton(
                        onPressed: () => Navigator.pop(context, true),
                        style: TextButton.styleFrom(
                          foregroundColor: isDark ? Colors.red.shade400 : Colors.red,
                        ),
                        child: const Text('Delete'),
                      ),
                    ],
                  ),
                );
                if (shouldDelete == true && context.mounted) {
                  await context.read<AiChatProvider>().deleteConversation(
                        conversation.id,
                        isAuthenticated: isAuthed,
                      );
                }
              },
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(),
              tooltip: 'Delete',
            ),
          ],
        ),
      ),
    );
  }

  void _showHelpDialog(BuildContext context, bool isDark) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(
          'AI Assistant Help',
          style: TextStyle(
            color: isDark ? Colors.grey[200] : Colors.grey[900],
          ),
        ),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'About',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                  color: isDark ? Colors.grey[200] : Colors.grey[900],
                ),
              ),
              const SizedBox(height: 8),
              Text(
                'The AI Assistant helps you find information and answer questions about the IFRC Network Databank.',
                style: TextStyle(
                  fontSize: 14,
                  color: isDark ? Colors.grey[300] : Colors.grey[700],
                ),
              ),
              const SizedBox(height: 16),
              Text(
                'Features',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                  color: isDark ? Colors.grey[200] : Colors.grey[900],
                ),
              ),
              const SizedBox(height: 8),
              _buildHelpItem(
                isDark,
                '• Ask questions about assignments, resources, and more',
              ),
              _buildHelpItem(
                isDark,
                '• Get help navigating the app',
              ),
              _buildHelpItem(
                isDark,
                '• Search through your conversation history',
              ),
              _buildHelpItem(
                isDark,
                '• All conversations are saved when you\'re logged in',
              ),
              const SizedBox(height: 16),
              Text(
                'Tips',
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.bold,
                  color: isDark ? Colors.grey[200] : Colors.grey[900],
                ),
              ),
              const SizedBox(height: 8),
              _buildHelpItem(
                isDark,
                '• Be specific in your questions for better results',
              ),
              _buildHelpItem(
                isDark,
                '• Tap on links in responses to navigate to relevant pages',
              ),
              _buildHelpItem(
                isDark,
                '• Use the search bar to quickly find past conversations',
              ),
            ],
          ),
        ),
        backgroundColor: isDark ? Colors.grey[850] : Colors.white,
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text(
              'Got it',
              style: TextStyle(
                color: IOSColors.getSystemBlue(context),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildHelpItem(bool isDark, String text) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Text(
        text,
        style: TextStyle(
          fontSize: 14,
          color: isDark ? Colors.grey[300] : Colors.grey[700],
        ),
      ),
    );
  }

  Widget _buildActionIcon({
    required IconData icon,
    required double size,
    required Color color,
    required VoidCallback onTap,
    required String tooltip,
  }) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(4),
        child: Padding(
          padding: const EdgeInsets.all(4),
          child: Icon(
            icon,
            size: size,
            color: color,
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
    bool isDark,
    bool isAuthed,
  ) {
    final ai = context.read<AiChatProvider>();
    return Align(
      alignment: Alignment.centerLeft,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.85,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              margin: const EdgeInsets.symmetric(vertical: 6),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: isDark
                    ? Colors.red.shade900.withOpacity(0.3)
                    : Colors.red.shade50,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(
                  color: isDark ? Colors.red.shade700 : Colors.red.shade300,
                  width: 1,
                ),
              ),
              child: Row(
                children: [
                  Icon(
                    Icons.error_outline,
                    size: 18,
                    color: isDark ? Colors.red.shade400 : Colors.red.shade700,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      errorMessage,
                      style: TextStyle(
                        color: isDark ? Colors.red.shade300 : Colors.red.shade900,
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
                    size: 16,
                    color: isDark ? (Colors.grey[400] ?? Colors.grey) : (Colors.grey[600] ?? Colors.grey),
                    onTap: () {
                      final provider = context.read<AiChatProvider>();
                      // For quota errors, use retryFailedMessage which handles the stored failed message
                      if (ai.errorType == 'quota_exceeded' && ai.failedMessage != null) {
                        provider.retryFailedMessage(isAuthenticated: isAuthed);
                      } else {
                        // For other errors, retry the last user message
                        provider.retryLastMessage(isAuthenticated: isAuthed);
                      }
                    },
                    tooltip: 'Retry',
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
    required String prompt,
    required bool isDark,
    required VoidCallback onTap,
  }) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(16),
        child: Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
          decoration: BoxDecoration(
            color: isDark
                ? Colors.grey[800]?.withOpacity(0.5)
                : Colors.grey[200]?.withOpacity(0.7),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
              color: isDark
                  ? (Colors.grey[700] ?? Colors.grey)
                  : (Colors.grey[300] ?? Colors.grey),
              width: 1,
            ),
          ),
          child: Text(
            prompt,
            style: TextStyle(
              fontSize: 12,
              color: isDark ? Colors.grey[200] : Colors.grey[800],
            ),
          ),
        ),
      ),
    );
  }
}

class _TypingIndicator extends StatefulWidget {
  final bool isDark;

  const _TypingIndicator({required this.isDark});

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
    for (var controller in _controllers) {
      controller.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: List.generate(3, (index) {
        return AnimatedBuilder(
          animation: _animations[index],
          builder: (context, child) {
            return Opacity(
              opacity: 0.3 + (_animations[index].value * 0.7),
              child: Container(
                margin: const EdgeInsets.symmetric(horizontal: 3),
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  color: widget.isDark ? Colors.grey[400] : Colors.grey[600],
                  shape: BoxShape.circle,
                ),
              ),
            );
          },
        );
      }),
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
