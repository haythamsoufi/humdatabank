/// Primary / secondary / tertiary IDs for indicator bank (matches Backoffice JSON).
class IndicatorLevelIds {
  final int? primary;
  final int? secondary;
  final int? tertiary;

  const IndicatorLevelIds({
    this.primary,
    this.secondary,
    this.tertiary,
  });

  static int? _coerce(dynamic v) {
    if (v == null) return null;
    if (v is int) return v > 0 ? v : null;
    final t = int.tryParse('$v');
    return t != null && t > 0 ? t : null;
  }

  factory IndicatorLevelIds.fromJson(dynamic json) {
    if (json == null) return const IndicatorLevelIds();
    if (json is! Map) return const IndicatorLevelIds();
    final m = Map<String, dynamic>.from(json);
    return IndicatorLevelIds(
      primary: _coerce(m['primary']),
      secondary: _coerce(m['secondary']),
      tertiary: _coerce(m['tertiary']),
    );
  }

  Map<String, dynamic> toJson() {
    final out = <String, dynamic>{};
    if (primary != null) out['primary'] = primary;
    if (secondary != null) out['secondary'] = secondary;
    if (tertiary != null) out['tertiary'] = tertiary;
    return out;
  }

  bool get isEmpty => primary == null && secondary == null && tertiary == null;
}
