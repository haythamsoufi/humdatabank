/// A reunified (unified) planning PDF from the IFRC GO PublicSiteAppeals API.
class ReunifiedPlanningDocument {
  final String url;
  final String title;
  final String? countryCode;
  final String? countryName;
  final int? appealsTypeId;
  final String? documentTypeLabel;
  final int? year;

  const ReunifiedPlanningDocument({
    required this.url,
    required this.title,
    this.countryCode,
    this.countryName,
    this.appealsTypeId,
    this.documentTypeLabel,
    this.year,
  });
}
