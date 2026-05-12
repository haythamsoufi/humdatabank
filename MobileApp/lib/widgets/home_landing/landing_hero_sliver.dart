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

  /// Called when the user taps the hero background while [chatExpanded] is
  /// `true` (i.e. any area not covered by [footer] or [quickPrompts]).
  /// Use this to dismiss focus mode from the hero itself so that the full
  /// hero surface acts as a dismiss target — not just the scrims outside it.
  final VoidCallback? onBackgroundTap;

  const LandingHeroSliver({
    super.key,
    required this.title,
    required this.description,
    this.expandedHeight = 188,
    this.footer,
    this.quickPrompts,
    this.chatExpanded = false,
    this.onBackgroundTap,
  });

  /// Reserved height for [footer] (card + overlap into the hero).
  static const double footerPreferredHeight = 212;

  /// Extra flex height when [quickPrompts] is non-null (list + padding).
  static const double quickPromptsSlotHeight = 58;

  /// Pixel height of the hero region in the scroll body (matches [SliverAppBar.expandedHeight]
  /// when a footer is present). Use to align focus-mode scrims above/below the hero.
  ///
  /// Important: this must NOT include `MediaQuery.padding.top`. Flutter's [Scaffold]
  /// strips the top safe-area inset from the body's [MediaQuery], so inside the body
  /// Stack the coordinate system starts at y = 0 directly below the [AppBar]. The
  /// sliver itself adds that same 0-value to its own height, so the two are consistent
  /// only when the status-bar height is excluded here.
  static double bodyHeroExtent({
    double expandedHeight = 188,
    bool hasFooter = true,
  }) {
    final footerExtra = hasFooter ? footerPreferredHeight : 0.0;
    return expandedHeight + footerExtra;
  }

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
    final footerExtra =
        widget.footer != null ? LandingHeroSliver.footerPreferredHeight : 0.0;
    // Quick-prompt space is NOT added to the expanded height; prompts appear
    // in the space freed by the collapsing title area (expandedHeight - 12 px).
    //
    // Note: MediaQuery.padding.top is intentionally excluded. The Scaffold
    // removes the status-bar inset from the body's MediaQuery, so it is
    // always 0 here. bodyHeroExtent() follows the same convention so that
    // focus-mode scrim positioning stays consistent.
    final h = widget.expandedHeight + footerExtra;

    // Title region height (see comment below: chat card is bottom-weighted via Spacer).
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

            // ── Background dismiss target ────────────────────────────────────
            // Sits between the gradient overlay (below) and the content column
            // (above).  In Flutter, Stacks are hit-tested from the last child
            // backwards, so the content column is always tried first.  The
            // Column only registers a hit where its rendered children are
            // (card, prompts, title); tapping the visible gradient region falls
            // through to this layer and fires onBackgroundTap to end focus mode.
            // opaque behaviour ensures the gradient layers below don't also fire.
            if (widget.chatExpanded && widget.onBackgroundTap != null)
              GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: widget.onBackgroundTap,
              ),

            // ── Content column ───────────────────────────────────────────────
            // Bottom-weight the chat card: [Spacer] eats space between the title
            // and footer so the card sits lower in the hero (same expandedHeight).
            // Single traversal scope so Tab moves: chat field → send → prompts.
            FocusTraversalGroup(
              policy: OrderedTraversalPolicy(),
              child: Builder(
                builder: (context) {
                  final children = <Widget>[
                    const SizedBox(height: 12),

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
                                    padding: const EdgeInsets.symmetric(
                                      horizontal: 20,
                                    ),
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
                                                        .withValues(
                                                            alpha: 0.9),
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

                    if (widget.footer != null) ...[
                      const SizedBox(height: 20),
                      Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: widget.footer!,
                      ),
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
                  ];

                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: children,
                  );
                },
              ),
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
