/// A unified planning PDF from the IFRC GO PublicSiteAppeals API.
///
/// Aggregated stats (document types grouped by year) are shown on the unified
/// planning analytics route `/unified-planning-analytics`.
class UnifiedPlanningDocument {
  final String url;
  final String title;
  final String? countryCode;
  final String? countryName;
  final int? appealsTypeId;
  final String? documentTypeLabel;

  /// Calendar year from IFRC `AppealOrigType` + `AppealsName` (first `20xx` with digit
  /// boundaries, same as Backoffice `IFRC_APPEALS_TITLE_YEAR_RE`).
  final int? year;

  /// Parsed from IFRC `AppealsDate` when present (publication / document date).
  final DateTime? publishedAt;

  const UnifiedPlanningDocument({
    required this.url,
    required this.title,
    this.countryCode,
    this.countryName,
    this.appealsTypeId,
    this.documentTypeLabel,
    this.year,
    this.publishedAt,
  });

  /// Distinct country for analytics: ISO2 code if set, else normalized display name.
  static String? countryIdentityKey(UnifiedPlanningDocument d) {
    final code = (d.countryCode ?? '').trim().toUpperCase();
    if (code.isNotEmpty) return 'c:$code';
    final name = (d.countryName ?? '').trim();
    if (name.isNotEmpty) return 'n:${name.toLowerCase()}';
    return null;
  }

  /// Stable grouping key for analytics and filters (label, or `Type {id}`, or unknown).
  static String typeKey(UnifiedPlanningDocument d) {
    final tid = d.appealsTypeId;
    final tlab = (d.documentTypeLabel ?? '').trim();
    if (tid != null) {
      return tlab.isNotEmpty ? tlab : 'Type $tid';
    }
    if (tlab.isNotEmpty) return tlab;
    return '__type_unknown__';
  }

  /// True when [publishedAt] falls within the **last 3 days** (local clock).
  bool get isPublishedWithinLastThreeDays {
    final t = publishedAt;
    if (t == null) return false;
    final now = DateTime.now();
    const window = Duration(days: 3);
    final start = now.subtract(window);
    return !t.isBefore(start) && !t.isAfter(now);
  }
}
