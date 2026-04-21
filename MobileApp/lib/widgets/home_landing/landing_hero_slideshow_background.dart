import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'landing_hero_slides.dart';

/// Full-bleed crossfading images on top of [fallback] (e.g. gradient mesh).
class LandingHeroSlideshowBackground extends StatefulWidget {
  final Widget fallback;
  final Duration interval;

  const LandingHeroSlideshowBackground({
    super.key,
    required this.fallback,
    this.interval = LandingHeroSlides.defaultInterval,
  });

  @override
  State<LandingHeroSlideshowBackground> createState() =>
      _LandingHeroSlideshowBackgroundState();
}

class _LandingHeroSlideshowBackgroundState
    extends State<LandingHeroSlideshowBackground> {
  Timer? _timer;
  int _index = 0;

  List<String> get _paths => LandingHeroSlides.assetPaths;

  @override
  void initState() {
    super.initState();
    if (_paths.length > 1) {
      _timer = Timer.periodic(widget.interval, (_) {
        if (!mounted) return;
        setState(() => _index = (_index + 1) % _paths.length);
      });
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        widget.fallback,
        if (_paths.isNotEmpty)
          AnimatedSwitcher(
            duration: const Duration(milliseconds: 900),
            switchInCurve: Curves.easeInOut,
            switchOutCurve: Curves.easeInOut,
            transitionBuilder: (child, animation) =>
                FadeTransition(opacity: animation, child: child),
            child: SizedBox.expand(
              key: ValueKey<String>(_paths[_index]),
              child: Image.asset(
                _paths[_index],
                fit: BoxFit.cover,
                gaplessPlayback: true,
                errorBuilder: (context, error, stackTrace) {
                  if (kDebugMode) {
                    debugPrint(
                      'LandingHeroSlideshow: asset load failed for '
                      '${_paths[_index]} — $error (flutter pub get; commit '
                      'JPEGs under assets/images/hero/)',
                    );
                  }
                  return const SizedBox.shrink();
                },
              ),
            ),
          ),
      ],
    );
  }
}
