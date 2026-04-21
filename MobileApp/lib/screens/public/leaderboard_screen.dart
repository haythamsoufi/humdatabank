import 'dart:math' show max;
import 'dart:ui' show ImageFilter;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../l10n/app_localizations.dart';
import '../../models/public/leaderboard_entry.dart';
import '../../providers/public/leaderboard_provider.dart';
import '../../providers/shared/auth_provider.dart';
import '../../utils/theme_extensions.dart';

// ---------------------------------------------------------------------------
// Screen
// ---------------------------------------------------------------------------

class LeaderboardScreen extends StatefulWidget {
  const LeaderboardScreen({super.key});

  @override
  State<LeaderboardScreen> createState() => _LeaderboardScreenState();
}

class _LeaderboardScreenState extends State<LeaderboardScreen>
    with TickerProviderStateMixin {
  late final AnimationController _headerController;
  late final AnimationController _listController;
  late final Animation<double> _headerFade;
  late final Animation<double> _headerScale;

  @override
  void initState() {
    super.initState();

    _headerController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 600),
    );
    _listController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    );
    _headerFade = CurvedAnimation(
      parent: _headerController,
      curve: Curves.easeOut,
    );
    _headerScale = Tween<double>(begin: 0.88, end: 1.0).animate(
      CurvedAnimation(parent: _headerController, curve: Curves.easeOutBack),
    );

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final auth = Provider.of<AuthProvider>(context, listen: false);
      if (!auth.isAuthenticated) {
        if (context.mounted) Navigator.of(context).maybePop();
        return;
      }
      Provider.of<LeaderboardProvider>(context, listen: false)
          .loadLeaderboard()
          .then((_) {
        if (mounted) {
          _headerController.forward();
          Future.delayed(
            const Duration(milliseconds: 200),
            () {
              if (mounted) _listController.forward();
            },
          );
        }
      });
    });
  }

  @override
  void dispose() {
    _headerController.dispose();
    _listController.dispose();
    super.dispose();
  }

  // ── helpers ──────────────────────────────────────────────────────────────

  static Color _avatarColor(String name) {
    final palette = [
      const Color(0xFF6366F1),
      const Color(0xFF8B5CF6),
      const Color(0xFF06B6D4),
      const Color(0xFF10B981),
      const Color(0xFFF59E0B),
      const Color(0xFFEF4444),
      const Color(0xFFEC4899),
      const Color(0xFF3B82F6),
      const Color(0xFF14B8A6),
      const Color(0xFFF97316),
    ];
    final idx = name.isEmpty ? 0 : name.codeUnitAt(0) % palette.length;
    return palette[idx];
  }

  static String _initials(String name) {
    final parts = name.trim().split(RegExp(r'\s+'));
    if (parts.isEmpty || parts.first.isEmpty) return '?';
    if (parts.length == 1) return parts.first[0].toUpperCase();
    return (parts.first[0] + parts.last[0]).toUpperCase();
  }

  // ── build ─────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final loc = AppLocalizations.of(context)!;

    return Scaffold(
      extendBodyBehindAppBar: true,
      backgroundColor: theme.scaffoldBackgroundColor,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        scrolledUnderElevation: 0,
        leading: Padding(
          padding: const EdgeInsets.all(6),
          child: _GlassButton(
            onTap: () => Navigator.of(context).maybePop(),
            child: const Icon(Icons.arrow_back_rounded, size: 20),
          ),
        ),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 8),
            child: _GlassButton(
              onTap: () =>
                  Provider.of<LeaderboardProvider>(context, listen: false)
                      .refresh(),
              child: const Icon(Icons.refresh_rounded, size: 20),
            ),
          ),
        ],
      ),
      body: Consumer<LeaderboardProvider>(
        builder: (context, provider, _) {
          if (provider.isLoading) {
            return _LoadingView(theme: theme, loc: loc);
          }
          if (provider.error != null) {
            return _ErrorView(
              theme: theme,
              loc: loc,
              error: provider.error!,
              onRetry: provider.refresh,
            );
          }
          if (provider.leaderboard.isEmpty) {
            return _EmptyView(theme: theme, loc: loc);
          }

          final currentEmail =
              Provider.of<AuthProvider>(context, listen: false).user?.email;
          final entries = provider.leaderboard;
          final top3 = entries.take(3).toList();
          final rest = entries.skip(3).toList();
          final maxScore =
              entries.isEmpty ? 1 : max(1, entries.first.score);

          return RefreshIndicator(
            onRefresh: provider.refresh,
            child: CustomScrollView(
              physics: const AlwaysScrollableScrollPhysics(),
              slivers: [
                // ── Hero header ──────────────────────────────────────────
                SliverToBoxAdapter(
                  child: FadeTransition(
                    opacity: _headerFade,
                    child: ScaleTransition(
                      scale: _headerScale,
                      child: _HeroHeader(
                        theme: theme,
                        loc: loc,
                        totalPlayers: entries.length,
                        top3: top3,
                        currentEmail: currentEmail,
                        avatarColor: _avatarColor,
                        initials: _initials,
                      ),
                    ),
                  ),
                ),

                // ── Rest of list ─────────────────────────────────────────
                if (rest.isNotEmpty) ...[
                  SliverPadding(
                    padding: const EdgeInsets.fromLTRB(16, 16, 16, 0),
                    sliver: SliverToBoxAdapter(
                      child: Text(
                        '#4 — #${entries.length}',
                        style: theme.textTheme.labelSmall?.copyWith(
                          color: context.textSecondaryColor,
                          fontWeight: FontWeight.w600,
                          letterSpacing: 1,
                        ),
                      ),
                    ),
                  ),
                  SliverPadding(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 24),
                    sliver: SliverList(
                      delegate: SliverChildBuilderDelegate(
                        (context, i) {
                          final entry = rest[i];
                          final delay = Duration(
                            milliseconds: 60 * i,
                          );
                          return _AnimatedListEntry(
                            delay: delay,
                            controller: _listController,
                            child: _RankRow(
                              theme: theme,
                              loc: loc,
                              entry: entry,
                              rank: entry.rank,
                              isCurrentUser:
                                  currentEmail == entry.email,
                              maxScore: maxScore,
                              avatarColor: _avatarColor(entry.name),
                              initials: _initials(entry.name),
                            ),
                          );
                        },
                        childCount: rest.length,
                      ),
                    ),
                  ),
                ] else
                  const SliverToBoxAdapter(
                    child: SizedBox(height: 24),
                  ),
              ],
            ),
          );
        },
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Hero header + podium
// ---------------------------------------------------------------------------

class _HeroHeader extends StatelessWidget {
  const _HeroHeader({
    required this.theme,
    required this.loc,
    required this.totalPlayers,
    required this.top3,
    required this.currentEmail,
    required this.avatarColor,
    required this.initials,
  });

  final ThemeData theme;
  final AppLocalizations loc;
  final int totalPlayers;
  final List<LeaderboardEntry> top3;
  final String? currentEmail;
  final Color Function(String) avatarColor;
  final String Function(String) initials;

  @override
  Widget build(BuildContext context) {
    final scheme = theme.colorScheme;
    final mediaTop = MediaQuery.paddingOf(context).top;

    return Stack(
      clipBehavior: Clip.none,
      children: [
        // Gradient background
        Container(
          width: double.infinity,
          padding: EdgeInsets.fromLTRB(20, mediaTop + 52, 20, 32),
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              stops: const [0.0, 0.45, 1.0],
              colors: [
                Color.lerp(scheme.primary, scheme.secondary, 0.15)!,
                scheme.primary,
                Color.lerp(scheme.secondary, scheme.tertiary, 0.5)!,
              ],
            ),
          ),
          child: Column(
            children: [
              // Trophy
              Container(
                width: 68,
                height: 68,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: scheme.onPrimary.withValues(alpha: 0.15),
                  border: Border.all(
                    color: scheme.onPrimary.withValues(alpha: 0.35),
                    width: 2,
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withValues(alpha: 0.18),
                      blurRadius: 20,
                      offset: const Offset(0, 8),
                    ),
                  ],
                ),
                child: Center(
                  child: ShaderMask(
                    blendMode: BlendMode.srcIn,
                    shaderCallback: (bounds) => LinearGradient(
                      colors: [Colors.amber.shade300, Colors.orange.shade400],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ).createShader(bounds),
                    child: const Icon(Icons.emoji_events_rounded, size: 36),
                  ),
                ),
              ),
              const SizedBox(height: 12),
              Text(
                loc.quizGameLeaderboard,
                style: theme.textTheme.headlineSmall?.copyWith(
                  color: scheme.onPrimary,
                  fontWeight: FontWeight.w800,
                  letterSpacing: -0.3,
                ),
              ),
              const SizedBox(height: 4),
              Text(
                '$totalPlayers ${loc.quizGameTopPlayers}',
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: scheme.onPrimary.withValues(alpha: 0.8),
                ),
              ),
              const SizedBox(height: 28),

              // Podium
              if (top3.isNotEmpty)
                _Podium(
                  theme: theme,
                  loc: loc,
                  top3: top3,
                  currentEmail: currentEmail,
                  avatarColor: avatarColor,
                  initials: initials,
                ),
            ],
          ),
        ),

        // Bottom wave clip
        Positioned(
          bottom: 0,
          left: 0,
          right: 0,
          child: CustomPaint(
            size: const Size(double.infinity, 24),
            painter: _WavePainter(
              color: theme.scaffoldBackgroundColor,
            ),
          ),
        ),
      ],
    );
  }
}

class _Podium extends StatelessWidget {
  const _Podium({
    required this.theme,
    required this.loc,
    required this.top3,
    required this.currentEmail,
    required this.avatarColor,
    required this.initials,
  });

  final ThemeData theme;
  final AppLocalizations loc;
  final List<LeaderboardEntry> top3;
  final String? currentEmail;
  final Color Function(String) avatarColor;
  final String Function(String) initials;

  static const _podiumColors = [
    Color(0xFFFFD700), // gold
    Color(0xFFC0C0C0), // silver
    Color(0xFFCD7F32), // bronze
  ];

  // Podium order: 2nd (left), 1st (center), 3rd (right)
  @override
  Widget build(BuildContext context) {
    // Build mapping: display position → leaderboard entry
    final positions = <int, LeaderboardEntry?>{};
    for (int i = 0; i < top3.length; i++) {
      positions[i] = top3[i];
    }

    final displayOrder = [1, 0, 2]; // left=2nd, center=1st, right=3rd

    final pillars = <Widget>[];
    for (final pos in displayOrder) {
      final entry = positions[pos];
      if (entry == null) {
        pillars.add(const Expanded(child: SizedBox.shrink()));
        continue;
      }
      final isCenter = pos == 0;
      pillars.add(
        Expanded(
          child: _PodiumPillar(
            theme: theme,
            loc: loc,
            entry: entry,
            rank: pos + 1,
            medalColor: _podiumColors[pos],
            isCenter: isCenter,
            isCurrentUser: currentEmail == entry.email,
            avatarColor: avatarColor(entry.name),
            initials: initials(entry.name),
          ),
        ),
      );
    }

    return SizedBox(
      height: 210,
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: pillars,
      ),
    );
  }
}

class _PodiumPillar extends StatelessWidget {
  const _PodiumPillar({
    required this.theme,
    required this.loc,
    required this.entry,
    required this.rank,
    required this.medalColor,
    required this.isCenter,
    required this.isCurrentUser,
    required this.avatarColor,
    required this.initials,
  });

  final ThemeData theme;
  final AppLocalizations loc;
  final LeaderboardEntry entry;
  final int rank;
  final Color medalColor;
  final bool isCenter;
  final bool isCurrentUser;
  final Color avatarColor;
  final String initials;

  @override
  Widget build(BuildContext context) {
    final pillarHeight = isCenter ? 100.0 : (rank == 2 ? 76.0 : 58.0);
    final avatarRadius = isCenter ? 32.0 : 26.0;
    final scheme = theme.colorScheme;

    return Column(
      mainAxisAlignment: MainAxisAlignment.end,
      children: [
        // Avatar + "You" badge
        Stack(
          clipBehavior: Clip.none,
          children: [
            CircleAvatar(
              radius: avatarRadius,
              backgroundColor: avatarColor,
              child: Text(
                initials,
                style: TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.w800,
                  fontSize: avatarRadius * 0.72,
                ),
              ),
            ),
            if (isCurrentUser)
              Positioned(
                right: -4,
                top: -4,
                child: Container(
                  padding: const EdgeInsets.all(3),
                  decoration: BoxDecoration(
                    color: scheme.primary,
                    shape: BoxShape.circle,
                    border: Border.all(color: Colors.white, width: 1.5),
                  ),
                  child: const Icon(
                    Icons.star_rounded,
                    size: 10,
                    color: Colors.white,
                  ),
                ),
              ),
            // Medal rank number
            Positioned(
              bottom: -6,
              left: 0,
              right: 0,
              child: Center(
                child: Container(
                  width: 22,
                  height: 22,
                  decoration: BoxDecoration(
                    color: medalColor,
                    shape: BoxShape.circle,
                    border: Border.all(color: Colors.white, width: 2),
                  ),
                  child: Center(
                    child: Text(
                      '$rank',
                      style: const TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w900,
                        color: Colors.white,
                      ),
                    ),
                  ),
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 10),

        // Name
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 4),
          child: Text(
            entry.name.split(' ').first,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            textAlign: TextAlign.center,
            style: theme.textTheme.labelMedium?.copyWith(
              color: scheme.onPrimary,
              fontWeight: FontWeight.w700,
              fontSize: isCenter ? 13 : 11,
            ),
          ),
        ),
        const SizedBox(height: 2),

        // Score
        Text(
          '${entry.score}',
          style: theme.textTheme.titleSmall?.copyWith(
            color: medalColor,
            fontWeight: FontWeight.w900,
            fontSize: isCenter ? 17 : 13,
          ),
        ),
        const SizedBox(height: 6),

        // Pillar block
        ClipRRect(
          borderRadius: const BorderRadius.only(
            topLeft: Radius.circular(8),
            topRight: Radius.circular(8),
          ),
          child: Container(
            width: double.infinity,
            height: pillarHeight,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  medalColor.withValues(alpha: 0.85),
                  medalColor.withValues(alpha: 0.55),
                ],
              ),
            ),
            child: Center(
              child: Icon(
                Icons.emoji_events_rounded,
                color: Colors.white.withValues(alpha: 0.35),
                size: isCenter ? 32 : 22,
              ),
            ),
          ),
        ),
      ],
    );
  }
}

// ---------------------------------------------------------------------------
// Rank row (#4+)
// ---------------------------------------------------------------------------

class _RankRow extends StatelessWidget {
  const _RankRow({
    required this.theme,
    required this.loc,
    required this.entry,
    required this.rank,
    required this.isCurrentUser,
    required this.maxScore,
    required this.avatarColor,
    required this.initials,
  });

  final ThemeData theme;
  final AppLocalizations loc;
  final LeaderboardEntry entry;
  final int rank;
  final bool isCurrentUser;
  final int maxScore;
  final Color avatarColor;
  final String initials;

  @override
  Widget build(BuildContext context) {
    final scheme = theme.colorScheme;
    final progress = maxScore == 0 ? 0.0 : entry.score / maxScore;

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      decoration: BoxDecoration(
        color: isCurrentUser
            ? scheme.primaryContainer.withValues(alpha: 0.25)
            : theme.cardColor,
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: isCurrentUser
              ? scheme.primary.withValues(alpha: 0.7)
              : scheme.outline.withValues(alpha: 0.15),
          width: isCurrentUser ? 1.5 : 1,
        ),
        boxShadow: [
          BoxShadow(
            color: theme.ambientShadow(lightOpacity: 0.04, darkOpacity: 0.3),
            blurRadius: 6,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(12, 12, 14, 12),
        child: Column(
          children: [
            Row(
              children: [
                // Rank badge
                SizedBox(
                  width: 36,
                  child: Text(
                    '#$rank',
                    style: theme.textTheme.labelMedium?.copyWith(
                      color: context.textSecondaryColor,
                      fontWeight: FontWeight.w700,
                    ),
                    textAlign: TextAlign.center,
                  ),
                ),
                const SizedBox(width: 10),

                // Avatar
                CircleAvatar(
                  radius: 20,
                  backgroundColor: avatarColor,
                  child: Text(
                    initials,
                    style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w800,
                      fontSize: 13,
                    ),
                  ),
                ),
                const SizedBox(width: 12),

                // Name / email
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Flexible(
                            child: Text(
                              entry.name,
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: theme.textTheme.bodyMedium?.copyWith(
                                fontWeight: FontWeight.w700,
                                color: context.textColor,
                              ),
                            ),
                          ),
                          if (isCurrentUser) ...[
                            const SizedBox(width: 6),
                            Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 7,
                                vertical: 2,
                              ),
                              decoration: BoxDecoration(
                                color: scheme.primary,
                                borderRadius: BorderRadius.circular(20),
                              ),
                              child: Text(
                                loc.quizGameYou,
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 10,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                            ),
                          ],
                        ],
                      ),
                      Text(
                        entry.email,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: context.textSecondaryColor,
                          fontSize: 11,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 12),

                // Score
                Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      '${entry.score}',
                      style: theme.textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w800,
                        color: context.textColor,
                      ),
                    ),
                    Text(
                      loc.quizGamePoints,
                      style: theme.textTheme.labelSmall?.copyWith(
                        color: context.textSecondaryColor,
                        fontSize: 10,
                      ),
                    ),
                  ],
                ),
              ],
            ),

            // Progress bar
            const SizedBox(height: 8),
            ClipRRect(
              borderRadius: BorderRadius.circular(4),
              child: LinearProgressIndicator(
                value: progress.clamp(0.0, 1.0),
                minHeight: 3,
                backgroundColor: scheme.outline.withValues(alpha: 0.12),
                valueColor: AlwaysStoppedAnimation<Color>(
                  isCurrentUser
                      ? scheme.primary
                      : avatarColor.withValues(alpha: 0.8),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Animated list entry
// ---------------------------------------------------------------------------

class _AnimatedListEntry extends StatelessWidget {
  const _AnimatedListEntry({
    required this.delay,
    required this.controller,
    required this.child,
  });

  final Duration delay;
  final AnimationController controller;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    // Create a delayed sub-interval within the shared controller.
    final totalMs = controller.duration?.inMilliseconds ?? 800;
    final delayFraction = (delay.inMilliseconds / totalMs).clamp(0.0, 0.9);
    final animation = CurvedAnimation(
      parent: controller,
      curve: Interval(delayFraction, 1.0, curve: Curves.easeOutCubic),
    );
    return AnimatedBuilder(
      animation: animation,
      builder: (context, child) => Opacity(
        opacity: animation.value,
        child: Transform.translate(
          offset: Offset(0, 20 * (1 - animation.value)),
          child: child,
        ),
      ),
      child: child,
    );
  }
}

// ---------------------------------------------------------------------------
// Loading
// ---------------------------------------------------------------------------

class _LoadingView extends StatelessWidget {
  const _LoadingView({required this.theme, required this.loc});
  final ThemeData theme;
  final AppLocalizations loc;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          SizedBox(
            width: 48,
            height: 48,
            child: CircularProgressIndicator(
              strokeWidth: 3,
              valueColor: AlwaysStoppedAnimation<Color>(
                theme.colorScheme.primary,
              ),
            ),
          ),
          const SizedBox(height: 20),
          Text(
            loc.quizGameLoadingLeaderboard,
            style: theme.textTheme.bodyLarge?.copyWith(
              color: context.textSecondaryColor,
            ),
          ),
        ],
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Error
// ---------------------------------------------------------------------------

class _ErrorView extends StatelessWidget {
  const _ErrorView({
    required this.theme,
    required this.loc,
    required this.error,
    required this.onRetry,
  });
  final ThemeData theme;
  final AppLocalizations loc;
  final String error;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.wifi_off_rounded,
              size: 72,
              color: theme.colorScheme.error.withValues(alpha: 0.7),
            ),
            const SizedBox(height: 16),
            Text(
              error,
              style: theme.textTheme.bodyLarge?.copyWith(
                color: context.textSecondaryColor,
              ),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 28),
            FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh_rounded),
              label: Text(loc.retry),
            ),
          ],
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Empty
// ---------------------------------------------------------------------------

class _EmptyView extends StatelessWidget {
  const _EmptyView({required this.theme, required this.loc});
  final ThemeData theme;
  final AppLocalizations loc;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.emoji_events_outlined,
              size: 80,
              color: context.textSecondaryColor.withValues(alpha: 0.5),
            ),
            const SizedBox(height: 16),
            Text(
              loc.quizGameNoLeaderboardData,
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
}

// ---------------------------------------------------------------------------
// Small frosted glass icon button (for the app bar)
// ---------------------------------------------------------------------------

class _GlassButton extends StatelessWidget {
  const _GlassButton({required this.onTap, required this.child});
  final VoidCallback onTap;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return ClipRRect(
      borderRadius: BorderRadius.circular(12),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: 12, sigmaY: 12),
        child: Material(
          color: theme.colorScheme.surface.withValues(alpha: 0.8),
          borderRadius: BorderRadius.circular(12),
          child: InkWell(
            borderRadius: BorderRadius.circular(12),
            onTap: onTap,
            child: Padding(
              padding: const EdgeInsets.all(8),
              child: IconTheme(
                data: IconThemeData(
                  color: theme.colorScheme.onSurface,
                  size: 20,
                ),
                child: child,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// ---------------------------------------------------------------------------
// Wave painter (clips hero bottom)
// ---------------------------------------------------------------------------

class _WavePainter extends CustomPainter {
  _WavePainter({required this.color});
  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()..color = color;
    final path = Path()
      ..moveTo(0, size.height)
      ..lineTo(0, size.height * 0.5)
      ..quadraticBezierTo(
        size.width * 0.25,
        0,
        size.width * 0.5,
        size.height * 0.4,
      )
      ..quadraticBezierTo(
        size.width * 0.75,
        size.height * 0.85,
        size.width,
        size.height * 0.2,
      )
      ..lineTo(size.width, size.height)
      ..close();
    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(covariant _WavePainter old) => old.color != color;
}
