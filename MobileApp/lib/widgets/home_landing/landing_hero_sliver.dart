import 'dart:ui';

import 'package:flutter/material.dart';
import '../../utils/constants.dart';
import 'landing_hero_slideshow_background.dart';

/// Collapsing hero with gradient mesh, title and subtitle.
///
/// Optional [footer] (e.g. AI entry card) and [quickPrompts] are laid out
/// inside [FlexibleSpaceBar] so they sit on the same gradient.
///
/// When [chatExpanded] flips to `true` the title + description fade out and
/// their vertical space collapses (via [SizeTransition]), causing the footer
/// to slide upward.  The [quickPrompts] widget then expands below the footer
/// in the freed space.
class LandingHeroSliver extends StatefulWidget {
  final String title;
  final String description;
  final double expandedHeight;

  /// Placed on the hero gradient (e.g. AI entry card).
  final Widget? footer;

  /// Placed below [footer] once [chatExpanded] is `true`.
  final Widget? quickPrompts;

  /// When `true` the title/description collapse and [quickPrompts] appear.
  final bool chatExpanded;

  const LandingHeroSliver({
    super.key,
    required this.title,
    required this.description,
    this.expandedHeight = 188,
    this.footer,
    this.quickPrompts,
    this.chatExpanded = false,
  });

  /// Reserved height for [footer] (card + overlap into the hero).
  static const double footerPreferredHeight = 212;

  /// Extra flex height when [quickPrompts] is non-null (list + padding).
  static const double quickPromptsSlotHeight = 58;

  @override
  State<LandingHeroSliver> createState() => _LandingHeroSliverState();
}

class _LandingHeroSliverState extends State<LandingHeroSliver>
    with TickerProviderStateMixin {
  // Intro: fades/slides the title in on mount.
  late AnimationController _introCtrl;
  late Animation<double> _fadeIn;
  late Animation<Offset> _slide;

  // Chat expansion: collapses title, reveals quick prompts.
  late AnimationController _chatCtrl;

  // Title shrinks out (1 → 0) across the first 65 % of _chatCtrl.
  late Animation<double> _titleShrink;
  // Title fades faster (1 → 0) across the first 35 %.
  late Animation<double> _titleFade;
  // Quick-prompts grow in (0 → 1) during the last 55 %.
  late Animation<double> _promptsGrow;
  // Quick-prompts fade in during the last 40 %.
  late Animation<double> _promptsFade;

  static const List<Color> _meshColors = [
    Color(0xFF0F172A),
    Color(0xFF1E3A5F),
    Color(0xFF7F1D1D),
    Color(0xFF0F172A),
  ];

  @override
  void initState() {
    super.initState();

    _introCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    );
    _fadeIn = CurvedAnimation(parent: _introCtrl, curve: Curves.easeOutCubic);
    _slide = Tween<Offset>(
      begin: const Offset(0, 0.06),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _introCtrl, curve: Curves.easeOutCubic));
    _introCtrl.forward();

    _chatCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 400),
      value: widget.chatExpanded ? 1.0 : 0.0,
    );
    _buildChatAnimations();
  }

  void _buildChatAnimations() {
    _titleFade = Tween<double>(begin: 1, end: 0).animate(
      CurvedAnimation(
        parent: _chatCtrl,
        curve: const Interval(0.0, 0.35, curve: Curves.easeOut),
      ),
    );
    _titleShrink = Tween<double>(begin: 1, end: 0).animate(
      CurvedAnimation(
        parent: _chatCtrl,
        curve: const Interval(0.0, 0.65, curve: Curves.easeOutCubic),
      ),
    );
    _promptsGrow = CurvedAnimation(
      parent: _chatCtrl,
      curve: const Interval(0.45, 1.0, curve: Curves.easeOutCubic),
    );
    _promptsFade = Tween<double>(begin: 0, end: 1).animate(
      CurvedAnimation(
        parent: _chatCtrl,
        curve: const Interval(0.6, 1.0, curve: Curves.easeIn),
      ),
    );
  }

  @override
  void didUpdateWidget(LandingHeroSliver old) {
    super.didUpdateWidget(old);
    if (widget.chatExpanded != old.chatExpanded) {
      if (widget.chatExpanded) {
        _chatCtrl.forward();
      } else {
        _chatCtrl.reverse();
      }
    }
  }

  @override
  void dispose() {
    _introCtrl.dispose();
    _chatCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final top = MediaQuery.paddingOf(context).top;
    final footerExtra =
        widget.footer != null ? LandingHeroSliver.footerPreferredHeight : 0.0;
    // Quick-prompt space is NOT added to the expanded height; prompts appear
    // in the space freed by the collapsing title area (expandedHeight - 12 px).
    final h = widget.expandedHeight + top + footerExtra;

    // The title area occupies exactly (expandedHeight - 12) px when visible.
    // The 12 comes from the SizedBox(height: top + 12) offset at the top,
    // which means: h - (top + 12) - footerExtra = expandedHeight - 12.
    final titleAreaHeight = widget.expandedHeight - 12.0;

    return SliverAppBar(
      pinned: false,
      floating: false,
      stretch: true,
      clipBehavior: Clip.none,
      toolbarHeight: 0,
      expandedHeight: h,
      automaticallyImplyLeading: false,
      backgroundColor: _meshColors.first,
      flexibleSpace: FlexibleSpaceBar(
        stretchModes: const [StretchMode.zoomBackground],
        background: Stack(
          fit: StackFit.expand,
          children: [
            // ── Background ──────────────────────────────────────────────────
            const LandingHeroSlideshowBackground(
              fallback: _MeshGradient(colors: _meshColors),
            ),
            DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    Colors.black.withValues(alpha: 0.45),
                    Colors.black.withValues(alpha: 0.78),
                  ],
                ),
              ),
            ),

            // ── Content column ───────────────────────────────────────────────
            Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                SizedBox(height: top + 12),

                // Title + description — collapses when chatExpanded.
                AnimatedBuilder(
                  animation: _chatCtrl,
                  builder: (context, _) {
                    return ClipRect(
                      child: SizeTransition(
                        sizeFactor: _titleShrink,
                        axisAlignment: -1,
                        child: SizedBox(
                          height: titleAreaHeight,
                          child: FadeTransition(
                            opacity: _titleFade,
                            child: Center(
                              child: Padding(
                                padding:
                                    const EdgeInsets.symmetric(horizontal: 20),
                                child: FadeTransition(
                                  opacity: _fadeIn,
                                  child: SlideTransition(
                                    position: _slide,
                                    child: Column(
                                      mainAxisSize: MainAxisSize.min,
                                      crossAxisAlignment:
                                          CrossAxisAlignment.stretch,
                                      children: [
                                        Text(
                                          widget.title,
                                          textAlign: TextAlign.center,
                                          maxLines: 2,
                                          overflow: TextOverflow.ellipsis,
                                          style: Theme.of(context)
                                              .textTheme
                                              .headlineSmall
                                              ?.copyWith(
                                                color: Colors.white,
                                                fontWeight: FontWeight.w800,
                                                height: 1.2,
                                                letterSpacing: -0.4,
                                              ),
                                        ),
                                        const SizedBox(height: 8),
                                        Text(
                                          widget.description,
                                          textAlign: TextAlign.center,
                                          maxLines: 4,
                                          overflow: TextOverflow.ellipsis,
                                          style: Theme.of(context)
                                              .textTheme
                                              .bodyMedium
                                              ?.copyWith(
                                                color: Colors.white
                                                    .withValues(alpha: 0.9),
                                                height: 1.35,
                                              ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                              ),
                            ),
                          ),
                        ),
                      ),
                    );
                  },
                ),

                // Footer (AI entry card) — always visible, slides upward as
                // the title area above it collapses.
                if (widget.footer != null)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: widget.footer!,
                  ),

                // Quick prompts — expand below the card when chatExpanded.
                if (widget.quickPrompts != null)
                  AnimatedBuilder(
                    animation: _chatCtrl,
                    builder: (context, _) {
                      return ClipRect(
                        child: SizeTransition(
                          sizeFactor: _promptsGrow,
                          axisAlignment: -1,
                          child: FadeTransition(
                            opacity: _promptsFade,
                            child: Padding(
                              padding:
                                  const EdgeInsets.fromLTRB(0, 6, 0, 8),
                              child: widget.quickPrompts!,
                            ),
                          ),
                        ),
                      );
                    },
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _MeshGradient extends StatelessWidget {
  final List<Color> colors;

  const _MeshGradient({required this.colors});

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        DecoratedBox(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: colors,
            ),
          ),
        ),
        Positioned(
          right: -80,
          top: -40,
          child: _Blob(
              color: Color(AppConstants.ifrcRed).withValues(alpha: 0.35)),
        ),
        Positioned(
          left: -60,
          bottom: 20,
          child: _Blob(
              color: Colors.blue.shade900.withValues(alpha: 0.4)),
        ),
      ],
    );
  }
}

class _Blob extends StatelessWidget {
  final Color color;

  const _Blob({required this.color});

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: ImageFiltered(
        imageFilter: ImageFilter.blur(sigmaX: 60, sigmaY: 60),
        child: Container(
          width: 200,
          height: 200,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: color,
          ),
        ),
      ),
    );
  }
}
