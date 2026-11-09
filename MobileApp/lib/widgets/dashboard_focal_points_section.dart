import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/shared/focal_point_contact.dart';
import '../l10n/app_localizations.dart';
import '../services/organization_config_service.dart';
import '../theme/grouped_dashboard_palette.dart';
import '../utils/constants.dart';
import '../utils/ios_constants.dart';
import 'dashboard_grouped_assignment_card.dart';

/// Distinct, stable avatar colors so each person is easy to tell apart.
const List<Color> _avatarPalette = GroupedDashboardPalette.avatarColors;

Color avatarColorFor(String key) {
  var hash = 0;
  for (final unit in key.codeUnits) {
    hash = (hash * 31 + unit) & 0x7fffffff;
  }
  return _avatarPalette[hash % _avatarPalette.length];
}

class DashboardFocalPointsSection extends StatefulWidget {
  const DashboardFocalPointsSection({
    super.key,
    required this.entityLabel,
    required this.nsFocalPoints,
    required this.orgFocalPoints,
    this.fdsMembers = const [],
  });

  final String entityLabel;
  final List<FocalPointContact> nsFocalPoints;
  final List<FocalPointContact> orgFocalPoints;
  final List<FocalPointContact> fdsMembers;

  @override
  State<DashboardFocalPointsSection> createState() =>
      _DashboardFocalPointsSectionState();
}

class _DashboardFocalPointsSectionState
    extends State<DashboardFocalPointsSection> {
  bool _expanded = true;

  List<FocalPointContact> get nsFocalPoints => widget.nsFocalPoints;
  List<FocalPointContact> get orgFocalPoints => widget.orgFocalPoints;
  List<FocalPointContact> get fdsMembers => widget.fdsMembers;
  String get entityLabel => widget.entityLabel;

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
    final hasContacts = nsFocalPoints.isNotEmpty ||
        orgFocalPoints.isNotEmpty ||
        fdsMembers.isNotEmpty;
    final total =
        nsFocalPoints.length + orgFocalPoints.length + fdsMembers.length;

    return Padding(
      padding: const EdgeInsets.fromLTRB(0, 8, 0, 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Semantics(
            button: true,
            expanded: _expanded,
            child: InkWell(
              onTap: () {
                HapticFeedback.selectionClick();
                setState(() => _expanded = !_expanded);
              },
              child: Padding(
                padding: const EdgeInsets.fromLTRB(20, 10, 20, 10),
                child: Row(
                  children: [
                    Expanded(
                      child: DashboardSectionLabel(
                        title: localizations.focalPoints,
                        count: hasContacts ? total : null,
                      ),
                    ),
                    AnimatedRotation(
                      turns: _expanded ? 0.5 : 0,
                      duration: const Duration(milliseconds: 200),
                      child: Icon(
                        Icons.expand_more_rounded,
                        size: 22,
                        color: scheme.onSurface.withValues(alpha: 0.48),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          if (_expanded)
            if (hasContacts)
              Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (nsFocalPoints.isNotEmpty)
                    _ContactGroup(
                      title: localizations.nationalSocietyFocalPoints,
                      contacts: nsFocalPoints,
                      onLaunch: _launchContactUri,
                    ),
                  if (orgFocalPoints.isNotEmpty)
                    _ContactGroup(
                      title: _orgFocalPointsTitle(localizations),
                      contacts: orgFocalPoints,
                      onLaunch: _launchContactUri,
                    ),
                  if (fdsMembers.isNotEmpty)
                    _ContactGroup(
                      title: localizations.translate('fds_member'),
                      contacts: fdsMembers,
                      onLaunch: _launchContactUri,
                    ),
                ],
              )
            else
              Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: 20,
                  vertical: 16,
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
          padding: const EdgeInsets.fromLTRB(20, 12, 20, 2),
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
        : GroupedDashboardPalette.hairline;

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 10, 14, 10),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              CircleAvatar(
                radius: 18,
                backgroundColor: avatar,
                child: Text(
                  contact.initials,
                  style: IOSTextStyle.caption1(context).copyWith(
                    fontWeight: FontWeight.w700,
                    color: GroupedDashboardPalette.onFill,
                  ),
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
                _ContactAction(
                  tooltip: localizations.email,
                  alignment: Alignment.centerRight,
                  onPressed: () {
                    HapticFeedback.lightImpact();
                    unawaited(
                      onLaunch(
                        context,
                        Uri(scheme: 'mailto', path: contact.email),
                      ),
                    );
                  },
                  child: Padding(
                    padding: const EdgeInsets.only(right: 3),
                    child: Icon(
                      Icons.mail_rounded,
                      size: 16,
                      color: _actionColor(
                        GroupedDashboardPalette.mailAction,
                        isDark,
                      ),
                    ),
                  ),
                ),
                _ContactAction(
                  tooltip: 'Teams',
                  alignment: Alignment.centerLeft,
                  onPressed: () {
                    HapticFeedback.lightImpact();
                    final teamsUri = Uri.parse(
                      'https://teams.microsoft.com/l/chat/0/0?users='
                      '${Uri.encodeComponent(contact.email)}',
                    );
                    unawaited(onLaunch(context, teamsUri));
                  },
                  child: Padding(
                    padding: const EdgeInsets.only(left: 3),
                    child: CustomPaint(
                      size: const Size(18, 18),
                      painter: _TeamsGlyphPainter(
                        _actionColor(
                          GroupedDashboardPalette.teamsAction,
                          isDark,
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
        if (showDivider)
          Padding(
            padding: const EdgeInsets.only(left: 70, right: 20),
            child: Divider(height: 1, thickness: 1, color: borderColor),
          ),
      ],
    );
  }
}

/// Lighten a brand color so a bare glyph stays visible on a dark row.
Color _actionColor(Color color, bool isDark) =>
    isDark ? Color.lerp(color, Colors.white, 0.42)! : color;

class _ContactAction extends StatelessWidget {
  const _ContactAction({
    required this.tooltip,
    required this.onPressed,
    required this.child,
    this.alignment = Alignment.center,
  });

  final String tooltip;
  final VoidCallback onPressed;
  final Widget child;
  final Alignment alignment;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: InkWell(
        onTap: onPressed,
        borderRadius: BorderRadius.circular(8),
        child: SizedBox(
          width: 28,
          height: 36,
          child: Align(alignment: alignment, child: child),
        ),
      ),
    );
  }
}

/// Two-person mark used for the Microsoft Teams chat action.
class _TeamsGlyphPainter extends CustomPainter {
  const _TeamsGlyphPainter(this.color);

  final Color color;

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()..color = color;
    final w = size.width;
    final h = size.height;

    canvas.drawCircle(Offset(w * 0.36, h * 0.26), w * 0.16, paint);
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(w * 0.12, h * 0.46, w * 0.48, h * 0.46),
        Radius.circular(w * 0.16),
      ),
      paint,
    );
    canvas.drawCircle(Offset(w * 0.74, h * 0.32), w * 0.11, paint);
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Rect.fromLTWH(w * 0.58, h * 0.48, w * 0.34, h * 0.32),
        Radius.circular(w * 0.12),
      ),
      paint,
    );
  }

  @override
  bool shouldRepaint(covariant _TeamsGlyphPainter oldDelegate) =>
      oldDelegate.color != color;
}
