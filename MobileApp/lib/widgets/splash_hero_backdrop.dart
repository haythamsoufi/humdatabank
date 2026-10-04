import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../theme/splash_hero_palette.dart';

/// Navy login-hero background: drifting aurora, grain, and a constellation
/// of nodes with traveling pulses. Matches the backoffice sign-in scene.
class SplashHeroBackdrop extends StatefulWidget {
  const SplashHeroBackdrop({super.key, required this.child});

  final Widget child;

  @override
  State<SplashHeroBackdrop> createState() => _SplashHeroBackdropState();
}

class _SplashHeroBackdropState extends State<SplashHeroBackdrop>
    with SingleTickerProviderStateMixin {
  late final AnimationController _clock;
  final _field = _ConstellationField();
  final Stopwatch _watch = Stopwatch();
  double _lastSeconds = 0;

  @override
  void initState() {
    super.initState();
    _clock = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 1),
    )..repeat();
    _watch.start();
    _clock.addListener(_onTick);
  }

  void _onTick() {
    final now = _watch.elapsedMicroseconds / 1e6;
    final dt = _lastSeconds == 0
        ? 1 / 60
        : (now - _lastSeconds).clamp(0.0, 0.05);
    _lastSeconds = now;
    _field.step(dt);
  }

  @override
  void dispose() {
    _clock.dispose();
    _watch.stop();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final reduced = MediaQuery.disableAnimationsOf(context);
    _field.reducedMotion = reduced;
    return ColoredBox(
      color: SplashHeroPalette.navy,
      child: Stack(
        fit: StackFit.expand,
        children: [
          RepaintBoundary(
            child: CustomPaint(
              painter: _HeroScenePainter(repaint: _clock, field: _field),
            ),
          ),
          widget.child,
        ],
      ),
    );
  }
}

class _Node {
  _Node({
    required this.x,
    required this.y,
    required this.vx,
    required this.vy,
    required this.r,
  });

  double x;
  double y;
  double vx;
  double vy;
  double r;
}

class _Pulse {
  _Pulse({required this.a, required this.b, required this.speed});

  final _Node a;
  final _Node b;
  final double speed;
  double t = 0;
}

class _ConstellationField {
  final math.Random _random = math.Random();
  final List<_Node> nodes = [];
  final List<_Pulse> pulses = [];
  final List<Offset> grain = [];
  Size size = Size.zero;
  double elapsed = 0;
  double boot = 0;
  bool reducedMotion = false;

  void ensureSize(Size next) {
    if (next.width < 2 || next.height < 2) return;
    if ((next.width - size.width).abs() < 8 &&
        (next.height - size.height).abs() < 8 &&
        nodes.isNotEmpty) {
      return;
    }
    size = next;
    final count = math.max(
      22,
      math.min(40, (next.width * next.height) / 22000).round(),
    );
    nodes
      ..clear()
      ..addAll(
        List.generate(count, (_) {
          return _Node(
            x: _random.nextDouble() * next.width,
            y: _random.nextDouble() * next.height,
            vx: (_random.nextDouble() - 0.5) * 11,
            vy: (_random.nextDouble() - 0.5) * 11,
            r: 1.1 + _random.nextDouble() * 1.3,
          );
        }),
      );
    pulses.clear();
    grain
      ..clear()
      ..addAll(
        List.generate(220, (_) {
          return Offset(
            _random.nextDouble() * next.width,
            _random.nextDouble() * next.height,
          );
        }),
      );
  }

  void step(double dt) {
    elapsed += dt;
    if (reducedMotion) {
      boot = 1;
      return;
    }
    boot = (elapsed / 1.6).clamp(0.0, 1.0);
    if (size == Size.zero) return;
    final w = size.width;
    final h = size.height;
    for (final n in nodes) {
      n.x += n.vx * dt;
      n.y += n.vy * dt;
      if (n.x < 0 || n.x > w) {
        n.vx *= -1;
        n.x = n.x.clamp(0, w);
      }
      if (n.y < 0 || n.y > h) {
        n.vy *= -1;
        n.y = n.y.clamp(0, h);
      }
      final drag = math.pow(0.999, dt * 60).toDouble();
      n.vx *= drag;
      n.vy *= drag;
    }

    if (pulses.length < 4 && nodes.length > 1 && _random.nextDouble() < 0.04) {
      final a = nodes[_random.nextInt(nodes.length)];
      final b = nodes[_random.nextInt(nodes.length)];
      if (!identical(a, b)) {
        pulses.add(
          _Pulse(a: a, b: b, speed: 0.35 + _random.nextDouble() * 0.25),
        );
      }
    }
    for (var i = pulses.length - 1; i >= 0; i--) {
      pulses[i].t += pulses[i].speed * dt;
      if (pulses[i].t >= 1) pulses.removeAt(i);
    }
  }
}

class _HeroScenePainter extends CustomPainter {
  _HeroScenePainter({required Listenable repaint, required this.field})
    : super(repaint: repaint);

  final _ConstellationField field;

  @override
  void paint(Canvas canvas, Size size) {
    field.ensureSize(size);
    _paintBackground(canvas, size);
    _paintAurora(canvas, size);
    _paintNetwork(canvas, size);
    _paintGrain(canvas);
  }

  void _paintBackground(Canvas canvas, Size size) {
    final rect = Offset.zero & size;
    final paint = Paint()
      ..shader = const LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [
          SplashHeroPalette.navyMid,
          SplashHeroPalette.navy,
          SplashHeroPalette.navyDeep,
        ],
        stops: [0.0, 0.42, 1.0],
      ).createShader(rect);
    canvas.drawRect(rect, paint);
  }

  void _paintAurora(Canvas canvas, Size size) {
    final t = field.reducedMotion ? 0.0 : field.elapsed;
    final driftA = Offset(
      math.sin(t / 24 * math.pi * 2) * size.width * 0.04,
      math.cos(t / 24 * math.pi * 2) * size.height * 0.03,
    );
    final driftB = Offset(
      math.cos(t / 28 * math.pi * 2) * size.width * 0.04,
      math.sin(t / 28 * math.pi * 2) * size.height * 0.035,
    );
    final driftC = Offset(
      math.sin(t / 20 * math.pi * 2) * size.width * 0.03,
      math.cos(t / 18 * math.pi * 2) * size.height * 0.025,
    );
    _blob(
      canvas,
      Offset(size.width * 0.08, size.height * 0.06) + driftA,
      size.shortestSide * 0.55,
      SplashHeroPalette.blue.withValues(alpha: 0.45),
    );
    _blob(
      canvas,
      Offset(size.width * 0.92, size.height * 0.88) + driftB,
      size.shortestSide * 0.48,
      SplashHeroPalette.red.withValues(alpha: 0.36),
    );
    _blob(
      canvas,
      Offset(size.width * 0.55, size.height * 0.42) + driftC,
      size.shortestSide * 0.32,
      SplashHeroPalette.ink.withValues(alpha: 0.08),
    );
  }

  void _blob(Canvas canvas, Offset center, double radius, Color color) {
    final paint = Paint()
      ..shader = RadialGradient(
        colors: [color, color.withValues(alpha: 0)],
      ).createShader(Rect.fromCircle(center: center, radius: radius));
    canvas.drawCircle(center, radius, paint);
  }

  void _paintNetwork(Canvas canvas, Size size) {
    final nodes = field.nodes;
    if (nodes.isEmpty) return;
    final bootEase = 1 - math.pow(1 - field.boot, 3).toDouble();
    final linkDist = math.max(
      78.0,
      math.min(140.0, math.min(size.width, size.height) * 0.28),
    );
    final linkNow = linkDist * (0.45 + 0.55 * bootEase);
    final maxLinks = bootEase > 0.45 ? 2 : 1;
    final seen = <String>{};

    for (var i = 0; i < nodes.length; i++) {
      final neighbors = <({int j, double d})>[];
      for (var j = 0; j < nodes.length; j++) {
        if (i == j) continue;
        final d =
            (Offset(nodes[i].x, nodes[i].y) - Offset(nodes[j].x, nodes[j].y))
                .distance;
        if (d < linkNow) neighbors.add((j: j, d: d));
      }
      neighbors.sort((a, b) => a.d.compareTo(b.d));
      var added = 0;
      for (final neighbor in neighbors) {
        if (added >= maxLinks) break;
        final j = neighbor.j;
        final key = i < j ? '$i-$j' : '$j-$i';
        if (!seen.add(key)) continue;
        final alpha = (0.16 + 0.16 * bootEase) * (1 - neighbor.d / linkNow);
        final paint = Paint()
          ..color = SplashHeroPalette.ink.withValues(alpha: alpha.clamp(0, 1))
          ..strokeWidth = 0.7;
        canvas.drawLine(
          Offset(nodes[i].x, nodes[i].y),
          Offset(nodes[j].x, nodes[j].y),
          paint,
        );
        added++;
      }
    }

    final dot = Paint()
      ..color = SplashHeroPalette.ink.withValues(alpha: 0.4 + 0.4 * bootEase);
    for (final n in nodes) {
      canvas.drawCircle(Offset(n.x, n.y), n.r, dot);
    }

    for (final pulse in field.pulses) {
      final x = pulse.a.x + (pulse.b.x - pulse.a.x) * pulse.t;
      final y = pulse.a.y + (pulse.b.y - pulse.a.y) * pulse.t;
      final a = math.sin(pulse.t * math.pi);
      final paint = Paint()
        ..shader = RadialGradient(
          colors: [
            SplashHeroPalette.ink.withValues(alpha: 0.85 * a),
            SplashHeroPalette.ink.withValues(alpha: 0),
          ],
        ).createShader(Rect.fromCircle(center: Offset(x, y), radius: 7));
      canvas.drawCircle(Offset(x, y), 7, paint);
    }
  }

  void _paintGrain(Canvas canvas) {
    final paint = Paint()
      ..color = SplashHeroPalette.ink.withValues(alpha: 0.035);
    for (final p in field.grain) {
      canvas.drawRect(Rect.fromCircle(center: p, radius: 0.6), paint);
    }
  }

  @override
  bool shouldRepaint(covariant _HeroScenePainter oldDelegate) => true;
}
