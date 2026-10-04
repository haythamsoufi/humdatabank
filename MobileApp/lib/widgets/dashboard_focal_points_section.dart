import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/shared/focal_point_contact.dart';
import '../l10n/app_localizations.dart';
import '../services/organization_config_service.dart';
import '../utils/constants.dart';
import '../utils/ios_constants.dart';
import 'dashboard_grouped_assignment_card.dart';

/// Distinct, stable avatar colors so each person is easy to tell apart.
const List<Color> _avatarPalette = [
  Color(0xFF0F766E),
  Color(0xFFB45309),
  Color(0xFF011E41),
  Color(0xFF1D4ED8),
  Color(0xFF7C3AED),
  Color(0xFFBE123C),
  Color(0xFF0369A1),
  Color(0xFF3F6212),
];

Color avatarColorFor(String key) {
  var hash = 0;
  for (final unit in key.codeUnits) {
    hash = (hash * 31 + unit) & 0x7fffffff;
  }
  return _avatarPalette[hash % _avatarPalette.length];
}

class DashboardFocalPointsSection extends StatelessWidget {
  const DashboardFocalPointsSection({
    super.key,
    required this.entityLabel,
    required this.nsFocalPoints,
    required this.orgFocalPoints,
  });

  final String entityLabel;
  final List<FocalPointContact> nsFocalPoints;
  final List<FocalPointContact> orgFocalPoints;

  String _orgFocalPointsTitle(AppLocalizations localizations) {
    if (OrganizationConfigService().isInitialized) {
      final shortName = OrganizationConfigService()
          .config
          .organization
          .shortName
          .trim();
      if (shortName.isNotEmpty) {
        return '$shortName ${localizations.focalPoints}';
      }
    }
    return localizations.ifrcFocalPoints;
  }

  Future<void> _launchContactUri(BuildContext context, Uri uri) async {
    try {
      final launched = await launchUrl(uri, mode: LaunchMode.platformDefault);
      if (!launched && context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(AppLocalizations.of(context)!.retry)),
        );
      }
    } catch (_) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(AppLocalizations.of(context)!.retry)),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final isDark = theme.brightness == Brightness.dark;
    final hasContacts = nsFocalPoints.isNotEmpty || orgFocalPoints.isNotEmpty;
    final cardColor = isDark ? scheme.surfaceContainerHigh : Colors.white;
    final borderColor = isDark
        ? scheme.outlineVariant.withValues(alpha: 0.45)
        : const Color(0xFFE5E5EA);
    final total = nsFocalPoints.length + orgFocalPoints.length;

    return Padding(
      padding: const EdgeInsets.fromLTRB(0, 8, 0, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 10, 20, 10),
            child: DashboardSectionLabel(
              title: localizations.focalPoints,
              count: hasContacts ? total : null,
            ),
          ),
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16),
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: cardColor,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: borderColor),
              ),
              child: hasContacts
                  ? Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        if (nsFocalPoints.isNotEmpty)
                          _ContactGroup(
                            title: localizations.nationalSocietyFocalPoints,
                            contacts: nsFocalPoints,
                            onLaunch: _launchContactUri,
                          ),
                        if (nsFocalPoints.isNotEmpty &&
                            orgFocalPoints.isNotEmpty)
                          Divider(height: 1, thickness: 1, color: borderColor),
                        if (orgFocalPoints.isNotEmpty)
                          _ContactGroup(
                            title: _orgFocalPointsTitle(localizations),
                            contacts: orgFocalPoints,
                            onLaunch: _launchContactUri,
                          ),
                      ],
                    )
                  : Padding(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 20,
                        vertical: 28,
                      ),
                      child: Text(
                        '${localizations.noFocalPointsAssignedTo} $entityLabel ${localizations.yet}',
                        style: IOSTextStyle.subheadline(context).copyWith(
                          color: scheme.onSurface.withValues(alpha: 0.6),
                          height: 1.35,
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ContactGroup extends StatelessWidget {
  const _ContactGroup({
    required this.title,
    required this.contacts,
    required this.onLaunch,
  });

  final String title;
  final List<FocalPointContact> contacts;
  final Future<void> Function(BuildContext context, Uri uri) onLaunch;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 2),
          child: Text(
            title.toUpperCase(),
            style: IOSTextStyle.caption2(context).copyWith(
              fontWeight: FontWeight.w700,
              letterSpacing: 0.5,
              color: scheme.onSurface.withValues(alpha: 0.45),
            ),
          ),
        ),
        for (var i = 0; i < contacts.length; i++)
          _ContactRow(
            contact: contacts[i],
            showDivider: i < contacts.length - 1,
            onLaunch: onLaunch,
          ),
      ],
    );
  }
}

class _ContactRow extends StatelessWidget {
  const _ContactRow({
    required this.contact,
    required this.showDivider,
    required this.onLaunch,
  });

  final FocalPointContact contact;
  final bool showDivider;
  final Future<void> Function(BuildContext context, Uri uri) onLaunch;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final isDark = theme.brightness == Brightness.dark;
    final localizations = AppLocalizations.of(context)!;
    final titleColor = isDark
        ? scheme.onSurface
        : const Color(AppConstants.defaultNavy);
    final avatar = avatarColorFor(
      contact.email.isNotEmpty ? contact.email : contact.displayName,
    );
    final borderColor = isDark
        ? scheme.outlineVariant.withValues(alpha: 0.35)
        : const Color(0xFFE5E5EA);

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(14, 10, 6, 10),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              CircleAvatar(
                radius: 18,
                backgroundColor: avatar,
                child: Text(
                  contact.initials,
                  style: IOSTextStyle.caption1(
                    context,
                  ).copyWith(fontWeight: FontWeight.w700, color: Colors.white),
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      contact.displayName,
                      style: IOSTextStyle.subheadline(context).copyWith(
                        fontWeight: FontWeight.w700,
                        color: titleColor,
                        height: 1.2,
                      ),
                    ),
                    if (contact.title != null &&
                        contact.title!.trim().isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 2),
                        child: Text(
                          contact.title!.trim(),
                          style: IOSTextStyle.footnote(context).copyWith(
                            color: scheme.onSurface.withValues(alpha: 0.62),
                            height: 1.2,
                          ),
                        ),
                      ),
                    if (contact.email.isNotEmpty)
                      Padding(
                        padding: const EdgeInsets.only(top: 1),
                        child: Text(
                          contact.email,
                          style: IOSTextStyle.caption1(context).copyWith(
                            color: scheme.onSurface.withValues(alpha: 0.42),
                            height: 1.2,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
              if (contact.email.isNotEmpty) ...[
                IconButton(
                  visualDensity: VisualDensity.compact,
                  tooltip: localizations.email,
                  icon: Icon(
                    Icons.mail_outline_rounded,
                    size: 18,
                    color: scheme.onSurface.withValues(alpha: 0.45),
                  ),
                  onPressed: () {
                    HapticFeedback.lightImpact();
                    unawaited(
                      onLaunch(
                        context,
                        Uri(scheme: 'mailto', path: contact.email),
                      ),
                    );
                  },
                ),
                IconButton(
                  visualDensity: VisualDensity.compact,
                  tooltip: 'Teams',
                  icon: Icon(
                    Icons.chat_bubble_outline_rounded,
                    size: 18,
                    color: scheme.onSurface.withValues(alpha: 0.45),
                  ),
                  onPressed: () {
                    HapticFeedback.lightImpact();
                    final teamsUri = Uri.parse(
                      'https://teams.microsoft.com/l/chat/0/0?users='
                      '${Uri.encodeComponent(contact.email)}',
                    );
                    unawaited(onLaunch(context, teamsUri));
                  },
                ),
              ],
            ],
          ),
        ),
        if (showDivider)
          Padding(
            padding: const EdgeInsets.only(left: 62),
            child: Divider(height: 1, thickness: 1, color: borderColor),
          ),
      ],
    );
  }
}
