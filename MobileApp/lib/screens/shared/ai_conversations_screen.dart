import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../providers/shared/ai_chat_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../config/routes.dart';

class AiConversationsScreen extends StatefulWidget {
  const AiConversationsScreen({super.key});

  @override
  State<AiConversationsScreen> createState() => _AiConversationsScreenState();
}

class _AiConversationsScreenState extends State<AiConversationsScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _load());
  }

  Future<void> _load() async {
    final auth = context.read<AuthProvider>();
    await context.read<AiChatProvider>().ensureTokenIfLoggedIn(isAuthenticated: auth.isAuthenticated);
    await context.read<AiChatProvider>().loadConversations(isAuthenticated: auth.isAuthenticated);
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    final ai = context.watch<AiChatProvider>();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Chats'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _load,
          ),
        ],
      ),
      body: !auth.isAuthenticated
          ? const Center(
              child: Text('Log in to see your saved chats.'),
            )
          : ai.isLoading
              ? const Center(child: CircularProgressIndicator())
              : ListView.separated(
                  itemCount: ai.conversations.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (context, i) {
                    final c = ai.conversations[i];
                    return ListTile(
                      title: Text(c.title ?? 'Chat'),
                      subtitle: Text(c.lastMessageAt?.toLocal().toString() ?? ''),
                      onTap: () async {
                        await context.read<AiChatProvider>().openConversation(
                              isAuthenticated: auth.isAuthenticated,
                              conversationId: c.id,
                            );
                        if (!context.mounted) return;
                        Navigator.of(context).pushNamed(AppRoutes.aiChat);
                      },
                    );
                  },
                ),
      floatingActionButton: FloatingActionButton(
        onPressed: () {
          context.read<AiChatProvider>().startNewConversation();
          Navigator.of(context).pushNamed(AppRoutes.aiChat);
        },
        child: const Icon(Icons.add),
      ),
    );
  }
}
