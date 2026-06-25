import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/shared/focal_point_contact.dart';
import '../l10n/app_localizations.dart';
import '../services/organization_config_service.dart';
import '../utils/ios_constants.dart';
import '../utils/theme_extensions.dart';

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
      final shortName =
          OrganizationConfigService().config.organization.shortName.trim();
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

  Widget _buildContactRow(BuildContext context, FocalPointContact contact) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final localizations = AppLocalizations.of(context)!;

    return Padding(
      padding: EdgeInsets.symmetric(vertical: IOSSpacing.smOf(context)),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          CircleAvatar(
            radius: 18,
            backgroundColor: scheme.primary.withValues(alpha: 0.12),
            child: Text(
              contact.initials,
              style: IOSTextStyle.caption1(context).copyWith(
                fontWeight: FontWeight.w700,
                color: scheme.primary,
              ),
            ),
          ),
          SizedBox(width: IOSSpacing.mdOf(context)),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  contact.displayName,
                  style: IOSTextStyle.subheadline(context).copyWith(
                    fontWeight: FontWeight.w600,
                    color: scheme.onSurface,
                  ),
                ),
                if (contact.title != null && contact.title!.trim().isNotEmpty)
                  Padding(
                    padding: EdgeInsets.only(top: IOSSpacing.xsOf(context) / 2),
                    child: Text(
                      contact.title!.trim(),
                      style: IOSTextStyle.footnote(context).copyWith(
                        color: scheme.onSurface.withValues(alpha: 0.72),
                      ),
                    ),
                  ),
                Padding(
                  padding: EdgeInsets.only(top: IOSSpacing.xsOf(context) / 2),
                  child: Text(
                    contact.email,
                    style: IOSTextStyle.footnote(context).copyWith(
                      color: scheme.onSurface.withValues(alpha: 0.72),
                    ),
                  ),
                ),
              ],
            ),
          ),
          if (contact.email.isNotEmpty) ...[
            IconButton(
              visualDensity: VisualDensity.compact,
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
              tooltip: localizations.email,
              icon: Icon(
                Icons.mail_outline_rounded,
                size: 20,
                color: IOSColors.getSystemBlue(context),
              ),
              onPressed: () {
                HapticFeedback.lightImpact();
                unawaited(
                  _launchContactUri(
                    context,
                    Uri(scheme: 'mailto', path: contact.email),
                  ),
                );
              },
            ),
            IconButton(
              visualDensity: VisualDensity.compact,
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
              tooltip: 'Teams',
              icon: Icon(
                Icons.chat_bubble_outline_rounded,
                size: 20,
                color: IOSColors.getSystemBlue(context),
              ),
              onPressed: () {
                HapticFeedback.lightImpact();
                final teamsUri = Uri.parse(
                  'https://teams.microsoft.com/l/chat/0/0?users='
                  '${Uri.encodeComponent(contact.email)}',
                );
                unawaited(_launchContactUri(context, teamsUri));
              },
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildSubsection({
    required BuildContext context,
    required String title,
    required List<FocalPointContact> contacts,
  }) {
    if (contacts.isEmpty) return const SizedBox.shrink();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(
          title,
          style: IOSTextStyle.subheadline(context).copyWith(
            fontWeight: FontWeight.w700,
            color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.9),
          ),
        ),
        SizedBox(height: IOSSpacing.smOf(context)),
        ...contacts.map((contact) => _buildContactRow(context, contact)),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final localizations = AppLocalizations.of(context)!;
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final hasContacts =
        nsFocalPoints.isNotEmpty || orgFocalPoints.isNotEmpty;
    final iconColor =
        context.isDarkTheme ? scheme.tertiary : context.navyIconColor;

    return Theme(
      data: theme.copyWith(dividerColor: Colors.transparent),
      child: ExpansionTile(
        tilePadding: const EdgeInsets.symmetric(
          horizontal: IOSSpacing.lg,
          vertical: IOSSpacing.xs,
        ),
        minTileHeight: 44,
        dense: true,
        initiallyExpanded: false,
        backgroundColor: Colors.transparent,
        collapsedBackgroundColor: Colors.transparent,
        shape: const Border(),
        collapsedShape: const Border(),
        title: Row(
          children: [
            Icon(Icons.people_outline_rounded, size: 20, color: iconColor),
            SizedBox(width: IOSSpacing.smOf(context)),
            Expanded(
              child: Text(
                '${localizations.focalPointsFor} $entityLabel',
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: IOSTextStyle.subheadline(context).copyWith(
                  fontWeight: FontWeight.w600,
                  color: scheme.onSurface.withValues(alpha: 0.92),
                  height: 1.25,
                ),
              ),
            ),
          ],
        ),
        children: [
          Padding(
            padding: EdgeInsets.fromLTRB(
              IOSSpacing.lgOf(context),
              IOSSpacing.smOf(context),
              IOSSpacing.lgOf(context),
              IOSSpacing.lgOf(context),
            ),
            child: hasContacts
                ? Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _buildSubsection(
                        context: context,
                        title: localizations.nationalSocietyFocalPoints,
                        contacts: nsFocalPoints,
                      ),
                      if (nsFocalPoints.isNotEmpty &&
                          orgFocalPoints.isNotEmpty) ...[
                        SizedBox(height: IOSSpacing.mdOf(context)),
                        Divider(
                          color: const Color(0xFFDC2626).withValues(alpha: 0.55),
                          height: 1,
                        ),
                        SizedBox(height: IOSSpacing.mdOf(context)),
                      ],
                      _buildSubsection(
                        context: context,
                        title: _orgFocalPointsTitle(localizations),
                        contacts: orgFocalPoints,
                      ),
                    ],
                  )
                : Column(
                    children: [
                      Icon(
                        Icons.person_outline_rounded,
                        size: 48,
                        color: scheme.onSurface.withValues(alpha: 0.35),
                      ),
                      SizedBox(height: IOSSpacing.mdOf(context)),
                      Text(
                        '${localizations.noFocalPointsAssignedTo} $entityLabel ${localizations.yet}',
                        style: IOSTextStyle.subheadline(context).copyWith(
                          color: scheme.onSurface.withValues(alpha: 0.65),
                          fontWeight: FontWeight.w500,
                          height: 1.35,
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ],
                  ),
          ),
        ],
      ),
    );
  }
}
