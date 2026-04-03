import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../providers/public/leaderboard_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../widgets/app_bar.dart';
import '../../utils/theme_extensions.dart';
import '../../utils/constants.dart';
import '../../l10n/app_localizations.dart';

class LeaderboardScreen extends StatefulWidget {
  const LeaderboardScreen({super.key});

  @override
  State<LeaderboardScreen> createState() => _LeaderboardScreenState();
}

class _LeaderboardScreenState extends State<LeaderboardScreen> {
  @override
  void initState() {
    super.initState();
    // Load leaderboard when screen opens
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final provider = Provider.of<LeaderboardProvider>(context, listen: false);
      provider.loadLeaderboard();
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final localizations = AppLocalizations.of(context)!;

    return Scaffold(
      appBar: AppAppBar(
        title: localizations.quizGameLeaderboard,
      ),
      body: Consumer<LeaderboardProvider>(
        builder: (context, provider, child) {
          if (provider.isLoading) {
            return Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  CircularProgressIndicator(
                    valueColor: AlwaysStoppedAnimation<Color>(
                      theme.colorScheme.primary,
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    localizations.quizGameLoadingLeaderboard,
                    style: theme.textTheme.bodyLarge?.copyWith(
                      color: context.textSecondaryColor,
                    ),
                  ),
                ],
              ),
            );
          }

          if (provider.error != null) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(
                      Icons.error_outline,
                      size: 64,
                      color: theme.colorScheme.error,
                    ),
                    const SizedBox(height: 16),
                    Text(
                      provider.error!,
                      style: theme.textTheme.bodyLarge?.copyWith(
                        color: theme.colorScheme.error,
                      ),
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 24),
                    ElevatedButton(
                      onPressed: () => provider.refresh(),
                      child: Text(localizations.retry),
                    ),
                  ],
                ),
              ),
            );
          }

          if (provider.leaderboard.isEmpty) {
            return Center(
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(
                      Icons.emoji_events_outlined,
                      size: 64,
                      color: context.textSecondaryColor,
                    ),
                    const SizedBox(height: 16),
                    Text(
                      localizations.quizGameNoLeaderboardData,
                      style: theme.textTheme.bodyLarge?.copyWith(
                        color: context.textSecondaryColor,
                      ),
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),
            );
          }

          final currentUser = Provider.of<AuthProvider>(context, listen: false).user;
          final currentUserEmail = currentUser?.email;

          return RefreshIndicator(
            onRefresh: () => provider.refresh(),
            child: SingleChildScrollView(
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Header
                  Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        colors: [
                          theme.colorScheme.primary,
                          theme.colorScheme.secondary,
                        ],
                      ),
                      borderRadius: BorderRadius.circular(12),
                      boxShadow: [
                        BoxShadow(
                          color: theme.colorScheme.primary.withOpacity(0.3),
                          blurRadius: 8,
                          spreadRadius: 2,
                        ),
                      ],
                    ),
                    child: Column(
                      children: [
                        Icon(
                          Icons.emoji_events,
                          size: 48,
                          color: Colors.white,
                        ),
                        const SizedBox(height: 8),
                        Text(
                          localizations.quizGameTopPlayers,
                          style: theme.textTheme.titleLarge?.copyWith(
                            color: Colors.white,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 24),
                  // Leaderboard list
                  ...provider.leaderboard.asMap().entries.map((entry) {
                    final index = entry.key;
                    final player = entry.value;
                    final isCurrentUser = currentUserEmail == player.email;
                    final isTopThree = index < 3;

                    return _buildLeaderboardItem(
                      context,
                      theme,
                      player,
                      index + 1,
                      isCurrentUser,
                      isTopThree,
                    );
                  }),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildLeaderboardItem(
    BuildContext context,
    ThemeData theme,
    LeaderboardEntry player,
    int rank,
    bool isCurrentUser,
    bool isTopThree,
  ) {
    final localizations = AppLocalizations.of(context)!;

    // Medal icons for top 3
    IconData? medalIcon;
    Color? medalColor;
    if (rank == 1) {
      medalIcon = Icons.emoji_events;
      medalColor = Colors.amber;
    } else if (rank == 2) {
      medalIcon = Icons.emoji_events;
      medalColor = Colors.grey.shade400;
    } else if (rank == 3) {
      medalIcon = Icons.emoji_events;
      medalColor = Colors.brown.shade400;
    }

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isCurrentUser
            ? theme.colorScheme.primaryContainer.withOpacity(0.3)
            : theme.cardColor,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(
          color: isCurrentUser
              ? theme.colorScheme.primary
              : theme.colorScheme.outline.withOpacity(0.2),
          width: isCurrentUser ? 2 : 1,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.05),
            blurRadius: 4,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Row(
        children: [
          // Rank
          Container(
            width: 50,
            height: 50,
            decoration: BoxDecoration(
              color: isTopThree
                  ? medalColor?.withOpacity(0.2)
                  : theme.colorScheme.surfaceContainerHighest,
              shape: BoxShape.circle,
            ),
            child: Center(
              child: medalIcon != null
                  ? Icon(
                      medalIcon,
                      color: medalColor,
                      size: 28,
                    )
                  : Text(
                      '#$rank',
                      style: theme.textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: isTopThree
                            ? medalColor
                            : context.textColor,
                      ),
                    ),
            ),
          ),
          const SizedBox(width: 16),
          // Name and email
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        player.name,
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                          color: context.textColor,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                    if (isCurrentUser)
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 4,
                        ),
                        decoration: BoxDecoration(
                          color: theme.colorScheme.primary,
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Text(
                          localizations.quizGameYou,
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: Colors.white,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  player.email,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: context.textSecondaryColor,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
          const SizedBox(width: 16),
          // Score
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            decoration: BoxDecoration(
              color: theme.colorScheme.primaryContainer,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Column(
              children: [
                Text(
                  '${player.score}',
                  style: theme.textTheme.titleLarge?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: theme.colorScheme.onPrimaryContainer,
                  ),
                ),
                Text(
                  localizations.quizGamePoints,
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: theme.colorScheme.onPrimaryContainer.withOpacity(0.7),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
