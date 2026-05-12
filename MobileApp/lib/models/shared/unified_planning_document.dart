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

  Map<String, dynamic> toJson() => {
        'url': url,
        'title': title,
        if (countryCode != null) 'countryCode': countryCode,
        if (countryName != null) 'countryName': countryName,
        if (appealsTypeId != null) 'appealsTypeId': appealsTypeId,
        if (documentTypeLabel != null) 'documentTypeLabel': documentTypeLabel,
        if (year != null) 'year': year,
        if (publishedAt != null) 'publishedAt': publishedAt!.toUtc().toIso8601String(),
      };

  factory UnifiedPlanningDocument.fromJson(Map<String, dynamic> json) {
    DateTime? published;
    final rawPub = json['publishedAt'];
    if (rawPub is String && rawPub.trim().isNotEmpty) {
      published = DateTime.tryParse(rawPub.trim());
    }
    final tid = json['appealsTypeId'];
    int? appealsId;
    if (tid is int) {
      appealsId = tid;
    } else if (tid is num) {
      appealsId = tid.toInt();
    }
    final y = json['year'];
    int? yearVal;
    if (y is int) {
      yearVal = y;
    } else if (y is num) {
      yearVal = y.toInt();
    }
    return UnifiedPlanningDocument(
      url: (json['url'] as String?)?.trim() ?? '',
      title: (json['title'] as String?)?.trim() ?? '',
      countryCode: json['countryCode'] as String?,
      countryName: json['countryName'] as String?,
      appealsTypeId: appealsId,
      documentTypeLabel: json['documentTypeLabel'] as String?,
      year: yearVal,
      publishedAt: published,
    );
  }

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

  /// True when the publication **calendar day** (local) is today, yesterday, or two
  /// days ago — or up to one local calendar day "ahead" of today (server/UTC skew).
  bool get isPublishedWithinLastThreeDays {
    final t = publishedAt;
    if (t == null) return false;
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final pubDay = DateTime(t.year, t.month, t.day);
    final daysBehind = today.difference(pubDay).inDays;
    if (daysBehind >= 0 && daysBehind <= 2) return true;
    // Same document stamped "tomorrow" in local time (common with UTC midnight).
    if (daysBehind == -1) return true;
    return false;
  }
}
